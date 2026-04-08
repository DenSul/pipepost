"""Fused LLM transform — combine translate + rewrite + adapt in a single LLM call."""

from __future__ import annotations

import logging
import os
import re
from typing import TYPE_CHECKING

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from pipepost.core.registry import get_style, register_step
from pipepost.core.step import Step, StepBuildContext
from pipepost.exceptions import TranslateError


if TYPE_CHECKING:
    from pipepost.core.context import FlowContext

logger = logging.getLogger(__name__)

_CONTENT_LIMIT = 15000


class TransformStep(Step):
    """Fused LLM step: translate + rewrite + adapt in one call.

    Dynamically builds a combined prompt based on which operations are
    enabled. Saves LLM tokens by avoiding multiple round-trips with
    the same content.

    Config flags:
        translate: bool — translate to target_lang (default True)
        rewrite: bool — deep rewrite for uniqueness (default False)
        adapt: bool — adapt style (default False)
        style: str — adapt style name (default "blog")
    """

    name = "transform"

    def __init__(
        self,
        model: str | None = None,
        target_lang: str = "ru",
        max_tokens: int = 16384,
        do_translate: bool = True,
        do_rewrite: bool = False,
        do_adapt: bool = False,
        style: str = "blog",
        creativity: float = 0.5,
        min_ratio: float = 0.5,
        api_base: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.model = model or os.getenv("PIPEPOST_MODEL", "deepseek/deepseek-chat")
        self.target_lang = target_lang
        self.max_tokens = max_tokens
        self.do_translate = do_translate
        self.do_rewrite = do_rewrite
        self.do_adapt = do_adapt
        self.style = style
        self.creativity = creativity
        self.min_ratio = min_ratio
        self.api_base = api_base or os.getenv("OPENAI_API_BASE") or os.getenv("LITELLM_API_BASE")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")

    @classmethod
    def from_config(cls, build_ctx: StepBuildContext) -> TransformStep:
        """Create from StepBuildContext."""
        return cls(
            model=build_ctx.transform_model or build_ctx.model or None,
            target_lang=build_ctx.target_lang,
            max_tokens=build_ctx.max_tokens,
            do_translate=build_ctx.transform_translate,
            do_rewrite=build_ctx.transform_rewrite,
            do_adapt=build_ctx.transform_adapt,
            style=build_ctx.transform_style,
            creativity=build_ctx.transform_creativity,
        )

    def should_skip(self, ctx: FlowContext) -> bool:
        """Skip if no article selected."""
        return ctx.selected is None

    async def execute(self, ctx: FlowContext) -> FlowContext:
        """Run the fused transform."""
        if not ctx.selected:
            ctx.add_error("No article to transform")
            return ctx

        article = ctx.selected
        prompt = self._build_prompt(article.title, article.content)

        try:
            raw = await self._call_llm(prompt)
        except TranslateError:
            raise
        except Exception as exc:
            raise TranslateError(f"Transform LLM call failed: {exc}") from exc

        parsed = self._parse_output(raw)
        if not parsed:
            raise TranslateError("Failed to parse transform output")

        title_out = parsed.get("title", article.title)
        content_out = parsed.get("content", "")
        tags = parsed.get("tags", [])

        if isinstance(title_out, list):
            title_out = str(title_out[0]) if title_out else article.title
        if isinstance(content_out, list):
            content_out = str(content_out[0]) if content_out else ""
        if not isinstance(tags, list):
            tags = []

        from pipepost.core.context import TranslatedArticle

        ctx.translated = TranslatedArticle(
            title=article.title,
            title_translated=str(title_out),
            content=article.content,
            content_translated=str(content_out),
            source_url=article.url,
            source_name=ctx.source_name,
            tags=list(tags),
            cover_image=article.cover_image,
        )

        # If adapt is enabled, also store in metadata for consistency
        if self.do_adapt:
            ctx.metadata["adapted_title"] = str(title_out)
            ctx.metadata["adapted_content"] = str(content_out)

        return ctx

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
        before_sleep=lambda rs: logger.warning(
            "Transform LLM attempt %d failed: %s — retrying",
            rs.attempt_number,
            rs.outcome.exception() if rs.outcome else "unknown",
        ),
    )
    async def _call_llm(self, prompt: str) -> str:
        """Call LLM with retry."""
        import litellm

        # Higher creativity when rewriting, lower for pure translation
        temperature = self.creativity if self.do_rewrite else 0.3

        kwargs: dict[str, object] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self.max_tokens,
            "temperature": temperature,
        }
        if self.api_base:
            kwargs["api_base"] = self.api_base
        if self.api_key:
            kwargs["api_key"] = self.api_key
        response = await litellm.acompletion(**kwargs)
        return str(response.choices[0].message.content or "")

    def _build_prompt(self, title: str, content: str) -> str:
        """Build a dynamic combined prompt based on enabled operations."""
        operations: list[str] = []
        rules: list[str] = []

        # --- Translate ---
        if self.do_translate:
            lang = self.target_lang
            operations.append(f"TRANSLATE the article from English to {lang}")
            rules.append("Full paragraph-by-paragraph translation (NOT a summary)")

        # --- Rewrite ---
        if self.do_rewrite:
            if self.do_translate:
                operations.append(
                    "REWRITE the translated text to make it 100% unique and "
                    "undetectable by plagiarism checkers"
                )
            else:
                operations.append(
                    "REWRITE the article to make it 100% unique and "
                    "undetectable by plagiarism checkers"
                )
            rules.extend([
                "Rephrase EVERY sentence — no phrases from the original",
                "Change paragraph structure and ordering where logically possible",
                "Use synonyms and alternative constructions throughout",
            ])

        # --- Adapt ---
        if self.do_adapt:
            try:
                style_instruction = get_style(self.style)
            except KeyError:
                style_instruction = get_style("blog")
            operations.append(f"ADAPT for {self.style} format")
            rules.append(f"Style: {style_instruction}")

        # --- Common rules ---
        rules.extend([
            "Keep the same meaning and factual accuracy",
            "Keep all URLs, proper nouns, and domain-specific terminology unchanged",
            "Keep markdown formatting",
            "Output must be at least 80% of original length",
            "Do NOT add disclaimers, notes, or commentary",
        ])

        ops_text = " → ".join(operations) if operations else "Process"
        rules_text = "\n".join(f"- {r}" for r in rules)

        return (
            f"TASK: {ops_text}\n\n"
            f"RULES:\n{rules_text}\n\n"
            "OUTPUT FORMAT (use exact markers):\n"
            "===TITLE===\n<result title>\n"
            "===CONTENT===\n<result content in markdown>\n"
            "===TAGS===\n<comma-separated lowercase tags>\n\n"
            f"ARTICLE TITLE: {title}\n\n"
            f"ARTICLE CONTENT:\n{content[:_CONTENT_LIMIT]}"
        )

    def _parse_output(self, raw: str) -> dict[str, str | list[str]] | None:
        """Parse LLM output with ===SECTION=== markers."""
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
        parts = re.split(r"===([A-Z_]+)===", raw)
        sections: dict[str, str] = {}
        for i in range(1, len(parts) - 1, 2):
            sections[parts[i]] = parts[i + 1].strip()

        if "CONTENT" not in sections:
            return None

        tags_raw = sections.get("TAGS", "")
        tags = [t.strip().lower() for t in tags_raw.split(",") if t.strip()]

        return {
            "title": sections.get("TITLE", ""),
            "content": sections["CONTENT"],
            "tags": tags,
        }


register_step("transform", TransformStep)

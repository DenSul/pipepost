"""Rewrite article content to make it unique for search engines."""

from __future__ import annotations

import logging
import os
import re
from typing import TYPE_CHECKING

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from pipepost.core.registry import register_step
from pipepost.core.step import Step, StepBuildContext
from pipepost.exceptions import RewriteError


if TYPE_CHECKING:
    from pipepost.core.context import FlowContext

logger = logging.getLogger(__name__)

_CONTENT_LIMIT = 15000


class RewriteStep(Step):
    """Deeply rewrite article content via LLM so it appears original to search engines."""

    name = "rewrite"

    def __init__(
        self,
        model: str | None = None,
        target_lang: str = "ru",
        max_tokens: int = 16384,
        creativity: float = 0.7,
        api_base: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.model = model or os.getenv("PIPEPOST_MODEL", "deepseek/deepseek-chat")
        self.target_lang = target_lang
        self.max_tokens = max_tokens
        self.creativity = creativity
        self.api_base = api_base or os.getenv("OPENAI_API_BASE") or os.getenv("LITELLM_API_BASE")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")

    @classmethod
    def from_config(cls, build_ctx: StepBuildContext) -> RewriteStep:
        """Create from StepBuildContext."""
        return cls(
            model=build_ctx.rewrite_model or build_ctx.model or None,
            target_lang=build_ctx.target_lang,
            max_tokens=build_ctx.max_tokens,
            creativity=build_ctx.rewrite_creativity,
        )

    def should_skip(self, ctx: FlowContext) -> bool:
        """Skip if no article available."""
        return ctx.translated is None and ctx.selected is None

    async def execute(self, ctx: FlowContext) -> FlowContext:
        """Rewrite the article content to make it unique."""
        if ctx.translated:
            title = ctx.translated.title_translated
            content = ctx.translated.content_translated
        elif ctx.selected:
            title = ctx.selected.title
            content = ctx.selected.content
        else:
            ctx.add_error("No article to rewrite")
            return ctx

        prompt = self._build_prompt(title, content)
        try:
            raw = await self._call_llm(prompt)
        except RewriteError:
            raise
        except Exception as exc:
            raise RewriteError(f"LLM call failed after retries: {exc}") from exc

        parsed = self._parse_output(raw)
        if not parsed:
            raise RewriteError("Failed to parse rewrite output")

        title_rewritten = parsed.get("title_rewritten", title)
        content_rewritten = parsed.get("content_rewritten", "")

        if isinstance(title_rewritten, list):
            title_rewritten = str(title_rewritten[0]) if title_rewritten else title
        if isinstance(content_rewritten, list):
            content_rewritten = str(content_rewritten[0]) if content_rewritten else ""

        if ctx.translated:
            ctx.translated.title_translated = str(title_rewritten)
            ctx.translated.content_translated = str(content_rewritten)
        else:
            # Create TranslatedArticle from selected article
            from pipepost.core.context import TranslatedArticle

            article = ctx.selected
            assert article is not None  # noqa: S101
            ctx.translated = TranslatedArticle(
                title=article.title,
                title_translated=str(title_rewritten),
                content=article.content,
                content_translated=str(content_rewritten),
                source_url=article.url,
                source_name=ctx.source_name,
                tags=[],
                cover_image=article.cover_image,
            )

        return ctx

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
        before_sleep=lambda rs: logger.warning(
            "LLM rewrite attempt %d failed: %s — retrying",
            rs.attempt_number,
            rs.outcome.exception() if rs.outcome else "unknown",
        ),
    )
    async def _call_llm(self, prompt: str) -> str:
        """Call LLM with tenacity retry and exponential backoff."""
        import litellm

        kwargs: dict[str, object] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self.max_tokens,
            "temperature": self.creativity,
        }
        if self.api_base:
            kwargs["api_base"] = self.api_base
        if self.api_key:
            kwargs["api_key"] = self.api_key
        response = await litellm.acompletion(**kwargs)
        return str(response.choices[0].message.content or "")

    def _build_prompt(self, title: str, content: str) -> str:
        """Build rewrite prompt for deep content transformation."""
        return (
            "You are an expert content rewriter. Your task is to completely rewrite "
            "the following article so that it is 100% unique and undetectable by "
            "plagiarism checkers or search engine duplicate detection.\n\n"
            "RULES:\n"
            "- Rephrase EVERY sentence completely — no phrases from the original\n"
            "- Change paragraph structure and ordering where logically possible\n"
            "- Use synonyms and alternative constructions throughout\n"
            "- Keep the same meaning and factual accuracy\n"
            "- Keep all URLs, proper nouns, brand names, and technical terms unchanged\n"
            "- Keep markdown formatting\n"
            "- Output must be the SAME LANGUAGE as the input\n"
            "- Output must be at least 80% of the original length\n"
            "- Do NOT add disclaimers, notes, or commentary\n"
            "- Output format: use ===SECTION=== markers as shown below\n\n"
            "===TITLE_REWRITTEN===\n<completely rewritten title>\n"
            "===CONTENT_REWRITTEN===\n<fully rewritten content in markdown>\n\n"
            f"ORIGINAL TITLE: {title}\n\n"
            f"ORIGINAL CONTENT:\n{content[:_CONTENT_LIMIT]}"
        )

    def _parse_output(self, raw: str) -> dict[str, str] | None:
        """Parse LLM output into structured sections."""
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
        parts = re.split(r"===([A-Z_]+)===", raw)
        sections: dict[str, str] = {}
        for i in range(1, len(parts) - 1, 2):
            sections[parts[i]] = parts[i + 1].strip()

        if "CONTENT_REWRITTEN" not in sections:
            return None

        return {
            "title_rewritten": sections.get("TITLE_REWRITTEN", ""),
            "content_rewritten": sections["CONTENT_REWRITTEN"],
        }


register_step("rewrite", RewriteStep)

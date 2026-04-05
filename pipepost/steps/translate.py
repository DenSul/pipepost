"""Translate article content using LLM."""

from __future__ import annotations

import logging
import os
import re
from typing import TYPE_CHECKING

from pipepost.core.step import Step
from pipepost.exceptions import TranslateError


if TYPE_CHECKING:
    from pipepost.core.context import FlowContext

logger = logging.getLogger(__name__)

_MAX_RETRIES = 2
_CONTENT_LIMIT = 15000


class TranslateStep(Step):
    """Translate article via LLM (LiteLLM — supports 100+ models)."""

    name = "translate"

    def __init__(
        self,
        model: str | None = None,
        target_lang: str = "ru",
        max_tokens: int = 16384,
        min_ratio: float = 0.5,
    ) -> None:
        self.model = model or os.getenv("PIPEPOST_MODEL", "deepseek/deepseek-chat")
        self.target_lang = target_lang
        self.max_tokens = max_tokens
        self.min_ratio = min_ratio

    def should_skip(self, ctx: FlowContext) -> bool:
        """Skip if no article selected."""
        return ctx.selected is None

    async def execute(self, ctx: FlowContext) -> FlowContext:
        """Translate the selected article."""
        if not ctx.selected:
            ctx.add_error("No article to translate")
            return ctx

        article = ctx.selected
        prompt = self._build_prompt(article.title, article.content)
        raw = await self._call_llm(prompt)

        parsed = self._parse_output(raw)
        if not parsed:
            raise TranslateError("Failed to parse translation output")

        title_translated = parsed.get("title_translated", article.title)
        content_translated = parsed.get("content_translated", "")
        tags = parsed.get("tags", [])

        if isinstance(title_translated, list):
            title_translated = str(title_translated[0]) if title_translated else article.title
        if isinstance(content_translated, list):
            content_translated = str(content_translated[0]) if content_translated else ""
        if not isinstance(tags, list):
            tags = []

        if len(content_translated) < len(article.content) * self.min_ratio:
            logger.warning(
                "Translation too short: %d vs %d (ratio: %.1f%%)",
                len(content_translated),
                len(article.content),
                len(content_translated) / max(1, len(article.content)) * 100,
            )

        from pipepost.core.context import TranslatedArticle

        ctx.translated = TranslatedArticle(
            title=article.title,
            title_translated=str(title_translated),
            content=article.content,
            content_translated=str(content_translated),
            source_url=article.url,
            source_name=ctx.source_name,
            tags=list(tags),
            cover_image=article.cover_image,
        )
        return ctx

    async def _call_llm(self, prompt: str) -> str:
        """Call LLM with one retry on failure."""
        import litellm

        last_error: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                response = await litellm.acompletion(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=self.max_tokens,
                    temperature=0.3,
                )
                return str(response.choices[0].message.content or "")
            except Exception as exc:
                last_error = exc
                if attempt < _MAX_RETRIES - 1:
                    logger.warning(
                        "LLM call attempt %d failed: %s — retrying",
                        attempt + 1,
                        exc,
                    )
                    continue

        raise TranslateError(f"LLM call failed after {_MAX_RETRIES} attempts: {last_error}")

    def _build_prompt(self, title: str, content: str) -> str:
        """Build translation prompt — domain-agnostic."""
        lang = self.target_lang
        return (
            f"Translate the following article from English to {lang}.\n\n"
            "RULES:\n"
            "- Full paragraph-by-paragraph translation (NOT a summary)\n"
            "- Keep all URLs, proper nouns, and domain-specific terminology unchanged\n"
            "- Keep markdown formatting\n"
            "- Translation must be at least 80% of original length\n"
            "- Output format: use ===SECTION=== markers\n\n"
            "===TITLE_RU===\n<translated title>\n"
            "===CONTENT_RU===\n<full translated content in markdown>\n"
            "===TAGS===\n<comma-separated lowercase tags>\n\n"
            f"ARTICLE TITLE: {title}\n\n"
            f"ARTICLE CONTENT:\n{content[:_CONTENT_LIMIT]}"
        )

    def _parse_output(self, raw: str) -> dict[str, str | list[str]] | None:
        """Parse LLM output into structured sections."""
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
        parts = re.split(r"===([A-Z_]+)===", raw)
        sections: dict[str, str] = {}
        for i in range(1, len(parts) - 1, 2):
            sections[parts[i]] = parts[i + 1].strip()

        if "CONTENT_RU" not in sections:
            return None

        tags_raw = sections.get("TAGS", "")
        tags = [t.strip().lower() for t in tags_raw.split(",") if t.strip()]

        return {
            "title_translated": sections.get("TITLE_RU", ""),
            "content_translated": sections["CONTENT_RU"],
            "tags": tags,
        }

"""Translate article content using LLM."""

from __future__ import annotations

import logging
import os
import re

from pipepost.core.context import FlowContext, TranslatedArticle
from pipepost.core.step import Step

logger = logging.getLogger(__name__)


class TranslateStep(Step):
    name = "translate"

    def __init__(
        self,
        model: str | None = None,
        target_lang: str = "ru",
        max_tokens: int = 16384,
        min_ratio: float = 0.5,
    ):
        self.model = model or os.getenv("PIPEPOST_MODEL", "deepseek/deepseek-chat")
        self.target_lang = target_lang
        self.max_tokens = max_tokens
        self.min_ratio = min_ratio

    def should_skip(self, ctx: FlowContext) -> bool:
        return ctx.selected is None

    async def execute(self, ctx: FlowContext) -> FlowContext:
        if not ctx.selected:
            ctx.add_error("No article to translate")
            return ctx

        article = ctx.selected
        prompt = self._build_prompt(article.title, article.content)

        try:
            import litellm

            response = await litellm.acompletion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self.max_tokens,
                temperature=0.3,
            )
            raw = response.choices[0].message.content or ""
        except Exception as e:
            ctx.add_error(f"LLM call failed: {e}")
            return ctx

        parsed = self._parse_output(raw)
        if not parsed:
            ctx.add_error("Failed to parse translation output")
            return ctx

        title_translated = parsed.get("title_ru", article.title)
        content_translated = parsed.get("content_ru", "")
        tags = parsed.get("tags", ["tech"])

        if len(content_translated) < len(article.content) * self.min_ratio:
            logger.warning(
                "Translation too short: %d vs %d (ratio: %.1f%%)",
                len(content_translated),
                len(article.content),
                len(content_translated) / max(1, len(article.content)) * 100,
            )

        ctx.translated = TranslatedArticle(
            title=article.title,
            title_translated=title_translated,
            content=article.content,
            content_translated=content_translated,
            source_url=article.url,
            source_name=ctx.source_name,
            tags=tags,
            cover_image=article.cover_image,
        )
        return ctx

    def _build_prompt(self, title: str, content: str) -> str:
        lang = self.target_lang
        return (
            f"Translate the following tech article from English to {lang}.\n\n"
            "RULES:\n"
            "- Full paragraph-by-paragraph translation (NOT a summary)\n"
            "- Keep all code blocks, URLs, and technical terms unchanged\n"
            "- Keep markdown formatting\n"
            "- Translation must be at least 80% of original length\n"
            "- Output format: use ===SECTION=== markers\n\n"
            "===TITLE_RU===\n<translated title>\n"
            "===CONTENT_RU===\n<full translated content in markdown>\n"
            "===TAGS===\n<comma-separated lowercase tags>\n\n"
            f"ARTICLE TITLE: {title}\n\n"
            f"ARTICLE CONTENT:\n{content[:15000]}"
        )

    def _parse_output(self, raw: str) -> dict[str, str | list[str]] | None:
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
        parts = re.split(r"===([A-Z_]+)===", raw)
        sections: dict[str, str] = {}
        for i in range(1, len(parts) - 1, 2):
            sections[parts[i]] = parts[i + 1].strip()

        if "CONTENT_RU" not in sections:
            return None

        tags_raw = sections.get("TAGS", "tech")
        tags = [t.strip().lower() for t in tags_raw.split(",") if t.strip()]

        return {
            "title_ru": sections.get("TITLE_RU", ""),
            "content_ru": sections["CONTENT_RU"],
            "tags": tags or ["tech"],
        }

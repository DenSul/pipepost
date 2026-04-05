"""Adapt translated content for different output styles."""

from __future__ import annotations

import logging
import os
import re
from typing import TYPE_CHECKING

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from pipepost.core.registry import register_step
from pipepost.core.step import Step
from pipepost.exceptions import TranslateError


if TYPE_CHECKING:
    from pipepost.core.context import FlowContext, TranslatedArticle

logger = logging.getLogger(__name__)

_VALID_STYLES = frozenset({"blog", "telegram", "newsletter", "thread"})

_STYLE_INSTRUCTIONS: dict[str, str] = {
    "blog": (
        "Adapt this article for a blog post. Keep full content, improve structure "
        "with headers, add an engaging intro paragraph."
    ),
    "telegram": (
        "Adapt this article for a Telegram channel post. Maximum 1000 characters. "
        "Keep the key insight, make it punchy and engaging. Add 2-3 relevant emoji."
    ),
    "newsletter": (
        "Adapt this article for an email newsletter. Add a brief 2-sentence summary "
        "at the top, then the key points as bullet list, then a 'Read more' CTA."
    ),
    "thread": (
        "Adapt this article into a Twitter/X thread format. Break into 5-8 numbered "
        "tweets (max 280 chars each). First tweet should hook the reader. Last tweet "
        "should have a takeaway."
    ),
}


class AdaptStep(Step):
    """Adapt translated content for a specific output style (blog, telegram, etc.)."""

    name = "adapt"

    def __init__(
        self,
        model: str | None = None,
        style: str = "blog",
        target_lang: str = "ru",
        max_tokens: int = 16384,
    ) -> None:
        self.model = model or os.getenv("PIPEPOST_MODEL", "deepseek/deepseek-chat")
        self.style = style
        self.target_lang = target_lang
        self.max_tokens = max_tokens

    def should_skip(self, ctx: FlowContext) -> bool:
        """Skip if no translated article."""
        return ctx.translated is None

    async def execute(self, ctx: FlowContext) -> FlowContext:
        """Adapt the translated article for the configured style."""
        if not ctx.translated:
            ctx.add_error("No translated article to adapt")
            return ctx

        article = ctx.translated
        prompt = self._build_prompt(article)
        try:
            raw = await self._call_llm(prompt)
        except TranslateError:
            raise
        except Exception as exc:
            raise TranslateError(f"LLM call failed after retries: {exc}") from exc

        parsed = self._parse_output(raw)
        if not parsed:
            raise TranslateError("Failed to parse adaptation output")

        ctx.metadata["adapted_title"] = parsed["adapted_title"]
        ctx.metadata["adapted_content"] = parsed["adapted_content"]
        return ctx

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
        before_sleep=lambda rs: logger.warning(
            "LLM call attempt %d failed: %s — retrying",
            rs.attempt_number,
            rs.outcome.exception(),
        ),
    )
    async def _call_llm(self, prompt: str) -> str:
        """Call LLM with tenacity retry and exponential backoff."""
        import litellm

        response = await litellm.acompletion(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=self.max_tokens,
            temperature=0.3,
        )
        return str(response.choices[0].message.content or "")

    def _build_prompt(self, article: TranslatedArticle) -> str:
        """Build adaptation prompt based on the configured style."""
        instruction = _STYLE_INSTRUCTIONS.get(self.style, _STYLE_INSTRUCTIONS["blog"])
        lang = self.target_lang
        return (
            f"{instruction} Output in {lang}.\n\n"
            f"ORIGINAL TITLE: {article.title_translated}\n\n"
            f"ORIGINAL CONTENT:\n{article.content_translated}\n\n"
            "Output format:\n"
            "===ADAPTED_TITLE===\n(adapted title here)\n"
            "===ADAPTED_CONTENT===\n(adapted content here)\n"
        )

    def _parse_output(self, raw: str) -> dict[str, str] | None:
        """Parse the LLM response for ADAPTED_TITLE and ADAPTED_CONTENT sections."""
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
        parts = re.split(r"===([A-Z_]+)===", raw)
        sections: dict[str, str] = {}
        for i in range(1, len(parts) - 1, 2):
            sections[parts[i]] = parts[i + 1].strip()

        if "ADAPTED_CONTENT" not in sections:
            return None

        return {
            "adapted_title": sections.get("ADAPTED_TITLE", ""),
            "adapted_content": sections["ADAPTED_CONTENT"],
        }


register_step("adapt", AdaptStep)

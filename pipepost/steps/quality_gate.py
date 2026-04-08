"""Quality gate — reject low-quality articles before expensive LLM steps."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from pipepost.core.registry import register_step
from pipepost.core.step import Step, StepBuildContext


if TYPE_CHECKING:
    from pipepost.core.context import FlowContext

logger = logging.getLogger(__name__)

# Common boilerplate patterns that inflate content length without adding value.
_BOILERPLATE_PATTERNS = [
    re.compile(r"(?i)subscribe\s+to\s+(our\s+)?newsletter"),
    re.compile(r"(?i)sign\s+up\s+(for|to)\s+(our\s+)?"),
    re.compile(r"(?i)cookie\s+(policy|consent|preferences)"),
    re.compile(r"(?i)privacy\s+policy"),
    re.compile(r"(?i)terms\s+(of|and)\s+(service|use)"),
    re.compile(r"(?i)share\s+(this|on)\s+(twitter|facebook|linkedin|reddit)"),
    re.compile(r"(?i)related\s+(articles?|posts?|stories)"),
    re.compile(r"(?i)you\s+may\s+also\s+like"),
    re.compile(r"(?i)advertisement"),
    re.compile(r"(?i)sponsored\s+(content|post)"),
]


class QualityGateStep(Step):
    """Reject articles that don't meet quality thresholds.

    Runs AFTER fetch but BEFORE any LLM steps to save tokens on bad content.

    Checks:
        - Minimum content length (after boilerplate strip)
        - Minimum paragraph count
        - Boilerplate ratio (too much junk = reject)
        - Code-to-text ratio (pure code dumps = reject)
        - Minimum unique word count (catches repetitive/spammy content)
    """

    name = "quality_gate"

    def __init__(
        self,
        min_content_len: int = 500,
        min_paragraphs: int = 3,
        max_boilerplate_ratio: float = 0.4,
        max_code_ratio: float = 0.7,
        min_unique_words: int = 50,
    ) -> None:
        self.min_content_len = min_content_len
        self.min_paragraphs = min_paragraphs
        self.max_boilerplate_ratio = max_boilerplate_ratio
        self.max_code_ratio = max_code_ratio
        self.min_unique_words = min_unique_words

    @classmethod
    def from_config(cls, build_ctx: StepBuildContext) -> QualityGateStep:
        """Create from StepBuildContext."""
        return cls(
            min_content_len=build_ctx.qg_min_content_len,
            min_paragraphs=build_ctx.qg_min_paragraphs,
            max_boilerplate_ratio=build_ctx.qg_max_boilerplate_ratio,
            max_code_ratio=build_ctx.qg_max_code_ratio,
            min_unique_words=build_ctx.qg_min_unique_words,
        )

    def should_skip(self, ctx: FlowContext) -> bool:
        """Skip if no article fetched yet."""
        return ctx.selected is None

    async def execute(self, ctx: FlowContext) -> FlowContext:
        """Run quality checks on the selected article."""
        if not ctx.selected:
            ctx.add_error("No article for quality check")
            return ctx

        content = ctx.selected.content
        failures: list[str] = []

        # 1. Strip boilerplate and measure ratio
        clean_content, boilerplate_ratio = self._strip_boilerplate(content)
        if boilerplate_ratio > self.max_boilerplate_ratio:
            failures.append(
                f"Boilerplate ratio too high: {boilerplate_ratio:.0%} "
                f"(max {self.max_boilerplate_ratio:.0%})"
            )

        # 2. Content length after boilerplate removal
        if len(clean_content) < self.min_content_len:
            failures.append(
                f"Content too short after cleanup: {len(clean_content)} "
                f"(min {self.min_content_len})"
            )

        # 3. Paragraph count
        paragraphs = [p.strip() for p in clean_content.split("\n\n") if p.strip()]
        if len(paragraphs) < self.min_paragraphs:
            failures.append(f"Too few paragraphs: {len(paragraphs)} (min {self.min_paragraphs})")

        # 4. Code ratio
        code_ratio = self._code_ratio(content)
        if code_ratio > self.max_code_ratio:
            failures.append(
                f"Code ratio too high: {code_ratio:.0%} (max {self.max_code_ratio:.0%})"
            )

        # 5. Unique words
        words = re.findall(r"[a-zA-Z\u0400-\u04FF]{3,}", clean_content.lower())
        unique_words = len(set(words))
        if unique_words < self.min_unique_words:
            failures.append(f"Too few unique words: {unique_words} (min {self.min_unique_words})")

        if failures:
            reason = "; ".join(failures)
            logger.warning(
                "Quality gate REJECTED '%s': %s",
                ctx.selected.title[:60],
                reason,
            )
            ctx.add_error(f"Quality gate rejected: {reason}")
            ctx.selected = None  # Clear so downstream steps skip
            return ctx

        logger.info(
            "Quality gate PASSED '%s' (len=%d, paragraphs=%d, "
            "boilerplate=%.0f%%, code=%.0f%%, unique_words=%d)",
            ctx.selected.title[:60],
            len(clean_content),
            len(paragraphs),
            boilerplate_ratio * 100,
            code_ratio * 100,
            unique_words,
        )
        return ctx

    def _strip_boilerplate(self, content: str) -> tuple[str, float]:
        """Remove boilerplate lines and return (clean_text, boilerplate_ratio)."""
        lines = content.split("\n")
        clean_lines: list[str] = []
        boilerplate_count = 0

        for line in lines:
            is_boilerplate = any(p.search(line) for p in _BOILERPLATE_PATTERNS)
            if is_boilerplate:
                boilerplate_count += 1
            else:
                clean_lines.append(line)

        total = len(lines) or 1
        ratio = boilerplate_count / total
        return "\n".join(clean_lines), ratio

    def _code_ratio(self, content: str) -> float:
        """Calculate ratio of content inside code blocks."""
        code_blocks = re.findall(r"```[\s\S]*?```", content)
        code_len = sum(len(block) for block in code_blocks)
        total = len(content) or 1
        return code_len / total


register_step("quality_gate", QualityGateStep)

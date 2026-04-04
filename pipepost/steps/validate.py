"""Validate translated article quality."""
from __future__ import annotations

import logging

from pipepost.core.context import FlowContext
from pipepost.core.step import Step

logger = logging.getLogger(__name__)


class ValidateStep(Step):
    """Check translated article meets minimum quality thresholds."""

    name = "validate"

    def __init__(self, min_content_len: int = 300, min_ratio: float = 0.3) -> None:
        self.min_content_len = min_content_len
        self.min_ratio = min_ratio

    def should_skip(self, ctx: FlowContext) -> bool:
        return ctx.translated is None

    async def execute(self, ctx: FlowContext) -> FlowContext:
        t = ctx.translated
        if not t:
            ctx.add_error("No translated article to validate")
            return ctx

        issues: list[str] = []

        if not t.title_translated:
            issues.append("Missing translated title")

        if len(t.content_translated) < self.min_content_len:
            issues.append(
                f"Translation too short: {len(t.content_translated)} < {self.min_content_len}"
            )

        original_len = len(t.content)
        if original_len > 0:
            ratio = len(t.content_translated) / original_len
            if ratio < self.min_ratio:
                issues.append(f"Translation ratio too low: {ratio:.1%} < {self.min_ratio:.0%}")

        if not t.source_url:
            issues.append("Missing source URL")

        if issues:
            for issue in issues:
                ctx.add_error(f"[validate] {issue}")
                logger.warning("Validation: %s", issue)
        else:
            logger.info(
                "Validation passed: %s (%d chars)",
                t.title_translated[:50],
                len(t.content_translated),
            )

        return ctx

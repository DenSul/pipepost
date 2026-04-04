"""Validate translated article quality."""

from __future__ import annotations

import logging

from pipepost.core.context import FlowContext
from pipepost.core.step import Step

logger = logging.getLogger(__name__)


class ValidateStep(Step):
    name = "validate"

    def __init__(self, min_content_len: int = 300, min_ratio: float = 0.3):
        self.min_content_len = min_content_len
        self.min_ratio = min_ratio

    def should_skip(self, ctx: FlowContext) -> bool:
        return ctx.translated is None

    async def execute(self, ctx: FlowContext) -> FlowContext:
        t = ctx.translated
        if not t:
            ctx.add_error("No translated article to validate")
            return ctx

        if not t.title_translated:
            ctx.add_error("[validate] Missing translated title")

        if len(t.content_translated) < self.min_content_len:
            ctx.add_error(
                f"[validate] Translation too short: {len(t.content_translated)} < {self.min_content_len}"
            )

        original_len = len(t.content)
        if original_len > 0:
            ratio = len(t.content_translated) / original_len
            if ratio < self.min_ratio:
                ctx.add_error(f"[validate] Translation ratio too low: {ratio:.1%} < {self.min_ratio:.0%}")

        if not t.source_url:
            ctx.add_error("[validate] Missing source URL")

        if not ctx.has_errors:
            logger.info(
                "Validation passed: %s (%d chars)",
                t.title_translated[:50],
                len(t.content_translated),
            )

        return ctx

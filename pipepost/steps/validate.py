"""Validate translated article quality."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pipepost.core.registry import register_step
from pipepost.core.step import Step


if TYPE_CHECKING:
    from pipepost.core.context import FlowContext

logger = logging.getLogger(__name__)


class ValidateStep(Step):
    """Check translation quality (length, ratio, required fields)."""

    name = "validate"

    def __init__(self, min_content_len: int = 300, min_ratio: float = 0.3) -> None:
        self.min_content_len = min_content_len
        self.min_ratio = min_ratio

    def should_skip(self, ctx: FlowContext) -> bool:
        """Skip if no translated article."""
        return ctx.translated is None

    async def execute(self, ctx: FlowContext) -> FlowContext:
        """Validate the translated article."""
        translated = ctx.translated
        if not translated:
            ctx.add_error("No translated article to validate")
            return ctx

        if not translated.title_translated:
            ctx.add_error("[validate] Missing translated title")

        if len(translated.content_translated) < self.min_content_len:
            ctx.add_error(
                f"[validate] Translation too short: "
                f"{len(translated.content_translated)} < {self.min_content_len}",
            )

        original_len = len(translated.content)
        if original_len > 0:
            ratio = len(translated.content_translated) / original_len
            if ratio < self.min_ratio:
                ctx.add_error(
                    f"[validate] Translation ratio too low: {ratio:.1%} < {self.min_ratio:.0%}",
                )

        if not translated.source_url:
            ctx.add_error("[validate] Missing source URL")

        if not ctx.has_errors:
            logger.info(
                "Validation passed: %s (%d chars)",
                translated.title_translated[:50],
                len(translated.content_translated),
            )

        return ctx


register_step("validate", ValidateStep)

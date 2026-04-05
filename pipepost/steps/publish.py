"""Publish translated article to a destination."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pipepost.core.registry import register_step
from pipepost.core.step import Step
from pipepost.exceptions import PublishError
from pipepost.metrics import metrics


if TYPE_CHECKING:
    from pipepost.core.context import FlowContext

logger = logging.getLogger(__name__)


class PublishStep(Step):
    """Send translated article to configured destination."""

    name = "publish"

    def __init__(self, destination_name: str = "default") -> None:
        self.destination_name = destination_name

    def should_skip(self, ctx: FlowContext) -> bool:
        """Skip if no translated article, errors present, or dry run."""
        if ctx.metadata.get("dry_run"):
            logger.info("Dry run — skipping publish")
            return True
        return ctx.translated is None or ctx.has_errors

    async def execute(self, ctx: FlowContext) -> FlowContext:
        """Publish translated article to destination."""
        from pipepost.core.context import PublishResult
        from pipepost.core.registry import get_destination

        dest = get_destination(self.destination_name)
        translated = ctx.translated
        if not translated:
            ctx.add_error("No article to publish")
            return ctx

        try:
            result = await dest.publish(translated)
            ctx.published = result
            if result.success:
                logger.info("Published to %s: %s", self.destination_name, result.slug)
                metrics.record_published(self.destination_name)
            else:
                ctx.add_error(f"Publish failed: {result.error}")
        except PublishError:
            raise
        except Exception as exc:
            error_msg = f"Publish to '{self.destination_name}' failed: {exc}"
            ctx.published = PublishResult(success=False, error=str(exc))
            ctx.add_error(error_msg)
            logger.error(error_msg)

        return ctx


register_step("publish", PublishStep)

"""Publish translated article to a destination."""
from __future__ import annotations

import logging

from pipepost.core.context import FlowContext, PublishResult
from pipepost.core.step import Step

logger = logging.getLogger(__name__)


class PublishStep(Step):
    """Send translated article to a registered destination."""

    name = "publish"

    def __init__(self, destination_name: str = "default") -> None:
        self.destination_name = destination_name

    def should_skip(self, ctx: FlowContext) -> bool:
        return ctx.translated is None or ctx.has_errors

    async def execute(self, ctx: FlowContext) -> FlowContext:
        from pipepost.core.registry import get_destination

        dest = get_destination(self.destination_name)
        t = ctx.translated
        if not t:
            ctx.add_error("No article to publish")
            return ctx

        try:
            result = await dest.publish(t)
            ctx.published = result
            if result.success:
                logger.info("Published to %s: %s", self.destination_name, result.slug)
            else:
                ctx.add_error(f"Publish failed: {result.error}")
        except Exception as e:
            ctx.published = PublishResult(success=False, error=str(e))
            ctx.add_error(f"Publish error: {e}")

        return ctx

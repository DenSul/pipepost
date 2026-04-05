"""Publish translated article to multiple destinations concurrently."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from pipepost.core.registry import register_step
from pipepost.core.step import Step
from pipepost.metrics import metrics


if TYPE_CHECKING:
    from pipepost.core.context import FlowContext
    from pipepost.destinations.base import Destination

logger = logging.getLogger(__name__)


class FanoutPublishStep(Step):
    """Publish to multiple destinations simultaneously via asyncio.gather."""

    name = "fanout_publish"

    def __init__(
        self,
        destination_names: list[str],
        *,
        stop_on_first_error: bool = False,
    ) -> None:
        self.destination_names = destination_names
        self.stop_on_first_error = stop_on_first_error

    def should_skip(self, ctx: FlowContext) -> bool:
        """Skip if no translated article, errors present, or dry run."""
        if ctx.metadata.get("dry_run"):
            logger.info("Dry run — skipping fanout publish")
            return True
        return ctx.translated is None or ctx.has_errors

    async def execute(self, ctx: FlowContext) -> FlowContext:
        """Publish translated article to all configured destinations."""
        from pipepost.core.context import PublishResult
        from pipepost.core.registry import get_destination

        translated = ctx.translated
        if not translated:
            ctx.add_error("No article to publish")
            return ctx

        # Resolve destinations up front; unknown names become errors.
        destinations: list[tuple[str, Destination]] = []
        for name in self.destination_names:
            try:
                dest = get_destination(name)
            except KeyError:
                error_msg = f"Unknown destination '{name}'"
                ctx.add_error(error_msg)
                logger.error(error_msg)
                continue
            destinations.append((name, dest))

        if not destinations:
            return ctx

        # Launch all publishes concurrently.
        async def _publish(dest_name: str, dest: Destination) -> tuple[str, PublishResult]:
            try:
                result = await dest.publish(translated)
            except Exception as exc:
                return dest_name, PublishResult(success=False, error=str(exc))
            return dest_name, result

        gathered = await asyncio.gather(
            *[_publish(n, d) for n, d in destinations],
            return_exceptions=True,
        )

        # Collect results.
        fanout_results: dict[str, dict[str, object]] = {}
        first_success: PublishResult | None = None
        success_count = 0
        summary_parts: list[str] = []

        for item in gathered:
            # return_exceptions=True means items may be BaseException
            if isinstance(item, BaseException):
                # Shouldn't happen since _publish catches, but be safe
                continue

            dest_name, result = item
            fanout_results[dest_name] = {
                "success": result.success,
                "slug": result.slug,
                "url": result.url,
                "error": result.error,
            }

            if result.success:
                success_count += 1
                summary_parts.append(f"{dest_name} \u2713")
                metrics.record_published(dest_name)
                if first_success is None:
                    first_success = result
            else:
                summary_parts.append(f"{dest_name} \u2717")
                error_msg = f"Fanout publish to '{dest_name}' failed: {result.error}"
                if self.stop_on_first_error:
                    ctx.add_error(error_msg)
                logger.warning(error_msg)

        ctx.metadata["fanout_results"] = fanout_results
        ctx.published = first_success

        total = len(destinations)
        summary = ", ".join(summary_parts)
        logger.info("Published to %d/%d destinations (%s)", success_count, total, summary)

        return ctx


register_step("fanout_publish", FanoutPublishStep)

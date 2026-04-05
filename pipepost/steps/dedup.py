"""Deduplication steps — load existing URLs and persist new ones."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pipepost.core.step import Step


if TYPE_CHECKING:
    from pipepost.core.context import FlowContext
    from pipepost.storage.sqlite import SQLiteStorage

logger = logging.getLogger(__name__)


class DeduplicationStep(Step):
    """Load previously published URLs into the flow context."""

    name = "dedup"

    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage

    async def execute(self, ctx: FlowContext) -> FlowContext:
        """Populate ctx.existing_urls from persistent storage."""
        ctx.existing_urls = self.storage.load_existing_urls()
        logger.info("Loaded %d existing URLs for dedup", len(ctx.existing_urls))
        return ctx

    def should_skip(self, ctx: FlowContext) -> bool:  # noqa: ARG002
        """Never skip — always load existing URLs."""
        return False


class PostPublishStep(Step):
    """Persist a successfully published URL to storage."""

    name = "post_publish"

    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage

    def should_skip(self, ctx: FlowContext) -> bool:
        """Skip if nothing was published or publish failed."""
        if ctx.published is None:
            return True
        return not ctx.published.success

    async def execute(self, ctx: FlowContext) -> FlowContext:
        """Record the published URL in persistent storage."""
        if ctx.selected and ctx.published and ctx.published.success:
            self.storage.mark_published(
                url=ctx.selected.url,
                source_name=ctx.source_name,
                slug=ctx.published.slug,
            )
            logger.info("Persisted published URL: %s", ctx.selected.url)
        return ctx

"""Batch runner — process multiple articles in a single invocation."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from pipepost.core.context import FlowContext
from pipepost.core.registry import get_destination, get_source
from pipepost.steps.fetch import FetchStep
from pipepost.steps.translate import TranslateStep
from pipepost.steps.validate import ValidateStep
from pipepost.storage.sqlite import SQLiteStorage


if TYPE_CHECKING:
    from pipepost.core.context import Candidate

logger = logging.getLogger(__name__)

__all__ = ["run_batch"]


async def run_batch(
    source_name: str,
    target_lang: str = "ru",
    max_articles: int = 3,
    destination_name: str = "default",
    db_path: str = "pipepost.db",
    dry_run: bool = False,
) -> list[FlowContext]:
    """Scout candidates, then process top-N articles through the pipeline.

    1. Load existing URLs from storage for dedup
    2. Scout candidates from the source
    3. Pick top ``max_articles`` candidates (after dedup)
    4. Translate candidates concurrently with ``asyncio.gather``
    5. Publish sequentially to avoid destination rate limits
    6. Persist each successfully published URL

    Returns a list of :class:`FlowContext` results, one per article.
    """
    storage = SQLiteStorage(db_path)
    existing_urls = storage.load_existing_urls()

    # Scout ----------------------------------------------------------------
    source = get_source(source_name)
    raw_candidates = await source.fetch_candidates(limit=30)
    filtered = [c for c in raw_candidates if c.url not in existing_urls]

    if not filtered:
        logger.info("Batch: no new candidates after dedup filtering")
        storage.close()
        return []

    selected = filtered[:max_articles]
    logger.info(
        "Batch: %d candidates scouted, %d after dedup, processing %d",
        len(raw_candidates),
        len(filtered),
        len(selected),
    )

    # Fetch + translate in parallel ----------------------------------------
    translate_tasks = [
        _fetch_and_translate(
            candidate=candidate,
            source_name=source_name,
            target_lang=target_lang,
            existing_urls=existing_urls,
            dry_run=dry_run,
        )
        for candidate in selected
    ]
    contexts: list[FlowContext] = list(await asyncio.gather(*translate_tasks))

    # Publish sequentially -------------------------------------------------
    dest = get_destination(destination_name)
    succeeded = 0
    failed = 0

    for ctx in contexts:
        if ctx.has_errors or ctx.translated is None:
            failed += 1
            continue

        if dry_run:
            succeeded += 1
            continue

        try:
            result = await dest.publish(ctx.translated)
            ctx.published = result
            if result.success:
                succeeded += 1
                if ctx.selected:
                    storage.mark_published(
                        url=ctx.selected.url,
                        source_name=source_name,
                        slug=result.slug,
                    )
            else:
                ctx.add_error(f"Publish failed: {result.error}")
                failed += 1
        except Exception as exc:
            ctx.add_error(f"Publish error: {exc}")
            failed += 1

    storage.close()

    skipped = len(selected) - succeeded - failed
    logger.info(
        "Processed %d/%d articles (%d failed, %d skipped)",
        succeeded,
        len(selected),
        failed,
        skipped,
    )

    return contexts


async def _fetch_and_translate(
    candidate: Candidate,
    source_name: str,
    target_lang: str,
    existing_urls: set[str],
    dry_run: bool,
) -> FlowContext:
    """Run fetch -> translate -> validate for a single candidate."""
    ctx = FlowContext(
        candidates=[candidate],
        source_name=source_name,
        target_lang=target_lang,
        existing_urls=existing_urls,
        metadata={"dry_run": True} if dry_run else {},
    )

    fetch_step = FetchStep()
    translate_step = TranslateStep(target_lang=target_lang)
    validate_step = ValidateStep()

    try:
        ctx = await fetch_step.execute(ctx)
    except Exception as exc:
        ctx.add_error(f"Fetch failed: {exc}")
        return ctx

    if ctx.selected is None:
        ctx.add_error("No article fetched")
        return ctx

    try:
        ctx = await translate_step.execute(ctx)
    except Exception as exc:
        ctx.add_error(f"Translate failed: {exc}")
        return ctx

    try:
        ctx = await validate_step.execute(ctx)
    except Exception as exc:
        ctx.add_error(f"Validate failed: {exc}")

    return ctx

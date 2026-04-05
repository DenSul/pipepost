"""Tests for batch runner — process multiple articles per run."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pipepost.core.context import (
    Article,
    Candidate,
    FlowContext,
    PublishResult,
    TranslatedArticle,
)


def _make_candidates(n: int) -> list[Candidate]:
    """Create *n* unique candidates."""
    return [
        Candidate(
            url=f"https://example.com/article-{i}",
            title=f"Article {i}",
            snippet=f"Snippet {i}",
            score=float(n - i),
            source_name="test-source",
        )
        for i in range(1, n + 1)
    ]


def _mock_source(candidates: list[Candidate]) -> MagicMock:
    source = MagicMock()
    source.fetch_candidates = AsyncMock(return_value=candidates)
    return source


def _translated_article(idx: int) -> TranslatedArticle:
    return TranslatedArticle(
        title=f"Article {idx}",
        title_translated=f"Translated {idx}",
        content="Original content " * 30,
        content_translated="Translated content " * 30,
        source_url=f"https://example.com/article-{idx}",
        source_name="test-source",
        tags=["test"],
    )


def _mock_fetch_and_translate(succeed: bool = True, idx: int = 1) -> AsyncMock:
    """Return an async function that produces a FlowContext."""

    async def _inner(
        candidate: Candidate,
        source_name: str,
        target_lang: str,
        existing_urls: set[str],
        dry_run: bool,
    ) -> FlowContext:
        ctx = FlowContext(
            candidates=[candidate],
            source_name=source_name,
            target_lang=target_lang,
            existing_urls=existing_urls,
        )
        if succeed:
            ctx.selected = Article(
                url=candidate.url,
                title=candidate.title,
                content="Original content " * 30,
            )
            ctx.translated = _translated_article(idx)
        else:
            ctx.add_error("Fetch failed: simulated")
        return ctx

    return AsyncMock(side_effect=_inner)


class TestBatchProcessesMultipleArticles:
    @pytest.mark.asyncio
    async def test_batch_processes_multiple_articles(self, tmp_path):
        """Mock source with 5 candidates, max_articles=3, verify 3 processed."""
        candidates = _make_candidates(5)
        source = _mock_source(candidates)
        dest = AsyncMock()
        dest.publish = AsyncMock(
            side_effect=[
                PublishResult(success=True, slug=f"slug-{i}", url=f"/out/slug-{i}.md")
                for i in range(1, 6)
            ]
        )
        db_path = str(tmp_path / "test.db")

        with (
            patch("pipepost.batch.get_source", return_value=source),
            patch("pipepost.batch.get_destination", return_value=dest),
            patch("pipepost.batch._fetch_and_translate") as mock_ft,
        ):
            # Each call returns a successful context
            async def _ft(candidate, source_name, target_lang, existing_urls, dry_run):
                ctx = FlowContext(
                    candidates=[candidate],
                    source_name=source_name,
                    target_lang=target_lang,
                )
                ctx.selected = Article(
                    url=candidate.url,
                    title=candidate.title,
                    content="content " * 30,
                )
                ctx.translated = TranslatedArticle(
                    title=candidate.title,
                    title_translated=f"Translated {candidate.title}",
                    content="content " * 30,
                    content_translated="translated " * 30,
                    source_url=candidate.url,
                    tags=["test"],
                )
                return ctx

            mock_ft.side_effect = _ft

            from pipepost.batch import run_batch

            results = await run_batch(
                source_name="test-source",
                max_articles=3,
                destination_name="default",
                db_path=db_path,
            )

        assert len(results) == 3
        assert dest.publish.call_count == 3


class TestBatchRespectsMaxArticles:
    @pytest.mark.asyncio
    async def test_batch_respects_max_articles(self, tmp_path):
        """Verify only N articles processed even when more candidates exist."""
        candidates = _make_candidates(10)
        source = _mock_source(candidates)
        dest = AsyncMock()
        dest.publish = AsyncMock(
            return_value=PublishResult(success=True, slug="s", url="/out/s.md")
        )
        db_path = str(tmp_path / "test.db")

        with (
            patch("pipepost.batch.get_source", return_value=source),
            patch("pipepost.batch.get_destination", return_value=dest),
            patch("pipepost.batch._fetch_and_translate") as mock_ft,
        ):

            async def _ft(candidate, source_name, target_lang, existing_urls, dry_run):
                ctx = FlowContext(candidates=[candidate], source_name=source_name)
                ctx.selected = Article(url=candidate.url, title=candidate.title, content="c " * 30)
                ctx.translated = TranslatedArticle(
                    title=candidate.title,
                    title_translated="T",
                    content="c " * 30,
                    content_translated="t " * 30,
                    source_url=candidate.url,
                )
                return ctx

            mock_ft.side_effect = _ft

            from pipepost.batch import run_batch

            results = await run_batch(
                source_name="test-source",
                max_articles=2,
                destination_name="default",
                db_path=db_path,
            )

        assert len(results) == 2


class TestBatchSkipsExistingUrls:
    @pytest.mark.asyncio
    async def test_batch_skips_existing_urls(self, tmp_path):
        """Dedup works in batch — existing URLs are excluded."""
        candidates = _make_candidates(5)
        source = _mock_source(candidates)
        dest = AsyncMock()
        dest.publish = AsyncMock(
            return_value=PublishResult(success=True, slug="s", url="/out/s.md")
        )
        db_path = str(tmp_path / "test.db")

        # Pre-populate storage with first 3 URLs
        from pipepost.storage.sqlite import SQLiteStorage

        storage = SQLiteStorage(db_path)
        for i in range(1, 4):
            storage.mark_published(f"https://example.com/article-{i}", "test-source", f"slug-{i}")
        storage.close()

        with (
            patch("pipepost.batch.get_source", return_value=source),
            patch("pipepost.batch.get_destination", return_value=dest),
            patch("pipepost.batch._fetch_and_translate") as mock_ft,
        ):

            async def _ft(candidate, source_name, target_lang, existing_urls, dry_run):
                ctx = FlowContext(candidates=[candidate], source_name=source_name)
                ctx.selected = Article(url=candidate.url, title=candidate.title, content="c " * 30)
                ctx.translated = TranslatedArticle(
                    title=candidate.title,
                    title_translated="T",
                    content="c " * 30,
                    content_translated="t " * 30,
                    source_url=candidate.url,
                )
                return ctx

            mock_ft.side_effect = _ft

            from pipepost.batch import run_batch

            results = await run_batch(
                source_name="test-source",
                max_articles=5,
                destination_name="default",
                db_path=db_path,
            )

        # Only articles 4 and 5 should be processed (3 were existing)
        assert len(results) == 2


class TestBatchContinuesOnSingleFailure:
    @pytest.mark.asyncio
    async def test_batch_continues_on_single_failure(self, tmp_path):
        """One article fails, others succeed."""
        candidates = _make_candidates(3)
        source = _mock_source(candidates)
        dest = AsyncMock()
        dest.publish = AsyncMock(
            return_value=PublishResult(success=True, slug="s", url="/out/s.md")
        )
        db_path = str(tmp_path / "test.db")

        call_count = 0

        with (
            patch("pipepost.batch.get_source", return_value=source),
            patch("pipepost.batch.get_destination", return_value=dest),
            patch("pipepost.batch._fetch_and_translate") as mock_ft,
        ):

            async def _ft(candidate, source_name, target_lang, existing_urls, dry_run):
                nonlocal call_count
                call_count += 1
                ctx = FlowContext(candidates=[candidate], source_name=source_name)
                if call_count == 2:
                    ctx.add_error("Simulated failure")
                    return ctx
                ctx.selected = Article(url=candidate.url, title=candidate.title, content="c " * 30)
                ctx.translated = TranslatedArticle(
                    title=candidate.title,
                    title_translated="T",
                    content="c " * 30,
                    content_translated="t " * 30,
                    source_url=candidate.url,
                )
                return ctx

            mock_ft.side_effect = _ft

            from pipepost.batch import run_batch

            results = await run_batch(
                source_name="test-source",
                max_articles=3,
                destination_name="default",
                db_path=db_path,
            )

        assert len(results) == 3
        # 2 should succeed, 1 should have errors
        succeeded = [r for r in results if r.published and r.published.success]
        failed = [r for r in results if r.has_errors]
        assert len(succeeded) == 2
        assert len(failed) == 1


class TestBatchDryRun:
    @pytest.mark.asyncio
    async def test_batch_dry_run(self, tmp_path):
        """No publish/persist in dry run."""
        candidates = _make_candidates(3)
        source = _mock_source(candidates)
        dest = AsyncMock()
        dest.publish = AsyncMock(
            return_value=PublishResult(success=True, slug="s", url="/out/s.md")
        )
        db_path = str(tmp_path / "test.db")

        with (
            patch("pipepost.batch.get_source", return_value=source),
            patch("pipepost.batch.get_destination", return_value=dest),
            patch("pipepost.batch._fetch_and_translate") as mock_ft,
        ):

            async def _ft(candidate, source_name, target_lang, existing_urls, dry_run):
                ctx = FlowContext(candidates=[candidate], source_name=source_name)
                ctx.selected = Article(url=candidate.url, title=candidate.title, content="c " * 30)
                ctx.translated = TranslatedArticle(
                    title=candidate.title,
                    title_translated="T",
                    content="c " * 30,
                    content_translated="t " * 30,
                    source_url=candidate.url,
                )
                return ctx

            mock_ft.side_effect = _ft

            from pipepost.batch import run_batch

            results = await run_batch(
                source_name="test-source",
                max_articles=3,
                destination_name="default",
                db_path=db_path,
                dry_run=True,
            )

        assert len(results) == 3
        # Destination publish should NOT have been called
        dest.publish.assert_not_called()
        # No articles should be marked as published
        for r in results:
            assert r.published is None


class TestBatchReturnsContexts:
    @pytest.mark.asyncio
    async def test_batch_returns_contexts(self, tmp_path):
        """Returns list of FlowContext."""
        candidates = _make_candidates(2)
        source = _mock_source(candidates)
        dest = AsyncMock()
        dest.publish = AsyncMock(
            return_value=PublishResult(success=True, slug="s", url="/out/s.md")
        )
        db_path = str(tmp_path / "test.db")

        with (
            patch("pipepost.batch.get_source", return_value=source),
            patch("pipepost.batch.get_destination", return_value=dest),
            patch("pipepost.batch._fetch_and_translate") as mock_ft,
        ):

            async def _ft(candidate, source_name, target_lang, existing_urls, dry_run):
                ctx = FlowContext(candidates=[candidate], source_name=source_name)
                ctx.selected = Article(url=candidate.url, title=candidate.title, content="c " * 30)
                ctx.translated = TranslatedArticle(
                    title=candidate.title,
                    title_translated="T",
                    content="c " * 30,
                    content_translated="t " * 30,
                    source_url=candidate.url,
                )
                return ctx

            mock_ft.side_effect = _ft

            from pipepost.batch import run_batch

            results = await run_batch(
                source_name="test-source",
                max_articles=2,
                destination_name="default",
                db_path=db_path,
            )

        assert isinstance(results, list)
        assert len(results) == 2
        for ctx in results:
            assert isinstance(ctx, FlowContext)

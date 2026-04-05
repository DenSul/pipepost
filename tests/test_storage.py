"""Tests for SQLiteStorage — table creation, CRUD, async context manager."""

from __future__ import annotations

import sqlite3

import pytest

from pipepost.storage.sqlite import SQLiteStorage


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


class TestSQLiteStorage:
    @pytest.mark.asyncio
    async def test_creates_table(self, db_path):
        storage = SQLiteStorage(db_path=db_path)
        # Trigger lazy connection + table creation
        await storage.load_existing_urls()
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='published_urls'"
        )
        assert cursor.fetchone() is not None
        conn.close()
        await storage.close()

    @pytest.mark.asyncio
    async def test_mark_and_load(self, db_path):
        storage = SQLiteStorage(db_path=db_path)
        await storage.mark_published("https://example.com/a", source_name="rss", slug="a")
        urls = await storage.load_existing_urls()
        assert "https://example.com/a" in urls
        await storage.close()

    @pytest.mark.asyncio
    async def test_duplicate_insert_ignored(self, db_path):
        storage = SQLiteStorage(db_path=db_path)
        await storage.mark_published("https://example.com/dup")
        await storage.mark_published("https://example.com/dup")
        assert await storage.count() == 1
        await storage.close()

    @pytest.mark.asyncio
    async def test_contains(self, db_path):
        storage = SQLiteStorage(db_path=db_path)
        assert await storage.contains("https://nope.com") is False
        await storage.mark_published("https://nope.com")
        assert await storage.contains("https://nope.com") is True
        await storage.close()

    @pytest.mark.asyncio
    async def test_count(self, db_path):
        storage = SQLiteStorage(db_path=db_path)
        for i in range(3):
            await storage.mark_published(f"https://example.com/{i}")
        assert await storage.count() == 3
        await storage.close()

    @pytest.mark.asyncio
    async def test_empty_db(self, db_path):
        storage = SQLiteStorage(db_path=db_path)
        assert await storage.load_existing_urls() == set()
        assert await storage.count() == 0
        await storage.close()

    @pytest.mark.asyncio
    async def test_async_context_manager(self, db_path):
        async with SQLiteStorage(db_path=db_path) as storage:
            await storage.mark_published("https://ctx.com")
            assert await storage.contains("https://ctx.com")

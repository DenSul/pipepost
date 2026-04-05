"""Tests for SQLiteStorage — table creation, CRUD, context manager."""

from __future__ import annotations

import sqlite3

import pytest

from pipepost.storage.sqlite import SQLiteStorage


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


class TestSQLiteStorage:
    def test_creates_table(self, db_path):
        storage = SQLiteStorage(db_path=db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='published_urls'"
        )
        assert cursor.fetchone() is not None
        conn.close()
        storage.close()

    def test_mark_and_load(self, db_path):
        storage = SQLiteStorage(db_path=db_path)
        storage.mark_published("https://example.com/a", source_name="rss", slug="a")
        urls = storage.load_existing_urls()
        assert "https://example.com/a" in urls
        storage.close()

    def test_duplicate_insert_ignored(self, db_path):
        storage = SQLiteStorage(db_path=db_path)
        storage.mark_published("https://example.com/dup")
        storage.mark_published("https://example.com/dup")
        assert storage.count() == 1
        storage.close()

    def test_contains(self, db_path):
        storage = SQLiteStorage(db_path=db_path)
        assert storage.contains("https://nope.com") is False
        storage.mark_published("https://nope.com")
        assert storage.contains("https://nope.com") is True
        storage.close()

    def test_count(self, db_path):
        storage = SQLiteStorage(db_path=db_path)
        for i in range(3):
            storage.mark_published(f"https://example.com/{i}")
        assert storage.count() == 3
        storage.close()

    def test_empty_db(self, db_path):
        storage = SQLiteStorage(db_path=db_path)
        assert storage.load_existing_urls() == set()
        assert storage.count() == 0
        storage.close()

    def test_context_manager(self, db_path):
        with SQLiteStorage(db_path=db_path) as storage:
            storage.mark_published("https://ctx.com")
            assert storage.contains("https://ctx.com")

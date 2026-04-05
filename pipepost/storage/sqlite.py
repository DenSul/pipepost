"""SQLite-based storage for persistent URL deduplication."""

from __future__ import annotations

import logging
import sqlite3
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from types import TracebackType

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS published_urls (
    url TEXT PRIMARY KEY,
    source_name TEXT,
    slug TEXT,
    published_at TEXT DEFAULT CURRENT_TIMESTAMP
)
"""


class SQLiteStorage:
    """Persistent storage backed by a local SQLite database."""

    def __init__(self, db_path: str = "pipepost.db") -> None:
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(_CREATE_TABLE_SQL)
        self._conn.commit()
        logger.info("SQLiteStorage initialised: %s", db_path)

    # -- public API ----------------------------------------------------------

    def load_existing_urls(self) -> set[str]:
        """Return all previously published URLs."""
        cursor = self._conn.execute("SELECT url FROM published_urls")
        urls = {row[0] for row in cursor.fetchall()}
        logger.debug("Loaded %d existing URLs from storage", len(urls))
        return urls

    def mark_published(
        self,
        url: str,
        source_name: str = "",
        slug: str = "",
    ) -> None:
        """Record a URL as published (duplicates are silently ignored)."""
        self._conn.execute(
            "INSERT OR IGNORE INTO published_urls (url, source_name, slug) VALUES (?, ?, ?)",
            (url, source_name, slug),
        )
        self._conn.commit()
        logger.info("Marked published: %s", url)

    def contains(self, url: str) -> bool:
        """Check whether a URL has already been published."""
        cursor = self._conn.execute(
            "SELECT 1 FROM published_urls WHERE url = ?",
            (url,),
        )
        return cursor.fetchone() is not None

    def count(self) -> int:
        """Return total number of published URLs."""
        cursor = self._conn.execute("SELECT COUNT(*) FROM published_urls")
        result = cursor.fetchone()
        return int(result[0]) if result else 0

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
        logger.debug("SQLiteStorage connection closed")

    # -- context manager -----------------------------------------------------

    def __enter__(self) -> SQLiteStorage:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

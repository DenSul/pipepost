"""SQLite-based storage for persistent URL deduplication."""

from __future__ import annotations

import contextlib
import logging
import sqlite3
import threading
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
    """Persistent storage backed by a local SQLite database.

    Uses a single reusable connection with a threading lock to ensure
    safe concurrent access from multiple threads.
    """

    def __init__(self, db_path: str = "pipepost.db") -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(_CREATE_TABLE_SQL)
        self._conn.commit()
        logger.info("SQLiteStorage initialised: %s", db_path)

    # -- public API ----------------------------------------------------------

    def load_existing_urls(self) -> set[str]:
        """Return all previously published URLs."""
        with self._lock:
            conn = self._get_conn()
            cursor = conn.execute("SELECT url FROM published_urls")
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
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                "INSERT OR IGNORE INTO published_urls (url, source_name, slug) VALUES (?, ?, ?)",
                (url, source_name, slug),
            )
            conn.commit()
        logger.info("Marked published: %s", url)

    def contains(self, url: str) -> bool:
        """Check whether a URL has already been published."""
        with self._lock:
            conn = self._get_conn()
            cursor = conn.execute(
                "SELECT 1 FROM published_urls WHERE url = ?",
                (url,),
            )
            return cursor.fetchone() is not None

    def count(self) -> int:
        """Return total number of published URLs."""
        with self._lock:
            conn = self._get_conn()
            cursor = conn.execute("SELECT COUNT(*) FROM published_urls")
            result = cursor.fetchone()
        return int(result[0]) if result else 0

    def close(self) -> None:
        """Close the database connection."""
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
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

    def __del__(self) -> None:
        """Safety net — close connection if not explicitly closed."""
        conn = getattr(self, "_conn", None)
        if conn is not None:
            with contextlib.suppress(Exception):
                conn.close()

    # -- internals -----------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        """Return the active connection, raising if already closed."""
        if self._conn is None:
            msg = "SQLiteStorage connection is already closed"
            raise RuntimeError(msg)
        return self._conn

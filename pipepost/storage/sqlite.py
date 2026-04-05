"""SQLite-based storage for persistent URL deduplication."""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING

import aiosqlite


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

    The constructor is synchronous (stores only the path); the actual
    connection is created lazily on the first async call via ``_get_conn``.
    """

    def __init__(self, db_path: str = "pipepost.db") -> None:
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None
        logger.info("SQLiteStorage initialised (lazy): %s", db_path)

    # -- internal helpers ----------------------------------------------------

    async def _get_conn(self) -> aiosqlite.Connection:
        """Return the active connection, creating it on first call."""
        if self._conn is None:
            self._conn = await aiosqlite.connect(self.db_path)
            await self._conn.execute(_CREATE_TABLE_SQL)
            await self._conn.commit()
        return self._conn

    async def _ensure_table(self) -> None:
        """Create the table if it doesn't exist yet."""
        conn = await self._get_conn()
        await conn.execute(_CREATE_TABLE_SQL)
        await conn.commit()

    # -- public API ----------------------------------------------------------

    async def load_existing_urls(self) -> set[str]:
        """Return all previously published URLs."""
        conn = await self._get_conn()
        cursor = await conn.execute("SELECT url FROM published_urls")
        rows = await cursor.fetchall()
        urls = {row[0] for row in rows}
        logger.debug("Loaded %d existing URLs from storage", len(urls))
        return urls

    async def mark_published(
        self,
        url: str,
        source_name: str = "",
        slug: str = "",
    ) -> None:
        """Record a URL as published (duplicates are silently ignored)."""
        conn = await self._get_conn()
        await conn.execute(
            "INSERT OR IGNORE INTO published_urls (url, source_name, slug) VALUES (?, ?, ?)",
            (url, source_name, slug),
        )
        await conn.commit()
        logger.info("Marked published: %s", url)

    async def contains(self, url: str) -> bool:
        """Check whether a URL has already been published."""
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT 1 FROM published_urls WHERE url = ?",
            (url,),
        )
        row = await cursor.fetchone()
        return row is not None

    async def count(self) -> int:
        """Return total number of published URLs."""
        conn = await self._get_conn()
        cursor = await conn.execute("SELECT COUNT(*) FROM published_urls")
        result = await cursor.fetchone()
        return int(result[0]) if result else 0

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
            logger.debug("SQLiteStorage connection closed")

    # -- async context manager -----------------------------------------------

    async def __aenter__(self) -> SQLiteStorage:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()

    def __del__(self) -> None:
        """Safety net -- warn if connection was not explicitly closed."""
        conn = getattr(self, "_conn", None)
        if conn is not None:
            with contextlib.suppress(Exception):
                logger.warning(
                    "SQLiteStorage for %s was not explicitly closed",
                    getattr(self, "db_path", "?"),
                )

"""Abstract base class for content sources."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from pipepost.core.context import Candidate

_DEFAULT_MAX_CONCURRENCY = 5


class Source(ABC):
    """A content source that provides article candidates."""

    name: str
    source_type: str  # "api" | "rss" | "scrape" | "search"
    _semaphore: asyncio.Semaphore

    def __init__(self, *, max_concurrency: int = _DEFAULT_MAX_CONCURRENCY) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrency)

    @asynccontextmanager
    async def rate_limit(self) -> AsyncIterator[None]:
        """Acquire the concurrency semaphore before making an external call."""
        async with self._semaphore:
            yield

    @abstractmethod
    async def fetch_candidates(self, limit: int = 10) -> list[Candidate]:
        """Fetch article candidates from this source."""

    def get_config_schema(self) -> dict[str, object]:
        """Return JSON schema for YAML config. Override for custom sources."""
        return {}

    @classmethod
    def from_config(cls, config: dict[str, object]) -> Source:
        """Create a source instance from a config dict."""
        msg = f"{cls.__name__} does not support config-based creation"
        raise NotImplementedError(msg)

    def __repr__(self) -> str:
        return f"<Source:{self.name} type={self.source_type}>"

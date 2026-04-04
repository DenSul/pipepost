"""Abstract base class for content sources."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pipepost.core.context import Candidate


class Source(ABC):
    """A content source that provides article candidates."""

    name: str
    source_type: str  # "api" | "rss" | "scrape" | "search"

    @abstractmethod
    async def fetch_candidates(self, limit: int = 10) -> list[Candidate]:
        """Fetch article candidates from this source."""

    def get_config_schema(self) -> dict[str, Any]:
        """Return JSON schema for YAML config. Override for custom sources."""
        return {}

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "Source":
        """Create a source instance from a config dict."""
        raise NotImplementedError(f"{cls.__name__} does not support config-based creation")

    def __repr__(self) -> str:
        return f"<Source:{self.name} type={self.source_type}>"

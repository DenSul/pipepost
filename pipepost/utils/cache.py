"""Simple in-memory TTL cache for fetched content."""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class CacheEntry:
    """A single cached value with its expiration timestamp."""

    value: object
    expires_at: float


class TTLCache:
    """Thread-safe in-memory cache with time-based expiration."""

    def __init__(self, ttl_seconds: float = 3600.0) -> None:
        self.ttl = ttl_seconds
        self._store: dict[str, CacheEntry] = {}

    def get(self, key: str) -> object | None:
        """Return cached value or *None* if missing / expired."""
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.monotonic() > entry.expires_at:
            del self._store[key]
            return None
        return entry.value

    def set(self, key: str, value: object) -> None:
        """Store *value* under *key* with the configured TTL."""
        self._store[key] = CacheEntry(
            value=value,
            expires_at=time.monotonic() + self.ttl,
        )

    def clear(self) -> None:
        """Remove all entries."""
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)

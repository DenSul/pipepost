"""Tests for the in-memory TTL cache."""

from __future__ import annotations

import time

from pipepost.utils.cache import TTLCache


class TestTTLCache:
    """Unit tests for TTLCache."""

    def test_get_miss_returns_none(self) -> None:
        cache = TTLCache(ttl_seconds=60.0)
        assert cache.get("missing") is None

    def test_set_and_get(self) -> None:
        cache = TTLCache(ttl_seconds=60.0)
        cache.set("key", "value")
        assert cache.get("key") == "value"

    def test_overwrite(self) -> None:
        cache = TTLCache(ttl_seconds=60.0)
        cache.set("k", 1)
        cache.set("k", 2)
        assert cache.get("k") == 2

    def test_expiration(self) -> None:
        cache = TTLCache(ttl_seconds=0.01)
        cache.set("k", "v")
        time.sleep(0.02)
        assert cache.get("k") is None

    def test_clear(self) -> None:
        cache = TTLCache(ttl_seconds=60.0)
        cache.set("a", 1)
        cache.set("b", 2)
        assert len(cache) == 2
        cache.clear()
        assert len(cache) == 0

    def test_len(self) -> None:
        cache = TTLCache(ttl_seconds=60.0)
        assert len(cache) == 0
        cache.set("x", 42)
        assert len(cache) == 1

    def test_complex_value(self) -> None:
        cache = TTLCache(ttl_seconds=60.0)
        val = ("markdown content", "https://img.example.com/cover.jpg")
        cache.set("url", val)
        assert cache.get("url") == val

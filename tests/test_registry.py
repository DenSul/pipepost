"""Tests for registry — register/get/list/discover."""

from __future__ import annotations

import sys

import pytest

from pipepost.core import registry
from pipepost.core.step import Step


class DummyStep(Step):
    name = "dummy"

    async def execute(self, ctx):
        return ctx


@pytest.fixture(autouse=True)
def _clean_registry():
    """Reset registry state between tests."""
    saved = (
        registry._sources.copy(),
        registry._destinations.copy(),
        registry._steps.copy(),
        registry._flows.copy(),
    )
    registry._sources.clear()
    registry._destinations.clear()
    registry._steps.clear()
    registry._flows.clear()
    yield
    registry._sources.update(saved[0])
    registry._destinations.update(saved[1])
    registry._steps.update(saved[2])
    registry._flows.update(saved[3])


class TestRegisterAndGet:
    def test_register_and_get_source(self):
        registry.register_source("test-src", {"type": "mock"})
        assert registry.get_source("test-src") == {"type": "mock"}

    def test_register_and_get_destination(self):
        registry.register_destination("test-dest", {"url": "http://x"})
        assert registry.get_destination("test-dest") == {"url": "http://x"}

    def test_register_and_get_flow(self):
        registry.register_flow("test-flow", "flow-obj")
        assert registry.get_flow("test-flow") == "flow-obj"

    def test_register_step(self):
        registry.register_step("test-step", DummyStep)
        assert registry._steps["test-step"] is DummyStep

    def test_get_missing_source_raises(self):
        with pytest.raises(KeyError, match="not registered"):
            registry.get_source("nonexistent")

    def test_get_missing_destination_raises(self):
        with pytest.raises(KeyError, match="not registered"):
            registry.get_destination("nonexistent")

    def test_get_missing_flow_raises(self):
        with pytest.raises(KeyError, match="not registered"):
            registry.get_flow("nonexistent")


class TestListFunctions:
    def test_list_sources_empty(self):
        assert registry.list_sources() == []

    def test_list_sources_sorted(self):
        registry.register_source("z-src", {})
        registry.register_source("a-src", {})
        assert registry.list_sources() == ["a-src", "z-src"]

    def test_list_destinations(self):
        registry.register_destination("webhook", {})
        assert "webhook" in registry.list_destinations()

    def test_list_flows(self):
        registry.register_flow("pipeline-a", {})
        registry.register_flow("pipeline-b", {})
        assert registry.list_flows() == ["pipeline-a", "pipeline-b"]


class TestDiscoverModules:
    def test_discover_nonexistent_package(self):
        """Should not raise, just log warning."""
        registry.discover_modules("nonexistent.package.xyz")

    def test_discover_modules_loads_sources(self):
        """discover_modules for pipepost.sources should register HN/Reddit.

        We need to remove them from sys.modules first so import triggers
        the module-level register_source() calls again.
        """
        # Remove source modules so re-import triggers registration
        to_remove = [k for k in sys.modules if k.startswith("pipepost.sources.")]
        for k in to_remove:
            del sys.modules[k]

        registry.discover_modules("pipepost.sources")
        sources = registry.list_sources()
        assert "hackernews" in sources
        assert "reddit" in sources

    def test_discover_all(self):
        """discover_all should register at least the built-in sources."""
        to_remove = [
            k for k in sys.modules if k.startswith(("pipepost.sources.", "pipepost.destinations."))
        ]
        for k in to_remove:
            del sys.modules[k]

        registry.discover_all()
        assert len(registry.list_sources()) > 0

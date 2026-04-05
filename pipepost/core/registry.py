"""Auto-discovery registry for sources, steps, destinations."""

from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from pipepost.core.flow import Flow
    from pipepost.core.step import Step
    from pipepost.destinations.base import Destination
    from pipepost.sources.base import Source

logger = logging.getLogger(__name__)

_sources: dict[str, Source] = {}
_destinations: dict[str, Destination] = {}
_steps: dict[str, type[Step]] = {}
_flows: dict[str, Flow] = {}


def register_source(name: str, source: Source) -> None:
    """Register a content source by name."""
    _sources[name] = source


def register_destination(name: str, dest: Destination) -> None:
    """Register a publish destination by name."""
    _destinations[name] = dest


def register_step(name: str, step_cls: type[Step]) -> None:
    """Register a step class by name."""
    _steps[name] = step_cls


def register_flow(name: str, flow: Flow) -> None:
    """Register a pipeline flow by name."""
    _flows[name] = flow


def get_source(name: str) -> Source:
    """Get a registered source by name."""
    if name not in _sources:
        msg = f"Source '{name}' not registered. Available: {list(_sources)}"
        raise KeyError(msg)
    return _sources[name]


def get_destination(name: str) -> Destination:
    """Get a registered destination by name."""
    if name not in _destinations:
        msg = f"Destination '{name}' not registered. Available: {list(_destinations)}"
        raise KeyError(msg)
    return _destinations[name]


def get_step_class(name: str) -> type[Step]:
    """Get a registered step class by name."""
    if name not in _steps:
        msg = f"Step '{name}' not registered. Available: {list(_steps)}"
        raise KeyError(msg)
    return _steps[name]


def list_steps() -> list[str]:
    """List all registered step names."""
    return sorted(_steps.keys())


def get_flow(name: str) -> Flow:
    """Get a registered flow by name."""
    if name not in _flows:
        msg = f"Flow '{name}' not registered. Available: {list(_flows)}"
        raise KeyError(msg)
    return _flows[name]


def list_sources() -> list[str]:
    """List all registered source names."""
    return sorted(_sources.keys())


def list_destinations() -> list[str]:
    """List all registered destination names."""
    return sorted(_destinations.keys())


def list_flows() -> list[str]:
    """List all registered flow names."""
    return sorted(_flows.keys())


def discover_modules(package_name: str) -> None:
    """Import all modules in a package to trigger registration."""
    try:
        package = importlib.import_module(package_name)
    except ImportError as exc:
        logger.warning("Cannot import package %s: %s", package_name, exc)
        return

    package_path = getattr(package, "__path__", None)
    if not package_path:
        return

    for _importer, modname, _ispkg in pkgutil.iter_modules(package_path):
        if modname.startswith("_"):
            continue
        full_name = f"{package_name}.{modname}"
        try:
            importlib.import_module(full_name)
        except Exception as exc:
            logger.warning("Failed to import %s: %s", full_name, exc)


def discover_all() -> None:
    """Discover all sources, destinations, and flows."""
    discover_modules("pipepost.sources")
    discover_modules("pipepost.steps")
    discover_modules("pipepost.destinations")
    discover_modules("pipepost.flows")

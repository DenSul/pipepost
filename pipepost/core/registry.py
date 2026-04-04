"""Auto-discovery registry for sources, steps, destinations."""

from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import Any

from pipepost.core.step import Step

logger = logging.getLogger(__name__)

_sources: dict[str, Any] = {}
_destinations: dict[str, Any] = {}
_steps: dict[str, type[Step]] = {}
_flows: dict[str, Any] = {}


def register_source(name: str, source: Any) -> None:
    _sources[name] = source


def register_destination(name: str, dest: Any) -> None:
    _destinations[name] = dest


def register_step(name: str, step_cls: type[Step]) -> None:
    _steps[name] = step_cls


def register_flow(name: str, flow: Any) -> None:
    _flows[name] = flow


def get_source(name: str) -> Any:
    if name not in _sources:
        raise KeyError(f"Source '{name}' not registered. Available: {list(_sources)}")
    return _sources[name]


def get_destination(name: str) -> Any:
    if name not in _destinations:
        raise KeyError(
            f"Destination '{name}' not registered. Available: {list(_destinations)}"
        )
    return _destinations[name]


def get_flow(name: str) -> Any:
    if name not in _flows:
        raise KeyError(f"Flow '{name}' not registered. Available: {list(_flows)}")
    return _flows[name]


def list_sources() -> list[str]:
    return sorted(_sources.keys())


def list_destinations() -> list[str]:
    return sorted(_destinations.keys())


def list_flows() -> list[str]:
    return sorted(_flows.keys())


def discover_modules(package_name: str) -> None:
    """Import all modules in a package to trigger registration."""
    try:
        package = importlib.import_module(package_name)
    except ImportError as e:
        logger.warning("Cannot import package %s: %s", package_name, e)
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
        except Exception as e:
            logger.warning("Failed to import %s: %s", full_name, e)


def discover_all() -> None:
    """Discover all sources, destinations, and flows."""
    discover_modules("pipepost.sources")
    discover_modules("pipepost.destinations")
    discover_modules("pipepost.flows")

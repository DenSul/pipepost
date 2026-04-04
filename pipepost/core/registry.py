"""Core registry — source registration and discovery."""
from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pipepost.sources.base import Source

logger = logging.getLogger(__name__)

_sources: dict[str, Any] = {}


def register_source(name: str, source: Source) -> None:
    """Register a source instance by name."""
    _sources[name] = source
    logger.debug("Registered source: %s", name)


def get_source(name: str) -> Source | None:
    """Get a registered source by name."""
    return _sources.get(name)


def get_all_sources() -> dict[str, Any]:
    """Return all registered sources."""
    return dict(_sources)


def discover_modules(package_name: str) -> None:
    """Import all modules in a package to trigger register_source calls."""
    try:
        package = importlib.import_module(package_name)
    except ImportError as e:
        logger.warning("Cannot import package %s: %s", package_name, e)
        return

    if not hasattr(package, "__path__"):
        return

    for _importer, modname, _ispkg in pkgutil.iter_modules(package.__path__):
        try:
            importlib.import_module(f"{package_name}.{modname}")
        except Exception as e:
            logger.warning("Failed to import %s.%s: %s", package_name, modname, e)

"""Abstract base class for pipeline steps."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from pipepost.core.context import FlowContext
    from pipepost.destinations.base import Destination
    from pipepost.storage.sqlite import SQLiteStorage

logger = logging.getLogger(__name__)


@dataclass
class StepBuildContext:
    """Shared context passed to Step.from_config() during flow assembly.

    Contains all config values and runtime objects that steps may need.
    Each step picks only what it requires and ignores the rest.
    """

    # Storage
    storage: SQLiteStorage | None = None

    # Translation / LLM
    model: str = ""
    target_lang: str = "ru"
    max_tokens: int = 16384

    # Fetch
    max_chars: int = 20000
    fetch_timeout: float = 30.0
    cache_ttl: float = 3600.0

    # Scoring
    score_model: str = ""
    niche: str = "general"
    max_score_candidates: int = 5

    # Adapt
    adapt_model: str = ""
    style: str = "blog"

    # Validation
    min_content_len: int = 300
    min_ratio: float = 0.3

    # Publish
    destination_name: str = "default"
    destination_names: list[str] = field(default_factory=list)
    destination: Destination | None = None
    destinations: dict[str, Destination] | None = None

    # Scout
    max_candidates: int = 30

    # Images
    images_output_dir: str = "./output/images"


class Step(ABC):
    """A single unit of work in a pipeline."""

    name: str = "unnamed"

    @abstractmethod
    async def execute(self, ctx: FlowContext) -> FlowContext:
        """Execute this step, transforming the context."""

    @classmethod
    def from_config(cls, build_ctx: StepBuildContext) -> Step:  # noqa: ARG003
        """Create a step instance from a StepBuildContext.

        Subclasses should override to pick relevant fields from build_ctx.
        Default implementation returns ``cls()`` (works for no-arg steps).
        """
        return cls()

    def should_skip(self, ctx: FlowContext) -> bool:  # noqa: ARG002
        """Return True to skip this step."""
        return False

    async def on_error(self, ctx: FlowContext, error: Exception) -> FlowContext:
        """Handle errors. Override for custom error handling."""
        ctx.add_error(f"[{self.name}] {error}")
        logger.error("Step %s failed: %s", self.name, error)
        return ctx

    def __repr__(self) -> str:
        return f"<Step:{self.name}>"

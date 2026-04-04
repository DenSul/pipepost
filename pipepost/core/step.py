"""Abstract base class for pipeline steps."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from pipepost.core.context import FlowContext

logger = logging.getLogger(__name__)


class Step(ABC):
    """A single unit of work in a pipeline."""

    name: str = "unnamed"

    @abstractmethod
    async def execute(self, ctx: FlowContext) -> FlowContext:
        """Execute this step, transforming the context."""

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

"""Flow — a composable chain of pipeline steps."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from pipepost.core.context import FlowContext
    from pipepost.core.step import Step

logger = logging.getLogger(__name__)

OnStepComplete = Callable[[str, "FlowContext", float], Awaitable[None] | None]


class Flow:
    """A pipeline flow — ordered chain of steps."""

    def __init__(
        self,
        name: str,
        steps: list[Step],
        on_error: str = "stop",
        on_step_complete: OnStepComplete | None = None,
    ) -> None:
        self.name = name
        self.steps = steps
        self.on_error = on_error
        self._on_step_complete = on_step_complete

    async def run(self, ctx: FlowContext) -> FlowContext:
        """Execute all steps in order."""
        logger.info("Flow '%s' starting with %d steps", self.name, len(self.steps))
        start = time.monotonic()

        for step in self.steps:
            if step.should_skip(ctx):
                logger.debug("Skipping step %s", step.name)
                continue

            step_start = time.monotonic()
            try:
                ctx = await step.execute(ctx)
                elapsed = time.monotonic() - step_start
                logger.info("Step %s completed in %.1fs", step.name, elapsed)
                await self._notify_step_complete(step.name, ctx, elapsed)
            except Exception as exc:
                elapsed = time.monotonic() - step_start
                ctx = await step.on_error(ctx, exc)
                await self._notify_step_complete(step.name, ctx, elapsed)
                if self.on_error == "stop":
                    logger.error(
                        "Flow '%s' stopped at step %s: %s",
                        self.name,
                        step.name,
                        exc,
                    )
                    break
                if self.on_error == "skip":
                    logger.warning("Skipping failed step %s: %s", step.name, exc)
                    continue
                # "continue" — errors accumulated but flow continues

        elapsed = time.monotonic() - start
        logger.info(
            "Flow '%s' finished in %.1fs (errors: %d)",
            self.name,
            elapsed,
            len(ctx.errors),
        )
        return ctx

    async def _notify_step_complete(
        self,
        step_name: str,
        ctx: FlowContext,
        elapsed: float,
    ) -> None:
        """Call the on_step_complete callback if set."""
        if self._on_step_complete is None:
            return
        result = self._on_step_complete(step_name, ctx, elapsed)
        if result is not None:
            await result

    def __repr__(self) -> str:
        step_names = " → ".join(s.name for s in self.steps)
        return f"<Flow:{self.name} [{step_names}]>"

"""Tests for Step base class."""

from __future__ import annotations

import pytest

from pipepost.core.context import FlowContext
from pipepost.core.step import Step


class DummyStep(Step):
    name = "dummy"

    def __init__(self, result_fn=None, skip_fn=None):
        self._result_fn = result_fn
        self._skip_fn = skip_fn

    async def execute(self, ctx: FlowContext) -> FlowContext:
        if self._result_fn:
            return self._result_fn(ctx)
        return ctx

    def should_skip(self, ctx: FlowContext) -> bool:
        if self._skip_fn:
            return self._skip_fn(ctx)
        return False


class FailingStep(Step):
    name = "failing"

    async def execute(self, ctx: FlowContext) -> FlowContext:
        raise RuntimeError("intentional failure")


class TestStepExecute:
    @pytest.mark.asyncio
    async def test_execute_returns_context(self):
        step = DummyStep()
        ctx = FlowContext()
        result = await step.execute(ctx)
        assert result is ctx

    @pytest.mark.asyncio
    async def test_execute_transforms_context(self):
        def add_candidate(ctx):
            ctx.metadata["touched"] = True
            return ctx

        step = DummyStep(result_fn=add_candidate)
        ctx = FlowContext()
        result = await step.execute(ctx)
        assert result.metadata["touched"] is True


class TestStepShouldSkip:
    def test_default_should_skip_false(self):
        step = DummyStep()
        ctx = FlowContext()
        assert step.should_skip(ctx) is False

    def test_custom_should_skip(self):
        step = DummyStep(skip_fn=lambda ctx: ctx.has_errors)
        ctx = FlowContext()
        assert step.should_skip(ctx) is False
        ctx.add_error("err")
        assert step.should_skip(ctx) is True


class TestStepOnError:
    @pytest.mark.asyncio
    async def test_on_error_adds_error_to_context(self):
        step = DummyStep()
        ctx = FlowContext()
        err = ValueError("bad value")
        result = await step.on_error(ctx, err)
        assert result.has_errors
        assert "[dummy] bad value" in result.errors[0]

    @pytest.mark.asyncio
    async def test_on_error_preserves_existing_errors(self):
        step = DummyStep()
        ctx = FlowContext()
        ctx.add_error("previous")
        await step.on_error(ctx, RuntimeError("new"))
        assert len(ctx.errors) == 2

    @pytest.mark.asyncio
    async def test_on_error_uses_step_name(self):
        step = FailingStep()
        ctx = FlowContext()
        await step.on_error(ctx, Exception("boom"))
        assert "[failing]" in ctx.errors[0]


class TestStepRepr:
    def test_repr(self):
        step = DummyStep()
        assert repr(step) == "<Step:dummy>"

"""Tests for Flow — step orchestration and error handling."""

from __future__ import annotations

import pytest

from pipepost.core.context import FlowContext
from pipepost.core.flow import Flow
from pipepost.core.step import Step


class PassStep(Step):
    name = "pass"

    def __init__(self, name: str = "pass", marker: str = ""):
        self.name = name
        self._marker = marker

    async def execute(self, ctx: FlowContext) -> FlowContext:
        ctx.metadata.setdefault("order", []).append(self._marker or self.name)
        return ctx


class FailStep(Step):
    name = "fail"

    def __init__(self, name: str = "fail"):
        self.name = name

    async def execute(self, ctx: FlowContext) -> FlowContext:
        raise RuntimeError(f"{self.name} exploded")


class SkipIfErrorStep(Step):
    name = "conditional"

    def __init__(self, name: str = "conditional", marker: str = ""):
        self.name = name
        self._marker = marker

    def should_skip(self, ctx: FlowContext) -> bool:
        return ctx.has_errors

    async def execute(self, ctx: FlowContext) -> FlowContext:
        ctx.metadata.setdefault("order", []).append(self._marker or self.name)
        return ctx


class TestFlowRun:
    @pytest.mark.asyncio
    async def test_empty_flow(self):
        flow = Flow(name="empty", steps=[])
        ctx = await flow.run(FlowContext())
        assert not ctx.has_errors

    @pytest.mark.asyncio
    async def test_single_step(self):
        flow = Flow(name="one", steps=[PassStep(name="s1", marker="s1")])
        ctx = await flow.run(FlowContext())
        assert ctx.metadata["order"] == ["s1"]

    @pytest.mark.asyncio
    async def test_steps_execute_in_order(self):
        steps = [
            PassStep(name="a", marker="a"),
            PassStep(name="b", marker="b"),
            PassStep(name="c", marker="c"),
        ]
        flow = Flow(name="ordered", steps=steps)
        ctx = await flow.run(FlowContext())
        assert ctx.metadata["order"] == ["a", "b", "c"]


class TestFlowErrorStop:
    @pytest.mark.asyncio
    async def test_stop_on_error_breaks_flow(self):
        steps = [
            PassStep(name="before", marker="before"),
            FailStep(name="boom"),
            PassStep(name="after", marker="after"),
        ]
        flow = Flow(name="stop-test", steps=steps, on_error="stop")
        ctx = await flow.run(FlowContext())
        assert ctx.has_errors
        assert "after" not in ctx.metadata.get("order", [])
        assert "before" in ctx.metadata["order"]

    @pytest.mark.asyncio
    async def test_stop_records_error(self):
        flow = Flow(name="f", steps=[FailStep(name="x")], on_error="stop")
        ctx = await flow.run(FlowContext())
        assert any("x" in e for e in ctx.errors)


class TestFlowErrorSkip:
    @pytest.mark.asyncio
    async def test_skip_continues_after_error(self):
        steps = [
            FailStep(name="boom"),
            PassStep(name="after", marker="after"),
        ]
        flow = Flow(name="skip-test", steps=steps, on_error="skip")
        ctx = await flow.run(FlowContext())
        assert ctx.has_errors
        assert "after" in ctx.metadata["order"]


class TestFlowErrorContinue:
    @pytest.mark.asyncio
    async def test_continue_accumulates_errors(self):
        steps = [
            FailStep(name="fail1"),
            FailStep(name="fail2"),
            PassStep(name="ok", marker="ok"),
        ]
        flow = Flow(name="cont-test", steps=steps, on_error="continue")
        ctx = await flow.run(FlowContext())
        assert len(ctx.errors) == 2
        assert "ok" in ctx.metadata["order"]


class TestFlowStepSkipping:
    @pytest.mark.asyncio
    async def test_should_skip_respected(self):
        steps = [
            FailStep(name="fail"),
            SkipIfErrorStep(name="skippable", marker="skippable"),
        ]
        flow = Flow(name="skip-flow", steps=steps, on_error="continue")
        ctx = await flow.run(FlowContext())
        assert "skippable" not in ctx.metadata.get("order", [])

    @pytest.mark.asyncio
    async def test_skip_not_triggered_when_no_errors(self):
        steps = [
            PassStep(name="ok", marker="ok"),
            SkipIfErrorStep(name="cond", marker="cond"),
        ]
        flow = Flow(name="no-skip", steps=steps)
        ctx = await flow.run(FlowContext())
        assert ctx.metadata["order"] == ["ok", "cond"]


class TestFlowRepr:
    def test_repr(self):
        flow = Flow(name="my-flow", steps=[PassStep(name="a"), PassStep(name="b")])
        r = repr(flow)
        assert "my-flow" in r
        assert "a → b" in r

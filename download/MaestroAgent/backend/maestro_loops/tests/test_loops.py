"""Smoke tests for maestro_loops — the reliability primitive.

Principle 2: "until tests pass" must not be a hand-rolled while loop.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from maestro_core.context import RunConfig, RunContext
from maestro_core.state import State
from maestro_core.streaming import EventBus
from maestro_loops.conditions import (
    AllOf,
    AnyOf,
    CallableCondition,
    ConditionResult,
    MetricThresholdCondition,
    TestPassCondition as _TestPassCondition,
)
from maestro_loops.handler import LoopHandler, LoopOutcome, LoopSpec
from maestro_loops.types import BackoffPolicy, LoopKind, OnExceedAction


def _make_ctx() -> RunContext:
    cfg = RunConfig(run_id="r1", template="t", goal="g", sandbox_enabled=False, max_cost_usd=1000.0)
    return RunContext(
        config=cfg, llm=None, memory=None, checkpoints=None,  # type: ignore[arg-type]
        events=EventBus(), verifiers=None, plugins=None,  # type: ignore[arg-type]
    )


def _const_cond(met: bool, score: float | None = None) -> CallableCondition:
    async def fn(s: State, ctx: RunContext) -> ConditionResult:
        return ConditionResult(met=met, score=score)
    return CallableCondition(fn=fn)


# MetricThresholdCondition

async def test_metric_ge_met() -> None:
    cond = MetricThresholdCondition(metric_key="pass_rate", threshold=0.8, comparator=">=")
    state = State(metadata={"pass_rate": 0.85})
    assert (await cond.evaluate(state, _make_ctx())).met is True


async def test_metric_ge_not_met_below() -> None:
    cond = MetricThresholdCondition(metric_key="pass_rate", threshold=0.8, comparator=">=")
    state = State(metadata={"pass_rate": 0.79})
    assert (await cond.evaluate(state, _make_ctx())).met is False


async def test_metric_missing_does_not_crash() -> None:
    """Principle 6: a missing metric must NOT crash — return met=False."""
    cond = MetricThresholdCondition(metric_key="nope", threshold=1.0)
    result = await cond.evaluate(State(metadata={}), _make_ctx())
    assert result.met is False
    assert "not set" in result.reason


async def test_metric_non_numeric_does_not_crash() -> None:
    cond = MetricThresholdCondition(metric_key="v", threshold=1.0)
    result = await cond.evaluate(State(metadata={"v": "not_a_number"}), _make_ctx())
    assert result.met is False


# AllOf / AnyOf

async def test_all_of_met_when_all_met() -> None:
    cond = AllOf(conditions=[_const_cond(True, 0.9), _const_cond(True, 0.8)])
    assert (await cond.evaluate(State(), _make_ctx())).met is True


async def test_all_of_not_met_when_any_fails() -> None:
    cond = AllOf(conditions=[_const_cond(True), _const_cond(False)])
    assert (await cond.evaluate(State(), _make_ctx())).met is False


async def test_any_of_met_when_any_met() -> None:
    cond = AnyOf(conditions=[_const_cond(False), _const_cond(True)])
    assert (await cond.evaluate(State(), _make_ctx())).met is True


async def test_any_of_not_met_when_all_fail() -> None:
    cond = AnyOf(conditions=[_const_cond(False), _const_cond(False)])
    assert (await cond.evaluate(State(), _make_ctx())).met is False


# LoopHandler

async def test_loop_exits_when_condition_met() -> None:
    calls = 0

    async def body(state: State, ctx: RunContext) -> State:
        nonlocal calls
        calls += 1
        return state

    spec = LoopSpec(id="l1", body=body, exit_condition=_const_cond(True), max_iterations=10)
    handler = LoopHandler(spec=spec)
    await handler(State(), _make_ctx())
    assert calls == 1


async def test_loop_hits_max_iterations() -> None:
    calls = 0

    async def body(state: State, ctx: RunContext) -> State:
        nonlocal calls
        calls += 1
        return state

    spec = LoopSpec(
        id="l1", body=body, exit_condition=_const_cond(False), max_iterations=3,
        backoff=BackoffPolicy(initial_seconds=0.001),
    )
    handler = LoopHandler(spec=spec)
    await handler(State(), _make_ctx())
    assert calls == 3


async def test_loop_without_body_raises() -> None:
    """Principle 6: a loop with no body must raise loudly, not silently no-op."""
    spec = LoopSpec(id="l1", body=None, exit_condition=_const_cond(True))
    with pytest.raises(ValueError, match="no body"):
        await LoopHandler(spec=spec)(State(), _make_ctx())


async def test_loop_without_exit_condition_raises() -> None:
    async def body(state: State, ctx: RunContext) -> State:
        return state

    spec = LoopSpec(id="l1", body=body, exit_condition=None)
    with pytest.raises(ValueError, match="no exit condition"):
        await LoopHandler(spec=spec)(State(), _make_ctx())

"""Test: the loop handler exits on condition met and respects iteration cap."""

from __future__ import annotations

from pathlib import Path

import pytest

from maestro_core.context import RunConfig, RunContext
from maestro_core.state import State, RunStatus
from maestro_core.checkpoint import SQLiteCheckpointStore
from maestro_core.streaming import EventBus
from maestro_llm.router import LLMRouter
from maestro_memory.manager import MemoryManager
from maestro_memory.short_term import ShortTermMemory
from maestro_memory.vector import InMemoryVectorMemory
from maestro_memory.graph import NetworkXGraphMemory
from maestro_memory.long_term import LongTermMemory
from maestro_verify.registry import VerifierRegistry
from maestro_plugins.registry import PluginRegistry
from maestro_loops.conditions import CallableCondition, ConditionResult
from maestro_loops.handler import LoopHandler, LoopSpec, LoopOutcome
from maestro_loops.types import OnExceedAction


@pytest.fixture
def ctx(tmp_path: Path) -> RunContext:
    db_path = str(tmp_path / "test.db")
    bus = EventBus()
    bus.start()
    return RunContext(
        config=RunConfig(run_id="test-run", template="blank", goal="test"),
        llm=LLMRouter.with_defaults(),
        memory=MemoryManager(
            short_term=ShortTermMemory(),
            semantic=InMemoryVectorMemory(),
            graph=NetworkXGraphMemory(persist_path=str(tmp_path / "graph.json")),
            long_term=LongTermMemory(db_path=db_path),
        ),
        checkpoints=SQLiteCheckpointStore(db_path=db_path),
        events=bus,
        verifiers=VerifierRegistry(),
        plugins=PluginRegistry(),
    )


async def test_loop_exits_when_condition_met(ctx: RunContext) -> None:
    """The loop should exit as soon as the condition is met."""
    counter = {"n": 0}

    async def _body(state: State, ctx: RunContext) -> State:
        counter["n"] += 1
        return state.with_updates(iteration=counter["n"])

    async def _cond(state: State, ctx: RunContext) -> ConditionResult:
        return ConditionResult(met=counter["n"] >= 3, reason=f"iter={counter['n']}")

    loop = LoopHandler(
        spec=LoopSpec(
            id="test_loop",
            body=_body,
            exit_condition=CallableCondition(fn=_cond),
            max_iterations=10,
            on_exceed=OnExceedAction.FAIL,
        )
    )

    state = State(run_id=ctx.config.run_id)
    result = await loop(state, ctx)

    assert counter["n"] == 3
    assert result.metadata.get("loop:test_loop:outcome") == LoopOutcome.EXIT_CONDITION_MET.value


async def test_loop_respects_max_iterations(ctx: RunContext) -> None:
    """The loop should stop at max_iterations if the condition never met."""
    counter = {"n": 0}

    async def _body(state: State, ctx: RunContext) -> State:
        counter["n"] += 1
        return state

    async def _cond(state: State, ctx: RunContext) -> ConditionResult:
        return ConditionResult(met=False, reason="never")

    loop = LoopHandler(
        spec=LoopSpec(
            id="test_loop",
            body=_body,
            exit_condition=CallableCondition(fn=_cond),
            max_iterations=5,
            on_exceed=OnExceedAction.CONTINUE,
        )
    )
    state = State(run_id=ctx.config.run_id)
    result = await loop(state, ctx)

    assert counter["n"] == 5
    assert result.metadata.get("loop:test_loop:outcome") == LoopOutcome.MAX_ITERATIONS.value


async def test_loop_escalates_on_exceed(ctx: RunContext) -> None:
    """On ESCALATE, the loop should pause with AWAITING_HUMAN status."""
    async def _body(state: State, ctx: RunContext) -> State:
        return state

    async def _cond(state: State, ctx: RunContext) -> ConditionResult:
        return ConditionResult(met=False, reason="never")

    loop = LoopHandler(
        spec=LoopSpec(
            id="test_loop",
            body=_body,
            exit_condition=CallableCondition(fn=_cond),
            max_iterations=2,
            on_exceed=OnExceedAction.ESCALATE,
        )
    )
    state = State(run_id=ctx.config.run_id)
    result = await loop(state, ctx)

    assert result.status == RunStatus.AWAITING_HUMAN
    assert "hitl_reason" in result.metadata

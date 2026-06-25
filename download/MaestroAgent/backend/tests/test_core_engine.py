"""Test: the core graph engine can run a simple 3-node graph end-to-end."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from maestro_core.context import RunConfig, RunContext
from maestro_core.engine import OrchestrationEngine
from maestro_core.graph import Graph, Node, ConditionalEdge
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


@pytest.fixture
def ctx(tmp_path: Path) -> RunContext:
    """Build a minimal RunContext for tests."""
    db_path = str(tmp_path / "test.db")
    bus = EventBus()
    bus.start()
    return RunContext(
        config=RunConfig(
            run_id="test-run",
            template="blank",
            goal="test goal",
            max_cost_usd=100.0,
            max_iterations=20,
        ),
        llm=LLMRouter.with_defaults(),  # no providers configured; tests stub calls
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


async def test_simple_linear_graph(ctx: RunContext) -> None:
    """Three nodes in a line: a → b → c. Each appends to messages."""
    calls: list[str] = []

    async def _a(state: State, ctx: RunContext) -> State:
        calls.append("a")
        return state.with_updates(messages=state.messages + [{"role": "x", "content": "a"}])

    async def _b(state: State, ctx: RunContext) -> State:
        calls.append("b")
        return state.with_updates(messages=state.messages + [{"role": "x", "content": "b"}])

    async def _c(state: State, ctx: RunContext) -> State:
        calls.append("c")
        return state.with_updates(messages=state.messages + [{"role": "x", "content": "c"}])

    g = Graph()
    g.add_node(Node(id="a", fn=_a))
    g.add_node(Node(id="b", fn=_b))
    g.add_node(Node(id="c", fn=_c))
    g.add_edge("a", "b")
    g.add_edge("b", "c")
    g.set_entry("a")

    engine = OrchestrationEngine(ctx=ctx, graph=g)
    result = await engine.run()

    assert result.status == RunStatus.SUCCEEDED
    assert calls == ["a", "b", "c"]
    assert result.final_state is not None
    assert len(result.final_state.messages) == 3


async def test_conditional_edge(ctx: RunContext) -> None:
    """Conditional edge: a → b if messages > 0 else a → c."""
    calls: list[str] = []

    async def _a(state: State, ctx: RunContext) -> State:
        calls.append("a")
        return state.with_updates(messages=state.messages + [{"role": "x", "content": "a"}])

    async def _b(state: State, ctx: RunContext) -> State:
        calls.append("b")
        return state

    async def _c(state: State, ctx: RunContext) -> State:
        calls.append("c")
        return state

    g = Graph()
    g.add_node(Node(id="a", fn=_a))
    g.add_node(Node(id="b", fn=_b))
    g.add_node(Node(id="c", fn=_c))
    # After a: if messages non-empty → b, else c.
    g.add_conditional_edge("a", "b", condition=lambda s: len(s.messages) > 0)
    g.add_conditional_edge("a", "c", condition=lambda s: len(s.messages) == 0)
    g.set_entry("a")

    engine = OrchestrationEngine(ctx=ctx, graph=g)
    result = await engine.run()

    assert result.status == RunStatus.SUCCEEDED
    assert "a" in calls
    assert "b" in calls
    assert "c" not in calls


async def test_checkpoint_persistence(ctx: RunContext) -> None:
    """A run's state is persisted and can be loaded back."""
    async def _a(state: State, ctx: RunContext) -> State:
        return state.with_updates(artifacts={"x": "1"})

    g = Graph()
    g.add_node(Node(id="a", fn=_a))
    g.set_entry("a")
    engine = OrchestrationEngine(ctx=ctx, graph=g)
    result = await engine.run()
    assert result.status == RunStatus.SUCCEEDED

    # Load the latest checkpoint.
    latest = await ctx.checkpoints.latest(ctx.config.run_id)
    assert latest is not None
    assert latest.artifacts.get("x") == "1"


async def test_audit_log_is_tamper_evident(ctx: RunContext) -> None:
    """The audit log's hash chain is verifiable."""
    async def _a(state: State, ctx: RunContext) -> State:
        return state
    g = Graph()
    g.add_node(Node(id="a", fn=_a))
    g.set_entry("a")
    engine = OrchestrationEngine(ctx=ctx, graph=g)
    await engine.run()

    log = await ctx.checkpoints.audit_log(ctx.config.run_id)
    assert len(log) > 0
    assert ctx.checkpoints.audit_verify(ctx.config.run_id) is True

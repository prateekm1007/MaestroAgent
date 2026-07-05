"""Smoke tests for maestro_core — the orchestration engine primitives.

Principle 2: the engine is the product. If its primitives are broken,
every run is broken. These tests cover State, RunContext budget, EventBus,
Graph validation, Node role enforcement.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from maestro_core.context import BudgetExhausted, RunConfig, RunContext
from maestro_core.graph import ConditionalEdge, Graph, Node, ParallelEdges, run_parallel_targets
from maestro_core.state import RunStatus, State
from maestro_core.streaming import Event, EventBus, EventType


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


def test_state_default_factory_generates_unique_ids() -> None:
    s1, s2 = State(), State()
    assert s1.run_id != s2.run_id
    assert s1.step_id != s2.step_id


def test_state_bump_increments_revision() -> None:
    s1 = State()
    s2 = s1.bump()
    assert s2.revision == s1.revision + 1
    assert s2.parent_step_id == s1.step_id


def test_state_with_updates_preserves_old_fields() -> None:
    s1 = State(run_id="r1")
    s2 = s1.with_updates(current_node="n2")
    assert s2.run_id == "r1"
    assert s2.current_node == "n2"


# ---------------------------------------------------------------------------
# RunContext — budget enforcement
# ---------------------------------------------------------------------------


def test_check_budget_raises_when_exhausted() -> None:
    cfg = RunConfig(run_id="r1", template="t", goal="g", max_cost_usd=5.0)
    ctx = RunContext(
        config=cfg, llm=None, memory=None, checkpoints=None,  # type: ignore[arg-type]
        events=None, verifiers=None, plugins=None,  # type: ignore[arg-type]
        cost_so_far=5.0,
    )
    with pytest.raises(BudgetExhausted):
        ctx.check_budget()


def test_check_budget_passes_when_under() -> None:
    cfg = RunConfig(run_id="r1", template="t", goal="g", max_cost_usd=5.0)
    ctx = RunContext(
        config=cfg, llm=None, memory=None, checkpoints=None,  # type: ignore[arg-type]
        events=None, verifiers=None, plugins=None,  # type: ignore[arg-type]
        cost_so_far=4.99,
    )
    ctx.check_budget()  # must not raise


# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------


async def test_event_bus_subscriber_receives_published_events() -> None:
    bus = EventBus()
    received: list[Event] = []

    async def sub(event: Event) -> None:
        received.append(event)

    bus.subscribe(sub)
    await bus.start_async()
    try:
        await bus.emit(EventType.RUN_STARTED, run_id="r1", goal="test")
        await asyncio.sleep(0.05)
    finally:
        await bus.stop()

    # Filter the internal __shutdown__ sentinel.
    real = [e for e in received if e.run_id != "__shutdown__"]
    assert len(real) == 1
    assert real[0].type is EventType.RUN_STARTED


async def test_event_bus_bad_subscriber_does_not_break_bus() -> None:
    """Principle 6: a bad subscriber must not silently break the bus."""
    bus = EventBus()
    good: list[Event] = []

    async def bad_sub(event: Event) -> None:
        raise RuntimeError("bad")

    async def good_sub(event: Event) -> None:
        good.append(event)

    bus.subscribe(bad_sub)
    bus.subscribe(good_sub)
    await bus.start_async()
    try:
        await bus.emit(EventType.RUN_STARTED, run_id="r1")
        await asyncio.sleep(0.05)
    finally:
        await bus.stop()

    real = [e for e in good if e.run_id != "__shutdown__"]
    assert len(real) == 1


# ---------------------------------------------------------------------------
# Graph validation
# ---------------------------------------------------------------------------


async def _identity(state: State, ctx: RunContext) -> State:
    return state


def test_graph_add_node_sets_first_as_entry() -> None:
    g = Graph()
    g.add_node(Node(id="n1", fn=_identity))
    assert g.entry == "n1"


def test_graph_rejects_duplicate_node_ids() -> None:
    g = Graph()
    g.add_node(Node(id="n1", fn=_identity))
    with pytest.raises(ValueError, match="Duplicate"):
        g.add_node(Node(id="n1", fn=_identity))


def test_graph_rejects_edge_to_unknown_node() -> None:
    g = Graph()
    g.add_node(Node(id="n1", fn=_identity))
    with pytest.raises(ValueError, match="Unknown node"):
        g.add_edge("n1", "does_not_exist")


def test_graph_validate_passes_for_well_formed_graph() -> None:
    g = Graph()
    g.add_node(Node(id="n1", fn=_identity))
    g.add_node(Node(id="n2", fn=_identity))
    g.add_edge("n1", "n2")
    assert g.validate() == []


def test_conditional_edge_swallows_condition_exception() -> None:
    """Principle 6 note: ConditionalEdge.matches() catches condition exceptions
    and returns False rather than propagating. This is a deliberate safety
    property — a buggy condition shouldn't crash the run. Documented here."""
    def bad_condition(s: State) -> bool:
        raise RuntimeError("bug")

    e = ConditionalEdge(source="a", target="b", condition=bad_condition)
    assert e.matches(State()) is False


# ---------------------------------------------------------------------------
# Node role enforcement
# ---------------------------------------------------------------------------


async def test_node_rejects_unauthorized_role() -> None:
    cfg = RunConfig(run_id="r1", template="t", goal="g")
    ctx = RunContext(
        config=cfg, llm=None, memory=None, checkpoints=None,  # type: ignore[arg-type]
        events=None, verifiers=None, plugins=None,  # type: ignore[arg-type]
        agent_role="junior",
    )

    async def admin_fn(state: State, ctx: RunContext) -> State:
        return state

    node = Node(id="admin_op", fn=admin_fn, allowed_roles=["admin"])
    with pytest.raises(PermissionError, match="role"):
        await node(State(), ctx)


async def test_node_allows_authorized_role() -> None:
    cfg = RunConfig(run_id="r1", template="t", goal="g")
    ctx = RunContext(
        config=cfg, llm=None, memory=None, checkpoints=None,  # type: ignore[arg-type]
        events=None, verifiers=None, plugins=None,  # type: ignore[arg-type]
        agent_role="admin",
    )

    async def admin_fn(state: State, ctx: RunContext) -> State:
        return state.with_updates(current_node="admin_op")

    node = Node(id="admin_op", fn=admin_fn, allowed_roles=["admin"])
    result = await node(State(), ctx)
    assert result.current_node == "admin_op"

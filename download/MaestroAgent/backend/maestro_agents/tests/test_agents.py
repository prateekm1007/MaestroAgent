"""Smoke tests for maestro_agents — the unit of agency."""

from __future__ import annotations

import json

import pytest

from maestro_agents.base import AgentSpec, BaseAgent
from maestro_core.context import BudgetExhausted, RunConfig, RunContext
from maestro_core.state import State
from maestro_core.streaming import EventBus


def test_agent_spec_defaults() -> None:
    s = AgentSpec(role="Engineer", goal="ship")
    assert s.backstory == ""
    assert s.tools == []
    assert s.memory_scope == "private"
    assert s.temperature == 0.2


def test_agent_to_dict_is_json_serializable() -> None:
    spec = AgentSpec(role="R", goal="g", llm_hint={"model": "gpt-4o"})
    d = BaseAgent(id="a1", spec=spec).to_dict()
    json.dumps(d)  # must not raise
    assert d["spec"]["role"] == "R"


def test_agent_system_prompt_includes_role_and_goal() -> None:
    agent = BaseAgent(id="a", spec=AgentSpec(role="Backend Dev", goal="ship API"))
    sp = agent._system_prompt()
    assert "Backend Dev" in sp
    assert "ship API" in sp


async def test_agent_raises_on_exhausted_budget() -> None:
    """Principle 6: budget exhaustion must raise loudly, not silently proceed."""
    spec = AgentSpec(role="A", goal="g")
    agent = BaseAgent(id="a", spec=spec)
    cfg = RunConfig(run_id="r1", template="t", goal="g", max_cost_usd=5.0)
    ctx = RunContext(
        config=cfg, llm=None, memory=None, checkpoints=None,  # type: ignore[arg-type]
        events=EventBus(), verifiers=None, plugins=None,  # type: ignore[arg-type]
        cost_so_far=5.0,
    )
    with pytest.raises(BudgetExhausted):
        await agent(State(), ctx)


def test_debate_module_imports() -> None:
    from maestro_agents import debate
    assert debate


def test_supervisor_module_imports() -> None:
    from maestro_agents import supervisor
    assert supervisor

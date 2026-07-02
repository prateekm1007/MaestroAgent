"""Smoke tests for maestro_hybrid — CrewAI → MaestroAgent graph compiler."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from maestro_hybrid import _slug, crew_to_graph
from maestro_core.graph import Graph


@dataclass
class _FakeAgent:
    role: str
    goal: str
    backstory: str = ""
    tools: list[Any] = field(default_factory=list)
    llm: Any = None
    allow_delegation: bool = False


@dataclass
class _FakeTask:
    agent: Any
    description: str = ""


@dataclass
class _FakeCrew:
    agents: list[Any]
    tasks: list[Any]
    process: str = "sequential"


def test_slug_lowercases_and_replaces_unsafe() -> None:
    assert _slug("Senior Engineer!") == "senior_engineer"
    assert _slug("") == "agent"


def test_crew_to_graph_rejects_empty_agents() -> None:
    with pytest.raises(ValueError, match="no agents"):
        crew_to_graph(_FakeCrew(agents=[], tasks=[_FakeTask(agent=None)]))


def test_crew_to_graph_rejects_empty_tasks() -> None:
    a = _FakeAgent(role="W", goal="g")
    with pytest.raises(ValueError, match="no tasks"):
        crew_to_graph(_FakeCrew(agents=[a], tasks=[]))


def test_crew_to_graph_sequential_valid() -> None:
    a1 = _FakeAgent(role="Researcher", goal="r")
    a2 = _FakeAgent(role="Writer", goal="w")
    crew = _FakeCrew(agents=[a1, a2], tasks=[_FakeTask(agent=a1), _FakeTask(agent=a2)])
    g = crew_to_graph(crew)
    assert isinstance(g, Graph)
    assert g.entry is not None
    assert len(g.nodes) == 2
    assert g.validate() == []

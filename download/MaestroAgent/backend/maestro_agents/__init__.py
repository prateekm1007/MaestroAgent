"""maestro_agents — agent primitives, supervisors, sub-agents, crews, debate.

This package wraps CrewAI's `Agent`/`Crew` abstractions as first-class
citizens of MaestroAgent, AND provides our own supervisor / dynamic
sub-agent runtime on top.

Layering
--------
- `BaseAgent` — our thin wrapper around a role/goal/backstory definition
  and an LLM call. Works with any provider via `LLMRouter`.
- `CrewAdapter` — adapts a CrewAI `Crew` into a single graph node so it
  can be embedded in a larger MaestroAgent graph.
- `Supervisor` — a supervisor agent that can spawn hierarchical
  sub-agents, delegate sub-goals, and auto-merge results.
- `SubAgent` — a dynamically-spawned child with isolated context and tools.
- `Debate` — multi-agent debate / vote / criticize primitives.
"""

from maestro_agents.base import BaseAgent, AgentSpec
from maestro_agents.supervisor import Supervisor
from maestro_agents.subagent import SubAgent, SubAgentSpec
from maestro_agents.crew import CrewAdapter, crew_as_node
from maestro_agents.debate import Debate, DebateResult, VotePolicy

__all__ = [
    "BaseAgent",
    "AgentSpec",
    "Supervisor",
    "SubAgent",
    "SubAgentSpec",
    "CrewAdapter",
    "crew_as_node",
    "Debate",
    "DebateResult",
    "VotePolicy",
]

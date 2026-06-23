"""maestro_hybrid — LangGraph + CrewAI hybrid orchestration.

This module is the bridge between CrewAI's high-level "crew" abstraction
and LangGraph's stateful graphs. It lets users author a crew in
CrewAI's ergonomic role/goal/backstory style, then compile it into a
MaestroAgent graph that gets checkpoints, loops, sub-agents, and full
observability — for free.

Why a separate module?
----------------------
- `maestro_agents.crew` wraps a CrewAI Crew as a single node (black box).
- `maestro_hybrid` decomposes a Crew into individual agent nodes wired
  into a LangGraph-style stateful graph, so each agent's call is
  checkpointed, streamed, and individually observable.

The decomposition rules:
1. Each CrewAI `Agent` becomes a `BaseAgent` node.
2. Each CrewAI `Task` becomes the agent's `goal` for that invocation.
3. Task dependencies become graph edges.
4. The crew's `process` (sequential or hierarchical) determines the
   graph topology.

Usage
-----
    from crewai import Agent, Task, Crew
    from maestro_hybrid import crew_to_graph

    researcher = Agent(role="Researcher", goal="...", backstory="...")
    writer = Agent(role="Writer", goal="...", backstory="...")
    crew = Crew(agents=[researcher, writer], tasks=[...], process="sequential")
    graph = crew_to_graph(crew)
    # `graph` is a maestro_core.Graph — feed it to OrchestrationEngine.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from maestro_agents.base import AgentSpec, BaseAgent
from maestro_core.graph import Graph, Node

logger = logging.getLogger(__name__)


def crew_to_graph(crew: Any, prefix: str = "crew") -> Graph:
    """Compile a CrewAI Crew into a MaestroAgent stateful Graph.

    Args:
        crew: A CrewAI Crew instance (agents + tasks + process).
        prefix: Node id prefix to avoid collisions when embedding
            multiple crews in one graph.

    Returns:
        A `maestro_core.Graph` ready to be run by `OrchestrationEngine`.
    """
    agents: list[Any] = list(getattr(crew, "agents", []))
    tasks: list[Any] = list(getattr(crew, "tasks", []))
    process = str(getattr(crew, "process", "sequential")).lower()

    if not agents:
        raise ValueError("Crew has no agents")
    if not tasks:
        raise ValueError("Crew has no tasks")

    # Build a map of role -> BaseAgent so tasks can be assigned.
    agent_by_role: dict[str, BaseAgent] = {}
    for a in agents:
        role = getattr(a, "role", f"agent_{len(agent_by_role)}")
        node_id = f"{prefix}__{_slug(role)}"
        llm_hint: dict[str, str] = {}
        llm = getattr(a, "llm", None)
        if llm is not None:
            model = getattr(llm, "model", "")
            if model:
                llm_hint["model"] = model
        spec = AgentSpec(
            role=role,
            goal=getattr(a, "goal", "") or f"Perform {role} duties",
            backstory=getattr(a, "backstory", "") or "",
            tools=[getattr(t, "name", str(t)) for t in (getattr(a, "tools", None) or [])],
            llm_hint=llm_hint,
            memory_scope="crew",
            allow_delegation=bool(getattr(a, "allow_delegation", False)),
            temperature=0.2,
        )
        agent_by_role[role] = BaseAgent(id=node_id, spec=spec)

    g = Graph()
    for agent in agent_by_role.values():
        g.add_node(Node(
            id=agent.id,
            fn=agent,
            description=f"CrewAI agent: {agent.spec.role}",
        ))

    # Wire edges based on process type.
    if process == "sequential":
        prev_node_id: str | None = None
        for task in tasks:
            role = getattr(task, "agent", None)
            role_name = getattr(role, "role", None) if role else None
            if role_name is None or role_name not in agent_by_role:
                logger.warning("Task has no resolvable agent; skipping: %s", task)
                continue
            node_id = agent_by_role[role_name].id
            if prev_node_id is not None and prev_node_id != node_id:
                g.add_edge(prev_node_id, node_id)
            if prev_node_id is None:
                g.set_entry(node_id)
            prev_node_id = node_id
        if g.entry is None and agent_by_role:
            first = next(iter(agent_by_role.values()))
            g.set_entry(first.id)

    elif process == "hierarchical":
        if not agent_by_role:
            raise ValueError("hierarchical crew has no agents")
        manager = agent_by_role[next(iter(agent_by_role))]
        g.set_entry(manager.id)
        prev = manager.id
        for agent in list(agent_by_role.values())[1:]:
            g.add_edge(prev, agent.id)
            prev = agent.id

    else:
        logger.warning("Unknown crew process '%s'; falling back to sequential", process)
        ids = list(agent_by_role.keys())
        for i in range(len(ids) - 1):
            g.add_edge(agent_by_role[ids[i]].id, agent_by_role[ids[i + 1]].id)
        if ids:
            g.set_entry(agent_by_role[ids[0]].id)

    problems = g.validate()
    if problems:
        raise ValueError(f"Compiled graph has problems: {problems}")

    logger.info(
        "Compiled crew to graph: %d agents, %d edges, entry=%s",
        len(agent_by_role), len(g.edges), g.entry,
    )
    return g


def _slug(s: str) -> str:
    """Make a string safe for use as a node id."""
    return re.sub(r"[^a-z0-9_]+", "_", s.lower()).strip("_") or "agent"

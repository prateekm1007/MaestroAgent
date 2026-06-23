"""Template: hybrid crew — CrewAI crew compiled to a MaestroAgent graph.

This template demonstrates the `maestro_hybrid` module: a CrewAI Crew
is compiled into a MaestroAgent stateful graph, getting checkpoints,
streaming, and observability for free while preserving CrewAI's
ergonomic role/goal/backstory API.

Usage
-----
    maestro run examples/templates/hybrid_crew.py --goal "Write a blog post about local-first AI"

Flow
----
    researcher (CrewAI Agent) → writer (CrewAI Agent) → editor (CrewAI Agent)

Each agent is a separate graph node (not a black-box crew), so:
- Each agent's LLM call is individually checkpointed.
- Each agent's output streams to the UI in real time.
- The graph can be paused/resumed between agents.
- Costs are tracked per agent, not just per crew.
"""

from __future__ import annotations

from typing import Any

from maestro_core.graph import Graph, Node


def build_graph(goal: str, **extras: Any) -> Graph:
    """Build a graph from a CrewAI crew via maestro_hybrid.

    We try to use real CrewAI classes if available; if CrewAI isn't
    installed (or fails to import), we fall back to building the
    equivalent BaseAgent nodes directly. This makes the template
    runnable in minimal environments.
    """
    try:
        from crewai import Agent, Task, Crew, Process
        from maestro_hybrid import crew_to_graph

        researcher = Agent(
            role="Researcher",
            goal=f"Find 3-5 high-quality sources about: {goal}",
            backstory="PhD in CS with a knack for finding canonical references.",
            allow_delegation=False,
            verbose=False,
        )
        writer = Agent(
            role="Writer",
            goal="Draft a 800-word blog post from the researcher's sources.",
            backstory="Former Wired editor. Clear, engaging, no fluff.",
            allow_delegation=False,
            verbose=False,
        )
        editor = Agent(
            role="Editor",
            goal="Polish the draft for clarity, grammar, and structure.",
            backstory="Meticulous editor with 15 years at Nature.",
            allow_delegation=False,
            verbose=False,
        )

        research_task = Task(
            description=f"Research: {goal}",
            agent=researcher,
            expected_output="A list of 3-5 sources with summaries.",
        )
        write_task = Task(
            description="Draft the blog post from the research.",
            agent=writer,
            expected_output="An 800-word draft.",
        )
        edit_task = Task(
            description="Edit the draft for clarity and grammar.",
            agent=editor,
            expected_output="A polished 800-word blog post.",
        )

        crew = Crew(
            agents=[researcher, writer, editor],
            tasks=[research_task, write_task, edit_task],
            process=Process.sequential,
            verbose=False,
        )

        return crew_to_graph(crew, prefix="blog_crew")

    except ImportError:
        # CrewAI not installed — build the equivalent with BaseAgent.
        from maestro_agents.base import AgentSpec, BaseAgent

        async def _noop(state, ctx):
            from maestro_core.state import RunStatus
            return state.with_updates(status=RunStatus.SUCCEEDED)

        g = Graph()
        g.add_node(Node(id="researcher", fn=BaseAgent(
            id="researcher",
            spec=AgentSpec(
                role="Researcher",
                goal=f"Find 3-5 sources about: {goal}",
                backstory="PhD in CS.",
                llm_hint={"provider": "ollama"},
                memory_scope="crew",
            ),
        )))
        g.add_node(Node(id="writer", fn=BaseAgent(
            id="writer",
            spec=AgentSpec(
                role="Writer",
                goal="Draft an 800-word blog post.",
                backstory="Former Wired editor.",
                llm_hint={"provider": "ollama"},
                memory_scope="crew",
            ),
        )))
        g.add_node(Node(id="editor", fn=BaseAgent(
            id="editor",
            spec=AgentSpec(
                role="Editor",
                goal="Polish the draft.",
                backstory="15 years at Nature.",
                llm_hint={"provider": "ollama"},
                memory_scope="crew",
            ),
        )))
        g.add_node(Node(id="done", fn=_noop))
        g.add_edge("researcher", "writer")
        g.add_edge("writer", "editor")
        g.add_edge("editor", "done")
        g.set_entry("researcher")
        return g

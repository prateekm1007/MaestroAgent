"""Template: research crew — survey a topic and produce a report.

Demonstrates the hybrid model: a CrewAI-style crew of role-playing
agents wrapped as a single node in a MaestroAgent graph. After the
crew produces a draft, an evaluator-optimizer polishes it against a
rubric, and a critic loop ensures the final report cites sources.

Usage
-----
    maestro run examples/templates/research_crew.py --goal "Survey of retrieval-augmented generation, 2024"
"""

from __future__ import annotations

from typing import Any

from maestro_agents.base import AgentSpec, BaseAgent
from maestro_loops.conditions import CriticCondition
from maestro_loops.handler import LoopHandler, LoopSpec
from maestro_loops.types import OnExceedAction
from maestro_core.graph import Graph, Node


def build_graph(goal: str, **extras: Any) -> Graph:
    """Build the research crew graph.

    Flow:
        entry → research_agent (gather sources)
              → synthesize_agent (draft report)
              → polish_loop (evaluator-optimizer until critic score >= 0.85)
              → done
    """
    g = Graph()

    research_agent = BaseAgent(
        id="researcher",
        spec=AgentSpec(
            role="Senior Researcher",
            goal=f"Find and summarize 5-10 high-quality sources on: {goal}",
            backstory=(
                "PhD in CS with a knack for finding the canonical papers and "
                "the best survey articles. Cites arXiv, ACM, IEEE."
            ),
            tools=["http_get", "file_read", "file_write"],
            llm_hint={"provider": "ollama", "model": "llama3.1:8b"},
            memory_scope="shared",
            temperature=0.3,
        ),
    )
    g.add_node(Node(id="researcher", fn=research_agent, description="Gather and summarize sources"))

    synthesize_agent = BaseAgent(
        id="synthesizer",
        spec=AgentSpec(
            role="Senior Technical Writer",
            goal="Synthesize the researcher's sources into a coherent 1500-word report.",
            backstory="Former Wired editor. Structures arguments clearly. No fluff.",
            tools=["file_read", "file_write"],
            llm_hint={"provider": "ollama", "model": "llama3.1:8b"},
            memory_scope="shared",
            temperature=0.4,
        ),
    )
    g.add_node(Node(id="synthesizer", fn=synthesize_agent, description="Draft the report"))

    # Polish loop: iterate on the report until the critic is satisfied.
    polish_agent = BaseAgent(
        id="polisher",
        spec=AgentSpec(
            role="Editor",
            goal="Revise the report to address the critic's feedback.",
            backstory="Meticulous editor with a 20-year career at Nature.",
            tools=["file_read", "file_write"],
            llm_hint={"provider": "ollama", "model": "llama3.1:8b"},
            memory_scope="shared",
            temperature=0.4,
        ),
    )

    async def _polish_body(state, ctx):
        # Read the latest report from artifacts and ask the polisher to revise.
        last_report = state.artifacts.get("synthesizer_last_output", "")
        if not last_report:
            last_report = state.artifacts.get("polisher_last_output", "")
        enriched = state.with_updates(
            messages=state.messages + [
                {"role": "user", "content": f"Revise this report:\n\n{last_report[:6000]}"}
            ]
        )
        return await polish_agent(enriched, ctx)

    polish_loop = LoopHandler(
        spec=LoopSpec(
            id="polish_until_critic_happy",
            body=_polish_body,
            exit_condition=CriticCondition(
                rubric=(
                    "The report must: (1) have a clear structure with sections, "
                    "(2) cite at least 5 sources, (3) be free of marketing language, "
                    "(4) be at most 2000 words, (5) end with a balanced conclusion."
                ),
                threshold=0.85,
                agent_id="report_critic",
            ),
            max_iterations=4,
            max_cost_usd=2.0,
            on_exceed=OnExceedAction.ESCALATE,
        )
    )
    g.add_node(Node(id="polish_loop", fn=polish_loop, description="Iterate report until critic >= 0.85"))

    async def _done(state, ctx):
        from maestro_core.state import RunStatus
        return state.with_updates(status=RunStatus.SUCCEEDED)
    g.add_node(Node(id="done", fn=_done, description="Finalize"))

    g.add_edge("researcher", "synthesizer")
    g.add_edge("synthesizer", "polish_loop")
    g.add_edge("polish_loop", "done")
    g.set_entry("researcher")
    return g

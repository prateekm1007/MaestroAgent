"""Template: build a full SaaS MVP.

This template demonstrates MaestroAgent's flagship capability: turning
a one-line goal into a working SaaS MVP. It uses:

- A `Supervisor` to decompose the goal into research / architecture /
  build / test sub-goals.
- Dynamic `SubAgent`s for each sub-goal.
- A `LoopHandler` with `TestPassCondition` to run until tests pass.
- An `EvaluatorOptimizer` loop to polish the final README.

Usage
-----
    maestro run examples/templates/build_saas_mvp.py --goal "Build a notes SaaS with auth + Stripe"

or via the API:

    POST /api/runs
    {"template": "build_saas_mvp", "goal": "Build a notes SaaS with auth + Stripe"}
"""

from __future__ import annotations

from typing import Any

from maestro_agents.base import AgentSpec, BaseAgent
from maestro_agents.supervisor import Supervisor
from maestro_loops.conditions import TestPassCondition
from maestro_loops.handler import LoopHandler, LoopSpec
from maestro_loops.types import OnExceedAction
from maestro_core.graph import Graph, Node


def build_graph(goal: str, **extras: Any) -> Graph:
    """Build the SaaS MVP graph.

    Flow:
        entry → supervisor (decompose + spawn + merge)
              → loop_until_tests_pass (build + test, retry)
              → polish_readme (evaluator-optimizer)
              → done
    """
    g = Graph()

    # --- Supervisor node ---
    supervisor = Supervisor(
        id="mvp_supervisor",
        spec=AgentSpec(
            role="Senior Product Engineer",
            goal=f"Coordinate the construction of: {goal}",
            backstory=(
                "20 years building SaaS products. Pragmatic, ships fast, "
                "writes tests first, prefers simple architectures."
            ),
            allow_spawning=True,
            allow_delegation=True,
            llm_hint={"provider": "ollama", "model": "llama3.1:8b"},
            memory_scope="shared",
        ),
    )
    g.add_node(Node(id="supervisor", fn=supervisor, description="Decompose goal + spawn sub-agents"))

    # --- Build agent (used inside the loop) ---
    build_agent = BaseAgent(
        id="build_agent",
        spec=AgentSpec(
            role="Senior Full-Stack Engineer",
            goal="Write code that implements the next slice of the SaaS.",
            backstory="Expert in Next.js, Prisma, Stripe, Tailwind. Writes tests alongside code.",
            tools=["shell", "file_read", "file_write", "git_status"],
            llm_hint={"provider": "ollama", "model": "llama3.1:8b"},
            memory_scope="shared",
        ),
    )

    # --- Loop: build → test until tests pass ---
    async def _build_body(state, ctx):
        # Run the build agent for one turn.
        return await build_agent(state, ctx)

    build_loop = LoopHandler(
        spec=LoopSpec(
            id="build_until_tests_pass",
            body=_build_body,
            exit_condition=TestPassCondition(command="pytest -x --tb=short", name="pytest"),
            max_iterations=15,
            max_cost_usd=5.0,
            max_wall_clock_seconds=20 * 60,
            on_exceed=OnExceedAction.ESCALATE,
            stagnation_window=3,
            stagnation_min_improvement=0.05,
        )
    )
    g.add_node(Node(id="build_loop", fn=build_loop, description="Loop: build + test until tests pass"))

    # --- Polish README via evaluator-optimizer ---
    from maestro_verify.evaluator import EvaluatorOptimizer

    async def _readme_generator(state, suggestions, ctx):
        from maestro_core.state import State
        # Use the build agent with the suggestions as feedback.
        last_output = state.artifacts.get("build_agent_last_output", "")
        prompt_agent = BaseAgent(
            id="readme_writer",
            spec=AgentSpec(
                role="Technical Writer",
                goal="Write a clear, accurate README for the SaaS MVP.",
                backstory="Documentation expert who hates hype.",
                tools=["file_read"],
                llm_hint={"provider": "ollama", "model": "llama3.1:8b"},
                memory_scope="shared",
            ),
        )
        # Inject suggestions into state.
        enriched = state.with_updates(
            messages=state.messages + [
                {"role": "user", "content": f"Feedback to address: {'; '.join(suggestions) or 'none'}"}
            ]
        )
        result = await prompt_agent(enriched, ctx)
        return result.artifacts.get("readme_writer_last_output", "")

    polish = EvaluatorOptimizer(
        id="polish_readme",
        generator=_readme_generator,
        rubric=(
            "The README must: (1) explain what the product does in 1-2 sentences, "
            "(2) have a Quick Start with copy-paste commands, (3) document env vars, "
            "(4) include a license section. No marketing fluff."
        ),
        threshold=0.85,
        max_iterations=3,
    )

    async def _polish_node(state, ctx):
        return await polish.run(state, ctx)

    g.add_node(Node(id="polish_readme", fn=_polish_node, description="Evaluator-optimizer loop for README"))

    # --- Done ---
    async def _done(state, ctx):
        from maestro_core.state import RunStatus
        return state.with_updates(status=RunStatus.SUCCEEDED)

    g.add_node(Node(id="done", fn=_done, description="Finalize run"))

    # --- Edges ---
    g.add_edge("supervisor", "build_loop")
    g.add_edge("build_loop", "polish_readme")
    g.add_edge("polish_readme", "done")
    g.set_entry("supervisor")

    return g

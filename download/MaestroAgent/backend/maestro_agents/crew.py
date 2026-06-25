"""CrewAdapter — embed a CrewAI Crew as a single graph node.

MaestroAgent is hybrid by construction: a `Crew` (CrewAI's flat
collection of role-playing agents) is wrapped as a single composite
node in our stateful graph. This lets users prototype fast with the
crew abstraction and graduate to graphs as complexity grows — without
leaving the same run.

Usage
-----
    from crewai import Agent, Crew, Task
    from maestro_agents.crew import crew_as_node

    researcher = Agent(role="Researcher", goal="...", backstory="...")
    writer = Agent(role="Writer", goal="...", backstory="...")
    crew = Crew(agents=[researcher, writer], tasks=[...])
    node = crew_as_node("research_and_write", crew)
    graph.add_node(node)

Why an adapter and not native?
------------------------------
CrewAI's runtime has its own loop, retry, and tool-call logic. We do
not reimplement it; we wrap it so the crew runs as a black box from
the graph's perspective. The crew's internal state is opaque to the
graph (the graph sees only the crew's final output). This is the right
boundary: the graph handles workflow-level concerns (loops, branches,
HITL); the crew handles task-level execution.

If users need finer-grained control, they should graduate to using
`BaseAgent` and `Supervisor` directly — that's the explicit upgrade
path the hybrid model is designed for.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from maestro_core.graph import Node
from maestro_core.state import State
from maestro_core.streaming import EventType

if TYPE_CHECKING:
    from maestro_core.context import RunContext

logger = logging.getLogger(__name__)


class CrewAdapter:
    """Wraps a CrewAI Crew as a MaestroAgent graph node."""

    def __init__(self, id: str, crew: Any, description: str = "") -> None:
        self.id = id
        self.crew = crew
        self.description = description

    def as_node(self) -> Node:
        """Return a `Node` whose `fn` runs the crew."""

        async def _run(state: State, ctx: "RunContext") -> State:
            ctx.check_budget()
            await ctx.events.emit(
                EventType.STEP_STARTED,
                run_id=ctx.config.run_id,
                node_id=self.id,
                kind="crew",
            )
            try:
                # CrewAI's Crew.kickoff() is synchronous; run in a thread.
                import anyio
                result = await anyio.to_thread.run_sync(self.crew.kickoff)
                # CrewAI returns a CrewOutput in newer versions; we stringify.
                output_text = getattr(result, "raw", None) or str(result)
                await ctx.events.emit(
                    EventType.STEP_COMPLETED,
                    run_id=ctx.config.run_id,
                    node_id=self.id,
                    kind="crew",
                )
                return state.with_updates(
                    messages=state.messages + [
                        {
                            "role": "assistant",
                            "agent_id": self.id,
                            "role_label": "crew",
                            "content": str(output_text),
                        }
                    ],
                    artifacts={**state.artifacts, f"{self.id}_output": str(output_text)},
                )
            except Exception as exc:
                logger.exception("Crew %s failed", self.id)
                await ctx.events.emit(
                    EventType.STEP_FAILED,
                    run_id=ctx.config.run_id,
                    node_id=self.id,
                    error=str(exc),
                )
                raise

        return Node(
            id=self.id,
            fn=_run,
            description=self.description or f"CrewAI crew: {self.id}",
        )


def crew_as_node(id: str, crew: Any, description: str = "") -> Node:
    """One-liner: wrap a CrewAI crew as a graph node."""
    return CrewAdapter(id=id, crew=crew, description=description).as_node()

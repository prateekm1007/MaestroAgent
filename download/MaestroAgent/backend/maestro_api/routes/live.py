"""Live control routes — spawn sub-agents, trigger debates, create loops at runtime.

These routes let the UI reach INTO a running run and inject actions:
- Spawn a new sub-agent under a supervisor mid-run.
- Trigger a debate between named agents.
- Create and attach a new loop to the graph.

These are the "human-in-the-loop" affordances that make MaestroAgent
feel like a control surface, not just a viewer. They write to the
audit log and emit events on the run's bus so the UI sees the effect.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from maestro_core.streaming import EventType

router = APIRouter()


class SpawnSubAgentRequest(BaseModel):
    parent_id: str
    sub_goal: str
    role: str = "Sub-agent"
    backstory: str = ""
    tools: list[str] = Field(default_factory=list)
    llm_hint: dict[str, str] = Field(default_factory=dict)
    memory_scope: str = "private"
    max_iterations: int = 10


@router.post("/{run_id}/spawn")
async def spawn_subagent(
    run_id: str, req: SpawnSubAgentRequest, request: Request
) -> dict[str, Any]:
    """Spawn a sub-agent under the given parent in a running run.

    The supervisor on the next iteration will pick this up and run it.
    Returns the new sub-agent id (also emitted as an event).
    """
    state: Any = request.app.state.maestro
    if run_id not in state.live_buses:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not live")

    sub_id = f"{req.parent_id}__sub_{uuid.uuid4().hex[:8]}"

    # Persist the spawn request in the audit log.
    await state.checkpoints.audit(
        run_id,
        "agent.spawn_requested",
        {
            "sub_id": sub_id,
            "parent_id": req.parent_id,
            "sub_goal": req.sub_goal,
            "role": req.role,
            "tools": req.tools,
            "llm_hint": req.llm_hint,
        },
    )

    # Emit a live event so the UI updates immediately.
    bus = state.get_or_create_bus(run_id)
    await bus.emit(
        EventType.AGENT_SPAWNED,
        run_id=run_id,
        agent_id=sub_id,
        parent_id=req.parent_id,
        role=req.role,
        goal=req.sub_goal,
        source="ui",
    )

    # Register in graph memory so the agent tree shows it.
    if state.memory and state.memory.graph:
        from maestro_memory.graph import GraphEdge, GraphNode
        await state.memory.graph.add_node(
            GraphNode(
                kind="agent",
                id=sub_id,
                properties={
                    "run_id": run_id,
                    "parent_id": req.parent_id,
                    "role": req.role,
                    "sub_goal": req.sub_goal,
                    "status": "pending",
                    "source": "ui",
                },
            )
        )
        await state.memory.graph.add_edge(
            GraphEdge(kind="spawned", src=req.parent_id, dst=sub_id)
        )

    return {"sub_id": sub_id, "parent_id": req.parent_id, "status": "queued"}


class DebateRequest(BaseModel):
    topic: str
    participants: list[str]
    seek_consensus: bool = True
    max_rounds: int = 3


@router.post("/{run_id}/debate")
async def trigger_debate(
    run_id: str, req: DebateRequest, request: Request
) -> dict[str, Any]:
    """Trigger a debate between the named agents in a running run.

    The debate runs synchronously (blocking the calling HTTP request)
    and returns the resolution. The supervisor will see the resolution
    in the run state on its next iteration.
    """
    state: Any = request.app.state.maestro
    if run_id not in state.live_buses:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not live")

    if len(req.participants) < 2:
        raise HTTPException(status_code=400, detail="debate needs >= 2 participants")

    debate_id = f"debate_{uuid.uuid4().hex[:8]}"

    await state.checkpoints.audit(
        run_id,
        "debate.requested",
        {
            "debate_id": debate_id,
            "topic": req.topic,
            "participants": req.participants,
            "seek_consensus": req.seek_consensus,
        },
    )

    bus = state.get_or_create_bus(run_id)
    await bus.emit(
        EventType.AGENT_DEBATE,
        run_id=run_id,
        debate_id=debate_id,
        topic=req.topic,
        participants=req.participants,
        source="ui",
    )

    # In v0.1 we just queue the debate request — the supervisor picks
    # it up on its next iteration. v0.2 will run it inline.
    return {
        "debate_id": debate_id,
        "status": "queued",
        "participants": req.participants,
    }


class CreateLoopRequest(BaseModel):
    loop_id: str
    body_agent_id: str
    exit_kind: str = "tests"  # "tests" | "metric" | "critic" | "callable"
    exit_config: dict[str, Any] = Field(default_factory=dict)
    max_iterations: int = 20
    max_cost_usd: float | None = None
    on_exceed: str = "escalate"  # "escalate" | "pause" | "fail" | "continue"


@router.post("/{run_id}/loops")
async def create_loop(
    run_id: str, req: CreateLoopRequest, request: Request
) -> dict[str, Any]:
    """Attach a new loop to a running run's graph.

    The loop is queued in the audit log; the engine will materialize it
    as a `LoopHandler` node on the next graph step.
    """
    state: Any = request.app.state.maestro
    if run_id not in state.live_buses:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not live")

    await state.checkpoints.audit(
        run_id,
        "loop.created",
        {
            "loop_id": req.loop_id,
            "body_agent_id": req.body_agent_id,
            "exit_kind": req.exit_kind,
            "exit_config": req.exit_config,
            "max_iterations": req.max_iterations,
            "max_cost_usd": req.max_cost_usd,
            "on_exceed": req.on_exceed,
            "source": "ui",
        },
    )

    bus = state.get_or_create_bus(run_id)
    await bus.emit(
        EventType.LOOP_ITERATION,
        run_id=run_id,
        loop_id=req.loop_id,
        iteration=0,
        kind="created",
        body_agent_id=req.body_agent_id,
        exit_kind=req.exit_kind,
        source="ui",
    )

    return {"loop_id": req.loop_id, "status": "queued"}


@router.get("/{run_id}/live")
async def get_live_state(run_id: str, request: Request) -> dict[str, Any]:
    """Get a snapshot of a live run: agents, loops, recent events, cost."""
    state: Any = request.app.state.maestro
    if run_id not in state.live_buses:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not live")

    # Cost.
    cost_total = 0.0
    cost_breakdown: list[dict[str, Any]] = []
    if state.ledger:
        cost_total = await state.ledger.total_for_run(run_id)
        cost_breakdown = await state.ledger.breakdown_for_run(run_id)

    # Agent tree from graph memory.
    agents: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    if state.memory and state.memory.graph:
        import networkx as nx
        g = state.memory.graph._graph
        for node_id, data in g.nodes(data=True):
            if data.get("kind") == "agent":
                agents.append({"id": node_id, **data})
        for u, v, data in g.edges(data=True):
            if data.get("kind") == "spawned":
                edges.append({"parent": u, "child": v, **data})

    # Latest checkpoint state.
    latest = await state.checkpoints.latest(run_id)

    return {
        "run_id": run_id,
        "status": latest.status if latest else "unknown",
        "iteration": latest.iteration if latest else 0,
        "current_node": latest.current_node if latest else None,
        "cost_usd": cost_total,
        "cost_breakdown": cost_breakdown,
        "agents": agents,
        "agent_edges": edges,
        "error": latest.error if latest else None,
    }

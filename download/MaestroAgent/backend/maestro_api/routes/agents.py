"""Agent routes — inspect agents, agent specs, and the agent hierarchy."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


@router.get("")
async def list_agents(request: Request) -> list[dict[str, Any]]:
    """List all known agent specs (from registered templates/plugins)."""
    state: Any = request.app.state.maestro
    agents = []
    if state.plugins:
        for entry in state.plugins.list_detailed():
            if entry["kind"] == "agent":
                agents.append(entry)
    return agents


@router.get("/{run_id}/tree")
async def get_agent_tree(run_id: str, request: Request) -> dict[str, Any]:
    """Get the live agent hierarchy for a run (from the graph memory)."""
    state: Any = request.app.state.maestro
    if state.memory is None or state.memory.graph is None:
        raise HTTPException(status_code=503, detail="graph memory not initialized")

    # Find all agent nodes for this run.
    # For v0.1 we walk the graph and return all agents with run_id matching.
    import networkx as nx
    g = state.memory.graph._graph  # access the underlying NetworkX graph
    nodes = []
    edges = []
    for node_id, data in g.nodes(data=True):
        if data.get("kind") == "agent":
            nodes.append({"id": node_id, **data})
    for u, v, data in g.edges(data=True):
        if data.get("kind") == "spawned":
            edges.append({"parent": u, "child": v, **data})
    return {"run_id": run_id, "agents": nodes, "edges": edges}

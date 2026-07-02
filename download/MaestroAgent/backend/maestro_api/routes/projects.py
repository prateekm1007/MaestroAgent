"""Project routes — export/import full runs + graphs as JSON.

A "project" is a complete portable bundle: graph definition + run
config + final state + cost breakdown + audit log. Users can export
a project, share it, and import it on another MaestroAgent instance.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from maestro_auth.permissions import is_auth_enabled, require_user
from maestro_api.security.policy import set_router_policy, AuthPolicy


def _require_user_if_auth_enabled(request: Request) -> None:
    if is_auth_enabled():
        require_user(request)


router = APIRouter(dependencies=[Depends(_require_user_if_auth_enabled)])


@router.get("/{run_id}/export")
async def export_project(run_id: str, request: Request) -> dict[str, Any]:
    """Export a full run as a portable JSON project.

    Includes:
    - Run config (template, goal, budgets)
    - Final state
    - Step history (checkpoint trace)
    - Cost breakdown
    - Audit log
    - Agent tree (from graph memory)

    The exported JSON can be re-imported on another instance or
    archived for compliance.
    """
    state: Any = request.app.state.maestro

    # Run summary + final state.
    latest = await state.checkpoints.latest(run_id)
    if latest is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    # Step history.
    history = await state.checkpoints.history(run_id)

    # Cost breakdown.
    cost = None
    if state.ledger:
        cost = {
            "total_usd": await state.ledger.total_for_run(run_id),
            "breakdown": await state.ledger.breakdown_for_run(run_id),
        }

    # Audit log.
    audit = await state.checkpoints.audit_log(run_id)

    # Agent tree.
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

    return {
        "version": "1.0",
        "exported_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "run": {
            "run_id": run_id,
            "status": latest.status,
            "iteration": latest.iteration,
            "current_node": latest.current_node,
            "error": latest.error,
            "metadata": latest.metadata,
            "artifacts": latest.artifacts,
        },
        "history": [
            {
                "step_id": s.step_id,
                "parent_step_id": s.parent_step_id,
                "node_id": s.node_id,
                "status": s.status,
                "revision": s.revision,
                "iteration": s.iteration,
                "ts": s.ts,
            }
            for s in history
        ],
        "cost": cost,
        "audit": audit,
        "agents": agents,
        "agent_edges": edges,
    }


class ImportProjectRequest(BaseModel):
    """Import a previously-exported project (for archival/inspection).

    v1.0 only imports for read-only inspection (the run is not re-executed).
    v1.1 will support "fork from step N" to re-run from a checkpoint.
    """
    project: dict[str, Any]


@router.post("/import")
async def import_project(req: ImportProjectRequest, request: Request) -> dict[str, Any]:
    """Import a project JSON (read-only inspection in v1.0)."""
    project = req.project
    version = project.get("version", "unknown")
    run = project.get("run", {})
    return {
        "imported": True,
        "version": version,
        "run_id": run.get("run_id"),
        "status": run.get("status"),
        "note": "Project imported for inspection. Re-execution is v1.1.",
    }


@router.get("/{run_id}/graph")
async def export_graph(run_id: str, request: Request) -> dict[str, Any]:
    """Export just the graph structure for a run (for the GraphBuilder).

    Returns the agent tree + edges in a format the GraphBuilder can
    import directly.
    """
    state: Any = request.app.state.maestro
    agents: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    if state.memory and state.memory.graph:
        import networkx as nx
        g = state.memory.graph._graph
        for node_id, data in g.nodes(data=True):
            if data.get("kind") == "agent":
                agents.append({"id": node_id, "label": data.get("role", node_id), **data})
        for u, v, data in g.edges(data=True):
            edges.append({"source": u, "target": v, **data})
    return {
        "run_id": run_id,
        "nodes": agents,
        "edges": edges,
    }

# Phase 1: stamp USER auth policy on all routes in this router
set_router_policy(router, AuthPolicy.USER)

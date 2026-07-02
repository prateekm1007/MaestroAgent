"""Run routes — start, list, get, resume, cancel."""

from __future__ import annotations

import asyncio
import importlib.util
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from maestro_core.context import RunConfig, RunContext
from maestro_core.engine import OrchestrationEngine
from maestro_core.state import RunStatus, State
from maestro_core.streaming import EventBus, EventType

from maestro_auth.permissions import is_auth_enabled, require_user
from maestro_api.security.policy import set_router_policy, AuthPolicy
def _require_user_if_auth_enabled(request: Request) -> None:
    """Auth gate that respects dev mode. See imports.py for the pattern."""
    if is_auth_enabled():
        require_user(request)


router = APIRouter(dependencies=[Depends(_require_user_if_auth_enabled)])


class StartRunRequest(BaseModel):
    template: str = "blank"
    goal: str
    max_cost_usd: float = 10.0
    max_iterations: int = 100
    max_wall_clock_seconds: int = 3600
    default_provider: str | None = None
    default_model: str | None = None
    agent_role: str = "default"
    env: dict[str, str] = Field(default_factory=dict)
    extras: dict[str, Any] = Field(default_factory=dict)


class StartRunResponse(BaseModel):
    run_id: str
    status: RunStatus


@router.post("", response_model=StartRunResponse)
async def start_run(req: StartRunRequest, request: Request) -> StartRunResponse:
    """Start a new run. Returns immediately; events stream over WebSocket."""
    state: Any = request.app.state.maestro
    run_id = str(uuid.uuid4())

    config = RunConfig(
        run_id=run_id,
        template=req.template,
        goal=req.goal,
        max_cost_usd=req.max_cost_usd,
        max_iterations=req.max_iterations,
        max_wall_clock_seconds=req.max_wall_clock_seconds,
        default_provider=req.default_provider,
        default_model=req.default_model,
        agent_role=req.agent_role,
        env=req.env,
        extras=req.extras,
    )

    # Build a RunContext with shared services + a per-run event bus.
    bus = state.get_or_create_bus(run_id)
    ctx = RunContext(
        config=config,
        llm=state.llm,
        memory=state.memory,
        checkpoints=state.checkpoints,
        events=bus,
        verifiers=state.verifiers,
        plugins=state.plugins,
    )

    # Resolve template -> graph.
    graph = await _resolve_template(req.template, req.extras)

    # Launch the engine in a background task.
    engine = OrchestrationEngine(ctx=ctx, graph=graph)
    task = asyncio.create_task(_run_engine(state, run_id, engine))
    state.run_tasks[run_id] = task

    return StartRunResponse(run_id=run_id, status=RunStatus.RUNNING)


@router.get("")
async def list_runs(request: Request) -> list[dict[str, Any]]:
    """List all runs (metadata only)."""
    state: Any = request.app.state.maestro
    # We don't have a separate runs table; we infer from checkpoints.
    # In v0.2, add a dedicated runs table.
    # For v0.1, return the live run ids.
    return [{"run_id": rid, "live": True} for rid in state.live_buses.keys()]


@router.get("/{run_id}")
async def get_run(run_id: str, request: Request) -> dict[str, Any]:
    """Get a run's status and latest state."""
    state: Any = request.app.state.maestro
    latest = await state.checkpoints.latest(run_id)
    if latest is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    cost = await state.ledger.total_for_run(run_id) if state.ledger else 0.0
    return {
        "run_id": run_id,
        "status": latest.status,
        "iteration": latest.iteration,
        "cost_usd": cost,
        "current_node": latest.current_node,
        "error": latest.error,
        "metadata": latest.metadata,
    }


@router.get("/{run_id}/history")
async def get_history(run_id: str, request: Request) -> list[dict[str, Any]]:
    """Get a run's step history (for the trace tree)."""
    state: Any = request.app.state.maestro
    history = await state.checkpoints.history(run_id)
    return [
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
    ]


@router.get("/{run_id}/audit")
async def get_audit(run_id: str, request: Request) -> list[dict[str, Any]]:
    """Get a run's tamper-evident audit log."""
    state: Any = request.app.state.maestro
    log = await state.checkpoints.audit_log(run_id)
    return log


@router.post("/{run_id}/resume")
async def resume_run(run_id: str, request: Request, human_input: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resume a paused run, optionally with human input."""
    state: Any = request.app.state.maestro
    # Look up the original config from the latest checkpoint's metadata.
    latest = await state.checkpoints.latest(run_id)
    if latest is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    config = RunConfig(
        run_id=run_id,
        template=latest.metadata.get("template", "blank"),
        goal=latest.metadata.get("goal", ""),
    )
    bus = state.get_or_create_bus(run_id)
    ctx = RunContext(
        config=config,
        llm=state.llm,
        memory=state.memory,
        checkpoints=state.checkpoints,
        events=bus,
        verifiers=state.verifiers,
        plugins=state.plugins,
    )
    # Resume requires the original graph — we need to re-resolve the template.
    graph = await _resolve_template(config.template, {})
    engine = OrchestrationEngine(ctx=ctx, graph=graph)
    task = asyncio.create_task(_resume_engine(state, run_id, engine, human_input))
    state.run_tasks[run_id] = task
    return {"run_id": run_id, "status": "resuming"}


@router.post("/{run_id}/cancel")
async def cancel_run(run_id: str, request: Request) -> dict[str, Any]:
    """Cancel a running task."""
    state: Any = request.app.state.maestro
    task = state.run_tasks.get(run_id)
    if task is not None:
        task.cancel()
    return {"run_id": run_id, "status": "cancelled"}


async def _run_engine(state: Any, run_id: str, engine: OrchestrationEngine) -> None:
    """Background task: run the engine to completion."""
    try:
        await engine.run()
    except Exception as exc:
        state.checkpoints and await state.checkpoints.audit(
            run_id, "run.fatal", {"error": str(exc)}
        )
    finally:
        state.remove_bus(run_id)
        state.run_tasks.pop(run_id, None)


async def _resume_engine(
    state: Any, run_id: str, engine: OrchestrationEngine, human_input: dict[str, Any] | None
) -> None:
    try:
        await engine.resume(human_input=human_input)
    except Exception as exc:
        state.checkpoints and await state.checkpoints.audit(
            run_id, "run.fatal", {"error": str(exc)}
        )
    finally:
        state.remove_bus(run_id)
        state.run_tasks.pop(run_id, None)


async def _resolve_template(template: str, extras: dict[str, Any]):
    """Resolve a template name to a Graph instance.

    Templates live in `backend/examples/templates/` and expose a
    `build_graph(goal: str, **extras) -> Graph` function.
    """
    # Special-case: blank template (single no-op node).
    if template == "blank":
        from maestro_core.graph import Graph, Node

        async def _noop(state: State, ctx: RunContext) -> State:
            return state

        g = Graph()
        g.add_node(Node(id="noop", fn=_noop))
        return g

    # Try to load from examples/templates/<template>.py.
    template_path = Path(__file__).parent.parent.parent / "examples" / "templates" / f"{template}.py"
    if not template_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Template '{template}' not found at {template_path}",
        )

    spec = importlib.util.spec_from_file_location(f"maestro_template_{template}", template_path)
    if spec is None or spec.loader is None:
        raise HTTPException(status_code=500, detail=f"Cannot load template {template}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "build_graph"):
        raise HTTPException(
            status_code=500,
            detail=f"Template {template} has no build_graph() function",
        )
    return module.build_graph(goal=extras.get("goal", ""), **extras)

# Phase 1: stamp USER auth policy on all routes in this router
set_router_policy(router, AuthPolicy.USER)

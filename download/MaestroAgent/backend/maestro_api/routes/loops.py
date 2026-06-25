"""Loop routes — inspect loop progress and outcomes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


@router.get("/{run_id}/loops")
async def get_run_loops(run_id: str, request: Request) -> list[dict[str, Any]]:
    """Get all loop events for a run (from the audit log)."""
    state: Any = request.app.state.maestro
    log = await state.checkpoints.audit_log(run_id)
    # Filter for loop-related audit entries; for v0.1 we return all events
    # tagged with kind containing "loop".
    return [e for e in log if "loop" in e.get("kind", "").lower() or "loop" in str(e.get("payload", {})).lower()]


@router.get("/{run_id}/loops/{loop_id}")
async def get_loop_detail(run_id: str, loop_id: str, request: Request) -> dict[str, Any]:
    """Get detailed info about a specific loop in a run."""
    state: Any = request.app.state.maestro
    log = await state.checkpoints.audit_log(run_id)
    loop_events = [
        e for e in log
        if e.get("payload", {}).get("loop_id") == loop_id
    ]
    if not loop_events:
        raise HTTPException(status_code=404, detail=f"Loop {loop_id} not found in run {run_id}")
    return {
        "run_id": run_id,
        "loop_id": loop_id,
        "events": loop_events,
        "iterations": max(
            (e.get("payload", {}).get("iteration", 0) for e in loop_events),
            default=0,
        ),
    }

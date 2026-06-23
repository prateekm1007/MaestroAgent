"""Cost routes — per-run spend and breakdowns."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


@router.get("/{run_id}")
async def get_run_cost(run_id: str, request: Request) -> dict[str, Any]:
    state: Any = request.app.state.maestro
    if state.ledger is None:
        raise HTTPException(status_code=503, detail="cost ledger not initialized")
    total = await state.ledger.total_for_run(run_id)
    breakdown = await state.ledger.breakdown_for_run(run_id)
    return {"run_id": run_id, "total_usd": total, "breakdown": breakdown}


@router.get("")
async def list_all_costs(request: Request) -> list[dict[str, Any]]:
    """Aggregate cost across all runs (for the analytics dashboard)."""
    state: Any = request.app.state.maestro
    if state.ledger is None:
        return []
    import sqlite3
    conn = sqlite3.connect(state.ledger.db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT run_id, SUM(cost_usd) AS total, COUNT(*) AS calls "
            "FROM cost_entries GROUP BY run_id ORDER BY total DESC LIMIT 100"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

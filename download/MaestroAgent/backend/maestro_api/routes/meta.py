"""Meta-agent routes — analyze runs + propose optimizations."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/recommendations")
async def get_recommendations(request: Request, limit: int = 20) -> dict[str, Any]:
    """Run the meta-agent and return optimization recommendations.

    The meta-agent analyzes recent runs (cost data + audit log) and
    proposes concrete changes: adjust LLM hints, tighten loop budgets,
    promote memory entries, etc. Recommendations are sorted by severity.
    """
    state: Any = request.app.state.maestro
    from maestro_meta import MetaAgent
    meta = MetaAgent(
        llm=state.llm,
        checkpoints=state.checkpoints,
        ledger=state.ledger,
        memory=state.memory,
    )
    recs = await meta.analyze_recent_runs(limit=limit)
    return {
        "recommendations": meta.to_dict(recs),
        "count": len(recs),
        "analyzed_runs": limit,
    }

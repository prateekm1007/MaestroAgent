"""Meta-agent routes — analyze runs + propose optimizations."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from maestro_auth.permissions import is_auth_enabled, require_user
from maestro_api.security.policy import set_router_policy, AuthPolicy


def _require_user_if_auth_enabled(request: Request) -> None:
    if is_auth_enabled():
        require_user(request)


router = APIRouter(dependencies=[Depends(_require_user_if_auth_enabled)])


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

# Phase 1: stamp USER auth policy on all routes in this router
set_router_policy(router, AuthPolicy.USER)

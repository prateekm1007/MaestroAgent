"""
Maestro + Nerve Integration: API routes.

Endpoints:
  - POST /api/nerve/briefing/morning  — morning briefing
  - POST /api/nerve/briefing/evening  — evening briefing
  - GET  /api/nerve/dashboard          — unified agent dashboard
  - GET  /api/nerve/agents             — list all 17 agents
  - POST /api/nerve/agent/{name}/insights — get insights from a specific agent
  - GET  /nerve-dashboard              — HTML frontend dashboard (Phase 2, Feature 4)

All /api/ routes require USER auth (Depends(require_user)) and stamp @auth_policy.
The /nerve-dashboard HTML page is PUBLIC (it's a static page; auth happens
client-side via the API key input field).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from maestro_api.security.policy import auth_policy, AuthPolicy, set_router_policy
from maestro_auth.permissions import require_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/nerve", tags=["nerve"])
# F4 lesson: stamp USER auth policy on the router
set_router_policy(router, AuthPolicy.USER)

# Separate router for the HTML dashboard page (PUBLIC — no auth, it's a
# static page; the API key is entered client-side and sent as a Bearer
# token to the /api/nerve/* endpoints which DO require auth).
dashboard_router = APIRouter(tags=["nerve-dashboard"])


class BriefingRequest(BaseModel):
    """Request for morning/evening briefings."""
    user_email: str = ""
    org_id: str = "default"
    request: dict[str, Any] = {}


class DashboardRequest(BaseModel):
    """Request for the unified dashboard."""
    user_email: str = ""
    org_id: str = "default"
    agent_filter: Optional[str] = None
    priority_filter: Optional[str] = None
    min_confidence: float = 0.0


@router.post("/briefing/morning")
@auth_policy(AuthPolicy.USER)
async def morning_briefing(
    req: BriefingRequest,
    user: dict = Depends(require_user),
) -> dict[str, Any]:
    """Generate the morning briefing.

    Returns top insights from all 17 agents, top actions, and a calendar preview.
    """
    try:
        from maestro_nerve.daily_briefing import DailyBriefingEngine
        engine = DailyBriefingEngine()
        # Tenant-scoped: use authenticated user's email if request omits it
        user_email = req.user_email or user.get("email", "")
        org_id = req.org_id or user.get("org_id", "default")
        return engine.generate_morning_briefing(
            user_email=user_email,
            org_id=org_id,
            request=req.request,
        )
    except Exception as e:
        logger.error(f"Morning briefing failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Morning briefing failed: {e}")


@router.post("/briefing/evening")
@auth_policy(AuthPolicy.USER)
async def evening_briefing(
    req: BriefingRequest,
    user: dict = Depends(require_user),
) -> dict[str, Any]:
    """Generate the evening briefing."""
    try:
        from maestro_nerve.daily_briefing import DailyBriefingEngine
        engine = DailyBriefingEngine()
        user_email = req.user_email or user.get("email", "")
        org_id = req.org_id or user.get("org_id", "default")
        return engine.generate_evening_briefing(
            user_email=user_email,
            org_id=org_id,
            request=req.request,
        )
    except Exception as e:
        logger.error(f"Evening briefing failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Evening briefing failed: {e}")


@router.get("/dashboard")
@auth_policy(AuthPolicy.USER)
async def agent_dashboard(
    user: dict = Depends(require_user),
    agent_filter: Optional[str] = Query(None, description="Filter by agent name"),
    priority_filter: Optional[str] = Query(None, description="Filter by priority (high/medium/low)"),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0, description="Minimum confidence"),
) -> dict[str, Any]:
    """Get the unified agent dashboard."""
    try:
        from maestro_nerve.daily_briefing import DailyBriefingEngine
        engine = DailyBriefingEngine()
        user_email = user.get("email", "")
        org_id = user.get("org_id", "default")
        return engine.generate_agent_dashboard(
            user_email=user_email,
            org_id=org_id,
            agent_filter=agent_filter,
            priority_filter=priority_filter,
            min_confidence=min_confidence,
        )
    except Exception as e:
        logger.error(f"Dashboard failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Dashboard failed: {e}")


@router.get("/agents")
@auth_policy(AuthPolicy.USER)
async def list_agents(
    user: dict = Depends(require_user),
) -> list[dict[str, str]]:
    """List all 17 registered agents with their descriptions."""
    try:
        from maestro_nerve.daily_briefing import DailyBriefingEngine
        engine = DailyBriefingEngine()
        return engine.list_available_agents()
    except Exception as e:
        logger.error(f"List agents failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"List agents failed: {e}")


@router.post("/agent/{agent_name}/insights")
@auth_policy(AuthPolicy.USER)
async def get_agent_insights(
    agent_name: str,
    req: BriefingRequest,
    user: dict = Depends(require_user),
) -> dict[str, Any]:
    """Get insights from a specific agent."""
    try:
        from maestro_nerve.base_agent import get_agent, AgentContext
        # Ensure all agents are registered
        from maestro_nerve import agents_revenue, agents_product, agents_internal, agents_strategy  # noqa: F401

        agent = get_agent(agent_name)
        if agent is None:
            raise HTTPException(
                status_code=404,
                detail=f"Agent '{agent_name}' not found. Use GET /api/nerve/agents to list available agents."
            )

        user_email = req.user_email or user.get("email", "")
        org_id = req.org_id or user.get("org_id", "default")
        ctx = AgentContext(
            user_email=user_email,
            org_id=org_id,
            request=req.request,
        )
        insights = agent.generate_insights(ctx)
        return {
            "agent": agent_name,
            "insight_count": len(insights),
            "insights": [i.to_dict() for i in insights],
            "user_email": user_email,
            "org_id": org_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Agent insights failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Agent insights failed: {e}")


# ════════════════════════════════════════════════════════════════════════════
# HTML Dashboard (Phase 2, Feature 4) — PUBLIC route
# ════════════════════════════════════════════════════════════════════════════

@dashboard_router.get("/nerve-dashboard", response_class=HTMLResponse)
async def nerve_dashboard_page() -> HTMLResponse:
    """Serve the Nerve frontend dashboard (HTML + inline CSS/JS).

    This is a PUBLIC route (no auth) — it serves a static HTML page. The
    actual data endpoints (/api/nerve/*) require auth. The user enters
    their API key in the dashboard's input field, and all fetch requests
    include it as a Bearer token.

    The HTML file is at static/nerve-dashboard.html.
    """
    # Resolve the HTML file path relative to the repo root
    html_path = Path(__file__).resolve().parents[3] / "static" / "nerve-dashboard.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="nerve-dashboard.html not found")
    html = html_path.read_text(encoding="utf-8")
    return HTMLResponse(content=html)

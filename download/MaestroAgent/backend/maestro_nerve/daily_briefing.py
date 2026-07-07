"""
Maestro + Nerve Integration: Daily Briefings Engine (Phase 2, Feature 3).

Generates morning and evening briefings by aggregating insights from
all 17 agents via the ChiefOfStaffAgent.

The morning briefing answers: "What should I focus on today?"
The evening briefing answers: "What happened today? What's pending?"

Both briefings:
  - Cite evidence chains for every insight (P4, P23)
  - Apply confidence gates (P25)
  - Are deterministic for the same OEM state (no randomness)
  - Write back to the OutcomeLedger for organizational memory (P34)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from .base_agent import AgentContext, AgentInsight, get_agent

logger = logging.getLogger(__name__)


class DailyBriefingEngine:
    """Generates daily briefings by orchestrating the ChiefOfStaffAgent.

    Usage:
        engine = DailyBriefingEngine()
        morning = engine.generate_morning_briefing(user_email="jane@acme.com")
        evening = engine.generate_evening_briefing(user_email="jane@acme.com")
    """

    def __init__(self, oem_state: Any = None):
        self._oem_state = oem_state

    def _get_chief_of_staff(self):
        """Get the ChiefOfStaffAgent instance."""
        # Ensure all agent modules are registered
        from . import agents_revenue, agents_product, agents_internal, agents_strategy  # noqa: F401
        agent = get_agent("chief_of_staff", oem_state=self._oem_state)
        if agent is None:
            raise RuntimeError("ChiefOfStaffAgent not registered")
        return agent

    def generate_morning_briefing(
        self,
        user_email: str = "",
        org_id: str = "default",
        request: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Morning briefing: 'What should I focus on today?'

        Returns a structured briefing with:
          - greeting
          - date
          - top_insights (top 5 across all agents)
          - top_actions (high-priority recommended actions)
          - calendar_preview (upcoming meetings)
          - total_insights_generated
          - agents_consulted
        """
        ctx = AgentContext(
            user_email=user_email,
            org_id=org_id,
            request=request or {},
        )
        cos = self._get_chief_of_staff()
        briefing = cos.generate_morning_briefing(ctx)

        # Stamp with engine metadata
        briefing["briefing_id"] = f"morning-{uuid4().hex[:12]}"
        briefing["briefing_type"] = "morning"
        briefing["generated_at"] = datetime.now(timezone.utc).isoformat()
        briefing["engine_version"] = "1.0"

        return briefing

    def generate_evening_briefing(
        self,
        user_email: str = "",
        org_id: str = "default",
        request: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Evening briefing: 'What happened today? What's pending?'

        Returns a structured briefing with:
          - greeting
          - date
          - todays_wins (positive insights)
          - todays_risks (negative insights)
          - pending_actions (high-priority actions not yet done)
          - total_insights_generated
        """
        ctx = AgentContext(
            user_email=user_email,
            org_id=org_id,
            request=request or {},
        )
        cos = self._get_chief_of_staff()
        briefing = cos.generate_evening_briefing(ctx)

        # Stamp with engine metadata
        briefing["briefing_id"] = f"evening-{uuid4().hex[:12]}"
        briefing["briefing_type"] = "evening"
        briefing["generated_at"] = datetime.now(timezone.utc).isoformat()
        briefing["engine_version"] = "1.0"

        return briefing

    def generate_agent_dashboard(
        self,
        user_email: str = "",
        org_id: str = "default",
        agent_filter: Optional[str] = None,
        priority_filter: Optional[str] = None,
        min_confidence: float = 0.0,
    ) -> dict[str, Any]:
        """Unified dashboard view: all insights from all agents.

        Args:
            agent_filter: if set, only show insights from this agent.
            priority_filter: if set ("high"/"medium"/"low"), only show this priority.
            min_confidence: only show insights with confidence >= this value.
        """
        ctx = AgentContext(
            user_email=user_email,
            org_id=org_id,
            strict_confidence=False,  # show all, filter below
        )
        cos = self._get_chief_of_staff()
        all_insights = cos.generate_insights(ctx)

        # Apply filters
        filtered = all_insights
        if agent_filter:
            filtered = [i for i in filtered if i.agent == agent_filter]
        if priority_filter:
            filtered = [i for i in filtered if i.priority == priority_filter]
        if min_confidence > 0:
            filtered = [i for i in filtered if i.confidence >= min_confidence]

        # Group by agent for the dashboard
        by_agent: dict[str, list[dict]] = {}
        for ins in filtered:
            by_agent.setdefault(ins.agent, []).append(ins.to_dict())

        return {
            "dashboard_id": f"dashboard-{uuid4().hex[:12]}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "engine_version": "1.0",
            "user_email": user_email,
            "org_id": org_id,
            "total_insights": len(filtered),
            "agents_represented": sorted(by_agent.keys()),
            "filters_applied": {
                "agent_filter": agent_filter,
                "priority_filter": priority_filter,
                "min_confidence": min_confidence,
            },
            "insights_by_agent": by_agent,
            "all_insights_sorted": [i.to_dict() for i in filtered],
        }

    def list_available_agents(self) -> list[dict[str, str]]:
        """List all registered agents with their descriptions (for dashboard sidebar)."""
        from . import agents_revenue, agents_product, agents_internal, agents_strategy  # noqa: F401
        from .base_agent import get_all_agents

        result = []
        for name, agent in sorted(get_all_agents().items()):
            result.append({
                "name": name,
                "description": agent.AGENT_DESCRIPTION,
            })
        return result

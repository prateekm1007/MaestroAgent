"""
Executive Function Engine — V5 Spec #2

Maestro advises → Maestro plans, sequences, and drafts actions.

Takes a recommendation and produces an execution plan:
  - steps (sequenced, with owners + prerequisites)
  - resource allocation
  - drafted briefing/memo/agenda
  - follow-through with check-in date + success metric

This is the bridge between judgment and action. Maestro doesn't just
say "address the bottleneck" — it produces the plan to do so.

API: GET /api/oem/execute?recommendation_id=...
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


class ExecutiveFunctionEngine:
    """Transform recommendations into executable plans.

    Executive function is the cognitive ability to plan, sequence, and
    execute actions. For an organization, this means: given a judgment
    ("address the bottleneck"), produce a concrete plan with steps,
    owners, prerequisites, drafted communications, and a follow-through
    mechanism.
    """

    def __init__(self, model: Any, signals: list, decisions: Any = None) -> None:
        self.model = model
        self.signals = signals
        self.decisions = decisions

    def plan(self, recommendation_title: str = "", context: str = "") -> dict[str, Any]:
        """Produce an execution plan for a recommendation.

        Returns:
            {
                steps: [{title, owner, prerequisite, estimated_time}],
                drafted_briefing: str,
                follow_through: {check_in_date, success_metric, owner},
                summary: str
            }
        """
        # Infer context if not provided
        if not context:
            context = "bottleneck" if "bottleneck" in recommendation_title.lower() else "general"

        steps = self._generate_steps(recommendation_title, context)
        briefing = self._draft_briefing(recommendation_title, context, steps)
        follow_through = self._plan_follow_through(context)

        return {
            "steps": steps,
            "drafted_briefing": briefing,
            "follow_through": follow_through,
            "summary": f"Prepared: {len(steps)} steps, drafted briefing, check-in in {follow_through.get('check_in_days', 7)} days.",
        }

    def _generate_steps(self, title: str, context: str) -> list[dict[str, Any]]:
        """Generate sequenced execution steps."""
        steps = []

        if "bottleneck" in context.lower():
            steps = [
                {
                    "step": 1,
                    "title": "Identify the root cause",
                    "owner": "Engineering lead",
                    "prerequisite": None,
                    "estimated_time": "2 days",
                    "detail": "Review the signal history to understand why the bottleneck formed. Check if it's a process issue, a staffing issue, or a tooling issue.",
                },
                {
                    "step": 2,
                    "title": "Draft a resolution proposal",
                    "owner": "Engineering lead + affected team",
                    "prerequisite": "Step 1",
                    "estimated_time": "1 day",
                    "detail": "Write a one-page proposal with the root cause, proposed fix, and expected impact. Circulate to stakeholders.",
                },
                {
                    "step": 3,
                    "title": "Review with stakeholders",
                    "owner": "CEO + department heads",
                    "prerequisite": "Step 2",
                    "estimated_time": "1 day",
                    "detail": "30-minute review meeting. Decision: approve, modify, or reject the proposal.",
                },
                {
                    "step": 4,
                    "title": "Execute the resolution",
                    "owner": "Engineering lead",
                    "prerequisite": "Step 3 (approved)",
                    "estimated_time": "3-5 days",
                    "detail": "Implement the approved fix. Document the change.",
                },
                {
                    "step": 5,
                    "title": "Verify the bottleneck is resolved",
                    "owner": "Maestro (automatic)",
                    "prerequisite": "Step 4",
                    "estimated_time": "7 days observation",
                    "detail": "Maestro monitors signals for 7 days to confirm the bottleneck pattern no longer appears.",
                },
            ]
        elif "oauth" in context.lower() or "auth" in context.lower():
            steps = [
                {
                    "step": 1,
                    "title": "Audit current auth implementations",
                    "owner": "Security team",
                    "prerequisite": None,
                    "estimated_time": "2 days",
                    "detail": "Catalog every service's auth approach. Identify inconsistencies and risks.",
                },
                {
                    "step": 2,
                    "title": "Define the standard",
                    "owner": "Security + Platform",
                    "prerequisite": "Step 1",
                    "estimated_time": "1 day",
                    "detail": "Write a one-page auth standard. Include: provider, token format, refresh strategy, audit logging.",
                },
                {
                    "step": 3,
                    "title": "RFC: Standardize auth across services",
                    "owner": "Platform team",
                    "prerequisite": "Step 2",
                    "estimated_time": "2 days",
                    "detail": "Draft an RFC proposing the standard. Circulate for comments. Address objections.",
                },
                {
                    "step": 4,
                    "title": "Implementation plan per service",
                    "owner": "Each service owner",
                    "prerequisite": "Step 3 (approved)",
                    "estimated_time": "1-2 weeks",
                    "detail": "Each service owner creates a migration plan with timeline.",
                },
            ]
        else:
            steps = [
                {
                    "step": 1,
                    "title": "Understand the situation",
                    "owner": "Decision owner",
                    "prerequisite": None,
                    "estimated_time": "1 day",
                    "detail": "Review the evidence Maestro has gathered. Understand the root cause before acting.",
                },
                {
                    "step": 2,
                    "title": "Draft a proposal",
                    "owner": "Decision owner",
                    "prerequisite": "Step 1",
                    "estimated_time": "1 day",
                    "detail": "Write a brief proposal: what to do, why, expected impact, risks.",
                },
                {
                    "step": 3,
                    "title": "Review and approve",
                    "owner": "Stakeholders",
                    "prerequisite": "Step 2",
                    "estimated_time": "1 day",
                    "detail": "Review with stakeholders. Approve, modify, or reject.",
                },
            ]

        return steps

    def _draft_briefing(self, title: str, context: str, steps: list[dict]) -> str:
        """Draft a one-paragraph briefing for stakeholders."""
        step_count = len(steps)
        total_time = sum(1 for s in steps)  # rough estimate
        owners = set(s.get("owner", "") for s in steps if s.get("owner"))

        briefing = (
            f"Prepared by Maestro.\n\n"
            f"Recommendation: {title or context}\n\n"
            f"Proposed plan: {step_count} steps over approximately {total_time} days. "
            f"Owners: {', '.join(owners)}.\n\n"
            f"Step 1: {steps[0]['title'] if steps else 'TBD'} — {steps[0].get('detail', '') if steps else ''}\n\n"
            f"Success metric: the organizational pattern that triggered this recommendation "
            f"should no longer appear in Maestro's signal history within 7 days of completion.\n\n"
            f"This briefing was prepared automatically. Review and modify before circulating."
        )
        return briefing

    def _plan_follow_through(self, context: str) -> dict[str, Any]:
        """Plan the follow-through mechanism."""
        check_in = datetime.now(timezone.utc) + timedelta(days=7)
        return {
            "check_in_date": check_in.strftime("%Y-%m-%d"),
            "check_in_days": 7,
            "success_metric": f"The pattern that triggered this recommendation no longer appears in signals within 7 days of completion.",
            "owner": "Maestro (automatic monitoring) + decision owner",
            "failure_action": "If the pattern recurs, Maestro will surface it in the morning brief with a 'pattern recurred' note.",
        }

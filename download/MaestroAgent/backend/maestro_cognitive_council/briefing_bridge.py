"""
Maestro Cognitive Council — Surface Wiring: Briefing → Situation Judgment.

The existing Nerve DailyBriefingEngine is agent-centric ("Growth Agent
has 4 insights"). This bridge makes Briefing situation-centric:

  "What materially changed?" — not "How many insights did each agent produce?"

The briefing includes:
  - One situation that needs your judgment
  - What changed since last briefing
  - What is currently unknown
  - What is disputed
  - What can be decided
  - What cannot yet be decided
  - What Maestro believes, why, and what would change that belief
  - Situations being watched quietly
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from .situation_engine import (
    LivingSituation,
    SituationEngine,
    SituationState,
    SideState,
    DeliveryRoute,
)
from .delivery_governor import DeliveryGovernor, UserContext

logger = logging.getLogger(__name__)


@dataclass
class SituationCentricBriefing:
    """A Situation-centric briefing — not an agent-centric feed.

    Structure (per CEO directive):
      - Greeting
      - One thing that needs your judgment (the top situation)
      - What changed since last briefing
      - What is currently unknown
      - What is disputed
      - What can be decided
      - What cannot yet be decided
      - What Maestro believes, why, what would change that
      - Situations being watched quietly
      - Ask Maestro (prompt for the next question)
    """
    greeting: str = ""
    date: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    briefing_type: str = "morning"  # "morning" | "evening"
    briefing_id: str = ""

    # The one thing that needs judgment
    top_situation: Optional[dict] = None

    # What changed
    material_changes: list[str] = field(default_factory=list)

    # What's unknown / disputed
    unknowns: list[str] = field(default_factory=list)
    disputes: list[dict] = field(default_factory=list)

    # Decision boundary
    can_decide_now: list[str] = field(default_factory=list)
    cannot_decide_yet: list[str] = field(default_factory=list)
    why_boundary: str = ""
    next_step: str = ""

    # What Maestro believes
    belief: str = ""
    why_belief: str = ""
    what_would_change_belief: str = ""

    # Situations being watched quietly
    watching_quietly: list[dict] = field(default_factory=list)

    # Ask prompt
    ask_prompt: str = "What do you want to understand?"

    def to_dict(self) -> dict:
        return {
            "greeting": self.greeting,
            "date": self.date,
            "briefing_type": self.briefing_type,
            "briefing_id": self.briefing_id,
            "top_situation": self.top_situation,
            "material_changes": self.material_changes,
            "unknowns": self.unknowns,
            "disputes": self.disputes,
            "can_decide_now": self.can_decide_now,
            "cannot_decide_yet": self.cannot_decide_yet,
            "why_boundary": self.why_boundary,
            "next_step": self.next_step,
            "belief": self.belief,
            "why_belief": self.why_belief,
            "what_would_change_belief": self.what_would_change_belief,
            "watching_quietly": self.watching_quietly,
            "ask_prompt": self.ask_prompt,
        }


class SituationBriefingEngine:
    """Generates Situation-centric briefings.

    Replaces the Nerve agent-centric briefing with a Situation-centric one.
    The briefing is NOT "12 insights, 8 actions, 4 risks" — it's "One thing
    needs your judgment. Here's what changed, what's unknown, what can be
    decided."

    Usage:
        engine = SituationBriefingEngine(oem_state=oem_state)
        morning = engine.generate_morning_briefing(user_email="jane@example.com")
    """

    def __init__(self, oem_state: Any = None):
        self._oem_state = oem_state
        self._situation_engine = SituationEngine(oem_state=oem_state)
        self._delivery_governor = DeliveryGovernor()

    def generate_morning_briefing(
        self,
        user_email: str = "",
        org_id: str = "default",
    ) -> SituationCentricBriefing:
        """Generate a morning briefing.

        Structure:
          - Greeting
          - One thing that needs your judgment (top situation by delivery route)
          - What changed (material_changes from the top situation)
          - What's unknown / disputed
          - Decision boundary
          - What Maestro believes
          - Situations being watched quietly
          - Ask prompt
        """
        briefing = SituationCentricBriefing(
            briefing_type="morning",
            briefing_id=f"morning-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            greeting=self._greeting(user_email, is_morning=True),
        )

        # Detect situations
        situations = self._situation_engine.detect_situations(org_id)

        if not situations:
            briefing.top_situation = None
            briefing.material_changes = ["No active situations require your attention."]
            briefing.ask_prompt = "What do you want to understand?"
            return briefing

        # Route situations through the Delivery Governor
        user_context = UserContext(
            is_doing_morning_review=True,
            fatigue_level=0.0,  # fresh
        )
        routes = self._delivery_governor.route_batch(
            situations,
            perspectives_by_situation={},  # no perspectives in briefing mode
            user_context=user_context,
        )

        # Find the top situation (highest-priority delivery route)
        priority_order = {
            DeliveryRoute.URGENT: 5,
            DeliveryRoute.PREPARE: 4,
            DeliveryRoute.WHISPER: 3,
            DeliveryRoute.BRIEFING: 2,
            DeliveryRoute.ASK: 1,
            DeliveryRoute.SILENT: 0,
        }

        # Sort by delivery route priority
        sorted_situations = sorted(
            situations,
            key=lambda s: priority_order.get(routes.get(s.situation_id, DeliveryRoute.SILENT), 0),
            reverse=True,
        )

        # Top situation = the one with the highest delivery priority
        top = sorted_situations[0] if sorted_situations else None
        top_route = routes.get(top.situation_id, DeliveryRoute.SILENT) if top else DeliveryRoute.SILENT

        if top and top_route != DeliveryRoute.SILENT:
            briefing.top_situation = {
                "situation_id": top.situation_id,
                "title": top.title,
                "entity": top.entity,
                "state": top.state.value,
                "delivery_route": top_route.value,
                "unknowns": [u.to_dict() for u in top.unknowns if not u.resolved],
            }

            # What changed
            briefing.material_changes = top.material_changes[-5:] if top.material_changes else [
                "No material changes since last briefing."
            ]

            # Unknowns
            briefing.unknowns = [
                u.question for u in top.unknowns if not u.resolved
            ]

            # Disputes
            briefing.disputes = [d.to_dict() for d in top.disagreements]

            # Decision boundary (from judgment if available)
            if top.judgment and top.judgment.decision_boundary:
                db = top.judgment.decision_boundary
                briefing.can_decide_now = db.can_decide_now
                briefing.cannot_decide_yet = db.cannot_decide_yet
                briefing.why_boundary = db.why
                briefing.next_step = db.smallest_useful_next_step

            # What Maestro believes
            if top.judgment:
                briefing.belief = top.judgment.central_claim
                briefing.why_belief = top.judgment.strongest_reason_to_act
                briefing.what_would_change_belief = (
                    f"Resolve the blocking unknown(s): {'; '.join(briefing.unknowns[:2])}"
                    if briefing.unknowns else "New evidence that contradicts the current assessment."
                )

        # Situations being watched quietly (SILENT route)
        briefing.watching_quietly = [
            {
                "situation_id": s.situation_id,
                "title": s.title,
                "entity": s.entity,
                "state": s.state.value,
            }
            for s in sorted_situations[1:]
            if routes.get(s.situation_id, DeliveryRoute.SILENT) == DeliveryRoute.SILENT
        ][:5]  # max 5 quiet situations

        return briefing

    def generate_evening_briefing(
        self,
        user_email: str = "",
        org_id: str = "default",
    ) -> SituationCentricBriefing:
        """Generate an evening briefing — quieter than morning.

        Structure:
          - What changed today
          - What remains unresolved
          - Tomorrow's preview
        """
        briefing = SituationCentricBriefing(
            briefing_type="evening",
            briefing_id=f"evening-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            greeting=self._greeting(user_email, is_morning=False),
        )

        situations = self._situation_engine.detect_situations(org_id)

        if not situations:
            briefing.material_changes = ["No situations changed today."]
            return briefing

        # Evening briefing: what changed today
        today = datetime.now(timezone.utc) - timedelta(hours=24)
        changed_today = [
            s for s in situations
            if s.updated_at > today
        ]

        if changed_today:
            briefing.material_changes = [
                f"{s.title}: {s.material_changes[-1] if s.material_changes else 'updated'}"
                for s in changed_today[:5]
            ]
        else:
            briefing.material_changes = ["No situations materially changed today."]

        # What remains unresolved
        for s in situations:
            for u in s.unknowns:
                if not u.resolved:
                    briefing.unknowns.append(u.question)

        # Tomorrow's preview
        needs_prep = self._situation_engine.get_situations_needing_preparation(org_id)
        if needs_prep:
            briefing.next_step = (
                f"Tomorrow: {len(needs_prep)} situation(s) need preparation. "
                f"Top: {needs_prep[0].title}"
            )
        else:
            briefing.next_step = "Tomorrow: no situations require preparation."

        return briefing

    def _greeting(self, user_email: str, is_morning: bool) -> str:
        """Generate a personalized greeting."""
        hour = datetime.now(timezone.utc).hour
        name = user_email.split("@")[0].split(".")[0].title() if user_email else "there"

        if is_morning:
            if 5 <= hour < 12:
                return f"Good morning, {name}. Here's what needs your attention today."
            else:
                return f"Good day, {name}. Here's what needs your attention."
        else:
            if 17 <= hour < 22:
                return f"Good evening, {name}. Here's what changed today."
            else:
                return f"Here's your end-of-day summary, {name}."

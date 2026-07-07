"""
Maestro Cognitive Council — Phase 4: Delivery Governor.

The Delivery Governor decides deterministically how (or whether) a
situation should be surfaced to the user. Specialists can only
RECOMMEND delivery; the Governor DECIDES.

Routes:
  silent    — no intervention justified; watch
  ask       — available if user asks, no proactive push
  briefing  — include in morning/evening briefing
  whisper   — proactive push during active context (mid-meeting)
  prepare   — surface a preparation workspace before a known event
  urgent    — immediate escalation (rare, reserved for critical risks)

The Governor is deterministic — not a model guess. It applies a fixed
priority order based on the situation's state, epistemic state,
unknowns, and the user's current context.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from .situation_engine import (
    LivingSituation,
    SituationState,
    EpistemicState,
    DeliveryRoute,
)
from .perspective import Perspective

logger = logging.getLogger(__name__)


@dataclass
class UserContext:
    """The user's current context — influences delivery routing.

    The Governor uses this to decide whether a whisper is appropriate
    (user is in a meeting) or whether a briefing is the right surface
    (user is doing their morning review).
    """
    is_in_meeting: bool = False
    is_in_focus_mode: bool = False
    is_doing_morning_review: bool = False
    is_doing_evening_review: bool = False
    last_seen_at: Optional[datetime] = None
    fatigue_level: float = 0.0  # 0.0 (fresh) - 1.0 (overloaded)


class DeliveryGovernor:
    """Deterministically routes situations to delivery surfaces.

    Usage:
        gov = DeliveryGovernor()
        route = gov.decide(situation, perspectives, user_context)
        if route == DeliveryRoute.PREPARE:
            # surface the preparation workspace
        elif route == DeliveryRoute.SILENT:
            # do nothing — watch quietly
    """

    # Priority order — higher = more likely to surface
    # URGENT is reserved for critical risks with strong evidence
    PRIORITY_ORDER = {
        DeliveryRoute.URGENT: 5,
        DeliveryRoute.PREPARE: 4,
        DeliveryRoute.WHISPER: 3,
        DeliveryRoute.BRIEFING: 2,
        DeliveryRoute.ASK: 1,
        DeliveryRoute.SILENT: 0,
    }

    def decide(
        self,
        situation: LivingSituation,
        perspectives: list[Perspective] = None,
        user_context: Optional[UserContext] = None,
    ) -> DeliveryRoute:
        """Decide the delivery route for a situation.

        This is DETERMINISTIC. The same inputs always produce the same
        output. There is no model guessing.

        Decision logic (in priority order):
          1. URGENT: critical urgency + strong evidence + blocking unknown
          2. PREPARE: needs_preparation state + upcoming event
          3. WHISPER: user is in a meeting + situation is relevant to it
          4. BRIEFING: situation changed since last briefing
          5. ASK: information available but no proactive push needed
          6. SILENT: no intervention justified
        """
        perspectives = perspectives or []
        user_context = user_context or UserContext()

        # 1. URGENT: critical urgency + strong evidence
        if self._meets_urgent_threshold(situation, perspectives):
            return DeliveryRoute.URGENT

        # 2. PREPARE: needs preparation + has blocking unknowns
        if situation.state == SituationState.NEEDS_PREPARATION:
            # But suppress if user is overloaded
            if user_context.fatigue_level < 0.8:
                return DeliveryRoute.PREPARE

        # 3. WHISPER: user is in a meeting + situation is relevant
        if user_context.is_in_meeting and self._is_relevant_to_active_context(situation):
            # Don't whisper during focus mode (unless urgent)
            if not user_context.is_in_focus_mode:
                return DeliveryRoute.WHISPER

        # 4. BRIEFING: situation is active or recently updated
        if situation.state in (SituationState.ACTIVE, SituationState.WATCHING):
            if user_context.is_doing_morning_review or user_context.is_doing_evening_review:
                return DeliveryRoute.BRIEFING
            # If not during a briefing context, downgrade to ASK
            return DeliveryRoute.ASK

        # 5. ASK: information available but no proactive push
        if situation.known_facts and situation.state != SituationState.DORMANT:
            return DeliveryRoute.ASK

        # 6. SILENT: default
        return DeliveryRoute.SILENT

    def _meets_urgent_threshold(
        self,
        situation: LivingSituation,
        perspectives: list[Perspective],
    ) -> bool:
        """Urgent requires: critical urgency from a specialist + strong evidence.

        URGENT is rare. It's reserved for situations where:
          - At least one perspective has urgency="critical"
          - That perspective has 2+ evidence items
          - The situation has a blocking unknown OR is in ACTIVE state
        """
        for p in perspectives:
            if p.urgency == "critical" and len(p.evidence) >= 2:
                if situation.has_blocking_unknown() or situation.state == SituationState.ACTIVE:
                    return True
        return False

    def _is_relevant_to_active_context(self, situation: LivingSituation) -> bool:
        """Is this situation relevant to the user's current active context?

        In production, this would check whether the situation's entity
        matches the meeting the user is currently in. For now, we check
        whether the situation is ACTIVE (recent signals).
        """
        return situation.state in (SituationState.ACTIVE, SituationState.NEEDS_PREPARATION)

    # ── Batch routing ───────────────────────────────────────────────────────

    def route_batch(
        self,
        situations: list[LivingSituation],
        perspectives_by_situation: dict[str, list[Perspective]],
        user_context: Optional[UserContext] = None,
    ) -> dict[str, DeliveryRoute]:
        """Route multiple situations at once.

        Returns a dict of situation_id → DeliveryRoute.

        Applies a fatigue-prevention cap: at most 1 URGENT + 2 PREPARE +
        3 WHISPER + 5 BRIEFING per routing cycle. Excess situations are
        downgraded to ASK.
        """
        user_context = user_context or UserContext()

        routes: dict[str, DeliveryRoute] = {}
        counts = {
            DeliveryRoute.URGENT: 0,
            DeliveryRoute.PREPARE: 0,
            DeliveryRoute.WHISPER: 0,
            DeliveryRoute.BRIEFING: 0,
        }

        # Sort situations by update recency (most recent first)
        sorted_situations = sorted(situations, key=lambda s: s.updated_at, reverse=True)

        caps = {
            DeliveryRoute.URGENT: 1,
            DeliveryRoute.PREPARE: 2,
            DeliveryRoute.WHISPER: 3,
            DeliveryRoute.BRIEFING: 5,
        }

        for situation in sorted_situations:
            persps = perspectives_by_situation.get(situation.situation_id, [])
            route = self.decide(situation, persps, user_context)

            # Apply fatigue-prevention cap
            if route in caps and counts[route] >= caps[route]:
                # Downgrade to ASK (still available, just not proactively pushed)
                route = DeliveryRoute.ASK

            routes[situation.situation_id] = route
            if route in counts:
                counts[route] += 1

        return routes

    # ── Explanation (transparency) ──────────────────────────────────────────

    def explain(
        self,
        situation: LivingSituation,
        perspectives: list[Perspective],
        user_context: UserContext,
        route: DeliveryRoute,
    ) -> str:
        """Explain WHY the Governor chose this route (transparency).

        The user should be able to understand why Maestro decided to
        whisper vs. brief vs. stay silent. This builds trust.
        """
        reasons: list[str] = []

        if route == DeliveryRoute.URGENT:
            for p in perspectives:
                if p.urgency == "critical":
                    reasons.append(
                        f"{p.specialist} flagged this as critical with {len(p.evidence)} evidence items."
                    )
                    break

        elif route == DeliveryRoute.PREPARE:
            reasons.append(f"Situation state is {situation.state.value}.")
            if situation.has_blocking_unknown():
                reasons.append(f"{len([u for u in situation.unknowns if u.blocking])} blocking unknown(s) need resolution.")

        elif route == DeliveryRoute.WHISPER:
            reasons.append("You are currently in a meeting and this situation is relevant.")

        elif route == DeliveryRoute.BRIEFING:
            reasons.append("Situation is active and you are doing a review.")

        elif route == DeliveryRoute.ASK:
            reasons.append("Information is available if you ask, but no proactive push is warranted.")

        else:  # SILENT
            reasons.append("No intervention is justified at this time. Maestro is watching quietly.")

        return " ".join(reasons)

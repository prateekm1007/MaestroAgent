"""
Maestro Cognitive Council — Gate 3: Contextual Delivery.

Gate 3 changes:
  1. Opportunity cost model (intervention value vs interruption cost)
  2. Wire CognitiveLoadEngine → UserContext.fatigue_level
  3. Unify InterruptEngine + delivery_decision into the Delivery Governor

The CEO's directive on the opportunity cost model:
  SURFACE NOW if:
    - delay materially reduces options
    - decision is imminent
    - new evidence invalidates preparation
    - user is about to act on stale assumptions
    - situation has crossed a previously stated boundary

  Remain silent if:
    - information is merely interesting
    - user cannot act yet
    - nothing materially changed
    - same issue was recently surfaced
    - evidence is still preliminary
    - another upcoming surface is better

The best Whisper system is not the one that discovers the most.
It is the one whose silence users learn to trust.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from .situation_engine import (
    LivingSituation,
    SituationState,
    SideState,
    EpistemicState,
    DeliveryRoute,
    EvidenceState,
)
from .perspective import Perspective

logger = logging.getLogger(__name__)


@dataclass
class UserContext:
    """The user's current context — influences delivery routing.

    Gate 3: fatigue_level can now be derived from CognitiveLoadEngine
    via DeliveryGovernor.derive_fatigue_from_cognitive_load().
    """
    is_in_meeting: bool = False
    is_in_focus_mode: bool = False
    is_doing_morning_review: bool = False
    is_doing_evening_review: bool = False
    last_seen_at: Optional[datetime] = None
    fatigue_level: float = 0.0  # 0.0 (fresh) - 1.0 (overloaded)
    # Gate 3: what was recently surfaced (for recency suppression)
    recently_surfaced_situation_ids: list[str] = field(default_factory=list)
    # Gate 3: user intent (for InterruptEngine compatibility)
    user_intent: str = ""  # "" | "preparing_for_negotiation" | "resolving_incident"


# ════════════════════════════════════════════════════════════════════════════
# Opportunity Cost Model — intervention value vs interruption cost
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class OpportunityCostAssessment:
    """The result of an opportunity cost assessment.

    The model evaluates:
      - intervention_value: how much value does surfacing this NOW provide?
      - interruption_cost: how much does interrupting the user cost?
      - net_value: intervention_value - interruption_cost
      - should_surface: net_value > 0

    This is NOT a numeric precision game. The model uses categorical
    assessments (high/medium/low/none) to avoid decorative precision.
    """
    intervention_value: str = "none"     # "high" | "medium" | "low" | "none"
    interruption_cost: str = "low"      # "high" | "medium" | "low"
    should_surface: bool = False
    reasons_to_surface: list[str] = field(default_factory=list)
    reasons_to_remain_silent: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "intervention_value": self.intervention_value,
            "interruption_cost": self.interruption_cost,
            "should_surface": self.should_surface,
            "reasons_to_surface": self.reasons_to_surface,
            "reasons_to_remain_silent": self.reasons_to_remain_silent,
        }


class OpportunityCostModel:
    """Evaluates intervention value vs interruption cost.

    SURFACE NOW if:
      - delay materially reduces options
      - decision is imminent
      - new evidence invalidates preparation
      - user is about to act on stale assumptions
      - situation has crossed a previously stated boundary

    Remain silent if:
      - information is merely interesting
      - user cannot act yet
      - nothing materially changed
      - same issue was recently surfaced
      - evidence is still preliminary
      - another upcoming surface is better
    """

    def assess(
        self,
        situation: LivingSituation,
        perspectives: list[Perspective],
        user_context: UserContext,
    ) -> OpportunityCostAssessment:
        """Assess whether to surface this situation now."""
        assessment = OpportunityCostAssessment()

        # ── Compute intervention value ──────────────────────────────────────
        value_reasons: list[str] = []

        # 1. Delay materially reduces options?
        if situation.has_blocking_unknown():
            value_reasons.append("Blocking unknown — delay reduces decision options")
        if situation.state == SituationState.DECISION_PENDING:
            value_reasons.append("Decision is imminent — delay reduces preparation window")

        # 2. New evidence invalidates preparation?
        if situation.material_changes:
            latest_change = situation.material_changes[-1].lower() if situation.material_changes else ""
            if any(kw in latest_change for kw in ["invalidates", "contradicts", "conflicts"]):
                value_reasons.append("New evidence invalidates prior preparation")

        # 3. User is about to act on stale assumptions?
        if user_context.is_in_meeting and situation.state == SituationState.MATERIAL:
            value_reasons.append("User is in a meeting — may be acting on stale assumptions")

        # 4. Situation has crossed a previously stated boundary?
        if situation.has_side_state(SideState.DISPUTED):
            value_reasons.append("Situation has crossed into disputed territory")
        if situation.has_side_state(SideState.BLOCKED):
            value_reasons.append("Situation is blocked — requires intervention")

        # 5. High-stakes perspectives?
        has_critical = any(p.urgency == "critical" for p in perspectives)
        if has_critical:
            value_reasons.append("Critical urgency from at least one specialist")

        if len(value_reasons) >= 3:
            assessment.intervention_value = "high"
        elif len(value_reasons) >= 2:
            assessment.intervention_value = "medium"
        elif len(value_reasons) >= 1:
            assessment.intervention_value = "low"
        else:
            assessment.intervention_value = "none"

        assessment.reasons_to_surface = value_reasons

        # ── Compute interruption cost ───────────────────────────────────────
        cost_reasons: list[str] = []

        # 1. User is in focus mode
        if user_context.is_in_focus_mode:
            cost_reasons.append("User is in focus mode")

        # 2. User fatigue is high
        if user_context.fatigue_level > 0.7:
            cost_reasons.append(f"User fatigue is high ({user_context.fatigue_level:.0%})")

        # 3. Same issue recently surfaced
        if situation.situation_id in user_context.recently_surfaced_situation_ids:
            cost_reasons.append("Same issue was recently surfaced")

        # 4. Evidence is still preliminary
        if situation.judgment and situation.judgment.evidence_state == EvidenceState.PRELIMINARY:
            cost_reasons.append("Evidence is still preliminary")

        # 5. User cannot act yet (no upcoming meeting, not doing review)
        can_act = (
            user_context.is_in_meeting
            or user_context.is_doing_morning_review
            or user_context.is_doing_evening_review
            or situation.state == SituationState.DECISION_PENDING
        )
        if not can_act and assessment.intervention_value != "high":
            cost_reasons.append("User cannot act on this yet")

        # 6. Nothing materially changed
        if not situation.material_changes and situation.state == SituationState.OBSERVING:
            cost_reasons.append("Nothing materially changed since last check")

        if len(cost_reasons) >= 3:
            assessment.interruption_cost = "high"
        elif len(cost_reasons) >= 2:
            assessment.interruption_cost = "medium"
        else:
            assessment.interruption_cost = "low"

        assessment.reasons_to_remain_silent = cost_reasons

        # ── Compute net value ───────────────────────────────────────────────
        value_rank = {"high": 3, "medium": 2, "low": 1, "none": 0}
        cost_rank = {"high": 3, "medium": 2, "low": 1}

        v = value_rank.get(assessment.intervention_value, 0)
        c = cost_rank.get(assessment.interruption_cost, 1)

        assessment.should_surface = v > c

        return assessment


# ════════════════════════════════════════════════════════════════════════════
# Delivery Governor — Gate 3 refactor with opportunity cost model
# ════════════════════════════════════════════════════════════════════════════

class DeliveryGovernor:
    """Deterministically routes situations to delivery surfaces.

    Gate 3 additions:
      1. Opportunity cost model (intervention value vs interruption cost)
      2. derive_fatigue_from_cognitive_load() — wires CognitiveLoadEngine
      3. Unifies InterruptEngine + delivery_decision logic

    Usage:
        gov = DeliveryGovernor()
        route = gov.decide(situation, perspectives, user_context)
        if route == DeliveryRoute.PREPARE:
            # surface the preparation workspace
        elif route == DeliveryRoute.SILENT:
            # do nothing — watch quietly
    """

    PRIORITY_ORDER = {
        DeliveryRoute.URGENT: 5,
        DeliveryRoute.PREPARE: 4,
        DeliveryRoute.WHISPER: 3,
        DeliveryRoute.BRIEFING: 2,
        DeliveryRoute.ASK: 1,
        DeliveryRoute.SILENT: 0,
    }

    def __init__(self, use_opportunity_cost: bool = True):
        """Initialize the governor.

        Args:
            use_opportunity_cost: if True, apply the opportunity cost model
                before deciding the route. This adds the CEO's directive:
                "The best Whisper system is not the one that discovers the
                most. It is the one whose silence users learn to trust."
        """
        self._use_opportunity_cost = use_opportunity_cost
        self._opportunity_model = OpportunityCostModel()

    def decide(
        self,
        situation: LivingSituation,
        perspectives: list[Perspective] = None,
        user_context: Optional[UserContext] = None,
    ) -> DeliveryRoute:
        """Decide the delivery route for a situation.

        Gate 3: now applies the opportunity cost model BEFORE the route
        decision. If the opportunity cost model says "remain silent,"
        the route is SILENT regardless of other factors (except URGENT).
        """
        perspectives = perspectives or []
        user_context = user_context or UserContext()

        # 1. URGENT: critical urgency + strong evidence (always surfaces)
        if self._meets_urgent_threshold(situation, perspectives):
            return DeliveryRoute.URGENT

        # 2. GATE 3: Opportunity cost model
        # Only apply the opportunity cost gate when the situation is in a
        # low-urgency state AND the user is not actively doing a review.
        # During morning/evening review, briefings are always appropriate —
        # the opportunity cost model should not suppress them.
        if self._use_opportunity_cost and situation.state in (
            SituationState.OBSERVING,
            SituationState.AWAITING_OUTCOME,
        ) and not (
            user_context.is_doing_morning_review
            or user_context.is_doing_evening_review
        ):
            assessment = self._opportunity_model.assess(situation, perspectives, user_context)
            # If the model says "don't surface" and value isn't high, suppress
            if not assessment.should_surface and assessment.intervention_value != "high":
                return DeliveryRoute.SILENT

        # 3. PREPARE: needs preparation OR decision is imminent
        if situation.state in (SituationState.NEEDS_PREPARATION, SituationState.DECISION_PENDING):
            if user_context.fatigue_level < 0.8:
                return DeliveryRoute.PREPARE

        # 4. WHISPER: user is in a meeting + situation is relevant
        if user_context.is_in_meeting and self._is_relevant_to_active_context(situation):
            if not user_context.is_in_focus_mode:
                return DeliveryRoute.WHISPER

        # 5. BRIEFING: situation is active or recently updated
        if situation.state in (SituationState.MATERIAL, SituationState.OBSERVING):
            if user_context.is_doing_morning_review or user_context.is_doing_evening_review:
                return DeliveryRoute.BRIEFING
            return DeliveryRoute.ASK

        # 6. ASK: information available but no proactive push
        if situation.known_facts and not situation.has_side_state(SideState.STALE):
            return DeliveryRoute.ASK

        # 7. SILENT: default
        return DeliveryRoute.SILENT

    def _meets_urgent_threshold(
        self,
        situation: LivingSituation,
        perspectives: list[Perspective],
    ) -> bool:
        """Urgent requires: critical urgency from a specialist + strong evidence."""
        for p in perspectives:
            if p.urgency == "critical" and len(p.evidence) >= 2:
                if situation.has_blocking_unknown() or situation.state == SituationState.MATERIAL:
                    return True
        return False

    def _is_relevant_to_active_context(self, situation: LivingSituation) -> bool:
        """Is this situation relevant to the user's current active context?"""
        return situation.state in (SituationState.MATERIAL, SituationState.NEEDS_PREPARATION)

    # ── Gate 3: Wire CognitiveLoadEngine → fatigue_level ────────────────────

    @staticmethod
    def derive_fatigue_from_cognitive_load(cognitive_load_score: float) -> float:
        """Derive a fatigue_level (0.0-1.0) from a CognitiveLoadEngine score.

        CognitiveLoadEngine.compute()["score"] is 0-100:
          <30 = low, <50 = moderate, <70 = high, else critical

        We map this to fatigue_level:
          <30  → 0.0-0.2 (fresh)
          <50  → 0.2-0.4 (light fatigue)
          <70  → 0.4-0.7 (moderate fatigue)
          >=70 → 0.7-1.0 (overloaded)

        Wires maestro_oem.cognitive_load.CognitiveLoadEngine without
        duplicating its 7-factor computation.
        """
        if cognitive_load_score < 30:
            return cognitive_load_score / 30 * 0.2
        elif cognitive_load_score < 50:
            return 0.2 + (cognitive_load_score - 30) / 20 * 0.2
        elif cognitive_load_score < 70:
            return 0.4 + (cognitive_load_score - 50) / 20 * 0.3
        else:
            return min(1.0, 0.7 + (cognitive_load_score - 70) / 30 * 0.3)

    @staticmethod
    def derive_fatigue_from_model(model: Any, signals: list) -> float:
        """Derive fatigue_level directly from the OEM model + signals.

        Convenience method that calls CognitiveLoadEngine internally.
        Wires the existing engine — does NOT reimplement the 7 factors.
        """
        try:
            from maestro_oem.cognitive_load import CognitiveLoadEngine
            engine = CognitiveLoadEngine(model=model, signals=signals)
            result = engine.compute()
            score = result.get("score", 0)
            return DeliveryGovernor.derive_fatigue_from_cognitive_load(score)
        except ImportError:
            logger.debug("CognitiveLoadEngine not available — returning 0 fatigue")
        except Exception as e:
            logger.debug(f"CognitiveLoadEngine failed: {e} — returning 0 fatigue")
        return 0.0

    # ── Gate 3: Unify InterruptEngine priority → DeliveryRoute ──────────────

    @staticmethod
    def interrupt_priority_to_route(priority: str) -> DeliveryRoute:
        """Map an InterruptEngine priority to a DeliveryRoute.

        InterruptEngine uses 5 levels: ignore/notify/recommend/escalate/interrupt
        DeliveryGovernor uses 6 routes: silent/ask/briefing/whisper/prepare/urgent

        This unifies the two systems — the governor can consume InterruptEngine
        output without duplicating its decision logic.
        """
        mapping = {
            "ignore": DeliveryRoute.SILENT,
            "notify": DeliveryRoute.ASK,
            "recommend": DeliveryRoute.BRIEFING,
            "escalate": DeliveryRoute.PREPARE,
            "interrupt": DeliveryRoute.URGENT,
        }
        return mapping.get(priority.lower(), DeliveryRoute.ASK)

    # ── Gate 3: Unify delivery_decision → DeliveryRoute ─────────────────────

    @staticmethod
    def delivery_decision_to_route(decision: str) -> DeliveryRoute:
        """Map a delivery_decision.DeliveryDecision to a DeliveryRoute.

        delivery_decision uses 7 options:
          DELIVER_NOW, DELIVER_AT_MEETING_TIME, DELIVER_ON_ASK,
          SUPPRESS_ALREADY_UNDERSTOOD, SUPPRESS_REDUNDANT,
          SUPPRESS_LOW_STAKES, DEFER_UNTIL_EVIDENCE

        This unifies the two systems.
        """
        mapping = {
            "deliver_now": DeliveryRoute.WHISPER,
            "deliver_at_meeting_time": DeliveryRoute.PREPARE,
            "deliver_on_ask": DeliveryRoute.ASK,
            "suppress_already_understood": DeliveryRoute.SILENT,
            "suppress_redundant": DeliveryRoute.SILENT,
            "suppress_low_stakes": DeliveryRoute.SILENT,
            "defer_until_evidence": DeliveryRoute.SILENT,
        }
        return mapping.get(decision.lower(), DeliveryRoute.ASK)

    # ── Batch routing ───────────────────────────────────────────────────────

    def route_batch(
        self,
        situations: list[LivingSituation],
        perspectives_by_situation: dict[str, list[Perspective]],
        user_context: Optional[UserContext] = None,
    ) -> dict[str, DeliveryRoute]:
        """Route multiple situations at once.

        Applies fatigue-prevention caps: at most 1 URGENT + 2 PREPARE +
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

            if route in caps and counts[route] >= caps[route]:
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
        """Explain WHY the Governor chose this route (transparency)."""
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
                blocking = len([u for u in situation.unknowns if u.blocking and not u.resolved])
                reasons.append(f"{blocking} blocking unknown(s) need resolution.")

        elif route == DeliveryRoute.WHISPER:
            reasons.append("You are currently in a meeting and this situation is relevant.")

        elif route == DeliveryRoute.BRIEFING:
            reasons.append("Situation is active and you are doing a review.")

        elif route == DeliveryRoute.ASK:
            reasons.append("Information is available if you ask, but no proactive push is warranted.")

        elif route == DeliveryRoute.SILENT:
            # Gate 3: explain WHY we're silent (opportunity cost)
            if self._use_opportunity_cost:
                assessment = self._opportunity_model.assess(situation, perspectives, user_context)
                if assessment.reasons_to_remain_silent:
                    reasons.append("Silent because: " + "; ".join(assessment.reasons_to_remain_silent[:2]))
                else:
                    reasons.append("No intervention is justified at this time.")
            else:
                reasons.append("No intervention is justified at this time. Maestro is watching quietly.")

        return " ".join(reasons)

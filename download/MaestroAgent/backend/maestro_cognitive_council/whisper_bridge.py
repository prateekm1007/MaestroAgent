"""
Maestro Cognitive Council — Surface Wiring: Whisper → Delivery Governor.

Connects the production Whisper system to the Cognitive Council's
Delivery Governor (Gate 3) with the opportunity cost model + 4D state.

The existing OrganizationalWhisper uses the old delivery_decision.decide_delivery()
(7 options, binary high/low stakes). This bridge replaces that with the
Delivery Governor's decide() method (6 routes, opportunity cost model,
4-dimensional state, CognitiveLoadEngine-derived fatigue).

Key differences from the old system:
  1. Takes a LivingSituation as primary input (not raw signals)
  2. Uses the Delivery Governor's decide() (not decide_delivery())
  3. Applies the opportunity cost model (intervention value vs interruption cost)
  4. References situation.evidence_refs (not copies)
  5. Uses the 4D state model (not the single-enum state)
  6. Explains WHY it's silent (transparency builds trust)

Usage:
    bridge = WhisperSituationBridge()
    result = bridge.from_situation(situation, context="meeting")
    # result contains: whispers, delivery_route, opportunity_cost_assessment,
    #   suppression_reasons, situation_id, evidence_refs
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from .situation_engine import (
    LivingSituation,
    SituationState,
    DeliveryRoute,
    EpistemicState,
)
from .delivery_governor import DeliveryGovernor, UserContext, OpportunityCostAssessment

logger = logging.getLogger(__name__)


@dataclass
class SituationWhisper:
    """A Whisper generated from a LivingSituation.

    Unlike the old 4-part whisper (which copies evidence), this references
    the Situation's evidence_refs. The user can drill into the Situation
    to see the full evidence chain.
    """
    whisper_id: str = ""
    situation_id: str = ""
    situation_title: str = ""
    entity: str = ""

    # The 4-part card (situation-centric, not signal-centric)
    situation_context: str = ""        # what the user is doing
    insight: str = ""                   # what Maestro noticed
    action: str = ""                    # what Maestro suggests
    why_surfaced: str = ""             # evidence-based explanation

    # Evidence by reference (NOT copies)
    evidence_refs: list[str] = field(default_factory=list)

    # Delivery info
    delivery_route: str = ""           # the DeliveryGovernor's route
    priority: str = "medium"           # high | medium | low

    # Unknowns this whisper surfaces
    unknowns_surfaced: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "whisper_id": self.whisper_id,
            "situation_id": self.situation_id,
            "situation_title": self.situation_title,
            "entity": self.entity,
            "situation_context": self.situation_context,
            "insight": self.insight,
            "action": self.action,
            "why_surfaced": self.why_surfaced,
            "evidence_refs": self.evidence_refs,
            "delivery_route": self.delivery_route,
            "priority": self.priority,
            "unknowns_surfaced": self.unknowns_surfaced,
        }


@dataclass
class WhisperResult:
    """The result of a Situation-aware Whisper generation.

    Includes:
      - The delivery route (from the Delivery Governor)
      - The opportunity cost assessment (intervention value vs interruption cost)
      - The whispers (if delivery route is not SILENT)
      - The suppression reason (if delivery route is SILENT)
      - Evidence references (not copies)
    """
    situation_id: str = ""
    situation_title: str = ""
    entity: str = ""

    # Delivery decision
    delivery_route: str = "silent"     # silent | ask | briefing | whisper | prepare | urgent
    delivery_explanation: str = ""     # WHY this route was chosen

    # Opportunity cost assessment
    opportunity_cost: Optional[dict] = None

    # Whispers (empty if SILENT)
    whispers: list[dict] = field(default_factory=list)

    # Suppression reason (if SILENT)
    suppression_reason: str = ""

    # Evidence references
    evidence_refs: list[str] = field(default_factory=list)

    # Metadata
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "situation_id": self.situation_id,
            "situation_title": self.situation_title,
            "entity": self.entity,
            "delivery_route": self.delivery_route,
            "delivery_explanation": self.delivery_explanation,
            "opportunity_cost": self.opportunity_cost,
            "whispers": self.whispers,
            "suppression_reason": self.suppression_reason,
            "evidence_refs": self.evidence_refs,
            "generated_at": self.generated_at,
        }


class WhisperSituationBridge:
    """Connects the Whisper surface to the Delivery Governor.

    This bridge:
      1. Takes a LivingSituation as primary input
      2. Uses the Delivery Governor's decide() (not the old decide_delivery())
      3. Applies the opportunity cost model
      4. References situation.evidence_refs (not copies)
      5. Uses the 4D state model
      6. Explains WHY it's silent (transparency builds trust)

    The old OrganizationalWhisper.for_context() is left untouched —
    this bridge is a separate class that can be used alongside or
    instead of the legacy system.

    Usage:
        bridge = WhisperSituationBridge()
        result = bridge.from_situation(situation, context="meeting")
        if result.delivery_route == "silent":
            print(f"Silent because: {result.suppression_reason}")
        else:
            for w in result.whispers:
                print(f"[{w['delivery_route']}] {w['insight']}")
    """

    def __init__(self, delivery_governor: Optional[DeliveryGovernor] = None):
        self._governor = delivery_governor or DeliveryGovernor(use_opportunity_cost=True)

    def from_situation(
        self,
        situation: LivingSituation,
        context: str = "",
        user_context: Optional[UserContext] = None,
    ) -> WhisperResult:
        """Generate Situation-aware Whispers.

        Args:
            situation: the LivingSituation to generate whispers for
            context: "meeting" | "proposal" | "decision" | "email" | "review"
            user_context: the user's current context (meeting, focus mode, etc.)

        Returns:
            WhisperResult with delivery route, whispers, and explanation
        """
        if user_context is None:
            user_context = UserContext(
                is_in_meeting=(context == "meeting"),
            )

        result = WhisperResult(
            situation_id=situation.situation_id,
            situation_title=situation.title,
            entity=situation.entity,
            evidence_refs=situation.evidence_refs,
        )

        # 1. Decide the delivery route via the Delivery Governor
        route = self._governor.decide(situation, [], user_context)
        result.delivery_route = route.value

        # 2. Explain WHY this route was chosen (transparency)
        result.delivery_explanation = self._governor.explain(
            situation, [], user_context, route
        )

        # 3. Get the opportunity cost assessment
        if self._governor._use_opportunity_cost:
            assessment = self._governor._opportunity_model.assess(
                situation, [], user_context
            )
            result.opportunity_cost = assessment.to_dict()

        # 4. If SILENT, explain why (transparency builds trust)
        if route == DeliveryRoute.SILENT:
            result.suppression_reason = result.delivery_explanation
            return result

        # 5. If not SILENT, generate whispers from the Situation
        result.whispers = self._generate_whispers(situation, route, context)

        return result

    def _generate_whispers(
        self,
        situation: LivingSituation,
        route: DeliveryRoute,
        context: str,
    ) -> list[dict]:
        """Generate whisper cards from the Situation.

        Unlike the old system (which scans signals), this generates
        whispers directly from the Situation's known facts, unknowns,
        and material changes — referencing evidence_refs, not copies.
        """
        whispers: list[SituationWhisper] = []

        # Whisper 1: Blocking unknowns (if any)
        for unknown in situation.unknowns:
            if unknown.blocking and not unknown.resolved:
                whisper = SituationWhisper(
                    whisper_id=f"wspr-unknown-{uuid4().hex[:8]}",
                    situation_id=situation.situation_id,
                    situation_title=situation.title,
                    entity=situation.entity,
                    situation_context=f"You're in a {context} context regarding {situation.entity}",
                    insight=f"Unresolved: {unknown.question}",
                    action=f"Resolve this before proceeding: {unknown.why_it_matters}",
                    why_surfaced=f"Blocking unknown detected in situation {situation.title}",
                    evidence_refs=situation.evidence_refs,
                    delivery_route=route.value,
                    priority="high",
                    unknowns_surfaced=[unknown.question],
                )
                whispers.append(whisper)
                break  # one blocking unknown whisper is enough

        # Whisper 2: Material changes (if any)
        if situation.material_changes:
            latest_change = situation.material_changes[-1]
            whisper = SituationWhisper(
                whisper_id=f"wspr-change-{uuid4().hex[:8]}",
                situation_id=situation.situation_id,
                situation_title=situation.title,
                entity=situation.entity,
                situation_context=f"You're in a {context} context regarding {situation.entity}",
                insight=f"What changed: {latest_change[:120]}",
                action="Consider whether this changes your approach",
                why_surfaced=f"Material change detected in situation {situation.title}",
                evidence_refs=situation.evidence_refs,
                delivery_route=route.value,
                priority="medium",
            )
            whispers.append(whisper)

        # Whisper 3: Disagreements (if any, and route is not SILENT)
        for disagreement in situation.disagreements[:1]:  # max 1 disagreement whisper
            if disagreement.unresolved:
                whisper = SituationWhisper(
                    whisper_id=f"wspr-disagree-{uuid4().hex[:8]}",
                    situation_id=situation.situation_id,
                    situation_title=situation.title,
                    entity=situation.entity,
                    situation_context=f"You're in a {context} context regarding {situation.entity}",
                    insight=f"Disagreement: {disagreement.topic}",
                    action="Review both positions before deciding",
                    why_surfaced=f"Unresolved disagreement in situation {situation.title}",
                    evidence_refs=situation.evidence_refs,
                    delivery_route=route.value,
                    priority="medium",
                )
                whispers.append(whisper)
                break

        # Whisper 4: Judgment (if available)
        if situation.judgment and situation.judgment.central_claim:
            whisper = SituationWhisper(
                whisper_id=f"wspr-judgment-{uuid4().hex[:8]}",
                situation_id=situation.situation_id,
                situation_title=situation.title,
                entity=situation.entity,
                situation_context=f"You're in a {context} context regarding {situation.entity}",
                insight=situation.judgment.central_claim[:150],
                action=situation.judgment.recommended_next_step[:150] if situation.judgment.recommended_next_step else "Review the situation",
                why_surfaced=f"Synthesized judgment for situation {situation.title}",
                evidence_refs=situation.evidence_refs,
                delivery_route=route.value,
                priority="high" if route == DeliveryRoute.URGENT else "medium",
            )
            whispers.append(whisper)

        return [w.to_dict() for w in whispers]

    def from_situations_batch(
        self,
        situations: list[LivingSituation],
        user_context: Optional[UserContext] = None,
    ) -> list[WhisperResult]:
        """Generate whispers for multiple situations.

        Applies the Delivery Governor's batch routing with fatigue caps:
        max 1 URGENT + 2 PREPARE + 3 WHISPER + 5 BRIEFING per cycle.
        """
        user_context = user_context or UserContext()
        routes = self._governor.route_batch(situations, {}, user_context)

        results: list[WhisperResult] = []
        for situation in situations:
            route = routes.get(situation.situation_id, DeliveryRoute.SILENT)
            # Override the governor's batch decision
            ctx = UserContext(
                is_in_meeting=user_context.is_in_meeting,
                is_in_focus_mode=user_context.is_in_focus_mode,
                is_doing_morning_review=user_context.is_doing_morning_review,
                is_doing_evening_review=user_context.is_doing_evening_review,
                fatigue_level=user_context.fatigue_level,
            )

            result = self.from_situation(situation, user_context=ctx)
            # Override with the batch route (which has fatigue caps applied)
            result.delivery_route = route.value
            if route == DeliveryRoute.SILENT:
                result.whispers = []  # clear whispers if batch route is SILENT
                result.suppression_reason = "Fatigue cap reached — deferred to next cycle"
            results.append(result)

        return results

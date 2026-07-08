"""
Maestro Cognitive Council — Surface Wiring: Prepare → LivingSituation.

The existing PreparationEngine is generic (prepares for calendar events
without Situation awareness). This bridge makes Preparation Situation-aware:

  1. Prepare FOR a specific Situation (not generic)
  2. Update as reality changes (stale preparation detection)
  3. Reference the Situation's unknowns and decision boundary
  4. Connect to the Behavioral Learning Engine (surface learned insights)

Usage:
    bridge = SituationPreparationBridge(oem_state=oem_state)
    prep = bridge.prepare_for_situation(situation_id="sit-globex-abc123")
    # prep contains: situation, unknowns to resolve, decision boundary,
    #   learned insights from similar past situations, stale detection
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
    DeliveryRoute,
)

logger = logging.getLogger(__name__)


@dataclass
class SituationPreparation:
    """Situation-aware preparation for an upcoming event.

    Includes:
      - The situation being prepared for
      - Unknowns that must be resolved before the event
      - Decision boundary (what can/cannot be decided)
      - Learned insights from similar past situations
      - Stale detection (has reality changed since preparation was made?)
      - Questions to ask in the meeting
      - Evidence to review
    """
    situation_id: str = ""
    situation_title: str = ""
    situation_state: str = ""
    entity: str = ""

    # Unknowns to resolve
    unknowns_to_resolve: list[dict] = field(default_factory=list)
    blocking_unknowns: list[str] = field(default_factory=list)

    # Decision boundary
    can_decide_now: list[str] = field(default_factory=list)
    cannot_decide_yet: list[str] = field(default_factory=list)
    why_boundary: str = ""
    smallest_next_step: str = ""

    # Learned insights (from BehavioralLearningEngine)
    learned_insights: list[str] = field(default_factory=list)
    prior_beliefs: list[str] = field(default_factory=list)

    # Stale detection
    is_stale: bool = False
    staleness_reason: str = ""
    last_updated: str = ""

    # Questions to ask
    questions_to_ask: list[str] = field(default_factory=list)

    # Evidence to review
    evidence_refs: list[str] = field(default_factory=list)

    # Generated at
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "situation_id": self.situation_id,
            "situation_title": self.situation_title,
            "situation_state": self.situation_state,
            "entity": self.entity,
            "unknowns_to_resolve": self.unknowns_to_resolve,
            "blocking_unknowns": self.blocking_unknowns,
            "can_decide_now": self.can_decide_now,
            "cannot_decide_yet": self.cannot_decide_yet,
            "why_boundary": self.why_boundary,
            "smallest_next_step": self.smallest_next_step,
            "learned_insights": self.learned_insights,
            "prior_beliefs": self.prior_beliefs,
            "is_stale": self.is_stale,
            "staleness_reason": self.staleness_reason,
            "last_updated": self.last_updated,
            "questions_to_ask": self.questions_to_ask,
            "evidence_refs": self.evidence_refs,
            "generated_at": self.generated_at,
        }


class SituationPreparationBridge:
    """Connects the Prepare surface to the Situation Engine.

    This bridge:
      1. Finds the Situation that needs preparation (NEEDS_PREPARATION state)
      2. Extracts the unknowns that must be resolved
      3. Includes the decision boundary
      4. Surfaces learned insights from the Behavioral Learning Engine
      5. Detects if the preparation is stale (reality changed since prep)
      6. Generates questions to ask in the meeting

    Usage:
        bridge = SituationPreparationBridge(oem_state=oem_state)
        prep = bridge.prepare_for_situation(situation_id)
        if prep.is_stale:
            print("Preparation is stale — reality changed")
    """

    # Staleness threshold: if the situation was updated after the preparation
    # was generated, the preparation is stale
    STALENESS_THRESHOLD_HOURS = 24

    def __init__(self, oem_state: Any = None, learning_engine: Any = None,
                 situation_engine: Any = None):
        self._oem_state = oem_state
        self._situation_engine = situation_engine or SituationEngine(oem_state=oem_state)
        self._learning_engine = learning_engine  # BehavioralLearningEngine

    def prepare_for_situation(
        self,
        situation_id: str,
        org_id: str = "default",
    ) -> SituationPreparation:
        """Generate Situation-aware preparation.

        Args:
            situation_id: the ID of the Situation to prepare for
            org_id: tenant scope

        Returns:
            SituationPreparation with unknowns, decision boundary,
            learned insights, and stale detection.
        """
        prep = SituationPreparation()

        # 1. Find the Situation
        situation = self._situation_engine.get_situation(situation_id)
        if not situation:
            # Try detecting situations first
            self._situation_engine.detect_situations(org_id)
            situation = self._situation_engine.get_situation(situation_id)

        if not situation:
            prep.situation_title = "Situation not found"
            prep.is_stale = True
            prep.staleness_reason = f"Situation {situation_id} not found"
            return prep

        # 2. Populate from Situation
        prep.situation_id = situation.situation_id
        prep.situation_title = situation.title
        prep.situation_state = situation.state.value
        prep.entity = situation.entity
        prep.last_updated = situation.updated_at.isoformat()

        # 3. Unknowns to resolve
        prep.unknowns_to_resolve = [
            u.to_dict() for u in situation.unknowns if not u.resolved
        ]
        prep.blocking_unknowns = [
            u.question for u in situation.unknowns
            if u.blocking and not u.resolved
        ]

        # 4. Decision boundary (from judgment if available)
        if situation.judgment and situation.judgment.decision_boundary:
            db = situation.judgment.decision_boundary
            prep.can_decide_now = db.can_decide_now
            prep.cannot_decide_yet = db.cannot_decide_yet
            prep.why_boundary = db.why
            prep.smallest_next_step = db.smallest_useful_next_step

        # 5. Learned insights from the Behavioral Learning Engine
        if self._learning_engine:
            try:
                # Look for candidates related to this entity
                cid = self._learning_engine._find_candidate_id(situation.entity, None)
                if cid:
                    metrics = self._learning_engine.get_replication_metrics(cid)
                    if metrics and "error" not in metrics:
                        if metrics.get("evidence_strength") is not None:
                            prep.learned_insights.append(
                                f"Pattern evidence strength: {metrics['evidence_strength']:.0%}"
                            )
                        if metrics.get("replication_strength") is not None:
                            prep.learned_insights.append(
                                f"Replication strength: {metrics['replication_strength']:.0%}"
                            )
                        if metrics.get("insufficient_evidence"):
                            prep.learned_insights.append(
                                "Insufficient evidence for pattern — treat as preliminary"
                            )
            except Exception as e:
                logger.debug(f"Could not get learned insights: {e}")

        # 6. Stale detection
        prep.is_stale, prep.staleness_reason = self._check_staleness(situation)

        # 7. Generate questions to ask
        prep.questions_to_ask = self._generate_questions(situation)

        # 8. Evidence references
        prep.evidence_refs = situation.evidence_refs

        return prep

    def prepare_for_upcoming_meetings(
        self,
        org_id: str = "default",
    ) -> list[SituationPreparation]:
        """Generate preparation for all situations needing preparation.

        Finds all situations in NEEDS_PREPARATION or DECISION_PENDING state
        and generates preparation for each.
        """
        situations = self._situation_engine.detect_situations(org_id)
        needing_prep = [
            s for s in situations
            if s.state in (SituationState.NEEDS_PREPARATION, SituationState.DECISION_PENDING)
        ]

        return [
            self.prepare_for_situation(s.situation_id, org_id)
            for s in needing_prep
        ]

    def _check_staleness(self, situation: LivingSituation) -> tuple[bool, str]:
        """Check if preparation is stale.

        Preparation is stale if:
          - The situation was updated after the staleness threshold
          - New material_changes have arrived since preparation
          - The situation's state has transitioned since preparation
        """
        now = datetime.now(timezone.utc)
        threshold = now - timedelta(hours=self.STALENESS_THRESHOLD_HOURS)

        if situation.updated_at > threshold:
            # Check if there are recent material changes
            if situation.material_changes:
                return True, (
                    f"Situation was updated recently ({situation.updated_at.isoformat()}). "
                    f"Latest material change: {situation.material_changes[-1][:80]}"
                )

        # Check if state has changed recently (look at transition history)
        if situation.state_history:
            latest_transition = situation.state_history[-1]
            if latest_transition.timestamp > threshold:
                return True, (
                    f"Situation state changed to {latest_transition.to_state.value} "
                    f"recently ({latest_transition.timestamp.isoformat()}). "
                    f"Reason: {latest_transition.reason}"
                )

        return False, ""

    def _generate_questions(self, situation: LivingSituation) -> list[str]:
        """Generate questions to ask in the meeting.

        Based on the Situation's unknowns, decision boundary, and disputes.
        """
        questions: list[str] = []

        # Questions from unknowns
        for u in situation.unknowns:
            if not u.resolved:
                questions.append(u.question)

        # Questions from disputes
        for d in situation.disagreements:
            if d.unresolved:
                questions.append(
                    f"Resolve the disagreement about: {d.topic}"
                )

        # Questions from decision boundary
        if situation.judgment and situation.judgment.decision_boundary:
            for cannot in situation.judgment.decision_boundary.cannot_decide_yet:
                questions.append(f"What would unblock: {cannot}")

        return questions[:5]  # max 5 questions

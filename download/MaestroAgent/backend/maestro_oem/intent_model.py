"""
Intent — the root entity of the Organizational Cognitive Model.

Every decision, assumption, hypothesis, prediction, preparation, and
evidence chain links to an Intent. The OEM's root query is
"tell me about this intent" — which returns the full cascade:

  Intent
  ├── Assumptions (beliefs about the present)
  ├── Hypotheses (testable claims about proposed interventions)
  │   └── Predictions (linked to hypotheses)
  ├── Preparations (work packets assembled for this intent)
  ├── Evidence (receipts, signals, laws)
  └── Calibration (computed from resolved predictions)

This is NOT the ambient intent inference engine (intent.py). That
infers "user is preparing for a negotiation" from context. This is
the data model: a first-class entity that roots the cognitive model.

Product law: eliminates REMEMBERING ("what were we trying to do?"),
COORDINATING ("who is working on this?"), and THINKING ("is this
assumption still valid for this goal?").
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


class Intent:
    """A strategic or tactical goal the organization is pursuing.

    Every receipt, pattern, law, and prediction can link to an Intent.
    Assumptions and hypotheses are children of Intent, not siblings.
    """

    def __init__(
        self,
        intent_id: str,
        goal: str,
        owner: str = "",
        success_criteria: str = "",
        deadline: str = "",
        stakeholders: list[str] | None = None,
        status: str = "active",  # active | achieved | abandoned | superseded
        intent_type: str = "tactical",  # strategic | tactical | operational
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        assumption_ids: list[str] | None = None,
        hypothesis_ids: list[str] | None = None,
        prediction_ids: list[str] | None = None,
        preparation_ids: list[str] | None = None,
        evidence: list[dict[str, Any]] | None = None,
    ) -> None:
        self.intent_id = intent_id
        self.goal = goal
        self.owner = owner
        self.success_criteria = success_criteria
        self.deadline = deadline
        self.stakeholders = stakeholders or []
        self.status = status
        self.intent_type = intent_type
        self.created_at = created_at or datetime.now(timezone.utc)
        self.updated_at = updated_at or datetime.now(timezone.utc)
        self.assumption_ids = assumption_ids or []
        self.hypothesis_ids = hypothesis_ids or []
        self.prediction_ids = prediction_ids or []
        self.preparation_ids = preparation_ids or []
        self.evidence = evidence or []

    def add_assumption(self, assumption_id: str) -> None:
        if assumption_id not in self.assumption_ids:
            self.assumption_ids.append(assumption_id)
            self.updated_at = datetime.now(timezone.utc)

    def add_hypothesis(self, hypothesis_id: str) -> None:
        if hypothesis_id not in self.hypothesis_ids:
            self.hypothesis_ids.append(hypothesis_id)
            self.updated_at = datetime.now(timezone.utc)

    def add_prediction(self, prediction_id: str) -> None:
        if prediction_id not in self.prediction_ids:
            self.prediction_ids.append(prediction_id)
            self.updated_at = datetime.now(timezone.utc)

    def add_preparation(self, preparation_id: str) -> None:
        if preparation_id not in self.preparation_ids:
            self.preparation_ids.append(preparation_id)
            self.updated_at = datetime.now(timezone.utc)

    def add_evidence(self, evidence: dict[str, Any]) -> None:
        self.evidence.append(evidence)
        self.updated_at = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "goal": self.goal,
            "owner": self.owner,
            "success_criteria": self.success_criteria,
            "deadline": self.deadline,
            "stakeholders": self.stakeholders,
            "status": self.status,
            "intent_type": self.intent_type,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "assumption_ids": self.assumption_ids,
            "hypothesis_ids": self.hypothesis_ids,
            "prediction_ids": self.prediction_ids,
            "preparation_ids": self.preparation_ids,
            "evidence": self.evidence,
        }


class IntentStore:
    """Stores and manages Intent objects.

    The IntentStore is the root of the cognitive model. Every assumption,
    hypothesis, prediction, and preparation links back to an Intent via
    intent_id.

    Usage:
        store = IntentStore()
        intent_id = store.create("Reduce customer onboarding time by 30%")
        store.add_assumption(intent_id, "Legal review takes 3 days")
        store.add_hypothesis(intent_id, "Moving Legal earlier reduces cycle time")
        cascade = store.get_cascade(intent_id)
    """

    def __init__(self) -> None:
        self._intents: dict[str, Intent] = {}

    def create(
        self,
        goal: str,
        owner: str = "",
        success_criteria: str = "",
        deadline: str = "",
        stakeholders: list[str] | None = None,
        intent_type: str = "tactical",
    ) -> str:
        """Create a new Intent. Returns the intent_id."""
        intent_id = f"intent-{uuid4().hex[:12]}"
        intent = Intent(
            intent_id=intent_id,
            goal=goal,
            owner=owner,
            success_criteria=success_criteria,
            deadline=deadline,
            stakeholders=stakeholders or [],
            intent_type=intent_type,
        )
        self._intents[intent_id] = intent
        logger.info("Intent created: %s — '%s'", intent_id, goal[:60])
        return intent_id

    def get(self, intent_id: str) -> Intent | None:
        return self._intents.get(intent_id)

    def list_intents(self, status: str | None = None) -> list[dict[str, Any]]:
        if status:
            return [i.to_dict() for i in self._intents.values() if i.status == status]
        return [i.to_dict() for i in self._intents.values()]

    def update_status(self, intent_id: str, status: str) -> bool:
        intent = self._intents.get(intent_id)
        if not intent:
            return False
        intent.status = status
        intent.updated_at = datetime.now(timezone.utc)
        return True

    def add_assumption(self, intent_id: str, assumption_id: str) -> bool:
        intent = self._intents.get(intent_id)
        if not intent:
            return False
        intent.add_assumption(assumption_id)
        return True

    def add_hypothesis(self, intent_id: str, hypothesis_id: str) -> bool:
        intent = self._intents.get(intent_id)
        if not intent:
            return False
        intent.add_hypothesis(hypothesis_id)
        return True

    def add_prediction(self, intent_id: str, prediction_id: str) -> bool:
        intent = self._intents.get(intent_id)
        if not intent:
            return False
        intent.add_prediction(prediction_id)
        return True

    def add_preparation(self, intent_id: str, preparation_id: str) -> bool:
        intent = self._intents.get(intent_id)
        if not intent:
            return False
        intent.add_preparation(preparation_id)
        return True

    def add_evidence(self, intent_id: str, evidence: dict[str, Any]) -> bool:
        intent = self._intents.get(intent_id)
        if not intent:
            return False
        intent.add_evidence(evidence)
        return True

    def get_cascade(self, intent_id: str, assumption_graph=None, hypothesis_store=None,
                    preparation_engine=None) -> dict[str, Any] | None:
        """Get the full cascade: intent → assumptions → hypotheses → predictions → preparations → evidence.

        This is the OEM's root query: 'tell me about this intent.'
        """
        intent = self._intents.get(intent_id)
        if not intent:
            return None

        cascade = intent.to_dict()

        # Enrich with assumptions
        if assumption_graph and intent.assumption_ids:
            cascade["assumptions"] = [
                assumption_graph.get_assumption(aid)
                for aid in intent.assumption_ids
                if assumption_graph.get_assumption(aid)
            ]
        else:
            cascade["assumptions"] = []

        # Enrich with hypotheses
        if hypothesis_store and intent.hypothesis_ids:
            cascade["hypotheses"] = [
                hypothesis_store.get(hid)
                for hid in intent.hypothesis_ids
                if hypothesis_store.get(hid)
            ]
        else:
            cascade["hypotheses"] = []

        # Enrich with preparations
        if preparation_engine and intent.preparation_ids:
            cascade["preparations"] = [
                preparation_engine.get_preparation(pid)
                for pid in intent.preparation_ids
                if preparation_engine.get_preparation(pid)
            ]
        else:
            cascade["preparations"] = []

        return cascade

    def infer_from_recommendations(self, recommendations: list[Any],
                                    assumption_graph=None, preparation_engine=None) -> list[str]:
        """Infer intents from OEM recommendations.

        Each recommendation implies an intent: "address bottleneck X"
        implies the intent "unblock work gated by X."

        If assumption_graph and preparation_engine are provided, this method
        also auto-links existing assumptions and preparations that were
        created for the same recommendation, so the cascade query returns
        a fully populated tree without manual linking.
        """
        inferred_ids = []
        for rec in recommendations:
            title = getattr(rec, "title", str(rec))
            rec_id = getattr(rec, "rec_id", "")
            confidence = getattr(rec, "confidence", 0.5)

            # Infer the goal from the recommendation
            if "bottleneck" in title.lower():
                goal = f"Unblock work gated by the bottleneck in '{title[:50]}'"
                intent_type = "tactical"
            elif "expert" in title.lower():
                goal = f"Formalize knowledge to reduce bus-factor risk in '{title[:50]}'"
                intent_type = "strategic"
            elif "risk" in title.lower() or "bus-factor" in title.lower():
                goal = f"Mitigate the risk described in '{title[:50]}'"
                intent_type = "strategic"
            elif "customer" in title.lower():
                goal = f"Address the customer situation in '{title[:50]}'"
                intent_type = "tactical"
            else:
                goal = f"Act on recommendation: '{title[:50]}'"
                intent_type = "tactical"

            intent_id = self.create(
                goal=goal,
                owner=getattr(rec, "provenance", [{}])[0].get("gate", "system") if getattr(rec, "provenance", []) else "system",
                success_criteria=f"Confidence {confidence:.0%} — linked to rec {rec_id}",
                intent_type=intent_type,
            )
            inferred_ids.append(intent_id)

            # Auto-link existing assumptions that were created for this recommendation
            if assumption_graph:
                for assumption in assumption_graph.list_assumptions():
                    # Match by recommendation_id in the assumption's context or linked_recommendation_id
                    a_context = assumption.get("context", "")
                    a_rec_id = assumption.get("linked_recommendation_id", "")
                    if rec_id and (rec_id in a_context or rec_id == a_rec_id or title[:30] in a_context):
                        self.add_assumption(intent_id, assumption["assumption_id"])

            # Auto-link existing preparations that were created for this recommendation
            # Preparations use the recommendation title as a stable ID (rec_id changes between calls)
            if preparation_engine:
                for prep in preparation_engine.list_preparations():
                    prep_rec_id = prep.get("recommendation_id", "")
                    # Match by stable_id (title) since rec_id changes between calls
                    if title and (title == prep_rec_id or title[:30] in prep_rec_id):
                        self.add_preparation(intent_id, prep["preparation_id"])

        return inferred_ids

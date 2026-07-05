"""
Hypothesis Layer — testable claims linked to intents and assumptions.

Assumptions are beliefs about the present ("Legal takes 3 days").
Hypotheses are testable claims about proposed interventions
("Moving Legal earlier will reduce cycle time by 5 days").

The distinction matters:
  - An assumption is validated/invalidated by observing reality.
  - A hypothesis is validated/invalidated by running an experiment
    (i.e., making a prediction, taking action, measuring the outcome).

The scientific reasoning loop:
  1. Intent: "Reduce onboarding time by 30%"
  2. Assumption: "Legal review takes 3 days"
  3. Hypothesis: "If we move Legal review earlier, cycle time drops by 5 days"
  4. Prediction: "Cycle time will be 15 days (down from 20)"
  5. Action: Move Legal review earlier
  6. Outcome: Cycle time was 17 days (prediction was partially correct)
  7. Calibration: Hypothesis confidence adjusts

This is the biggest moat nobody is building. No enterprise product
distinguishes assumptions from hypotheses or runs a scientific
reasoning loop on organizational decisions.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


class Hypothesis:
    """A testable claim linked to an intent and its assumptions.

    A hypothesis says: "If we do X (informed by assumption Y),
    we expect outcome Z."
    """

    def __init__(
        self,
        hypothesis_id: str,
        statement: str,
        intent_id: str,
        assumption_ids: list[str] | None = None,
        prediction: str = "",
        predicted_value: float | None = None,
        actual_value: float | None = None,
        outcome: str = "pending",  # pending | validated | invalidated | inconclusive
        confidence: float = 0.5,
        calibrated_confidence: float | None = None,
        created_at: datetime | None = None,
        resolved_at: datetime | None = None,
        evidence: list[dict[str, Any]] | None = None,
        experiment_notes: str = "",
    ) -> None:
        self.hypothesis_id = hypothesis_id
        self.statement = statement
        self.intent_id = intent_id
        self.assumption_ids = assumption_ids or []
        self.prediction = prediction
        self.predicted_value = predicted_value
        self.actual_value = actual_value
        self.outcome = outcome
        self.confidence = confidence
        self.calibrated_confidence = calibrated_confidence
        self.created_at = created_at or datetime.now(timezone.utc)
        self.resolved_at = resolved_at
        self.evidence = evidence or []
        self.experiment_notes = experiment_notes

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "statement": self.statement,
            "intent_id": self.intent_id,
            "assumption_ids": self.assumption_ids,
            "prediction": self.prediction,
            "predicted_value": self.predicted_value,
            "actual_value": self.actual_value,
            "outcome": self.outcome,
            "confidence": round(self.confidence, 4),
            "calibrated_confidence": round(self.calibrated_confidence, 4) if self.calibrated_confidence is not None else None,
            "created_at": self.created_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "evidence": self.evidence,
            "experiment_notes": self.experiment_notes,
        }


class HypothesisStore:
    """Stores, tracks, and resolves hypotheses.

    Usage:
        store = HypothesisStore()
        hid = store.create(
            statement="Moving Legal earlier reduces cycle time by 5 days",
            intent_id="intent-abc123",
            assumption_ids=["asmp-def456"],
            prediction="Cycle time will be 15 days",
            predicted_value=15.0,
        )
        store.resolve(hid, actual_value=17.0)  # Partially correct
        report = store.calibration_report()
    """

    def __init__(self) -> None:
        self._hypotheses: dict[str, Hypothesis] = {}

    def create(
        self,
        statement: str,
        intent_id: str,
        assumption_ids: list[str] | None = None,
        prediction: str = "",
        predicted_value: float | None = None,
        confidence: float = 0.5,
        experiment_notes: str = "",
    ) -> str:
        """Create a new hypothesis linked to an intent."""
        hypothesis_id = f"hyp-{uuid4().hex[:12]}"
        hypothesis = Hypothesis(
            hypothesis_id=hypothesis_id,
            statement=statement,
            intent_id=intent_id,
            assumption_ids=assumption_ids or [],
            prediction=prediction,
            predicted_value=predicted_value,
            confidence=confidence,
            experiment_notes=experiment_notes,
        )
        self._hypotheses[hypothesis_id] = hypothesis
        logger.info("Hypothesis created: %s — '%s'", hypothesis_id, statement[:60])
        return hypothesis_id

    def get(self, hypothesis_id: str) -> dict[str, Any] | None:
        h = self._hypotheses.get(hypothesis_id)
        return h.to_dict() if h else None

    def list_hypotheses(self, status: str | None = None, intent_id: str | None = None) -> list[dict[str, Any]]:
        results = []
        for h in self._hypotheses.values():
            if status and h.outcome != status:
                continue
            if intent_id and h.intent_id != intent_id:
                continue
            results.append(h.to_dict())
        return results

    def resolve(
        self,
        hypothesis_id: str,
        actual_value: float | None = None,
        outcome: str | None = None,
        evidence: list[dict[str, Any]] | None = None,
        notes: str = "",
    ) -> bool:
        """Resolve a hypothesis with the actual outcome.

        If actual_value is provided and predicted_value exists, the
        outcome is determined automatically based on proximity:
          - Within 10% → validated
          - Within 25% → inconclusive
          - Beyond 25% → invalidated
        """
        h = self._hypotheses.get(hypothesis_id)
        if not h:
            return False

        h.actual_value = actual_value
        h.resolved_at = datetime.now(timezone.utc)
        if evidence:
            h.evidence.extend(evidence)
        if notes:
            h.experiment_notes = notes

        # Auto-determine outcome if not explicitly provided
        if outcome:
            h.outcome = outcome
        elif actual_value is not None and h.predicted_value is not None:
            diff = abs(actual_value - h.predicted_value)
            threshold = max(abs(h.predicted_value) * 0.1, 0.5)  # 10% or 0.5
            if diff < threshold:
                h.outcome = "validated"
            elif diff < threshold * 2.5:
                h.outcome = "inconclusive"
            else:
                h.outcome = "invalidated"
        else:
            h.outcome = outcome or "inconclusive"

        # Adjust calibrated confidence based on outcome
        if h.outcome == "validated":
            h.calibrated_confidence = min(1.0, h.confidence + 0.1)
        elif h.outcome == "invalidated":
            h.calibrated_confidence = max(0.0, h.confidence - 0.2)
        else:
            h.calibrated_confidence = h.confidence

        logger.info("Hypothesis %s resolved as %s (predicted=%s, actual=%s)",
                     hypothesis_id, h.outcome, h.predicted_value, actual_value)
        return True

    def calibration_report(self) -> dict[str, Any]:
        """Report on hypothesis accuracy and calibration.

        After 90 days: 'Our hypotheses were 60% accurate. The ones based
        on assumptions about Legal were systematically overconfident.'
        """
        total = len(self._hypotheses)
        if total == 0:
            return {
                "total_hypotheses": 0,
                "validated": 0,
                "invalidated": 0,
                "inconclusive": 0,
                "pending": 0,
                "accuracy_rate": 0,
                "avg_confidence_gap": 0,
                "narrative": "No hypotheses tracked yet.",
            }

        validated = sum(1 for h in self._hypotheses.values() if h.outcome == "validated")
        invalidated = sum(1 for h in self._hypotheses.values() if h.outcome == "invalidated")
        inconclusive = sum(1 for h in self._hypotheses.values() if h.outcome == "inconclusive")
        pending = sum(1 for h in self._hypotheses.values() if h.outcome == "pending")
        resolved = validated + invalidated + inconclusive
        accuracy = validated / resolved if resolved > 0 else 0

        # Confidence gap: how far off was the predicted confidence from reality?
        gaps = []
        for h in self._hypotheses.values():
            if h.outcome in ("validated", "invalidated") and h.calibrated_confidence is not None:
                actual = 1.0 if h.outcome == "validated" else 0.0
                gaps.append(abs(h.confidence - actual))

        avg_gap = sum(gaps) / len(gaps) if gaps else 0

        return {
            "total_hypotheses": total,
            "validated": validated,
            "invalidated": invalidated,
            "inconclusive": inconclusive,
            "pending": pending,
            "accuracy_rate": round(accuracy, 4),
            "avg_confidence_gap": round(avg_gap, 4),
            "narrative": (
                f"{accuracy:.0%} of resolved hypotheses were validated. "
                f"{validated} validated, {invalidated} invalidated, "
                f"{inconclusive} inconclusive, {pending} pending. "
                f"Average confidence gap: {avg_gap:.2f} (lower = better calibrated)."
            ),
        }

    def get_for_intent(self, intent_id: str) -> list[dict[str, Any]]:
        """Get all hypotheses linked to a specific intent."""
        return self.list_hypotheses(intent_id=intent_id)

    def infer_from_recommendations(self, recommendations: list[Any], intent_store=None) -> list[str]:
        """Infer hypotheses from OEM recommendations.

        Each recommendation implies a hypothesis: "addressing this bottleneck
        will improve velocity" → "If we resolve bottleneck X, velocity
        increases by Y."
        """
        inferred = []
        for rec in recommendations:
            title = getattr(rec, "title", str(rec))
            confidence = getattr(rec, "confidence", 0.5)
            rec_id = getattr(rec, "rec_id", "")

            # Infer intent_id if available
            intent_id = ""
            if intent_store:
                intents = intent_store.list_intents()
                for i in intents:
                    if rec_id in i.get("success_criteria", ""):
                        intent_id = i["intent_id"]
                        break

            if "bottleneck" in title.lower():
                stmt = f"Resolving the bottleneck in '{title[:40]}' will improve execution velocity"
                prediction = "Velocity will increase within 2 sprints"
                predicted_value = 1.0  # Normalized improvement
            elif "expert" in title.lower():
                stmt = f"Formalizing the expert in '{title[:40]}' will reduce knowledge risk"
                prediction = "Knowledge concentration risk will decrease"
                predicted_value = 0.5
            elif "risk" in title.lower():
                stmt = f"Addressing the risk in '{title[:40]}' will prevent the predicted outcome"
                prediction = "The risk will not materialize"
                predicted_value = 0.0
            elif "customer" in title.lower():
                stmt = f"Acting on the customer situation in '{title[:40]}' will improve relationship health"
                prediction = "Customer relationship state will improve"
                predicted_value = 1.0
            else:
                stmt = f"Acting on '{title[:40]}' will produce the expected outcome"
                prediction = "The expected outcome will occur"
                predicted_value = 1.0

            hid = self.create(
                statement=stmt,
                intent_id=intent_id,
                prediction=prediction,
                predicted_value=predicted_value,
                confidence=confidence,
            )
            inferred.append(hid)

        return inferred

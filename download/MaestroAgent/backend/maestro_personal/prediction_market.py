"""
V8 Personal Mode — Phase 2-6: Personal Prediction Market.

User bets on their own goals ("Will I finish the book this month?"),
Maestro tracks calibration over time. Reuses the enterprise Brier-score
logic. No social accountability circles. Predictions are private.

WITHDRAWAL PATH (Guideline P9):
The user could stop using the prediction market and simply track their
goals in a notebook. The market adds calibration awareness; without it,
the user is less aware of their own overconfidence but fully functional.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class Prediction:
    """A personal prediction — the user bets on their own goal."""
    prediction_id: str = field(default_factory=lambda: str(uuid4()))
    question: str = ""
    user_probability: float = 0.5  # user's stated probability (0..1)
    outcome: str = "pending"  # "pending", "yes", "no"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved_at: str | None = None

    @property
    def brier_score(self) -> float | None:
        """Brier score: (predicted_prob - actual_outcome)^2.
        actual_outcome = 1.0 for "yes", 0.0 for "no".
        Lower Brier = better calibration.
        """
        if self.outcome == "pending":
            return None
        actual = 1.0 if self.outcome == "yes" else 0.0
        return round((self.user_probability - actual) ** 2, 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "prediction_id": self.prediction_id,
            "question": self.question,
            "user_probability": self.user_probability,
            "outcome": self.outcome,
            "brier_score": self.brier_score,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
        }


class PersonalPredictionMarket:
    """Private prediction market for personal goals.

    No leaderboards, no sharing, no social pressure. The user bets on
    their own goals and tracks calibration over time.

    MULTI-USER SAFETY (P7 isolation fix):
    Predictions are scoped per-user via a user_id key. The prior
    implementation used a bare class-level ``_predictions: dict = {}``
    which is a shared mutable — all "users" (in a multi-tenant
    deployment) would see the same dict, leaking predictions across
    users. The fix keys the dict by ``user_id``; callers MUST pass
    ``user_id``. The single-user convenience API (no user_id) routes
    to the ``"__default__"`` slot for backward compatibility with
    existing tests, but production callers must pass a real user_id.
    """

    _predictions: dict[str, dict[str, Prediction]] = {}

    @classmethod
    def create_prediction(cls, question: str, probability: float, user_id: str = "__default__") -> Prediction:
        """Create a prediction. Probability must be 0..1.

        Args:
            question: The prediction question.
            probability: User's stated probability (0..1).
            user_id: The user this prediction belongs to. Required in
                multi-user deployment; defaults to "__default__" for
                single-user backward compatibility.
        """
        if not 0.0 <= probability <= 1.0:
            raise ValueError("Probability must be between 0 and 1.")
        pred = Prediction(question=question, user_probability=probability)
        cls._predictions.setdefault(user_id, {})[pred.prediction_id] = pred
        return pred

    @classmethod
    def resolve_prediction(cls, prediction_id: str, outcome: str, user_id: str = "__default__") -> Prediction | None:
        """Resolve a prediction. outcome must be 'yes' or 'no'.

        Args:
            prediction_id: The prediction to resolve.
            outcome: Must be 'yes' or 'no'.
            user_id: The user the prediction belongs to. Required in
                multi-user deployment; defaults to "__default__" for
                single-user backward compatibility.
        """
        if outcome not in ("yes", "no"):
            raise ValueError("Outcome must be 'yes' or 'no'.")
        user_preds = cls._predictions.get(user_id, {})
        pred = user_preds.get(prediction_id)
        if not pred:
            return None
        pred.outcome = outcome
        pred.resolved_at = datetime.now(timezone.utc).isoformat()
        return pred

    @classmethod
    def get_predictions(cls, user_id: str = "__default__") -> list[Prediction]:
        """Get all predictions for a user. Defaults to '__default__' for backward compat."""
        return list(cls._predictions.get(user_id, {}).values())

    @classmethod
    def get_calibration(cls, user_id: str = "__default__") -> dict[str, Any]:
        """Get calibration summary — average Brier score across resolved predictions.

        P25 (confidence display gate): if fewer than 10 resolved predictions
        exist, the message says "insufficient calibration history" rather
        than displaying a 4-decimal Brier average that implies more rigor
        than the sample supports.
        """
        resolved = [p for p in cls._predictions.get(user_id, {}).values() if p.outcome != "pending"]
        if not resolved:
            return {"total": 0, "average_brier": None, "message": "No resolved predictions yet."}
        brier_scores = [p.brier_score for p in resolved if p.brier_score is not None]
        avg_brier = sum(brier_scores) / len(brier_scores) if brier_scores else None
        # P25: gate 4-decimal precision on sample size
        if len(resolved) < 10:
            message = (
                f"Insufficient calibration history: {len(resolved)} resolved prediction(s). "
                f"Need 10+ for a reliable Brier average. Keep predicting."
            )
        else:
            message = f"Average Brier score: {avg_brier:.4f} across {len(resolved)} resolved predictions."
        return {
            "total": len(resolved),
            "average_brier": round(avg_brier, 4) if avg_brier is not None else None,
            "message": message,
        }

    @classmethod
    def clear(cls, user_id: str | None = None) -> None:
        """Clear predictions. If user_id is None, clears ALL users (test helper only).

        Args:
            user_id: If provided, clears only that user's predictions.
                If None, clears all users. Use None only in test teardown.
        """
        if user_id is None:
            cls._predictions = {}
        else:
            cls._predictions.pop(user_id, None)

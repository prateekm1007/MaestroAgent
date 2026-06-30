"""
Prediction Market — calibrate individual prediction accuracy.

Nobody calibrates individual prediction accuracy inside an enterprise.
Maestro can. This is the second biggest moat after the Assumption Graph.

People submit probability estimates ("70% chance this ships on time").
When the outcome arrives, each predictor gets a Brier score. Over time,
the system builds a calibration profile for each person.

The killer view: ranked list of predictors by calibration accuracy.
Not hierarchy. Accuracy. This becomes an internal trust network based
on evidence, not org charts.

Links directly to the Hypothesis Layer — predictions attach to
hypotheses, hypotheses attach to intents.

Product law: eliminates THINKING ("whose estimate should I trust?")
by providing evidence-based calibration data for each predictor.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


class PersonalPrediction:
    """A single person's probability estimate for a specific event."""

    def __init__(
        self,
        prediction_id: str,
        predictor: str,  # person's email
        event: str,  # "Q4 launch ships on time"
        probability: float,  # 0.0-1.0
        made_at: datetime | None = None,
        resolution_window: str = "",  # "Q4 2025"
        hypothesis_id: str = "",  # links to Hypothesis if applicable
        intent_id: str = "",  # links to Intent if applicable
        status: str = "open",  # open | resolved
        actual_outcome: bool | None = None,  # True=happened, False=didn't
        resolved_at: datetime | None = None,
        brier_score: float | None = None,
        notes: str = "",
    ) -> None:
        self.prediction_id = prediction_id
        self.predictor = predictor
        self.event = event
        self.probability = probability
        self.made_at = made_at or datetime.now(timezone.utc)
        self.resolution_window = resolution_window
        self.hypothesis_id = hypothesis_id
        self.intent_id = intent_id
        self.status = status
        self.actual_outcome = actual_outcome
        self.resolved_at = resolved_at
        self.brier_score = brier_score
        self.notes = notes

    def to_dict(self) -> dict[str, Any]:
        return {
            "prediction_id": self.prediction_id,
            "predictor": self.predictor,
            "event": self.event,
            "probability": round(self.probability, 4),
            "made_at": self.made_at.isoformat(),
            "resolution_window": self.resolution_window,
            "hypothesis_id": self.hypothesis_id,
            "intent_id": self.intent_id,
            "status": self.status,
            "actual_outcome": self.actual_outcome,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "brier_score": round(self.brier_score, 4) if self.brier_score is not None else None,
            "notes": self.notes,
        }


class PredictorProfile:
    """Calibration profile for a single person."""

    def __init__(self, email: str) -> None:
        self.email = email
        self.total_predictions = 0
        self.resolved_predictions = 0
        self.correct_predictions = 0
        self.avg_brier_score: float | None = None
        self.avg_confidence = 0.0
        self.overconfidence_bias = 0.0  # positive = overconfident
        self.calibration_trend: list[float] = []  # brier scores over time

    def update(self, prediction: PersonalPrediction) -> None:
        """Update the profile with a resolved prediction."""
        self.total_predictions += 1
        self.avg_confidence = (
            (self.avg_confidence * (self.total_predictions - 1) + prediction.probability)
            / self.total_predictions
        )
        if prediction.status == "resolved" and prediction.brier_score is not None:
            self.resolved_predictions += 1
            self.calibration_trend.append(prediction.brier_score)
            if prediction.actual_outcome and prediction.probability > 0.5:
                self.correct_predictions += 1
            elif not prediction.actual_outcome and prediction.probability < 0.5:
                self.correct_predictions += 1
            # Update avg brier
            if self.avg_brier_score is None:
                self.avg_brier_score = prediction.brier_score
            else:
                self.avg_brier_score = (
                    (self.avg_brier_score * (self.resolved_predictions - 1) + prediction.brier_score)
                    / self.resolved_predictions
                )
            # Overconfidence: avg confidence - actual success rate
            actual_rate = self.correct_predictions / self.resolved_predictions
            self.overconfidence_bias = self.avg_confidence - actual_rate

    def to_dict(self) -> dict[str, Any]:
        accuracy = self.correct_predictions / self.resolved_predictions if self.resolved_predictions > 0 else 0
        return {
            "email": self.email,
            "total_predictions": self.total_predictions,
            "resolved_predictions": self.resolved_predictions,
            "correct_predictions": self.correct_predictions,
            "accuracy_rate": round(accuracy, 4),
            "avg_brier_score": round(self.avg_brier_score, 4) if self.avg_brier_score is not None else None,
            "avg_confidence": round(self.avg_confidence, 4),
            "overconfidence_bias": round(self.overconfidence_bias, 4),
            "calibration_quality": self._calibration_label(),
            "calibration_trend": self.calibration_trend[-10:],  # last 10
        }

    def _calibration_label(self) -> str:
        if self.avg_brier_score is None:
            return "untested"
        if self.avg_brier_score < 0.1:
            return "excellent"
        if self.avg_brier_score < 0.2:
            return "well-calibrated"
        if self.avg_brier_score < 0.3:
            return "moderate"
        if self.avg_brier_score < 0.4:
            return "poor"
        return "uncalibrated"


class PredictionMarket:
    """Stores personal predictions and computes calibration profiles.

    Usage:
        market = PredictionMarket()
        pid = market.submit("jane@acme.com", "Q4 launch ships on time", 0.7)
        market.resolve(pid, actual_outcome=True)
        profiles = market.calibration_ranking()
        # [{email: "jane@acme.com", avg_brier_score: 0.09, ...}]
    """

    def __init__(self) -> None:
        self._predictions: dict[str, PersonalPrediction] = {}
        self._profiles: dict[str, PredictorProfile] = {}

    def submit(
        self,
        predictor: str,
        event: str,
        probability: float,
        resolution_window: str = "",
        hypothesis_id: str = "",
        intent_id: str = "",
        notes: str = "",
    ) -> str:
        """Submit a personal prediction. Returns prediction_id."""
        if not 0.0 <= probability <= 1.0:
            raise ValueError(f"Probability must be 0.0-1.0, got {probability}")
        prediction_id = f"pp-{uuid4().hex[:12]}"
        prediction = PersonalPrediction(
            prediction_id=prediction_id,
            predictor=predictor,
            event=event,
            probability=probability,
            resolution_window=resolution_window,
            hypothesis_id=hypothesis_id,
            intent_id=intent_id,
            notes=notes,
        )
        self._predictions[prediction_id] = prediction
        logger.info("Prediction submitted: %s by %s — '%s' (%.0f%%)",
                     prediction_id, predictor, event[:40], probability * 100)
        return prediction_id

    def resolve(self, prediction_id: str, actual_outcome: bool) -> bool:
        """Resolve a prediction with the actual outcome.

        Computes the Brier score: (probability - outcome)^2
        where outcome is 1.0 (happened) or 0.0 (didn't).
        Lower Brier = better. 0 = perfect, 0.25 = random, 1 = worst.
        """
        p = self._predictions.get(prediction_id)
        if not p:
            return False

        p.actual_outcome = actual_outcome
        p.status = "resolved"
        p.resolved_at = datetime.now(timezone.utc)
        outcome_val = 1.0 if actual_outcome else 0.0
        p.brier_score = (p.probability - outcome_val) ** 2

        # Update predictor profile
        profile = self._profiles.setdefault(p.predictor, PredictorProfile(p.predictor))
        profile.update(p)

        logger.info("Prediction %s resolved: outcome=%s, brier=%.4f",
                     prediction_id, actual_outcome, p.brier_score)
        return True

    def get(self, prediction_id: str) -> dict[str, Any] | None:
        p = self._predictions.get(prediction_id)
        return p.to_dict() if p else None

    def list_predictions(
        self,
        status: str | None = None,
        predictor: str | None = None,
    ) -> list[dict[str, Any]]:
        results = []
        for p in self._predictions.values():
            if status and p.status != status:
                continue
            if predictor and p.predictor != predictor:
                continue
            results.append(p.to_dict())
        return results

    def calibration_ranking(self) -> list[dict[str, Any]]:
        """Ranked list of predictors by calibration accuracy.

        Not hierarchy. Accuracy. This is the internal trust network.
        """
        profiles = [p.to_dict() for p in self._profiles.values() if p.resolved_predictions > 0]
        # Sort by avg_brier_score ascending (lower = better)
        profiles.sort(key=lambda p: p.get("avg_brier_score", 1.0))
        return profiles

    def get_profile(self, email: str) -> dict[str, Any] | None:
        profile = self._profiles.get(email)
        return profile.to_dict() if profile else None

    def infer_from_signals(self, signals: list) -> list[str]:
        """Infer predictions from signals that contain probability language.

        Slack/GitHub comments with "probably", "unlikely", "definitely"
        are mapped to probability ranges and stored as predictions.
        """
        probability_map = {
            "definitely": 0.95, "certainly": 0.95, "guaranteed": 0.98,
            "very likely": 0.85, "highly likely": 0.85,
            "likely": 0.7, "probably": 0.7, "most likely": 0.75,
            "possibly": 0.5, "maybe": 0.45, "might": 0.4,
            "unlikely": 0.25, "probably not": 0.2,
            "very unlikely": 0.1, "doubt it": 0.15,
            "no way": 0.05, "impossible": 0.02,
        }

        inferred = []
        from maestro_oem.signal import SignalType
        for s in signals:
            if s.type not in (SignalType.MESSAGE_SENT, SignalType.DECISION_SIGNAL,
                              SignalType.THREAD_STARTED):
                continue
            text = s.metadata.get("text", "").lower()
            if not text:
                continue

            for phrase, prob in probability_map.items():
                if phrase in text:
                    pid = self.submit(
                        predictor=s.actor,
                        event=f"Predicted from: {s.metadata.get('text', '')[:60]}",
                        probability=prob,
                        resolution_window="",
                        notes=f"Inferred from {s.type.value} signal",
                    )
                    inferred.append(pid)
                    break  # Only one prediction per signal

        return inferred

"""
Historical Replay — replaces storytelling with actual backtesting.

Given a date:
  1. Freeze the OEM at that point (only process signals up to that date)
  2. Generate predictions from the frozen model
  3. Replay the remaining signals (the "future")
  4. Compare predictions against actual outcomes
  5. Store accuracy metrics: hit rate, false positives, false negatives, calibration drift

Every simulation now shows:
  - Historical Validation (was the prediction correct?)
  - Prediction Accuracy (fraction of predictions that held)
  - False Positives (predicted event, didn't happen)
  - False Negatives (didn't predict, event happened)
  - Calibration Drift (predicted confidence vs actual hit rate)

The simulator no longer tells stories. It replays history.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from maestro_oem.confidence import ConfidenceCalculator
from maestro_oem.engine import OEMEngine
from maestro_oem.model import ExecutionModel, ModelDelta
from maestro_oem.signal import ExecutionSignal


class PredictionOutcome(str, Enum):
    """Outcome of a prediction after replay."""
    PENDING = "pending"
    HIT = "hit"               # Predicted correctly
    MISS = "miss"             # Predicted incorrectly
    FALSE_POSITIVE = "false_positive"  # Predicted event, didn't happen
    FALSE_NEGATIVE = "false_negative"  # Didn't predict, event happened


class HistoricalPrediction(BaseModel):
    """
    A prediction made at a frozen point in time.

    The prediction is generated from the OEM state at the freeze date.
    The outcome is determined by replaying the "future" signals.
    """
    prediction_id: UUID = Field(default_factory=uuid4)
    freeze_date: datetime
    prediction_text: str
    predicted_confidence: float
    predicted_event: str  # What we predicted would happen
    predicted_probability: float  # P(event) at freeze time

    # Actual outcome (filled after replay)
    actual_outcome: str = ""
    actual_event_occurred: bool | None = None
    outcome: PredictionOutcome = PredictionOutcome.PENDING

    # Verification
    verified_at: datetime | None = None
    verification_evidence: list[dict[str, Any]] = Field(default_factory=list)
    confidence_bucket: int = 0  # For calibration curve

    # Metadata
    linked_law: str = ""
    linked_lo: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass
class ReplayMetrics:
    """
    Metrics from a historical replay run.

    Every simulation returns these — no storytelling, just numbers.
    """
    freeze_date: datetime
    replay_end_date: datetime
    total_predictions: int = 0
    hits: int = 0
    misses: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    pending: int = 0

    # Calibration
    predicted_confidence_avg: float = 0.0
    actual_hit_rate: float = 0.0
    calibration_drift: float = 0.0  # |predicted_confidence - actual_hit_rate|

    # Per-bucket calibration (0-9)
    bucket_hits: list[int] = field(default_factory=lambda: [0] * 10)
    bucket_total: list[int] = field(default_factory=lambda: [0] * 10)

    @property
    def prediction_accuracy(self) -> float:
        """Fraction of predictions that were correct."""
        verified = self.hits + self.misses
        return self.hits / verified if verified > 0 else 0.0

    @property
    def false_positive_rate(self) -> float:
        """Fraction of predicted events that didn't happen."""
        predicted_events = self.hits + self.false_positives
        return self.false_positives / predicted_events if predicted_events > 0 else 0.0

    @property
    def false_negative_rate(self) -> float:
        """Fraction of actual events that weren't predicted."""
        actual_events = self.hits + self.false_negatives
        return self.false_negatives / actual_events if actual_events > 0 else 0.0

    @property
    def shr(self) -> float:
        """Surprise Hit Rate — same as prediction_accuracy."""
        return self.prediction_accuracy

    def to_dict(self) -> dict[str, Any]:
        return {
            "freeze_date": self.freeze_date.isoformat(),
            "replay_end_date": self.replay_end_date.isoformat(),
            "total_predictions": self.total_predictions,
            "hits": self.hits,
            "misses": self.misses,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "pending": self.pending,
            "prediction_accuracy": round(self.prediction_accuracy, 4),
            "false_positive_rate": round(self.false_positive_rate, 4),
            "false_negative_rate": round(self.false_negative_rate, 4),
            "shr": round(self.shr, 4),
            "predicted_confidence_avg": round(self.predicted_confidence_avg, 4),
            "actual_hit_rate": round(self.actual_hit_rate, 4),
            "calibration_drift": round(self.calibration_drift, 4),
            "bucket_hits": self.bucket_hits,
            "bucket_total": self.bucket_total,
        }


class HistoricalReplay:
    """
    Replays history to validate predictions.

    Usage:
        replay = HistoricalReplay(all_signals)
        result = replay.run(freeze_date=datetime(2024, 6, 1, tzinfo=timezone.utc))

        result.metrics.prediction_accuracy  # 0.83
        result.metrics.false_positive_rate  # 0.12
        result.metrics.calibration_drift    # 0.05
        result.predictions[0].outcome       # PredictionOutcome.HIT

    The simulator no longer tells stories. It replays history.
    """

    def __init__(self, all_signals: list[ExecutionSignal]) -> None:
        self.all_signals = sorted(all_signals, key=lambda s: s.timestamp)
        self.predictions: list[HistoricalPrediction] = []

    def run(
        self,
        freeze_date: datetime,
        end_date: datetime | None = None,
    ) -> ReplayResult:
        """
        Run a historical replay.

        1. Freeze OEM at freeze_date (process only signals up to that date)
        2. Generate predictions from the frozen model
        3. Replay the "future" signals (after freeze_date)
        4. Compare predictions against actual outcomes
        5. Compute metrics

        Returns a ReplayResult with predictions and metrics.
        """
        if end_date is None:
            end_date = self.all_signals[-1].timestamp if self.all_signals else datetime.now(timezone.utc)

        # 1. Split signals into "past" and "future"
        past_signals = [s for s in self.all_signals if s.timestamp <= freeze_date]
        future_signals = [s for s in self.all_signals if freeze_date < s.timestamp <= end_date]

        # 2. Build frozen OEM
        frozen_engine = OEMEngine()
        if past_signals:
            frozen_engine.ingest(past_signals)
        frozen_model = frozen_engine.get_model()

        # 3. Generate predictions from the frozen model
        predictions = self._generate_predictions(frozen_model, freeze_date)

        # 4. Replay the future and verify predictions
        future_engine = OEMEngine()
        # Start from the frozen state (copy the model)
        future_engine.model = frozen_model
        if future_signals:
            future_engine.ingest(future_signals)
        future_model = future_engine.get_model()

        # 5. Verify each prediction against the future state
        for pred in predictions:
            self._verify_prediction(pred, frozen_model, future_model, future_signals)

        # 6. Compute metrics
        metrics = self._compute_metrics(predictions, freeze_date, end_date)

        self.predictions = predictions

        return ReplayResult(
            freeze_date=freeze_date,
            end_date=end_date,
            frozen_model_summary=frozen_model.get_summary(),
            future_model_summary=future_model.get_summary(),
            predictions=predictions,
            metrics=metrics.to_dict(),
            past_signal_count=len(past_signals),
            future_signal_count=len(future_signals),
        )

    def _generate_predictions(
        self,
        model: ExecutionModel,
        freeze_date: datetime,
    ) -> list[HistoricalPrediction]:
        """
        Generate predictions from the frozen model.

        Each law, risk, and health metric becomes a prediction.
        """
        predictions: list[HistoricalPrediction] = []

        # Predictions from laws
        for law_code, law in model.laws.items():
            if law.confidence < 0.3:
                continue  # Don't predict from low-confidence laws

            pred = HistoricalPrediction(
                freeze_date=freeze_date,
                prediction_text=f"Law {law_code}: {law.statement}",
                predicted_confidence=law.confidence,
                predicted_event=law.outcome,
                predicted_probability=law.confidence,
                linked_law=law_code,
                confidence_bucket=ConfidenceCalculator.compute_confidence_bucket(law.confidence),
                metadata={
                    "law_validated_runtimes": law.validated_runtimes,
                    "law_failed_runtimes": law.failed_runtimes,
                    "law_status": law.status.value,
                },
            )
            predictions.append(pred)

        # Predictions from risks
        for entity, prob in model.risks.departure_risks.items():
            if prob < 0.3:
                continue
            pred = HistoricalPrediction(
                freeze_date=freeze_date,
                prediction_text=f"Departure risk: {entity} may leave (P={prob:.0%})",
                predicted_confidence=prob,
                predicted_event=f"{entity}_departs",
                predicted_probability=prob,
                metadata={"entity": entity, "risk_type": "departure"},
                confidence_bucket=ConfidenceCalculator.compute_confidence_bucket(prob),
            )
            predictions.append(pred)

        # Prediction from health: P1 cluster risk
        if model.health.p1_cluster_risk > 0.3:
            pred = HistoricalPrediction(
                freeze_date=freeze_date,
                prediction_text=f"P1 cluster risk: velocity drop predicted (P={model.health.p1_cluster_risk:.0%})",
                predicted_confidence=model.health.p1_cluster_risk,
                predicted_event="velocity_drop",
                predicted_probability=model.health.p1_cluster_risk,
                metadata={"incident_rate_at_freeze": model.health.incident_rate},
                confidence_bucket=ConfidenceCalculator.compute_confidence_bucket(model.health.p1_cluster_risk),
            )
            predictions.append(pred)

        # Prediction from bottlenecks: gate will continue to bottleneck
        for bn in model.approvals.get_bottlenecks(min_count=3):
            pred = HistoricalPrediction(
                freeze_date=freeze_date,
                prediction_text=f"Bottleneck {bn['gate']} will continue to gate items",
                predicted_confidence=min(0.9, 0.5 + bn["items_gated"] * 0.05),
                predicted_event=f"bottleneck_continues_{bn['gate']}",
                predicted_probability=min(0.9, 0.5 + bn["items_gated"] * 0.05),
                metadata={"gate": bn["gate"], "items_gated": bn["items_gated"]},
                confidence_bucket=ConfidenceCalculator.compute_confidence_bucket(
                    min(0.9, 0.5 + bn["items_gated"] * 0.05)
                ),
            )
            predictions.append(pred)

        return predictions

    def _verify_prediction(
        self,
        pred: HistoricalPrediction,
        frozen_model: ExecutionModel,
        future_model: ExecutionModel,
        future_signals: list[ExecutionSignal],
    ) -> None:
        """
        Verify a prediction against the actual future state.

        Determines HIT, MISS, FALSE_POSITIVE, or FALSE_NEGATIVE.
        """
        pred.verified_at = datetime.now(timezone.utc)
        pred.outcome = PredictionOutcome.HIT  # Default, will be overridden

        # Verify law predictions
        if pred.linked_law:
            law_code = pred.linked_law
            frozen_law = frozen_model.laws.get(law_code)
            future_law = future_model.laws.get(law_code)

            if not future_law:
                # Law disappeared — invalidated by future evidence
                pred.actual_outcome = "Law invalidated by future evidence"
                pred.actual_event_occurred = False
                pred.outcome = PredictionOutcome.MISS
                pred.verification_evidence = [{"signal": "law_invalidated", "law": law_code}]
                return

            # Check if the law held (more validations than counter-examples added)
            frozen_validations = frozen_law.validated_runtimes if frozen_law else 0
            frozen_failures = frozen_law.failed_runtimes if frozen_law else 0
            future_validations = future_law.validated_runtimes
            future_failures = future_law.failed_runtimes

            new_validations = future_validations - frozen_validations
            new_failures = future_failures - frozen_failures

            if new_failures > new_validations:
                pred.actual_outcome = f"Law stressed: +{new_failures} failures vs +{new_validations} validations"
                pred.actual_event_occurred = False
                pred.outcome = PredictionOutcome.MISS
            else:
                pred.actual_outcome = f"Law held: +{new_validations} validations vs +{new_failures} failures"
                pred.actual_event_occurred = True
                pred.outcome = PredictionOutcome.HIT

            pred.verification_evidence = [
                {"frozen_validations": frozen_validations, "frozen_failures": frozen_failures},
                {"future_validations": future_validations, "future_failures": future_failures},
            ]
            return

        # Verify departure risk predictions
        entity = pred.metadata.get("entity")
        if entity and pred.metadata.get("risk_type") == "departure":
            # Check if the entity actually departed (no future signals from them)
            future_signals_from_entity = [s for s in future_signals if s.actor == entity]
            if len(future_signals_from_entity) == 0:
                pred.actual_outcome = f"{entity} went silent (no future signals)"
                pred.actual_event_occurred = True
                pred.outcome = PredictionOutcome.HIT
            else:
                # Check if departure risk increased or decreased
                future_risk = future_model.risks.departure_risks.get(entity, 0)
                if future_risk > pred.predicted_probability:
                    pred.actual_outcome = f"Departure risk increased: {pred.predicted_probability:.2f} → {future_risk:.2f}"
                    pred.actual_event_occurred = True
                    pred.outcome = PredictionOutcome.HIT
                else:
                    pred.actual_outcome = f"Departure risk decreased: {pred.predicted_probability:.2f} → {future_risk:.2f}"
                    pred.actual_event_occurred = False
                    pred.outcome = PredictionOutcome.FALSE_POSITIVE
            return

        # Verify velocity drop predictions
        if pred.predicted_event == "velocity_drop":
            frozen_incident_rate = frozen_model.health.incident_rate
            future_incident_rate = future_model.health.incident_rate
            new_incidents = future_incident_rate - frozen_incident_rate

            if new_incidents > 0:
                pred.actual_outcome = f"Velocity drop materialized: +{new_incidents} new incidents"
                pred.actual_event_occurred = True
                pred.outcome = PredictionOutcome.HIT
            else:
                pred.actual_outcome = "No new incidents — velocity drop did not materialize"
                pred.actual_event_occurred = False
                pred.outcome = PredictionOutcome.FALSE_POSITIVE

            pred.verification_evidence = [
                {"frozen_incident_rate": frozen_incident_rate},
                {"future_incident_rate": future_incident_rate},
            ]
            return

        # Verify bottleneck predictions
        if pred.predicted_event and pred.predicted_event.startswith("bottleneck_continues_"):
            gate = pred.metadata.get("gate", "")
            future_bottlenecks = future_model.approvals.get_bottlenecks(min_count=3)
            still_bottlenecked = any(b["gate"] == gate for b in future_bottlenecks)

            if still_bottlenecked:
                pred.actual_outcome = f"Bottleneck {gate} continues in future"
                pred.actual_event_occurred = True
                pred.outcome = PredictionOutcome.HIT
            else:
                pred.actual_outcome = f"Bottleneck {gate} resolved in future"
                pred.actual_event_occurred = False
                pred.outcome = PredictionOutcome.FALSE_POSITIVE
            return

        # Default: can't verify
        pred.actual_outcome = "Could not verify — no matching event type"
        pred.actual_event_occurred = None
        pred.outcome = PredictionOutcome.PENDING

    def _compute_metrics(
        self,
        predictions: list[HistoricalPrediction],
        freeze_date: datetime,
        end_date: datetime,
    ) -> ReplayMetrics:
        """Compute accuracy metrics from verified predictions."""
        metrics = ReplayMetrics(freeze_date=freeze_date, replay_end_date=end_date)

        verified_confidences: list[float] = []
        hits_count = 0
        verified_count = 0

        for pred in predictions:
            metrics.total_predictions += 1
            bucket = pred.confidence_bucket
            metrics.bucket_total[bucket] += 1

            if pred.outcome == PredictionOutcome.HIT:
                metrics.hits += 1
                metrics.bucket_hits[bucket] += 1
                verified_confidences.append(pred.predicted_confidence)
                hits_count += 1
                verified_count += 1
            elif pred.outcome == PredictionOutcome.MISS:
                metrics.misses += 1
                verified_confidences.append(pred.predicted_confidence)
                verified_count += 1
            elif pred.outcome == PredictionOutcome.FALSE_POSITIVE:
                metrics.false_positives += 1
                verified_confidences.append(pred.predicted_confidence)
                verified_count += 1
            elif pred.outcome == PredictionOutcome.FALSE_NEGATIVE:
                metrics.false_negatives += 1
            elif pred.outcome == PredictionOutcome.PENDING:
                metrics.pending += 1

        # Averaged predicted confidence (over verified predictions)
        if verified_confidences:
            metrics.predicted_confidence_avg = sum(verified_confidences) / len(verified_confidences)
        else:
            metrics.predicted_confidence_avg = 0.0

        # Actual hit rate
        if verified_count > 0:
            metrics.actual_hit_rate = hits_count / verified_count
        else:
            metrics.actual_hit_rate = 0.0

        # Calibration drift = |predicted confidence - actual hit rate|
        metrics.calibration_drift = abs(metrics.predicted_confidence_avg - metrics.actual_hit_rate)

        return metrics


class ReplayResult(BaseModel):
    """Result of a historical replay run."""
    freeze_date: datetime
    end_date: datetime
    frozen_model_summary: dict[str, Any]
    future_model_summary: dict[str, Any]
    predictions: list[HistoricalPrediction]
    metrics: dict[str, Any]  # Serialized ReplayMetrics
    past_signal_count: int
    future_signal_count: int

    model_config = {"arbitrary_types_allowed": True}

    def get_historical_validation(self) -> dict[str, Any]:
        """
        Get the historical validation summary for display.

        Every simulation must show this.
        """
        return {
            "freeze_date": self.freeze_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "past_signals": self.past_signal_count,
            "future_signals": self.future_signal_count,
            "total_predictions": len(self.predictions),
            "metrics": self.metrics,
            "predictions": [
                {
                    "text": p.prediction_text,
                    "confidence": round(p.predicted_confidence, 4),
                    "outcome": p.outcome.value,
                    "actual": p.actual_outcome,
                    "law": p.linked_law,
                }
                for p in self.predictions
            ],
        }

"""
Maestro Cognitive Council — Task 3: Calibration Infrastructure.

Unifies calibration INFRASTRUCTURE (event schemas, scoring primitives,
reporting conventions) while keeping prediction POPULATIONS separate.

Per the CEO audit directive:
  "Recommendation calibration and hypothesis calibration may be different
   statistical objects. They can share infrastructure, event schemas,
   scoring primitives, and reporting conventions without necessarily
   sharing one calibration population. Combining heterogeneous prediction
   classes into one calibration score would be scientifically wrong."

WHAT IS SHARED (infrastructure):
  - PredictionEvent: unified event schema (prediction_id, kind, predicted_confidence, etc.)
  - brier_score(): true per-prediction Brier = mean((p - y)^2)
  - bucket_of(): 10-bucket reliability structure
  - CalibrationBucket + CalibrationReport: unified reporting shape
  - is_well_calibrated(): shared predicate

WHAT STAYS SEPARATE (populations):
  - Recommendation predictions (did the user accept it? did the law fire?)
  - Hypothesis predictions (did the predicted organizational event happen?)
  - prediction_type is a hard partition key on every shared table/function

THE BLOCKING FIX:
  The hypothesis system (CandidatePattern.calibration_score) currently uses
  a degenerate (0.5 - actual)^2 formula because it has NO predicted_confidence
  per prediction. This module provides the shared brier_score() that requires
  a real predicted_confidence — forcing the hypothesis system to start
  recording one.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# Prediction Event Schema (shared)
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class PredictionEvent:
    """Unified prediction event schema (shared infrastructure).

    Both recommendation predictions and hypothesis predictions use this
    schema. The `prediction_type` field is a HARD PARTITION KEY — it
    determines which population this prediction belongs to. Predictions
    of different types are NEVER combined into one calibration score.

    Fields:
      prediction_id: unique identifier
      prediction_type: "recommendation" | "law" | "hypothesis" (population key)
      predicted_confidence: 0.0-1.0 (REQUIRED — no degenerate 0.5 assumption)
      expected_outcome_label: free-form label (e.g., "hit", "supporting")
      predicted_at: ISO timestamp
      entity_id: optional (law_code, rec_id, candidate_id)
      metadata: optional dict
    """
    prediction_id: str
    prediction_type: str                    # "recommendation" | "law" | "hypothesis"
    predicted_confidence: float             # 0.0-1.0 — REQUIRED
    expected_outcome_label: str = ""        # free-form (e.g., "hit", "supporting")
    predicted_at: str = ""                  # ISO timestamp
    entity_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "prediction_id": self.prediction_id,
            "prediction_type": self.prediction_type,
            "predicted_confidence": round(self.predicted_confidence, 4),
            "expected_outcome_label": self.expected_outcome_label,
            "predicted_at": self.predicted_at,
            "entity_id": self.entity_id,
            "metadata": self.metadata,
        }


# ════════════════════════════════════════════════════════════════════════════
# Outcome Vocabulary (shared mapping)
# ════════════════════════════════════════════════════════════════════════════

# The two systems use different outcome vocabularies:
#   Recommendation: "hit" | "miss" | "pending"
#   Hypothesis:     "supporting" | "contradicting" | "insufficient_data" | "pending"
#
# These are isomorphic. The shared mapping normalizes them to a canonical
# form: "hit" | "miss" | "expired" | "pending"

OUTCOME_CANONICAL: dict[str, str] = {
    # Recommendation vocabulary
    "hit": "hit",
    "miss": "miss",
    # Hypothesis vocabulary
    "supporting": "hit",
    "contradicting": "miss",
    "insufficient_data": "expired",
    # Shared
    "pending": "pending",
}


def canonical_outcome(outcome: str) -> str:
    """Normalize an outcome label to canonical form.

    Returns: "hit" | "miss" | "expired" | "pending" | "unknown"
    """
    return OUTCOME_CANONICAL.get(outcome.lower(), "unknown")


def outcome_to_value(outcome: str) -> Optional[float]:
    """Convert an outcome label to a numeric value for Brier scoring.

    hit → 1.0, miss → 0.0, expired/pending/unknown → None (excluded from Brier)
    """
    canonical = canonical_outcome(outcome)
    if canonical == "hit":
        return 1.0
    if canonical == "miss":
        return 0.0
    return None  # expired, pending, unknown — excluded from Brier


# ════════════════════════════════════════════════════════════════════════════
# Brier Score (shared scoring primitive)
# ════════════════════════════════════════════════════════════════════════════

def brier_score(resolved_predictions: list[tuple[float, float]]) -> Optional[float]:
    """Compute the true per-prediction Brier score.

    Brier = mean over resolved predictions of (p - y)^2
    where p = predicted_confidence, y ∈ {0.0, 1.0}

    This is the textbook half-Brier (binary-outcome) score:
      0.0 = perfect
      0.25 = random with 50% base rate
      1.0 = worst

    This REPLACES the degenerate (0.5 - actual)^2 formula used by
    CandidatePattern.calibration_score. The degenerate formula assumed
    every prediction was made with p=0.5, which made the score
    meaningless (0.25 meant both "fully correct" and "fully wrong").

    Args:
        resolved_predictions: list of (predicted_confidence, actual_value) tuples.
                              actual_value must be 1.0 (hit) or 0.0 (miss).

    Returns:
        The Brier score, or None if no resolved predictions.
    """
    if not resolved_predictions:
        return None

    total = 0.0
    count = 0
    for p, y in resolved_predictions:
        # Skip invalid actual values (should only be 0.0 or 1.0)
        if y not in (0.0, 1.0):
            continue
        total += (p - y) ** 2
        count += 1

    if count == 0:
        return None

    return total / count


# ════════════════════════════════════════════════════════════════════════════
# 10-Bucket Reliability Structure (shared)
# ════════════════════════════════════════════════════════════════════════════

NUM_BUCKETS = 10
CALIBRATION_THRESHOLD = 0.1  # |expected - actual| < 0.1 = "well calibrated"
BRIER_WELL_CALIBRATED = 0.3  # Brier < 0.3 = "calibration acceptable"


def bucket_of(confidence: float) -> int:
    """Map a confidence value (0.0-1.0) to a bucket index (0-9).

    bucket = min(int(confidence * 10), 9)
    Bucket midpoints: 0.05, 0.15, 0.25, ..., 0.95
    """
    return min(int(confidence * 10), 9)


def bucket_expected_rate(bucket: int) -> float:
    """The expected hit rate for a bucket.

    expected_rate = (bucket + 0.5) / 10.0
    """
    return (bucket + 0.5) / 10.0


@dataclass
class CalibrationBucket:
    """One bucket in the 10-bucket reliability diagram."""
    bucket: int                          # 0-9
    expected_rate: float                 # (bucket + 0.5) / 10.0
    actual_rate: float = 0.0             # hits / (hits + misses)
    calibration_error: float = 0.0       # abs(expected - actual)
    is_calibrated: bool = True           # calibration_error < threshold
    predictions: int = 0
    hits: int = 0
    misses: int = 0
    pending: int = 0

    def to_dict(self) -> dict:
        return {
            "bucket": self.bucket,
            "expected_rate": round(self.expected_rate, 3),
            "actual_rate": round(self.actual_rate, 3),
            "calibration_error": round(self.calibration_error, 4),
            "is_calibrated": self.is_calibrated,
            "predictions": self.predictions,
            "hits": self.hits,
            "misses": self.misses,
            "pending": self.pending,
        }


@dataclass
class CalibrationReport:
    """Unified calibration report (shared reporting convention).

    Both recommendation calibration and hypothesis calibration produce
    this shape. The `prediction_type` field identifies which population
    this report covers — they are NEVER combined.
    """
    prediction_type: str                          # "recommendation" | "law" | "hypothesis"
    buckets: list[CalibrationBucket] = field(default_factory=list)
    overall: dict[str, Any] = field(default_factory=dict)
    insufficient_evidence: bool = True            # True if < 3 resolved predictions

    def to_dict(self) -> dict:
        return {
            "prediction_type": self.prediction_type,
            "buckets": [b.to_dict() for b in self.buckets],
            "overall": self.overall,
            "insufficient_evidence": self.insufficient_evidence,
        }


def build_calibration_report(
    prediction_type: str,
    resolved_predictions: list[tuple[float, str]],
) -> CalibrationReport:
    """Build a CalibrationReport from resolved predictions.

    This is the shared reporting function. Both recommendation and
    hypothesis calibration use it. The prediction_type is a hard
    partition key — predictions of different types are NEVER combined.

    Args:
        prediction_type: "recommendation" | "law" | "hypothesis"
        resolved_predictions: list of (predicted_confidence, outcome_label) tuples.
                              outcome_label is "hit"/"miss"/"supporting"/"contradicting"/etc.

    Returns:
        A CalibrationReport with 10 buckets + overall stats.
    """
    # Initialize 10 buckets
    buckets = [
        CalibrationBucket(
            bucket=i,
            expected_rate=bucket_expected_rate(i),
        )
        for i in range(NUM_BUCKETS)
    ]

    total_resolved = 0
    total_hits = 0
    total_misses = 0
    brier_predictions: list[tuple[float, float]] = []

    for confidence, outcome_label in resolved_predictions:
        canonical = canonical_outcome(outcome_label)
        b = bucket_of(confidence)
        buckets[b].predictions += 1

        if canonical == "hit":
            buckets[b].hits += 1
            total_hits += 1
            total_resolved += 1
            brier_predictions.append((confidence, 1.0))
        elif canonical == "miss":
            buckets[b].misses += 1
            total_misses += 1
            total_resolved += 1
            brier_predictions.append((confidence, 0.0))
        elif canonical == "pending":
            buckets[b].pending += 1
        # "expired" and "unknown" are not counted in any bucket

    # Compute actual rates and calibration errors
    for b in buckets:
        resolved_in_bucket = b.hits + b.misses
        if resolved_in_bucket > 0:
            b.actual_rate = b.hits / resolved_in_bucket
            b.calibration_error = abs(b.expected_rate - b.actual_rate)
            b.is_calibrated = b.calibration_error < CALIBRATION_THRESHOLD

    # Compute overall stats
    brier = brier_score(brier_predictions)
    mean_cal_error = 0.0
    if total_resolved > 0:
        weighted_errors = sum(
            b.calibration_error * (b.hits + b.misses) for b in buckets
        )
        mean_cal_error = weighted_errors / total_resolved

    overall = {
        "total_predictions": sum(b.predictions for b in buckets),
        "total_resolved": total_resolved,
        "total_hits": total_hits,
        "total_misses": total_misses,
        "hit_rate": round(total_hits / total_resolved, 4) if total_resolved > 0 else 0.0,
        "brier_score": round(brier, 4) if brier is not None else None,
        "mean_calibration_error": round(mean_cal_error, 4),
        "is_well_calibrated": mean_cal_error < CALIBRATION_THRESHOLD,
    }

    insufficient = total_resolved < 3

    return CalibrationReport(
        prediction_type=prediction_type,
        buckets=buckets,
        overall=overall,
        insufficient_evidence=insufficient,
    )


def is_well_calibrated(report: CalibrationReport) -> bool:
    """Shared predicate: is this calibration report well-calibrated?

    Per the CEO audit directive, this replaces the dead `brier_score < 0.3`
    check in GovernanceGate and the `mean_calibration_error < 0.1` check
    in CalibrationEngine with one shared predicate.

    A report is well-calibrated if:
      1. It has sufficient evidence (≥3 resolved predictions)
      2. Mean calibration error < 0.1
      3. Brier score < 0.3 (if available)
    """
    if report.insufficient_evidence:
        return False
    if not report.overall.get("is_well_calibrated", False):
        return False
    brier = report.overall.get("brier_score")
    if brier is not None and brier >= BRIER_WELL_CALIBRATED:
        return False
    return True

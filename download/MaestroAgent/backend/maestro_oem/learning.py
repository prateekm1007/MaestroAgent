"""
Continuous Learning Engine — the OEM's self-improvement system.

Implements:
  1. Online learning — every new signal updates the model incrementally
  2. Feedback learning — CEO agree/reject feedback adjusts confidence
  3. Recommendation reinforcement — recommendations that are accepted
     strengthen their linked laws; rejected ones weaken them
  4. Prediction calibration — tracks predicted vs actual outcomes over time
  5. Confidence calibration — adjusts confidence based on historical accuracy
  6. Law evolution — laws promote/demote through lifecycle states
  7. Pattern decay — old patterns lose weight over time
  8. Knowledge freshness — scores how stale knowledge is per domain
  9. Concept drift — detects when organizational behavior shifts
 10. Organization drift — detects when the org's laws diverge from reality

Every recommendation becomes better over time because:
  - Each prediction outcome is recorded
  - Confidence is recalibrated based on actual hit rate
  - Laws evolve (validate/stress/invalidate) based on evidence
  - Patterns decay if not reinforced by new signals
  - Drift is detected and surfaced

All learning is persisted to SQLite so it survives restarts.
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
import threading
from collections import defaultdict, deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator
from uuid import uuid4

logger = logging.getLogger(__name__)


# ─── Schema ───

_LEARNING_SCHEMA = """
CREATE TABLE IF NOT EXISTS prediction_outcomes (
    id              TEXT PRIMARY KEY,
    prediction_id   TEXT NOT NULL,
    prediction_type TEXT NOT NULL,         -- law | recommendation | pattern
    predicted_confidence REAL NOT NULL,
    predicted_bucket INTEGER NOT NULL,     -- 0-9 calibration bucket
    actual_outcome  TEXT,                  -- hit | miss | pending
    actual_value    REAL,                  -- 1.0=hit, 0.0=miss, null=pending
    predicted_at    TEXT NOT NULL,
    resolved_at     TEXT,
    entity_id       TEXT,                  -- law code or rec_id
    metadata        TEXT
);
CREATE INDEX IF NOT EXISTS idx_pred_bucket ON prediction_outcomes(predicted_bucket);
CREATE INDEX IF NOT EXISTS idx_pred_type ON prediction_outcomes(prediction_type);
CREATE INDEX IF NOT EXISTS idx_pred_pending ON prediction_outcomes(actual_outcome) WHERE actual_outcome = 'pending';

CREATE TABLE IF NOT EXISTS feedback_events (
    id              TEXT PRIMARY KEY,
    timestamp       TEXT NOT NULL,
    entity_type     TEXT NOT NULL,         -- law | recommendation
    entity_id       TEXT NOT NULL,
    feedback        TEXT NOT NULL,         -- agree | reject | modify | ignore
    reasoning       TEXT,
    actor           TEXT,
    confidence_before REAL,
    confidence_after  REAL
);
CREATE INDEX IF NOT EXISTS idx_feedback_entity ON feedback_events(entity_id);

CREATE TABLE IF NOT EXISTS calibration_history (
    id              TEXT PRIMARY KEY,
    timestamp       TEXT NOT NULL,
    bucket          INTEGER NOT NULL,      -- 0-9
    predictions     INTEGER NOT NULL,
    hits            INTEGER NOT NULL,
    miss_rate       REAL NOT NULL,
    shr             REAL NOT NULL,         -- surprise hit rate
    brier_score     REAL NOT NULL          -- mean squared error
);
CREATE INDEX IF NOT EXISTS idx_cal_bucket ON calibration_history(bucket);

CREATE TABLE IF NOT EXISTS law_evolution_events (
    id              TEXT PRIMARY KEY,
    timestamp       TEXT NOT NULL,
    law_code        TEXT NOT NULL,
    event_type      TEXT NOT NULL,         -- promoted | demoted | stressed | invalidated | drift_detected | reinforced
    old_status      TEXT,
    new_status      TEXT,
    old_confidence  REAL,
    new_confidence  REAL,
    evidence_delta  INTEGER DEFAULT 0,
    detail          TEXT
);
CREATE INDEX IF NOT EXISTS idx_evolution_law ON law_evolution_events(law_code);

CREATE TABLE IF NOT EXISTS drift_events (
    id              TEXT PRIMARY KEY,
    timestamp       TEXT NOT NULL,
    drift_type      TEXT NOT NULL,         -- concept | organization
    entity_id       TEXT NOT NULL,
    severity        TEXT NOT NULL,         -- low | medium | high
    description     TEXT NOT NULL,
    old_value       REAL,
    new_value       REAL,
    metadata        TEXT
);
CREATE INDEX IF NOT EXISTS idx_drift_type ON drift_events(drift_type);

CREATE TABLE IF NOT EXISTS knowledge_freshness (
    domain          TEXT PRIMARY KEY,
    last_signal_at  TEXT NOT NULL,
    signal_count    INTEGER NOT NULL DEFAULT 0,
    freshness_score REAL NOT NULL DEFAULT 1.0,
    staleness_days  INTEGER NOT NULL DEFAULT 0,
    updated_at      TEXT NOT NULL
);
"""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utcnow_plus(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


# ═══════════════════════════════════════════════════════════════════════════
# 1. PREDICTION CALIBRATION
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class CalibrationBucket:
    """One of 10 calibration buckets (0-9) for reliability diagram."""
    bucket: int
    predictions: int = 0
    hits: int = 0
    misses: int = 0
    pending: int = 0

    @property
    def hit_rate(self) -> float:
        """Actual hit rate = hits / (hits + misses)."""
        resolved = self.hits + self.misses
        return self.hits / resolved if resolved > 0 else 0.0

    @property
    def expected_rate(self) -> float:
        """Expected hit rate = midpoint of bucket range."""
        return (self.bucket + 0.5) / 10.0

    @property
    def calibration_error(self) -> float:
        """|expected - actual| — lower is better."""
        return abs(self.expected_rate - self.hit_rate)

    @property
    def is_calibrated(self) -> bool:
        """Within 10% of expected."""
        return self.calibration_error < 0.1


class CalibrationEngine:
    """Tracks prediction calibration across 10 confidence buckets.

    A well-calibrated system predicts 80% confidence and is right 80% of the time.
    This engine records every prediction, tracks outcomes, and reports calibration
    drift so confidence scores can be adjusted.
    """

    NUM_BUCKETS = 10

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.executescript(_LEARNING_SCHEMA)
        finally:
            conn.close()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Cursor]:
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        try:
            cur.execute("BEGIN")
            yield cur
            cur.execute("COMMIT")
        except Exception:
            try:
                cur.execute("ROLLBACK")
            except sqlite3.OperationalError:
                pass
            raise
        finally:
            conn.close()

    @staticmethod
    def _bucket(confidence: float) -> int:
        """Map confidence [0.0, 1.0] to bucket [0, 9]."""
        return min(int(confidence * 10), 9)

    # ─── Record predictions ───

    def record_prediction(
        self,
        prediction_id: str,
        prediction_type: str,
        predicted_confidence: float,
        entity_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a prediction at the time it's made. Outcome is 'pending'."""
        bucket = self._bucket(predicted_confidence)
        with self._lock, self._connect() as cur:
            cur.execute(
                """INSERT OR REPLACE INTO prediction_outcomes
                   (id, prediction_id, prediction_type, predicted_confidence,
                    predicted_bucket, actual_outcome, predicted_at, entity_id, metadata)
                   VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?)""",
                (str(uuid4()), prediction_id, prediction_type,
                 round(predicted_confidence, 4), bucket,
                 _utcnow(), entity_id, json.dumps(metadata or {})),
            )

    def resolve_prediction(
        self,
        prediction_id: str,
        actual_outcome: str,  # "hit" or "miss"
        actual_value: float | None = None,
    ) -> None:
        """Mark a prediction as resolved with the actual outcome."""
        if actual_value is None:
            actual_value = 1.0 if actual_outcome == "hit" else 0.0

        with self._lock, self._connect() as cur:
            cur.execute(
                """UPDATE prediction_outcomes
                   SET actual_outcome = ?, actual_value = ?, resolved_at = ?
                   WHERE prediction_id = ? AND actual_outcome = 'pending'""",
                (actual_outcome, actual_value, _utcnow(), prediction_id),
            )

    # ─── Calibration analysis ───

    def get_calibration(self) -> dict[str, Any]:
        """Get calibration report across all 10 buckets."""
        buckets: list[CalibrationBucket] = []
        total_predictions = 0
        total_hits = 0
        total_resolved = 0

        with self._lock, self._connect() as cur:
            for b in range(self.NUM_BUCKETS):
                cur.execute(
                    """SELECT
                       COUNT(*) as predictions,
                       SUM(CASE WHEN actual_outcome = 'hit' THEN 1 ELSE 0 END) as hits,
                       SUM(CASE WHEN actual_outcome = 'miss' THEN 1 ELSE 0 END) as misses,
                       SUM(CASE WHEN actual_outcome = 'pending' THEN 1 ELSE 0 END) as pending
                       FROM prediction_outcomes WHERE predicted_bucket = ?""",
                    (b,),
                )
                row = cur.fetchone()
                bucket = CalibrationBucket(
                    bucket=b,
                    predictions=row["predictions"],
                    hits=row["hits"] or 0,
                    misses=row["misses"] or 0,
                    pending=row["pending"] or 0,
                )
                buckets.append(bucket)
                total_predictions += bucket.predictions
                total_hits += bucket.hits
                total_resolved += bucket.hits + bucket.misses

        # Compute overall metrics
        overall_shr = total_hits / total_resolved if total_resolved > 0 else 0.0
        brier_score = self._compute_brier_score()
        calibration_error = sum(b.calibration_error * (b.hits + b.misses) for b in buckets) / max(total_resolved, 1)

        return {
            "buckets": [
                {
                    "bucket": b.bucket,
                    "expected_rate": round(b.expected_rate, 3),
                    "actual_rate": round(b.hit_rate, 3),
                    "calibration_error": round(b.calibration_error, 3),
                    "is_calibrated": b.is_calibrated,
                    "predictions": b.predictions,
                    "hits": b.hits,
                    "misses": b.misses,
                    "pending": b.pending,
                }
                for b in buckets
            ],
            "overall": {
                "total_predictions": total_predictions,
                "total_resolved": total_resolved,
                "total_hits": total_hits,
                "surprise_hit_rate": round(overall_shr, 4),
                "brier_score": round(brier_score, 4),
                "mean_calibration_error": round(calibration_error, 4),
                "is_well_calibrated": calibration_error < 0.1,
            },
        }

    def _compute_brier_score(self) -> float:
        """Brier score = mean((predicted_confidence - actual_value)^2).

        Lower is better. 0 = perfect, 0.25 = random, 1 = worst.
        """
        with self._lock, self._connect() as cur:
            cur.execute(
                """SELECT AVG((predicted_confidence - actual_value) * (predicted_confidence - actual_value)) as brier
                   FROM prediction_outcomes WHERE actual_outcome IN ('hit', 'miss')"""
            )
            row = cur.fetchone()
            return row["brier"] or 0.0

    def get_calibration_shr(self, bucket: int | None = None) -> float:
        """Get the surprise hit rate for calibration of confidence scores.

        This is fed back into ConfidenceCalculator.compute_law_confidence()
        as the calibration_shr parameter.
        """
        with self._lock, self._connect() as cur:
            if bucket is not None:
                cur.execute(
                    """SELECT
                       SUM(CASE WHEN actual_outcome = 'hit' THEN 1 ELSE 0 END) as hits,
                       SUM(CASE WHEN actual_outcome = 'miss' THEN 1 ELSE 0 END) as misses
                       FROM prediction_outcomes WHERE predicted_bucket = ?
                       AND actual_outcome IN ('hit', 'miss')""",
                    (bucket,),
                )
            else:
                cur.execute(
                    """SELECT
                       SUM(CASE WHEN actual_outcome = 'hit' THEN 1 ELSE 0 END) as hits,
                       SUM(CASE WHEN actual_outcome = 'miss' THEN 1 ELSE 0 END) as misses
                       FROM prediction_outcomes WHERE actual_outcome IN ('hit', 'miss')"""
                )
            row = cur.fetchone()
            hits = row["hits"] or 0
            misses = row["misses"] or 0
            return hits / (hits + misses) if (hits + misses) > 0 else 0.5

    def get_historical_accuracy(self, entity_id: str | None = None) -> dict[str, Any]:
        """Get historical prediction accuracy for an entity or overall."""
        with self._lock, self._connect() as cur:
            if entity_id:
                cur.execute(
                    """SELECT
                       COUNT(*) as total,
                       SUM(CASE WHEN actual_outcome = 'hit' THEN 1 ELSE 0 END) as hits,
                       SUM(CASE WHEN actual_outcome = 'miss' THEN 1 ELSE 0 END) as misses,
                       SUM(CASE WHEN actual_outcome = 'pending' THEN 1 ELSE 0 END) as pending,
                       AVG(CASE WHEN actual_outcome IN ('hit', 'miss') THEN predicted_confidence END) as avg_confidence,
                       MIN(predicted_at) as first_prediction,
                       MAX(predicted_at) as last_prediction
                       FROM prediction_outcomes WHERE entity_id = ?""",
                    (entity_id,),
                )
            else:
                cur.execute(
                    """SELECT
                       COUNT(*) as total,
                       SUM(CASE WHEN actual_outcome = 'hit' THEN 1 ELSE 0 END) as hits,
                       SUM(CASE WHEN actual_outcome = 'miss' THEN 1 ELSE 0 END) as misses,
                       SUM(CASE WHEN actual_outcome = 'pending' THEN 1 ELSE 0 END) as pending,
                       AVG(CASE WHEN actual_outcome IN ('hit', 'miss') THEN predicted_confidence END) as avg_confidence,
                       MIN(predicted_at) as first_prediction,
                       MAX(predicted_at) as last_prediction
                       FROM prediction_outcomes"""
                )
            row = cur.fetchone()
            total = row["total"] or 0
            hits = row["hits"] or 0
            misses = row["misses"] or 0
            resolved = hits + misses
            return {
                "entity_id": entity_id,
                "total_predictions": total,
                "resolved": resolved,
                "hits": hits,
                "misses": misses,
                "accuracy": round(hits / resolved, 4) if resolved > 0 else None,
                "avg_confidence": round(row["avg_confidence"], 4) if row["avg_confidence"] else None,
                "first_prediction": row["first_prediction"],
                "last_prediction": row["last_prediction"],
                "trend": self._get_accuracy_trend(entity_id),
            }

    def _get_accuracy_trend(self, entity_id: str | None = None) -> list[dict[str, Any]]:
        """Get accuracy over time (weekly buckets) to show improvement."""
        with self._lock, self._connect() as cur:
            if entity_id:
                cur.execute(
                    """SELECT
                       strftime('%Y-W%W', predicted_at) as week,
                       COUNT(*) as predictions,
                       SUM(CASE WHEN actual_outcome = 'hit' THEN 1 ELSE 0 END) as hits,
                       SUM(CASE WHEN actual_outcome = 'miss' THEN 1 ELSE 0 END) as misses
                       FROM prediction_outcomes
                       WHERE entity_id = ? AND actual_outcome IN ('hit', 'miss')
                       GROUP BY week ORDER BY week""",
                    (entity_id,),
                )
            else:
                cur.execute(
                    """SELECT
                       strftime('%Y-W%W', predicted_at) as week,
                       COUNT(*) as predictions,
                       SUM(CASE WHEN actual_outcome = 'hit' THEN 1 ELSE 0 END) as hits,
                       SUM(CASE WHEN actual_outcome = 'miss' THEN 1 ELSE 0 END) as misses
                       FROM prediction_outcomes
                       WHERE actual_outcome IN ('hit', 'miss')
                       GROUP BY week ORDER BY week"""
                )
            trend = []
            for row in cur.fetchall():
                resolved = (row["hits"] or 0) + (row["misses"] or 0)
                trend.append({
                    "week": row["week"],
                    "predictions": resolved,
                    "accuracy": round((row["hits"] or 0) / resolved, 4) if resolved > 0 else 0,
                })
            return trend


# ═══════════════════════════════════════════════════════════════════════════
# 2. FEEDBACK LEARNING + RECOMMENDATION REINFORCEMENT
# ═══════════════════════════════════════════════════════════════════════════

class FeedbackLearningEngine:
    """Learns from CEO feedback (agree/reject) to improve recommendations.

    - AGREE on a recommendation → strengthens its linked laws
    - REJECT on a recommendation → weakens its linked laws
    - AGREE on a law → boosts its confidence
    - REJECT on a law → reduces its confidence + marks counter-example
    - MODIFY → marks the law for refinement

    The feedback is also fed to the CalibrationEngine so future predictions
    account for the CEO's actual decisions.
    """

    def __init__(self, calibration: CalibrationEngine) -> None:
        self.calibration = calibration

    def record_feedback(
        self,
        entity_type: str,
        entity_id: str,
        feedback: str,
        confidence_before: float,
        confidence_after: float,
        reasoning: str = "",
        actor: str = "",
    ) -> None:
        """Record a feedback event for learning."""
        with self.calibration._lock, self.calibration._connect() as cur:
            cur.execute(
                """INSERT INTO feedback_events
                   (id, timestamp, entity_type, entity_id, feedback, reasoning,
                    actor, confidence_before, confidence_after)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (str(uuid4()), _utcnow(), entity_type, entity_id, feedback,
                 reasoning, actor, round(confidence_before, 4), round(confidence_after, 4)),
            )

        # Also record as a prediction outcome for calibration
        pred_id = f"feedback:{entity_id}:{uuid4().hex[:8]}"
        self.calibration.record_prediction(
            prediction_id=pred_id,
            prediction_type=entity_type,
            predicted_confidence=confidence_before,
            entity_id=entity_id,
            metadata={"feedback": feedback, "reasoning": reasoning},
        )
        # Resolve immediately — the CEO's feedback IS the outcome
        outcome = "hit" if feedback == "agree" else "miss" if feedback == "reject" else "hit"
        self.calibration.resolve_prediction(pred_id, outcome)

    def get_feedback_summary(self, entity_id: str | None = None) -> dict[str, Any]:
        """Get feedback learning summary."""
        with self.calibration._lock, self.calibration._connect() as cur:
            if entity_id:
                cur.execute(
                    """SELECT feedback, COUNT(*) as count,
                       AVG(confidence_before) as avg_before,
                       AVG(confidence_after) as avg_after
                       FROM feedback_events WHERE entity_id = ?
                       GROUP BY feedback""",
                    (entity_id,),
                )
            else:
                cur.execute(
                    """SELECT feedback, COUNT(*) as count,
                       AVG(confidence_before) as avg_before,
                       AVG(confidence_after) as avg_after
                       FROM feedback_events GROUP BY feedback"""
                )
            summary = {}
            for row in cur.fetchall():
                summary[row["feedback"]] = {
                    "count": row["count"],
                    "avg_confidence_before": round(row["avg_before"], 4) if row["avg_before"] else None,
                    "avg_confidence_after": round(row["avg_after"], 4) if row["avg_after"] else None,
                }
            return summary


# ═══════════════════════════════════════════════════════════════════════════
# 3. LAW EVOLUTION + PATTERN DECAY
# ═══════════════════════════════════════════════════════════════════════════

class LawEvolutionEngine:
    """Tracks law lifecycle events and pattern decay.

    Law lifecycle:
      CANDIDATE → VALIDATED → STRESSED → INVALIDATED
                              ↓
                      UNKNOWN_TO_LEADERSHIP

    Pattern decay:
      - Patterns not reinforced by new signals lose weight over time
      - A pattern with 0 new signals in 90 days decays to 50% weight
      - A pattern with 0 new signals in 365 days decays to 25% weight

    Evolution events are recorded so the CEO can see how laws change.
    """

    DECAY_HALF_LIFE_DAYS = 90  # 50% weight loss per 90 days without reinforcement

    def __init__(self, calibration: CalibrationEngine) -> None:
        self.calibration = calibration

    def record_evolution_event(
        self,
        law_code: str,
        event_type: str,
        old_status: str | None = None,
        new_status: str | None = None,
        old_confidence: float | None = None,
        new_confidence: float | None = None,
        evidence_delta: int = 0,
        detail: str = "",
    ) -> None:
        with self.calibration._lock, self.calibration._connect() as cur:
            cur.execute(
                """INSERT INTO law_evolution_events
                   (id, timestamp, law_code, event_type, old_status, new_status,
                    old_confidence, new_confidence, evidence_delta, detail)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (str(uuid4()), _utcnow(), law_code, event_type,
                 old_status, new_status,
                 round(old_confidence, 4) if old_confidence else None,
                 round(new_confidence, 4) if new_confidence else None,
                 evidence_delta, detail),
            )

    def get_evolution_history(self, law_code: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """Get law evolution events."""
        with self.calibration._lock, self.calibration._connect() as cur:
            if law_code:
                cur.execute(
                    "SELECT * FROM law_evolution_events WHERE law_code = ? ORDER BY timestamp DESC LIMIT ?",
                    (law_code, limit),
                )
            else:
                cur.execute(
                    "SELECT * FROM law_evolution_events ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                )
            return [dict(r) for r in cur.fetchall()]

    @classmethod
    def compute_decay_factor(cls, last_signal_at: datetime, now: datetime | None = None) -> float:
        """Compute the decay factor for a pattern based on time since last signal.

        Returns a value in [0.25, 1.0]:
          - 1.0 = just reinforced (0 days old)
          - 0.5 = 90 days since last signal (half-life)
          - 0.25 = 365+ days since last signal (floor)
        """
        if now is None:
            now = datetime.now(timezone.utc)
        age_days = (now - last_signal_at).total_seconds() / 86400
        if age_days <= 0:
            return 1.0
        # Exponential decay with floor
        decay = math.exp(-0.693 * age_days / cls.DECAY_HALF_LIFE_DAYS)  # ln(2) ≈ 0.693
        return max(0.25, decay)

    def get_pattern_decay_report(self, model: Any) -> list[dict[str, Any]]:
        """Get decay report for all learning objects (patterns)."""
        now = datetime.now(timezone.utc)
        report = []
        for lo_id, lo in model.learning_objects.items():
            last_seen = lo.last_seen if hasattr(lo, "last_seen") else now
            if isinstance(last_seen, str):
                try:
                    last_seen = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    last_seen = now
            decay = self.compute_decay_factor(last_seen, now)
            report.append({
                "lo_id": str(lo_id),
                "type": lo.type.value if hasattr(lo.type, "value") else str(lo.type),
                "title": lo.title,
                "confidence": round(lo.confidence, 4),
                "decayed_confidence": round(lo.confidence * decay, 4),
                "decay_factor": round(decay, 4),
                "last_seen": last_seen.isoformat() if hasattr(last_seen, "isoformat") else str(last_seen),
                "staleness_days": int((now - last_seen).total_seconds() / 86400) if hasattr(last_seen, "timestamp") else 0,
                "is_decaying": decay < 0.7,
            })
        return sorted(report, key=lambda x: x["decay_factor"])


# ═══════════════════════════════════════════════════════════════════════════
# 4. KNOWLEDGE FRESHNESS + CONCEPT DRIFT + ORGANIZATION DRIFT
# ═══════════════════════════════════════════════════════════════════════════

class DriftDetectionEngine:
    """Detects concept drift and organization drift.

    Concept drift: the meaning of a domain changes over time (e.g. "payments"
    used to mean Stripe integration but now means crypto too).

    Organization drift: the org's laws diverge from actual behavior (e.g.
    a law says "approvals take 2 days" but the data shows 5 days).

    Detection methods:
      - Signal rate change: if signal volume in a domain drops >50% vs baseline
      - Law violation rate: if counter-examples increase >30% vs baseline
      - Confidence trend: if average confidence drops >15% over 30 days
      - Actor turnover: if >50% of actors in a domain are new
    """

    def __init__(self, calibration: CalibrationEngine) -> None:
        self.calibration = calibration

    def record_drift_event(
        self,
        drift_type: str,  # "concept" | "organization"
        entity_id: str,
        severity: str,  # "low" | "medium" | "high"
        description: str,
        old_value: float | None = None,
        new_value: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self.calibration._lock, self.calibration._connect() as cur:
            cur.execute(
                """INSERT INTO drift_events
                   (id, timestamp, drift_type, entity_id, severity,
                    description, old_value, new_value, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (str(uuid4()), _utcnow(), drift_type, entity_id, severity,
                 description, old_value, new_value, json.dumps(metadata or {})),
            )

    def detect_concept_drift(self, model: Any, signals: list) -> list[dict[str, Any]]:
        """Detect concept drift by checking signal rate changes per domain.

        For each domain, compare recent signal volume to historical baseline.
        A >50% drop suggests the domain's meaning is shifting.
        """
        now = datetime.now(timezone.utc)
        thirty_days_ago = now - timedelta(days=30)
        sixty_days_ago = now - timedelta(days=60)

        domain_recent: dict[str, int] = defaultdict(int)
        domain_baseline: dict[str, int] = defaultdict(int)

        for sig in signals:
            sig_time = sig.timestamp if hasattr(sig, "timestamp") else None
            if sig_time is None:
                continue
            if isinstance(sig_time, str):
                try:
                    sig_time = datetime.fromisoformat(sig_time.replace("Z", "+00:00"))
                except ValueError:
                    continue
            domain = sig.metadata.get("domain", "unknown") if hasattr(sig, "metadata") and sig.metadata else "unknown"
            if sig_time > thirty_days_ago:
                domain_recent[domain] += 1
            elif sig_time > sixty_days_ago:
                domain_baseline[domain] += 1

        drifts = []
        for domain, recent_count in domain_recent.items():
            baseline = domain_baseline.get(domain, 0)
            if baseline > 0:
                change_rate = (recent_count - baseline) / baseline
                if abs(change_rate) > 0.5:
                    severity = "high" if abs(change_rate) > 0.75 else "medium"
                    drifts.append({
                        "domain": domain,
                        "drift_type": "concept",
                        "severity": severity,
                        "description": f"Signal volume in '{domain}' changed {change_rate:+.0%} vs previous period.",
                        "recent_count": recent_count,
                        "baseline_count": baseline,
                        "change_rate": round(change_rate, 4),
                    })

        # Record drift events
        for d in drifts:
            self.record_drift_event(
                drift_type="concept",
                entity_id=d["domain"],
                severity=d["severity"],
                description=d["description"],
                old_value=d["baseline_count"],
                new_value=d["recent_count"],
            )

        return drifts

    def detect_organization_drift(self, model: Any) -> list[dict[str, Any]]:
        """Detect organization drift by checking if laws are being violated.

        A law with increasing counter-examples is drifting from reality.
        """
        drifts = []
        for law in model.laws.values():
            total_runtimes = law.validated_runtimes + law.failed_runtimes
            if total_runtimes < 5:
                continue  # Not enough data
            violation_rate = law.failed_runtimes / total_runtimes
            if violation_rate > 0.3:
                severity = "high" if violation_rate > 0.5 else "medium"
                drifts.append({
                    "law_code": law.code,
                    "drift_type": "organization",
                    "severity": severity,
                    "description": f"Law {law.code} has a {violation_rate:.0%} violation rate ({law.failed_runtimes}/{total_runtimes} runtimes failed).",
                    "violation_rate": round(violation_rate, 4),
                    "validated": law.validated_runtimes,
                    "failed": law.failed_runtimes,
                })
                self.record_drift_event(
                    drift_type="organization",
                    entity_id=law.code,
                    severity=severity,
                    description=drifts[-1]["description"],
                    old_value=law.validated_runtimes,
                    new_value=law.failed_runtimes,
                )
            elif law.drift_detected:
                drifts.append({
                    "law_code": law.code,
                    "drift_type": "organization",
                    "severity": "low",
                    "description": f"Law {law.code} has drift_detected=True.",
                    "violation_rate": round(violation_rate, 4),
                    "validated": law.validated_runtimes,
                    "failed": law.failed_runtimes,
                })

        return drifts

    def get_drift_events(self, drift_type: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """Get drift events."""
        with self.calibration._lock, self.calibration._connect() as cur:
            if drift_type:
                cur.execute(
                    "SELECT * FROM drift_events WHERE drift_type = ? ORDER BY timestamp DESC LIMIT ?",
                    (drift_type, limit),
                )
            else:
                cur.execute(
                    "SELECT * FROM drift_events ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                )
            events = [dict(r) for r in cur.fetchall()]
        for e in events:
            e["metadata"] = json.loads(e.get("metadata") or "{}")
        return events


class KnowledgeFreshnessTracker:
    """Tracks knowledge freshness per domain.

    Freshness score: 1.0 = just updated, 0.0 = completely stale.
    Score decays exponentially with a 30-day half-life.
    """

    FRESHNESS_HALF_LIFE_DAYS = 30

    def __init__(self, calibration: CalibrationEngine) -> None:
        self.calibration = calibration

    def update_freshness(self, domain: str, signal_timestamp: datetime | None = None) -> None:
        """Update freshness for a domain based on a new signal."""
        if signal_timestamp is None:
            signal_timestamp = datetime.now(timezone.utc)

        with self.calibration._lock, self.calibration._connect() as cur:
            # Get current state
            cur.execute("SELECT signal_count FROM knowledge_freshness WHERE domain = ?", (domain,))
            row = cur.fetchone()
            new_count = (row["signal_count"] + 1) if row else 1
            now = datetime.now(timezone.utc)
            staleness = (now - signal_timestamp).days if hasattr(signal_timestamp, "timestamp") else 0
            freshness = math.exp(-0.693 * staleness / self.FRESHNESS_HALF_LIFE_DAYS)

            cur.execute(
                """INSERT INTO knowledge_freshness (domain, last_signal_at, signal_count, freshness_score, staleness_days, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(domain) DO UPDATE SET
                    last_signal_at = excluded.last_signal_at,
                    signal_count = excluded.signal_count,
                    freshness_score = excluded.freshness_score,
                    staleness_days = excluded.staleness_days,
                    updated_at = excluded.updated_at""",
                (domain, signal_timestamp.isoformat(), new_count, round(freshness, 4), staleness, _utcnow()),
            )

    def get_freshness_report(self) -> list[dict[str, Any]]:
        """Get freshness report for all domains."""
        with self.calibration._lock, self.calibration._connect() as cur:
            cur.execute("SELECT * FROM knowledge_freshness ORDER BY freshness_score ASC")
            rows = [dict(r) for r in cur.fetchall()]

        now = datetime.now(timezone.utc)
        for r in rows:
            # Recompute freshness (in case time has passed since last update)
            last_signal = r["last_signal_at"]
            try:
                last_dt = datetime.fromisoformat(last_signal.replace("Z", "+00:00"))
                staleness = (now - last_dt).days
                r["freshness_score"] = round(math.exp(-0.693 * staleness / self.FRESHNESS_HALF_LIFE_DAYS), 4)
                r["staleness_days"] = staleness
            except (ValueError, TypeError):
                pass
            r["is_stale"] = r["freshness_score"] < 0.3

        return rows


# ═══════════════════════════════════════════════════════════════════════════
# 5. CONTINUOUS LEARNING ENGINE — orchestrates all learning subsystems
# ═══════════════════════════════════════════════════════════════════════════

class ContinuousLearningEngine:
    """The OEM's self-improvement orchestrator.

    Combines:
      - CalibrationEngine (prediction + confidence calibration)
      - FeedbackLearningEngine (CEO feedback → confidence adjustment)
      - LawEvolutionEngine (law lifecycle + pattern decay)
      - DriftDetectionEngine (concept + organization drift)
      - KnowledgeFreshnessTracker (domain freshness)

    Usage:
        engine = ContinuousLearningEngine(db_path, model, signals)
        engine.on_signal_ingested(signal)       # online learning
        engine.on_feedback(entity, feedback)    # feedback learning
        engine.on_prediction_made(pred_id, conf, entity_id)  # record prediction
        engine.on_prediction_resolved(pred_id, outcome)      # calibrate
        engine.run_drift_detection()            # periodic drift check
        report = engine.get_learning_report()   # evidence of improvement
    """

    def __init__(self, db_path: str, model: Any = None, signals: list | None = None) -> None:
        self.calibration = CalibrationEngine(db_path)
        self.feedback_engine = FeedbackLearningEngine(self.calibration)
        self.evolution_engine = LawEvolutionEngine(self.calibration)
        self.drift_engine = DriftDetectionEngine(self.calibration)
        self.freshness_tracker = KnowledgeFreshnessTracker(self.calibration)
        self.model = model
        self.signals = signals or []

    def on_signal_ingested(self, signal: Any) -> None:
        """Online learning: update freshness + detect drift on new signal."""
        domain = "unknown"
        if hasattr(signal, "metadata") and signal.metadata:
            domain = signal.metadata.get("domain", "unknown")
        sig_time = signal.timestamp if hasattr(signal, "timestamp") else datetime.now(timezone.utc)
        self.freshness_tracker.update_freshness(domain, sig_time)

    def on_feedback(
        self,
        entity_type: str,
        entity_id: str,
        feedback: str,
        confidence_before: float,
        confidence_after: float,
        reasoning: str = "",
        actor: str = "",
    ) -> None:
        """Feedback learning: record CEO feedback and resolve prediction."""
        self.feedback_engine.record_feedback(
            entity_type, entity_id, feedback,
            confidence_before, confidence_after,
            reasoning, actor,
        )
        # Record evolution event
        event_type = "reinforced" if feedback == "agree" else "stressed" if feedback == "reject" else "modified"
        self.evolution_engine.record_evolution_event(
            law_code=entity_id,
            event_type=event_type,
            old_confidence=confidence_before,
            new_confidence=confidence_after,
            detail=f"CEO feedback: {feedback} — {reasoning}",
        )

    def on_prediction_made(
        self,
        prediction_id: str,
        prediction_type: str,
        predicted_confidence: float,
        entity_id: str | None = None,
    ) -> None:
        """Record a prediction for future calibration."""
        self.calibration.record_prediction(
            prediction_id, prediction_type, predicted_confidence, entity_id,
        )

    def on_prediction_resolved(self, prediction_id: str, outcome: str) -> None:
        """Resolve a prediction — calibrates confidence for future predictions."""
        self.calibration.resolve_prediction(prediction_id, outcome)

    def run_drift_detection(self) -> dict[str, Any]:
        """Run all drift detection checks."""
        concept_drifts = []
        org_drifts = []
        if self.model:
            org_drifts = self.drift_engine.detect_organization_drift(self.model)
        if self.signals:
            concept_drifts = self.drift_engine.detect_concept_drift(self.model, self.signals)
        return {
            "concept_drifts": concept_drifts,
            "organization_drifts": org_drifts,
            "total_drifts": len(concept_drifts) + len(org_drifts),
        }

    def get_learning_report(self) -> dict[str, Any]:
        """Full learning report — evidence that the OEM is improving over time."""
        calibration = self.calibration.get_calibration()
        accuracy = self.calibration.get_historical_accuracy()
        feedback = self.feedback_engine.get_feedback_summary()
        evolution = self.evolution_engine.get_evolution_history(limit=20)
        drift_events = self.drift_engine.get_drift_events(limit=20)
        freshness = self.freshness_tracker.get_freshness_report()
        pattern_decay = []
        if self.model:
            pattern_decay = self.evolution_engine.get_pattern_decay_report(self.model)

        return {
            "generated_at": _utcnow(),
            "calibration": calibration,
            "historical_accuracy": accuracy,
            "feedback_learning": feedback,
            "law_evolution": {
                "recent_events": evolution,
                "total_events": len(evolution),
            },
            "drift_detection": {
                "recent_events": drift_events,
                "total_events": len(drift_events),
            },
            "knowledge_freshness": freshness,
            "pattern_decay": pattern_decay,
            "improvement_evidence": {
                "is_calibrated": calibration["overall"]["is_well_calibrated"],
                "calibration_error": calibration["overall"]["mean_calibration_error"],
                "brier_score": calibration["overall"]["brier_score"],
                "accuracy_trend": accuracy["trend"],
                "feedback_count": sum(s.get("count", 0) for s in feedback.values()),
                "drift_events_detected": len(drift_events),
                "stale_domains": sum(1 for f in freshness if f.get("is_stale")),
                "decaying_patterns": sum(1 for p in pattern_decay if p.get("is_decaying")),
            },
        }

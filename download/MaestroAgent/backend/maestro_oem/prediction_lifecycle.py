"""
Prediction Lifecycle Engine — closes the learning loop.

When Maestro surfaces a recommendation → automatically creates a Prediction.
When future signals arrive → automatically resolves predictions.
When predictions resolve → automatically recalibrates confidence.

This is the moat: Maestro proves its recommendations get better over time.

Pipeline:
  1. Recommendation surfaced → PredictionRecorder.create_prediction()
  2. New signals ingested → PredictionResolver.check_pending()
  3. Prediction resolved → CalibrationEngine recalibrates
  4. Recalibrated confidence → affects future recommendations

The PredictionResolver checks if the predicted outcome occurred by
examining new signals for evidence that supports or contradicts the prediction.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator
from uuid import uuid4

logger = logging.getLogger(__name__)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS predictions (
    id                  TEXT PRIMARY KEY,
    prediction_id       TEXT UNIQUE NOT NULL,
    created_at          TEXT NOT NULL,
    organization        TEXT DEFAULT 'default',
    scope               TEXT DEFAULT 'org',
    prediction_type     TEXT NOT NULL,         -- recommendation | risk | simulation | law | autocomplete
    entity_id           TEXT,                  -- law code, rec title, etc.
    recommendation      TEXT,
    expected_outcome    TEXT,
    expected_metric     TEXT,                  -- e.g. 'p1_cluster_risk'
    baseline_value      REAL,
    predicted_value     REAL,
    expected_timeframe  TEXT,                  -- e.g. '7d', '30d'
    expires_at          TEXT,
    linked_receipts     TEXT,                  -- JSON array
    linked_laws         TEXT,                  -- JSON array
    linked_patterns     TEXT,                  -- JSON array
    confidence          REAL NOT NULL,
    decision_quality    TEXT DEFAULT 'medium', -- low | medium | high
    status              TEXT NOT NULL DEFAULT 'pending',  -- pending | correct | incorrect | partially_correct | insufficient_data | expired
    resolved_at         TEXT,
    resolution_evidence TEXT,                  -- JSON
    created_by          TEXT DEFAULT 'system'
);
CREATE INDEX IF NOT EXISTS idx_pred_status ON predictions(status);
CREATE INDEX IF NOT EXISTS idx_pred_entity ON predictions(entity_id);
CREATE INDEX IF NOT EXISTS idx_pred_type ON predictions(prediction_type);
CREATE INDEX IF NOT EXISTS idx_pred_expires ON predictions(expires_at);

CREATE TABLE IF NOT EXISTS confidence_history (
    id                  TEXT PRIMARY KEY,
    timestamp           TEXT NOT NULL,
    entity_type         TEXT NOT NULL,         -- law | recommendation | pattern
    entity_id           TEXT NOT NULL,
    confidence          REAL NOT NULL,
    reason              TEXT,
    prediction_id       TEXT,                  -- linked prediction that triggered this
    source              TEXT DEFAULT 'calibration'  -- calibration | feedback | drift | decay | creation
);
CREATE INDEX IF NOT EXISTS idx_conf_entity ON confidence_history(entity_type, entity_id);
"""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utcnow_plus(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


# ═══════════════════════════════════════════════════════════════════════════
# 1. PREDICTION RECORDER
# ═══════════════════════════════════════════════════════════════════════════

class PredictionRecorder:
    """Creates predictions whenever Maestro surfaces a recommendation, risk,
    simulation, law, or autocomplete suggestion.

    Every prediction has full provenance: linked receipts, laws, patterns.
    No prediction exists without evidence.
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        try:
            conn.executescript(_SCHEMA)
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

    def create_prediction(
        self,
        prediction_type: str,
        entity_id: str,
        recommendation: str,
        expected_outcome: str,
        confidence: float,
        expected_metric: str | None = None,
        baseline_value: float | None = None,
        predicted_value: float | None = None,
        expected_timeframe: str = "30d",
        linked_laws: list[str] | None = None,
        linked_patterns: list[str] | None = None,
        linked_receipts: list[str] | None = None,
        organization: str = "default",
        scope: str = "org",
        decision_quality: str = "medium",
        created_by: str = "system",
    ) -> str:
        """Create a prediction. Returns the prediction_id.

        Called automatically whenever Maestro surfaces a recommendation.
        """
        prediction_id = f"pred-{uuid4().hex[:12]}"

        # Parse timeframe to expiry
        timeframe_seconds = self._parse_timeframe(expected_timeframe)
        expires_at = _utcnow_plus(timeframe_seconds)

        with self._lock, self._connect() as cur:
            cur.execute(
                """INSERT INTO predictions
                   (id, prediction_id, created_at, organization, scope,
                    prediction_type, entity_id, recommendation, expected_outcome,
                    expected_metric, baseline_value, predicted_value,
                    expected_timeframe, expires_at, linked_receipts,
                    linked_laws, linked_patterns, confidence, decision_quality,
                    status, created_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
                (str(uuid4()), prediction_id, _utcnow(), organization, scope,
                 prediction_type, entity_id, recommendation, expected_outcome,
                 expected_metric, baseline_value, predicted_value,
                 expected_timeframe, expires_at,
                 json.dumps(linked_receipts or []),
                 json.dumps(linked_laws or []),
                 json.dumps(linked_patterns or []),
                 round(confidence, 4), decision_quality, created_by),
            )

        logger.info("Created prediction %s (type=%s, entity=%s, confidence=%.4f)",
                     prediction_id, prediction_type, entity_id, confidence)
        return prediction_id

    @staticmethod
    def _parse_timeframe(timeframe: str) -> int:
        """Parse '7d', '30d', '12h', '60m' to seconds."""
        tf = timeframe.lower().strip()
        if tf.endswith('d'):
            return int(tf[:-1]) * 86400
        if tf.endswith('h'):
            return int(tf[:-1]) * 3600
        if tf.endswith('m'):
            return int(tf[:-1]) * 60
        return 30 * 86400  # Default 30 days

    def get_pending_predictions(self) -> list[dict[str, Any]]:
        """Get all pending predictions that need resolution."""
        with self._lock, self._connect() as cur:
            cur.execute(
                "SELECT * FROM predictions WHERE status = 'pending' ORDER BY created_at"
            )
            return [self._row_to_dict(r) for r in cur.fetchall()]

    def get_prediction(self, prediction_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as cur:
            cur.execute("SELECT * FROM predictions WHERE prediction_id = ?", (prediction_id,))
            row = cur.fetchone()
            return self._row_to_dict(row) if row else None

    def list_predictions(
        self, status: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        with self._lock, self._connect() as cur:
            if status:
                cur.execute(
                    "SELECT * FROM predictions WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, limit),
                )
            else:
                cur.execute(
                    "SELECT * FROM predictions ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                )
            return [self._row_to_dict(r) for r in cur.fetchall()]

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        d["linked_receipts"] = json.loads(d.get("linked_receipts") or "[]")
        d["linked_laws"] = json.loads(d.get("linked_laws") or "[]")
        d["linked_patterns"] = json.loads(d.get("linked_patterns") or "[]")
        d["resolution_evidence"] = json.loads(d.get("resolution_evidence") or "null")
        return d


# ═══════════════════════════════════════════════════════════════════════════
# 2. PREDICTION RESOLVER
# ═══════════════════════════════════════════════════════════════════════════

class PredictionResolver:
    """Resolves pending predictions by examining new signals.

    When new signals arrive, the resolver checks if the predicted outcome
    occurred, partially occurred, or was contradicted.

    Resolution states:
      - correct: predicted outcome occurred
      - incorrect: opposite of prediction occurred
      - partially_correct: some aspects occurred
      - insufficient_data: not enough signals to determine
      - expired: timeframe elapsed without resolution
    """

    def __init__(
        self,
        recorder: PredictionRecorder,
        calibration: Any,
        contradiction_log: Any = None,
    ) -> None:
        self.recorder = recorder
        self.calibration = calibration
        # Shared ContradictionLog (maestro_oem.contradiction.ContradictionLog).
        # When set, the resolver reads CEO feedback (agree/reject/modify) from
        # this log instead of looking for a nonexistent _feedback_index on the
        # calibration engine. This is what closes the loop: feedback submitted
        # via /contradict is visible to check_pending() on the next signal
        # ingest (or the next manual /predictions/resolve call).
        self.contradiction_log = contradiction_log

    def check_pending(self, model: Any, signals: list) -> dict[str, Any]:
        """Check all pending predictions against current model state.

        Called automatically after new signals are ingested.
        Returns summary of resolutions.
        """
        pending = self.recorder.get_pending_predictions()
        now = datetime.now(timezone.utc)
        resolved_count = 0
        expired_count = 0

        for pred in pending:
            # Check expiry first
            expires_at = pred.get("expires_at")
            if expires_at:
                try:
                    exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                    if now > exp_dt:
                        self._resolve(pred, "expired", "Prediction timeframe elapsed without resolution.")
                        expired_count += 1
                        continue
                except (ValueError, TypeError):
                    pass

            # Try to resolve from model state
            outcome = self._evaluate_prediction(pred, model, signals)
            if outcome:
                self._resolve(pred, outcome["status"], outcome["evidence"])
                resolved_count += 1

        return {
            "checked": len(pending),
            "resolved": resolved_count,
            "expired": expired_count,
            "still_pending": len(pending) - resolved_count - expired_count,
        }

    def _evaluate_prediction(
        self, pred: dict[str, Any], model: Any, signals: list
    ) -> dict[str, Any] | None:
        """Evaluate whether a prediction's expected outcome occurred.

        Logic depends on prediction type:
          - recommendation: check if the recommended action was taken
          - risk: check if the risk materialized (metric increased)
          - simulation: check if predicted metric value was close to actual
          - law: check if law was validated or contradicted by new signals
        """
        pred_type = pred.get("prediction_type", "")
        entity_id = pred.get("entity_id", "")
        expected_metric = pred.get("expected_metric")
        predicted_value = pred.get("predicted_value")

        # For recommendations: check if CEO gave feedback (agree/reject/modify)
        # on the recommendation itself OR on any law linked to it.
        if pred_type == "recommendation":
            # Check feedback on the recommendation entity_id (title) and on
            # every linked law. A rejection on a linked law should also
            # resolve the recommendation prediction as incorrect.
            entity_ids_to_check = {entity_id}
            linked_laws = pred.get("linked_laws") or []
            entity_ids_to_check.update(linked_laws)

            total_agree = 0
            total_reject = 0
            total_modify = 0
            for eid in entity_ids_to_check:
                if not eid:
                    continue
                a, r, m = self._count_feedback(str(eid))
                total_agree += a
                total_reject += r
                total_modify += m

            if total_reject > 0 and total_agree == 0:
                return {
                    "status": "incorrect",
                    "evidence": f"CEO rejected ({total_reject} rejections across rec + linked laws).",
                }
            if total_agree > 0 and total_reject == 0:
                return {
                    "status": "correct",
                    "evidence": f"CEO agreed ({total_agree} agreements across rec + linked laws).",
                }
            if total_agree > 0 and total_reject > 0:
                return {
                    "status": "partially_correct",
                    "evidence": f"Mixed feedback: {total_agree} agree, {total_reject} reject.",
                }
            if total_modify > 0:
                return {
                    "status": "partially_correct",
                    "evidence": f"CEO modified ({total_modify} modifications).",
                }

        # For simulations: check if predicted metric was close to actual
        if pred_type == "simulation" and expected_metric and predicted_value is not None:
            actual = self._get_metric_value(model, expected_metric)
            if actual is not None:
                diff = abs(actual - predicted_value)
                threshold = max(0.05, predicted_value * 0.2)  # 20% or 0.05
                if diff < threshold:
                    return {"status": "correct", "evidence": f"Predicted {expected_metric}={predicted_value}, actual={actual}. Within threshold."}
                elif diff < threshold * 2:
                    return {"status": "partially_correct", "evidence": f"Predicted {expected_metric}={predicted_value}, actual={actual}. Partially close."}
                else:
                    return {"status": "incorrect", "evidence": f"Predicted {expected_metric}={predicted_value}, actual={actual}. Outside threshold."}

        # For laws: check if law was validated or contradicted
        if pred_type == "law" and entity_id in getattr(model, "laws", {}):
            law = model.laws[entity_id]
            if law.validated_runtimes > 0 and law.failed_runtimes == 0:
                return {"status": "correct", "evidence": f"Law {entity_id} validated {law.validated_runtimes} times with 0 failures."}
            elif law.failed_runtimes > law.validated_runtimes:
                return {"status": "incorrect", "evidence": f"Law {entity_id} has {law.failed_runtimes} failures vs {law.validated_runtimes} validations."}
            elif law.failed_runtimes > 0:
                return {"status": "partially_correct", "evidence": f"Law {entity_id} has {law.validated_runtimes} validations and {law.failed_runtimes} failures."}

        # For risks: check if risk materialized
        if pred_type == "risk" and expected_metric:
            actual = self._get_metric_value(model, expected_metric)
            baseline = pred.get("baseline_value")
            if actual is not None and baseline is not None:
                if actual > baseline * 1.2:  # Risk materialized (20% increase)
                    return {"status": "correct", "evidence": f"Risk materialized: {expected_metric} went from {baseline} to {actual}."}
                elif actual < baseline * 0.9:  # Risk decreased
                    return {"status": "incorrect", "evidence": f"Risk did not materialize: {expected_metric} went from {baseline} to {actual}."}

        return None  # Insufficient data to resolve

    def _count_feedback(self, entity_id: str) -> tuple[int, int, int]:
        """Count CEO feedback events for an entity from the contradiction log.

        Returns (agree_count, reject_count, modify_count).

        This replaces the old broken lookup that read ``self.calibration._feedback_index``
        — an attribute that only exists on SemanticAutocompleteEngine, not on
        CalibrationEngine. With the contradiction_log wired in, the resolver
        can finally see feedback submitted via /contradict.
        """
        if not self.contradiction_log:
            return (0, 0, 0)
        try:
            from maestro_oem.contradiction import FeedbackAction
            events = self.contradiction_log.get_events_for_target(entity_id)
            agree = sum(1 for e in events if e.action == FeedbackAction.AGREE)
            reject = sum(1 for e in events if e.action == FeedbackAction.REJECT)
            modify = sum(1 for e in events if e.action == FeedbackAction.MODIFY)
            return (agree, reject, modify)
        except Exception as e:
            logger.debug("Feedback count lookup failed for %s: %s", entity_id, e)
            return (0, 0, 0)

    @staticmethod
    def _get_metric_value(model: Any, metric: str) -> float | None:
        """Get a metric value from the model."""
        if metric == "p1_cluster_risk":
            return model.health.p1_cluster_risk
        if metric == "incident_rate":
            return model.health.incident_rate
        if metric == "decision_velocity_days":
            return model.health.decision_velocity_days
        if metric == "release_frequency":
            return model.health.release_frequency
        return None

    def _resolve(self, pred: dict[str, Any], status: str, evidence: str) -> None:
        """Mark a prediction as resolved and update calibration."""
        prediction_id = pred["prediction_id"]
        confidence = pred["confidence"]

        # Update prediction record
        with self.recorder._lock, self.recorder._connect() as cur:
            cur.execute(
                """UPDATE predictions SET status = ?, resolved_at = ?, resolution_evidence = ?
                   WHERE prediction_id = ? AND status = 'pending'""",
                (status, _utcnow(), json.dumps({"evidence": evidence}), prediction_id),
            )

        # Record calibration outcome
        # Map resolution to hit/miss for calibration
        if status == "correct":
            outcome = "hit"
        elif status == "incorrect":
            outcome = "miss"
        elif status == "partially_correct":
            outcome = "hit"  # Count partial as hit for calibration
        else:
            return  # expired/insufficient_data don't calibrate

        self.calibration.record_prediction(
            prediction_id=f"resolution:{prediction_id}",
            prediction_type=pred["prediction_type"],
            predicted_confidence=confidence,
            entity_id=pred.get("entity_id"),
        )
        self.calibration.resolve_prediction(
            prediction_id=f"resolution:{prediction_id}",
            actual_outcome=outcome,
        )

        # Record confidence history
        self._record_confidence_history(
            entity_type=pred["prediction_type"],
            entity_id=pred.get("entity_id", ""),
            confidence=confidence,
            reason=f"Prediction resolved as {status}: {evidence}",
            prediction_id=prediction_id,
            source="calibration",
        )

        logger.info("Resolved prediction %s as %s: %s", prediction_id, status, evidence[:80])

    def _record_confidence_history(
        self, entity_type: str, entity_id: str, confidence: float,
        reason: str, prediction_id: str | None = None, source: str = "calibration"
    ) -> None:
        with self.recorder._lock, self.recorder._connect() as cur:
            cur.execute(
                """INSERT INTO confidence_history
                   (id, timestamp, entity_type, entity_id, confidence, reason, prediction_id, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (str(uuid4()), _utcnow(), entity_type, entity_id,
                 round(confidence, 4), reason, prediction_id, source),
            )

    def expire_old_predictions(self) -> int:
        """Expire all predictions past their expiry date. Returns count."""
        now = _utcnow()
        with self.recorder._lock, self.recorder._connect() as cur:
            cur.execute(
                """UPDATE predictions SET status = 'expired', resolved_at = ?,
                   resolution_evidence = ?
                   WHERE status = 'pending' AND expires_at < ?""",
                (now, json.dumps({"evidence": "Prediction expired without resolution."}), now),
            )
            return cur.rowcount


# ═══════════════════════════════════════════════════════════════════════════
# 3. EXPLAINABLE CONFIDENCE
# ═══════════════════════════════════════════════════════════════════════════

class ExplainableConfidence:
    """Produces human-readable confidence explanations.

    Instead of returning 'confidence: 0.87', returns:
    'Confidence is HIGH because:
      42 similar executions
      37 succeeded
      5 failed
      Prediction calibration error 0.08
      Last validated 3 days ago.'
    """

    def __init__(self, recorder: PredictionRecorder, calibration: Any) -> None:
        self.recorder = recorder
        self.calibration = calibration

    def explain(self, entity_id: str, confidence: float, entity_type: str = "law") -> dict[str, Any]:
        """Produce an explainable confidence report for an entity."""
        # Get historical predictions for this entity
        with self.recorder._lock, self.recorder._connect() as cur:
            cur.execute(
                """SELECT status, COUNT(*) as count FROM predictions
                   WHERE entity_id = ? GROUP BY status""",
                (entity_id,),
            )
            status_counts = {r["status"]: r["count"] for r in cur.fetchall()}

            # Get confidence history
            cur.execute(
                """SELECT confidence, timestamp, reason FROM confidence_history
                   WHERE entity_id = ? ORDER BY timestamp DESC LIMIT 5""",
                (entity_id,),
            )
            history = [dict(r) for r in cur.fetchall()]

        total = sum(status_counts.values())
        correct = status_counts.get("correct", 0)
        incorrect = status_counts.get("incorrect", 0)
        partial = status_counts.get("partially_correct", 0)

        # Get calibration data
        cal_data = self.calibration.get_calibration()
        overall = cal_data.get("overall", {})
        brier = overall.get("brier_score", 0)
        cal_error = overall.get("mean_calibration_error", 0)

        # Determine quality level
        if confidence >= 0.8:
            level = "HIGH"
        elif confidence >= 0.5:
            level = "MEDIUM"
        else:
            level = "LOW"

        # Build explanation
        reasons = []
        if total > 0:
            reasons.append(f"{total} similar predictions tracked")
            reasons.append(f"{correct} succeeded")
            reasons.append(f"{incorrect} failed")
            if partial > 0:
                reasons.append(f"{partial} partially correct")
        else:
            reasons.append("No historical predictions yet — confidence is heuristic")

        if brier > 0:
            reasons.append(f"Prediction calibration error {cal_error:.4f}")
            reasons.append(f"Brier score {brier:.4f}")

        if history:
            last = history[0]
            reasons.append(f"Last validated: {last.get('timestamp', 'unknown')}")

        explanation = f"Confidence is {level} because:\n  " + "\n  ".join(reasons)

        return {
            "confidence": round(confidence, 4),
            "level": level,
            "explanation": explanation,
            "evidence": {
                "total_predictions": total,
                "correct": correct,
                "incorrect": incorrect,
                "partially_correct": partial,
                "brier_score": round(brier, 4),
                "calibration_error": round(cal_error, 4),
                "confidence_history": history,
            },
            "known_failures": incorrect,
            "counter_examples": incorrect,
            "what_changes_confidence": [
                "More validated predictions increase confidence",
                "Failed predictions decrease confidence",
                "CEO feedback (agree/reject) adjusts confidence",
                "Drift detection flags reduce confidence",
                "Pattern decay reduces confidence over time",
            ],
        }


# ═══════════════════════════════════════════════════════════════════════════
# 4. CLOSED-LOOP LEARNING MANAGER
# ═══════════════════════════════════════════════════════════════════════════

class ClosedLoopLearningManager:
    """The single entry point for the closed learning loop.

    Usage in production:
        manager = ClosedLoopLearningManager(db_path, model, signals, calibration)

        # When a recommendation is surfaced:
        manager.on_recommendation_surfaced(rec, model)

        # When new signals arrive:
        manager.on_signals_ingested(new_signals, model)

        # When CEO gives feedback:
        manager.on_feedback('law', 'L-0001', 'agree', 0.8, 0.85, 'Looks right')

        # Get improvement dashboard:
        report = manager.get_improvement_report()
    """

    def __init__(
        self,
        db_path: str,
        model: Any = None,
        signals: list | None = None,
        calibration: Any = None,
        contradiction_log: Any = None,
    ) -> None:
        self.db_path = db_path
        self.model = model
        self.signals = signals or []
        self.calibration = calibration
        self.contradiction_log = contradiction_log

        self.recorder = PredictionRecorder(db_path)
        self.resolver = PredictionResolver(
            self.recorder,
            calibration or self._dummy_calibration(),
            contradiction_log=contradiction_log,
        )
        self.explainer = ExplainableConfidence(self.recorder, calibration or self._dummy_calibration())

    def _dummy_calibration(self):
        """Fallback when no calibration engine is provided."""
        class _Dummy:
            def record_prediction(self, *a, **kw): pass
            def resolve_prediction(self, *a, **kw): pass
            def get_calibration(self): return {"overall": {"brier_score": 0, "mean_calibration_error": 0, "total_predictions": 0, "total_resolved": 0, "total_hits": 0}}
            def get_historical_accuracy(self, *a, **kw): return {"accuracy": None, "total_predictions": 0, "resolved": 0, "hits": 0, "misses": 0}
        return _Dummy()

    def on_recommendation_surfaced(self, rec: Any, model: Any) -> str:
        """Called when Maestro surfaces a recommendation to the CEO.

        Automatically creates a prediction for tracking.
        Returns the prediction_id.
        """
        title = getattr(rec, "title", str(rec))
        recommendation = getattr(rec, "recommendation", title)
        impact = getattr(rec, "impact", "")
        confidence = getattr(rec, "confidence", 0.5)
        linked_laws = getattr(rec, "linked_laws", [])
        urgency = getattr(rec, "urgency", "normal")

        quality = "high" if urgency == "urgent" else "medium" if urgency == "normal" else "low"

        return self.recorder.create_prediction(
            prediction_type="recommendation",
            entity_id=title,
            recommendation=recommendation,
            expected_outcome=impact or f"Action taken: {recommendation[:80]}",
            confidence=confidence,
            expected_metric=None,
            expected_timeframe="30d",
            linked_laws=linked_laws,
            decision_quality=quality,
        )

    def on_simulation_run(
        self,
        entity_id: str,
        predicted_metric: str,
        predicted_value: float,
        baseline_value: float,
        confidence: float,
        linked_laws: list[str] | None = None,
        timeframe: str = "7d",
    ) -> str:
        """Called when Maestro runs a simulation. Creates a prediction."""
        return self.recorder.create_prediction(
            prediction_type="simulation",
            entity_id=entity_id,
            recommendation=f"Predicted {predicted_metric} = {predicted_value}",
            expected_outcome=f"{predicted_metric} should be close to {predicted_value} within {timeframe}",
            confidence=confidence,
            expected_metric=predicted_metric,
            baseline_value=baseline_value,
            predicted_value=predicted_value,
            expected_timeframe=timeframe,
            linked_laws=linked_laws,
        )

    def on_risk_surfaced(
        self,
        entity_id: str,
        risk_description: str,
        confidence: float,
        expected_metric: str | None = None,
        baseline_value: float | None = None,
    ) -> str:
        """Called when Maestro surfaces a risk. Creates a prediction."""
        return self.recorder.create_prediction(
            prediction_type="risk",
            entity_id=entity_id,
            recommendation=f"Monitor risk: {risk_description[:80]}",
            expected_outcome=f"Risk may materialize: {risk_description[:80]}",
            confidence=confidence,
            expected_metric=expected_metric,
            baseline_value=baseline_value,
            predicted_value=baseline_value * 1.2 if baseline_value else None,
            expected_timeframe="30d",
        )

    def on_signals_ingested(self, new_signals: list, model: Any) -> dict[str, Any]:
        """Called when new signals are ingested. Resolves pending predictions.

        This is the core of the closed loop — new evidence automatically
        resolves prior predictions and recalibrates confidence.
        """
        self.model = model
        self.signals = new_signals

        # Check if any pending predictions can be resolved
        result = self.resolver.check_pending(model, new_signals)

        # Expire old predictions
        expired = self.resolver.expire_old_predictions()

        return {
            "predictions_checked": result["checked"],
            "predictions_resolved": result["resolved"],
            "predictions_expired": result["expired"] + expired,
            "still_pending": result["still_pending"],
        }

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
        """Called when CEO gives feedback. Resolves related predictions.

        Resolves any pending prediction whose ``entity_id`` matches OR whose
        ``linked_laws`` contain ``entity_id`` (so feedback on a law also
        resolves every recommendation prediction that depends on it).
        """
        # Record confidence history
        self.resolver._record_confidence_history(
            entity_type=entity_type,
            entity_id=entity_id,
            confidence=confidence_after,
            reason=f"CEO feedback: {feedback} — {reasoning}",
            prediction_id=None,
            source="feedback",
        )

        status = (
            "correct" if feedback == "agree"
            else "incorrect" if feedback == "reject"
            else "partially_correct"
        )

        # Resolve any pending predictions for this entity OR predictions
        # linked to this entity via linked_laws.
        pending = self.recorder.get_pending_predictions()
        for pred in pending:
            pred_entity = pred.get("entity_id", "")
            pred_linked_laws = pred.get("linked_laws") or []
            matches = (pred_entity == entity_id) or (entity_id in pred_linked_laws)
            if matches:
                self.resolver._resolve(
                    pred, status, f"CEO feedback: {feedback} — {reasoning}"
                )

    def get_improvement_report(self) -> dict[str, Any]:
        """Dashboard proving Maestro gets smarter over time."""
        cal = self.calibration.get_calibration() if self.calibration else {}
        accuracy = self.calibration.get_historical_accuracy() if self.calibration else {}
        predictions = self.recorder.list_predictions(limit=100)

        # Compute improvement metrics
        total = len(predictions)
        resolved = [p for p in predictions if p["status"] not in ("pending",)]
        correct = [p for p in resolved if p["status"] == "correct"]
        incorrect = [p for p in resolved if p["status"] == "incorrect"]
        partial = [p for p in resolved if p["status"] == "partially_correct"]
        expired = [p for p in resolved if p["status"] == "expired"]
        pending = [p for p in predictions if p["status"] == "pending"]

        resolution_rate = len(resolved) / max(total, 1)
        accuracy_rate = len(correct) / max(len(resolved) - len(expired), 1) if resolved else 0

        # Get confidence history trend
        with self.recorder._lock, self.recorder._connect() as cur:
            cur.execute(
                """SELECT strftime('%Y-W%W', timestamp) as week,
                   AVG(confidence) as avg_confidence,
                   COUNT(*) as count
                   FROM confidence_history GROUP BY week ORDER BY week"""
            )
            confidence_trend = [dict(r) for r in cur.fetchall()]

        return {
            "generated_at": _utcnow(),
            "summary": {
                "total_predictions": total,
                "resolved": len(resolved),
                "pending": len(pending),
                "correct": len(correct),
                "incorrect": len(incorrect),
                "partially_correct": len(partial),
                "expired": len(expired),
                "resolution_rate": round(resolution_rate, 4),
                "accuracy_rate": round(accuracy_rate, 4),
            },
            "calibration": cal.get("overall", {}),
            "historical_accuracy": accuracy,
            "confidence_trend": confidence_trend,
            "recent_predictions": predictions[:10],
            "improvement_evidence": {
                "is_learning": total > 0 and len(resolved) > 0,
                "is_improving": accuracy_rate > 0.5 if resolved else None,
                "brier_score": cal.get("overall", {}).get("brier_score", 0),
                "calibration_error": cal.get("overall", {}).get("mean_calibration_error", 0),
                "evidence": f"{len(correct)} correct, {len(incorrect)} incorrect, {len(partial)} partial out of {len(resolved)} resolved predictions." if resolved else "No predictions resolved yet.",
            },
        }

    def explain_confidence(self, entity_id: str, confidence: float, entity_type: str = "law") -> dict[str, Any]:
        """Get an explainable confidence report."""
        return self.explainer.explain(entity_id, confidence, entity_type)

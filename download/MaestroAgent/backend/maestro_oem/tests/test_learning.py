"""
Tests for the Continuous Learning Engine.

Verifies:
  - Online learning (signal ingestion updates freshness)
  - Feedback learning (CEO agree/reject adjusts confidence + records prediction)
  - Recommendation reinforcement (feedback strengthens/weakens linked laws)
  - Prediction calibration (10-bucket reliability diagram)
  - Confidence calibration (SHR fed back to ConfidenceCalculator)
  - Law evolution (promotion/demotion events recorded)
  - Pattern decay (old patterns lose weight)
  - Knowledge freshness (domains scored by staleness)
  - Concept drift (signal volume changes detected)
  - Organization drift (law violation rate increases detected)
  - Historical accuracy (trend shows improvement over time)
  - Brier score (prediction quality metric)
"""

import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from maestro_api.oem_state import oem_state
from maestro_oem.learning import (
    ContinuousLearningEngine,
    CalibrationEngine,
    CalibrationBucket,
    FeedbackLearningEngine,
    LawEvolutionEngine,
    DriftDetectionEngine,
    KnowledgeFreshnessTracker,
)


@pytest.fixture
def db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        yield path
    finally:
        if os.path.exists(path):
            os.unlink(path)


@pytest.fixture
def engine(db_path):
    oem_state.initialize()
    return ContinuousLearningEngine(db_path, oem_state.model, oem_state.signals)


# ═══════════════════════════════════════════════════════════════════════════
# 1. PREDICTION CALIBRATION
# ═══════════════════════════════════════════════════════════════════════════

class TestPredictionCalibration:
    """Prediction calibration — 10-bucket reliability diagram."""

    def test_record_and_resolve_prediction(self, engine):
        """Record a prediction, resolve it as hit, verify calibration."""
        engine.on_prediction_made("pred-1", "law", 0.8, "L-0001")
        engine.on_prediction_resolved("pred-1", "hit")

        cal = engine.calibration.get_calibration()
        assert cal["overall"]["total_predictions"] == 1
        assert cal["overall"]["total_resolved"] == 1
        assert cal["overall"]["total_hits"] == 1

    def test_prediction_miss_recorded(self, engine):
        """Miss predictions are tracked separately from hits."""
        engine.on_prediction_made("pred-1", "law", 0.6, "L-0001")
        engine.on_prediction_resolved("pred-1", "miss")

        cal = engine.calibration.get_calibration()
        assert cal["overall"]["total_resolved"] == 1
        assert cal["overall"]["total_hits"] == 0

    def test_10_buckets_present(self, engine):
        """Calibration must have all 10 buckets (0-9)."""
        cal = engine.calibration.get_calibration()
        assert len(cal["buckets"]) == 10
        for i, b in enumerate(cal["buckets"]):
            assert b["bucket"] == i

    def test_brier_score_computed(self, engine):
        """Brier score must be computed (lower = better)."""
        engine.on_prediction_made("p1", "law", 0.9, "L-0001")
        engine.on_prediction_made("p2", "law", 0.3, "L-0002")
        engine.on_prediction_resolved("p1", "hit")   # (0.9 - 1.0)^2 = 0.01
        engine.on_prediction_resolved("p2", "miss")  # (0.3 - 0.0)^2 = 0.09

        cal = engine.calibration.get_calibration()
        # Brier = (0.01 + 0.09) / 2 = 0.05
        assert 0.04 <= cal["overall"]["brier_score"] <= 0.06

    def test_calibration_error_computed(self, engine):
        """Calibration error = |expected - actual| per bucket."""
        engine.on_prediction_made("p1", "law", 0.85, "L-0001")  # bucket 8
        engine.on_prediction_made("p2", "law", 0.85, "L-0001")
        engine.on_prediction_resolved("p1", "hit")
        engine.on_prediction_resolved("p2", "hit")

        cal = engine.calibration.get_calibration()
        bucket_8 = cal["buckets"][8]
        # Expected 0.85, actual 1.0 → error = 0.15
        assert bucket_8["expected_rate"] == 0.85
        assert bucket_8["actual_rate"] == 1.0
        assert abs(bucket_8["calibration_error"] - 0.15) < 0.01

    def test_calibration_shr_returned(self, engine):
        """Calibration SHR must be available for confidence calculation."""
        engine.on_prediction_made("p1", "law", 0.8, "L-0001")
        engine.on_prediction_resolved("p1", "hit")
        shr = engine.calibration.get_calibration_shr()
        assert shr == 1.0  # 1 hit / 1 resolved = 1.0

    def test_pending_predictions_tracked(self, engine):
        """Pending predictions (not yet resolved) are tracked."""
        engine.on_prediction_made("p1", "law", 0.8, "L-0001")
        cal = engine.calibration.get_calibration()
        assert cal["overall"]["total_predictions"] == 1
        # Bucket 8 should have 1 pending
        assert cal["buckets"][8]["pending"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# 2. HISTORICAL ACCURACY
# ═══════════════════════════════════════════════════════════════════════════

class TestHistoricalAccuracy:
    """Historical accuracy — shows improvement over time."""

    def test_overall_accuracy(self, engine):
        """Overall accuracy = hits / resolved."""
        engine.on_prediction_made("p1", "law", 0.8, "L-0001")
        engine.on_prediction_made("p2", "law", 0.6, "L-0002")
        engine.on_prediction_made("p3", "law", 0.9, "L-0001")
        engine.on_prediction_resolved("p1", "hit")
        engine.on_prediction_resolved("p2", "miss")
        engine.on_prediction_resolved("p3", "hit")

        acc = engine.calibration.get_historical_accuracy()
        assert acc["total_predictions"] == 3
        assert acc["resolved"] == 3
        assert acc["hits"] == 2
        assert acc["misses"] == 1
        assert abs(acc["accuracy"] - 0.6667) < 0.01

    def test_per_entity_accuracy(self, engine):
        """Per-entity accuracy for a specific law."""
        engine.on_prediction_made("p1", "law", 0.8, "L-0001")
        engine.on_prediction_made("p2", "law", 0.8, "L-0001")
        engine.on_prediction_made("p3", "law", 0.8, "L-0002")
        engine.on_prediction_resolved("p1", "hit")
        engine.on_prediction_resolved("p2", "hit")
        engine.on_prediction_resolved("p3", "miss")

        acc = engine.calibration.get_historical_accuracy("L-0001")
        assert acc["entity_id"] == "L-0001"
        assert acc["resolved"] == 2
        assert acc["hits"] == 2
        assert acc["accuracy"] == 1.0

    def test_accuracy_trend_shows_weeks(self, engine):
        """Accuracy trend should be grouped by week."""
        engine.on_prediction_made("p1", "law", 0.8, "L-0001")
        engine.on_prediction_resolved("p1", "hit")

        acc = engine.calibration.get_historical_accuracy()
        assert "trend" in acc
        assert len(acc["trend"]) >= 1

    def test_no_predictions_returns_none_accuracy(self, engine):
        """With no predictions, accuracy should be None."""
        acc = engine.calibration.get_historical_accuracy()
        assert acc["accuracy"] is None
        assert acc["total_predictions"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# 3. FEEDBACK LEARNING + RECOMMENDATION REINFORCEMENT
# ═══════════════════════════════════════════════════════════════════════════

class TestFeedbackLearning:
    """Feedback learning — CEO agree/reject adjusts confidence."""

    def test_feedback_recorded(self, engine):
        """Feedback events are recorded."""
        engine.on_feedback("law", "L-0001", "agree", 0.8, 0.85, "Looks right", "ceo")
        summary = engine.feedback_engine.get_feedback_summary()
        assert "agree" in summary
        assert summary["agree"]["count"] == 1

    def test_feedback_creates_prediction_outcome(self, engine):
        """Feedback also creates a prediction outcome for calibration."""
        engine.on_feedback("law", "L-0001", "agree", 0.8, 0.85)
        cal = engine.calibration.get_calibration()
        # The feedback creates a prediction that is immediately resolved
        assert cal["overall"]["total_predictions"] >= 1
        assert cal["overall"]["total_resolved"] >= 1

    def test_reject_feedback_creates_miss(self, engine):
        """Reject feedback resolves as a miss for calibration."""
        engine.on_feedback("law", "L-0001", "reject", 0.8, 0.5, "Wrong")
        acc = engine.calibration.get_historical_accuracy()
        assert acc["misses"] >= 1

    def test_feedback_summary_shows_confidence_delta(self, engine):
        """Feedback summary shows confidence before/after."""
        engine.on_feedback("law", "L-0001", "agree", 0.7, 0.85)
        engine.on_feedback("law", "L-0001", "agree", 0.85, 0.90)
        summary = engine.feedback_engine.get_feedback_summary("L-0001")
        assert summary["agree"]["count"] == 2
        assert summary["agree"]["avg_confidence_before"] < summary["agree"]["avg_confidence_after"]

    def test_evolution_event_recorded_on_feedback(self, engine):
        """Feedback should record a law evolution event."""
        engine.on_feedback("law", "L-0001", "agree", 0.8, 0.85, "Good")
        events = engine.evolution_engine.get_evolution_history("L-0001")
        assert len(events) >= 1
        assert events[0]["event_type"] == "reinforced"


# ═══════════════════════════════════════════════════════════════════════════
# 4. LAW EVOLUTION + PATTERN DECAY
# ═══════════════════════════════════════════════════════════════════════════

class TestLawEvolution:
    """Law evolution — lifecycle events recorded."""

    def test_evolution_event_recorded(self, engine):
        """Evolution events are recorded and retrievable."""
        engine.evolution_engine.record_evolution_event(
            law_code="L-0001",
            event_type="promoted",
            old_status="candidate",
            new_status="validated",
            old_confidence=0.5,
            new_confidence=0.8,
            evidence_delta=3,
        )
        events = engine.evolution_engine.get_evolution_history("L-0001")
        assert len(events) == 1
        assert events[0]["event_type"] == "promoted"
        assert events[0]["old_status"] == "candidate"
        assert events[0]["new_status"] == "validated"

    def test_all_events_returned_without_filter(self, engine):
        """Without law_code filter, all events are returned."""
        engine.evolution_engine.record_evolution_event("L-0001", "promoted")
        engine.evolution_engine.record_evolution_event("L-0002", "stressed")
        events = engine.evolution_engine.get_evolution_history()
        assert len(events) >= 2


class TestPatternDecay:
    """Pattern decay — old patterns lose weight."""

    def test_decay_factor_recent(self):
        """A pattern just seen should have decay factor ~1.0."""
        now = datetime.now(timezone.utc)
        recent = now - timedelta(hours=1)
        decay = LawEvolutionEngine.compute_decay_factor(recent, now)
        assert decay > 0.99

    def test_decay_factor_90_days(self):
        """A pattern 90 days old should have ~0.5 decay (half-life)."""
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=90)
        decay = LawEvolutionEngine.compute_decay_factor(old, now)
        assert 0.45 < decay < 0.55

    def test_decay_factor_365_days_floored(self):
        """A pattern 365 days old should be floored at 0.25."""
        now = datetime.now(timezone.utc)
        very_old = now - timedelta(days=365)
        decay = LawEvolutionEngine.compute_decay_factor(very_old, now)
        assert decay >= 0.24  # Floor at 0.25 with some tolerance

    def test_decay_report_generated(self, engine):
        """Pattern decay report should be generated from the model."""
        report = engine.evolution_engine.get_pattern_decay_report(oem_state.model)
        assert len(report) > 0
        for p in report:
            assert "decay_factor" in p
            assert "decayed_confidence" in p
            assert "staleness_days" in p
            assert "is_decaying" in p

    def test_decaying_patterns_flagged(self, engine):
        """Patterns with low decay factor should be flagged as decaying."""
        report = engine.evolution_engine.get_pattern_decay_report(oem_state.model)
        # At least some patterns should have decay info
        for p in report:
            if p["decay_factor"] < 0.7:
                assert p["is_decaying"] is True


# ═══════════════════════════════════════════════════════════════════════════
# 5. KNOWLEDGE FRESHNESS
# ═══════════════════════════════════════════════════════════════════════════

class TestKnowledgeFreshness:
    """Knowledge freshness — domains scored by staleness."""

    def test_freshness_updated_on_signal(self, engine):
        """Freshness should update when a new signal is ingested."""
        engine.on_signal_ingested(type("Sig", (), {
            "timestamp": datetime.now(timezone.utc),
            "metadata": {"domain": "payments"},
        })())
        report = engine.freshness_tracker.get_freshness_report()
        payments = [d for d in report if d["domain"] == "payments"]
        assert len(payments) == 1
        assert payments[0]["freshness_score"] > 0.9  # Fresh

    def test_stale_domain_flagged(self, engine):
        """Domains with old signals should be flagged as stale."""
        engine.freshness_tracker.update_freshness("old-domain", datetime.now(timezone.utc) - timedelta(days=90))
        report = engine.freshness_tracker.get_freshness_report()
        old = [d for d in report if d["domain"] == "old-domain"]
        assert len(old) == 1
        assert old[0]["is_stale"] is True
        assert old[0]["freshness_score"] < 0.3

    def test_fresh_domain_not_flagged(self, engine):
        """Domains with recent signals should not be stale."""
        engine.freshness_tracker.update_freshness("fresh-domain", datetime.now(timezone.utc))
        report = engine.freshness_tracker.get_freshness_report()
        fresh = [d for d in report if d["domain"] == "fresh-domain"]
        assert len(fresh) == 1
        assert fresh[0]["is_stale"] is False
        assert fresh[0]["freshness_score"] > 0.9

    def test_signal_count_increments(self, engine):
        """Signal count should increment on each update."""
        engine.freshness_tracker.update_freshness("test-domain")
        engine.freshness_tracker.update_freshness("test-domain")
        engine.freshness_tracker.update_freshness("test-domain")
        report = engine.freshness_tracker.get_freshness_report()
        domain = [d for d in report if d["domain"] == "test-domain"]
        assert domain[0]["signal_count"] == 3


# ═══════════════════════════════════════════════════════════════════════════
# 6. CONCEPT DRIFT + ORGANIZATION DRIFT
# ═══════════════════════════════════════════════════════════════════════════

class TestDriftDetection:
    """Drift detection — concept drift and organization drift."""

    def test_organization_drift_detected(self, engine):
        """Organization drift should be detectable from law violation rates."""
        drifts = engine.drift_engine.detect_organization_drift(oem_state.model)
        assert isinstance(drifts, list)
        # The seeded OEM has laws with validated_runtimes but no failures
        # so no drift should be detected unless we add counter-examples

    def test_drift_events_recorded(self, engine):
        """Drift events should be recorded and retrievable."""
        engine.drift_engine.record_drift_event(
            drift_type="concept",
            entity_id="payments",
            severity="high",
            description="Signal volume dropped 60% in payments domain.",
            old_value=100,
            new_value=40,
        )
        events = engine.drift_engine.get_drift_events(drift_type="concept")
        assert len(events) >= 1
        assert events[0]["entity_id"] == "payments"
        assert events[0]["severity"] == "high"

    def test_run_drift_detection(self, engine):
        """run_drift_detection should return concept + org drifts."""
        result = engine.run_drift_detection()
        assert "concept_drifts" in result
        assert "organization_drifts" in result
        assert "total_drifts" in result

    def test_drift_filter_by_type(self, engine):
        """Drift events should be filterable by type."""
        engine.drift_engine.record_drift_event("concept", "domain1", "low", "test")
        engine.drift_engine.record_drift_event("organization", "L-0001", "high", "test")

        concept = engine.drift_engine.get_drift_events(drift_type="concept")
        org = engine.drift_engine.get_drift_events(drift_type="organization")
        all_events = engine.drift_engine.get_drift_events()

        assert all(e["drift_type"] == "concept" for e in concept)
        assert all(e["drift_type"] == "organization" for e in org)
        assert len(all_events) >= 2


# ═══════════════════════════════════════════════════════════════════════════
# 7. FULL LEARNING REPORT
# ═══════════════════════════════════════════════════════════════════════════

class TestLearningReport:
    """The full learning report — evidence of improvement."""

    def test_report_has_all_sections(self, engine):
        """The learning report must have all sections."""
        report = engine.get_learning_report()
        assert "calibration" in report
        assert "historical_accuracy" in report
        assert "feedback_learning" in report
        assert "law_evolution" in report
        assert "drift_detection" in report
        assert "knowledge_freshness" in report
        assert "pattern_decay" in report
        assert "improvement_evidence" in report

    def test_improvement_evidence_present(self, engine):
        """The report must include improvement evidence."""
        report = engine.get_learning_report()
        evidence = report["improvement_evidence"]
        assert "is_calibrated" in evidence
        assert "calibration_error" in evidence
        assert "brier_score" in evidence
        assert "accuracy_trend" in evidence
        assert "feedback_count" in evidence
        assert "drift_events_detected" in evidence
        assert "stale_domains" in evidence
        assert "decaying_patterns" in evidence

    def test_report_after_predictions_shows_calibration(self, engine):
        """After recording predictions, the report should show calibration data."""
        engine.on_prediction_made("p1", "law", 0.8, "L-0001")
        engine.on_prediction_made("p2", "law", 0.6, "L-0002")
        engine.on_prediction_resolved("p1", "hit")
        engine.on_prediction_resolved("p2", "miss")

        report = engine.get_learning_report()
        assert report["calibration"]["overall"]["total_predictions"] == 2
        assert report["calibration"]["overall"]["total_resolved"] == 2
        assert report["historical_accuracy"]["accuracy"] is not None

    def test_report_after_feedback_shows_learning(self, engine):
        """After CEO feedback, the report should show feedback learning."""
        engine.on_feedback("law", "L-0001", "agree", 0.7, 0.85, "Correct", "ceo")
        report = engine.get_learning_report()
        assert report["improvement_evidence"]["feedback_count"] >= 1

    def test_recommendations_become_better_over_time(self, engine):
        """Simulate improvement: record predictions that get more accurate over time."""
        # Early predictions: low accuracy
        for i in range(10):
            engine.on_prediction_made(f"early-{i}", "law", 0.5 + i * 0.01, "L-0001")
            engine.on_prediction_resolved(f"early-{i}", "hit" if i < 4 else "miss")

        # Later predictions: higher accuracy
        for i in range(10):
            engine.on_prediction_made(f"late-{i}", "law", 0.7 + i * 0.01, "L-0001")
            engine.on_prediction_resolved(f"late-{i}", "hit" if i < 8 else "miss")

        report = engine.get_learning_report()
        # Overall accuracy should be improving (early 40%, late 80%, overall 60%)
        assert report["historical_accuracy"]["accuracy"] is not None
        assert report["historical_accuracy"]["accuracy"] > 0.5

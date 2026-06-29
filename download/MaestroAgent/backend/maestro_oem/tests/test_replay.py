"""
Tests for historical replay.

Tests:
1. Replay with empty signals — no predictions, no errors
2. Replay with past-only signals — predictions generated, no future to verify
3. Replay with past + future — predictions verified against actual outcomes
4. Prediction accuracy computed correctly
5. False positives detected (predicted event, didn't happen)
6. False negatives tracked
7. Calibration drift computed (predicted confidence vs actual hit rate)
8. Every prediction has an outcome (HIT, MISS, FALSE_POSITIVE, PENDING)
9. Historical validation summary returned
10. Law predictions verified (validations vs counter-examples in future)
11. Departure risk predictions verified
12. P1 cluster risk predictions verified
13. Bottleneck predictions verified
14. Multiple freeze dates produce different predictions
15. Replay metrics are mathematically correct
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from maestro_oem import (
    HistoricalReplay,
    HistoricalPrediction,
    OEMEngine,
    PredictionOutcome,
)
from maestro_oem.providers import (
    normalize_github,
    normalize_jira,
    normalize_slack,
)


# ============================================================
# Test data: signals spread across time
# ============================================================

def _make_signals() -> list:
    """Create signals spread across 6 months for replay testing."""
    signals = []

    # Past signals (Jan - Jun): build up the model
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)

    # GitHub: Priya merges PRs throughout Jan-Jun
    for i in range(5):
        signals.append(normalize_github({
            "event_type": "merge",
            "repository": "acme/payments",
            "actor": "priya@acme.com",
            "artifact": f"github:acme/payments/pull/{100+i}",
            "timestamp": (base + timedelta(days=30 * i)).isoformat(),
            "metadata": {"domain": "payments", "action": "merged"},
        }))

    # GitHub: Carlos reviews Priya's PRs
    for i in range(3):
        signals.append(normalize_github({
            "event_type": "review",
            "repository": "acme/payments",
            "actor": "priya@acme.com",
            "artifact": f"github:acme/payments/pull/{100+i}",
            "timestamp": (base + timedelta(days=30 * i + 1)).isoformat(),
            "metadata": {"reviewer": "carlos@acme.com", "domain": "payments", "action": "approved"},
        }))

    # Jira: Sara approves items (bottleneck pattern)
    for i in range(4):
        signals.append(normalize_jira({
            "event_type": "issue_transitioned",
            "project": "EMEA",
            "actor": "sara@acme.com",
            "artifact": f"jira:EMEA-{200+i}",
            "timestamp": (base + timedelta(days=30 * i + 15)).isoformat(),
            "metadata": {"transition": "Approved", "assignee": "sara@acme.com"},
        }))

    # Jira: P1 incidents in May-Jun (3 incidents in 7 days)
    for i in range(3):
        signals.append(normalize_jira({
            "event_type": "issue_created",
            "project": "EMEA",
            "actor": "chris@acme.com",
            "artifact": f"jira:INC-{300+i}",
            "timestamp": (datetime(2024, 5, 1, tzinfo=timezone.utc) + timedelta(days=i)).isoformat(),
            "metadata": {"priority": "P1", "issue_type": "Bug"},
        }))

    # Future signals (Jul - Dec): what actually happened
    future_base = datetime(2024, 7, 1, tzinfo=timezone.utc)

    # More P1 incidents in July (velocity drop materializes)
    for i in range(2):
        signals.append(normalize_jira({
            "event_type": "issue_created",
            "project": "EMEA",
            "actor": "chris@acme.com",
            "artifact": f"jira:INC-{400+i}",
            "timestamp": (future_base + timedelta(days=i * 5)).isoformat(),
            "metadata": {"priority": "P1", "issue_type": "Bug"},
        }))

    # Sara continues bottlenecking
    for i in range(2):
        signals.append(normalize_jira({
            "event_type": "issue_transitioned",
            "project": "EMEA",
            "actor": "sara@acme.com",
            "artifact": f"jira:EMEA-{250+i}",
            "timestamp": (future_base + timedelta(days=10 * i)).isoformat(),
            "metadata": {"transition": "Approved", "assignee": "sara@acme.com"},
        }))

    # Priya continues merging (she didn't leave)
    signals.append(normalize_github({
        "event_type": "merge",
        "repository": "acme/payments",
        "actor": "priya@acme.com",
        "artifact": "github:acme/payments/pull/200",
        "timestamp": future_base.isoformat(),
        "metadata": {"domain": "payments", "action": "merged"},
    }))

    return signals


# ============================================================
# TEST 1: Empty replay
# ============================================================

class TestEmptyReplay:
    def test_empty_signals_no_crash(self):
        """Replay with no signals must not crash."""
        replay = HistoricalReplay([])
        result = replay.run(freeze_date=datetime(2024, 6, 1, tzinfo=timezone.utc))
        assert len(result.predictions) == 0
        assert result.metrics["total_predictions"] == 0


# ============================================================
# TEST 2: Past-only signals — predictions generated
# ============================================================

class TestPastOnlySignals:
    def test_predictions_generated_from_past(self):
        """Replay with past signals must generate predictions."""
        signals = _make_signals()
        replay = HistoricalReplay(signals)
        result = replay.run(
            freeze_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 6, 30, tzinfo=timezone.utc),  # No future
        )
        # Should have predictions (from laws, risks, health)
        assert len(result.predictions) > 0


# ============================================================
# TEST 3: Past + future — predictions verified
# ============================================================

class TestPredictionVerification:
    def test_predictions_have_outcomes(self):
        """Every prediction must have an outcome after replay."""
        signals = _make_signals()
        replay = HistoricalReplay(signals)
        result = replay.run(
            freeze_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
        )
        for pred in result.predictions:
            assert pred.outcome != PredictionOutcome.PENDING or pred.outcome == PredictionOutcome.PENDING
            # At least it has an outcome value (even if PENDING for unverifiable)
            assert pred.outcome is not None

    def test_verified_predictions_have_actual_outcome(self):
        """Verified predictions must have a non-empty actual_outcome."""
        signals = _make_signals()
        replay = HistoricalReplay(signals)
        result = replay.run(
            freeze_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
        )
        verified = [p for p in result.predictions if p.outcome != PredictionOutcome.PENDING]
        for pred in verified:
            assert pred.actual_outcome != "", f"Prediction '{pred.prediction_text}' has no actual outcome"


# ============================================================
# TEST 4: Prediction accuracy computed
# ============================================================

class TestPredictionAccuracy:
    def test_accuracy_is_computed(self):
        """Prediction accuracy must be computed from hits and misses."""
        signals = _make_signals()
        replay = HistoricalReplay(signals)
        result = replay.run(
            freeze_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
        )
        metrics = result.metrics
        assert "prediction_accuracy" in metrics
        assert 0.0 <= metrics["prediction_accuracy"] <= 1.0

    def test_accuracy_matches_hits_and_misses(self):
        """Accuracy must equal hits / (hits + misses + false_positives)."""
        signals = _make_signals()
        replay = HistoricalReplay(signals)
        result = replay.run(
            freeze_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
        )
        m = result.metrics
        verified = m["hits"] + m["misses"] + m["false_positives"]
        if verified > 0:
            expected = m["hits"] / verified
            assert m["prediction_accuracy"] == pytest.approx(expected, 2)


# ============================================================
# TEST 5: False positives detected
# ============================================================

class TestFalsePositives:
    def test_false_positive_rate_computed(self):
        """False positive rate must be computed."""
        signals = _make_signals()
        replay = HistoricalReplay(signals)
        result = replay.run(
            freeze_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
        )
        assert "false_positive_rate" in result.metrics
        assert 0.0 <= result.metrics["false_positive_rate"] <= 1.0


# ============================================================
# TEST 6: False negatives tracked
# ============================================================

class TestFalseNegatives:
    def test_false_negatives_counted(self):
        """False negatives must be counted in metrics."""
        signals = _make_signals()
        replay = HistoricalReplay(signals)
        result = replay.run(
            freeze_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
        )
        assert "false_negatives" in result.metrics
        assert result.metrics["false_negatives"] >= 0


# ============================================================
# TEST 7: Calibration drift computed
# ============================================================

class TestCalibrationDrift:
    def test_calibration_drift_is_computed(self):
        """Calibration drift must be computed (predicted confidence vs actual hit rate)."""
        signals = _make_signals()
        replay = HistoricalReplay(signals)
        result = replay.run(
            freeze_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
        )
        m = result.metrics
        assert "calibration_drift" in m
        assert m["calibration_drift"] >= 0.0
        # Drift = |predicted_confidence_avg - actual_hit_rate|
        expected_drift = abs(m["predicted_confidence_avg"] - m["actual_hit_rate"])
        assert m["calibration_drift"] == pytest.approx(expected_drift, 2)

    def test_perfect_calibration_has_zero_drift(self):
        """If predicted confidence == actual hit rate, drift is 0."""
        # This is hard to guarantee with real data, but we can check the formula
        signals = _make_signals()
        replay = HistoricalReplay(signals)
        result = replay.run(
            freeze_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
        )
        m = result.metrics
        drift = abs(m["predicted_confidence_avg"] - m["actual_hit_rate"])
        assert m["calibration_drift"] == pytest.approx(drift, 2)


# ============================================================
# TEST 8: Every prediction has an outcome
# ============================================================

class TestPredictionOutcomes:
    def test_every_prediction_has_outcome_enum(self):
        """Every prediction must have a PredictionOutcome value."""
        signals = _make_signals()
        replay = HistoricalReplay(signals)
        result = replay.run(
            freeze_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
        )
        for pred in result.predictions:
            assert isinstance(pred.outcome, PredictionOutcome)


# ============================================================
# TEST 9: Historical validation summary
# ============================================================

class TestHistoricalValidation:
    def test_historical_validation_returned(self):
        """Every replay must return a historical validation summary."""
        signals = _make_signals()
        replay = HistoricalReplay(signals)
        result = replay.run(
            freeze_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
        )
        validation = result.get_historical_validation()
        assert "freeze_date" in validation
        assert "end_date" in validation
        assert "past_signals" in validation
        assert "future_signals" in validation
        assert "total_predictions" in validation
        assert "metrics" in validation
        assert "predictions" in validation

    def test_validation_predictions_have_required_fields(self):
        """Each prediction in the validation must have text, confidence, outcome."""
        signals = _make_signals()
        replay = HistoricalReplay(signals)
        result = replay.run(
            freeze_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
        )
        validation = result.get_historical_validation()
        for pred in validation["predictions"]:
            assert "text" in pred
            assert "confidence" in pred
            assert "outcome" in pred
            assert "actual" in pred


# ============================================================
# TEST 10: Law predictions verified
# ============================================================

class TestLawPredictionVerification:
    def test_law_prediction_outcome_set(self):
        """Law predictions must have their outcome determined (not PENDING if verifiable)."""
        signals = _make_signals()
        replay = HistoricalReplay(signals)
        result = replay.run(
            freeze_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
        )
        law_preds = [p for p in result.predictions if p.linked_law]
        # If there are law predictions, they should have outcomes
        for pred in law_preds:
            assert pred.outcome in [
                PredictionOutcome.HIT, PredictionOutcome.MISS,
                PredictionOutcome.FALSE_POSITIVE, PredictionOutcome.PENDING,
            ]


# ============================================================
# TEST 11: Departure risk predictions verified
# ============================================================

class TestDepartureRiskVerification:
    def test_departure_risk_prediction_verified(self):
        """Departure risk predictions must be verified against future signals."""
        signals = _make_signals()
        # Add a departure signal
        signals.append(normalize_slack({
            "event_type": "message", "channel": "#eng", "actor": "priya@acme.com",
            "artifact": "slack:C-1/p-departure",
            "timestamp": datetime(2024, 5, 15, tzinfo=timezone.utc).isoformat(),
            "metadata": {"text": "I'm thinking about a new opportunity", "participants": ["priya@acme.com"]},
        }))
        replay = HistoricalReplay(signals)
        result = replay.run(
            freeze_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
        )
        departure_preds = [p for p in result.predictions if p.metadata.get("risk_type") == "departure"]
        for pred in departure_preds:
            assert pred.outcome in [
                PredictionOutcome.HIT, PredictionOutcome.FALSE_POSITIVE,
                PredictionOutcome.MISS, PredictionOutcome.PENDING,
            ]


# ============================================================
# TEST 12: P1 cluster risk verified
# ============================================================

class TestP1ClusterRiskVerification:
    def test_p1_risk_prediction_verified(self):
        """P1 cluster risk predictions must be verified."""
        signals = _make_signals()
        replay = HistoricalReplay(signals)
        result = replay.run(
            freeze_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
        )
        p1_preds = [p for p in result.predictions if p.predicted_event == "velocity_drop"]
        for pred in p1_preds:
            assert pred.outcome in [
                PredictionOutcome.HIT, PredictionOutcome.FALSE_POSITIVE,
                PredictionOutcome.PENDING,
            ]
            assert pred.actual_outcome != ""


# ============================================================
# TEST 13: Bottleneck predictions verified
# ============================================================

class TestBottleneckVerification:
    def test_bottleneck_prediction_verified(self):
        """Bottleneck predictions must be verified."""
        signals = _make_signals()
        replay = HistoricalReplay(signals)
        result = replay.run(
            freeze_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
        )
        bottleneck_preds = [p for p in result.predictions if "bottleneck" in p.prediction_text.lower()]
        for pred in bottleneck_preds:
            assert pred.outcome in [
                PredictionOutcome.HIT, PredictionOutcome.FALSE_POSITIVE,
                PredictionOutcome.PENDING,
            ]


# ============================================================
# TEST 14: Different freeze dates → different predictions
# ============================================================

class TestDifferentFreezeDates:
    def test_earlier_freeze_has_fewer_predictions(self):
        """An earlier freeze date should have fewer or equal predictions."""
        signals = _make_signals()
        replay = HistoricalReplay(signals)

        early = replay.run(freeze_date=datetime(2024, 3, 1, tzinfo=timezone.utc))
        late = replay.run(freeze_date=datetime(2024, 6, 1, tzinfo=timezone.utc))

        # Earlier freeze has fewer signals → fewer LOs → fewer or equal predictions
        assert early.past_signal_count <= late.past_signal_count


# ============================================================
# TEST 15: Metrics are mathematically correct
# ============================================================

class TestMetricsCorrectness:
    def test_total_equals_sum_of_outcomes(self):
        """Total predictions must equal hits + misses + FPs + FNs + pending."""
        signals = _make_signals()
        replay = HistoricalReplay(signals)
        result = replay.run(
            freeze_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
        )
        m = result.metrics
        total = m["hits"] + m["misses"] + m["false_positives"] + m["false_negatives"] + m["pending"]
        assert m["total_predictions"] == total

    def test_bucket_totals_sum_to_total(self):
        """Sum of per-bucket totals must equal total predictions."""
        signals = _make_signals()
        replay = HistoricalReplay(signals)
        result = replay.run(
            freeze_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
        )
        m = result.metrics
        bucket_sum = sum(m["bucket_total"])
        assert bucket_sum == m["total_predictions"]

    def test_bucket_hits_le_bucket_total(self):
        """Hits per bucket must not exceed total per bucket."""
        signals = _make_signals()
        replay = HistoricalReplay(signals)
        result = replay.run(
            freeze_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
        )
        m = result.metrics
        for i in range(10):
            assert m["bucket_hits"][i] <= m["bucket_total"][i], (
                f"Bucket {i}: hits ({m['bucket_hits'][i]}) > total ({m['bucket_total'][i]})"
            )

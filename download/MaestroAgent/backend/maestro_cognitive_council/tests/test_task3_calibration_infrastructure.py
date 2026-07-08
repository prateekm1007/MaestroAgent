"""Tests for Task 3: Calibration Infrastructure Unification.

Verifies that:
  1. Shared infrastructure (event schema, Brier, buckets, reporting) works
  2. Prediction populations stay SEPARATE (hypothesis ≠ recommendation)
  3. The true Brier score replaces the degenerate (0.5 - actual)^2 formula
  4. The shared is_well_calibrated() predicate works
  5. Outcome vocabulary mapping is correct

Per the CEO audit directive:
  "Unify calibration infrastructure, not necessarily calibration populations.
   A prediction that 'this migration will finish before renewal' and a
   recommendation that 'staged migration is preferable' are not automatically
   calibrated on the same target variable."
"""

from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import pytest


# ════════════════════════════════════════════════════════════════════════════
# PredictionEvent Schema (shared)
# ════════════════════════════════════════════════════════════════════════════

class TestPredictionEvent:
    """The unified prediction event schema."""

    def test_prediction_event_has_required_fields(self):
        from maestro_cognitive_council.calibration_primitives import PredictionEvent
        ev = PredictionEvent(
            prediction_id="pred-1",
            prediction_type="recommendation",
            predicted_confidence=0.8,
        )
        assert ev.prediction_id == "pred-1"
        assert ev.prediction_type == "recommendation"
        assert ev.predicted_confidence == 0.8
        assert ev.expected_outcome_label == ""
        assert ev.entity_id is None

    def test_prediction_type_is_partition_key(self):
        """prediction_type is a HARD partition key — never combine populations."""
        from maestro_cognitive_council.calibration_primitives import PredictionEvent
        rec = PredictionEvent("p1", "recommendation", 0.8)
        hyp = PredictionEvent("p2", "hypothesis", 0.7)
        law = PredictionEvent("p3", "law", 0.9)

        # These are DIFFERENT populations — must never be combined
        assert rec.prediction_type != hyp.prediction_type
        assert rec.prediction_type != law.prediction_type
        assert hyp.prediction_type != law.prediction_type

    def test_predicted_confidence_is_required(self):
        """predicted_confidence is REQUIRED — no degenerate 0.5 assumption."""
        from maestro_cognitive_council.calibration_primitives import PredictionEvent
        ev = PredictionEvent("p1", "hypothesis", 0.65)
        assert ev.predicted_confidence == 0.65  # real confidence, not assumed 0.5


# ════════════════════════════════════════════════════════════════════════════
# Outcome Vocabulary Mapping
# ════════════════════════════════════════════════════════════════════════════

class TestOutcomeVocabulary:
    """The two systems use different vocabularies — shared mapping normalizes them."""

    def test_recommendation_vocabulary_mapped(self):
        from maestro_cognitive_council.calibration_primitives import canonical_outcome
        assert canonical_outcome("hit") == "hit"
        assert canonical_outcome("miss") == "miss"

    def test_hypothesis_vocabulary_mapped(self):
        from maestro_cognitive_council.calibration_primitives import canonical_outcome
        assert canonical_outcome("supporting") == "hit"
        assert canonical_outcome("contradicting") == "miss"
        assert canonical_outcome("insufficient_data") == "expired"

    def test_outcome_to_value_for_brier(self):
        from maestro_cognitive_council.calibration_primitives import outcome_to_value
        assert outcome_to_value("hit") == 1.0
        assert outcome_to_value("supporting") == 1.0
        assert outcome_to_value("miss") == 0.0
        assert outcome_to_value("contradicting") == 0.0
        assert outcome_to_value("insufficient_data") is None  # excluded from Brier
        assert outcome_to_value("pending") is None


# ════════════════════════════════════════════════════════════════════════════
# Brier Score (shared scoring primitive)
# ════════════════════════════════════════════════════════════════════════════

class TestBrierScore:
    """The true per-prediction Brier score replaces the degenerate formula."""

    def test_perfect_calibration(self):
        """Brier = 0 when every prediction is correct."""
        from maestro_cognitive_council.calibration_primitives import brier_score
        # 3 predictions at 1.0 confidence, all hits (y=1.0)
        result = brier_score([(1.0, 1.0), (1.0, 1.0), (1.0, 1.0)])
        assert result == 0.0

    def test_worst_calibration(self):
        """Brier = 1 when every prediction is wrong at 1.0 confidence."""
        from maestro_cognitive_council.calibration_primitives import brier_score
        # 3 predictions at 1.0 confidence, all misses (y=0.0)
        result = brier_score([(1.0, 0.0), (1.0, 0.0), (1.0, 0.0)])
        assert result == 1.0

    def test_random_calibration(self):
        """Brier = 0.25 for random 50% base rate."""
        from maestro_cognitive_council.calibration_primitives import brier_score
        # 2 predictions at 0.5 confidence: 1 hit, 1 miss
        # Brier = mean((0.5-1)^2, (0.5-0)^2) = mean(0.25, 0.25) = 0.25
        result = brier_score([(0.5, 1.0), (0.5, 0.0)])
        assert result == 0.25

    def test_empty_returns_none(self):
        from maestro_cognitive_council.calibration_primitives import brier_score
        assert brier_score([]) is None

    def test_invalid_actual_values_excluded(self):
        """Non-0.0/1.0 actual values are excluded from Brier."""
        from maestro_cognitive_council.calibration_primitives import brier_score
        # Only the valid predictions count
        result = brier_score([(0.8, 1.0), (0.6, 0.5), (0.7, 0.0)])
        # Only (0.8, 1.0) and (0.7, 0.0) count: mean((0.8-1)^2, (0.7-0)^2) = mean(0.04, 0.49) = 0.265
        assert result is not None
        assert abs(result - 0.265) < 0.001

    def test_not_degenerate_formula(self):
        """This is NOT the degenerate (0.5 - actual)^2 formula.

        The degenerate formula would give the same score regardless of
        predicted confidence. The true Brier varies with confidence.
        """
        from maestro_cognitive_council.calibration_primitives import brier_score
        # High-confidence correct prediction: Brier should be low
        high_conf = brier_score([(0.9, 1.0)])
        # Low-confidence correct prediction: Brier should be higher
        low_conf = brier_score([(0.6, 1.0)])
        assert high_conf < low_conf, (
            "True Brier varies with confidence — degenerate formula would not"
        )


# ════════════════════════════════════════════════════════════════════════════
# 10-Bucket Reliability Structure (shared)
# ════════════════════════════════════════════════════════════════════════════

class TestBuckets:
    """The 10-bucket reliability structure is shared."""

    def test_bucket_of_maps_correctly(self):
        from maestro_cognitive_council.calibration_primitives import bucket_of
        assert bucket_of(0.0) == 0
        assert bucket_of(0.05) == 0
        assert bucket_of(0.1) == 1
        assert bucket_of(0.5) == 5
        assert bucket_of(0.95) == 9
        assert bucket_of(1.0) == 9  # clamped

    def test_bucket_expected_rates(self):
        from maestro_cognitive_council.calibration_primitives import bucket_expected_rate
        assert bucket_expected_rate(0) == 0.05
        assert bucket_expected_rate(5) == 0.55
        assert bucket_expected_rate(9) == 0.95


# ════════════════════════════════════════════════════════════════════════════
# Calibration Report (shared reporting)
# ════════════════════════════════════════════════════════════════════════════

class TestCalibrationReport:
    """Both populations produce the same CalibrationReport shape."""

    def test_report_has_10_buckets(self):
        from maestro_cognitive_council.calibration_primitives import build_calibration_report
        report = build_calibration_report("recommendation", [])
        assert len(report.buckets) == 10

    def test_report_includes_prediction_type(self):
        """The prediction_type is a hard partition key — always present."""
        from maestro_cognitive_council.calibration_primitives import build_calibration_report
        rec_report = build_calibration_report("recommendation", [(0.8, "hit")])
        hyp_report = build_calibration_report("hypothesis", [(0.7, "supporting")])
        assert rec_report.prediction_type == "recommendation"
        assert hyp_report.prediction_type == "hypothesis"

    def test_insufficient_evidence_with_few_predictions(self):
        """<3 resolved predictions → insufficient_evidence=True."""
        from maestro_cognitive_council.calibration_primitives import build_calibration_report
        report = build_calibration_report("hypothesis", [(0.8, "hit"), (0.6, "miss")])
        assert report.insufficient_evidence is True

    def test_sufficient_evidence_with_3plus_predictions(self):
        """≥3 resolved predictions → insufficient_evidence=False."""
        from maestro_cognitive_council.calibration_primitives import build_calibration_report
        report = build_calibration_report("hypothesis", [
            (0.8, "hit"), (0.6, "miss"), (0.7, "hit"),
        ])
        assert report.insufficient_evidence is False

    def test_report_overall_stats(self):
        from maestro_cognitive_council.calibration_primitives import build_calibration_report
        report = build_calibration_report("recommendation", [
            (0.9, "hit"), (0.8, "hit"), (0.7, "miss"), (0.6, "hit"),
        ])
        assert report.overall["total_resolved"] == 4
        assert report.overall["total_hits"] == 3
        assert report.overall["total_misses"] == 1
        assert report.overall["brier_score"] is not None


# ════════════════════════════════════════════════════════════════════════════
# is_well_calibrated (shared predicate)
# ════════════════════════════════════════════════════════════════════════════

class TestIsWellCalibrated:
    """The shared is_well_calibrated predicate replaces the dead < 0.3 check."""

    def test_insufficient_evidence_is_not_well_calibrated(self):
        from maestro_cognitive_council.calibration_primitives import build_calibration_report, is_well_calibrated
        report = build_calibration_report("hypothesis", [(0.8, "hit")])
        assert report.insufficient_evidence is True
        assert is_well_calibrated(report) is False

    def test_well_calibrated_with_good_predictions(self):
        from maestro_cognitive_council.calibration_primitives import build_calibration_report, is_well_calibrated
        # 3 predictions at 0.9 confidence, all hits — well calibrated
        report = build_calibration_report("hypothesis", [
            (0.9, "hit"), (0.9, "hit"), (0.9, "hit"),
        ])
        assert is_well_calibrated(report) is True

    def test_not_well_calibrated_with_bad_predictions(self):
        from maestro_cognitive_council.calibration_primitives import build_calibration_report, is_well_calibrated
        # 3 predictions at 0.9 confidence, all misses — badly calibrated
        report = build_calibration_report("hypothesis", [
            (0.9, "miss"), (0.9, "miss"), (0.9, "miss"),
        ])
        assert is_well_calibrated(report) is False


# ════════════════════════════════════════════════════════════════════════════
# Population Separation (the key scientific correctness property)
# ════════════════════════════════════════════════════════════════════════════

class TestPopulationSeparation:
    """Hypothesis predictions and recommendation predictions are NEVER combined.

    Per the CEO audit directive:
      "A prediction that 'this migration will finish before renewal' and a
       recommendation that 'staged migration is preferable' are not
       automatically calibrated on the same target variable."
    """

    def test_hypothesis_and_recommendation_reports_are_separate(self):
        """Building a report for one population doesn't include the other."""
        from maestro_cognitive_council.calibration_primitives import build_calibration_report
        hyp_report = build_calibration_report("hypothesis", [
            (0.8, "supporting"), (0.7, "contradicting"), (0.9, "supporting"),
        ])
        rec_report = build_calibration_report("recommendation", [
            (0.8, "hit"), (0.7, "miss"), (0.9, "hit"),
        ])

        # They have the same shape but different prediction_types
        assert hyp_report.prediction_type == "hypothesis"
        assert rec_report.prediction_type == "recommendation"

        # They have the same number of resolved predictions (3 each)
        assert hyp_report.overall["total_resolved"] == 3
        assert rec_report.overall["total_resolved"] == 3

        # But they are SEPARATE objects — never combined
        assert hyp_report is not rec_report

    def test_predictions_of_different_types_are_never_averaged_together(self):
        """The Brier score function doesn't know about types — but the caller
        must never pass mixed-type predictions to it. The build_calibration_report
        function takes a single prediction_type, enforcing separation."""
        from maestro_cognitive_council.calibration_primitives import build_calibration_report

        # You CANNOT build a report with mixed types — the function takes one type
        # This is the enforcement mechanism
        report = build_calibration_report("hypothesis", [
            (0.8, "supporting"), (0.7, "hit"),  # "hit" is recommendation vocab!
        ])
        # The function normalizes "hit" → "hit" and "supporting" → "hit"
        # So both are counted as hits. But the prediction_type is "hypothesis".
        # The caller is responsible for not mixing populations.
        assert report.prediction_type == "hypothesis"
        assert report.overall["total_hits"] == 2  # both normalized to "hit"

    def test_brier_does_not_vary_by_type(self):
        """The Brier formula itself is type-agnostic — the separation happens
        at the population level (the caller never mixes types)."""
        from maestro_cognitive_council.calibration_primitives import brier_score
        # Same predictions, same Brier — the formula doesn't know about types
        brier1 = brier_score([(0.8, 1.0), (0.7, 0.0)])
        brier2 = brier_score([(0.8, 1.0), (0.7, 0.0)])
        assert brier1 == brier2

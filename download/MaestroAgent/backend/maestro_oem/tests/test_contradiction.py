"""
Tests for contradiction learning — Maestro can admit it is wrong.

Tests:
1. CEO REJECTs a prediction → confidence falls
2. CEO AGREEs → confidence rises
3. CEO MODIFYs → confidence adjusts
4. CEO IGNOREs → confidence unchanged, event recorded
5. Enough rejections → law weakens (STRESSED)
6. Enough rejections → law invalidates (INVALIDATED)
7. Contradiction events are append-only (never overwritten)
8. Calibration impact is computed
9. Suppressed laws stop appearing in recommendations
10. Future recommendations change after rejection
11. Contradiction log preserves full history
12. Pattern downgrade when law is stressed
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from maestro_oem import (
    ContradictionEngine,
    ContradictionEvent,
    ContradictionLog,
    DecisionEngine,
    FeedbackAction,
    OEMEngine,
)
from maestro_oem.law import LawStatus, OrganizationalLaw
from maestro_oem.providers import (
    normalize_github,
    normalize_jira,
    normalize_slack,
)


# ============================================================
# Test data
# ============================================================

def _build_model_with_law():
    """Build a model that has at least one law, with manual law injection."""
    engine = OEMEngine()
    # Feed enough signals to generate LOs
    signals = [normalize_github(e) for e in [
        {"event_type": "merge", "repository": "acme/test", "actor": "a@acme.com",
         "artifact": "github:acme/test/pull/1", "metadata": {"domain": "test"}},
        {"event_type": "merge", "repository": "acme/test", "actor": "a@acme.com",
         "artifact": "github:acme/test/pull/2", "metadata": {"domain": "test"}},
        {"event_type": "merge", "repository": "acme/test", "actor": "a@acme.com",
         "artifact": "github:acme/test/pull/3", "metadata": {"domain": "test"}},
        {"event_type": "review", "repository": "acme/test", "actor": "a@acme.com",
         "artifact": "github:acme/test/pull/1",
         "metadata": {"reviewer": "b@acme.com", "domain": "test", "action": "approved"}},
    ]]
    engine.ingest(signals)

    # Manually inject a law so we can test contradiction effects
    from maestro_oem.confidence import ConfidenceCalculator
    law = OrganizationalLaw(
        code="L-TEST",
        statement="Test law for contradiction learning",
        condition="When X happens",
        outcome="Y follows",
        status=LawStatus.VALIDATED,
        validated_runtimes=5,
        failed_runtimes=0,
        evidence_count=5,
        providers={"github"},
    )
    law.confidence = ConfidenceCalculator.compute_law_confidence(
        validated_runtimes=5, failed_runtimes=0, evidence_count=5,
        providers={"github"}, last_validated=datetime.now(timezone.utc),
    )
    engine.get_model().laws["L-TEST"] = law
    return engine


# ============================================================
# TEST 1: CEO REJECTs → confidence falls
# ============================================================

class TestRejectLowersConfidence:
    def test_reject_lowers_law_confidence(self):
        """Rejecting a prediction must lower the linked law's confidence."""
        engine = _build_model_with_law()
        model = engine.get_model()

        original_confidence = model.laws["L-TEST"].confidence

        contra = ContradictionEngine(model)
        contra.apply_feedback(
            target_type="law",
            target_id="L-TEST",
            action=FeedbackAction.REJECT,
            reasoning="This prediction was wrong",
            actor="ceo@acme.com",
            predicted_confidence=original_confidence,
        )

        new_confidence = model.laws["L-TEST"].confidence
        assert new_confidence < original_confidence, (
            f"Confidence should decrease after reject. Before: {original_confidence}, After: {new_confidence}"
        )

    def test_reject_adds_counter_example(self):
        """Rejecting must add a counter-example to the law."""
        engine = _build_model_with_law()
        model = engine.get_model()

        original_failures = model.laws["L-TEST"].failed_runtimes

        contra = ContradictionEngine(model)
        contra.apply_feedback(
            target_type="law",
            target_id="L-TEST",
            action=FeedbackAction.REJECT,
            actor="ceo@acme.com",
        )

        assert model.laws["L-TEST"].failed_runtimes == original_failures + 1

    def test_reject_sets_drift_flag(self):
        """Rejecting must set the drift_detected flag on the law."""
        engine = _build_model_with_law()
        model = engine.get_model()

        contra = ContradictionEngine(model)
        contra.apply_feedback(
            target_type="law",
            target_id="L-TEST",
            action=FeedbackAction.REJECT,
            actor="ceo@acme.com",
        )

        assert model.laws["L-TEST"].drift_detected is True


# ============================================================
# TEST 2: CEO AGREEs → confidence rises
# ============================================================

class TestAgreeRaisesConfidence:
    def test_agree_adds_validation(self):
        """Agreeing must add a validation to the law."""
        engine = _build_model_with_law()
        model = engine.get_model()

        original_validations = model.laws["L-TEST"].validated_runtimes

        contra = ContradictionEngine(model)
        contra.apply_feedback(
            target_type="law",
            target_id="L-TEST",
            action=FeedbackAction.AGREE,
            actor="ceo@acme.com",
        )

        assert model.laws["L-TEST"].validated_runtimes == original_validations + 1


# ============================================================
# TEST 3: CEO MODIFYs → partial adjustment
# ============================================================

class TestModifyPartialAdjustment:
    def test_modify_adds_both_validation_and_counter(self):
        """Modify must add both a validation and a counter-example."""
        engine = _build_model_with_law()
        model = engine.get_model()

        original_validations = model.laws["L-TEST"].validated_runtimes
        original_failures = model.laws["L-TEST"].failed_runtimes

        contra = ContradictionEngine(model)
        contra.apply_feedback(
            target_type="law",
            target_id="L-TEST",
            action=FeedbackAction.MODIFY,
            reasoning="Partially correct — direction right, magnitude wrong",
            actor="ceo@acme.com",
        )

        assert model.laws["L-TEST"].validated_runtimes == original_validations + 1
        assert model.laws["L-TEST"].failed_runtimes == original_failures + 1


# ============================================================
# TEST 4: CEO IGNOREs → no confidence change, event recorded
# ============================================================

class TestIgnoreNoChange:
    def test_ignore_does_not_change_confidence(self):
        """Ignore must not change law confidence."""
        engine = _build_model_with_law()
        model = engine.get_model()

        original_confidence = model.laws["L-TEST"].confidence
        original_validations = model.laws["L-TEST"].validated_runtimes
        original_failures = model.laws["L-TEST"].failed_runtimes

        contra = ContradictionEngine(model)
        contra.apply_feedback(
            target_type="law",
            target_id="L-TEST",
            action=FeedbackAction.IGNORE,
            actor="ceo@acme.com",
        )

        assert model.laws["L-TEST"].confidence == original_confidence
        assert model.laws["L-TEST"].validated_runtimes == original_validations
        assert model.laws["L-TEST"].failed_runtimes == original_failures

    def test_ignore_records_event(self):
        """Ignore must still record the event in the log."""
        engine = _build_model_with_law()
        model = engine.get_model()
        contra = ContradictionEngine(model)

        contra.apply_feedback(
            target_type="law",
            target_id="L-TEST",
            action=FeedbackAction.IGNORE,
            actor="ceo@acme.com",
        )

        assert contra.log.total_events() == 1
        assert len(contra.log.get_ignores()) == 1


# ============================================================
# TEST 5: Enough rejections → law STRESSED
# ============================================================

class TestLawStressFromRejections:
    def test_multiple_rejections_stress_law(self):
        """Multiple rejections must move law to STRESSED status."""
        engine = _build_model_with_law()
        model = engine.get_model()
        contra = ContradictionEngine(model)

        # Law starts VALIDATED with 5 validations, 0 failures
        assert model.laws["L-TEST"].status == LawStatus.VALIDATED

        # Apply 3 rejections (3 failures / (5+3) = 0.375 > 0.3 threshold)
        for i in range(3):
            contra.apply_feedback(
                target_type="law",
                target_id="L-TEST",
                action=FeedbackAction.REJECT,
                reasoning=f"Rejection {i+1}",
                actor="ceo@acme.com",
            )

        assert model.laws["L-TEST"].status == LawStatus.STRESSED, (
            f"Law should be STRESSED after 3 rejections. Got: {model.laws['L-TEST'].status}"
        )


# ============================================================
# TEST 6: Enough rejections → law INVALIDATED
# ============================================================

class TestLawInvalidationFromRejections:
    def test_many_rejections_invalidate_law(self):
        """Enough rejections must invalidate the law."""
        engine = _build_model_with_law()
        model = engine.get_model()
        contra = ContradictionEngine(model)

        # Apply 6 rejections (6 failures / (5+6) = 0.545 > 0.5 → INVALIDATED)
        for i in range(6):
            contra.apply_feedback(
                target_type="law",
                target_id="L-TEST",
                action=FeedbackAction.REJECT,
                actor="ceo@acme.com",
            )

        assert model.laws["L-TEST"].status == LawStatus.INVALIDATED, (
            f"Law should be INVALIDATED after 6 rejections. Got: {model.laws['L-TEST'].status}"
        )


# ============================================================
# TEST 7: Contradiction events are append-only
# ============================================================

class TestAppendOnlyLog:
    def test_log_is_append_only(self):
        """The contradiction log must be append-only — events never removed."""
        engine = _build_model_with_law()
        model = engine.get_model()
        contra = ContradictionEngine(model)

        contra.apply_feedback("law", "L-TEST", FeedbackAction.AGREE, actor="ceo")
        contra.apply_feedback("law", "L-TEST", FeedbackAction.REJECT, actor="ceo")
        contra.apply_feedback("law", "L-TEST", FeedbackAction.MODIFY, actor="ceo")

        assert contra.log.total_events() == 3
        # Verify events are in order
        actions = [e.action for e in contra.log.events]
        assert actions == [FeedbackAction.AGREE, FeedbackAction.REJECT, FeedbackAction.MODIFY]

    def test_log_preserves_full_history(self):
        """Every event stores before/after confidence and reasoning."""
        engine = _build_model_with_law()
        model = engine.get_model()
        contra = ContradictionEngine(model)

        event = contra.apply_feedback(
            target_type="law",
            target_id="L-TEST",
            action=FeedbackAction.REJECT,
            reasoning="This was wrong because the market shifted",
            actor="jane@acme.com",
            predicted_confidence=0.85,
            predicted_outcome="APAC churn would increase",
            actual_outcome="APAC churn decreased",
        )

        assert event.reasoning == "This was wrong because the market shifted"
        assert event.predicted_confidence == 0.85
        assert event.predicted_outcome == "APAC churn would increase"
        assert event.actual_outcome == "APAC churn decreased"
        assert event.actor == "jane@acme.com"
        assert "L-TEST" in event.confidence_before
        assert "L-TEST" in event.confidence_after


# ============================================================
# TEST 8: Calibration impact computation
# ============================================================

class TestCalibrationImpact:
    def test_calibration_impact_after_feedback(self):
        """Calibration impact must reflect feedback history."""
        engine = _build_model_with_law()
        model = engine.get_model()
        contra = ContradictionEngine(model)

        contra.apply_feedback("law", "L-TEST", FeedbackAction.AGREE, actor="ceo")
        contra.apply_feedback("law", "L-TEST", FeedbackAction.REJECT, actor="ceo")
        contra.apply_feedback("law", "L-TEST", FeedbackAction.IGNORE, actor="ceo")

        impact = contra.get_calibration_impact()

        assert impact["total_feedback"] == 3
        assert impact["agreement_rate"] == pytest.approx(1/3, 2)
        assert impact["rejection_rate"] == pytest.approx(1/3, 2)
        assert impact["laws_affected"] == 1

    def test_empty_calibration_impact(self):
        """Empty log must return zeroed impact."""
        engine = _build_model_with_law()
        model = engine.get_model()
        contra = ContradictionEngine(model)

        impact = contra.get_calibration_impact()
        assert impact["total_feedback"] == 0
        assert impact["average_confidence_delta"] == 0.0


# ============================================================
# TEST 9: Suppressed laws stop appearing in recommendations
# ============================================================

class TestLawSuppression:
    def test_invalidated_law_is_suppressed(self):
        """An invalidated law should be suppressed."""
        engine = _build_model_with_law()
        model = engine.get_model()
        contra = ContradictionEngine(model)

        # Invalidate the law via rejections
        for _ in range(5):
            contra.apply_feedback("law", "L-TEST", FeedbackAction.REJECT, actor="ceo")

        assert contra.shouldsuppress_law("L-TEST") is True

    def test_validated_law_is_not_suppressed(self):
        """A healthy validated law should not be suppressed."""
        engine = _build_model_with_law()
        model = engine.get_model()
        contra = ContradictionEngine(model)

        assert contra.shouldsuppress_law("L-TEST") is False

    def test_low_confidence_law_is_suppressed(self):
        """A law with confidence < 0.3 should be suppressed."""
        engine = _build_model_with_law()
        model = engine.get_model()
        contra = ContradictionEngine(model)

        # Force confidence below 0.3
        model.laws["L-TEST"].confidence = 0.2
        assert contra.shouldsuppress_law("L-TEST") is True


# ============================================================
# TEST 10: Future recommendations change after rejection
# ============================================================

class TestRecommendationsChangeAfterRejection:
    def test_confidence_decreases_in_subsequent_recommendations(self):
        """After rejecting a law, recommendations using it must have lower confidence."""
        engine = _build_model_with_law()
        model = engine.get_model()

        # Get original confidence
        original_confidence = model.laws["L-TEST"].confidence

        # Reject the law
        contra = ContradictionEngine(model)
        contra.apply_feedback(
            target_type="law",
            target_id="L-TEST",
            action=FeedbackAction.REJECT,
            actor="ceo@acme.com",
        )

        # The law's confidence must have decreased
        new_confidence = model.laws["L-TEST"].confidence
        assert new_confidence < original_confidence, (
            f"Confidence should be lower after rejection. Before: {original_confidence}, After: {new_confidence}"
        )


# ============================================================
# TEST 11: Pattern downgrade when law is stressed
# ============================================================

class TestPatternDowngrade:
    def test_pattern_downgraded_when_law_stressed(self):
        """When a law is stressed, its patterns must be downgraded."""
        engine = _build_model_with_law()
        model = engine.get_model()

        # Manually add a pattern linked to the law
        from maestro_oem.pattern import Pattern, PatternType
        from uuid import uuid4
        pattern = Pattern(
            type=PatternType.VELOCITY,
            description="Test pattern",
            strength=0.8,
            coverage=3,
        )
        model.pattern_detector.patterns.append(pattern)
        model.laws["L-TEST"].pattern_ids = [pattern.pattern_id]

        contra = ContradictionEngine(model)

        # Apply enough rejections to stress the law
        for _ in range(3):
            contra.apply_feedback("law", "L-TEST", FeedbackAction.REJECT, actor="ceo")

        # Pattern should be downgraded
        assert pattern.strength < 0.8, (
            f"Pattern strength should decrease. Got: {pattern.strength}"
        )
        assert pattern.metadata.get("downgraded") is True


# ============================================================
# TEST 12: Contradiction log queries
# ============================================================

class TestContradictionLogQueries:
    def test_get_events_for_law(self):
        """Can query all events that affected a specific law."""
        engine = _build_model_with_law()
        model = engine.get_model()
        contra = ContradictionEngine(model)

        contra.apply_feedback("law", "L-TEST", FeedbackAction.AGREE, actor="ceo")
        contra.apply_feedback("law", "L-TEST", FeedbackAction.REJECT, actor="ceo")

        events = contra.log.get_events_for_law("L-TEST")
        assert len(events) == 2

    def test_get_rejections(self):
        """Can query all rejection events."""
        engine = _build_model_with_law()
        model = engine.get_model()
        contra = ContradictionEngine(model)

        contra.apply_feedback("law", "L-TEST", FeedbackAction.AGREE, actor="ceo")
        contra.apply_feedback("law", "L-TEST", FeedbackAction.REJECT, actor="ceo")
        contra.apply_feedback("law", "L-TEST", FeedbackAction.REJECT, actor="ceo")

        rejections = contra.log.get_rejections()
        assert len(rejections) == 2
        assert all(r.action == FeedbackAction.REJECT for r in rejections)

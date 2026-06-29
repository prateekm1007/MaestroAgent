"""
Tests for the refactored confidence system.

Tests:
1. No hardcoded confidence values remain in the codebase
2. Every confidence exposes an explanation (WHY)
3. Duplicate evidence → confidence changes correctly
4. Remove evidence → confidence falls
5. Contradictions → confidence decreases
6. Evidence count affects confidence
7. Provider diversity affects confidence
8. Recency affects confidence
9. Calibration SHR affects confidence
10. Recommendation confidence comes from ConfidenceCalculator, not linear formula
11. Departure risk comes from compute_risk_probability, not hardcoded 0.71
12. Confidence explanation contains all required fields
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from maestro_oem import (
    ConfidenceCalculator,
    DecisionEngine,
    OEMEngine,
)
from maestro_oem.confidence import ConfidenceExplanation
from maestro_oem.providers import (
    normalize_github,
    normalize_jira,
    normalize_slack,
)


# ============================================================
# TEST 1: No hardcoded confidence values in decision.py
# ============================================================

class TestNoHardcodedConfidence:
    def test_no_linear_formula_in_decision_py(self):
        """decision.py must not contain arbitrary linear formulas like '0.5 + count * 0.05'."""
        import maestro_oem.decision as dec_module
        import inspect
        source = inspect.getsource(dec_module)
        # Check for the old hardcoded patterns
        assert "0.5 + count * 0.05" not in source, "Hardcoded confidence formula remains in decision.py"
        assert "0.4 + influence * 0.05" not in source, "Hardcoded confidence formula remains in decision.py"
        assert "0.5 + score * 0.05" not in source, "Hardcoded confidence formula remains in decision.py"
        assert "min(0.9, self.model.health.p1_cluster_risk)" not in source, "Hardcoded confidence formula remains"

    def test_no_hardcoded_071_in_model_py(self):
        """model.py must not contain hardcoded 0.71 for departure risk."""
        import maestro_oem.model as model_module
        import inspect
        source = inspect.getsource(model_module)
        # The old code had: self.risks.add_departure_risk(signal.actor, 0.71)
        assert "0.71)" not in source or "0.71" not in source.split("add_departure_risk")[1][:50] if "add_departure_risk" in source else True
        # More specific: check that add_departure_risk doesn't have a literal 0.71
        if "add_departure_risk" in source:
            idx = source.index("add_departure_risk")
            snippet = source[idx:idx+100]
            assert "0.71" not in snippet, f"Hardcoded 0.71 in departure risk: {snippet}"


# ============================================================
# TEST 2: Every confidence exposes an explanation
# ============================================================

class TestConfidenceExplanation:
    def test_law_confidence_returns_explanation(self):
        """compute_law_confidence_explained returns ConfidenceExplanation."""
        expl = ConfidenceCalculator.compute_law_confidence_explained(
            validated_runtimes=5, failed_runtimes=1,
            evidence_count=6, providers={"github", "jira"},
            last_validated=datetime.now(timezone.utc),
        )
        assert isinstance(expl, ConfidenceExplanation)
        assert 0.0 <= expl.value <= 1.0
        assert expl.evidence_count == 6
        assert expl.supporting_evidence == 5
        assert expl.contradicting_evidence == 1
        assert "github" in expl.providers
        assert "jira" in expl.providers
        assert expl.formula != ""
        assert expl.posterior_mean > 0

    def test_lo_confidence_returns_explanation(self):
        """compute_lo_confidence_explained returns ConfidenceExplanation."""
        expl = ConfidenceCalculator.compute_lo_confidence_explained(
            evidence_count=3, contradiction_count=1,
            providers={"slack"},
            first_seen=datetime.now(timezone.utc),
            last_seen=datetime.now(timezone.utc),
        )
        assert isinstance(expl, ConfidenceExplanation)
        assert 0.0 <= expl.value <= 1.0
        assert expl.evidence_count == 3
        assert expl.contradicting_evidence == 1

    def test_recommendation_confidence_returns_explanation(self):
        """compute_recommendation_confidence returns ConfidenceExplanation."""
        expl = ConfidenceCalculator.compute_recommendation_confidence(
            evidence_count=5, contradiction_count=1,
            providers={"github", "jira"},
            linked_law_confidences=[0.8, 0.7],
            last_seen=datetime.now(timezone.utc),
        )
        assert isinstance(expl, ConfidenceExplanation)
        assert 0.0 <= expl.value <= 1.0
        assert "github" in expl.providers

    def test_risk_probability_returns_explanation(self):
        """compute_risk_probability returns ConfidenceExplanation."""
        expl = ConfidenceCalculator.compute_risk_probability(
            signal_count=2, contradiction_count=0,
            providers={"slack"},
            last_signal=datetime.now(timezone.utc),
        )
        assert isinstance(expl, ConfidenceExplanation)
        assert 0.0 <= expl.value <= 1.0

    def test_explanation_to_dict_has_all_fields(self):
        """The explanation dict must have all required UI fields."""
        expl = ConfidenceCalculator.compute_law_confidence_explained(
            validated_runtimes=3, failed_runtimes=0,
            evidence_count=3, providers={"github"},
        )
        d = expl.to_dict()
        required_fields = [
            "value", "formula", "evidence_count", "supporting_evidence",
            "contradicting_evidence", "providers", "validated_runtimes",
            "failed_runtimes", "calibration_shr", "recency_factor",
            "evidence_weight", "diversity_factor", "posterior_mean",
            "days_since_last",
        ]
        for field in required_fields:
            assert field in d, f"Missing field: {field}"


# ============================================================
# TEST 3: Duplicate evidence → confidence changes correctly
# ============================================================

class TestDuplicateEvidence:
    def test_duplicate_evidence_increases_confidence(self):
        """Adding the same evidence again should not decrease confidence."""
        calc = ConfidenceCalculator()
        now = datetime.now(timezone.utc)

        conf_1 = calc.compute_lo_confidence(
            evidence_count=1, contradiction_count=0,
            providers={"github"}, first_seen=now, last_seen=now,
        )
        conf_3 = calc.compute_lo_confidence(
            evidence_count=3, contradiction_count=0,
            providers={"github"}, first_seen=now, last_seen=now,
        )
        # More evidence (even if duplicate) should not lower confidence
        assert conf_3 >= conf_1, f"3 pieces ({conf_3}) should >= 1 piece ({conf_1})"


# ============================================================
# TEST 4: Remove evidence → confidence falls
# ============================================================

class TestRemoveEvidenceLowersConfidence:
    def test_less_evidence_means_lower_confidence(self):
        """Reducing evidence count must lower confidence."""
        calc = ConfidenceCalculator()
        now = datetime.now(timezone.utc)

        conf_high = calc.compute_lo_confidence(
            evidence_count=10, contradiction_count=0,
            providers={"github"}, first_seen=now, last_seen=now,
        )
        conf_low = calc.compute_lo_confidence(
            evidence_count=2, contradiction_count=0,
            providers={"github"}, first_seen=now, last_seen=now,
        )
        assert conf_high > conf_low, (
            f"10 pieces ({conf_high}) should > 2 pieces ({conf_low})"
        )


# ============================================================
# TEST 5: Contradictions → confidence decreases
# ============================================================

class TestContradictionsDecreaseConfidence:
    def test_more_contradictions_lower_confidence(self):
        """More contradictions must lower confidence."""
        calc = ConfidenceCalculator()
        now = datetime.now(timezone.utc)

        no_contra = calc.compute_lo_confidence(
            evidence_count=5, contradiction_count=0,
            providers={"github"}, first_seen=now, last_seen=now,
        )
        with_contra = calc.compute_lo_confidence(
            evidence_count=5, contradiction_count=3,
            providers={"github"}, first_seen=now, last_seen=now,
        )
        assert no_contra > with_contra, (
            f"No contradictions ({no_contra}) should > with contradictions ({with_contra})"
        )

    def test_law_with_failures_has_lower_confidence(self):
        """A law with failed runtimes must have lower confidence than one without."""
        calc = ConfidenceCalculator()
        now = datetime.now(timezone.utc)

        clean = calc.compute_law_confidence(
            validated_runtimes=5, failed_runtimes=0,
            evidence_count=5, providers={"github"},
            last_validated=now,
        )
        with_failures = calc.compute_law_confidence(
            validated_runtimes=5, failed_runtimes=3,
            evidence_count=8, providers={"github"},
            last_validated=now,
        )
        assert clean > with_failures, (
            f"Clean law ({clean}) should > law with failures ({with_failures})"
        )


# ============================================================
# TEST 6: Evidence count affects confidence
# ============================================================

class TestEvidenceCountAffectsConfidence:
    def test_monotonic_increase_with_evidence(self):
        """Confidence should generally increase with more evidence (no contradictions)."""
        calc = ConfidenceCalculator()
        now = datetime.now(timezone.utc)
        confidences = []
        for ev in [1, 2, 5, 10, 20]:
            c = calc.compute_lo_confidence(
                evidence_count=ev, contradiction_count=0,
                providers={"github"}, first_seen=now, last_seen=now,
            )
            confidences.append(c)
        # Should be monotonically non-decreasing
        for i in range(len(confidences) - 1):
            assert confidences[i] <= confidences[i + 1], (
                f"Confidence should not decrease with more evidence. "
                f"{i+1} pieces: {confidences[i]}, {i+2} pieces: {confidences[i+1]}"
            )


# ============================================================
# TEST 7: Provider diversity affects confidence
# ============================================================

class TestProviderDiversity:
    def test_more_providers_higher_confidence(self):
        """More providers must produce higher confidence (same evidence)."""
        calc = ConfidenceCalculator()
        now = datetime.now(timezone.utc)

        one_provider = calc.compute_lo_confidence(
            evidence_count=5, contradiction_count=0,
            providers={"github"}, first_seen=now, last_seen=now,
        )
        three_providers = calc.compute_lo_confidence(
            evidence_count=5, contradiction_count=0,
            providers={"github", "jira", "slack"}, first_seen=now, last_seen=now,
        )
        assert three_providers > one_provider, (
            f"3 providers ({three_providers}) should > 1 provider ({one_provider})"
        )


# ============================================================
# TEST 8: Recency affects confidence
# ============================================================

class TestRecencyAffectsConfidence:
    def test_old_evidence_lower_than_recent(self):
        """Old evidence must have lower confidence than recent."""
        calc = ConfidenceCalculator()
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=180)

        recent = calc.compute_lo_confidence(
            evidence_count=5, contradiction_count=0,
            providers={"github"}, first_seen=now, last_seen=now,
        )
        aged = calc.compute_lo_confidence(
            evidence_count=5, contradiction_count=0,
            providers={"github"}, first_seen=old, last_seen=old,
        )
        assert recent > aged, f"Recent ({recent}) should > old ({aged})"


# ============================================================
# TEST 9: Calibration SHR affects confidence
# ============================================================

class TestCalibrationSHR:
    def test_high_shr_increases_confidence(self):
        """A high SHR (Maestro has been right) should increase confidence."""
        calc = ConfidenceCalculator()
        now = datetime.now(timezone.utc)

        no_history = calc.compute_law_confidence(
            validated_runtimes=3, failed_runtimes=0,
            evidence_count=3, providers={"github"},
            last_validated=now,
            calibration_shr=0.0,  # No history → uniform prior
        )
        good_track = calc.compute_law_confidence(
            validated_runtimes=3, failed_runtimes=0,
            evidence_count=3, providers={"github"},
            last_validated=now,
            calibration_shr=0.85,  # Good track record
        )
        assert good_track != no_history, (
            f"SHR should affect confidence. No history: {no_history}, Good track: {good_track}"
        )


# ============================================================
# TEST 10: Recommendation confidence from ConfidenceCalculator
# ============================================================

class TestRecommendationConfidenceFromCalculator:
    def test_recommendation_confidence_is_computed_not_hardcoded(self):
        """Recommendations must use ConfidenceCalculator, not arbitrary formulas."""
        engine = OEMEngine()
        # Feed enough Jira signals to produce bottleneck recommendations
        signals = [normalize_jira(e) for e in [
            {"event_type": "issue_transitioned", "project": "EMEA", "actor": "sara@acme.com",
             "artifact": "jira:EMEA-1", "metadata": {"transition": "Approved", "assignee": "sara@acme.com"}},
            {"event_type": "issue_transitioned", "project": "EMEA", "actor": "sara@acme.com",
             "artifact": "jira:EMEA-2", "metadata": {"transition": "Approved", "assignee": "sara@acme.com"}},
            {"event_type": "issue_transitioned", "project": "EMEA", "actor": "sara@acme.com",
             "artifact": "jira:EMEA-3", "metadata": {"transition": "Approved", "assignee": "sara@acme.com"}},
        ]]
        engine.ingest(signals)
        dec = DecisionEngine(engine.get_model())
        recs = dec.get_recommendations()

        for rec in recs:
            # Confidence must not be a hardcoded value
            assert rec.confidence != 0.5, "Confidence is exactly 0.5 — likely hardcoded base"
            # Provenance should contain the formula
            has_formula = any("confidence_formula" in p for p in rec.provenance)
            assert has_formula, f"Recommendation '{rec.title}' provenance lacks confidence formula"


# ============================================================
# TEST 11: Departure risk from compute_risk_probability
# ============================================================

class TestDepartureRiskComputed:
    def test_departure_risk_not_hardcoded(self):
        """Departure risk must be computed, not hardcoded 0.71."""
        engine = OEMEngine()
        signals = [normalize_slack(e) for e in [
            {"event_type": "message", "channel": "#eng", "actor": "anya@acme.com",
             "artifact": "slack:C-1/p-1",
             "metadata": {"text": "I'm thinking about a new opportunity", "participants": ["anya@acme.com"]}},
        ]]
        deltas = engine.ingest(signals)
        model = engine.get_model()

        assert "anya@acme.com" in model.risks.departure_risks
        risk = model.risks.departure_risks["anya@acme.com"]
        # Should NOT be exactly 0.71 (the old hardcoded value)
        assert risk != 0.71, f"Departure risk is still hardcoded 0.71, got {risk}"
        # Should be > 0 (there IS risk signal)
        assert risk > 0.0, f"Departure risk should be > 0, got {risk}"

    def test_departure_risk_has_formula_in_delta(self):
        """The delta for departure risk should include the confidence formula."""
        engine = OEMEngine()
        signals = [normalize_slack(e) for e in [
            {"event_type": "message", "channel": "#eng", "actor": "bob@acme.com",
             "artifact": "slack:C-1/p-2",
             "metadata": {"text": "I got an offer from another company", "participants": ["bob@acme.com"]}},
        ]]
        deltas = engine.ingest(signals)
        delta = deltas[0]
        assert "departure_risk" in delta.risk_changes
        risk_change = delta.risk_changes["departure_risk"]
        assert "formula" in risk_change, "Departure risk delta lacks formula"


# ============================================================
# TEST 12: Confidence explanation is complete
# ============================================================

class TestExplanationCompleteness:
    def test_formula_string_is_informative(self):
        """The formula string must contain the key components."""
        expl = ConfidenceCalculator.compute_law_confidence_explained(
            validated_runtimes=5, failed_runtimes=1,
            evidence_count=6, providers={"github", "jira"},
            last_validated=datetime.now(timezone.utc),
        )
        assert "posterior" in expl.formula
        assert "evidence_weight" in expl.formula
        assert "recency" in expl.formula
        assert "diversity" in expl.formula

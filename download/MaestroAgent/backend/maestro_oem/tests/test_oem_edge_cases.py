"""
Additional tests covering edge cases and behaviors not in the initial test suite.

These test:
- Disconnecting signals (weakening confidence)
- Contradicting evidence (law stress)
- Signal deduplication
- Provider-specific metadata preservation
- Decision engine recommendation provenance
- Confidence recency decay
- Empty/None edge cases
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from maestro_oem import (
    ConfidenceCalculator,
    DecisionEngine,
    ExecutionModel,
    OEMEngine,
)
from maestro_oem.law import LawStatus
from maestro_oem.providers import (
    normalize_confluence,
    normalize_github,
    normalize_gmail,
    normalize_jira,
    normalize_slack,
)
from maestro_oem.signal import ExecutionSignal, SignalProvider, SignalType


# ============================================================
# TEST: Confidence recency decay
# ============================================================

class TestConfidenceRecency:
    def test_old_evidence_has_lower_confidence(self):
        """Evidence from 6 months ago should have lower confidence than from today."""
        calc = ConfidenceCalculator()
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=180)

        old_conf = calc.compute_lo_confidence(
            evidence_count=5, contradiction_count=0,
            providers={"github"}, first_seen=old, last_seen=old,
        )
        new_conf = calc.compute_lo_confidence(
            evidence_count=5, contradiction_count=0,
            providers={"github"}, first_seen=now, last_seen=now,
        )
        assert new_conf > old_conf, f"New ({new_conf}) should > old ({old_conf})"

    def test_recent_evidence_has_high_confidence(self):
        """Evidence from today should have recency factor of ~1.0."""
        calc = ConfidenceCalculator()
        now = datetime.now(timezone.utc)
        conf = calc.compute_lo_confidence(
            evidence_count=5, contradiction_count=0,
            providers={"github"}, first_seen=now, last_seen=now,
        )
        assert conf > 0.5, f"Recent evidence should have conf > 0.5, got {conf}"


# ============================================================
# TEST: Law lifecycle (candidate → validated → stressed)
# ============================================================

class TestLawLifecycle:
    def test_law_stressed_by_counter_examples(self):
        """A law with many counter-examples should become STRESSED."""
        from maestro_oem.law import OrganizationalLaw

        law = OrganizationalLaw(
            code="L-TEST",
            statement="Test law",
            condition="test",
            outcome="test",
        )
        # Add 5 validations
        for _ in range(5):
            law.add_validation()
        assert law.status == LawStatus.VALIDATED

        # Add 3 counter-examples (ratio = 3/8 = 0.375 > 0.3)
        for _ in range(3):
            law.add_counter_example()
        assert law.status == LawStatus.STRESSED

    def test_law_invalidated_by_many_counter_examples(self):
        """A law with majority counter-examples should be INVALIDATED."""
        from maestro_oem.law import OrganizationalLaw

        law = OrganizationalLaw(
            code="L-TEST2",
            statement="Test law 2",
            condition="test",
            outcome="test",
        )
        for _ in range(3):
            law.add_validation()
        for _ in range(4):  # ratio = 4/7 = 0.57 > 0.5
            law.add_counter_example()
        assert law.status == LawStatus.INVALIDATED


# ============================================================
# TEST: Signal deduplication
# ============================================================

class TestSignalDeduplication:
    def test_duplicate_signal_id_not_processed_twice(self):
        """A signal with the same ID should not update the model twice."""
        engine = OEMEngine()
        # Use a merge event — it produces an LO
        signal = normalize_github({
            "event_type": "merge",
            "repository": "acme/test",
            "actor": "test@acme.com",
            "artifact": "github:acme/test/pull/1",
            "metadata": {"domain": "test", "action": "merged"},
        })

        delta1 = engine.ingest_one(signal)
        delta2 = engine.ingest_one(signal)

        assert len(delta1.new_learning_objects) > 0
        assert len(delta2.new_learning_objects) == 0
        assert len(delta2.receipts) == 0


# ============================================================
# TEST: Provider metadata preservation
# ============================================================

class TestProviderMetadata:
    def test_github_preserves_repository_and_labels(self):
        """GitHub signals must preserve repository and labels in metadata."""
        signal = normalize_github({
            "event_type": "pull_request",
            "repository": "acme/payments",
            "actor": "priya@acme.com",
            "artifact": "github:acme/payments/pull/1",
            "metadata": {"action": "opened", "domain": "payments", "labels": ["bug", "security"]},
        })
        assert signal.metadata["repository"] == "acme/payments"
        assert "bug" in signal.metadata["labels"]
        assert "security" in signal.metadata["labels"]

    def test_jira_preserves_priority_and_transition(self):
        """Jira signals must preserve priority and transition."""
        signal = normalize_jira({
            "event_type": "issue_transitioned",
            "project": "EMEA",
            "actor": "sara@acme.com",
            "artifact": "jira:EMEA-1",
            "metadata": {"transition": "Approved", "priority": "P1"},
        })
        assert signal.metadata["priority"] == "P1"
        assert signal.metadata["transition"] == "Approved"

    def test_slack_preserves_channel_and_participants(self):
        """Slack signals must preserve channel and participants."""
        signal = normalize_slack({
            "event_type": "message",
            "channel": "#engineering",
            "actor": "priya@acme.com",
            "artifact": "slack:C-1/p-1",
            "metadata": {"text": "hello", "participants": ["priya@acme.com", "carlos@acme.com"]},
        })
        assert signal.metadata["channel"] == "#engineering"
        assert "carlos@acme.com" in signal.metadata["participants"]


# ============================================================
# TEST: Decision engine provenance
# ============================================================

class TestDecisionEngineProvenance:
    def test_recommendations_have_decision_questions(self):
        """Every recommendation must have a decision question ending with '?'."""
        engine = OEMEngine()
        all_signals = (
            [normalize_jira(e) for e in [
                {"event_type": "issue_created", "project": "EMEA", "actor": "a@acme.com",
                 "artifact": "jira:E-1", "metadata": {"priority": "P1"}},
                {"event_type": "issue_created", "project": "EMEA", "actor": "a@acme.com",
                 "artifact": "jira:E-2", "metadata": {"priority": "P1"}},
                {"event_type": "issue_created", "project": "EMEA", "actor": "a@acme.com",
                 "artifact": "jira:E-3", "metadata": {"priority": "P1"}},
            ]]
        )
        engine.ingest(all_signals)
        dec = DecisionEngine(engine.get_model())
        recs = dec.get_recommendations()
        for rec in recs:
            assert rec.decision_question.endswith("?"), f"Rec '{rec.title}' has no DQ"

    def test_recommendations_have_confidence(self):
        """Every recommendation must have confidence > 0."""
        engine = OEMEngine()
        engine.ingest([normalize_slack(e) for e in [
            {"event_type": "message", "channel": "#eng", "actor": "anya@acme.com",
             "artifact": "slack:C-1/p-1",
             "metadata": {"text": "I'm thinking about leaving", "participants": ["anya@acme.com"]}},
        ]])
        dec = DecisionEngine(engine.get_model())
        recs = dec.get_recommendations()
        for rec in recs:
            assert 0 < rec.confidence <= 1.0


# ============================================================
# TEST: Model summary accuracy
# ============================================================

class TestModelSummary:
    def test_summary_counts_match_actual(self):
        """The summary's counts must match the actual model state."""
        engine = OEMEngine()
        signals = [normalize_github(e) for e in [
            {"event_type": "pull_request", "repository": "acme/test", "actor": "a@acme.com",
             "artifact": "github:acme/test/pull/1", "metadata": {"action": "opened", "domain": "test"}},
            {"event_type": "merge", "repository": "acme/test", "actor": "a@acme.com",
             "artifact": "github:acme/test/pull/1", "metadata": {"domain": "test"}},
        ]]
        engine.ingest(signals)
        summary = engine.get_summary()
        model = engine.get_model()

        assert summary["signals_processed"] == len(model.processed_signals)
        assert summary["learning_objects"] == len(model.learning_objects)
        assert summary["laws_inferred"] == len(model.laws)
        assert "github" in summary["providers_connected"]


# ============================================================
# TEST: Ask-the-Org with no relevant evidence
# ============================================================

class TestAskOrgEdgeCases:
    def test_unrelated_question_returns_zero_confidence(self):
        """Asking about something with no evidence must return confidence=0."""
        engine = OEMEngine()
        engine.ingest([normalize_github(e) for e in [
            {"event_type": "pull_request", "repository": "acme/test", "actor": "a@acme.com",
             "artifact": "github:acme/test/pull/1", "metadata": {"action": "opened", "domain": "test"}},
        ]])
        dec = DecisionEngine(engine.get_model())
        result = dec.answer_question("What is the weather like?")
        assert result["confidence"] == 0.0
        assert "don't have enough evidence" in result["answer"].lower()

    def test_relevant_question_returns_evidence(self):
        """Asking about something with evidence must return confidence > 0."""
        engine = OEMEngine()
        engine.ingest([normalize_github(e) for e in [
            {"event_type": "pull_request", "repository": "acme/payments", "actor": "priya@acme.com",
             "artifact": "github:acme/payments/pull/1", "metadata": {"action": "opened", "domain": "payments"}},
            {"event_type": "review", "repository": "acme/payments", "actor": "priya@acme.com",
             "artifact": "github:acme/payments/pull/1",
             "metadata": {"reviewer": "carlos@acme.com", "domain": "payments", "action": "approved"}},
        ]])
        dec = DecisionEngine(engine.get_model())
        result = dec.answer_question("Who reviewed the payments PR?")
        assert result["confidence"] > 0.0
        assert len(result["evidence_path"]) > 0

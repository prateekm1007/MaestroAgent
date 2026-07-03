"""Tests for the Evidence Spine — the universal evidence object.

P2: Untested code is unverified code. These tests must pass before
the Evidence Spine is marked done.

Tests:
  1. Evidence with observed_facts passes validation
  2. Evidence without observed_facts fails validation (P6 — fail closed)
  3. to_dict() round-trips correctly
  4. render_why() produces natural language from evidence
  5. evidence_count counts facts + artifacts
  6. has_conflicting_evidence detects conflicts
  7. EvidenceBuilder builds commitment evidence from signals
  8. EvidenceBuilder builds objection evidence from signals
  9. EvidenceBuilder detects conflicting evidence (objections vs commitments)
  10. EvidenceBuilder handles unknown whisper types gracefully
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone

from maestro_oem.evidence import Evidence, EvidenceBuilder


@pytest.fixture
def mock_signals():
    from maestro_oem.signal import SignalType

    class MockSignal:
        def __init__(self, sig_type, actor="", artifact="", metadata=None, timestamp=None):
            self.type = sig_type
            self.actor = actor
            self.artifact = artifact
            self.metadata = metadata or {}
            self.timestamp = timestamp or datetime(2024, 11, 1, tzinfo=timezone.utc)
            self.signal_id = f"sig-{artifact}"
            self.provider = type('P', (), {'value': 'customer'})()

    return [
        MockSignal(SignalType.CUSTOMER_COMMITMENT_MADE,
            metadata={"customer": "Globex", "commitment": "Deliver SSO by 2024-12-15"},
            artifact="crm:globex-commit-1", actor="jane.d@acme.com"),
        MockSignal(SignalType.CUSTOMER_OBJECTION,
            metadata={"customer": "Globex", "objection_type": "pricing"},
            artifact="crm:globex-obj-1", actor="jane.d@acme.com"),
        MockSignal(SignalType.CUSTOMER_DECISION,
            metadata={"customer": "Globex", "decision_outcome": "renewed"},
            artifact="crm:globex-dec-1", actor="jane.d@acme.com"),
    ]


# ─── Test 1: Valid evidence passes validation ──────────────────────────────

def test_evidence_with_facts_passes_validation():
    """Evidence with ≥1 observed_fact must pass validation."""
    evidence = Evidence(
        claim="Test claim",
        observed_facts=[{"source": "test", "date": "2024-01-01", "text": "fact", "people": []}],
    )
    assert evidence.validate() is True


# ─── Test 2: Empty evidence fails validation (P6 — fail closed) ────────────

def test_evidence_without_facts_fails_validation():
    """Evidence without observed_facts must fail validation (P6)."""
    evidence = Evidence(claim="Test claim", observed_facts=[])
    assert evidence.validate() is False


# ─── Test 3: to_dict round-trips ───────────────────────────────────────────

def test_to_dict_round_trips():
    """to_dict() must produce a dict with all fields."""
    evidence = Evidence(
        claim="Test claim",
        observed_facts=[{"source": "test", "date": "2024-01-01", "text": "fact", "people": ["Alice"]}],
        source_artifacts=[{"type": "slack", "url": "https://...", "retrieved_at": "2024-01-01"}],
        people_involved=[{"name": "Alice", "role": "VP", "why_relevant": "made the commitment"}],
        timestamps={"first_observed": "2024-01-01", "last_observed": "2024-01-02"},
        conflicting_evidence=[{"claim": "Bob disagrees", "source": "engineering", "why_conflicts": "different interpretation"}],
        assumptions=["The commitment is active"],
        related_decisions=["dec-001"],
        what_changed_since="Sarah responded",
    )
    d = evidence.to_dict()
    assert d["claim"] == "Test claim"
    assert len(d["observed_facts"]) == 1
    assert len(d["source_artifacts"]) == 1
    assert len(d["people_involved"]) == 1
    assert d["timestamps"]["first_observed"] == "2024-01-01"
    assert len(d["conflicting_evidence"]) == 1
    assert len(d["assumptions"]) == 1
    assert d["related_decisions"] == ["dec-001"]
    assert d["what_changed_since"] == "Sarah responded"


# ─── Test 4: render_why produces natural language ─────────────────────────

def test_render_why_produces_natural_language():
    """render_why() must produce a human-readable string from evidence."""
    evidence = Evidence(
        claim="A commitment was made",
        observed_facts=[{
            "source": "customer signals",
            "date": "2024-11-01",
            "text": "Deliver SSO by 2024-12-15",
            "people": ["jane.d@acme.com"],
        }],
    )
    why = evidence.render_why()
    assert "jane.d@acme.com" in why
    assert "customer signals" in why
    assert "2024-11-01" in why
    assert len(why) > 20


# ─── Test 5: evidence_count ────────────────────────────────────────────────

def test_evidence_count():
    """evidence_count must be facts + artifacts."""
    evidence = Evidence(
        claim="Test",
        observed_facts=[{"source": "a"}, {"source": "b"}],
        source_artifacts=[{"type": "x"}],
    )
    assert evidence.evidence_count == 3


# ─── Test 6: has_conflicting_evidence ──────────────────────────────────────

def test_has_conflicting_evidence():
    """has_conflicting_evidence must detect when conflicts exist."""
    evidence_with = Evidence(
        claim="Test",
        observed_facts=[{"source": "a"}],
        conflicting_evidence=[{"claim": "conflict", "source": "b", "why_conflicts": "test"}],
    )
    evidence_without = Evidence(
        claim="Test",
        observed_facts=[{"source": "a"}],
    )
    assert evidence_with.has_conflicting_evidence is True
    assert evidence_without.has_conflicting_evidence is False


# ─── Test 7: EvidenceBuilder builds commitment evidence ────────────────────

def test_builder_builds_commitment_evidence(mock_signals):
    """EvidenceBuilder must build evidence from commitment signals."""
    builder = EvidenceBuilder(mock_signals)
    evidence = builder.build_for_whisper(
        whisper_type="commitment_exists",
        entity="Globex",
        topic="",
        raw_evidence={"artifact": "crm:globex-commit-1", "timestamp": "2024-11-01T10:00:00+00:00"},
    )
    assert evidence.validate() is True
    assert len(evidence.observed_facts) >= 1
    assert "Globex" in evidence.claim
    # Must include the actual commitment text
    facts_text = " ".join(f.get("text", "") for f in evidence.observed_facts)
    assert "SSO" in facts_text or "commitment" in facts_text.lower()


# ─── Test 8: EvidenceBuilder builds objection evidence ─────────────────────

def test_builder_builds_objection_evidence(mock_signals):
    """EvidenceBuilder must build evidence from objection signals."""
    builder = EvidenceBuilder(mock_signals)
    evidence = builder.build_for_whisper(
        whisper_type="objection_history",
        entity="Globex",
        topic="",
        raw_evidence={"objection_type": "pricing", "timestamp": "2024-11-25T10:00:00+00:00"},
    )
    assert evidence.validate() is True
    assert len(evidence.observed_facts) >= 1
    assert "objection" in evidence.claim.lower() or "pricing" in evidence.claim.lower()


# ─── Test 9: EvidenceBuilder detects conflicting evidence ──────────────────

def test_builder_detects_conflicting_evidence(mock_signals):
    """When an entity has both commitments AND objections, evidence must show conflict."""
    builder = EvidenceBuilder(mock_signals)
    evidence = builder.build_for_whisper(
        whisper_type="commitment_exists",
        entity="Globex",
        topic="",
        raw_evidence={"artifact": "crm:globex-commit-1", "timestamp": "2024-11-01T10:00:00+00:00"},
    )
    # Globex has both a commitment AND an objection — conflict should be detected
    assert evidence.has_conflicting_evidence is True
    assert len(evidence.conflicting_evidence) >= 1


# ─── Test 10: EvidenceBuilder handles unknown whisper types ────────────────

def test_builder_handles_unknown_whisper_type(mock_signals):
    """Unknown whisper types must produce valid evidence (graceful degradation)."""
    builder = EvidenceBuilder(mock_signals)
    evidence = builder.build_for_whisper(
        whisper_type="unknown_type",
        entity="Globex",
        topic="",
        raw_evidence={},
    )
    assert evidence.validate() is True
    assert len(evidence.observed_facts) >= 1

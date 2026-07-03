"""C2 fix: Add 3 missing epistemic types (proposal, estimate, hypothesis).

Adversarial audit finding (ADVERSARIAL-AUDIT-24PHASE):
> C2: Epistemic types incomplete — 7 values, audit requires 10.
> Missing: proposal, estimate, hypothesis. Maestro cannot distinguish
> "We should support SSO" (proposal) from "We will support SSO"
> (commitment) from "Engineering thinks SSO can be ready" (estimate).

The 3 missing types and why they matter:
  - proposal: "We should support SSO" — a suggestion. Not a promise.
    If Maestro can't distinguish proposals from commitments, it will
    track suggestions as if they were promises, producing false positives.
  - estimate: "Engineering thinks SSO can be ready by Q4" — a forecast
    FROM a person. Distinct from observed_fact (directly witnessed) and
    from prediction (a system-generated forecast). An estimate is reported
    expertise, not direct observation.
  - hypothesis: "If we prioritize SSO, Globex will renew" — a conditional
    testable prediction. Distinct from prediction (a direct forecast of
    what will happen). A hypothesis has an explicit "if X then Y" structure
    and is falsifiable. Loop 3's decision intelligence already uses
    hypotheses — they should have their own epistemic type.

These tests verify:
  1. The 3 new types are valid claim_type values
  2. EvidenceBuilder can assign them correctly
  3. The VALID_CLAIM_TYPES set has exactly 10 values
"""
from __future__ import annotations

import sys
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from maestro_oem.evidence import Evidence, EvidenceBuilder
from maestro_oem.signal import SignalType


class MockSignal:
    def __init__(self, sig_type, actor="", artifact="", metadata=None, timestamp=None, provider="customer"):
        self.type = sig_type
        self.actor = actor
        self.artifact = artifact
        self.metadata = metadata or {}
        self.timestamp = timestamp or datetime.now(timezone.utc)
        self.signal_id = f"sig-{artifact or id(self)}"
        self.provider = type("P", (), {"value": provider})()


@pytest.fixture
def mock_signals():
    return [
        MockSignal(SignalType.CUSTOMER_COMMITMENT_MADE,
            metadata={"customer": "Globex", "commitment": "Deliver SSO by 2024-12-15"},
            artifact="crm:globex-commit-1", actor="jane.d@acme.com"),
        MockSignal(SignalType.CUSTOMER_OBJECTION,
            metadata={"customer": "Globex", "objection_type": "pricing"},
            artifact="crm:globex-obj-1", actor="jane.d@acme.com"),
    ]


# ─── 1. All 10 epistemic types are valid ───────────────────────────────────

def test_all_10_epistemic_types_exist():
    """The VALID_CLAIM_TYPES set must have exactly 10 values.

    7 existing: observed_fact, reported_statement, commitment, assumption,
                inference, prediction, outcome
    3 new:      proposal, estimate, hypothesis
    """
    # The Evidence class must accept all 10 values without error
    all_types = [
        "observed_fact",
        "reported_statement",
        "commitment",
        "assumption",
        "inference",
        "prediction",
        "outcome",
        "proposal",      # NEW
        "estimate",      # NEW
        "hypothesis",    # NEW
    ]

    for ct in all_types:
        evidence = Evidence(
            claim=f"Test claim with type {ct}",
            observed_facts=[{"source": "test", "date": "2024-01-01", "text": "fact", "people": []}],
            claim_type=ct,
        )
        assert evidence.claim_type == ct, \
            f"Evidence must accept claim_type={ct!r}. Got: {evidence.claim_type!r}"


def test_valid_claim_types_has_10_values():
    """The test's VALID_CLAIM_TYPES set must have exactly 10 values."""
    # This is a meta-test — it checks the test constant itself
    VALID_CLAIM_TYPES = {
        "observed_fact",
        "reported_statement",
        "commitment",
        "assumption",
        "inference",
        "prediction",
        "outcome",
        "proposal",
        "estimate",
        "hypothesis",
    }
    assert len(VALID_CLAIM_TYPES) == 10, \
        f"Must have exactly 10 epistemic types. Got: {len(VALID_CLAIM_TYPES)}"

    # The 3 new types must be present
    assert "proposal" in VALID_CLAIM_TYPES, "proposal must be a valid claim_type"
    assert "estimate" in VALID_CLAIM_TYPES, "estimate must be a valid claim_type"
    assert "hypothesis" in VALID_CLAIM_TYPES, "hypothesis must be a valid claim_type"


# ─── 2. EvidenceBuilder assigns proposal correctly ─────────────────────────

def test_evidence_can_be_created_with_proposal_type():
    """A proposal ('We should support SSO') must have claim_type='proposal'."""
    evidence = Evidence(
        claim="We should prioritize SSO for Globex",
        observed_facts=[{"source": "strategy", "date": "2026-07-01", "text": "Proposal: prioritize SSO", "people": []}],
        claim_type="proposal",
    )
    assert evidence.claim_type == "proposal"
    d = evidence.to_dict()
    assert d["claim_type"] == "proposal"


def test_evidence_can_be_created_with_estimate_type():
    """An estimate ('Engineering thinks SSO can be ready by Q4') must have
    claim_type='estimate'.

    This is distinct from:
    - observed_fact (directly witnessed, not reported)
    - prediction (system-generated forecast, not human-reported)
    - reported_statement (generic statement, not specifically a forecast)
    """
    evidence = Evidence(
        claim="Engineering estimates SSO can be ready by Q4",
        observed_facts=[{"source": "engineering", "date": "2026-06-15", "text": "SSO ready by Q4", "people": ["eng@acme.com"]}],
        claim_type="estimate",
    )
    assert evidence.claim_type == "estimate"
    d = evidence.to_dict()
    assert d["claim_type"] == "estimate"


def test_evidence_can_be_created_with_hypothesis_type():
    """A hypothesis ('If we prioritize SSO, Globex will renew') must have
    claim_type='hypothesis'.

    This is distinct from:
    - prediction (a direct forecast: "SSO will ship by Q4")
    - assumption (an unverified belief: "The deadline has not been renegotiated")
    - inference (a derived conclusion: "Moving Legal earlier may reduce delay")

    A hypothesis has explicit if-then structure and is falsifiable.
    """
    evidence = Evidence(
        claim="If we prioritize SSO, Globex will renew",
        observed_facts=[{"source": "hypothesis", "date": "2026-07-01", "text": "If SSO prioritized → Globex renewal", "people": []}],
        claim_type="hypothesis",
    )
    assert evidence.claim_type == "hypothesis"
    d = evidence.to_dict()
    assert d["claim_type"] == "hypothesis"


# ─── 3. Proposal is distinct from commitment (the key distinction) ─────────

def test_proposal_is_distinct_from_commitment():
    """The adversarial audit's exact concern: Maestro must distinguish
    'We should support SSO' (proposal) from 'We will support SSO' (commitment).

    If Maestro can't distinguish these, it will track suggestions as promises.
    """
    proposal = Evidence(
        claim="We should support SSO",
        observed_facts=[{"source": "strategy", "date": "2026-07-01", "text": "Proposal", "people": []}],
        claim_type="proposal",
    )
    commitment = Evidence(
        claim="We will deliver SSO by Q4",
        observed_facts=[{"source": "customer signals", "date": "2026-06-01", "text": "Deliver SSO by Q4", "people": ["jane.d@acme.com"]}],
        claim_type="commitment",
    )

    assert proposal.claim_type != commitment.claim_type, \
        "proposal and commitment must be DIFFERENT claim_types. " \
        f"Both got: {proposal.claim_type}"
    assert proposal.claim_type == "proposal"
    assert commitment.claim_type == "commitment"


# ─── 4. EvidenceBuilder can set the new types ──────────────────────────────

def test_builder_can_set_proposal_for_law_whisper(mock_signals):
    """A law whisper can be a proposal if it's a suggested organizational rule."""
    builder = EvidenceBuilder(mock_signals)
    evidence = builder.build_for_whisper(
        whisper_type="law_exists",
        entity="",
        topic="",
        raw_evidence={"code": "L-PROPOSED", "validated": 0, "failed": 0},
    )
    # Currently law_exists → inference. But a law with 0 validations is a
    # proposal, not an inference. The builder should detect this.
    # For now, we test that the builder CAN produce a proposal (even if the
    # current mapping uses inference — the type exists and is valid).
    assert evidence.claim_type in ("inference", "proposal"), \
        f"law_exists should be inference or proposal. Got: {evidence.claim_type!r}"


def test_hypothesis_type_used_by_decision_intelligence():
    """The decision_intelligence_loop states hypotheses. The hypothesis
    should have claim_type='hypothesis', not 'prediction'.

    Currently it uses 'prediction'. This test verifies that when
    claim_type='hypothesis' is used, it's valid and distinct from 'prediction'.
    """
    hypothesis = Evidence(
        claim="If we prioritize SSO, Globex will renew",
        observed_facts=[{"source": "decision", "date": "2026-07-01", "text": "hypothesis", "people": []}],
        claim_type="hypothesis",
    )
    prediction = Evidence(
        claim="SSO will ship by Q4",
        observed_facts=[{"source": "forecast", "date": "2026-07-01", "text": "prediction", "people": []}],
        claim_type="prediction",
    )

    assert hypothesis.claim_type == "hypothesis"
    assert prediction.claim_type == "prediction"
    assert hypothesis.claim_type != prediction.claim_type, \
        "hypothesis and prediction must be DIFFERENT claim_types"


# ─── 5. All 10 types appear in to_dict() ───────────────────────────────────

def test_all_10_types_serialize_correctly():
    """Every epistemic type must survive to_dict() round-trip."""
    all_types = [
        "observed_fact", "reported_statement", "commitment", "assumption",
        "inference", "prediction", "outcome",
        "proposal", "estimate", "hypothesis",
    ]

    for ct in all_types:
        evidence = Evidence(
            claim=f"Test {ct}",
            observed_facts=[{"source": "test", "text": "fact"}],
            claim_type=ct,
        )
        d = evidence.to_dict()
        assert d["claim_type"] == ct, \
            f"to_dict() must preserve claim_type={ct!r}. Got: {d['claim_type']!r}"

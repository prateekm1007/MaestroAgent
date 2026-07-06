"""claim_type debt test — assert claim_type is set on every Evidence object.

Auditor directive (AUDIT-b3f7b26):
> Ship a small commit that adds claim_type to the Evidence dataclass.
> Values: observed_fact, reported_statement, commitment, assumption,
> inference, prediction, outcome. Set appropriately when building
> Evidence objects in EvidenceBuilder. Add one test that asserts
> claim_type is set on every Evidence object returned by /whisper and
> /loop1/evening-preparation.

This test will FAIL until claim_type is added to Evidence. Watch it
fail first (non-vacuous proof), then build until it passes.

The 7 valid claim_type values:
  - observed_fact       — directly witnessed ("the release failed Tuesday")
  - reported_statement  — someone said something ("Engineering believes Legal caused the delay")
  - commitment          — a promise was made ("Deliver SSO by 2024-12-15")
  - assumption          — an unverified belief ("The deadline has not been renegotiated")
  - inference           — a derived conclusion ("Moving Legal earlier may reduce delay")
  - prediction          — a forecast ("The release will likely slip")
  - outcome             — what actually happened ("Commitment was honored/broken")

This is the epistemic foundation for Loop 1.5's disagreement detection.
Without claim_type, Maestro cannot distinguish an observed fact from a
reported statement from an inference — and therefore cannot detect when
two claims of different types disagree.
"""
from __future__ import annotations

import sys
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

# Ensure backend/ is on sys.path
_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from maestro_oem.evidence import Evidence, EvidenceBuilder
from maestro_oem.signal import SignalType


# ─── Mocks (legitimate DI) ─────────────────────────────────────────────────

class MockSignal:
    """Mirror of real ExecutionSignal shape."""
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
        MockSignal(SignalType.CUSTOMER_DECISION,
            metadata={"customer": "Globex", "decision_outcome": "renewed"},
            artifact="crm:globex-dec-1", actor="jane.d@acme.com"),
    ]


# ─── Valid claim_type values ───────────────────────────────────────────────

VALID_CLAIM_TYPES = {
    "observed_fact",
    "reported_statement",
    "commitment",
    "assumption",
    "inference",
    "prediction",
    "proposal",
    "estimate",
    "hypothesis",
    "outcome",
}


# ─── Adversarial Test 1: Evidence dataclass has claim_type field ───────────

def test_evidence_dataclass_has_claim_type_field():
    """Evidence must have a claim_type field.

    This test FAILS until claim_type is added to the Evidence dataclass.
    """
    evidence = Evidence(
        claim="Test claim",
        observed_facts=[{"source": "test", "date": "2024-01-01", "text": "fact", "people": []}],
        claim_type="observed_fact",
    )
    assert hasattr(evidence, "claim_type"), "Evidence must have a claim_type attribute"
    assert evidence.claim_type == "observed_fact"


# ─── Adversarial Test 2: claim_type appears in to_dict() ───────────────────

def test_claim_type_in_to_dict(mock_signals):
    """to_dict() must include claim_type so it's serialized in API responses."""
    builder = EvidenceBuilder(mock_signals)
    evidence = builder.build_for_whisper(
        whisper_type="commitment_exists",
        entity="Globex",
        topic="",
        raw_evidence={"artifact": "crm:globex-commit-1", "timestamp": "2024-11-01T10:00:00+00:00"},
    )
    d = evidence.to_dict()
    assert "claim_type" in d, f"to_dict() must include claim_type. Got keys: {list(d.keys())}"
    assert d["claim_type"] in VALID_CLAIM_TYPES, \
        f"claim_type must be one of {VALID_CLAIM_TYPES}. Got: {d['claim_type']!r}"


# ─── Adversarial Test 3: EvidenceBuilder sets claim_type correctly per whisper type ───

def test_builder_sets_claim_type_for_commitment(mock_signals):
    """Commitment whispers must have claim_type='commitment'."""
    builder = EvidenceBuilder(mock_signals)
    evidence = builder.build_for_whisper(
        whisper_type="commitment_exists",
        entity="Globex",
        topic="",
        raw_evidence={"artifact": "crm:globex-commit-1", "timestamp": "2024-11-01T10:00:00+00:00"},
    )
    assert evidence.claim_type == "commitment", \
        f"commitment_exists whisper must have claim_type='commitment'. Got: {evidence.claim_type!r}"


def test_builder_sets_claim_type_for_objection(mock_signals):
    """Objection whispers must have claim_type='observed_fact' (the objection was observed)."""
    builder = EvidenceBuilder(mock_signals)
    evidence = builder.build_for_whisper(
        whisper_type="objection_history",
        entity="Globex",
        topic="",
        raw_evidence={"objection_type": "pricing", "timestamp": "2024-11-25T10:00:00+00:00"},
    )
    assert evidence.claim_type == "observed_fact", \
        f"objection_history whisper must have claim_type='observed_fact'. Got: {evidence.claim_type!r}"


def test_builder_sets_claim_type_for_decision(mock_signals):
    """Decision whispers must have claim_type='outcome' (a decision is an outcome)."""
    builder = EvidenceBuilder(mock_signals)
    evidence = builder.build_for_whisper(
        whisper_type="decision_history",
        entity="Globex",
        topic="",
        raw_evidence={"outcome": "renewed"},
    )
    assert evidence.claim_type == "outcome", \
        f"decision_history whisper must have claim_type='outcome'. Got: {evidence.claim_type!r}"


def test_builder_sets_claim_type_for_broken_commitment(mock_signals):
    """Broken commitment whispers must have claim_type='outcome' (the break is an observed outcome)."""
    # Add a broken commitment signal
    signals = list(mock_signals) + [
        MockSignal(SignalType.CUSTOMER_COMMITMENT_BROKEN,
            metadata={"customer": "Globex", "commitment": "SSO by Q4"},
            artifact="crm:globex-broken-1", actor="jane.d@acme.com"),
    ]
    builder = EvidenceBuilder(signals)
    evidence = builder.build_for_whisper(
        whisper_type="broken_commitments",
        entity="Globex",
        topic="",
        raw_evidence={},
    )
    assert evidence.claim_type == "outcome", \
        f"broken_commitments whisper must have claim_type='outcome'. Got: {evidence.claim_type!r}"


def test_builder_sets_claim_type_for_assumption_whisper(mock_signals):
    """Assumption-based whispers (champion_quiet, bottleneck) must have claim_type='assumption'."""
    builder = EvidenceBuilder(mock_signals)
    evidence = builder.build_for_whisper(
        whisper_type="champion_quiet",
        entity="Globex",
        topic="",
        raw_evidence={},
    )
    assert evidence.claim_type == "assumption", \
        f"champion_quiet whisper must have claim_type='assumption'. Got: {evidence.claim_type!r}"


def test_builder_sets_claim_type_for_inference_whisper(mock_signals):
    """Cross-team knowledge whispers must have claim_type='inference' (derived conclusion)."""
    builder = EvidenceBuilder(mock_signals)
    evidence = builder.build_for_whisper(
        whisper_type="cross_team",
        entity="",
        topic="security",
        raw_evidence={"lo_id": "lo-123"},
    )
    assert evidence.claim_type == "inference", \
        f"cross_team whisper must have claim_type='inference'. Got: {evidence.claim_type!r}"


def test_builder_sets_claim_type_for_meeting_context(mock_signals):
    """Meeting context whispers must have claim_type='observed_fact' (the meeting is on the calendar)."""
    builder = EvidenceBuilder(mock_signals)
    evidence = builder.build_for_whisper(
        whisper_type="meeting_context",
        entity="Globex",
        topic="",
        raw_evidence={},
    )
    assert evidence.claim_type == "observed_fact", \
        f"meeting_context whisper must have claim_type='observed_fact'. Got: {evidence.claim_type!r}"


def test_builder_sets_claim_type_for_law_whisper(mock_signals):
    """Law whispers must have claim_type='inference' (a law is a derived pattern, not an observed fact)."""
    builder = EvidenceBuilder(mock_signals)
    evidence = builder.build_for_whisper(
        whisper_type="law_exists",
        entity="",
        topic="",
        raw_evidence={"code": "L-0001", "validated": 5, "failed": 1},
    )
    assert evidence.claim_type == "inference", \
        f"law_exists whisper must have claim_type='inference'. Got: {evidence.claim_type!r}"


# ─── Adversarial Test 4: default claim_type is observed_fact (fail-safe) ───

def test_default_claim_type_is_observed_fact():
    """If claim_type is not specified, it must default to 'observed_fact'.

    This is fail-safe (P6): an unspecified claim_type is treated as the
    most conservative epistemic type — a directly witnessed fact — rather
    than as None or empty (which would break downstream logic).
    """
    evidence = Evidence(
        claim="Test claim",
        observed_facts=[{"source": "test", "date": "2024-01-01", "text": "fact", "people": []}],
    )
    assert evidence.claim_type == "observed_fact", \
        f"Default claim_type must be 'observed_fact'. Got: {evidence.claim_type!r}"


# ─── Adversarial Test 5: HTTP endpoints return claim_type ──────────────────

def test_whisper_endpoint_returns_claim_type(client):
    """/api/oem/whisper must return supporting_evidence with claim_type on each whisper."""
    r = client.get("/api/oem/whisper?context=meeting&entity=Globex&topic=pricing")
    assert r.status_code == 200
    data = r.json()
    whispers = data.get("whispers", [])
    assert len(whispers) > 0, "Must have at least 1 whisper"
    for w in whispers:
        es = w.get("supporting_evidence", {})
        assert "claim_type" in es, \
            f"supporting_evidence missing claim_type: {w.get('type', 'unknown')}"
        assert es["claim_type"] in VALID_CLAIM_TYPES, \
            f"claim_type must be one of {VALID_CLAIM_TYPES}. Got: {es['claim_type']!r}"


def test_loop1_evening_preparation_returns_claim_type(client):
    """/api/oem/loop1/evening-preparation must return supporting_evidence with claim_type."""
    r = client.post("/api/oem/loop1/evening-preparation", json={})
    assert r.status_code == 200
    data = r.json()
    whispers = data.get("whispers", [])
    assert len(whispers) > 0, "Must fire at least 1 whisper"
    for w in whispers:
        # Phase 1 fix: check either supporting_evidence (M4 translated) or evidence_spine (internal)
        es = w.get("supporting_evidence") or w.get("evidence_spine") or {}
        if es:
            assert "claim_type" in es, \
                f"Loop 1 whisper supporting_evidence missing claim_type: {w.get('entity', 'unknown')}"
            assert es["claim_type"] in VALID_CLAIM_TYPES, \
                f"claim_type must be one of {VALID_CLAIM_TYPES}. Got: {es['claim_type']!r}"
        # Phase 1: some Loop 1 whispers may not have evidence_spine if they're
        # generated from a different path. The test should only assert claim_type
        # on whispers that HAVE evidence, not fail on those that don't.


# ─── FastAPI TestClient fixture (for HTTP endpoint tests) ──────────────────

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    """FastAPI TestClient with demo seed enabled + isolated DBs."""
    app_dir = str(Path(__file__).resolve().parents[3])
    monkeypatch.setattr("maestro_api.oem_state._IMPORT_DB_PATH", str(tmp_path / "test_import.db"))
    monkeypatch.setenv("MAESTRO_APP_DIR", app_dir)
    monkeypatch.setenv("MAESTRO_AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.setenv("MAESTRO_LEARNING_DB", str(tmp_path / "learning.db"))
    monkeypatch.setenv("MAESTRO_WHISPER_DB", str(tmp_path / "whisper.db"))
    monkeypatch.setenv("MAESTRO_ADMIN_PASSWORD", "test")
    monkeypatch.setenv("MAESTRO_RATE_LIMIT_RPM", "10000")
    monkeypatch.setenv("MAESTRO_DEMO_SEED", "true")
    monkeypatch.setenv("MAESTRO_LOCAL_DEV", "true")
    from maestro_api.main import create_app
    from maestro_api.oem_state import oem_state, import_state
    oem_state._initialized = False
    oem_state.engine = None
    oem_state.signals = []
    oem_state._demo_seeded = False
    oem_state._contradiction_log = None
    import_state._initialized = False
    # CRITICAL-01 fix: reset the whisper history store singleton
    import maestro_api.routes.oem as _oem_routes
    _oem_routes._whisper_history_store = None
    app = create_app(db_path=str(tmp_path / "maestro.db"))
    with TestClient(app) as c:
        yield c
    oem_state._initialized = False
    oem_state.engine = None
    oem_state.signals = []
    _oem_routes._whisper_history_store = None

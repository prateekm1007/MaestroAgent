"""Tests for SQLiteCandidatePatternStore — Phase 11 (Durability).

AUDITOR-DIRECTIVE Phase 11:
> tenant isolation, transactions, schema migrations, idempotent writes,
> restart durability, concurrent update safety, audit history, versioning.

P7 (anti-entropy): two tenants sharing the same DB file must never see
each other's data. This test creates two stores with different org_ids
and proves isolation.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ["MAESTRO_LOCAL_DEV"] = "true"


@pytest.fixture
def temp_db():
    """Create a temp DB file, yield the path, clean up after."""
    db = tempfile.mktemp(suffix="_candidate_test.db")
    yield db
    if os.path.exists(db):
        os.unlink(db)


# ═══════════════════════════════════════════════════════════════════════════
# RESTART DURABILITY
# ═══════════════════════════════════════════════════════════════════════════

def test_candidates_survive_restart(temp_db):
    """Candidates persist across restart (new store instance loads from SQLite)."""
    from maestro_oem.candidate_pattern_store_sqlite import SQLiteCandidatePatternStore
    from maestro_oem.pattern_proposer import PatternProposer

    store1 = SQLiteCandidatePatternStore(db_path=temp_db, org_id="default")
    proposer = PatternProposer(store=store1)
    proposer.propose(
        [{"text": "Pattern [1].", "citation_numbers": [1], "claim_type": "inference"}],
        entities=["CustomerA"], query_id="q1",
    )
    assert len(store1.get_all()) == 1

    # Simulate restart — create a new store instance pointing at the same DB
    store2 = SQLiteCandidatePatternStore(db_path=temp_db, org_id="default")
    assert len(store2.get_all()) == 1
    assert store2.get_all()[0].entities == ["CustomerA"]


def test_predictions_survive_restart(temp_db):
    """Prospective predictions persist across restart."""
    from maestro_oem.candidate_pattern_store_sqlite import SQLiteCandidatePatternStore
    from maestro_oem.pattern_proposer import PatternProposer
    from maestro_oem.empirical_loop import CaseFingerprintBuilder

    store1 = SQLiteCandidatePatternStore(db_path=temp_db, org_id="default")
    proposer = PatternProposer(store=store1)
    candidates = proposer.propose(
        [{"text": "Pattern [1].", "citation_numbers": [1], "claim_type": "inference"}],
        entities=["CustomerA"], query_id="q1",
    )
    cid = candidates[0].candidate_id

    class MockSituation:
        timeline = [{"date": "2024-11-01", "event": "e"}]
        evidence = [{"text": "ev", "source": "crm:1"}]
    case = CaseFingerprintBuilder.build("CustomerA", MockSituation(), "churn")
    pred_id = store1.register_prospective_prediction_from_case(cid, case, "churn")
    assert pred_id is not None

    # Restart
    store2 = SQLiteCandidatePatternStore(db_path=temp_db, org_id="default")
    pending = store2.get_pending_predictions()
    assert len(pending) == 1
    assert pending[0]["prediction_id"] == pred_id


def test_resolved_outcomes_survive_restart(temp_db):
    """Resolved predictions + updated candidate counters persist across restart."""
    from maestro_oem.candidate_pattern_store_sqlite import SQLiteCandidatePatternStore
    from maestro_oem.pattern_proposer import PatternProposer, CandidateStatus
    from maestro_oem.empirical_loop import CaseFingerprintBuilder

    store1 = SQLiteCandidatePatternStore(db_path=temp_db, org_id="default")
    proposer = PatternProposer(store=store1)
    candidates = proposer.propose(
        [{"text": "Pattern [1].", "citation_numbers": [1], "claim_type": "inference"}],
        entities=["CustomerA"], query_id="q1",
    )
    cid = candidates[0].candidate_id

    # Register + resolve 3 predictions as supporting → promotes to TESTING
    for i in range(3):
        s = type("S", (), {
            "commitments": [{"commitment": f"c{i}"}],
            "timeline": [{"date": f"2024-11-0{i+1}", "event": f"e{i}"}],
            "evidence": [{"text": f"ev{i}", "source": f"crm:{i+10}"}],
        })()
        case = CaseFingerprintBuilder.build("CustomerA", s, "churn")
        pred_id = store1.register_prospective_prediction_from_case(cid, case, "churn")
        store1.resolve_prospective_prediction(pred_id, "supporting", f"signal:{i}")

    c1 = store1.get_all()[0]
    assert c1.status == CandidateStatus.TESTING
    assert c1.supporting_outcomes == 3

    # Restart
    store2 = SQLiteCandidatePatternStore(db_path=temp_db, org_id="default")
    c2 = store2.get_all()[0]
    assert c2.status == CandidateStatus.TESTING
    assert c2.supporting_outcomes == 3


# ═══════════════════════════════════════════════════════════════════════════
# P7: TENANT ISOLATION — two orgs must never see each other's data
# ═══════════════════════════════════════════════════════════════════════════

def test_tenant_isolation_candidates(temp_db):
    """P7: two orgs sharing the same DB file never see each other's candidates."""
    from maestro_oem.candidate_pattern_store_sqlite import SQLiteCandidatePatternStore
    from maestro_oem.pattern_proposer import PatternProposer

    store_a = SQLiteCandidatePatternStore(db_path=temp_db, org_id="org_a")
    store_b = SQLiteCandidatePatternStore(db_path=temp_db, org_id="org_b")

    proposer_a = PatternProposer(store=store_a)
    proposer_a.propose(
        [{"text": "Pattern A [1].", "citation_numbers": [1], "claim_type": "inference"}],
        entities=["CustomerA"], query_id="q_a",
    )

    proposer_b = PatternProposer(store=store_b)
    proposer_b.propose(
        [{"text": "Pattern B [1].", "citation_numbers": [1], "claim_type": "inference"}],
        entities=["CustomerB"], query_id="q_b",
    )

    # Org A sees only its candidate
    assert len(store_a.get_all()) == 1
    assert store_a.get_all()[0].entities == ["CustomerA"]

    # Org B sees only its candidate
    assert len(store_b.get_all()) == 1
    assert store_b.get_all()[0].entities == ["CustomerB"]

    # Cross-check: org A cannot see org B's candidate
    for c in store_a.get_all():
        assert "CustomerB" not in c.entities
    for c in store_b.get_all():
        assert "CustomerA" not in c.entities


def test_tenant_isolation_predictions(temp_db):
    """P7: predictions are scoped by org_id — no cross-tenant leakage."""
    from maestro_oem.candidate_pattern_store_sqlite import SQLiteCandidatePatternStore
    from maestro_oem.pattern_proposer import PatternProposer
    from maestro_oem.empirical_loop import CaseFingerprintBuilder

    store_a = SQLiteCandidatePatternStore(db_path=temp_db, org_id="org_a")
    store_b = SQLiteCandidatePatternStore(db_path=temp_db, org_id="org_b")

    proposer_a = PatternProposer(store=store_a)
    cand_a = proposer_a.propose(
        [{"text": "Pattern [1].", "citation_numbers": [1], "claim_type": "inference"}],
        entities=["CustomerA"], query_id="q_a",
    )

    proposer_b = PatternProposer(store=store_b)
    cand_b = proposer_b.propose(
        [{"text": "Pattern [1].", "citation_numbers": [1], "claim_type": "inference"}],
        entities=["CustomerA"], query_id="q_b",
    )

    situation = type("S", (), {
        "timeline": [{"date": "2024-11-01", "event": "e"}],
        "evidence": [{"text": "ev", "source": "crm:1"}],
    })()
    case = CaseFingerprintBuilder.build("CustomerA", situation, "churn")

    # Both orgs register a prediction with the SAME case_fingerprint
    pred_a = store_a.register_prospective_prediction_from_case(cand_a[0].candidate_id, case, "churn")
    pred_b = store_b.register_prospective_prediction_from_case(cand_b[0].candidate_id, case, "churn")

    # Both should succeed — the case_fingerprint is the same, but the org_id differs
    assert pred_a is not None
    assert pred_b is not None
    assert pred_a != pred_b

    # Each org sees only its own prediction
    assert len(store_a.get_pending_predictions()) == 1
    assert len(store_b.get_pending_predictions()) == 1
    assert store_a.get_pending_predictions()[0]["prediction_id"] == pred_a
    assert store_b.get_pending_predictions()[0]["prediction_id"] == pred_b


# ═══════════════════════════════════════════════════════════════════════════
# IDEMPOTENT WRITES
# ═══════════════════════════════════════════════════════════════════════════

def test_idempotent_candidate_write(temp_db):
    """Writing the same candidate twice (same dedup_key) is idempotent."""
    from maestro_oem.candidate_pattern_store_sqlite import SQLiteCandidatePatternStore
    from maestro_oem.pattern_proposer import PatternProposer

    store = SQLiteCandidatePatternStore(db_path=temp_db, org_id="default")
    proposer = PatternProposer(store=store)
    claims = [{"text": "Pattern [1].", "citation_numbers": [1], "claim_type": "inference"}]

    proposer.propose(claims, entities=["CustomerA"], query_id="q1")
    proposer.propose(claims, entities=["CustomerA"], query_id="q2")  # same dedup_key

    assert len(store.get_all()) == 1  # not 2
    assert store.get_all()[0].reasoning_mentions == 2  # incremented


# ═══════════════════════════════════════════════════════════════════════════
# AUDIT HISTORY
# ═══════════════════════════════════════════════════════════════════════════

def test_status_transition_history_recorded(temp_db):
    """Status transitions are recorded in the audit history table."""
    from maestro_oem.candidate_pattern_store_sqlite import SQLiteCandidatePatternStore
    from maestro_oem.pattern_proposer import PatternProposer, CandidateStatus
    from maestro_oem.empirical_loop import CaseFingerprintBuilder

    store = SQLiteCandidatePatternStore(db_path=temp_db, org_id="default")
    proposer = PatternProposer(store=store)
    candidates = proposer.propose(
        [{"text": "Pattern [1].", "citation_numbers": [1], "claim_type": "inference"}],
        entities=["CustomerA"], query_id="q1",
    )
    cid = candidates[0].candidate_id

    # Promote to TESTING via 3 supporting outcomes
    for i in range(3):
        s = type("S", (), {
            "commitments": [{"commitment": f"c{i}"}],
            "timeline": [{"date": f"2024-11-0{i+1}", "event": f"e{i}"}],
        })()
        case = CaseFingerprintBuilder.build("CustomerA", s, "churn")
        pred_id = store.register_prospective_prediction_from_case(cid, case, "churn")
        store.resolve_prospective_prediction(pred_id, "supporting", f"signal:{i}")

    # Verify the status transition was recorded
    history = store.get_status_history(str(cid))
    assert len(history) >= 1
    assert history[0]["to_status"] == "TESTING"
    assert history[0]["from_status"] == "HYPOTHESIS"
    assert history[0]["reason"] == "auto_promote_3_prospective_supports"


def test_status_transition_history_survives_restart(temp_db):
    """The audit history survives restart."""
    from maestro_oem.candidate_pattern_store_sqlite import SQLiteCandidatePatternStore
    from maestro_oem.pattern_proposer import PatternProposer
    from maestro_oem.empirical_loop import CaseFingerprintBuilder

    store1 = SQLiteCandidatePatternStore(db_path=temp_db, org_id="default")
    proposer = PatternProposer(store=store1)
    candidates = proposer.propose(
        [{"text": "Pattern [1].", "citation_numbers": [1], "claim_type": "inference"}],
        entities=["CustomerA"], query_id="q1",
    )
    cid = candidates[0].candidate_id
    for i in range(3):
        s = type("S", (), {
            "commitments": [{"commitment": f"c{i}"}],
            "timeline": [{"date": f"2024-11-0{i+1}", "event": f"e{i}"}],
        })()
        case = CaseFingerprintBuilder.build("CustomerA", s, "churn")
        pred_id = store1.register_prospective_prediction_from_case(cid, case, "churn")
        store1.resolve_prospective_prediction(pred_id, "supporting", f"signal:{i}")

    # Restart
    store2 = SQLiteCandidatePatternStore(db_path=temp_db, org_id="default")
    history = store2.get_status_history(str(cid))
    assert len(history) >= 1
    assert history[0]["to_status"] == "TESTING"


# ═══════════════════════════════════════════════════════════════════════════
# SCHEMA MIGRATIONS (idempotent — CREATE TABLE IF NOT EXISTS)
# ═══════════════════════════════════════════════════════════════════════════

def test_schema_creation_is_idempotent(temp_db):
    """Creating the store twice on the same DB doesn't error."""
    from maestro_oem.candidate_pattern_store_sqlite import SQLiteCandidatePatternStore
    store1 = SQLiteCandidatePatternStore(db_path=temp_db, org_id="default")
    store2 = SQLiteCandidatePatternStore(db_path=temp_db, org_id="default")
    # No error — CREATE TABLE IF NOT EXISTS is idempotent
    assert len(store2.get_all()) == len(store1.get_all())

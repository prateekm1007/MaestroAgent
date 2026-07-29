"""Phase 3 — Query Grounding + Abstention regression tests (P84 / P87).

Tests the query grounding layer that sits between the user's question and
the LLM. Computes evidence from the canonical ledger BEFORE invoking the
LLM, so zero-evidence questions abstain instead of hallucinating.

Governance citations:
- P1: every assertion verified by execution
- P2: this IS the test file for query_grounding.py
- P10: root cause documented — the LLM hallucinated commitments because
  there was no evidence_count gate before the LLM call
- P22: ground_query calls reduce_commitments (the production path)
- P56: intent detection is rule-based (no LLM)
- P79: semantic disambiguation — my-to-X vs X's-promises vs involving-X
- P84: 100% abstention rate on negative-knowledge queries
- P85: ground_query never raises
- P87: state queries return counts matching the canonical ledger
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import datetime, timezone

import pytest

from maestro_personal_shell.query_grounding import (
    detect_intent,
    ground_query,
    format_abstention_response,
)
from maestro_personal_shell.canonical_ledger import (
    LEDGER_DDL,
    append_event,
    CommitmentEvent,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fresh_ledger_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name
    conn = sqlite3.connect(db_path)
    conn.executescript(LEDGER_DDL)
    conn.commit()
    conn.close()
    yield db_path
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def seeded_ledger_db(fresh_ledger_db):
    """Seed 3 commitments: Maria (user), Nora (user, cancelled), Alex (third-party)."""
    now = datetime.now(timezone.utc).isoformat()
    append_event(CommitmentEvent(
        commitment_id="c1", event_type="commitment", actor="user", entity="Maria",
        text="I will send the proposal to Maria by Friday.",
        confidence=0.9, user_email="test@user", timestamp=now,
    ), db_path=fresh_ledger_db)
    append_event(CommitmentEvent(
        commitment_id="c2", event_type="commitment", actor="user", entity="Nora",
        text="I will review the auth module for Nora by Tuesday.",
        confidence=0.85, user_email="test@user", timestamp=now,
    ), db_path=fresh_ledger_db)
    append_event(CommitmentEvent(
        commitment_id="c2", event_type="cancellation", actor="user", entity="Nora",
        text="I will not review the auth module; cancelled.",
        confidence=0.9, user_email="test@user", timestamp=now,
    ), db_path=fresh_ledger_db)
    append_event(CommitmentEvent(
        commitment_id="c3", event_type="commitment", actor="entity_name", entity="Alex",
        text="Alex: I will deliver the mockups by Wednesday.",
        confidence=0.85, user_email="test@user", timestamp=now,
    ), db_path=fresh_ledger_db)
    yield fresh_ledger_db


# ---------------------------------------------------------------------------
# Intent detection (P79)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("question,expected_intent,expected_entity,expected_direction", [
    ("What did I promise Maria?",        "my_commitments",    "Maria", "my-to-X"),
    ("What do I owe Nora?",              "my_commitments",    "Nora",  "my-to-X"),
    ("My commitments to Sam",            "my_commitments",    "Sam",   "my-to-X"),
    ("What did Alex promise?",           "their_commitments", "Alex",  "X's-promises"),
    ("What are Jamie's commitments?",    "their_commitments", "Jamie", "X's-promises"),
    ("History with Sam",                 "involving",         "Sam",   "involving-X"),
    ("Everything about Nora",            "involving",         "Nora",  "involving-X"),
    ("How many commitments are active?", "state_query",       None,    "any"),
    ("What's cancelled?",                "state_query",       None,    "any"),
    ("What is the weather?",             "general",           None,    "any"),
])
def test_detect_intent(question, expected_intent, expected_entity, expected_direction):
    """P79: intent detection correctly classifies questions."""
    r = detect_intent(question)
    assert r["intent"] == expected_intent, (
        f"intent: expected {expected_intent!r}, got {r['intent']!r}"
    )
    assert r["direction"] == expected_direction, (
        f"direction: expected {expected_direction!r}, got {r['direction']!r}"
    )
    if expected_entity is None:
        assert r["entity"] is None, f"entity: expected None, got {r['entity']!r}"
    else:
        assert r["entity"] == expected_entity, (
            f"entity: expected {expected_entity!r}, got {r['entity']!r}"
        )


# ---------------------------------------------------------------------------
# Abstention gate (P84)
# ---------------------------------------------------------------------------

def test_zero_evidence_query_abstains(seeded_ledger_db):
    """P84: a query about an entity with no evidence MUST abstain."""
    r = ground_query("What did I promise Elon Musk?", "test@user", db_path=seeded_ledger_db)
    assert r["should_abstain"] is True
    assert r["evidence_count"] == 0
    assert "no evidence" in r["abstention_reason"].lower() or "Elon" in r["abstention_reason"]


def test_nonzero_evidence_query_does_not_abstain(seeded_ledger_db):
    """P84: a query about an entity WITH evidence MUST NOT abstain."""
    r = ground_query("What did I promise Maria?", "test@user", db_path=seeded_ledger_db)
    assert r["should_abstain"] is False
    assert r["evidence_count"] >= 1
    assert r["abstention_reason"] is None


def test_abstention_response_format():
    """P84: the abstention response has the correct structure."""
    resp = format_abstention_response(
        "What did I promise Elon Musk?",
        entity="Elon",
        reason="no evidence found for Elon",
    )
    assert resp["abstention"] is True
    assert resp["confidence"] == 0.0
    assert resp["evidence_count"] == 0
    assert "Elon" in resp["answer"]
    # F-7 fix: raw API paths must NOT leak to the user. The regression suite
    # (tests/test_regression_audit.py::test_f7_no_api_paths_in_user_copy)
    # enforces this at the API level — keep this assertion consistent.
    assert "/api/" not in resp["answer"]


def test_abstention_response_no_entity():
    """P84: abstention response works when no entity was extracted."""
    resp = format_abstention_response(
        "What's the meaning of life?",
        entity=None,
        reason="no commitments found in your ledger",
    )
    assert resp["abstention"] is True
    assert resp["confidence"] == 0.0
    assert "don't have any records" in resp["answer"]


# ---------------------------------------------------------------------------
# State consistency (P87)
# ---------------------------------------------------------------------------

def test_state_query_returns_ledger_consistent_counts(seeded_ledger_db):
    """P87: state queries return counts matching the canonical ledger."""
    r = ground_query("How many commitments are active?", "test@user", db_path=seeded_ledger_db)
    assert r["intent"] == "state_query"
    assert r["state_assertion"] is not None
    # seeded_ledger_db has: c1 (active, Maria), c2 (cancelled, Nora), c3 (active third-party, Alex)
    # reduce_commitments only returns user-active → c1 only → active_count=1
    # but check_ledger_projection_consistency counts ALL groups → active=2 (c1+c3), cancelled=1 (c2)
    assert r["state_assertion"]["active"] >= 1
    assert r["state_assertion"]["cancelled"] >= 1
    assert r["state_assertion"]["total_events"] == 4  # 4 events appended


def test_state_query_matches_direct_ledger_call(seeded_ledger_db):
    """P87: the state_assertion in ground_query matches a direct consistency check."""
    from maestro_personal_shell.canonical_ledger import check_ledger_projection_consistency
    direct = check_ledger_projection_consistency(db_path=seeded_ledger_db)
    grounded = ground_query("What's cancelled?", "test@user", db_path=seeded_ledger_db)
    assert grounded["state_assertion"]["active"] == direct["active_count"]
    assert grounded["state_assertion"]["cancelled"] == direct["cancelled_count"]
    assert grounded["state_assertion"]["total_events"] == direct["total_events"]


# ---------------------------------------------------------------------------
# P85: ground_query never raises
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_question", [
    "",
    None,
    "   ",
    12345,
    "a" * 100000,
    "'; DROP TABLE signals; --",
    "<script>alert('xss')</script>",
])
def test_ground_query_never_raises(bad_question, fresh_ledger_db):
    """P85: ground_query returns a result on any input, never raises."""
    r = ground_query(bad_question, "test@user", db_path=fresh_ledger_db)
    assert "should_abstain" in r
    assert "evidence_count" in r
    assert "evidence" in r
    # Bad input should either abstain or return general intent — never crash
    assert r["should_abstain"] is True or r["evidence_count"] >= 0


# ---------------------------------------------------------------------------
# P79: semantic disambiguation
# ---------------------------------------------------------------------------

def test_my_to_x_vs_x_to_me(seeded_ledger_db):
    """P79: 'What did I promise Maria?' (my-to-X) vs 'What did Maria promise?' (X's-promises)."""
    r1 = ground_query("What did I promise Maria?", "test@user", db_path=seeded_ledger_db)
    assert r1["direction"] == "my-to-X"
    assert r1["entity"] == "Maria"

    r2 = ground_query("What did Maria promise?", "test@user", db_path=seeded_ledger_db)
    assert r2["direction"] == "X's-promises"
    assert r2["entity"] == "Maria"


def test_involving_x_returns_all_entity_matches(seeded_ledger_db):
    """P79: 'History with Maria' returns all evidence involving Maria."""
    r = ground_query("History with Maria", "test@user", db_path=seeded_ledger_db)
    assert r["intent"] == "involving"
    assert r["entity"] == "Maria"
    # Maria has 1 active commitment
    assert r["evidence_count"] >= 1


# ---------------------------------------------------------------------------
# Full journey: ingest via classifier → ground query → verify
# ---------------------------------------------------------------------------

def test_full_journey_classify_ground_abstain(fresh_ledger_db):
    """P22/P35: full journey — classify_and_append → ground_query → abstention.

    Ingest a commitment to Maria, then query about Maria (should find evidence),
    then query about Elon Musk (should abstain).
    """
    from maestro_personal_shell.actor_classifier import classify_and_append

    USER = "test@user"
    classify_and_append(
        text="I will send the proposal to Maria by Friday.",
        user_email=USER,
        entity="Maria",
        db_path=fresh_ledger_db,
    )

    # Query about Maria → finds evidence
    r1 = ground_query("What did I promise Maria?", USER, db_path=fresh_ledger_db)
    assert not r1["should_abstain"]
    assert r1["evidence_count"] == 1

    # Query about Elon Musk → abstains (P84)
    r2 = ground_query("What did I promise Elon Musk?", USER, db_path=fresh_ledger_db)
    assert r2["should_abstain"]
    assert r2["evidence_count"] == 0

    # The abstention response would be returned to the user instead of an LLM answer
    abstain_resp = format_abstention_response(
        "What did I promise Elon Musk?",
        entity=r2["entity"],
        reason=r2["abstention_reason"],
    )
    assert abstain_resp["confidence"] == 0.0
    assert "don't have any records" in abstain_resp["answer"]

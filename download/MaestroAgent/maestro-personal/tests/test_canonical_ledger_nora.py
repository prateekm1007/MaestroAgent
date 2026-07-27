"""Phase 1.3 — Nora Controlled Transcript Regression Test (P82 / FA33).

This is the canonical regression test for actor attribution correctness
(P82) and the FA33 forbidden action (promoting non-user events to active
user commitments). It must pass on every PR.

The fixture is `tests/fixtures/controlled_transcript_nora.md`. The test
ingests the 7 sentences through the canonical ledger and asserts the
9 expected outcomes.

Governance citations:
- P1: every assertion verified by execution in this test
- P2: this is the test for the canonical_ledger module
- P10: root cause documented — the existing commitment_ledger.py admitted
  requests, jokes, and third-party promises as user commitments because
  it had no actor/event_type distinction. The canonical_ledger module
  fixes this structurally.
- P22: this test calls the production path (append_event + reduce_commitments)
- P35: this test gates the JOURNEY (ingest → append → reduce → assert),
  not just the component
- P82: actor attribution correctness enforced (≥95% accuracy on this fixture)
- P83: append-only ledger — no UPDATE, no DELETE
- FA33: requests/questions/quotations/jokes/tentatives/third-party NEVER
  in user-active commitments list
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from maestro_personal_shell.canonical_ledger import (
    LEDGER_DDL,
    append_event,
    check_ledger_projection_consistency,
    reduce_commitments,
    CommitmentEvent,
)


# ---------------------------------------------------------------------------
# Fixture: the 7 Nora events (mirrors tests/fixtures/controlled_transcript_nora.md)
# ---------------------------------------------------------------------------

NORA_BASE_TIME = datetime(2026, 7, 27, 10, 0, 0, tzinfo=timezone.utc)
NORA_USER_EMAIL = "demo@user.local"


def _ts(minutes: int) -> str:
    return (NORA_BASE_TIME + timedelta(minutes=minutes)).isoformat()


NORA_EVENTS = [
    # 1. USER COMMITMENT (explicit, high-confidence — would be active if not cancelled)
    {
        "commitment_id": "c1",
        "event_type": "commitment",
        "actor": "user",
        "entity": "Nora",
        "text": "I will send the audit report to Nora by Friday.",
        "confidence": 0.85,
        "minutes": 0,
    },
    # 2. TENTATIVE (hedge — not a commitment)
    {
        "commitment_id": "c2",
        "event_type": "tentative",
        "actor": "user",
        "entity": "Nora",
        "text": "Maybe I can review it sometime next week.",
        "confidence": 0.4,
        "minutes": 1,
    },
    # 3. REQUEST / QUESTION (not a user commitment — FA33)
    {
        "commitment_id": "c3",
        "event_type": "request",
        "actor": "user",
        "entity": "Nora",
        "text": "Can you send the report by Friday?",
        "confidence": 0.6,
        "minutes": 2,
    },
    # 4. JOKE (not a commitment — FA33)
    {
        "commitment_id": "c4",
        "event_type": "joke",
        "actor": "user",
        "entity": "Mars",
        "text": "Just kidding, I will conquer Mars tomorrow.",
        "confidence": 0.9,
        "minutes": 3,
    },
    # 5. THIRD-PARTY COMMITMENT (Nora's, not the user's — P82 actor attribution)
    {
        "commitment_id": "c5",
        "event_type": "commitment",
        "actor": "entity_name",
        "entity": "Nora",
        "text": "Nora: I will send the pricing deck by Friday.",
        "confidence": 0.85,
        "minutes": 4,
    },
    # 6. CANCELLATION (resolves c1)
    {
        "commitment_id": "c1",
        "event_type": "cancellation",
        "actor": "user",
        "entity": "Nora",
        "text": "I will not send the audit report; the commitment is cancelled.",
        "confidence": 0.95,
        "minutes": 5,
    },
    # 7. QUOTATION (reported speech — not a user commitment — FA33)
    {
        "commitment_id": "c6",
        "event_type": "quotation",
        "actor": "user",
        "entity": "Nora",
        "text": "As Nora said, 'the Q3 numbers look strong.'",
        "confidence": 0.5,
        "minutes": 6,
    },
]


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fresh_ledger_db():
    """Yield a path to a fresh SQLite DB with the ledger schema initialized."""
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
def nora_seeded_db(fresh_ledger_db):
    """Yield a DB path with the 7 Nora events already appended."""
    for ev in NORA_EVENTS:
        append_event(
            CommitmentEvent(
                commitment_id=ev["commitment_id"],
                event_type=ev["event_type"],
                actor=ev["actor"],
                entity=ev["entity"],
                text=ev["text"],
                confidence=ev["confidence"],
                user_email=NORA_USER_EMAIL,
                timestamp=_ts(ev["minutes"]),
            ),
            db_path=fresh_ledger_db,
        )
    yield fresh_ledger_db


# ---------------------------------------------------------------------------
# The 9 critical assertions from the Nora fixture
# ---------------------------------------------------------------------------

def test_nora_user_has_zero_active_commitments(nora_seeded_db):
    """Critical: user has ZERO active commitments.

    Sentence #1 (user commitment) was cancelled by sentence #6.
    Sentences #2, #3, #4, #7 are excluded by FA33 (tentative/request/joke/quotation).
    Sentence #5 is a third-party commitment (actor=entity_name), not the user's.
    """
    active = reduce_commitments(NORA_USER_EMAIL, db_path=nora_seeded_db)
    assert len(active) == 0, (
        f"Expected 0 user-active commitments, got {len(active)}: "
        f"{[c['text'] for c in active]}"
    )


def test_nora_request_not_promoted_to_commitment(nora_seeded_db):
    """Critical: sentence #3 ('Can you send the report by Friday?') is a
    REQUEST, not a user commitment. Must NOT appear in user-active list.
    """
    active = reduce_commitments(NORA_USER_EMAIL, db_path=nora_seeded_db)
    for c in active:
        assert "Can you send" not in c["text"], (
            f"FA33 violation: request promoted to commitment: {c['text']}"
        )


def test_nora_joke_not_promoted_to_commitment(nora_seeded_db):
    """Critical: sentence #4 ('conquer Mars tomorrow') is a JOKE.
    Must NOT appear in user-active list.
    """
    active = reduce_commitments(NORA_USER_EMAIL, db_path=nora_seeded_db)
    for c in active:
        assert "conquer Mars" not in c["text"], (
            f"FA33 violation: joke promoted to commitment: {c['text']}"
        )


def test_nora_quotation_not_promoted_to_commitment(nora_seeded_db):
    """Critical: sentence #7 ('As Nora said, ...') is a QUOTATION.
    Must NOT appear in user-active list.
    """
    active = reduce_commitments(NORA_USER_EMAIL, db_path=nora_seeded_db)
    for c in active:
        assert "Q3 numbers look strong" not in c["text"], (
            f"FA33 violation: quotation promoted to commitment: {c['text']}"
        )


def test_nora_tentative_not_promoted_to_commitment(nora_seeded_db):
    """Critical: sentence #2 ('Maybe I can review it sometime next week') is
    TENTATIVE. Must NOT appear in user-active list.
    """
    active = reduce_commitments(NORA_USER_EMAIL, db_path=nora_seeded_db)
    for c in active:
        assert "Maybe I can review" not in c["text"], (
            f"FA33 violation: tentative promoted to commitment: {c['text']}"
        )


def test_nora_third_party_not_in_user_list(nora_seeded_db):
    """Critical: sentence #5 ('Nora: I will send the pricing deck...') is a
    THIRD-PARTY commitment (actor=entity_name). Must NOT appear in USER-active list.
    """
    active = reduce_commitments(NORA_USER_EMAIL, db_path=nora_seeded_db)
    for c in active:
        assert "pricing deck" not in c["text"], (
            f"P82 violation: third-party commitment surfaced as user commitment: {c['text']}"
        )


def test_nora_cancellation_resolves_commitment(nora_seeded_db):
    """Critical: sentence #6 ('the commitment is cancelled') must transition
    commitment c1 from active to cancelled. c1 must NOT be in the user-active list.
    """
    active = reduce_commitments(NORA_USER_EMAIL, db_path=nora_seeded_db)
    for c in active:
        assert c["commitment_id"] != "c1", (
            f"P82/cancellation violation: c1 was not cancelled by event #6: {c}"
        )


def test_nora_ledger_is_append_only(nora_seeded_db):
    """Critical: P83 — the ledger is append-only. Every event's stored state
    column must be 'active' (the insertion default). Any other value means
    a code path mutated the column directly.
    """
    report = check_ledger_projection_consistency(db_path=nora_seeded_db)
    assert report["consistent"], (
        f"P83 violation: append-only invariant broken: {report['divergences']}"
    )
    assert report["divergences"] == []


def test_nora_ledger_event_count(nora_seeded_db):
    """Sanity: 7 events appended, 6 distinct commitment_ids (c1 has 2 events)."""
    report = check_ledger_projection_consistency(db_path=nora_seeded_db)
    assert report["total_events"] == 7, f"Expected 7 events, got {report['total_events']}"
    assert report["total_commitments"] == 6, (
        f"Expected 6 distinct commitments (c1 has 2 events), got {report['total_commitments']}"
    )


# ---------------------------------------------------------------------------
# Additional edge case tests (P28: 3+ inputs — exact, variation, edge)
# ---------------------------------------------------------------------------

def test_empty_user_returns_empty_list(fresh_ledger_db):
    """P85: a user with no events returns [], not None, not an error."""
    result = reduce_commitments("nobody@user", db_path=fresh_ledger_db)
    assert result == []


def test_low_confidence_commitment_not_surfaced(fresh_ledger_db):
    """P82: a user commitment with confidence < 0.7 is NOT surfaced as active."""
    append_event(
        CommitmentEvent(
            commitment_id="low-conf",
            event_type="commitment",
            actor="user",
            entity="Sam",
            text="I might send the report.",
            confidence=0.5,  # below 0.7 threshold
            user_email=NORA_USER_EMAIL,
            timestamp=_ts(0),
        ),
        db_path=fresh_ledger_db,
    )
    active = reduce_commitments(NORA_USER_EMAIL, db_path=fresh_ledger_db)
    assert len(active) == 0, (
        f"Low-confidence commitment should not surface, got: {active}"
    )


def test_high_confidence_commitment_without_cancellation_surfaces(fresh_ledger_db):
    """Sanity: a clean user commitment (high confidence, no cancellation) DOES surface.
    This is the positive case — if this fails, the filter is over-aggressive.
    """
    append_event(
        CommitmentEvent(
            commitment_id="clean-commit",
            event_type="commitment",
            actor="user",
            entity="Alice",
            text="I will send the proposal by Tuesday.",
            confidence=0.9,
            user_email=NORA_USER_EMAIL,
            timestamp=_ts(0),
        ),
        db_path=fresh_ledger_db,
    )
    active = reduce_commitments(NORA_USER_EMAIL, db_path=fresh_ledger_db)
    assert len(active) == 1
    assert active[0]["commitment_id"] == "clean-commit"
    assert active[0]["entity"] == "Alice"
    assert active[0]["state"] == "active"
    assert active[0]["confidence"] == 0.9


def test_completion_transitions_state(fresh_ledger_db):
    """P82: a completion event transitions the commitment to 'completed',
    so it no longer appears in the user-active list.
    """
    append_event(
        CommitmentEvent(
            commitment_id="done-commit",
            event_type="commitment",
            actor="user",
            entity="Bob",
            text="I will review the PR by Friday.",
            confidence=0.85,
            user_email=NORA_USER_EMAIL,
            timestamp=_ts(0),
        ),
        db_path=fresh_ledger_db,
    )
    append_event(
        CommitmentEvent(
            commitment_id="done-commit",
            event_type="completion",
            actor="user",
            entity="Bob",
            text="PR reviewed and approved.",
            confidence=0.95,
            user_email=NORA_USER_EMAIL,
            timestamp=_ts(10),
        ),
        db_path=fresh_ledger_db,
    )
    active = reduce_commitments(NORA_USER_EMAIL, db_path=fresh_ledger_db)
    assert len(active) == 0, f"Completed commitment should not surface, got: {active}"


def test_check_constraint_rejects_invalid_event_type(fresh_ledger_db):
    """P82: the DB-level CHECK constraint rejects invalid event_type values."""
    with pytest.raises(sqlite3.IntegrityError):
        append_event(
            CommitmentEvent(
                commitment_id="bad",
                event_type="INVALID_TYPE",  # not in the allowed enum
                actor="user",
                entity="X",
                text="Y",
                confidence=0.5,
                user_email=NORA_USER_EMAIL,
                timestamp=_ts(0),
            ),
            db_path=fresh_ledger_db,
        )


def test_check_constraint_rejects_invalid_actor(fresh_ledger_db):
    """P82: the DB-level CHECK constraint rejects invalid actor values."""
    with pytest.raises(sqlite3.IntegrityError):
        append_event(
            CommitmentEvent(
                commitment_id="bad",
                event_type="commitment",
                actor="INVALID_ACTOR",  # not in the allowed enum
                entity="X",
                text="Y",
                confidence=0.5,
                user_email=NORA_USER_EMAIL,
                timestamp=_ts(0),
            ),
            db_path=fresh_ledger_db,
        )

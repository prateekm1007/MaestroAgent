"""P41 — Single source of truth for signal classification/ownership.

The 5-layer ownership trace exposed a class-level smell: classification
truth was stored in 4 parallel places (signal metadata, ledger column,
evidence dict, answer lines) — each drifted. P41: derive from ONE record.

This test verifies:
1. reconcile_signal() returns a record with the canonical fields.
2. reconcile_signals_for_user() filters out non-commitments (P37).
3. filter_for_promise_query() excludes third_party_report + non-user
   owners (P36) — the structural end of the 5-layer wack-a-mole.
4. The function does NOT consult the commitment_ledger (the stale copy).

Run:
  cd /home/z/my-project/MaestroAgent/download/MaestroAgent/maestro-personal
  python -m pytest tests/test_P41_single_source_of_truth.py -v
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
os.environ.setdefault("MAESTRO_ENV", "dev")
os.environ["MAESTRO_PERSONAL_DB"] = str(REPO_ROOT / "test_P41_ssot.db")
_env_local = Path("/home/z/my-project/.env.local")
if _env_local.exists():
    for line in _env_local.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _reset_test_db():
    db_path = REPO_ROOT / "test_P41_ssot.db"
    if db_path.exists():
        db_path.unlink()
    for suffix in ("-wal", "-shm"):
        p = Path(str(db_path) + suffix)
        if p.exists():
            p.unlink()


@pytest.fixture(scope="function")
def fresh_db():
    """Provide a fresh test DB with the signals table initialized."""
    _reset_test_db()
    from maestro_personal_shell.api import init_db
    init_db()
    yield
    _reset_test_db()


def _insert_signal(db_path, *, signal_id, entity, text, metadata, signal_type="commitment_made", user_email="ssot-test@example.com", timestamp="2026-07-25T10:00:00Z"):
    """Insert a signal directly into the DB for testing."""
    import sqlite3
    conn = sqlite3.connect(db_path)
    # Use INSERT OR REPLACE to handle re-inserts; include created_at (NOT NULL)
    conn.execute(
        "INSERT INTO signals (signal_id, entity, text, timestamp, metadata, signal_type, user_email, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (signal_id, entity, text, timestamp, json.dumps(metadata), signal_type, user_email, timestamp),
    )
    conn.commit()
    conn.close()


def test_reconcile_signal_returns_canonical_record(fresh_db):
    """P41: reconcile_signal() returns a record with the canonical fields,
    derived from the signal's metadata (single source of truth)."""
    sig_id = str(uuid.uuid4())
    db_path = os.environ["MAESTRO_PERSONAL_DB"]
    _insert_signal(db_path, signal_id=sig_id, entity="Maria",
                   text="I will send the proposal to Maria by Friday",
                   metadata={"commitment_type": "explicit", "is_commitment": True, "owner": "user", "source": "manual"})

    from maestro_personal_shell.reconcile import reconcile_signal
    rec = reconcile_signal(sig_id, db_path=db_path, user_email="ssot-test@example.com")

    assert rec is not None, "reconcile_signal returned None for an existing signal"
    assert rec["signal_id"] == sig_id
    assert rec["entity"] == "Maria"
    assert rec["commitment_type"] == "explicit"
    assert rec["is_commitment"] is True
    assert rec["owner"] == "user"
    assert rec["text"] == "I will send the proposal to Maria by Friday"  # ORIGINAL, not normalized
    assert rec["reconcile_source"] == "signal.metadata"  # P41 provenance


def test_reconcile_signal_returns_none_for_missing(fresh_db):
    """P41: reconcile_signal() returns None for a non-existent signal_id."""
    from maestro_personal_shell.reconcile import reconcile_signal
    rec = reconcile_signal("nonexistent-uuid", db_path=os.environ["MAESTRO_PERSONAL_DB"])
    assert rec is None


def test_reconcile_signal_handles_legacy_signal_without_metadata(fresh_db):
    """P41: reconcile_signal() falls back to signal_type when metadata has
    no classification (legacy signal). The function NEVER crashes — it
    derives a reasonable default."""
    sig_id = str(uuid.uuid4())
    db_path = os.environ["MAESTRO_PERSONAL_DB"]
    _insert_signal(db_path, signal_id=sig_id, entity="Alex",
                   text="Some legacy signal",
                   metadata={},  # no classification
                   signal_type="reported_statement")

    from maestro_personal_shell.reconcile import reconcile_signal
    rec = reconcile_signal(sig_id, db_path=db_path)
    assert rec is not None
    # Legacy fallback: reported_statement → third_party_report
    assert rec["commitment_type"] == "third_party_report"
    assert rec["is_commitment"] is False  # third_party_report is not a user commitment
    assert rec["owner"] == "unknown"  # no owner in metadata


def test_reconcile_signals_for_user_filters_non_commitments(fresh_db):
    """P41 + P37: reconcile_signals_for_user() MUST filter out non-commitments
    by default (P37 — non-commitments MUST NOT surface in commitment lists)."""
    db_path = os.environ["MAESTRO_PERSONAL_DB"]
    user_email = "ssot-filter@example.com"
    # Insert 3 signals: 1 commitment, 1 question (non-commitment), 1 tentative
    _insert_signal(db_path, signal_id=str(uuid.uuid4()), entity="Maria",
                   text="I will send the proposal",
                   metadata={"commitment_type": "explicit", "is_commitment": True, "owner": "user"},
                   user_email=user_email, timestamp="2026-07-25T10:00:00Z")
    _insert_signal(db_path, signal_id=str(uuid.uuid4()), entity="Alex",
                   text="Will you send the report by Friday?",
                   metadata={"commitment_type": "request", "is_commitment": False, "owner": "user"},
                   user_email=user_email, timestamp="2026-07-25T11:00:00Z")
    _insert_signal(db_path, signal_id=str(uuid.uuid4()), entity="Dana",
                   text="I will try to get it done, but dont count on it",
                   metadata={"commitment_type": "tentative", "is_commitment": False, "owner": "user"},
                   user_email=user_email, timestamp="2026-07-25T12:00:00Z")

    from maestro_personal_shell.reconcile import reconcile_signals_for_user
    records = reconcile_signals_for_user(user_email, db_path=db_path)

    # Only the explicit commitment should survive (P37)
    assert len(records) == 1, (
        f"P37 violation: reconcile_signals_for_user returned {len(records)} "
        f"records, expected 1 (the explicit commitment). Non-commitments "
        f"should be filtered out by default."
    )
    assert records[0]["entity"] == "Maria"
    assert records[0]["commitment_type"] == "explicit"


def test_filter_for_promise_query_excludes_third_party_reports(fresh_db):
    """P36 + P41: filter_for_promise_query() MUST exclude third_party_report
    signals — the auditor's 'What did I promise Maria?' returning Maria's
    own promises bug. ONE filter on the reconciled record (P41)."""
    db_path = os.environ["MAESTRO_PERSONAL_DB"]
    user_email = "ssot-promise@example.com"
    # Maria's own promise (third_party_report — she said it, not the user)
    _insert_signal(db_path, signal_id=str(uuid.uuid4()), entity="Maria",
                   text="Maria said: I will send the proposal",
                   metadata={"commitment_type": "third_party_report", "is_commitment": True, "owner": "other"},
                   user_email=user_email, timestamp="2026-07-25T10:00:00Z")
    # User's promise to Maria (explicit, owner=user)
    _insert_signal(db_path, signal_id=str(uuid.uuid4()), entity="Maria",
                   text="I will send the proposal to Maria by Friday",
                   metadata={"commitment_type": "explicit", "is_commitment": True, "owner": "user"},
                   user_email=user_email, timestamp="2026-07-25T11:00:00Z")

    from maestro_personal_shell.reconcile import reconcile_signals_for_user, filter_for_promise_query
    all_records = reconcile_signals_for_user(user_email, db_path=db_path, include_non_commitments=True)
    # Filter to Maria only
    maria_records = [r for r in all_records if r["entity"] == "Maria"]
    assert len(maria_records) == 2

    # Apply P36 ownership filter
    filtered = filter_for_promise_query(maria_records, user_email=user_email, entity_filter="Maria")

    assert len(filtered) == 1, (
        f"P36 violation: filter_for_promise_query returned {len(filtered)} "
        f"records, expected 1 (only the user's own promise to Maria). "
        f"Third-party reports MUST be excluded."
    )
    assert filtered[0]["owner"] == "user"
    assert filtered[0]["commitment_type"] == "explicit"
    assert filtered[0]["text"] == "I will send the proposal to Maria by Friday"


def test_filter_for_promise_query_excludes_non_commitment_types(fresh_db):
    """P36 + P37: filter_for_promise_query() MUST exclude tentative,
    proposal, request, aspiration, negation, not_a_commitment types."""
    db_path = os.environ["MAESTRO_PERSONAL_DB"]
    user_email = "ssot-promise2@example.com"
    # Various non-commitment types owned by user
    for ctype in ["tentative", "proposal", "request", "aspiration", "negation"]:
        _insert_signal(db_path, signal_id=str(uuid.uuid4()), entity="Maria",
                       text=f"Test {ctype} signal",
                       metadata={"commitment_type": ctype, "is_commitment": False, "owner": "user"},
                       user_email=user_email, timestamp="2026-07-25T10:00:00Z")
    # One real commitment
    _insert_signal(db_path, signal_id=str(uuid.uuid4()), entity="Maria",
                   text="I will send the proposal",
                   metadata={"commitment_type": "explicit", "is_commitment": True, "owner": "user"},
                   user_email=user_email, timestamp="2026-07-25T11:00:00Z")

    from maestro_personal_shell.reconcile import reconcile_signals_for_user, filter_for_promise_query
    all_records = reconcile_signals_for_user(user_email, db_path=db_path, include_non_commitments=True)
    maria_records = [r for r in all_records if r["entity"] == "Maria"]
    filtered = filter_for_promise_query(maria_records, user_email=user_email, entity_filter="Maria")

    assert len(filtered) == 1, (
        f"P37 violation: filter_for_promise_query returned {len(filtered)} "
        f"records, expected 1 (only the explicit commitment). All "
        f"non-commitment types must be excluded."
    )
    assert filtered[0]["commitment_type"] == "explicit"


def test_reconcile_does_not_consult_ledger(fresh_db):
    """P41 structural check: reconcile_signal MUST NOT read from the
    commitment_ledger table. The ledger's commitment_type column is a
    stale copy — the signal's metadata is the single source of truth.

    We verify this by inserting a signal AND a ledger entry with DIFFERENT
    commitment_types, then asserting reconcile_signal returns the metadata's
    type (not the ledger's).
    """
    sig_id = str(uuid.uuid4())
    db_path = os.environ["MAESTRO_PERSONAL_DB"]
    # Signal metadata says "explicit"
    _insert_signal(db_path, signal_id=sig_id, entity="Maria",
                   text="I will send the proposal",
                   metadata={"commitment_type": "explicit", "is_commitment": True, "owner": "user"})

    # Insert a ledger entry with a DIFFERENT commitment_type (stale)
    import sqlite3
    conn = sqlite3.connect(db_path)
    # Create the ledger table if it doesn't exist (the function shouldn't
    # read from it, but we want to ensure the ledger EXISTS with a stale value)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS commitment_ledger (
                ledger_id TEXT PRIMARY KEY,
                signal_id TEXT,
                user_email TEXT,
                entity TEXT,
                commitment_type TEXT,
                state TEXT,
                evidence_quote TEXT,
                timestamp TEXT
            )
        """)
        conn.execute(
            "INSERT INTO commitment_ledger (ledger_id, signal_id, user_email, entity, commitment_type, state, evidence_quote, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), sig_id, "ssot-test@example.com", "Maria",
             "tentative",  # STALE — the metadata says "explicit"
             "active", "I will send the proposal", "2026-07-25T10:00:00Z"),
        )
        conn.commit()
    finally:
        conn.close()

    from maestro_personal_shell.reconcile import reconcile_signal
    rec = reconcile_signal(sig_id, db_path=db_path)
    assert rec is not None
    # MUST return the metadata's value, NOT the ledger's stale value
    assert rec["commitment_type"] == "explicit", (
        f"P41 violation: reconcile_signal returned commitment_type="
        f"{rec['commitment_type']!r} — the ledger's stale value ('tentative') "
        f"leaked into the reconciled record. The signal's metadata is the "
        f"single source of truth; the ledger MUST NOT be consulted."
    )
    assert rec["reconcile_source"] == "signal.metadata"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

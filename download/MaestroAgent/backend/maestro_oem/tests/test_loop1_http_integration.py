"""Loop 1 Iteration — HTTP integration tests.

CEO directive (2026-07-03):
> Loop 1 was validated in direct engine execution only. HTTP wiring +
> real schema migration needed before production-grade. Process gap:
> validated the engine, not the delivery path.

These tests exercise the Loop 1 lifecycle through HTTP — not direct
engine execution. They will FAIL until the endpoints are wired and the
schema is migrated. Watch them fail first (non-vacuous proof), then
build until they pass.

The tests:
  1. test_loop1_http_honored_path: POST evening-preparation → POST action
     → POST outcome (honored) → GET learning. Assert the Learning Ledger
     entry references the actual commitment + honored outcome, not a
     template.
  2. test_loop1_http_broken_path: same sequence but with a broken
     outcome. Assert the ledger says "broken", not "honored".
  3. test_loop1_http_whispers_endpoint: GET /loop1/whispers returns all
     Whispers with Delivery Intelligence fields.
  4. test_whisper_history_schema_migration_survives: existing data
     survives the schema migration (P7 isolation test).

P2: Untested code is unverified code. P5: Self-certification is weak.
P6: Fail closed — placeholder Learning Ledger entries REJECTED.
"""
from __future__ import annotations

import json
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

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
    app = create_app(db_path=str(tmp_path / "maestro.db"))
    with TestClient(app) as c:
        yield c
    oem_state._initialized = False
    oem_state.engine = None
    oem_state.signals = []


def _headers(client: TestClient) -> dict:
    """Get auth headers — local dev mode may not require, but include if available."""
    return {"Content-Type": "application/json"}


# ─── Adversarial Test 1: Honored path through HTTP ─────────────────────────

def test_loop1_http_honored_path(client):
    """Full Loop 1 lifecycle through HTTP with a honored outcome.

    Sequence:
      POST /api/oem/loop1/evening-preparation  → fires Whisper
      POST /api/oem/loop1/action               → records action
      POST /api/oem/loop1/outcome              → records outcome (honored)
      GET  /api/oem/loop1/learning/{wid}       → returns Learning Ledger

    Assert: the Learning Ledger entry references the actual commitment
    + honored outcome, not a template. Must NOT be a placeholder.
    """
    # ── Step 1: Evening preparation ───────────────────────────────────
    r = client.post("/api/oem/loop1/evening-preparation", json={}, headers=_headers(client))
    assert r.status_code == 200, f"evening-preparation failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    assert data["whispers_fired"] >= 1, \
        f"Must fire at least 1 Whisper, got {data['whispers_fired']}"
    whisper = data["whispers"][0]
    wid = whisper["whisper_id"]
    assert whisper.get("recipient"), "Whisper must have a recipient (Delivery Intelligence)"
    assert whisper.get("timing_reason"), "Whisper must have a timing_reason"
    assert whisper.get("depth"), "Whisper must have a depth"
    assert "materially_changed_since_last_shown" in whisper, \
        "Whisper must have materially_changed_since_last_shown"
    assert "evidence_spine" in whisper, "Whisper must carry an Evidence Spine"
    es = whisper["evidence_spine"]
    assert len(es.get("observed_facts", [])) > 0, "Evidence Spine must have observed_facts"

    # ── Step 2: Record executive action ───────────────────────────────
    r = client.post("/api/oem/loop1/action", json={
        "whisper_id": wid,
        "action": "acted",
        "decision_influenced": "Q4 delivery prioritized based on this commitment",
        "follow_up_questions": [
            "What did we promise?",
            "Who is the internal expert?",
        ],
    }, headers=_headers(client))
    assert r.status_code == 200, f"action failed: {r.status_code} {r.text[:200]}"
    action_data = r.json()
    assert action_data["status"] == "recorded", f"Action must be recorded: {action_data}"
    assert action_data["action_taken"] == "acted"

    # ── Step 3: Record outcome (honored) ──────────────────────────────
    r = client.post("/api/oem/loop1/outcome", json={
        "whisper_id": wid,
        "outcome": "honored",
    }, headers=_headers(client))
    assert r.status_code == 200, f"outcome failed: {r.status_code} {r.text[:200]}"
    outcome_data = r.json()
    assert outcome_data["status"] == "recorded", f"Outcome must be recorded: {outcome_data}"
    assert outcome_data["outcome"] == "honored"

    # ── Step 4: GET Learning Ledger entry ─────────────────────────────
    r = client.get(f"/api/oem/loop1/learning/{wid}", headers=_headers(client))
    assert r.status_code == 200, f"learning GET failed: {r.status_code} {r.text[:200]}"
    learning_data = r.json()
    entry = learning_data.get("learning_entry", "")
    assert entry, "Learning Ledger entry must be non-empty"
    assert len(entry) >= 20, \
        f"Learning Ledger entry must be a real sentence (≥20 chars). Got: {entry!r}"

    # REJECT placeholder/template entries (P6)
    FORBIDDEN_PHRASES = [
        "Learning recorded.",
        "Outcome observed.",
        "Loop complete.",
        "Maestro learned something.",
        "The system learned.",
        "TODO",
        "placeholder",
    ]
    for phrase in FORBIDDEN_PHRASES:
        assert phrase.lower() not in entry.lower(), \
            f"Learning Ledger entry must not be a placeholder. Got: {entry!r}"

    # The entry MUST honestly say the commitment was honored (not broken)
    assert "honored" in entry.lower() or "kept" in entry.lower() or "fulfilled" in entry.lower() or "met" in entry.lower(), \
        f"Learning Ledger must reference the honored outcome. Got: {entry!r}"

    # Must NOT say "broken" (that's the other path)
    assert "broken" not in entry.lower() and "missed" not in entry.lower(), \
        f"Learning Ledger must NOT say broken for an honored outcome. Got: {entry!r}"

    # Must reference the actual commitment or entity (signal-derived)
    # The demo seed has Globex/Initech/Hooli — at least one should appear
    assert any(name.lower() in entry.lower() for name in ["globex", "initech", "hooli", "commitment"]), \
        f"Learning Ledger must reference the actual entity or commitment. Got: {entry!r}"

    # Must honestly acknowledge causality uncertainty
    assert "does not know" in entry.lower() or "uncertain" in entry.lower() or "caus" in entry.lower() or "may have" in entry.lower(), \
        f"Learning Ledger must acknowledge causality uncertainty. Got: {entry!r}"


# ─── Adversarial Test 2: Broken path through HTTP ──────────────────────────

def test_loop1_http_broken_path(client):
    """Full Loop 1 lifecycle through HTTP with a broken outcome.

    Same sequence as test_loop1_http_honored_path but outcome='broken'.
    The Learning Ledger must honestly say "broken" — NOT spin it as
    "honored" or "learning opportunity." Maestro never invents precision.
    """
    # Evening preparation
    r = client.post("/api/oem/loop1/evening-preparation", json={}, headers=_headers(client))
    assert r.status_code == 200
    data = r.json()
    assert data["whispers_fired"] >= 1
    wid = data["whispers"][0]["whisper_id"]

    # Record action (ignored this time — the exec ignored the Whisper)
    r = client.post("/api/oem/loop1/action", json={
        "whisper_id": wid,
        "action": "ignored",
        "decision_influenced": None,
        "follow_up_questions": [],
    }, headers=_headers(client))
    assert r.status_code == 200

    # Record outcome (broken)
    r = client.post("/api/oem/loop1/outcome", json={
        "whisper_id": wid,
        "outcome": "broken",
    }, headers=_headers(client))
    assert r.status_code == 200
    assert r.json()["outcome"] == "broken"

    # GET Learning Ledger entry
    r = client.get(f"/api/oem/loop1/learning/{wid}", headers=_headers(client))
    assert r.status_code == 200
    entry = r.json().get("learning_entry", "")
    assert entry, "Learning Ledger entry must be non-empty"

    # The entry MUST honestly say "broken" (or "missed"/"not honored"/"failed")
    assert "broken" in entry.lower() or "missed" in entry.lower() or "not honored" in entry.lower() or "failed" in entry.lower(), \
        f"Learning Ledger must honestly say commitment was broken. Got: {entry!r}"

    # Must NOT spin it positively
    assert "honored" not in entry.lower() and "fulfilled" not in entry.lower(), \
        f"Learning Ledger must NOT spin a broken commitment as honored. Got: {entry!r}"


# ─── Adversarial Test 3: Whispers endpoint returns Delivery Intelligence ───

def test_loop1_http_whispers_endpoint(client):
    """GET /api/oem/loop1/whispers returns all Whispers with Delivery
    Intelligence fields and learning entries (for the auditor's inspection).
    """
    # First fire some Whispers via evening-preparation
    r = client.post("/api/oem/loop1/evening-preparation", json={}, headers=_headers(client))
    assert r.status_code == 200
    fired_count = r.json()["whispers_fired"]
    assert fired_count >= 1

    # Now GET the whispers list
    r = client.get("/api/oem/loop1/whispers", headers=_headers(client))
    assert r.status_code == 200
    data = r.json()
    whispers = data.get("whispers", [])
    assert len(whispers) >= 1, "Must return at least 1 Whisper"

    for w in whispers:
        # Each whisper must have the Delivery Intelligence fields
        assert "whisper_id" in w
        assert "recipient" in w, f"Whisper missing recipient: {w}"
        assert "timing_reason" in w, f"Whisper missing timing_reason: {w}"
        assert "depth" in w, f"Whisper missing depth: {w}"
        # learning_entry may be None if not yet written — that's OK
        assert "learning_entry" in w, f"Whisper missing learning_entry key: {w}"
        # action_taken may be None if not yet recorded — that's OK
        assert "action_taken" in w, f"Whisper missing action_taken key: {w}"


# ─── Adversarial Test 4: Schema migration survives (P7 isolation test) ────

def test_whisper_history_schema_migration_survives(tmp_path):
    """Existing whisper_history data must survive the schema migration.

    P7: state change needs isolation test. The migration adds 9 new
    columns (recipient, reason_recipient_chosen, timing_reason, depth,
    materially_changed_since_last_shown, decision_influenced,
    follow_up_questions, outcome, learning_entry). Existing rows (with
    only the old columns) must still be readable after migration.

    Test:
      1. Create an OLD-format whisper_history table (pre-Loop-1 schema)
      2. Insert a row with old fields only
      3. Open WhisperHistoryStore (which triggers the migration)
      4. Verify the old row is still readable
      5. Verify the new columns exist (empty/null for the old row)
      6. Insert a NEW-format row (with all Loop 1 fields)
      7. Verify both rows coexist
    """
    import sqlite3
    import sys
    backend_path = str(Path(__file__).resolve().parents[2])
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)

    db_path = tmp_path / "test_migration.db"

    # ── Step 1: Create OLD-format table (pre-Loop-1 schema) ───────────
    # This is the schema BEFORE the Loop 1 iteration migration
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE whisper_history (
            whisper_id TEXT NOT NULL,
            org_id TEXT NOT NULL DEFAULT 'default',
            shown_count INTEGER NOT NULL DEFAULT 0,
            action_taken TEXT,
            first_shown TEXT,
            last_shown TEXT,
            insight TEXT,
            embedding BLOB,
            entity TEXT,
            type TEXT,
            PRIMARY KEY (whisper_id, org_id)
        )
    """)
    conn.execute("""
        INSERT INTO whisper_history
        (whisper_id, org_id, shown_count, action_taken, first_shown, last_shown, insight, embedding, entity, type)
        VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
    """, (
        "wspr-old-format-test", "default", 3, "ignored",
        "2026-06-01T10:00:00+00:00", "2026-06-03T10:00:00+00:00",
        "Old whisper before Loop 1 migration",
        "Globex", "commitment_exists",
    ))
    conn.commit()
    conn.close()

    # ── Step 2: Open WhisperHistoryStore (triggers migration) ─────────
    from maestro_oem.whisper_history_store import WhisperHistoryStore
    store = WhisperHistoryStore(db_path)

    # ── Step 3: Verify the old row survived ───────────────────────────
    history = store.get_history("wspr-old-format-test", org_id="default")
    assert history.get("shown_count") == 3, \
        f"Old shown_count must survive migration. Got: {history}"
    assert history.get("action_taken") == "ignored", \
        f"Old action_taken must survive migration. Got: {history}"
    assert history.get("insight") == "Old whisper before Loop 1 migration", \
        f"Old insight must survive migration. Got: {history}"
    assert history.get("entity") == "Globex", \
        f"Old entity must survive migration. Got: {history}"

    # ── Step 4: Verify new columns exist (empty for old row) ──────────
    assert "recipient" in history, "New column 'recipient' must be in get_history result"
    assert "decision_influenced" in history, "New column 'decision_influenced' must be in get_history result"
    assert "outcome" in history, "New column 'outcome' must be in get_history result"
    assert "learning_entry" in history, "New column 'learning_entry' must be in get_history result"
    # Old row should have null/None for the new columns
    assert history.get("recipient") is None or history.get("recipient") == "", \
        f"Old row recipient must be null/empty. Got: {history.get('recipient')}"
    assert history.get("outcome") is None or history.get("outcome") == "", \
        f"Old row outcome must be null/empty. Got: {history.get('outcome')}"

    # ── Step 5: Insert a NEW-format row (with all Loop 1 fields) ──────
    store.record_shown(
        whisper_id="wspr-new-format-test",
        org_id="default",
        insight="New whisper after Loop 1 migration",
        entity="Initech",
        whisper_type="commitment_exists",
        recipient="jane.d@acme.com",
        timing_reason="Meeting in 22 hours",
        depth="full",
        materially_changed_since_last_shown=True,
    )
    store.record_outcome(
        whisper_id="wspr-new-format-test",
        action="acted",
        org_id="default",
        decision_influenced="Initech renewal prioritized",
        follow_up_questions=["What did we promise?"],
    )
    store.record_outcome_signal(
        whisper_id="wspr-new-format-test",
        outcome="honored",
        org_id="default",
    )
    store.record_learning_entry(
        whisper_id="wspr-new-format-test",
        learning_entry="Initech honored its commitment after the executive acted.",
        org_id="default",
    )

    # ── Step 6: Verify both rows coexist ──────────────────────────────
    all_history = store.get_all_history(org_id="default")
    assert "wspr-old-format-test" in all_history, "Old row must still be present"
    assert "wspr-new-format-test" in all_history, "New row must be present"

    new_row = all_history["wspr-new-format-test"]
    assert new_row.get("recipient") == "jane.d@acme.com", \
        f"New row recipient must be persisted. Got: {new_row.get('recipient')}"
    assert new_row.get("decision_influenced") == "Initech renewal prioritized", \
        f"New row decision_influenced must be persisted. Got: {new_row.get('decision_influenced')}"
    assert new_row.get("outcome") == "honored", \
        f"New row outcome must be persisted. Got: {new_row.get('outcome')}"
    assert new_row.get("learning_entry") == "Initech honored its commitment after the executive acted.", \
        f"New row learning_entry must be persisted. Got: {new_row.get('learning_entry')}"

    store.close()

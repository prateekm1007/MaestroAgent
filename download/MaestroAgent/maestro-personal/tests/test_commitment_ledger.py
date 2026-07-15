"""
Tests for the Phase 3 Commitment Ledger.

Covers the roadmap's Phase 3 requirements:
  - Structured extraction schema persisted (owner, recipient, action, deadline)
  - Full lifecycle state machine with legal-transition enforcement
  - Closure matching by topic/action/recipient (not entity only)
  - Correction propagation to ledger + FTS
  - Cross-user isolation on the ledger
  - Audit logging of every state transition (legal + rejected)

These tests do NOT exercise the LLM classifier — they feed the ledger
directly with synthetic classification dicts. The classifier is tested
separately (test_classifier_wiring.py) and must call Core's
classify_transcript_chunk per the no-dilution guard.
"""

import os
import sys
import sqlite3
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from maestro_personal_shell.commitment_ledger import (
    LEGAL_TRANSITIONS,
    backfill_ledger_from_signals,
    get_ledger_entries,
    init_ledger_table,
    is_legal_transition,
    match_closure,
    propagate_correction,
    transition_ledger_state,
    upsert_ledger_entry,
    _action_keywords,
)
from maestro_personal_shell.api import init_db, save_signal_to_db
from maestro_personal_shell.audit_trust import init_audit_tables, get_audit_log


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["MAESTRO_PERSONAL_DB"] = path
    init_db(path)
    init_audit_tables(path)
    init_ledger_table(path)
    yield path
    os.unlink(path)
    del os.environ["MAESTRO_PERSONAL_DB"]


def _signal(signal_id, entity, text, signal_type="commitment_made",
            user_email="user@test.com", timestamp="2026-07-10T10:00:00Z"):
    return {
        "signal_id": signal_id,
        "entity": entity,
        "text": text,
        "signal_type": signal_type,
        "timestamp": timestamp,
        "user_email": user_email,
    }


def _classification(commitment_type="explicit", state="active", owner="user",
                    recipient="Alex", action="send proposal",
                    deadline_text="Friday EOD", deadline_datetime="2026-07-10T17:00:00+05:30",
                    confidence=0.91, evidence_quote="I'll send the proposal by Friday EOD."):
    return {
        "is_commitment": True,
        "commitment_type": commitment_type,
        "state": state,
        "owner": owner,
        "recipient": recipient,
        "action": action,
        "deadline_text": deadline_text,
        "deadline_datetime": deadline_datetime,
        "confidence": confidence,
        "evidence_quote": evidence_quote,
    }


# ---------------------------------------------------------------------------
# 1. Schema + persistence
# ---------------------------------------------------------------------------

class TestLedgerSchema:
    def test_init_creates_table(self, temp_db):
        conn = sqlite3.connect(temp_db)
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='commitments_ledger'"
        ).fetchall()]
        conn.close()
        assert "commitments_ledger" in tables

    def test_ledger_columns_match_roadmap_schema(self, temp_db):
        """The roadmap specifies a structured extraction schema. Verify
        the ledger has columns for every required field."""
        conn = sqlite3.connect(temp_db)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(commitments_ledger)").fetchall()}
        conn.close()
        required = {
            "ledger_id", "signal_id", "user_email", "entity",
            "commitment_type", "state", "owner", "recipient", "action",
            "deadline_text", "deadline_datetime", "confidence",
            "evidence_quote", "superseded_by", "created_at", "updated_at",
        }
        assert required.issubset(cols), f"Missing columns: {required - cols}"

    def test_upsert_persists_all_fields(self, temp_db):
        sig = _signal("sig-1", "Alex", "I'll send the proposal by Friday EOD.")
        clf = _classification()
        entry = upsert_ledger_entry(clf, sig, "user@test.com", temp_db)
        assert entry is not None
        assert entry["entity"] == "Alex"
        assert entry["commitment_type"] == "explicit"
        assert entry["state"] == "active"
        assert entry["owner"] == "user"
        assert entry["recipient"] == "Alex"
        assert entry["action"] == "send proposal"
        assert entry["deadline_text"] == "Friday EOD"
        assert entry["deadline_datetime"] == "2026-07-10T17:00:00+05:30"
        assert abs(entry["confidence"] - 0.91) < 0.001
        assert entry["evidence_quote"] == "I'll send the proposal by Friday EOD."

    def test_upsert_skips_non_commitments(self, temp_db):
        sig = _signal("sig-2", "Alex", "Nice weather today", signal_type="smalltalk")
        clf = {**_classification(), "is_commitment": False, "commitment_type": "not_a_commitment"}
        entry = upsert_ledger_entry(clf, sig, "user@test.com", temp_db)
        assert entry is None
        entries = get_ledger_entries("user@test.com", temp_db)
        assert len(entries) == 0


# ---------------------------------------------------------------------------
# 2. State machine
# ---------------------------------------------------------------------------

class TestStateMachine:
    def test_legal_transitions_defined(self):
        """Every state in the roadmap lifecycle must be in LEGAL_TRANSITIONS."""
        roadmap_states = {
            "candidate", "active", "at_risk", "completed_claimed",
            "completed_verified", "disputed", "cancelled", "superseded",
            "tombstoned",
        }
        assert roadmap_states == set(LEGAL_TRANSITIONS.keys())

    def test_tombstoned_is_terminal(self):
        assert LEGAL_TRANSITIONS["tombstoned"] == set()

    def test_legal_transition_allowed(self):
        assert is_legal_transition("candidate", "active")
        assert is_legal_transition("active", "at_risk")
        assert is_legal_transition("at_risk", "completed_claimed")
        assert is_legal_transition("completed_claimed", "completed_verified")
        assert is_legal_transition("completed_verified", "disputed")
        assert is_legal_transition("disputed", "cancelled")

    def test_illegal_transition_rejected(self):
        assert not is_legal_transition("tombstoned", "active")
        assert not is_legal_transition("cancelled", "active")
        assert not is_legal_transition("candidate", "completed_verified")  # skip states
        assert not is_legal_transition("active", "completed_verified")     # skip completed_claimed

    def test_transition_applied_and_audit_logged(self, temp_db):
        sig = _signal("sig-3", "Alex", "I'll send the proposal by Friday EOD.")
        clf = _classification(state="candidate")
        entry = upsert_ledger_entry(clf, sig, "user@test.com", temp_db)

        ok = transition_ledger_state(entry["ledger_id"], "active", "user@test.com", temp_db)
        assert ok
        entries = get_ledger_entries("user@test.com", temp_db)
        assert entries[0]["state"] == "active"

        # Audit log must record the transition.
        events = get_audit_log(user_email="user@test.com", db_path=temp_db, limit=50)
        transitions = [e for e in events if e["action"] == "commitment_transition"]
        assert len(transitions) >= 1
        details = __import__("json").loads(transitions[0]["details"])
        assert details["from"] == "candidate"
        assert details["to"] == "active"

    def test_illegal_transition_rejected_and_audit_logged(self, temp_db):
        sig = _signal("sig-4", "Alex", "I'll send the proposal by Friday EOD.")
        clf = _classification(state="active")
        entry = upsert_ledger_entry(clf, sig, "user@test.com", temp_db)

        # active → completed_verified is illegal (must go through completed_claimed)
        ok = transition_ledger_state(entry["ledger_id"], "completed_verified", "user@test.com", temp_db)
        assert not ok

        # State unchanged.
        entries = get_ledger_entries("user@test.com", temp_db)
        assert entries[0]["state"] == "active"

        # Rejection audit-logged.
        events = get_audit_log(user_email="user@test.com", db_path=temp_db, limit=50)
        rejected = [e for e in events if e["action"] == "rejected_transition"]
        assert len(rejected) >= 1

    def test_upsert_with_changed_state_routes_through_transition(self, temp_db):
        """When the classifier re-classifies a signal with a new state,
        upsert must route through the state machine (not blind-overwrite)."""
        sig = _signal("sig-5", "Alex", "I'll send the proposal by Friday EOD.")
        upsert_ledger_entry(_classification(state="active"), sig, "user@test.com", temp_db)

        # Re-classify with a legal transition: active → at_risk
        upsert_ledger_entry(_classification(state="at_risk"), sig, "user@test.com", temp_db)
        entries = get_ledger_entries("user@test.com", temp_db)
        assert entries[0]["state"] == "at_risk"

    def test_upsert_with_illegal_state_change_is_rejected(self, temp_db):
        """If the classifier emits an illegal transition, the ledger keeps
        the old state (don't silently corrupt the lifecycle)."""
        sig = _signal("sig-6", "Alex", "I'll send the proposal by Friday EOD.")
        upsert_ledger_entry(_classification(state="active"), sig, "user@test.com", temp_db)

        # active → completed_verified is illegal.
        upsert_ledger_entry(_classification(state="completed_verified"), sig, "user@test.com", temp_db)
        entries = get_ledger_entries("user@test.com", temp_db)
        # State must NOT have jumped to completed_verified.
        assert entries[0]["state"] == "active"


# ---------------------------------------------------------------------------
# 3. Closure matching (roadmap requirement #4)
# ---------------------------------------------------------------------------

class TestClosureMatching:
    def test_action_keywords_extract_content_words(self):
        kw = _action_keywords("I will send the security proposal by Friday EOD")
        assert "send" in kw
        assert "security" in kw
        assert "proposal" in kw
        # Stopwords excluded.
        assert "will" not in kw
        assert "the" not in kw
        assert "friday" not in kw  # day-of-week stopword
        assert "eod" not in kw     # deadline stopword

    def test_match_closure_by_action_overlap(self, temp_db):
        """A completion signal must close the active commitment with
        overlapping action keywords — even when the texts differ."""
        active = {
            "entity": "Alex",
            "action": "send security proposal",
            "recipient": "Alex",
            "evidence_quote": "I'll send the security proposal by Friday",
        }
        completion = {
            "entity": "Alex",
            "text": "Sent the security proposal yesterday",
            "recipient": "Alex",
        }
        match = match_closure(completion, [active])
        assert match is not None
        assert match["action"] == "send security proposal"

    def test_match_closure_requires_action_overlap(self, temp_db):
        """Without action overlap, no match — even if entity matches.
        This prevents 'Sent the invoice' from closing 'send the proposal'."""
        active = {
            "entity": "Alex",
            "action": "send proposal",
            "recipient": "Alex",
            "evidence_quote": "I'll send the proposal",
        }
        completion = {
            "entity": "Alex",
            "text": "Sent the invoice yesterday",
            "recipient": "Alex",
        }
        match = match_closure(completion, [active])
        assert match is None  # 'invoice' doesn't overlap 'proposal'

    def test_match_closure_respects_recipient(self, temp_db):
        """If both commitments specify recipients, they must match."""
        active = {
            "entity": "Alex",
            "action": "send proposal",
            "recipient": "Sara",
            "evidence_quote": "I'll send the proposal to Sara",
        }
        completion = {
            "entity": "Alex",
            "text": "Sent the proposal",
            "recipient": "Bob",  # different recipient
        }
        match = match_closure(completion, [active])
        assert match is None

    def test_match_closure_fuzzy_entity(self, temp_db):
        """'AcmeCorp' should match 'Acme Corp' (whitespace variation)."""
        active = {
            "entity": "AcmeCorp",
            "action": "deliver roadmap",
            "recipient": "",
            "evidence_quote": "We'll deliver the roadmap",
        }
        completion = {
            "entity": "Acme Corp",
            "text": "Delivered the roadmap",
            "recipient": "",
        }
        match = match_closure(completion, [active])
        assert match is not None

    def test_match_closure_picks_best_overlap(self, temp_db):
        """When multiple entries match, pick the one with the most overlap."""
        entries = [
            {"entity": "Alex", "action": "send proposal", "recipient": "Alex",
             "evidence_quote": "send proposal"},
            {"entity": "Alex", "action": "send security proposal", "recipient": "Alex",
             "evidence_quote": "send security proposal"},
        ]
        completion = {
            "entity": "Alex",
            "text": "Sent the security proposal",
            "recipient": "Alex",
        }
        match = match_closure(completion, entries)
        assert match is not None
        assert match["action"] == "send security proposal"  # more overlap


# ---------------------------------------------------------------------------
# 4. Correction propagation (roadmap requirement #6)
# ---------------------------------------------------------------------------

class TestCorrectionPropagation:
    def test_propagate_cancel_transitions_to_cancelled(self, temp_db):
        sig = _signal("sig-7", "Alex", "I'll send the proposal by Friday EOD.")
        upsert_ledger_entry(_classification(state="active"), sig, "user@test.com", temp_db)

        result = propagate_correction("sig-7", "cancel", "user@test.com", temp_db)
        assert result["ledger_updated"] is True
        assert result["from_state"] == "active"
        assert result["to_state"] == "cancelled"
        entries = get_ledger_entries("user@test.com", temp_db)
        assert entries[0]["state"] == "cancelled"

    def test_propagate_dismiss_transitions_to_cancelled(self, temp_db):
        sig = _signal("sig-8", "Alex", "I'll send the proposal by Friday EOD.")
        upsert_ledger_entry(_classification(state="active"), sig, "user@test.com", temp_db)

        result = propagate_correction("sig-8", "dismiss", "user@test.com", temp_db)
        assert result["ledger_updated"] is True
        assert result["to_state"] == "cancelled"

    def test_propagate_dispute_transitions_to_disputed(self, temp_db):
        sig = _signal("sig-9", "Alex", "I'll send the proposal by Friday EOD.")
        upsert_ledger_entry(_classification(state="completed_claimed"), sig, "user@test.com", temp_db)

        result = propagate_correction("sig-9", "dispute", "user@test.com", temp_db)
        assert result["ledger_updated"] is True
        assert result["to_state"] == "disputed"

    def test_propagate_removes_from_fts(self, temp_db):
        """Correction must remove the signal from FTS so retrieval stops
        surfacing it (roadmap requirement #6 — propagate to all surfaces)."""
        from maestro_personal_shell.semantic_retrieval import init_fts_index, index_signal, semantic_search
        init_fts_index(temp_db)
        sig = _signal("sig-10", "Alex", "I'll send the proposal by Friday EOD.")
        index_signal(sig, db_path=temp_db)

        # Before correction: retrievable.
        results = semantic_search("proposal", db_path=temp_db)
        assert any(r.get("signal_id") == "sig-10" for r in results)

        upsert_ledger_entry(_classification(state="active"), sig, "user@test.com", temp_db)
        propagate_correction("sig-10", "cancel", "user@test.com", temp_db)

        # After correction: gone from FTS.
        results = semantic_search("proposal", db_path=temp_db)
        assert not any(r.get("signal_id") == "sig-10" for r in results)

    def test_propagate_no_ledger_entry_is_safe(self, temp_db):
        """Correcting a signal with no ledger entry must not raise."""
        result = propagate_correction("nonexistent-sig", "cancel", "user@test.com", temp_db)
        assert result["ledger_updated"] is False
        assert result["ledger_id"] is None


# ---------------------------------------------------------------------------
# 5. Cross-user isolation
# ---------------------------------------------------------------------------

class TestCrossUserIsolation:
    def test_user_a_cannot_see_user_b_entries(self, temp_db):
        sig_a = _signal("sig-a", "Alex", "I'll send the proposal", user_email="a@x.com")
        sig_b = _signal("sig-b", "Bob", "I'll review the design", user_email="b@x.com")
        upsert_ledger_entry(_classification(), sig_a, "a@x.com", temp_db)
        upsert_ledger_entry(_classification(), sig_b, "b@x.com", temp_db)

        a_entries = get_ledger_entries("a@x.com", temp_db)
        b_entries = get_ledger_entries("b@x.com", temp_db)
        assert len(a_entries) == 1
        assert a_entries[0]["entity"] == "Alex"
        assert len(b_entries) == 1
        assert b_entries[0]["entity"] == "Bob"

    def test_user_a_cannot_transition_user_b_entry(self, temp_db):
        """transition_ledger_state is user-scoped via the audit log; the
        transition itself doesn't re-check ownership (the API layer must
        verify ownership before calling). But propagate_correction IS
        user-scoped — it filters by user_email."""
        sig_b = _signal("sig-b2", "Bob", "I'll review the design", user_email="b@x.com")
        entry = upsert_ledger_entry(_classification(state="active"), sig_b, "b@x.com", temp_db)

        # User A tries to correct User B's signal.
        result = propagate_correction("sig-b2", "cancel", "a@x.com", temp_db)
        assert result["ledger_updated"] is False  # no row matched user_email=a@x.com

        # User B's entry unchanged.
        entries = get_ledger_entries("b@x.com", temp_db)
        assert entries[0]["state"] == "active"


# ---------------------------------------------------------------------------
# 6. Backfill
# ---------------------------------------------------------------------------

class TestBackfill:
    def test_backfill_creates_entries_for_commitment_signals(self, temp_db):
        save_signal_to_db(_signal("s1", "Alex", "I'll send the proposal",
                                   signal_type="commitment_made"), db_path=temp_db, user_email="u@x.com")
        save_signal_to_db(_signal("s2", "Bob", "Weekly newsletter",
                                   signal_type="newsletter"), db_path=temp_db, user_email="u@x.com")

        count = backfill_ledger_from_signals(temp_db, user_email="u@x.com")
        assert count == 1  # only the commitment_made signal

        entries = get_ledger_entries("u@x.com", temp_db)
        assert len(entries) == 1
        assert entries[0]["entity"] == "Alex"
        assert entries[0]["state"] == "candidate"  # conservative backfill state

    def test_backfill_idempotent(self, temp_db):
        save_signal_to_db(_signal("s3", "Alex", "I'll send the proposal",
                                   signal_type="commitment_made"), db_path=temp_db, user_email="u@x.com")
        backfill_ledger_from_signals(temp_db, user_email="u@x.com")
        count2 = backfill_ledger_from_signals(temp_db, user_email="u@x.com")
        assert count2 == 0  # already backfilled


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

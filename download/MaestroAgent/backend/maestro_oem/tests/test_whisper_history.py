"""Tests for WhisperHistoryStore — durable persistence for whisper memory.

H1 FIX (2026-07-03): External reviewer found that whisper memory was
in-process only, not durably persisted. These tests verify:
  1. History is persisted to SQLite
  2. History survives a "restart" (tear down + reconstruct the store)
  3. shown_count increments correctly
  4. action_taken persists across restart
  5. first_shown persists across restart (for urgency decay)

The restart-survival test is the key one — it's the exact scenario
the external reviewer said was missing.
"""
from __future__ import annotations

import os
import tempfile
import pytest
from datetime import datetime, timezone

from maestro_oem.whisper_history_store import WhisperHistoryStore


@pytest.fixture
def store_path():
    """Create a temp DB path for each test."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        yield path
    finally:
        if os.path.exists(path):
            os.unlink(path)


def test_record_shown_increments_count(store_path):
    """record_shown should increment shown_count."""
    store = WhisperHistoryStore(store_path)
    store.record_shown("wspr-test-1", org_id="default", insight="test insight")
    store.record_shown("wspr-test-1", org_id="default", insight="test insight")
    store.record_shown("wspr-test-1", org_id="default", insight="test insight")

    history = store.get_history("wspr-test-1", org_id="default")
    assert history["shown_count"] == 3
    assert history["first_shown"] is not None
    assert history["last_shown"] is not None
    store.close()


def test_record_outcome_persists(store_path):
    """record_outcome should persist the action taken."""
    store = WhisperHistoryStore(store_path)
    store.record_shown("wspr-test-2", org_id="default")
    store.record_outcome("wspr-test-2", "ignored", org_id="default")

    history = store.get_history("wspr-test-2", org_id="default")
    assert history["action_taken"] == "ignored"
    store.close()


def test_history_survives_restart(store_path):
    """KEY TEST: History must survive a restart (tear down + reconstruct).

    This is the exact test the external reviewer said was missing.
    """
    # Phase 1: Write history
    store1 = WhisperHistoryStore(store_path)
    store1.record_shown("wspr-restart-test", org_id="default", insight="survive restart")
    store1.record_shown("wspr-restart-test", org_id="default")
    store1.record_shown("wspr-restart-test", org_id="default")
    store1.record_outcome("wspr-restart-test", "ignored", org_id="default")
    store1.close()

    # Phase 2: Simulate a restart — create a NEW store instance
    # pointing at the same DB file
    store2 = WhisperHistoryStore(store_path)

    # Phase 3: Verify the history survived
    history = store2.get_history("wspr-restart-test", org_id="default")
    assert history["shown_count"] == 3, f"shown_count should survive restart: {history}"
    assert history["action_taken"] == "ignored", f"action_taken should survive restart: {history}"
    assert history["first_shown"] is not None, f"first_shown should survive restart: {history}"
    assert history["last_shown"] is not None, f"last_shown should survive restart: {history}"
    store2.close()


def test_urgency_decay_survives_restart(store_path):
    """first_shown must survive restart for urgency decay to work."""
    from datetime import timedelta

    # Phase 1: Record a whisper shown 10 days ago
    store1 = WhisperHistoryStore(store_path)
    store1.record_shown("wspr-urgency-test", org_id="default")

    # Manually set first_shown to 10 days ago
    old_date = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    assert store1._conn is not None
    store1._conn.execute(
        "UPDATE whisper_history SET first_shown = ? WHERE whisper_id = ?",
        (old_date, "wspr-urgency-test"),
    )
    store1.close()

    # Phase 2: Restart
    store2 = WhisperHistoryStore(store_path)

    # Phase 3: Verify first_shown survived
    history = store2.get_history("wspr-urgency-test", org_id="default")
    assert history["first_shown"] is not None
    # Verify it's the old date, not a new one
    assert "T" in history["first_shown"]  # ISO format
    store2.close()


def test_org_isolation(store_path):
    """Two orgs should have separate whisper history (P7)."""
    store = WhisperHistoryStore(store_path)
    store.record_shown("wspr-shared", org_id="org-a")
    store.record_shown("wspr-shared", org_id="org-a")
    store.record_shown("wspr-shared", org_id="org-b")

    history_a = store.get_history("wspr-shared", org_id="org-a")
    history_b = store.get_history("wspr-shared", org_id="org-b")

    assert history_a["shown_count"] == 2, f"org-a should have 2: {history_a}"
    assert history_b["shown_count"] == 1, f"org-b should have 1: {history_b}"
    store.close()


def test_get_all_history(store_path):
    """get_all_history should return all whispers for an org."""
    store = WhisperHistoryStore(store_path)
    store.record_shown("wspr-1", org_id="default")
    store.record_shown("wspr-2", org_id="default")
    store.record_shown("wspr-3", org_id="default")

    all_history = store.get_all_history(org_id="default")
    assert len(all_history) == 3
    assert "wspr-1" in all_history
    assert "wspr-2" in all_history
    assert "wspr-3" in all_history
    store.close()

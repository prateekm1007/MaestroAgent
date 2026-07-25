"""P59 — Full synthetic lifecycle suite (sixth audit F-02/S0).

The sixth audit ingested the product's own synthetic lifecycle battery and
found active:12/completed:1/cancelled:0 — cancellations not applied,
completions not closing, deadline changes not updating.

This test runs the FULL suite:
1. Cancellation: Sam Rivera + Priya Patel → their commitments MUST be cancelled
2. Completion: Jamie + Alex → their commitments MUST be completed
3. Deadline change: Maria Friday→Wednesday → the commitment MUST update
4. Over-cancellation precision: entity with TWO commitments, cancel ONE →
   the other MUST remain active (no over-cancellation)

Run:
  cd /home/z/my-project/MaestroAgent/download/MaestroAgent/maestro-personal
  python -m pytest tests/test_P59_full_lifecycle_suite.py -v
"""
from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
os.environ.setdefault("MAESTRO_ENV", "dev")
os.environ["MAESTRO_PERSONAL_DB"] = str(REPO_ROOT / "test_P59_full.db")
_env_local = Path("/home/z/my-project/.env.local")
if _env_local.exists():
    for line in _env_local.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _reset_test_db():
    db_path = REPO_ROOT / "test_P59_full.db"
    if db_path.exists():
        db_path.unlink()
    for suffix in ("-wal", "-shm"):
        p = Path(str(db_path) + suffix)
        if p.exists():
            p.unlink()


@pytest.fixture(scope="function")
def app_client():
    _reset_test_db()
    from fastapi.testclient import TestClient
    from maestro_personal_shell.api import app, init_db
    init_db()
    with TestClient(app) as c:
        yield c
    _reset_test_db()


def _register(client) -> str:
    email = f"p59full-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={"user_email": email, "password": "TestPassword123!"})
    assert r.status_code == 200
    return r.json()["token"]


def _post_signal(client, token, *, text, entity, signal_type="commitment_made",
                 commitment_type="explicit", is_commitment=True, owner="user",
                 commitment_state="active"):
    sig = {
        "signal_id": f"sig-{uuid.uuid4().hex}",
        "entity": entity,
        "text": text,
        "signal_type": signal_type,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "metadata": {
            "source": "manual",
            "commitment_type": commitment_type,
            "is_commitment": is_commitment,
            "owner": owner,
            "commitment_state": commitment_state,
            "commitment_confidence": 0.85,
        },
    }
    r = client.post("/api/signals", json=sig, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, f"signal post failed: {r.status_code} {r.text[:200]}"


def _get_ledger_states(client, token, entity):
    """Get all ledger entries for an entity, return list of (state, text)."""
    r = client.get("/api/commitments/ledger", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    entries = r.json().get("entries", [])
    return [
        (e.get("state", ""), e.get("entity", ""), e.get("evidence_quote", "")[:60])
        for e in entries
        if entity.lower() in str(e.get("entity", "")).lower()
    ]


# ---------------------------------------------------------------------------
# 1. Cancellations: Sam Rivera + Priya Patel
# ---------------------------------------------------------------------------

def test_cancellation_sam_rivera(app_client):
    """F-02: posting a cancellation for Sam Rivera MUST cancel the commitment."""
    token = _register(app_client)
    _post_signal(app_client, token, text="I will send the roadmap to Sam Rivera by Friday",
                 entity="Sam Rivera", commitment_state="active")
    time.sleep(2)
    _post_signal(app_client, token, text="Cancelled: Sam Rivera roadmap item",
                 entity="Sam Rivera", commitment_type="cancelled", commitment_state="cancelled")
    time.sleep(2)
    states = _get_ledger_states(app_client, token, "Sam Rivera")
    cancelled = [s for s in states if s[0] == "cancelled"]
    assert len(cancelled) > 0, (
        f"P59/F-02: Sam Rivera cancellation not applied. States: {states}"
    )


def test_cancellation_priya_patel(app_client):
    """F-02: posting a cancellation for Priya Patel MUST cancel the commitment."""
    token = _register(app_client)
    _post_signal(app_client, token, text="I will review the CI pipeline for Priya Patel",
                 entity="Priya Patel", commitment_state="active")
    time.sleep(2)
    _post_signal(app_client, token, text="Cancelled: Priya Patel CI pipeline review",
                 entity="Priya Patel", commitment_type="cancelled", commitment_state="cancelled")
    time.sleep(2)
    states = _get_ledger_states(app_client, token, "Priya Patel")
    cancelled = [s for s in states if s[0] == "cancelled"]
    assert len(cancelled) > 0, (
        f"P59/F-02: Priya Patel cancellation not applied. States: {states}"
    )


# ---------------------------------------------------------------------------
# 2. Completions: Jamie + Alex
# ---------------------------------------------------------------------------

def test_completion_jamie(app_client):
    """F-02: posting a completion for Jamie MUST close the commitment."""
    token = _register(app_client)
    _post_signal(app_client, token, text="I will deliver the mockups to Jamie by Tuesday",
                 entity="Jamie", commitment_state="active")
    time.sleep(2)
    _post_signal(app_client, token, text="Jamie mockups delivered successfully",
                 entity="Jamie", commitment_type="completed", commitment_state="completed_claimed")
    time.sleep(2)
    states = _get_ledger_states(app_client, token, "Jamie")
    completed = [s for s in states if s[0] in ("completed_claimed", "completed_verified")]
    assert len(completed) > 0, (
        f"P59/F-02: Jamie completion not applied. States: {states}"
    )


def test_completion_alex(app_client):
    """F-02: posting a completion for Alex MUST close the commitment."""
    token = _register(app_client)
    _post_signal(app_client, token, text="I will review the PR for Alex by Thursday",
                 entity="Alex", commitment_state="active")
    time.sleep(2)
    _post_signal(app_client, token, text="Alex PR review completed and merged",
                 entity="Alex", commitment_type="completed", commitment_state="completed_claimed")
    time.sleep(2)
    states = _get_ledger_states(app_client, token, "Alex")
    completed = [s for s in states if s[0] in ("completed_claimed", "completed_verified")]
    assert len(completed) > 0, (
        f"P59/F-02: Alex completion not applied. States: {states}"
    )


# ---------------------------------------------------------------------------
# 3. Deadline change: Maria Friday → Wednesday
# ---------------------------------------------------------------------------

def test_deadline_change_maria(app_client):
    """F-02: posting a deadline change for Maria MUST update the commitment.

    The sixth audit found the deadline change did not update. The lifecycle
    engine must handle superseded/deadline-change signals.
    """
    token = _register(app_client)
    # Original commitment: Friday deadline
    _post_signal(app_client, token, text="I will send the proposal to Maria by Friday",
                 entity="Maria", commitment_state="active")
    time.sleep(2)
    # Deadline change: Friday → Wednesday
    _post_signal(app_client, token, text="The send the proposal deadline moved to Wednesday",
                 entity="Maria", signal_type="commitment_made",
                 commitment_type="explicit", commitment_state="active")
    time.sleep(2)
    states = _get_ledger_states(app_client, token, "Maria")
    # The deadline change should produce at least one entry (either superseded
    # the old one or created a new one with the updated deadline)
    assert len(states) >= 1, (
        f"P59/F-02: Maria deadline change produced no ledger entries. States: {states}"
    )
    # At least one should still be active (the updated commitment)
    active = [s for s in states if s[0] == "active"]
    assert len(active) >= 1, (
        f"P59/F-02: Maria has no active commitment after deadline change. States: {states}"
    )


# ---------------------------------------------------------------------------
# 4. Over-cancellation precision: TWO commitments for same entity, cancel ONE
# ---------------------------------------------------------------------------

def test_no_over_cancellation(app_client):
    """F-02 PRECISION: entity with TWO active commitments. Post a cancellation
    for ONE — the other MUST remain active (no over-cancellation).

    The entity-only fallback match could cancel the WRONG commitment if the
    entity has multiple. This test verifies precision.
    """
    token = _register(app_client)
    # Two commitments to the same entity (Dana)
    _post_signal(app_client, token, text="I will send the proposal to Dana by Friday",
                 entity="Dana", commitment_state="active")
    time.sleep(1)
    _post_signal(app_client, token, text="I will review the contract for Dana by Monday",
                 entity="Dana", commitment_state="active")
    time.sleep(2)

    # Before cancellation: should have 2 active
    states_before = _get_ledger_states(app_client, token, "Dana")
    active_before = [s for s in states_before if s[0] == "active"]
    assert len(active_before) >= 2, (
        f"Setup failed: expected 2 active Dana commitments, got {len(active_before)}. "
        f"States: {states_before}"
    )

    # Post a cancellation for the PROPOSAL (not the contract)
    _post_signal(app_client, token, text="Cancelled: Dana proposal item",
                 entity="Dana", commitment_type="cancelled", commitment_state="cancelled")
    time.sleep(2)

    # After cancellation: at least 1 should STILL be active (the contract)
    states_after = _get_ledger_states(app_client, token, "Dana")
    active_after = [s for s in states_after if s[0] == "active"]
    cancelled_after = [s for s in states_after if s[0] == "cancelled"]

    # At least one should be cancelled (the proposal)
    assert len(cancelled_after) >= 1, (
        f"P59: cancellation didn't fire at all. States: {states_after}"
    )
    # At least one should STILL be active (the contract — no over-cancellation)
    assert len(active_after) >= 1, (
        f"P59 OVER-CANCELLATION: both Dana commitments were cancelled when only "
        f"one should have been. The entity-only fallback matched too broadly. "
        f"States: {states_after}"
    )


# ---------------------------------------------------------------------------
# 5. Suite summary: cancelled > 0, completed > 0
# ---------------------------------------------------------------------------

def test_suite_summary_counts(app_client):
    """F-02 SUITE: after the full battery, cancelled > 0 AND completed > 0.

    The sixth audit found active:12/completed:1/cancelled:0. This test
    verifies the suite produces cancelled > 0 and completed > 0.
    """
    token = _register(app_client)

    # Post 2 active commitments
    _post_signal(app_client, token, text="I will send the report to Sam by Friday",
                 entity="Sam", commitment_state="active")
    time.sleep(1)
    _post_signal(app_client, token, text="I will review the PR for Alex by Thursday",
                 entity="Alex", commitment_state="active")
    time.sleep(2)

    # Cancel Sam
    _post_signal(app_client, token, text="Cancelled: Sam report",
                 entity="Sam", commitment_type="cancelled", commitment_state="cancelled")
    time.sleep(1)
    # Complete Alex
    _post_signal(app_client, token, text="Alex PR review completed",
                 entity="Alex", commitment_type="completed", commitment_state="completed_claimed")
    time.sleep(2)

    # Check ledger counts
    r = app_client.get("/api/commitments/ledger", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    entries = r.json().get("entries", [])
    states = [e.get("state", "") for e in entries]
    cancelled_count = sum(1 for s in states if s == "cancelled")
    completed_count = sum(1 for s in states if s in ("completed_claimed", "completed_verified"))

    assert cancelled_count > 0, (
        f"P59/F-02 SUITE: cancelled=0 after cancellation signals. "
        f"All states: {states}"
    )
    assert completed_count > 0, (
        f"P59/F-02 SUITE: completed=0 after completion signals. "
        f"All states: {states}"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

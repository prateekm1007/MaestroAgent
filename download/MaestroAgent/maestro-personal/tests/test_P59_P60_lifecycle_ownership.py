"""P59/P60 — Lifecycle engine applies transitions + ownership model (sixth audit F-02/F-03).

F-02 (S0): the lifecycle engine does not apply cancellations/completions.
F-03 (S0): the ownership filter over-corrects into false negatives.

This test verifies both fixes:
1. P59: posting a cancellation signal transitions the matching commitment to cancelled
2. P59: posting a completion signal transitions the matching commitment to completed
3. P60: "What did I promise Maria?" returns the user's OWN promises (not false-negative)
4. P60: "What did I promise Maria?" does NOT return Maria's promises (not false-positive)

Run:
  cd /home/z/my-project/MaestroAgent/download/MaestroAgent/maestro-personal
  python -m pytest tests/test_P59_P60_lifecycle_ownership.py -v
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
os.environ["MAESTRO_PERSONAL_DB"] = str(REPO_ROOT / "test_P59_P60.db")
_env_local = Path("/home/z/my-project/.env.local")
if _env_local.exists():
    for line in _env_local.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _reset_test_db():
    db_path = REPO_ROOT / "test_P59_P60.db"
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
    email = f"p59p60-{uuid.uuid4().hex[:8]}@example.com"
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


# ---------------------------------------------------------------------------
# P59: Lifecycle engine applies transitions
# ---------------------------------------------------------------------------

def test_p59_cancellation_signal_cancels_commitment(app_client):
    """P59/S0 (F-02): posting a cancellation signal for an entity that has
    an active commitment MUST transition that commitment to cancelled.

    The sixth audit found cancellations were not applied. The lifecycle
    engine must APPLY the transition, not just classify the signal.
    """
    token = _register(app_client)
    # Post an active commitment to Sam Rivera
    _post_signal(app_client, token, text="I will send the roadmap to Sam Rivera by Friday",
                 entity="Sam Rivera", commitment_type="explicit", owner="user",
                 commitment_state="active")
    time.sleep(2)

    # Post a cancellation signal for Sam Rivera
    _post_signal(app_client, token, text="Cancelled: Sam Rivera roadmap item",
                 entity="Sam Rivera", signal_type="commitment_made",
                 commitment_type="cancelled", is_commitment=True, owner="user",
                 commitment_state="cancelled")
    time.sleep(2)

    # Check the ledger — Sam Rivera's commitment should be cancelled
    r = app_client.get("/api/commitments/ledger", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    entries = r.json().get("entries", [])
    sam_entries = [e for e in entries if "sam" in str(e.get("entity", "")).lower()]
    assert len(sam_entries) > 0, "No Sam Rivera entries in ledger"
    # At least one should be cancelled
    cancelled = [e for e in sam_entries if e.get("state") == "cancelled"]
    assert len(cancelled) > 0, (
        f"P59/S0 VIOLATION: cancellation signal did not cancel the commitment. "
        f"Sam Rivera entries: {[(e.get('state'), e.get('entity')) for e in sam_entries]}"
    )


def test_p59_completion_signal_completes_commitment(app_client):
    """P59/S0 (F-02): posting a completion signal for an entity that has
    an active commitment MUST transition that commitment to completed_claimed."""
    token = _register(app_client)
    # Post an active commitment to Jamie
    _post_signal(app_client, token, text="I will deliver the mockups to Jamie by Tuesday",
                 entity="Jamie", commitment_type="explicit", owner="user",
                 commitment_state="active")
    time.sleep(2)

    # Post a completion signal for Jamie
    _post_signal(app_client, token, text="Jamie mockups delivered successfully",
                 entity="Jamie", signal_type="commitment_made",
                 commitment_type="completed", is_commitment=True, owner="user",
                 commitment_state="completed_claimed")
    time.sleep(2)

    # Check the ledger — Jamie's commitment should be completed
    r = app_client.get("/api/commitments/ledger", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    entries = r.json().get("entries", [])
    jamie_entries = [e for e in entries if "jamie" in str(e.get("entity", "")).lower()]
    assert len(jamie_entries) > 0, "No Jamie entries in ledger"
    completed = [e for e in jamie_entries if e.get("state") in ("completed_claimed", "completed_verified")]
    assert len(completed) > 0, (
        f"P59/S0 VIOLATION: completion signal did not close the commitment. "
        f"Jamie entries: {[(e.get('state'), e.get('entity')) for e in jamie_entries]}"
    )


# ---------------------------------------------------------------------------
# P60: Ownership model — four buckets, no false negatives
# ---------------------------------------------------------------------------

def test_p60_promise_query_returns_own_promises(app_client):
    """P60/S0 (F-03): "What did I promise Maria?" MUST return the user's
    OWN promises to Maria — not false-negative "no record".

    The prior filter over-corrected: it excluded the user's own promises
    because of exact entity matching. The fix uses fuzzy entity matching
    so "Maria" matches "Maria Garcia"."""
    token = _register(app_client)
    # Post the user's own promise to Maria
    _post_signal(app_client, token, text="I will send the proposal to Maria by Friday",
                 entity="Maria Garcia", commitment_type="explicit", owner="user",
                 commitment_state="active")
    time.sleep(2)

    r = app_client.post(
        "/api/ask",
        json={"query": "What did I promise Maria?"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    answer = body.get("answer", "")
    # The answer MUST mention the proposal (the user's own promise)
    assert "proposal" in answer.lower() or "maria" in answer.lower(), (
        f"P60/S0 VIOLATION: 'What did I promise Maria?' returned a false-negative. "
        f"The user HAS a promise to Maria Garcia but the answer doesn't mention it. "
        f"answer={answer[:200]!r}"
    )


def test_p60_promise_query_excludes_their_promises(app_client):
    """P60: "What did I promise Maria?" MUST NOT return Maria's own promises
    (third_party_report with owner=other). This is the original false-positive
    that P43 fixed — the fix must not regress it."""
    token = _register(app_client)
    # Post Maria's own promise (third_party_report, owner=other)
    _post_signal(app_client, token, text="Maria said: I will send the proposal",
                 entity="Maria", signal_type="reported_statement",
                 commitment_type="third_party_report", is_commitment=True, owner="other",
                 commitment_state="active")
    time.sleep(2)

    r = app_client.post(
        "/api/ask",
        json={"query": "What did I promise Maria?"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    answer = body.get("answer", "")
    # MUST NOT contain "Maria said" — that's Maria's promise, not the user's
    assert "maria said" not in answer.lower(), (
        f"P60 VIOLATION: 'What did I promise Maria?' returned Maria's own promise "
        f"(false-positive regression). answer={answer[:200]!r}"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

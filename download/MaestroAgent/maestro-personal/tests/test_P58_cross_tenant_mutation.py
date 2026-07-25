"""P58 — Authorization covers mutations, not just reads (sixth audit F-01/S0).

The sixth audit found a cross-tenant mutation IDOR: any user can cancel
any other user's commitments via /api/commitments/{id}/transition. The
fifth audit verified READ isolation but did not test MUTATIONS.

This test registers two users, creates a commitment for user A, then
attempts to transition (cancel) it as user B — which MUST return 403.

Run:
  cd /home/z/my-project/MaestroAgent/download/MaestroAgent/maestro-personal
  python -m pytest tests/test_P58_cross_tenant_mutation.py -v
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
os.environ["MAESTRO_PERSONAL_DB"] = str(REPO_ROOT / "test_P58_idor.db")
_env_local = Path("/home/z/my-project/.env.local")
if _env_local.exists():
    for line in _env_local.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _reset_test_db():
    db_path = REPO_ROOT / "test_P58_idor.db"
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


def _register(client, email=None) -> str:
    email = email or f"p58-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={"user_email": email, "password": "TestPassword123!"})
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text[:200]}"
    return r.json()["token"], email


def _post_signal(client, token, *, text, entity):
    sig = {
        "signal_id": f"sig-{uuid.uuid4().hex}",
        "entity": entity,
        "text": text,
        "signal_type": "commitment_made",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "metadata": {
            "source": "manual",
            "commitment_type": "explicit",
            "is_commitment": True,
            "owner": "user",
            "commitment_state": "active",
            "commitment_confidence": 0.85,
        },
    }
    r = client.post("/api/signals", json=sig, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


def _get_ledger_id(client, token, entity) -> str:
    """Get the ledger_id for a commitment matching the entity."""
    r = client.get("/api/commitments/ledger", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    entries = r.json().get("entries", [])
    for e in entries:
        if entity.lower() in str(e.get("entity", "")).lower():
            return e["ledger_id"]
    # If no ledger entry yet, check /api/commitments
    r2 = client.get("/api/commitments", headers={"Authorization": f"Bearer {token}"})
    comms = r2.json() if isinstance(r2.json(), list) else r2.json().get("commitments", [])
    for c in comms:
        if entity.lower() in str(c.get("entity", "")).lower():
            return c.get("signal_id", "")
    return ""


def test_cross_tenant_transition_returns_403(app_client):
    """P58/S0: user B MUST NOT be able to cancel user A's commitment.

    This is the EXACT reproduction from the sixth audit: register two
    users, create a commitment for user A, attempt to transition (cancel)
    it as user B. The prior code returned 200 (transitioned: true) —
    a cross-tenant mutation IDOR. The fix MUST return 403.
    """
    # User A registers and creates a commitment
    token_a, email_a = _register(app_client)
    _post_signal(app_client, token_a, text="I will send the proposal to Maria by Friday",
                 entity="Maria")
    time.sleep(2)  # allow ledger write

    # Get user A's ledger entry
    ledger_id = _get_ledger_id(app_client, token_a, "Maria")
    assert ledger_id, "Could not find ledger_id for user A's Maria commitment"

    # User B registers (a completely different tenant)
    token_b, email_b = _register(app_client)

    # User B attempts to transition (cancel) user A's commitment
    r = app_client.post(
        f"/api/commitments/{ledger_id}/transition?to_state=cancelled",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 403, (
        f"P58/S0 VIOLATION: cross-tenant transition returned {r.status_code}, "
        f"expected 403. User B ({email_b}) was able to cancel user A's ({email_a}) "
        f"commitment (ledger_id={ledger_id}). This is the cross-tenant mutation "
        f"IDOR the sixth audit found. Response: {r.text[:200]}"
    )


def test_same_tenant_transition_succeeds(app_client):
    """P58 regression: user A CAN transition their OWN commitment."""
    token_a, _ = _register(app_client)
    _post_signal(app_client, token_a, text="I will send the proposal to Maria by Friday",
                 entity="Maria")
    time.sleep(2)

    ledger_id = _get_ledger_id(app_client, token_a, "Maria")
    assert ledger_id

    r = app_client.post(
        f"/api/commitments/{ledger_id}/transition?to_state=cancelled",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert r.status_code == 200, (
        f"P58 regression: same-tenant transition failed: {r.status_code} {r.text[:200]}"
    )
    assert r.json().get("transitioned") is True


def test_cross_tenant_transition_nonexistent_returns_404(app_client):
    """P58: a transition on a non-existent ledger_id returns 404, not 403."""
    token_a, _ = _register(app_client)
    fake_id = f"nonexistent-{uuid.uuid4().hex}"

    r = app_client.post(
        f"/api/commitments/{fake_id}/transition?to_state=cancelled",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert r.status_code == 404, (
        f"P58: transition on non-existent ledger should return 404, got {r.status_code}"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

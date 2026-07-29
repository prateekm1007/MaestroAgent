"""Phase 4.1: Multi-tenancy isolation test (auditor v13).

The v13 auditor found: "Auth principal == data principal (still
default@personal.local); cross-user isolation proven by test."

This test creates two users, posts a signal as user A, and verifies
that user B cannot see user A's signal. This is the cross-user
isolation proof.

Run locally:
  PYTHONPATH=src pytest tests/test_multi_tenant_isolation.py -v
"""
from __future__ import annotations

import os
import tempfile
import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def fresh_client():
    """Create a fresh test client with an isolated DB."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False, prefix="mt_test_")
    tmp.close()
    os.environ["MAESTRO_PERSONAL_DB"] = tmp.name
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "mt-test-token"
    os.environ["MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL"] = "1"
    os.environ.pop("MAESTRO_PERSONAL_ENV", None)

    import importlib
    from maestro_personal_shell import api as personal_api
    importlib.reload(personal_api)
    personal_api.init_db()

    yield TestClient(personal_api.app)

    os.unlink(tmp.name)


def _register_and_login(client, email: str, password: str = "TestPassword123!") -> str:
    """Register a new user and return their auth token."""
    r = client.post("/api/auth/register", json={
        "user_email": email,
        "password": password,
        "name": email.split("@")[0],
    })
    assert r.status_code == 200, f"Register failed: {r.status_code} {r.text}"
    return r.json()["token"]


def _post_signal(client, token: str, entity: str, text: str) -> dict:
    """Post a signal as the given user."""
    r = client.post("/api/signals", json={
        "entity": entity,
        "text": text,
        "signal_type": "commitment_made",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, f"POST signal failed: {r.status_code} {r.text}"
    return r.json()


def _get_signals(client, token: str) -> list:
    """Get all signals for the given user."""
    r = client.get("/api/signals", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    return r.json()


def test_cross_user_isolation(fresh_client):
    """Phase 4.1: User A's signals must NOT be visible to User B.

    This is the fundamental multi-tenancy guarantee: auth principal ==
    data principal. If user B can see user A's signals, the isolation
    is broken.
    """
    c = fresh_client

    # Register two distinct users
    token_a = _register_and_login(c, "alice@test.com")
    token_b = _register_and_login(c, "bob@test.com")

    # Alice posts a signal
    _post_signal(c, token_a, "Charlie Delta", "Alice's private commitment to Charlie")

    # Bob posts a different signal
    _post_signal(c, token_b, "Eve Frank", "Bob's private commitment to Eve")

    # Alice should see ONLY her signal (Charlie Delta), not Bob's (Eve Frank)
    alice_signals = _get_signals(c, token_a)
    alice_entities = {s.get("entity", "") for s in alice_signals}
    assert "Charlie Delta" in alice_entities, "Alice should see her own signal"
    assert "Eve Frank" not in alice_entities, (
        "SECURITY: Alice can see Bob's signal — cross-user isolation BROKEN"
    )

    # Bob should see ONLY his signal (Eve Frank), not Alice's (Charlie Delta)
    bob_signals = _get_signals(c, token_b)
    bob_entities = {s.get("entity", "") for s in bob_signals}
    assert "Eve Frank" in bob_entities, "Bob should see his own signal"
    assert "Charlie Delta" not in bob_entities, (
        "SECURITY: Bob can see Alice's signal — cross-user isolation BROKEN"
    )


def test_cross_user_ask_isolation(fresh_client):
    """Phase 4.1: User B's Ask queries must NOT return User A's data."""
    c = fresh_client

    token_a = _register_and_login(c, "alice2@test.com")
    token_b = _register_and_login(c, "bob2@test.com")

    # Alice posts a signal about "Project Secret"
    _post_signal(c, token_a, "Project Secret", "Alice's confidential project deadline")

    # Bob asks about Project Secret — should get abstention (no records)
    r = c.post("/api/ask", json={"query": "What's the status of Project Secret?"},
               headers={"Authorization": f"Bearer {token_b}"})
    assert r.status_code == 200
    answer = r.json().get("answer", "").lower()
    # Bob should NOT see Alice's confidential project info
    assert "confidential project" not in answer, (
        "SECURITY: Bob's Ask query returned Alice's private data — isolation BROKEN"
    )


def test_cross_user_commitment_isolation(fresh_client):
    """Phase 4.1: User B's commitment list must NOT include User A's commitments."""
    c = fresh_client

    token_a = _register_and_login(c, "alice3@test.com")
    token_b = _register_and_login(c, "bob3@test.com")

    # Alice posts a commitment
    _post_signal(c, token_a, "Alice Client", "I will send the report by Friday")

    # Bob checks his commitments — should NOT include Alice's
    r = c.get("/api/commitments", headers={"Authorization": f"Bearer {token_b}"})
    assert r.status_code == 200
    commitments = r.json()
    bob_entities = {c.get("entity", "") for c in commitments}
    assert "Alice Client" not in bob_entities, (
        "SECURITY: Bob's commitment list includes Alice's data — isolation BROKEN"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

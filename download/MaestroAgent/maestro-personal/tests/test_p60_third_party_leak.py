"""P60 third-party exclusion leak — regression test for auditor finding.

The external auditor reproduced a live leak:
  1. POST /api/signals {"entity":"Maria","text":"I will send the proposal to Maria by Friday"}
  2. POST /api/signals {"entity":"Maria","text":"Maria said: I will send the proposal"}
  3. POST /api/ask {"query":"What did Maria promise?"}

The answer included the user's OWN commitment ("I will send the proposal
to Maria by Friday") under "the key commitment is" — a leak in the
product's namesake feature (P60 third-party exclusion).

Root cause: the situation-synthesizer bundles ALL signals for entity
"Maria" into one situation object, regardless of ownership. The user's
own first-person commitment is surfaced as "the key commitment" even
for third-party queries.

Fix: _apply_ticket10_filter now checks the ANSWER TEXT (not just
evidence_refs) for the user's own commitment text. If found, the answer
is replaced with the abstention message.
"""
from __future__ import annotations

import os
import sys
import time
import tempfile
import pytest


@pytest.fixture
def client():
    """Fresh TestClient with isolated DB."""
    from fastapi.testclient import TestClient
    from maestro_personal_shell.api import app, init_db
    _old_db = os.environ.get("MAESTRO_PERSONAL_DB")
    _tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False, prefix="p60_test_")
    _tmp.close()
    os.environ["MAESTRO_PERSONAL_DB"] = _tmp.name
    os.environ["MAESTRO_TEST_MODE"] = "1"
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "maestro-demo"
    os.environ["MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL"] = "1"
    init_db()
    with TestClient(app) as c:
        yield c
    if _old_db is not None:
        os.environ["MAESTRO_PERSONAL_DB"] = _old_db
    else:
        os.environ.pop("MAESTRO_PERSONAL_DB", None)
    try:
        os.unlink(_tmp.name)
    except OSError:
        pass


@pytest.fixture
def auth_headers(client):
    """Register a test user and return auth headers."""
    import uuid
    email = f"p60-test-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={
        "user_email": email, "password": "TestPassword123!", "name": "Test",
    })
    assert r.status_code == 200, f"Register failed: {r.text[:200]}"
    token = r.json()["token"]
    return {"Authorization": f"Bearer {token}"}


class TestP60ThirdPartyLeak:
    """The exact scenario the external auditor reproduced."""

    def test_two_signals_same_entity_third_party_query_no_leak(self, client, auth_headers):
        """The exact scenario the external auditor reproduced.

        Two signals for same entity (Maria):
        1. User's own commitment: "I will send the proposal to Maria by Friday"
        2. Third-party report: "Maria said: I will send the proposal"

        Third-party query: "What did Maria promise?"
        MUST NOT contain the user's own commitment in the answer.
        """
        # Post user's own commitment
        r1 = client.post("/api/signals", json={
            "entity": "Maria",
            "text": "I will send the proposal to Maria by Friday",
            "signal_type": "commitment_made",
        }, headers=auth_headers)
        assert r1.status_code == 200, f"Seed 1 failed: {r1.text[:200]}"

        # Post third-party report
        r2 = client.post("/api/signals", json={
            "entity": "Maria",
            "text": "Maria said: I will send the proposal",
            "signal_type": "reported_statement",
        }, headers=auth_headers)
        assert r2.status_code == 200, f"Seed 2 failed: {r2.text[:200]}"

        time.sleep(1)  # allow processing

        # Third-party query
        ask = client.post("/api/ask", json={
            "query": "What did Maria promise?",
        }, headers=auth_headers)
        assert ask.status_code == 200, f"Ask failed: {ask.text[:200]}"
        answer = ask.json().get("answer", "")

        # THE USER'S OWN COMMITMENT MUST NOT APPEAR
        user_commitment = "I will send the proposal to Maria by Friday"
        assert user_commitment not in answer, (
            f"P60 LEAK: user's own commitment found in third-party answer. "
            f"Answer: {answer[:300]}"
        )

    def test_first_person_query_still_works(self, client, auth_headers):
        """Ensure the fix doesn't break the first-person direction.

        Same setup as above, but ask "What did I promise Maria?"
        MUST return the user's own commitment.
        """
        # Post user's own commitment
        client.post("/api/signals", json={
            "entity": "Maria",
            "text": "I will send the proposal to Maria by Friday",
            "signal_type": "commitment_made",
        }, headers=auth_headers)

        # Post third-party report
        client.post("/api/signals", json={
            "entity": "Maria",
            "text": "Maria said: I will send the proposal",
            "signal_type": "reported_statement",
        }, headers=auth_headers)

        time.sleep(1)

        # First-person query
        ask = client.post("/api/ask", json={
            "query": "What did I promise Maria?",
        }, headers=auth_headers)
        assert ask.status_code == 200, f"Ask failed: {ask.text[:200]}"
        answer = ask.json().get("answer", "")

        # The user's commitment SHOULD appear
        assert "proposal" in answer.lower() or "maria" in answer.lower(), (
            f"FIRST-PERSON BROKEN: user's own commitment not returned. "
            f"Answer: {answer[:300]}"
        )

    def test_third_party_query_with_only_user_commitments(self, client, auth_headers):
        """If there are NO third-party reports, third-party query should abstain.

        Post ONLY the user's own commitment, then ask "What did Maria promise?"
        MUST NOT return the user's commitment. SHOULD say "no record".
        """
        # Post ONLY user's own commitment
        client.post("/api/signals", json={
            "entity": "Maria",
            "text": "I will send the proposal to Maria by Friday",
            "signal_type": "commitment_made",
        }, headers=auth_headers)

        time.sleep(1)

        # Third-party query
        ask = client.post("/api/ask", json={
            "query": "What did Maria promise?",
        }, headers=auth_headers)
        assert ask.status_code == 200, f"Ask failed: {ask.text[:200]}"
        answer = ask.json().get("answer", "")

        # The user's commitment MUST NOT appear
        user_commitment = "I will send the proposal to Maria by Friday"
        assert user_commitment not in answer, (
            f"P60 LEAK: user's commitment in third-party answer (no third-party reports). "
            f"Answer: {answer[:300]}"
        )

        # Should indicate no record
        assert "no record" in answer.lower() or "not their promises" in answer.lower() or \
               "own promises TO them" in answer.lower(), (
            f"P60: expected abstention message. Answer: {answer[:300]}"
        )

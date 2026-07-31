"""TICKET-10: Final-gate ownership/third-party filter on EVERY AskResponse.

Verifies that:
1. "What did I promise Maria?" → returns user's own commitment (owner=user)
2. "What did Maria promise?" → does NOT return user's own commitment (third-party leak prevented)
3. The filter works on BOTH the RC2 fast path AND the general/LLM path
"""
from __future__ import annotations

import os
import pytest


def test_ticket10_first_person_promise_returns_user_commitment(client, auth_headers):
    """TICKET-10: 'What did I promise Maria?' returns the user's own commitment."""
    r = client.post("/api/inbox/synthetic/email_01/receive", headers=auth_headers)
    assert r.status_code == 200, f"Seed failed: {r.text}"

    r = client.post("/api/ask",
        headers=auth_headers,
        json={"query": "What did I promise Maria?"})
    assert r.status_code == 200, f"Ask failed: {r.text}"
    answer = r.json().get("answer", "").lower()
    assert "maria" in answer
    # Should contain the user's commitment
    assert "proposal" in answer or "budget" in answer or "send" in answer


def test_ticket10_third_party_promise_excludes_user_commitment(client, auth_headers):
    """TICKET-10: 'What did Maria promise?' does NOT return the user's own commitment.

    This is the core third-party leak prevention. The user's commitment TO Maria
    is NOT what Maria promised — it's what the user promised. The filter must
    exclude owner=user evidence for third-party promise queries.
    """
    r = client.post("/api/inbox/synthetic/email_01/receive", headers=auth_headers)
    assert r.status_code == 200, f"Seed failed: {r.text}"

    r = client.post("/api/ask",
        headers=auth_headers,
        json={"query": "What did Maria promise?"})
    assert r.status_code == 200, f"Ask failed: {r.text}"
    data = r.json()
    answer = data.get("answer", "").lower()

    # The answer should NOT contain the user's commitment text
    # (the user's commitment is "I will send the Q3 budget proposal")
    user_commitment_text = "i will send"
    assert user_commitment_text not in answer, (
        f"TICKET-10 VIOLATION: 'What did Maria promise?' returned the user's own "
        f"commitment ('{user_commitment_text}'). This is a third-party leak — the "
        f"user's promise TO Maria is not what Maria promised. Answer: {answer}"
    )

    # The answer should indicate no record of Maria's promises
    assert "no record" in answer or "no promises" in answer or "not their promises" in answer, (
        f"TICKET-10: expected honest abstention for third-party query. Answer: {answer}"
    )


def test_ticket10_filter_works_on_multiple_phrasings(client, auth_headers):
    """TICKET-10: the third-party exclusion works on different phrasings."""
    r = client.post("/api/inbox/synthetic/email_01/receive", headers=auth_headers)
    assert r.status_code == 200

    # Test multiple phrasings that should all exclude the user's commitment
    for query in [
        "What did Maria promise?",
        "What did Maria commit to?",
        "What did Maria agree to?",
    ]:
        r = client.post("/api/ask",
            headers=auth_headers,
            json={"query": query})
        assert r.status_code == 200, f"Ask failed for '{query}': {r.text}"
        answer = r.json().get("answer", "").lower()
        # None of these should contain the user's commitment
        assert "i will send" not in answer, (
            f"TICKET-10 VIOLATION: '{query}' returned the user's own commitment. "
            f"Answer: {answer}"
        )

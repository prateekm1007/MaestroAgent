"""K3-COMPOUND: compound-question decomposition test.

Verifies that "What did I promise Maria? Also, what did I promise Elon Musk?"
returns BOTH:
- Maria's actual commitment (from the ledger)
- A grounded negative for Elon Musk ("No record of any promise to Elon Musk.")

Previously, only the Maria half was answered — the Elon half was silently
dropped. This is the Cat 3 S2 finding from the K3 forensic audit that kept
Cat 3 at 8/10 instead of 9/10.
"""
from __future__ import annotations

import os
import time
import pytest


def test_compound_question_addresses_both_halves(client, auth_headers):
    """K3-COMPOUND: 'What did I promise Maria? Also, what did I promise Elon Musk?' addresses both."""
    # Seed a Maria commitment
    r = client.post("/api/inbox/synthetic/email_01/receive",
        headers=auth_headers)
    assert r.status_code == 200, f"Seed failed: {r.text}"

    # Ask the compound question
    r = client.post("/api/ask",
        headers=auth_headers,
        json={"query": "What did I promise Maria? Also, what did I promise Elon Musk?"},
    )
    assert r.status_code == 200, f"Ask failed: {r.text}"
    answer = r.json().get("answer", "").lower()

    # Maria half: should contain Maria's commitment
    assert "maria" in answer, f"Maria half not addressed. Answer: {answer}"

    # Elon half: should contain a grounded negative for Elon
    assert "elon" in answer, f"Elon half not addressed. Answer: {answer}"
    assert "no record" in answer or "no evidence" in answer or "don't have" in answer, \
        f"Elon half should have a grounded negative. Answer: {answer}"


def test_single_entity_question_unchanged(client, auth_headers):
    """K3-COMPOUND: single-entity questions still work as before (no regression)."""
    r = client.post("/api/inbox/synthetic/email_01/receive",
        headers=auth_headers)
    assert r.status_code == 200, f"Seed failed: {r.text}"

    r = client.post("/api/ask",
        headers=auth_headers,
        json={"query": "What did I promise Maria?"})
    assert r.status_code == 200, f"Ask failed: {r.text}"
    answer = r.json().get("answer", "").lower()
    assert "maria" in answer
    # Should NOT contain a grounded negative for Elon (Elon isn't mentioned)
    assert "elon" not in answer


def test_compound_with_unknown_entity_only(client, auth_headers):
    """K3-COMPOUND: 'What did I promise NonexistentPerson?' abstains honestly."""
    r = client.post("/api/ask",
        headers=auth_headers,
        json={"query": "What did I promise NonexistentPerson?"})
    assert r.status_code == 200, f"Ask failed: {r.text}"
    answer = r.json().get("answer", "").lower()
    # Should contain a grounded negative or abstention
    assert "no record" in answer or "no evidence" in answer or "don't have" in answer or "nothing" in answer, \
        f"Unknown entity should get grounded negative. Answer: {answer}"

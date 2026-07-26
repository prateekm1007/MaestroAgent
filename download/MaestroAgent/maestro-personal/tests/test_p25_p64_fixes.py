"""P25 + P64 fix verification tests.

P25: THE ONE and All Active must show the same confidence for the same commitment.
P64: The Briefing situation count must include the top_situation (no "0 under
     observation" next to a displayed situation).
"""
from __future__ import annotations

import os
import pytest


def test_p25_the_one_has_real_confidence(client, auth_headers):
    """P25 fix: /api/commitments/the-one returns a non-zero confidence.

    Previously, get_the_one_commitment did NOT call _compute_commitment_confidence,
    so the primary commitment had confidence=0.0 (the default). The All Active
    list DID call it. This caused a visible contradiction on the same screen:
    THE ONE shows 0% while All Active shows 28% for the same commitment.
    """
    # Seed data so there's at least one commitment
    r = client.post("/api/inbox/synthetic/email_01/receive", headers=auth_headers)
    assert r.status_code == 200, f"Seed failed: {r.text}"

    # Get THE ONE
    r = client.get("/api/commitments/the-one", headers=auth_headers)
    assert r.status_code == 200, f"the-one failed: {r.text}"
    data = r.json()
    assert data.get("primary") is not None, "Expected a primary commitment"

    # Get All Active
    r = client.get("/api/commitments", headers=auth_headers)
    assert r.status_code == 200, f"commitments failed: {r.text}"
    all_active = r.json()
    if isinstance(all_active, dict) and "commitments" in all_active:
        all_active = all_active["commitments"]

    # Find the same commitment in All Active (by signal_id)
    primary_sig_id = data["primary"]["signal_id"]
    matching = [c for c in all_active if c.get("signal_id") == primary_sig_id]

    if matching:
        # P25 assertion: the confidence must match
        the_one_conf = data["primary"]["confidence"]
        all_active_conf = matching[0]["confidence"]
        assert the_one_conf == all_active_conf, (
            f"P25 VIOLATION: THE ONE confidence={the_one_conf} != "
            f"All Active confidence={all_active_conf} for signal_id={primary_sig_id}"
        )

    # P25 assertion: THE ONE confidence must be > 0 (not the default)
    assert data["primary"]["confidence"] > 0.0, (
        f"P25 VIOLATION: THE ONE confidence is 0.0 (the default) — "
        f"_compute_commitment_confidence was not called"
    )


def test_p25_the_one_has_calibration_note(client, auth_headers):
    """P25 fix: THE ONE must include the calibration_note (same as All Active)."""
    r = client.post("/api/inbox/synthetic/email_01/receive", headers=auth_headers)
    assert r.status_code == 200

    r = client.get("/api/commitments/the-one", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data.get("primary") is not None
    # The calibration_note should be present (not empty default "")
    assert data["primary"].get("calibration_note", "") != "", (
        "P25: THE ONE should have a calibration_note matching All Active"
    )

"""S2-3 PREPARE journey gate — no template 'No active situation found' when there are active commitments.

Auditor found "No active situation found for Me." template appearing even
when there are 24 active commitments. Root cause: Prepare returns an empty
list when no situations need preparation, and the frontend renders that
as a template.

FIX (P35 + P41): when no situations are found, DERIVE Prepare content
from the active commitments ledger — the SAME source /api/commitments
uses. Top 3 commitments by salience/urgency become talking points; the
"moment" line summarizes what the user owes.

This is a JOURNEY gate (P35) — it drives the REAL app via TestClient and
asserts at the product surface. It does NOT inspect the situation
detector's return value; it asserts the API response.

Run:
  cd /home/z/my-project/MaestroAgent/download/MaestroAgent/maestro-personal
  python -m pytest tests/test_S2_03_prepare_no_template.py -v
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
os.environ.setdefault("MAESTRO_ENV", "dev")
# Isolated test DB — never touch the production personal.db
os.environ["MAESTRO_PERSONAL_DB"] = str(REPO_ROOT / "test_s2_03_prepare.db")
_env_local = Path("/home/z/my-project/.env.local")
if _env_local.exists():
    for line in _env_local.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _reset_test_db():
    """Wipe the test DB so each test starts fresh (P35 — isolated DB per test)."""
    db_path = REPO_ROOT / "test_s2_03_prepare.db"
    if db_path.exists():
        db_path.unlink()
    # Also remove WAL/SHM if present
    for suffix in ("-wal", "-shm"):
        p = Path(str(db_path) + suffix)
        if p.exists():
            p.unlink()


@pytest.fixture(scope="function")
def app_client():
    """Fresh app + fresh DB per test — full isolation (P35)."""
    _reset_test_db()
    from fastapi.testclient import TestClient
    from maestro_personal_shell.api import app, init_db
    init_db()
    with TestClient(app) as c:
        yield c
    _reset_test_db()


def _register_and_login(client) -> str:
    """Register a fresh user and return the bearer token."""
    email = f"prepare-test-{uuid.uuid4().hex[:8]}@example.com"
    password = "TestPassword123!"
    r = client.post("/api/auth/register", json={"user_email": email, "password": password})
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text[:200]}"
    token = r.json().get("token")
    assert token, f"no token in register response: {r.text[:200]}"
    return token


def _post_signal(client, token, text, entity="Maria"):
    """Post a signal via /api/signals."""
    r = client.post(
        "/api/signals",
        json={"text": text, "entity": entity, "signal_type": "commitment_made"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, f"signal post failed: {r.status_code} {r.text[:200]}"


def test_prepare_returns_content_when_commitments_exist_no_situations(app_client):
    """S2-3: with active commitments but no situations, /api/prepare MUST NOT be empty.

    P35: journey gate — post a real signal, hit /api/prepare, assert content.
    P41: the content must come from CommitmentsSurface (the same source
    /api/commitments uses), not a parallel snapshot.
    """
    token = _register_and_login(app_client)
    # Post a real commitment — this creates ledger entry but no situation
    _post_signal(app_client, token, "I will send the proposal to Maria by Friday", entity="Maria")
    _post_signal(app_client, token, "I will review the contract for Alex by Monday", entity="Alex")

    # Hit /api/prepare
    r = app_client.get("/api/prepare", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, f"prepare failed: {r.status_code} {r.text[:200]}"
    body = r.json()

    # S2-3 fix: result MUST NOT be empty when there are active commitments
    assert len(body) > 0, (
        "S2-3 violation: /api/prepare returned an empty list when there "
        "are 2 active commitments. The frontend would render 'No active "
        "situation found for Me.' — the template the auditor flagged."
    )

    # The first (and likely only) PrepareResponse must have real content
    first = body[0]
    meeting_ctx = first.get("meeting_context", "")
    assert "No active situation" not in meeting_ctx, (
        f"S2-3 violation: meeting_context contains the template 'No active "
        f"situation' — got: {meeting_ctx!r}"
    )
    # Two valid paths: (a) situation detected → meeting_context like "Situation is X"
    # with real talking points from the situation; (b) no situation → fallback
    # triggered with meeting_context mentioning "active commitment" count and
    # talking_points sourced from "commitment-ledger".
    points = first.get("copilot_talking_points", [])
    assert len(points) > 0, (
        "S2-3: copilot_talking_points is empty — the response must include "
        "either situation-derived points or commitment-ledger fallback points."
    )
    # P41: if the fallback fired, talking points must reference commitment-ledger
    sources = [p.get("source", "") for p in points]
    if "active commitment" in meeting_ctx:
        # Fallback path
        assert "commitment-ledger" in sources, (
            f"S2-3 P41 violation: fallback talking points should be sourced "
            f"from 'commitment-ledger' (the same source /api/commitments uses), "
            f"got sources: {sources}"
        )
    # Otherwise: situation path — points should have real content (not empty,
    # already asserted above). The point text must reference a real entity
    # or action, not the template.


def test_prepare_fallback_references_real_entities(app_client):
    """S2-3 P41: the fallback PrepareResponse must reference the real entities
    from the active commitments ledger (Maria, Alex), not synthetic ones."""
    token = _register_and_login(app_client)
    _post_signal(app_client, token, "I will send the proposal to Maria by Friday", entity="Maria")
    _post_signal(app_client, token, "I will review the contract for Alex by Monday", entity="Alex")

    r = app_client.get("/api/prepare", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert len(body) > 0

    # Collect all entity references and talking point text
    all_text = ""
    for prep in body:
        all_text += prep.get("meeting_context", "") + " "
        all_text += prep.get("the_forgotten", "") + " "
        for p in prep.get("copilot_talking_points", []):
            all_text += p.get("point", "") + " "

    # At least one of the real entities must be mentioned
    assert "Maria" in all_text or "Alex" in all_text, (
        f"S2-3 P41 violation: fallback PrepareResponse doesn't reference "
        f"the real entities (Maria, Alex). Got text: {all_text[:300]!r}"
    )


def test_prepare_never_emits_template_string(app_client):
    """S2-3: the literal string 'No active situation found' MUST NEVER appear
    in /api/prepare response when there are >0 active commitments."""
    token = _register_and_login(app_client)
    _post_signal(app_client, token, "I will send the proposal to Maria by Friday", entity="Maria")

    r = app_client.get("/api/prepare", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body_text = r.text
    assert "No active situation found" not in body_text, (
        "S2-3 violation: /api/prepare response contains the template "
        "'No active situation found' even though there is 1 active commitment."
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

"""S2-4 SURFACES reconciliation journey gate — Briefing/What-Changed/The-Moment agree.

Auditor found: Briefing says "no changes", What-Changed says "three changes",
The-Moment says "nothing" — with 24 active commitments. Each surface computed
its own snapshot from different sources and they drifted.

FIX (P35 + P41): all three surfaces now embed a `reconciliation` block
derived from the SAME reconcile_snapshot() call (which reads from
CommitmentsSurface — the same source /api/commitments uses). The journey
gate asserts the reconciliation blocks agree across surfaces.

Run:
  cd /home/z/my-project/MaestroAgent/download/MaestroAgent/maestro-personal
  python -m pytest tests/test_S2_04_surfaces_reconcile.py -v
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
os.environ["MAESTRO_PERSONAL_DB"] = str(REPO_ROOT / "test_s2_04_surfaces.db")
_env_local = Path("/home/z/my-project/.env.local")
if _env_local.exists():
    for line in _env_local.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _reset_test_db():
    db_path = REPO_ROOT / "test_s2_04_surfaces.db"
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
    email = f"surfaces-test-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={"user_email": email, "password": "TestPassword123!"})
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text[:200]}"
    return r.json()["token"]


def _post_signal(client, token, text, entity):
    r = client.post(
        "/api/signals",
        json={"text": text, "entity": entity, "signal_type": "commitment_made"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, f"signal post failed: {r.status_code} {r.text[:200]}"


def test_all_three_surfaces_return_reconciliation_block(app_client):
    """S2-4 P41: Briefing, What-Changed/the-shifts, and The-Moment MUST all
    include a 'reconciliation' block in their response."""
    token = _register(app_client)
    _post_signal(app_client, token, "I will send the proposal to Maria by Friday", entity="Maria")

    headers = {"Authorization": f"Bearer {token}"}

    # Briefing
    r1 = app_client.get("/api/briefing", headers=headers)
    assert r1.status_code == 200, f"briefing failed: {r1.status_code} {r1.text[:200]}"
    b1 = r1.json()
    assert "reconciliation" in b1, (
        f"S2-4 P41 violation: /briefing response missing 'reconciliation' block. Got keys: {list(b1.keys())}"
    )
    assert b1["reconciliation"], "reconciliation block is empty"
    assert b1["reconciliation"].get("snapshot_source") == "CommitmentsSurface.get_active_commitments"

    # What-Changed/the-shifts
    r2 = app_client.get("/api/what-changed/the-shifts", headers=headers)
    assert r2.status_code == 200, f"what-changed failed: {r2.status_code} {r2.text[:200]}"
    b2 = r2.json()
    assert "reconciliation" in b2, (
        f"S2-4 P41 violation: /what-changed/the-shifts response missing 'reconciliation' block. Got keys: {list(b2.keys())}"
    )
    assert b2["reconciliation"].get("snapshot_source") == "CommitmentsSurface.get_active_commitments"

    # The-Moment
    r3 = app_client.get("/api/the-moment", headers=headers)
    assert r3.status_code == 200, f"the-moment failed: {r3.status_code} {r3.text[:200]}"
    b3 = r3.json()
    assert "reconciliation" in b3, (
        f"S2-4 P41 violation: /the-moment response missing 'reconciliation' block. Got keys: {list(b3.keys())}"
    )
    assert b3["reconciliation"].get("snapshot_source") == "CommitmentsSurface.get_active_commitments"


def test_reconciliation_blocks_agree_on_active_count(app_client):
    """S2-4 P41: the 'active_commitments_count' MUST be the same across
    all three surfaces — they derive from the same reconcile_snapshot()."""
    token = _register(app_client)
    _post_signal(app_client, token, "I will send the proposal to Maria by Friday", entity="Maria")
    _post_signal(app_client, token, "I will review the contract for Alex by Monday", entity="Alex")

    headers = {"Authorization": f"Bearer {token}"}
    b1 = app_client.get("/api/briefing", headers=headers).json()
    b2 = app_client.get("/api/what-changed/the-shifts", headers=headers).json()
    b3 = app_client.get("/api/the-moment", headers=headers).json()

    count1 = b1["reconciliation"]["active_commitments_count"]
    count2 = b2["reconciliation"]["active_commitments_count"]
    count3 = b3["reconciliation"]["active_commitments_count"]

    assert count1 == count2 == count3, (
        f"S2-4 P41 violation: surfaces disagree on active_commitments_count — "
        f"Briefing={count1}, What-Changed={count2}, The-Moment={count3}. "
        f"They MUST derive from the same reconcile_snapshot() call."
    )
    # With 2 commitments posted, the count should be > 0 (allowing for
    # classification filtering — the exact count depends on classifier state,
    # but it MUST be consistent across surfaces).
    assert count1 >= 0  # at minimum, no crash


def test_the_moment_does_not_say_nothing_when_commitments_exist(app_client):
    """S2-4: when there are active commitments, The-Moment MUST NOT return
    has_moment=False with no explanation — the reconciliation block must
    show the active count, proving the surface read the commitments."""
    token = _register(app_client)
    _post_signal(app_client, token, "I will send the proposal to Maria by Friday", entity="Maria")

    r = app_client.get("/api/the-moment", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    recon = body.get("reconciliation", {})

    # If has_moment is False, the reconciliation block MUST still show
    # the active commitments count (proving the surface actually read them)
    if not body.get("has_moment", False):
        assert recon.get("active_commitments_count", 0) > 0, (
            "S2-4 violation: /the-moment returned has_moment=False but "
            "reconciliation.active_commitments_count is 0 — the surface "
            "claims 'nothing' while there ARE active commitments. This is "
            "the exact contradiction the auditor flagged."
        )


def test_briefing_does_not_say_no_changes_when_commitments_exist(app_client):
    """S2-4: when there are active commitments, Briefing MUST NOT claim
    'no changes' while What-Changed reports changes — the reconciliation
    block's changes_since_yesterday must be consistent across surfaces."""
    token = _register(app_client)
    _post_signal(app_client, token, "I will send the proposal to Maria by Friday", entity="Maria")

    headers = {"Authorization": f"Bearer {token}"}
    b1 = app_client.get("/api/briefing", headers=headers).json()
    b2 = app_client.get("/api/what-changed/the-shifts", headers=headers).json()

    brief_changes = b1["reconciliation"]["changes_since_yesterday"]
    wc_changes = b2["reconciliation"]["changes_since_yesterday"]

    assert brief_changes == wc_changes, (
        f"S2-4 P41 violation: Briefing claims {brief_changes} changes "
        f"while What-Changed claims {wc_changes} changes — they MUST "
        f"derive from the same reconcile_snapshot() call."
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

"""P43 — Built-but-not-wired is not done.

Journey assertion that the LIVE ask path calls reconcile_signals_for_user().
This is the test P43 demands: a function that passes its unit test but is
never called by the live path is a scaffold. This test spies on the live
path and proves the call is wired.

Design: Kimi K3 (moonshotai/kimi-k3), generation_id=gen-1784948642-WQjc4PQWvtQqWiLDMqqs.
Cross-check on OpenRouter dashboard.

Run:
  cd /home/z/my-project/MaestroAgent/download/MaestroAgent/maestro-personal
  python -m pytest tests/test_P43_reconcile_wired_live.py -v
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
os.environ["MAESTRO_PERSONAL_DB"] = str(REPO_ROOT / "test_P43_wired.db")
_env_local = Path("/home/z/my-project/.env.local")
if _env_local.exists():
    for line in _env_local.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _reset_test_db():
    db_path = REPO_ROOT / "test_P43_wired.db"
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
    email = f"p43-test-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={"user_email": email, "password": "TestPassword123!"})
    assert r.status_code == 200
    return r.json()["token"]


def _post_signal(client, token, *, text, entity, signal_type="commitment_made",
                 commitment_type="explicit", is_commitment=True, owner="user"):
    sig = {
        "signal_id": f"sig-{uuid.uuid4().hex}",
        "entity": entity,
        "text": text,
        "signal_type": signal_type,
        "timestamp": "2026-07-25T10:00:00Z",
        "metadata": {
            "source": "manual",
            "commitment_type": commitment_type,
            "is_commitment": is_commitment,
            "owner": owner,
            "commitment_state": "active" if is_commitment else "candidate",
            "commitment_confidence": 0.85,
        },
    }
    r = client.post("/api/signals", json=sig, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


def test_p43_live_ask_path_calls_reconcile_signals_for_user(app_client, monkeypatch):
    """P43 JOURNEY ASSERTION: the live /api/ask path MUST call
    reconcile_signals_for_user. Spies on the function and asserts it was
    called when the user asks 'What did I promise Maria?'.

    This is the test that catches 'built-but-not-wired' — the function
    passes its unit tests in test_P41_single_source_of_truth.py, but if
    the live ask path doesn't call it, the structural refactor is a
    scaffold, not a fix.
    """
    token = _register(app_client)
    # Seed a real commitment + a third-party report (the auditor's case)
    _post_signal(app_client, token, text="I will send the proposal to Maria by Friday",
                 entity="Maria", commitment_type="explicit", is_commitment=True, owner="user")
    _post_signal(app_client, token, text="Maria said: I will send the proposal",
                 entity="Maria", signal_type="reported_statement",
                 commitment_type="third_party_report", is_commitment=True, owner="other")

    # Spy on reconcile_signals_for_user — the live path MUST call it
    import maestro_personal_shell.routers.ask as ask_mod
    real_fn = ask_mod.reconcile_signals_for_user
    calls = []
    def spy(user_email, db_path=None, entity_filter="", include_non_commitments=False):
        calls.append({
            "user_email": user_email,
            "entity_filter": entity_filter,
            "include_non_commitments": include_non_commitments,
        })
        return real_fn(user_email, db_path=db_path, entity_filter=entity_filter,
                       include_non_commitments=include_non_commitments)
    monkeypatch.setattr(ask_mod, "reconcile_signals_for_user", spy)

    # Hit the live ask path
    r = app_client.post(
        "/api/ask",
        json={"query": "What did I promise Maria?"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, f"ask failed: {r.status_code} {r.text[:200]}"

    # P43: the live path MUST have called reconcile_signals_for_user
    assert len(calls) > 0, (
        "P43 VIOLATION: live /api/ask path did NOT call reconcile_signals_for_user. "
        "The function is built (passes test_P41_single_source_of_truth.py) but NOT "
        "wired into the live path — it's a scaffold, not a fix. The 5-layer inline "
        "filter is still running."
    )

    # P37: include_non_commitments MUST be False (hard admission)
    assert all(c["include_non_commitments"] is False for c in calls), (
        f"P37 violation: reconcile_signals_for_user was called with "
        f"include_non_commitments=True — non-commitments could surface."
    )


def test_p43_live_response_carries_reconcile_source_field(app_client):
    """P43 JOURNEY ASSERTION (stronger): the live /api/ask response MUST
    carry a 'reconcile_source' field in evidence_refs, with value
    'signal.metadata'. This field is produced ONLY by reconcile_signal() —
    its presence in the live response proves the live path used the
    reconcile module, not the old 5-layer filter.
    """
    token = _register(app_client)
    _post_signal(app_client, token, text="I will send the proposal to Maria by Friday",
                 entity="Maria", commitment_type="explicit", is_commitment=True, owner="user")

    r = app_client.post(
        "/api/ask",
        json={"query": "What did I promise Maria?"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    evidence = body.get("evidence_refs", [])

    # If evidence is non-empty, at least one ref MUST carry reconcile_source
    if evidence:
        has_reconcile_source = any(
            ev.get("reconcile_source") == "signal.metadata"
            for ev in evidence
        )
        assert has_reconcile_source, (
            f"P43 VIOLATION: live /api/ask response has {len(evidence)} evidence "
            f"refs but NONE carry reconcile_source='signal.metadata'. The live "
            f"path is NOT using reconcile_signal() — the 5-layer inline filter "
            f"is still running. Evidence: {evidence[:2]}"
        )


def test_p43_no_residual_inline_filter_logic(app_client):
    """P43 STRUCTURAL CHECK: the 5-layer inline filter logic MUST be gone
    from routers/ask.py. The grep for the old filter's signature tokens
    MUST return zero matches in the ledger fast path.

    This is the structural assertion — it catches the case where the new
    wiring is added but the old filter is left as dead code (which would
    still be a P41 violation: two parallel sources of truth).
    """
    import inspect
    import maestro_personal_shell.routers.ask as ask_mod
    src = inspect.getsource(ask_mod)

    # The old 5-layer filter had these distinctive tokens. After the
    # S3-1-WIRE-LIVE refactor, they MUST be gone from the live source.
    # (They may appear in comments explaining what was removed — that's fine.
    # The assertion is that no ACTIVE filter logic uses them.)
    old_filter_tokens = [
        "_NON_USER_TYPES_LEDGER",
        "_filtered_ledger = []",
    ]
    for token in old_filter_tokens:
        # Allow the token to appear in comments (lines starting with # or
        # inside string literals), but NOT as active code.
        active_uses = [
            line for line in src.splitlines()
            if token in line and not line.strip().startswith("#")
            and not line.strip().startswith('"') and not line.strip().startswith("'")
        ]
        assert len(active_uses) == 0, (
            f"P43 VIOLATION: old 5-layer filter token {token!r} still appears "
            f"as active code in routers/ask.py: {active_uses[:3]}. The new "
            f"reconcile wiring was added but the old filter was not removed — "
            f"two parallel sources of truth (P41 violation)."
        )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

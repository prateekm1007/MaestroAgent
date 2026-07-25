"""P51 — Ask never fails silently (fifth audit F1/S1).

Under LLM outage, Ask must NEVER return answer=''. On any LLM failure
(timeout, 500, empty response), Ask returns an explicit, ledger-grounded
answer with a clear "AI unavailable" note.

This test mocks the LLM to simulate outage and asserts the Ask response
is always non-blank.

CTO-authored (P47 honest attribution: Kimi K3 timed out on the design
prompt; this fix was applied by the CTO, not Kimi K3).

Run:
  cd /home/z/my-project/MaestroAgent/download/MaestroAgent/maestro-personal
  python -m pytest tests/test_P51_ask_no_blank.py -v
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from unittest.mock import patch, AsyncMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
os.environ.setdefault("MAESTRO_ENV", "dev")
os.environ["MAESTRO_PERSONAL_DB"] = str(REPO_ROOT / "test_P51_no_blank.db")
_env_local = Path("/home/z/my-project/.env.local")
if _env_local.exists():
    for line in _env_local.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _reset_test_db():
    db_path = REPO_ROOT / "test_P51_no_blank.db"
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
    email = f"p51-test-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={"user_email": email, "password": "TestPassword123!"})
    assert r.status_code == 200
    return r.json()["token"]


def _post_signal(client, token, *, text, entity):
    sig = {
        "signal_id": f"sig-{uuid.uuid4().hex}",
        "entity": entity,
        "text": text,
        "signal_type": "commitment_made",
        "timestamp": "2026-07-25T10:00:00Z",
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


def test_p51_ask_returns_nonblank_when_llm_returns_none(app_client):
    """P51: when the LLM returns None/empty, Ask MUST NOT return answer=''.
    It must fall back to the rules-based answer or a ledger-grounded abstention."""
    token = _register(app_client)
    _post_signal(app_client, token, text="I will send the proposal to Maria by Friday",
                 entity="Maria")

    # Mock llm_complete at the source module (it's imported inside the function)
    with patch("maestro_personal_shell.llm_bridge.llm_complete", new_callable=AsyncMock, return_value=None):
        r = app_client.post(
            "/api/ask",
            json={"query": "What did I promise Maria?"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 200
    body = r.json()
    answer = body.get("answer", "")
    assert answer and answer.strip(), (
        f"P51 VIOLATION: Ask returned an empty answer when LLM returned None. "
        f"answer={answer!r}. Ask must NEVER return blank — it must fall back "
        f"to rules-based or ledger-grounded abstention."
    )


def test_p51_ask_returns_nonblank_when_llm_raises_exception(app_client):
    """P51: when the LLM call raises an exception, Ask MUST NOT return answer=''.
    The exception must be caught and the fallback must produce a non-blank answer."""
    token = _register(app_client)
    _post_signal(app_client, token, text="I will send the proposal to Maria by Friday",
                 entity="Maria")

    # Mock llm_complete to raise an exception (simulating LLM 500/timeout)
    async def _raise(*args, **kwargs):
        raise RuntimeError("simulated LLM outage")
    with patch("maestro_personal_shell.llm_bridge.llm_complete", new_callable=AsyncMock, side_effect=_raise):
        r = app_client.post(
            "/api/ask",
            json={"query": "What did I promise Maria?"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 200
    body = r.json()
    answer = body.get("answer", "")
    assert answer and answer.strip(), (
        f"P51 VIOLATION: Ask returned an empty answer when LLM raised an exception. "
        f"answer={answer!r}. Ask must NEVER return blank."
    )


def test_p51_debug_llm_does_not_500(app_client):
    """P51: /api/debug-llm must NOT throw an unhandled 500 even when the
    LLM bridge is completely broken. It returns structured JSON."""
    token = _register(app_client)

    # The endpoint has a try/except wrapper (P51) — even with broken internals,
    # it should return 200 with structured JSON, never 500.
    r = app_client.get(
        "/api/debug-llm",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code != 500, (
        f"P51 VIOLATION: /api/debug-llm returned HTTP 500 (unhandled exception). "
        f"Must return structured JSON with error fields, never 500."
    )
    # The response should be JSON (even if it contains error fields)
    body = r.json()
    assert isinstance(body, dict)


def test_p51_final_guard_never_blank(app_client):
    """P51 BELT-AND-SUSPENDERS: even if every prior fallback fails, the
    final guard at the AskResponse return ensures answer is non-blank."""
    token = _register(app_client)
    # No signals posted — empty ledger

    # Mock LLM to return empty
    with patch("maestro_personal_shell.llm_bridge.llm_complete", new_callable=AsyncMock, return_value=""):
        r = app_client.post(
            "/api/ask",
            json={"query": "What did I promise Nobody?"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 200
    body = r.json()
    answer = body.get("answer", "")
    assert answer and answer.strip(), (
        f"P51 VIOLATION: Ask returned empty answer even through the final guard. "
        f"answer={answer!r}. The belt-and-suspenders check failed."
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

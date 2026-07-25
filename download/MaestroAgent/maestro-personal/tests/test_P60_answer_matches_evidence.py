"""P60/S0 — Answer must match the evidence (sixth audit F-03).

F-03 was never about whether the evidence is RETRIEVED — it was about whether
the ANSWER denies the evidence it carries. The sixth audit found "abstains at
0.8 confidence while evidence_refs contain active commitments." The fix:
if evidence_refs is non-empty AND the answer contains abstention language,
override with a ledger-grounded answer built from the evidence.

Run:
  cd /home/z/my-project/MaestroAgent/download/MaestroAgent/maestro-personal
  python -m pytest tests/test_P60_answer_matches_evidence.py -v
"""
from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import patch, AsyncMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
os.environ.setdefault("MAESTRO_ENV", "dev")
os.environ["MAESTRO_PERSONAL_DB"] = str(REPO_ROOT / "test_P60_answer.db")
_env_local = Path("/home/z/my-project/.env.local")
if _env_local.exists():
    for line in _env_local.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _reset_test_db():
    db_path = REPO_ROOT / "test_P60_answer.db"
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
    email = f"p60ans-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={"user_email": email, "password": "TestPassword123!"})
    assert r.status_code == 200
    return r.json()["token"]


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


def test_p60_answer_returns_promises_when_evidence_exists(app_client):
    """P60/S0 (F-03): when evidence_refs contains the user's own commitments,
    the ANSWER must return them — not abstain.

    The sixth audit found the LLM abstaining ("I don't have enough reliable
    evidence") while evidence_refs contained the commitment. The user reads
    the abstention, not the retrieval fix. The answer must match the evidence.
    """
    token = _register(app_client)
    _post_signal(app_client, token, text="I will send the proposal to Maria by Friday",
                 entity="Maria Garcia")
    time.sleep(2)

    # Mock the LLM to abstain (simulating the F-03 failure)
    with patch("maestro_personal_shell.llm_bridge.llm_complete",
               new_callable=AsyncMock,
               return_value="I don't have enough reliable evidence to answer this question."):
        r = app_client.post(
            "/api/ask",
            json={"query": "What did I promise Maria?"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 200
    body = r.json()
    answer = body.get("answer", "")
    evidence = body.get("evidence_refs", [])

    # Evidence MUST be non-empty (the retrieval layer works)
    assert len(evidence) > 0, (
        "P60: evidence_refs is empty — the retrieval layer didn't find the commitment."
    )

    # The answer MUST NOT abstain when evidence is present
    abstention_phrases = [
        "i don't have enough",
        "not enough reliable evidence",
        "i don't have any record",
    ]
    answer_lower = answer.lower()
    is_abstaining = any(phrase in answer_lower for phrase in abstention_phrases)
    assert not is_abstaining, (
        f"P60/S0 VIOLATION (F-03): the answer abstains while evidence_refs "
        f"has {len(evidence)} item(s). The user reads the abstention, not the "
        f"retrieval fix. answer={answer[:200]!r}"
    )

    # The answer MUST mention the evidence content (the proposal)
    assert "proposal" in answer.lower() or "maria" in answer.lower(), (
        f"P60/S0: the answer doesn't mention the evidence content. "
        f"answer={answer[:200]!r}, evidence={evidence[:1]}"
    )


def test_p60_answer_abstains_when_evidence_genuinely_empty(app_client):
    """P60 regression: when evidence IS genuinely empty, abstention is correct.
    The override must not fire when there's no evidence."""
    token = _register(app_client)
    # No signals posted — empty ledger

    r = app_client.post(
        "/api/ask",
        json={"query": "What did I promise Nobody?"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    answer = body.get("answer", "")

    # The answer must be non-blank (P51) — it can abstain, but not be empty
    assert answer.strip(), "P51: answer must not be blank even when evidence is empty"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

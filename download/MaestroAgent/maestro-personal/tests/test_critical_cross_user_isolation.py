"""
CRITICAL verification: cross-user data isolation on main.

The 4th external auditor (at 3dfe17a on main) found that verify_token
returns the same user_email for different logins, causing total cross-user
data leakage. This test verifies the fix at current HEAD.

This is the hard-cap trigger — if this fails, the score is capped at 4.0.
"""

import sys
import os
import tempfile
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


@pytest.fixture
def isolated_api():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-critical-iso"
    os.environ.pop("MAESTRO_PERSONAL_ENV", None)

    import importlib
    import maestro_personal_shell.api as api_module
    importlib.reload(api_module)
    api_module.init_db(db_path)

    try:
        from maestro_personal_shell.semantic_retrieval import init_fts_index, rebuild_fts_index
        init_fts_index(db_path)
        rebuild_fts_index(db_path)
    except Exception:
        pass

    yield api_module
    os.unlink(db_path)
    os.environ.pop("MAESTRO_PERSONAL_DB", None)
    os.environ.pop("MAESTRO_PERSONAL_TOKEN", None)


@pytest.fixture
def client(isolated_api):
    return TestClient(isolated_api.app)


class TestCrossUserIsolationCritical:
    """The CRITICAL finding: verify_token must return DIFFERENT user_emails
    for different logins, and users must NOT see each other's signals."""

    def test_different_logins_get_different_user_emails(self, client):
        """Two distinct logins must resolve to two distinct user_emails
        inside verify_token. The auditor found they were the same."""
        # Login as alpha
        resp_a = client.post("/api/auth/login", json={
            "user_email": "alpha-user-001",
            "password": os.environ["MAESTRO_PERSONAL_TOKEN"],
        })
        assert resp_a.status_code == 200
        token_a = resp_a.json()["token"]
        user_email_a = resp_a.json()["user_email"]

        # Login as bravo
        resp_b = client.post("/api/auth/login", json={
            "user_email": "bravo-user-002",
            "password": os.environ["MAESTRO_PERSONAL_TOKEN"],
        })
        assert resp_b.status_code == 200
        token_b = resp_b.json()["token"]
        user_email_b = resp_b.json()["user_email"]

        # The user_emails MUST be different
        assert user_email_a != user_email_b, (
            f"CRITICAL: Two different logins resolved to the same user_email! "
            f"alpha={user_email_a}, bravo={user_email_b}"
        )
        assert token_a != token_b, "Tokens must be unique"

    def test_alpha_cannot_see_bravo_signals(self, client):
        """Alpha creates a signal, Bravo creates a signal. Alpha's GET
        /api/signals must NOT include Bravo's signal, and vice versa."""
        # Login as two users
        resp_a = client.post("/api/auth/login", json={
            "user_email": "alpha-iso@test.com",
            "password": os.environ["MAESTRO_PERSONAL_TOKEN"],
        })
        token_a = resp_a.json()["token"]
        headers_a = {"Authorization": f"Bearer {token_a}"}

        resp_b = client.post("/api/auth/login", json={
            "user_email": "bravo-iso@test.com",
            "password": os.environ["MAESTRO_PERSONAL_TOKEN"],
        })
        token_b = resp_b.json()["token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        with patch("maestro_personal_shell.commitment_classifier.classify_commitment",
                   new_callable=AsyncMock,
                   return_value={"commitment_type": "explicit", "is_commitment": True,
                                 "confidence": 0.85, "state": "active", "owner": "user",
                                 "reasoning": "test", "llm_powered": False}), \
             patch("maestro_personal_shell.llm_bridge.llm_complete",
                   new_callable=AsyncMock, return_value=None), \
             patch("maestro_personal_shell.llm_bridge.is_llm_available",
                   return_value=False):
            # Alpha creates a private signal
            client.post("/api/signals", json={
                "entity": "AlphaPrivate",
                "text": "Alpha's secret commitment UNIQUE_ALPHA_MARKER",
                "signal_type": "commitment_made",
            }, headers=headers_a)

            # Bravo creates a private signal
            client.post("/api/signals", json={
                "entity": "BravoPrivate",
                "text": "Bravo's secret commitment UNIQUE_BRAVO_MARKER",
                "signal_type": "commitment_made",
            }, headers=headers_b)

            # Alpha lists signals — must NOT see Bravo's
            resp = client.get("/api/signals", headers=headers_a)
            assert resp.status_code == 200
            alpha_signals_text = [s.get("text", "") for s in resp.json()]
            assert any("UNIQUE_ALPHA_MARKER" in t for t in alpha_signals_text), (
                "Alpha should see Alpha's signal"
            )
            assert not any("UNIQUE_BRAVO_MARKER" in t for t in alpha_signals_text), (
                "CRITICAL: Alpha can see Bravo's private signal! Cross-user leak."
            )

            # Bravo lists signals — must NOT see Alpha's
            resp = client.get("/api/signals", headers=headers_b)
            assert resp.status_code == 200
            bravo_signals_text = [s.get("text", "") for s in resp.json()]
            assert any("UNIQUE_BRAVO_MARKER" in t for t in bravo_signals_text), (
                "Bravo should see Bravo's signal"
            )
            assert not any("UNIQUE_ALPHA_MARKER" in t for t in bravo_signals_text), (
                "CRITICAL: Bravo can see Alpha's private signal! Cross-user leak."
            )

    def test_alpha_cannot_see_bravo_commitments(self, client):
        """Cross-user isolation must extend to /api/commitments."""
        resp_a = client.post("/api/auth/login", json={
            "user_email": "alpha-comm@test.com",
            "password": os.environ["MAESTRO_PERSONAL_TOKEN"],
        })
        headers_a = {"Authorization": f"Bearer {resp_a.json()['token']}"}

        resp_b = client.post("/api/auth/login", json={
            "user_email": "bravo-comm@test.com",
            "password": os.environ["MAESTRO_PERSONAL_TOKEN"],
        })
        headers_b = {"Authorization": f"Bearer {resp_b.json()['token']}"}

        with patch("maestro_personal_shell.commitment_classifier.classify_commitment",
                   new_callable=AsyncMock,
                   return_value={"commitment_type": "explicit", "is_commitment": True,
                                 "confidence": 0.85, "state": "active", "owner": "user",
                                 "reasoning": "test", "llm_powered": False}), \
             patch("maestro_personal_shell.llm_bridge.llm_complete",
                   new_callable=AsyncMock, return_value=None), \
             patch("maestro_personal_shell.llm_bridge.is_llm_available",
                   return_value=False):
            client.post("/api/signals", json={
                "entity": "AlphaCommEntity",
                "text": "I will send the ALPHA_COMM_MARKER proposal",
                "signal_type": "commitment_made",
            }, headers=headers_a)

            client.post("/api/signals", json={
                "entity": "BravoCommEntity",
                "text": "I will send the BRAVO_COMM_MARKER proposal",
                "signal_type": "commitment_made",
            }, headers=headers_b)

            # Alpha's commitments must not include Bravo's entity
            resp = client.get("/api/commitments", headers=headers_a)
            alpha_entities = [c.get("entity", "") for c in resp.json()]
            assert "AlphaCommEntity" in alpha_entities
            assert "BravoCommEntity" not in alpha_entities, (
                "CRITICAL: Alpha can see Bravo's commitment!"
            )

            # Bravo's commitments must not include Alpha's entity
            resp = client.get("/api/commitments", headers=headers_b)
            bravo_entities = [c.get("entity", "") for c in resp.json()]
            assert "BravoCommEntity" in bravo_entities
            assert "AlphaCommEntity" not in bravo_entities, (
                "CRITICAL: Bravo can see Alpha's commitment!"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

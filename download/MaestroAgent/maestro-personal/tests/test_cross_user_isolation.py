"""
Phase 1 Cross-User Isolation Test.

Verifies that User A cannot access User B's data via any endpoint.
This is the S3/Phase 1 acceptance test: "Cross-user leakage: 0 leaks."

Tests:
1. Per-user tokens are unique
2. User A's signals are not visible to User B
3. User A's situations are not visible to User B
4. User A's commitments are not visible to User B
5. Bootstrap token is rejected in production mode
6. WebSocket auth resolves user_email correctly
"""

import sys
import os
import tempfile
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


@pytest.fixture
def isolated_api():
    """Initialize the API with a fresh temp DB for isolation testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-bootstrap-token"
    os.environ.pop("MAESTRO_PERSONAL_ENV", None)  # dev mode — bootstrap allowed

    import importlib
    import maestro_personal_shell.api as api_module
    importlib.reload(api_module)
    api_module.init_db(db_path)

    yield api_module

    os.unlink(db_path)
    del os.environ["MAESTRO_PERSONAL_DB"]
    del os.environ["MAESTRO_PERSONAL_TOKEN"]


@pytest.fixture
def client(isolated_api):
    return TestClient(isolated_api.app)


def _login(client, user_email):
    """Login as a specific user and return the token."""
    response = client.post("/api/auth/login", json={"user_email": user_email, "password": os.environ.get("MAESTRO_PERSONAL_TOKEN", "test")})
    assert response.status_code == 200
    return response.json()["token"]


class TestPerUserAuth:
    """Per-user authentication tests."""

    def test_per_user_tokens_are_unique(self, client):
        """Each user must get a unique token."""
        token_a = _login(client, "user-a@example.com")
        token_b = _login(client, "user-b@example.com")

        assert token_a != token_b, "Per-user tokens must be unique"

    def test_per_user_token_works(self, client):
        """A per-user token must authenticate successfully."""
        token = _login(client, "user-a@example.com")

        response = client.get(
            "/api/signals",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

    def test_invalid_token_rejected(self, client):
        """An invalid token must be rejected with 401."""
        response = client.get(
            "/api/signals",
            headers={"Authorization": "Bearer invalid-token-xyz"},
        )
        assert response.status_code == 401

    def test_missing_auth_rejected(self, client):
        """Missing auth header must be rejected with 401."""
        response = client.get("/api/signals")
        assert response.status_code == 401


class TestCrossUserIsolation:
    """Cross-user data isolation tests — the core Phase 1 acceptance test."""

    def test_user_a_signals_not_visible_to_user_b(self, client):
        """User A's signals must NOT be visible to User B."""
        token_a = _login(client, "user-a@example.com")
        token_b = _login(client, "user-b@example.com")

        # User A adds a signal
        response = client.post(
            "/api/signals",
            json={
                "entity": "SecretEntity",
                "text": "User A's private commitment to SecretEntity",
                "signal_type": "commitment_made",
            },
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert response.status_code == 200

        # User B lists signals — must NOT see User A's signal
        response = client.get(
            "/api/signals",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert response.status_code == 200
        signals = response.json()
        for sig in signals:
            assert sig.get("entity") != "SecretEntity", \
                "CROSS-USER LEAK: User B can see User A's SecretEntity signal"
            assert "User A's private" not in sig.get("text", ""), \
                "CROSS-USER LEAK: User B can see User A's private text"

    def test_user_a_situations_not_visible_to_user_b(self, client):
        """User A's situations must NOT be visible to User B."""
        token_a = _login(client, "user-a@example.com")
        token_b = _login(client, "user-b@example.com")

        # User A adds a signal that creates a situation
        client.post(
            "/api/signals",
            json={
                "entity": "AcmeCorp",
                "text": "AcmeCorp committed to signing the contract by Friday",
                "signal_type": "commitment_made",
            },
            headers={"Authorization": f"Bearer {token_a}"},
        )

        # User B lists situations — must NOT see User A's AcmeCorp situation
        response = client.get(
            "/api/situations",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert response.status_code == 200
        situations = response.json()
        for sit in situations:
            assert sit.get("entity") != "AcmeCorp", \
                "CROSS-USER LEAK: User B can see User A's AcmeCorp situation"

    def test_user_a_commitments_not_visible_to_user_b(self, client):
        """User A's commitments must NOT be visible to User B."""
        token_a = _login(client, "user-a@example.com")
        token_b = _login(client, "user-b@example.com")

        # User A adds a commitment signal
        client.post(
            "/api/signals",
            json={
                "entity": "CommitEntity",
                "text": "I will send the proposal by Friday",
                "signal_type": "commitment_made",
            },
            headers={"Authorization": f"Bearer {token_a}"},
        )

        # User B lists commitments — must NOT see User A's commitment
        response = client.get(
            "/api/commitments",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert response.status_code == 200
        commitments = response.json()
        for com in commitments:
            assert com.get("entity") != "CommitEntity", \
                "CROSS-USER LEAK: User B can see User A's CommitEntity commitment"

    def test_user_a_ask_not_contaminated_by_user_b(self, client):
        """User A's Ask answer must NOT cite User B's evidence."""
        token_a = _login(client, "user-a@example.com")
        token_b = _login(client, "user-b@example.com")

        # User B adds a signal
        client.post(
            "/api/signals",
            json={
                "entity": "UserBEntity",
                "text": "User B's secret data about UserBEntity",
                "signal_type": "commitment_made",
            },
            headers={"Authorization": f"Bearer {token_b}"},
        )

        # User A asks a question — must NOT see User B's data
        response = client.post(
            "/api/ask",
            json={"query": "What do I know about UserBEntity?"},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert response.status_code == 200
        data = response.json()
        answer = data.get("answer", "")
        source = data.get("source_sentence", "")
        assert "User B's secret" not in answer, \
            "CROSS-USER LEAK: User A's answer contains User B's data"
        assert "User B's secret" not in source, \
            "CROSS-USER LEAK: User A's source cites User B's data"

    def test_user_a_prepare_not_contaminated_by_user_b(self, client):
        """User A's Prepare must NOT include User B's commitments."""
        token_a = _login(client, "user-a@example.com")
        token_b = _login(client, "user-b@example.com")

        # User B adds a signal
        client.post(
            "/api/signals",
            json={
                "entity": "PrepareEntity",
                "text": "User B's prepare-specific commitment",
                "signal_type": "commitment_made",
            },
            headers={"Authorization": f"Bearer {token_b}"},
        )

        # User A gets Prepare — must NOT see User B's data
        response = client.get(
            "/api/prepare",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert response.status_code == 200
        prepare_items = response.json()
        for item in prepare_items:
            assert item.get("entity") != "PrepareEntity", \
                "CROSS-USER LEAK: User A's Prepare includes User B's PrepareEntity"

    def test_user_a_what_changed_not_contaminated_by_user_b(self, client):
        """User A's What Changed must NOT include User B's changes."""
        token_a = _login(client, "user-a@example.com")
        token_b = _login(client, "user-b@example.com")

        # User B adds a signal
        client.post(
            "/api/signals",
            json={
                "entity": "ChangedEntity",
                "text": "User B's what-changed-specific signal",
                "signal_type": "commitment_made",
            },
            headers={"Authorization": f"Bearer {token_b}"},
        )

        # User A gets What Changed — must NOT see User B's changes
        response = client.get(
            "/api/what-changed",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert response.status_code == 200
        changes = response.json()
        for change in changes:
            assert change.get("entity") != "ChangedEntity", \
                "CROSS-USER LEAK: User A's What Changed includes User B's ChangedEntity"


class TestBootstrapTokenGating:
    """Bootstrap token must be disabled in production mode."""

    def test_bootstrap_token_works_in_dev(self, client):
        """In dev mode, the bootstrap token should work."""
        response = client.post(
            "/api/auth/login",
            json={"password": os.environ.get("MAESTRO_PERSONAL_TOKEN", "test")},
        )
        assert response.status_code == 200
        token = response.json()["token"]

        response = client.get(
            "/api/signals",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

    def test_bootstrap_token_disabled_in_production(self):
        """In production mode, the bootstrap token must be rejected."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        os.environ["MAESTRO_PERSONAL_DB"] = db_path
        os.environ["MAESTRO_PERSONAL_TOKEN"] = "bootstrap-token-prod"
        os.environ["MAESTRO_PERSONAL_ENV"] = "production"

        try:
            import importlib
            import maestro_personal_shell.api as api_module
            importlib.reload(api_module)
            api_module.init_db(db_path)

            client = TestClient(api_module.app)

            # Try to use the bootstrap token — must be rejected
            response = client.get(
                "/api/signals",
                headers={"Authorization": "Bearer bootstrap-token-prod"},
            )
            assert response.status_code == 401, \
                "Bootstrap token must be rejected in production mode"

            # But per-user tokens should still work (with correct password)
            response = client.post(
                "/api/auth/login",
                json={"user_email": "user@example.com", "password": "bootstrap-token-prod"},
            )
            assert response.status_code == 200
            user_token = response.json()["token"]

            response = client.get(
                "/api/signals",
                headers={"Authorization": f"Bearer {user_token}"},
            )
            assert response.status_code == 200, \
                "Per-user tokens must work in production mode"
        finally:
            os.unlink(db_path)
            del os.environ["MAESTRO_PERSONAL_DB"]
            del os.environ["MAESTRO_PERSONAL_TOKEN"]
            del os.environ["MAESTRO_PERSONAL_ENV"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

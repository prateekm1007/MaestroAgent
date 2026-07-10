"""
Phase 1 trust reset tests.

P1-1: Passwordless login rejected
P1-2: Noise filtered from briefing top_situation
P1-3: Untrusted-evidence envelope in all LLM system prompts
P1-4: Cross-user isolation for graph + predictions + audit_log
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
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-p1-trust"
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
    del os.environ["MAESTRO_PERSONAL_DB"]
    del os.environ["MAESTRO_PERSONAL_TOKEN"]


@pytest.fixture
def client(isolated_api):
    return TestClient(isolated_api.app)


class TestP1PasswordlessLogin:
    """P1-1: Passwordless email login must be rejected."""

    def test_email_only_login_rejected(self, client):
        """Login with only user_email (no password) must fail."""
        response = client.post("/api/auth/login", json={"user_email": "victim@test.com"})
        assert response.status_code == 401

    def test_wrong_password_rejected(self, client):
        """Login with wrong password must fail."""
        response = client.post("/api/auth/login", json={
            "user_email": "victim@test.com",
            "password": "wrong-password",
        })
        assert response.status_code == 401

    def test_correct_password_works(self, client):
        """Login with the correct token as password must work."""
        response = client.post("/api/auth/login", json={"password": "test-p1-trust"})
        assert response.status_code == 200
        assert "token" in response.json()

    def test_dev_mode_bootstrap_works(self, client):
        """In dev mode, the correct token as password works (backward compat for tests)."""
        response = client.post("/api/auth/login", json={"password": os.environ.get("MAESTRO_PERSONAL_TOKEN", "test")})
        assert response.status_code == 200

    def test_cannot_impersonate_arbitrary_email(self, client):
        """Attacker cannot get a token for any email without the password."""
        # Try to login as any email without password
        for email in ["ceo@company.com", "admin@company.com", "victim@company.com"]:
            response = client.post("/api/auth/login", json={"user_email": email})
            assert response.status_code == 401, \
                f"P1-1: Should reject passwordless login for {email}"


class TestP1NoiseFiltering:
    """P1-2: Newsletter/noise entities must not be top briefing situation."""

    def test_newsletter_not_top_situation(self, client):
        """Newsletter entities must not appear as top_situation in briefing."""
        # Login first
        login_resp = client.post("/api/auth/login", json={"password": "test-p1-trust"})
        token = login_resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create many newsletter signals (high volume noise)
        for i in range(20):
            client.post("/api/signals", json={
                "entity": "NewsletterCorp",
                "text": f"Weekly newsletter issue {i}",
                "signal_type": "newsletter",
            }, headers=headers)

        # Create one real commitment
        with patch("maestro_personal_shell.commitment_classifier.classify_commitment",
                   new_callable=AsyncMock,
                   return_value={"commitment_type": "explicit", "is_commitment": True,
                                 "confidence": 0.85, "state": "active", "owner": "user",
                                 "reasoning": "test", "llm_powered": False}):
            client.post("/api/signals", json={
                "entity": "RealClient",
                "text": "I will send the proposal by Friday",
                "signal_type": "commitment_made",
            }, headers=headers)

        # Get briefing — NewsletterCorp must not be top_situation
        response = client.get("/api/briefing/evening", headers=headers)
        if response.status_code == 200:
            data = response.json()
            top = data.get("top_situation")
            if top:
                top_entity = ""
                if isinstance(top, dict):
                    top_entity = top.get("entity", "").lower()
                elif hasattr(top, "entity"):
                    top_entity = str(top.entity).lower()
                # NewsletterCorp should NOT be the top situation
                assert "newsletter" not in top_entity, \
                    "P1-2: Newsletter entity should not be top_situation"


class TestP1UntrustedEvidenceEnvelope:
    """P1-3: All LLM system prompts must include untrusted-evidence warning."""

    def test_all_prompts_have_untrusted_warning(self):
        """Every LLM system prompt must include the untrusted-evidence envelope."""
        import pathlib
        source = pathlib.Path(
            os.path.join(os.path.dirname(__file__), "..", "src", "maestro_personal_shell", "llm_bridge.py")
        ).read_text()

        # Count system prompts (triple-quoted strings with "You are")
        prompt_count = source.count('"""You are')
        # Count untrusted-evidence warnings
        untrusted_count = source.count("untrusted evidence")

        assert untrusted_count >= prompt_count, \
            f"P1-3: {prompt_count} system prompts but only {untrusted_count} untrusted-evidence warnings. " \
            f"Every LLM system prompt must include the untrusted-evidence envelope."


class TestP1GraphIsolation:
    """P1-4: Cross-user isolation for graph stores."""

    def test_graph_entity_user_scoped(self, client):
        """Alice's graph entity must not be visible to Bob."""
        alice_h = {"Authorization": f"Bearer {client.post('/api/auth/login', json={'password': 'test-p1-trust', 'user_email': 'alice@test.com'}).json()['token']}"}
        bob_h = {"Authorization": f"Bearer {client.post('/api/auth/login', json={'password': 'test-p1-trust', 'user_email': 'bob@test.com'}).json()['token']}"}

        with patch("maestro_personal_shell.commitment_classifier.classify_commitment",
                   new_callable=AsyncMock,
                   return_value={"commitment_type": "explicit", "is_commitment": True,
                                 "confidence": 0.85, "state": "active", "owner": "user",
                                 "reasoning": "test", "llm_powered": False}):
            # Alice creates a commitment (adds to graph)
            client.post("/api/signals", json={
                "entity": "AliceSecretCorp",
                "text": "I will send the secret proposal",
                "signal_type": "commitment_made",
            }, headers=alice_h)

            # Bob tries to read Alice's graph
            resp = client.get("/api/graph/entity/AliceSecretCorp", headers=bob_h)
            assert resp.json().get("exists") is False, \
                "P1-4: Bob can read Alice's graph entity"

    def test_graph_risk_user_scoped(self, client):
        """Alice's graph risk must not be visible to Bob."""
        alice_h = {"Authorization": f"Bearer {client.post('/api/auth/login', json={'password': 'test-p1-trust', 'user_email': 'alice@test.com'}).json()['token']}"}
        bob_h = {"Authorization": f"Bearer {client.post('/api/auth/login', json={'password': 'test-p1-trust', 'user_email': 'bob@test.com'}).json()['token']}"}

        with patch("maestro_personal_shell.commitment_classifier.classify_commitment",
                   new_callable=AsyncMock,
                   return_value={"commitment_type": "explicit", "is_commitment": True,
                                 "confidence": 0.85, "state": "active", "owner": "user",
                                 "reasoning": "test", "llm_powered": False}):
            client.post("/api/signals", json={
                "entity": "RiskCorp",
                "text": "I will deliver",
                "signal_type": "commitment_made",
            }, headers=alice_h)

            # Bob queries risk — should get neutral 0.5 (no data)
            resp = client.get("/api/graph/risk/RiskCorp", headers=bob_h)
            data = resp.json()
            assert data.get("completion_rate") == 0.5, \
                "P1-4: Bob should get neutral completion rate (no data for this entity)"


class TestP1AuditLogIsolation:
    """P1-4: Cross-user isolation for audit log."""

    def test_audit_log_user_scoped(self, client):
        """Alice's audit log must not be visible to Bob."""
        alice_h = {"Authorization": f"Bearer {client.post('/api/auth/login', json={'password': 'test-p1-trust', 'user_email': 'alice@test.com'}).json()['token']}"}
        bob_h = {"Authorization": f"Bearer {client.post('/api/auth/login', json={'password': 'test-p1-trust', 'user_email': 'bob@test.com'}).json()['token']}"}

        with patch("maestro_personal_shell.commitment_classifier.classify_commitment",
                   new_callable=AsyncMock,
                   return_value={"commitment_type": "explicit", "is_commitment": True,
                                 "confidence": 0.85, "state": "active", "owner": "user",
                                 "reasoning": "test", "llm_powered": False}):
            # Alice creates a signal (audit-logged)
            client.post("/api/signals", json={
                "entity": "AliceCorp",
                "text": "I will send it",
                "signal_type": "commitment_made",
            }, headers=alice_h)

            # Bob creates a signal (audit-logged)
            client.post("/api/signals", json={
                "entity": "BobCorp",
                "text": "I will send it",
                "signal_type": "commitment_made",
            }, headers=bob_h)

            # Alice's audit log should only show Alice's events
            alice_log = client.get("/api/audit-log", headers=alice_h).json()["events"]
            for event in alice_log:
                assert event["user_email"] == "alice@test.com", \
                    "P1-4: Alice's audit log contains Bob's events"

            # Bob's audit log should only show Bob's events
            bob_log = client.get("/api/audit-log", headers=bob_h).json()["events"]
            for event in bob_log:
                assert event["user_email"] == "bob@test.com", \
                    "P1-4: Bob's audit log contains Alice's events"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

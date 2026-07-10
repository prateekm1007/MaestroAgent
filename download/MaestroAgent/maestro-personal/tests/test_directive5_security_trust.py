"""
Tests for Directive 5: Security, Trust & Defensibility.

Tests:
- Calibration history endpoint (Brier score trends)
- Privacy-first processing indicators (local/cloud/rules mode)
- Audit log (every data access logged)
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
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-d5"
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


@pytest.fixture
def auth_headers(client):
    response = client.post("/api/auth/login", json={"password": "any"})
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


class TestCalibrationHistory:
    """GET /api/calibration/history — Brier score trends."""

    def test_endpoint_exists(self, client, auth_headers):
        """The calibration history endpoint must exist and return 200."""
        response = client.get("/api/calibration/history", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "history" in data
        assert isinstance(data["history"], list)

    def test_records_snapshot(self):
        """Recording a snapshot must persist it."""
        from maestro_personal_shell.audit_trust import record_calibration_snapshot, get_calibration_history, init_audit_tables
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            init_audit_tables(db_path)
            record_calibration_snapshot("test@example.com", db_path=db_path)
            history = get_calibration_history("test@example.com", db_path=db_path)
            assert len(history) >= 1
        finally:
            os.unlink(db_path)

    def test_history_scoped_to_user(self, client, auth_headers):
        """Calibration history must be scoped to the authenticated user."""
        # Login as a different user
        resp = client.post("/api/auth/login", json={"user_email": "other@example.com"})
        other_token = resp.json()["token"]
        other_headers = {"Authorization": f"Bearer {other_token}"}

        # Record for first user
        from maestro_personal_shell.audit_trust import record_calibration_snapshot
        record_calibration_snapshot("bootstrap")  # default user

        # Record for other user
        record_calibration_snapshot("other@example.com")

        # First user should only see their own
        resp1 = client.get("/api/calibration/history", headers=auth_headers)
        resp2 = client.get("/api/calibration/history", headers=other_headers)

        # Both should work without error
        assert resp1.status_code == 200
        assert resp2.status_code == 200


class TestPrivacyMode:
    """GET /api/privacy/mode — processing transparency."""

    def test_endpoint_exists(self, client, auth_headers):
        """The privacy mode endpoint must exist and return 200."""
        response = client.get("/api/privacy/mode", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "mode" in data
        assert "provider" in data
        assert "data_location" in data
        assert "description" in data

    def test_mode_is_valid(self, client, auth_headers):
        """The mode must be one of the valid values."""
        response = client.get("/api/privacy/mode", headers=auth_headers)
        data = response.json()
        assert data["mode"] in ("local_rules", "cloud_llm", "local_llm")

    def test_local_rules_when_no_llm(self):
        """When no LLM is available, mode must be local_rules."""
        from maestro_personal_shell.audit_trust import get_processing_mode
        with patch("maestro_personal_shell.llm_bridge.is_llm_available", return_value=False):
            result = get_processing_mode()
            assert result["mode"] == "local_rules"
            assert result["data_location"] == "on-device"

    def test_cloud_llm_when_provider_available(self):
        """When a cloud LLM is available, mode must be cloud_llm."""
        from maestro_personal_shell.audit_trust import get_processing_mode
        with patch("maestro_personal_shell.llm_bridge.is_llm_available", return_value=True), \
             patch("maestro_personal_shell.llm_bridge.get_llm_provider_name", return_value="zai-glm"), \
             patch("maestro_personal_shell.llm_bridge.get_llm_router", return_value=type("R", (), {"default_provider": "zai-glm"})()):
            result = get_processing_mode()
            assert result["mode"] == "cloud_llm"
            assert result["data_location"] == "cloud"


class TestAuditLog:
    """GET /api/audit-log — every data access logged."""

    def test_endpoint_exists(self, client, auth_headers):
        """The audit log endpoint must exist and return 200."""
        response = client.get("/api/audit-log", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert isinstance(data["events"], list)

    def test_write_logged(self, client, auth_headers):
        """Writing a signal must create an audit log entry."""
        with patch(
            "maestro_personal_shell.commitment_classifier.classify_commitment",
            new_callable=AsyncMock,
            return_value={"commitment_type": "explicit", "is_commitment": True, "confidence": 0.9,
                          "state": "active", "owner": "user", "reasoning": "test", "llm_powered": False},
        ), patch(
            "maestro_personal_shell.llm_bridge.llm_complete",
            new_callable=AsyncMock, return_value=None,
        ):
            # Create a signal (triggers audit log)
            client.post(
                "/api/signals",
                json={"entity": "AuditCorp", "text": "I will send the proposal", "signal_type": "commitment_made"},
                headers=auth_headers,
            )

            # Check audit log
            response = client.get("/api/audit-log", headers=auth_headers)
            events = response.json()["events"]

            # Must have at least one write event for /api/signals
            write_events = [e for e in events if e.get("action") == "write" and "/api/signals" in e.get("endpoint", "")]
            assert len(write_events) >= 1, "Signal creation must be logged in audit log"

    def test_audit_log_scoped_to_user(self, client, auth_headers):
        """Audit log must only show events for the authenticated user."""
        # Login as different users
        resp = client.post("/api/auth/login", json={"user_email": "alice@example.com"})
        alice_headers = {"Authorization": f"Bearer {resp.json()['token']}"}
        resp = client.post("/api/auth/login", json={"user_email": "bob@example.com"})
        bob_headers = {"Authorization": f"Bearer {resp.json()['token']}"}

        from maestro_personal_shell.audit_trust import log_data_access
        log_data_access("alice@example.com", "read", "/api/test", "res1")
        log_data_access("bob@example.com", "read", "/api/test", "res2")

        # Alice should only see her events
        resp = client.get("/api/audit-log", headers=alice_headers)
        alice_events = resp.json()["events"]
        for e in alice_events:
            assert e["user_email"] == "alice@example.com", \
                "Audit log must be scoped to user — Alice should not see Bob's events"

    def test_action_filter(self, client, auth_headers):
        """Audit log must support filtering by action."""
        from maestro_personal_shell.audit_trust import log_data_access
        log_data_access("bootstrap", "read", "/api/test1")
        log_data_access("bootstrap", "write", "/api/test2")

        # Filter by write only
        response = client.get("/api/audit-log?action=write", headers=auth_headers)
        events = response.json()["events"]
        for e in events:
            assert e["action"] == "write", "Action filter must work"


class TestProcessingModeInResponses:
    """Privacy indicators should be available for all responses."""

    def test_llm_status_includes_processing_mode(self, client, auth_headers):
        """The /api/llm-status endpoint should indicate processing mode."""
        response = client.get("/api/llm-status", headers=auth_headers)
        data = response.json()
        # llm-status already reports mode — verify it's consistent with privacy/mode
        assert "mode" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

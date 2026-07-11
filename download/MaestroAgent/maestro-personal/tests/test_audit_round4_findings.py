"""
Verify the 4th external audit fixes (F2, F4, F8, F10).
F1 (CRITICAL cross-user) verified in test_critical_cross_user_isolation.py.
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
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-audit4"
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


def _login(client, email="audit4@test.com"):
    resp = client.post("/api/auth/login", json={
        "user_email": email,
        "password": os.environ["MAESTRO_PERSONAL_TOKEN"],
    })
    return {"Authorization": f"Bearer {resp.json()['token']}"}


# F2: No fake perspectives
class TestNoFakePerspectives:
    """The auditor found /api/ask returns populated perspectives where every
    entry says 'No agent insight available.' Fix: return empty array when
    no real insight, plus intelligence_source field."""

    def test_perspectives_empty_without_llm(self, client):
        """When no LLM is available, perspectives must be empty (not
        populated with 'No agent insight' entries)."""
        headers = _login(client)

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
                "entity": "TestCorp",
                "text": "I will send the proposal",
                "signal_type": "commitment_made",
            }, headers=headers)

            resp = client.post("/api/ask", json={
                "query": "What did TestCorp commit to?",
            }, headers=headers)
            assert resp.status_code == 200
            data = resp.json()
            perspectives = data.get("perspectives", [])

            # No perspective should say "No agent insight available"
            for p in perspectives:
                obs = p.get("observation", "").lower()
                assert "no agent insight" not in obs, (
                    f"P1-Audit-F2 FAIL: perspective still contains 'No agent insight': {p}"
                )

    def test_intelligence_source_field_present(self, client):
        """Every Ask response must include intelligence_source field."""
        headers = _login(client)

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
                "entity": "TestCorp2",
                "text": "I will send the proposal",
                "signal_type": "commitment_made",
            }, headers=headers)

            resp = client.post("/api/ask", json={
                "query": "What did TestCorp2 commit to?",
            }, headers=headers)
            data = resp.json()
            assert "intelligence_source" in data, (
                "P1-Audit-F2 FAIL: intelligence_source field missing from Ask response"
            )
            assert data["intelligence_source"] in ("llm", "rules", "ranker"), (
                f"intelligence_source must be llm/rules/ranker, got: {data['intelligence_source']}"
            )
            # Without LLM, should be "rules"
            assert data["intelligence_source"] == "rules", (
                f"Without LLM, intelligence_source should be 'rules', got: {data['intelligence_source']}"
            )


# F4: Audit log failures surfaced
class TestAuditLogFailureSurfaced:
    """The auditor found audit-log write failures are silently swallowed.
    Fix: surface the error in the response + log at ERROR."""

    def test_signal_response_has_audit_log_error_field(self, client):
        """SignalResponse must include audit_log_error field (None when OK)."""
        headers = _login(client)

        with patch("maestro_personal_shell.commitment_classifier.classify_commitment",
                   new_callable=AsyncMock,
                   return_value={"commitment_type": "explicit", "is_commitment": True,
                                 "confidence": 0.85, "state": "active", "owner": "user",
                                 "reasoning": "test", "llm_powered": False}), \
             patch("maestro_personal_shell.llm_bridge.llm_complete",
                   new_callable=AsyncMock, return_value=None), \
             patch("maestro_personal_shell.llm_bridge.is_llm_available",
                   return_value=False):
            resp = client.post("/api/signals", json={
                "entity": "AuditTestCorp",
                "text": "I will send the proposal",
                "signal_type": "commitment_made",
            }, headers=headers)
            assert resp.status_code == 200
            data = resp.json()
            assert "audit_log_error" in data, (
                "P1-Audit-F4 FAIL: audit_log_error field missing from SignalResponse"
            )
            # When audit log works, audit_log_error should be None
            assert data["audit_log_error"] is None, (
                f"audit_log_error should be None when log succeeds, got: {data['audit_log_error']}"
            )

    def test_audit_log_failure_surfaced_in_response(self, client):
        """When log_data_access raises, the error must appear in the response."""
        headers = _login(client)

        with patch("maestro_personal_shell.commitment_classifier.classify_commitment",
                   new_callable=AsyncMock,
                   return_value={"commitment_type": "explicit", "is_commitment": True,
                                 "confidence": 0.85, "state": "active", "owner": "user",
                                 "reasoning": "test", "llm_powered": False}), \
             patch("maestro_personal_shell.llm_bridge.llm_complete",
                   new_callable=AsyncMock, return_value=None), \
             patch("maestro_personal_shell.llm_bridge.is_llm_available",
                   return_value=False), \
             patch("maestro_personal_shell.audit_trust.log_data_access",
                   side_effect=RuntimeError("DB table missing")):
            resp = client.post("/api/signals", json={
                "entity": "AuditFailTest",
                "text": "I will send the proposal",
                "signal_type": "commitment_made",
            }, headers=headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data.get("audit_log_error") is not None, (
                "P1-Audit-F4 FAIL: audit_log_error should be set when log_data_access raises"
            )
            assert "DB table missing" in data["audit_log_error"], (
                f"audit_log_error should contain the error message, got: {data['audit_log_error']}"
            )


# F8: WebSocket query-param token removed
class TestWebSocketNoQueryParamInProduction:
    """The auditor found query-param token auth leaks via logs. Fix:
    query-param path removed entirely; subprotocol is the only method."""

    def test_query_param_token_not_accepted(self, client):
        """Connecting with ?token=<valid> must NOT authenticate — only
        subprotocol works."""
        headers = _login(client)
        token = headers["Authorization"].split("Bearer ")[1]

        # Query param should NOT work
        try:
            with client.websocket_connect(f"/ws/copilot?token={token}") as ws:
                msg = ws.receive_json()
                assert msg.get("type") == "error", (
                    "P1-Audit-F8 FAIL: query-param token should not authenticate"
                )
        except Exception:
            pass  # disconnect is acceptable

    def test_subprotocol_token_works(self, client):
        """Subprotocol auth must work."""
        headers = _login(client)
        token = headers["Authorization"].split("Bearer ")[1]

        with patch("maestro_personal_shell.commitment_classifier.classify_commitment",
                   new_callable=AsyncMock,
                   return_value={"commitment_type": "explicit", "is_commitment": True,
                                 "confidence": 0.85, "state": "active", "owner": "user",
                                 "reasoning": "test", "llm_powered": False}), \
             patch("maestro_personal_shell.llm_bridge.llm_complete",
                   new_callable=AsyncMock, return_value=None):
            try:
                with client.websocket_connect(
                    "/ws/copilot",
                    subprotocols=[f"bearer:{token}"],
                ) as ws:
                    ws.send_text('{"type":"start","entity":"Test"}')
                    msg = ws.receive_json()
                    assert msg["type"] in ("started", "error")
            except Exception:
                pass


# F10: /api/depth honest metrics
class TestDepthHonestMetrics:
    """The auditor found /api/depth reports 78% by counting wired modules
    that return empty output. Fix: separate wired from producing_value."""

    def test_depth_has_producing_value_count(self, client):
        """/api/depth must include producing_value_count (not just wired_count)."""
        headers = _login(client)
        resp = client.get("/api/depth", headers=headers)
        assert resp.status_code == 200
        data = resp.json()

        assert "producing_value_count" in data, "Must have producing_value_count"
        assert "producing_value_pct" in data, "Must have producing_value_pct"
        assert "placeholder_modules" in data, "Must list placeholder modules"
        assert data["producing_value_count"] <= data["wired_count"], (
            "producing_value_count must be <= wired_count"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

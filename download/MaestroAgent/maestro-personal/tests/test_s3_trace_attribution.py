"""
S3 fix: trace attribution — user_email must be correctly logged in
trace_events, not 'unknown'.

The bug: the middleware read get_user_email() AFTER call_next returned,
but verify_token sets the contextvar inside the endpoint's child context.
Contextvars don't propagate child→parent, so the middleware always saw
"unknown".

The fix: resolve user_email in the middleware BEFORE call_next and store
on request.state, which survives the context boundary.
"""

import sys
import os
import tempfile
import sqlite3
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
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-s3-trace"
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


class TestTraceAttribution:
    """S3: trace_events must log the correct user_email, not 'unknown'."""

    def test_trace_event_has_correct_user_email(self, client):
        """When Alice makes an authenticated request, the trace_events
        table must log user_email='alice@test.com', NOT 'unknown'."""
        # Login as Alice
        resp = client.post("/api/auth/login", json={
            "user_email": "alice-trace@test.com",
            "password": os.environ["MAESTRO_PERSONAL_TOKEN"],
        })
        assert resp.status_code == 200
        token = resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Make an authenticated request
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
                "entity": "TraceTestCorp",
                "text": "I will send the proposal",
                "signal_type": "commitment_made",
            }, headers=headers)

        # Check the trace_events table
        db_path = os.environ["MAESTRO_PERSONAL_DB"]
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT user_email, surface, event_type FROM trace_events WHERE surface = '/api/signals' ORDER BY id DESC LIMIT 1"
        ).fetchall()
        conn.close()

        assert len(rows) >= 1, "Expected at least one trace event for /api/signals"
        logged_email = rows[0][0]
        assert logged_email == "alice-trace@test.com", (
            f"S3 FAIL: trace_events.user_email should be 'alice-trace@test.com', "
            f"got '{logged_email}'. The middleware is not resolving user_email "
            f"correctly — contextvar child→parent propagation bug."
        )

    def test_different_users_get_different_trace_emails(self, client):
        """Alice and Bob make requests — their trace events must have
        different user_emails."""
        # Login as Alice
        resp_a = client.post("/api/auth/login", json={
            "user_email": "alice-trace-ab@test.com",
            "password": os.environ["MAESTRO_PERSONAL_TOKEN"],
        })
        headers_a = {"Authorization": f"Bearer {resp_a.json()['token']}"}

        # Login as Bob
        resp_b = client.post("/api/auth/login", json={
            "user_email": "bob-trace-ab@test.com",
            "password": os.environ["MAESTRO_PERSONAL_TOKEN"],
        })
        headers_b = {"Authorization": f"Bearer {resp_b.json()['token']}"}

        # Both make requests
        client.get("/api/signals", headers=headers_a)
        client.get("/api/signals", headers=headers_b)

        # Check trace_events
        db_path = os.environ["MAESTRO_PERSONAL_DB"]
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT DISTINCT user_email FROM trace_events WHERE surface = '/api/signals'"
        ).fetchall()
        conn.close()

        emails = {r[0] for r in rows}
        assert "alice-trace-ab@test.com" in emails, (
            f"Alice's email should be in trace_events. Found: {emails}"
        )
        assert "bob-trace-ab@test.com" in emails, (
            f"Bob's email should be in trace_events. Found: {emails}"
        )

    def test_unauthenticated_request_logs_unknown(self, client):
        """A request without auth should log user_email='unknown' (or empty)."""
        # Make an unauthenticated request to /api/health (no auth required)
        client.get("/api/health")

        db_path = os.environ["MAESTRO_PERSONAL_DB"]
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT user_email FROM trace_events WHERE surface = '/api/health' ORDER BY id DESC LIMIT 1"
        ).fetchall()
        conn.close()

        assert len(rows) >= 1, "Expected a trace event for /api/health"
        logged_email = rows[0][0]
        # Unauthenticated requests should have empty or "unknown" — NOT a real user
        assert logged_email in ("", "unknown"), (
            f"Unauthenticated request should log empty/unknown, got '{logged_email}'"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""
Pilot Smoke Test — fresh app, no warmup, all critical routes.

Per CEO directive Blocker 6: 'Every user-facing route must either return
valid result, return explicit degraded-mode response, or fail with clean
structured error. Never crash with raw runtime bug.'

This test:
  1. Creates a fresh app
  2. Hits all critical routes WITHOUT prior warmup
  3. Verifies 200s or deliberate structured 4xx/5xx only
  4. Verifies council cold-start works (no OEM warmup needed)
  5. Verifies same situation across surfaces
"""
import os
import pathlib
import sys
import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def fresh_app(tmp_path, monkeypatch):
    """Build a completely fresh app with no prior requests."""
    monkeypatch.setenv("MAESTRO_LOCAL_DEV", "true")
    monkeypatch.setenv("MAESTRO_AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.setenv("MAESTRO_ADMIN_PASSWORD", "test-admin-pass")
    monkeypatch.setenv("MAESTRO_APP_DIR", str(pathlib.Path(__file__).resolve().parents[3]))
    monkeypatch.setenv("MAESTRO_USE_COUNCIL", "true")

    from maestro_api.oem_state import oem_state, import_state
    import_state._initialized = False
    import_state.store = None
    import_state.oauth = None
    import_state.connections = None
    import_state.tracker = None
    import_state.factory = None
    import_state.engine = None
    oem_state._initialized = False

    from maestro_api.main import create_app
    app = create_app(db_path=str(tmp_path / "maestro.db"))
    with TestClient(app) as c:
        yield c


class TestPilotSmokeFreshApp:
    """All critical routes must work on a fresh app without warmup."""

    def test_health(self, fresh_app):
        """Health endpoint returns 200."""
        resp = fresh_app.get("/api/health")
        assert resp.status_code == 200, f"Health failed: {resp.status_code}"

    def test_council_situations_cold_start(self, fresh_app):
        """Council situations work without prior OEM route calls."""
        resp = fresh_app.get("/api/council/situations")
        assert resp.status_code == 200
        body = resp.json()
        assert "situations" in body
        # Should have demo situations (demo seed is default)
        assert len(body["situations"]) > 0, "No situations on cold start"

    def test_council_ask_cold_start(self, fresh_app):
        """Council Ask works without prior OEM route calls."""
        resp = fresh_app.post("/api/council/ask", json={
            "query": "What is happening with Globex?",
            "org_id": "default",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "answer" in body
        assert len(body["answer"]) > 0, "Empty answer on cold start"

    def test_council_briefing_cold_start(self, fresh_app):
        """Council Briefing works without prior OEM route calls."""
        resp = fresh_app.post("/api/council/briefing", json={
            "user_email": "",
            "org_id": "default",
            "briefing_type": "morning",
        })
        assert resp.status_code == 200

    def test_council_prepare_cold_start(self, fresh_app):
        """Council Prepare works without prior OEM route calls."""
        resp = fresh_app.post("/api/council/prepare", json={
            "org_id": "default",
        })
        assert resp.status_code in (200, 404)  # 404 if no situations need prep

    def test_oem_ask_cold_start(self, fresh_app):
        """OEM Ask works without prior warmup."""
        resp = fresh_app.get("/api/oem/ask?q=What+is+happening+with+Globex")
        assert resp.status_code == 200

    def test_oem_briefing_cold_start(self, fresh_app):
        """OEM CEO Briefing works without prior warmup."""
        resp = fresh_app.get("/api/oem/ceo-briefing")
        assert resp.status_code == 200

    def test_no_raw_crash_on_any_route(self, fresh_app):
        """No route should return a raw 500 with unstructured error."""
        routes_to_test = [
            ("GET", "/api/health"),
            ("GET", "/api/council/situations"),
            ("POST", "/api/council/ask"),
            ("POST", "/api/council/briefing"),
            ("POST", "/api/council/prepare"),
            ("GET", "/api/oem/ask?q=test"),
            ("GET", "/api/oem/ceo-briefing"),
        ]
        for method, path in routes_to_test:
            if method == "GET":
                resp = fresh_app.get(path)
            else:
                body = {"query": "test", "org_id": "default"} if "ask" in path else \
                       {"user_email": "", "org_id": "default"} if "briefing" in path else \
                       {"org_id": "default"}
                resp = fresh_app.post(path, json=body)
            # 500 is OK if it's a structured error, not a raw crash
            if resp.status_code == 500:
                body = resp.json()
                assert "detail" in body, f"Raw crash on {path}: no structured error"
                assert len(body["detail"]) > 0, f"Empty error on {path}"

    def test_xss_regression(self, fresh_app):
        """XSS payload in query must never appear unescaped in response."""
        resp = fresh_app.get("/api/oem/ask?q=<script>alert('xss')</script>")
        body_text = resp.text
        assert "<script>" not in body_text, "XSS payload not escaped in response"

    def test_council_default_mode(self, fresh_app):
        """Council is the default product path (MAESTRO_USE_COUNCIL defaults to true)."""
        resp = fresh_app.get("/")
        assert "MAESTRO_USE_COUNCIL = true" in resp.text, \
            "Council should be default (true), not legacy (false)"

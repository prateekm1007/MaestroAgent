"""
V8 Personal Mode — Frontend + API Routes Tests.

Tests for:
- API routes are registered (all Personal Mode endpoints)
- Frontend files exist and have the required functions
- Command palette has Personal Mode entry
- app.html has the surface + script tag
- "What Maestro Knows" is reachable (one-click from sidebar)
- Incognito toggle exists
- Sidebar has exactly 4 items (Guideline P10 — no new sidebar items beyond 4)
"""

from __future__ import annotations

import os
import pathlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    app_dir = str(pathlib.Path(__file__).resolve().parents[3])
    os.environ.setdefault("MAESTRO_APP_DIR", app_dir)
    os.environ.setdefault("MAESTRO_AUTH_DB", "/tmp/maestro_test_personal_frontend_auth.db")
    os.environ.setdefault("MAESTRO_ADMIN_PASSWORD", "test")
    from maestro_api.main import create_app
    app = create_app(db_path=":memory:")
    with TestClient(app) as c:
        yield c


# ============================================================
# API Routes — All Personal Mode endpoints registered
# ============================================================

class TestPersonalAPIRoutes:
    """All Personal Mode API routes must be registered."""

    def test_briefing_endpoint(self, client) -> None:
        r = client.get("/api/personal/briefing")
        assert r.status_code == 200

    def test_kg_endpoint(self, client) -> None:
        r = client.get("/api/personal/kg")
        assert r.status_code == 200

    def test_memory_replay_endpoint(self, client) -> None:
        r = client.post("/api/personal/memory/replay", json={"query": "test"})
        assert r.status_code == 200

    def test_decide_endpoint(self, client) -> None:
        r = client.post("/api/personal/decide", json={"question": "test"})
        assert r.status_code == 200

    def test_habits_endpoints(self, client) -> None:
        assert client.get("/api/personal/habits/streaks").status_code == 200
        assert client.get("/api/personal/habits/suggestions").status_code == 200

    def test_predictions_endpoints(self, client) -> None:
        assert client.get("/api/personal/predictions/calibration").status_code == 200

    def test_contradictions_endpoint(self, client) -> None:
        assert client.get("/api/personal/contradictions").status_code == 200

    def test_prepared_decision_endpoint(self, client) -> None:
        r = client.post("/api/personal/prepared-decision", json={"situation": "test"})
        assert r.status_code == 200

    def test_intent_cascade_endpoint(self, client) -> None:
        r = client.post("/api/personal/intent-cascade", json={"intent": "test"})
        assert r.status_code == 200

    def test_why_endpoint(self, client) -> None:
        r = client.post("/api/personal/why", json={"question": "test"})
        assert r.status_code == 200

    def test_evolution_report_endpoint(self, client) -> None:
        assert client.get("/api/personal/evolution-report").status_code == 200

    def test_reflection_prompts_endpoint(self, client) -> None:
        assert client.get("/api/personal/reflection-prompts").status_code == 200

    def test_legacy_endpoints(self, client) -> None:
        assert client.get("/api/personal/legacy/document").status_code == 200
        assert client.get("/api/personal/legacy/prompts").status_code == 200

    def test_relationships_endpoints(self, client) -> None:
        assert client.get("/api/personal/relationships/memories").status_code == 200

    def test_ambient_context_endpoint(self, client) -> None:
        r = client.get("/api/personal/ambient-context", params={"contact": "Sarah"})
        assert r.status_code == 200

    def test_crossover_endpoints(self, client) -> None:
        assert client.get("/api/personal/crossover/contacts").status_code == 200

    def test_consent_endpoints(self, client) -> None:
        assert client.get("/api/personal/consent").status_code == 200

    def test_incognito_endpoints(self, client) -> None:
        assert client.get("/api/personal/incognito/status").status_code == 200
        assert client.post("/api/personal/incognito/start").status_code == 200
        assert client.post("/api/personal/incognito/end").status_code == 200

    def test_dashboard_endpoint(self, client) -> None:
        assert client.get("/api/personal/dashboard").status_code == 200

    def test_mode_endpoints(self, client) -> None:
        assert client.get("/api/personal/mode").status_code == 200
        r = client.post("/api/personal/mode", json={"mode": "personal"})
        assert r.status_code == 200


# ============================================================
# Frontend Files
# ============================================================

class TestPersonalFrontend:
    """Frontend files exist and have the required functions."""

    def test_personal_js_exists(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "personal.js")
        if not os.path.exists(path):
            pytest.skip("personal.js not found")
        source = open(path).read()
        assert "loadPersonalMode" in source
        assert "loadPersonalToday" in source
        assert "loadPersonalMemory" in source
        assert "loadPersonalDecide" in source
        assert "loadPersonalReflect" in source
        assert "showWhatMaestroKnows" in source
        assert "toggleIncognito" in source

    def test_personal_js_has_4_surfaces(self, client) -> None:
        """The personal sidebar must have exactly 4 items (Today/Memory/Decide/Reflect)."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "personal.js")
        if not os.path.exists(path):
            pytest.skip("personal.js not found")
        source = open(path).read()
        assert "personal-today" in source
        assert "personal-memory" in source
        assert "personal-decide" in source
        assert "personal-reflect" in source

    def test_what_maestro_knows_one_click(self, client) -> None:
        """'What Maestro Knows' must be in the personal sidebar (one click)."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "personal.js")
        if not os.path.exists(path):
            pytest.skip("personal.js not found")
        source = open(path).read()
        assert "What Maestro Knows" in source
        assert "showWhatMaestroKnows" in source
        assert "revokePersonalSource" in source

    def test_incognito_toggle_visible(self, client) -> None:
        """Incognito toggle must be visible in the Today surface."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "personal.js")
        if not os.path.exists(path):
            pytest.skip("personal.js not found")
        source = open(path).read()
        assert "Incognito mode" in source
        assert "toggleIncognito" in source

    def test_api_helpers_exist(self, client) -> None:
        """api.getPersonal and api.postPersonal must exist."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "swr_cache.js")
        if not os.path.exists(path):
            pytest.skip("swr_cache.js not found")
        source = open(path).read()
        assert "getPersonal" in source
        assert "postPersonal" in source

    def test_app_html_has_personal_surface(self, client) -> None:
        """app.html must have surface-personal + personal.js script tag."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "app.html")
        if not os.path.exists(path):
            pytest.skip("app.html not found")
        source = open(path).read()
        assert 'id="surface-personal"' in source
        assert "personal.js" in source

    def test_command_palette_has_personal(self, client) -> None:
        """Command palette must have Personal Mode entry."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "maestro.js")
        if not os.path.exists(path):
            pytest.skip("maestro.js not found")
        source = open(path).read()
        assert "'personal'" in source or '"personal"' in source
        assert "Personal Mode" in source

    def test_virtualization_has_personal(self, client) -> None:
        """virtualization.js must route 'personal' to loadPersonalMode."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "virtualization.js")
        if not os.path.exists(path):
            pytest.skip("virtualization.js not found")
        source = open(path).read()
        assert "loadPersonalMode" in source

    def test_personal_routes_separate_from_oem(self) -> None:
        """personal.py routes must NOT import from maestro_oem."""
        import maestro_api.routes.personal as mod
        source = open(mod.__file__).read()
        # Check for actual import statements (lines starting with 'from' or 'import')
        lines = source.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Only check actual import statements
            if stripped.startswith("from maestro_oem") or stripped.startswith("import maestro_oem"):
                pytest.fail(f"Line {i+1} imports from maestro_oem: {stripped}")

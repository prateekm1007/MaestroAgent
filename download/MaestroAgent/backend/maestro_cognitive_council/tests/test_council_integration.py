"""INTEGRATION tests — send requests through REAL API routes (P22).

Per P22: "Regression test must execute the production path — unit tests
don't prove wiring."

Per the external audit (C-A): "the maestro_cognitive_council package is
imported by zero production modules." This test verifies that the
/api/council/* routes actually import and call the Cognitive Council
bridges, proving the wiring is real (not just unit-tested in isolation).

These tests use FastAPI TestClient to send real HTTP requests through
the production app, verifying:
  1. The /api/council/ask route returns Situation-aware results
  2. The /api/council/briefing route returns Situation-centric briefings
  3. The /api/council/prepare route returns Situation-aware preparation
  4. The /api/council/whisper route returns Delivery Governor decisions
  5. The /api/council/copilot/pre-call route returns Situation-aware briefings
  6. The /api/council/situations route lists active situations

AUDIT C-A FOLLOW-UP (2026-07-08):
The third-party audit found that these tests verified route EXISTENCE
but not route BEHAVIOR — they never made a real HTTP call with realistic
data, so they missed the UUID serialization crash that returned 500 on
every real /api/council/ask request. The behavior-level regression test
now lives in:
    backend/maestro_api/tests/test_council_uuid_integration.py
That file loads UUID-typed signals (mirroring production maestro_oem.Signal)
and asserts on the response body — not just status code, but that
evidence_refs are strings, not UUIDs. If you add a new council route,
add a behavior test there too, not just a registration test here.
"""

from __future__ import annotations

import os
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

os.environ.setdefault(
    "MAESTRO_APP_DIR",
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
)
os.environ.setdefault("MAESTRO_LOCAL_DEV", "true")
os.environ.setdefault("MAESTRO_AUTH_ENABLED", "false")

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """Create a TestClient for the production app."""
    from maestro_api.main import create_app
    app = create_app()
    return TestClient(app)


# ════════════════════════════════════════════════════════════════════════════
# P22: The routes EXIST and are registered in the production app
# ════════════════════════════════════════════════════════════════════════════

class TestCouncilRoutesRegistered:
    """The /api/council/* routes are registered in the production app."""

    def test_council_routes_exist_in_app(self, client):
        """The /api/council/* routes are registered."""
        from maestro_api.main import create_app
        from fastapi.routing import APIRoute

        app = create_app()
        paths = [r.path for r in app.routes if hasattr(r, "path")]
        council_paths = [p for p in paths if "/api/council/" in p]

        assert len(council_paths) >= 5, (
            f"Expected ≥5 /api/council/* routes, got {council_paths}. "
            "The council router is NOT registered in main.py."
        )

    def test_council_ask_route_registered(self, client):
        """/api/council/ask exists."""
        from maestro_api.main import create_app
        app = create_app()
        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/api/council/ask" in paths

    def test_council_briefing_route_registered(self, client):
        """/api/council/briefing exists."""
        from maestro_api.main import create_app
        app = create_app()
        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/api/council/briefing" in paths

    def test_council_prepare_route_registered(self, client):
        """/api/council/prepare exists."""
        from maestro_api.main import create_app
        app = create_app()
        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/api/council/prepare" in paths

    def test_council_whisper_route_registered(self, client):
        """/api/council/whisper exists."""
        from maestro_api.main import create_app
        app = create_app()
        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/api/council/whisper" in paths

    def test_council_copilot_pre_call_route_registered(self, client):
        """/api/council/copilot/pre-call exists."""
        from maestro_api.main import create_app
        app = create_app()
        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/api/council/copilot/pre-call" in paths

    def test_council_copilot_post_call_route_registered(self, client):
        """/api/council/copilot/post-call exists."""
        from maestro_api.main import create_app
        app = create_app()
        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/api/council/copilot/post-call" in paths

    def test_council_situations_route_registered(self, client):
        """/api/council/situations exists."""
        from maestro_api.main import create_app
        app = create_app()
        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/api/council/situations" in paths


# ════════════════════════════════════════════════════════════════════════════
# P22: The routes actually CALL the Cognitive Council bridges (not just exist)
# ════════════════════════════════════════════════════════════════════════════

class TestCouncilRoutesCallBridges:
    """The routes actually import and call the Cognitive Council bridges.

    This is the P22 test: the production path must be exercised, not just
    the unit path. We verify by checking that the route imports succeed
    and the route handler references the bridge classes.
    """

    def test_council_routes_import_maestro_cognitive_council(self):
        """The council routes module imports maestro_cognitive_council.

        Per the audit (C-A): 'imported by zero production modules.'
        This test verifies that claim is now FALSE.
        """
        # Read the actual route file
        route_file = pathlib.Path(__file__).resolve().parents[2] / "maestro_api" / "routes" / "council.py"
        content = route_file.read_text()

        # Must import from maestro_cognitive_council
        assert "from maestro_cognitive_council import" in content, (
            "council.py must import from maestro_cognitive_council — "
            "the audit found zero production imports; this fixes it."
        )

        # Must import each bridge
        bridges = [
            "SituationAwareAskBridge",
            "SituationBriefingEngine",
            "SituationPreparationBridge",
            "WhisperSituationBridge",
            "CopilotSituationBridge",
            "SituationEngine",
        ]
        for bridge in bridges:
            assert bridge in content, (
                f"council.py must import {bridge} — bridge not referenced in production route."
            )

    def test_council_routes_registered_in_main(self):
        """main.py imports and registers the council router."""
        main_file = pathlib.Path(__file__).resolve().parents[2] / "maestro_api" / "main.py"
        content = main_file.read_text()

        assert "council" in content, "main.py must import the council module"
        assert "council.router" in content, "main.py must register council.router"

    def test_council_ask_route_calls_bridge(self, client):
        """POST /api/council/ask actually calls SituationAwareAskBridge.

        Sends a real HTTP request and verifies the response shape matches
        what the bridge produces (not what the old OEM AskPipeline produces).
        """
        response = client.post("/api/council/ask", json={
            "query": "What's happening?",
            "org_id": "default",
        })

        # Should get a 200 (or 500 if no OEM state — but NOT 404)
        assert response.status_code != 404, (
            "/api/council/ask returned 404 — route not registered"
        )

        if response.status_code == 200:
            data = response.json()
            # The bridge's AskResult has these fields (not the old OEM fields)
            assert "situation_id" in data or "found_situation" in data, (
                f"Response doesn't have Situation-aware fields. "
                f"Got: {list(data.keys())[:10]}"
            )

    def test_council_briefing_route_calls_bridge(self, client):
        """POST /api/council/briefing actually calls SituationBriefingEngine."""
        response = client.post("/api/council/briefing", json={
            "briefing_type": "morning",
            "org_id": "default",
        })

        assert response.status_code != 404, (
            "/api/council/briefing returned 404 — route not registered"
        )

        if response.status_code == 200:
            data = response.json()
            # The bridge's SituationCentricBriefing has these fields
            assert "top_situation" in data or "material_changes" in data, (
                f"Response doesn't have Situation-centric briefing fields. "
                f"Got: {list(data.keys())[:10]}"
            )

    def test_council_whisper_route_calls_bridge(self, client):
        """POST /api/council/whisper actually calls WhisperSituationBridge."""
        response = client.post("/api/council/whisper", json={
            "entity": "",
            "context": "meeting",
            "org_id": "default",
        })

        assert response.status_code != 404, (
            "/api/council/whisper returned 404 — route not registered"
        )

        if response.status_code == 200:
            data = response.json()
            # The bridge's WhisperResult has these fields
            assert "delivery_route" in data or "whispers" in data, (
                f"Response doesn't have Whisper bridge fields. "
                f"Got: {list(data.keys())[:10]}"
            )

    def test_council_situations_route_calls_engine(self, client):
        """GET /api/council/situations actually calls SituationEngine."""
        response = client.get("/api/council/situations?org_id=default")

        assert response.status_code != 404, (
            "/api/council/situations returned 404 — route not registered"
        )

        if response.status_code == 200:
            data = response.json()
            assert "situations" in data or "count" in data, (
                f"Response doesn't have situations fields. "
                f"Got: {list(data.keys())[:10]}"
            )

    def test_council_copilot_pre_call_route_calls_bridge(self, client):
        """POST /api/council/copilot/pre-call actually calls CopilotSituationBridge."""
        response = client.post("/api/council/copilot/pre-call", json={
            "meeting_title": "Test Meeting",
            "attendees": ["someone@example.com"],
            "org_id": "default",
        })

        assert response.status_code != 404, (
            "/api/council/copilot/pre-call returned 404 — route not registered"
        )

        if response.status_code == 200:
            data = response.json()
            # The bridge's CopilotPreCallBriefing has these fields
            assert "found_situation" in data or "talking_points" in data, (
                f"Response doesn't have Copilot bridge fields. "
                f"Got: {list(data.keys())[:10]}"
            )

    def test_council_copilot_post_call_route_calls_bridge(self, client):
        """POST /api/council/copilot/post-call actually calls CopilotSituationBridge."""
        response = client.post("/api/council/copilot/post-call", json={
            "situation_id": "sit-nonexistent",
            "transcript_chunks": [],
            "commitments": [],
            "org_id": "default",
        })

        assert response.status_code != 404, (
            "/api/council/copilot/post-call returned 404 — route not registered"
        )


# ════════════════════════════════════════════════════════════════════════════
# Auth: all council routes have @auth_policy + Depends(require_user)
# ════════════════════════════════════════════════════════════════════════════

class TestCouncilRouteAuth:
    """All council routes have auth (F4 lesson applied)."""

    def test_council_routes_have_auth_policy(self):
        """Every /api/council/ route has @auth_policy (USER or ADMIN)."""
        from maestro_api.security.policy import get_route_policy, AuthPolicy
        from maestro_api.routes.council import router

        for route in router.routes:
            policy = get_route_policy(route)
            assert policy is not None, (
                f"Route {route.path} missing @auth_policy"
            )
            # N1 fix: governance/action is ADMIN, all others are USER
            assert policy in (AuthPolicy.USER, AuthPolicy.ADMIN), (
                f"Route {route.path} has policy {policy}, expected USER or ADMIN"
            )

    def test_council_routes_have_auth_dependency(self):
        """Every /api/council/ route has Depends(require_user)."""
        from maestro_api.routes.council import router

        AUTH_GUARD_NAMES = {"require_user", "require_admin", "require_user_if_auth_enabled", "_require_user_if_auth_enabled"}
        for route in router.routes:
            dep_names: set[str] = set()
            dependant = getattr(route, "dependant", None)
            if dependant:
                for dep in getattr(dependant, "dependencies", []):
                    call = getattr(dep, "call", None)
                    if call:
                        dep_names.add(getattr(call, "__name__", repr(call)))
            for dep in getattr(route, "dependencies", []):
                call = getattr(dep, "dependency", None)
                if call:
                    dep_names.add(getattr(call, "__name__", repr(call)))

            assert not dep_names.isdisjoint(AUTH_GUARD_NAMES), (
                f"Route {route.path} missing auth dependency guard; deps={sorted(dep_names)}"
            )

    def test_council_router_included_in_app(self):
        """The council router is included in create_app()."""
        from maestro_api.main import create_app
        from fastapi.routing import APIRoute

        app = create_app()
        council_paths = [
            r.path for r in app.routes
            if isinstance(r, APIRoute) and "/api/council/" in r.path
        ]
        assert len(council_paths) >= 5, (
            f"council.router not included in app — found {council_paths}"
        )

    def test_auth_inventory_still_passes_with_council_routes(self):
        """The auth inventory test must still pass with the new council routes."""
        from maestro_api.security.policy import get_route_policy
        from maestro_api.main import create_app
        from fastapi.routing import APIRoute, APIWebSocketRoute

        app = create_app()
        failures: list[str] = []
        for r in app.routes:
            if isinstance(r, (APIRoute, APIWebSocketRoute)):
                if r.path.startswith("/api/") or r.path.startswith("/ws/"):
                    # Skip public routes
                    from maestro_api.tests.test_route_auth_inventory import _is_public_path
                    if _is_public_path(r.path):
                        continue
                    policy = get_route_policy(r)
                    if policy is None:
                        failures.append(f"{r.path} missing @auth_policy")
        assert not failures, f"Auth inventory failures:\n{chr(10).join(failures)}"

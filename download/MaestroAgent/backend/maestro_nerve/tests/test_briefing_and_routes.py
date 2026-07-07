"""Tests for the DailyBriefingEngine and the /api/nerve/* routes."""

from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import pytest


class TestDailyBriefingEngine:
    """DailyBriefingEngine — Phase 2, Feature 3."""

    def _make_engine(self):
        from maestro_nerve.daily_briefing import DailyBriefingEngine
        from maestro_nerve.base_agent import _NullOemState
        engine = DailyBriefingEngine()
        # Inject null OEM state so agents don't try to read real signals
        engine._oem_state = _NullOemState()
        return engine

    def test_morning_briefing_has_required_fields(self):
        engine = self._make_engine()
        briefing = engine.generate_morning_briefing(user_email="ceo@acme.com")
        assert "briefing_id" in briefing
        assert "briefing_type" in briefing
        assert briefing["briefing_type"] == "morning"
        assert "generated_at" in briefing
        assert "engine_version" in briefing
        assert "greeting" in briefing
        assert "date" in briefing
        assert "top_insights" in briefing
        assert "top_actions" in briefing
        assert "calendar_preview" in briefing
        assert "total_insights_generated" in briefing
        assert "agents_consulted" in briefing

    def test_evening_briefing_has_required_fields(self):
        engine = self._make_engine()
        briefing = engine.generate_evening_briefing(user_email="ceo@acme.com")
        assert "briefing_id" in briefing
        assert "briefing_type" in briefing
        assert briefing["briefing_type"] == "evening"
        assert "generated_at" in briefing
        assert "todays_wins" in briefing
        assert "todays_risks" in briefing
        assert "pending_actions" in briefing

    def test_morning_briefing_consults_17_agents(self):
        """The Chief of Staff consults 16 other agents (excludes itself)."""
        engine = self._make_engine()
        briefing = engine.generate_morning_briefing(user_email="ceo@acme.com")
        assert briefing["agents_consulted"] == 16  # 17 - 1 (chief_of_staff excludes self)

    def test_dashboard_has_required_fields(self):
        engine = self._make_engine()
        dashboard = engine.generate_agent_dashboard(user_email="ceo@acme.com")
        assert "dashboard_id" in dashboard
        assert "generated_at" in dashboard
        assert "engine_version" in dashboard
        assert "user_email" in dashboard
        assert "org_id" in dashboard
        assert "total_insights" in dashboard
        assert "agents_represented" in dashboard
        assert "filters_applied" in dashboard
        assert "insights_by_agent" in dashboard
        assert "all_insights_sorted" in dashboard

    def test_dashboard_filter_by_agent(self):
        engine = self._make_engine()
        dashboard = engine.generate_agent_dashboard(
            user_email="ceo@acme.com",
            agent_filter="growth",
        )
        assert dashboard["filters_applied"]["agent_filter"] == "growth"
        # Only growth-agent insights should be present
        for agent_name in dashboard["agents_represented"]:
            assert agent_name == "growth"

    def test_dashboard_filter_by_priority(self):
        engine = self._make_engine()
        dashboard = engine.generate_agent_dashboard(
            user_email="ceo@acme.com",
            priority_filter="high",
        )
        assert dashboard["filters_applied"]["priority_filter"] == "high"
        for ins in dashboard["all_insights_sorted"]:
            assert ins["priority"] == "high"

    def test_dashboard_filter_by_min_confidence(self):
        engine = self._make_engine()
        dashboard = engine.generate_agent_dashboard(
            user_email="ceo@acme.com",
            min_confidence=0.80,
        )
        for ins in dashboard["all_insights_sorted"]:
            assert ins["confidence"] >= 0.80

    def test_list_available_agents(self):
        engine = self._make_engine()
        agents = engine.list_available_agents()
        assert isinstance(agents, list)
        assert len(agents) == 17
        for a in agents:
            assert "name" in a
            assert "description" in a
            assert a["name"]
            assert a["description"]

    def test_morning_briefing_is_deterministic(self):
        """P25: same OEM state → same briefing (no randomness)."""
        engine = self._make_engine()
        b1 = engine.generate_morning_briefing(user_email="ceo@acme.com")
        b2 = engine.generate_morning_briefing(user_email="ceo@acme.com")
        # Same number of insights (content may differ slightly due to uuid/timestamp)
        assert b1["total_insights_generated"] == b2["total_insights_generated"]


class TestNerveRoutes:
    """API routes for /api/nerve/*."""

    def test_routes_have_auth_policy(self):
        """F4 lesson: every route must have @auth_policy."""
        from maestro_api.security.policy import get_route_policy, AuthPolicy
        from maestro_api.routes.nerve import router

        for route in router.routes:
            policy = get_route_policy(route)
            assert policy is not None, f"Route {route.path} missing @auth_policy"
            assert policy == AuthPolicy.USER, (
                f"Route {route.path} has policy {policy}, expected USER"
            )

    def test_routes_have_auth_dependency_guard(self):
        """F4 lesson: every non-public route must have Depends(require_user)."""
        from maestro_api.routes.nerve import router

        AUTH_GUARD_NAMES = {"require_user", "require_admin", "require_ws_user"}
        for route in router.routes:
            # Get all dependency call names in the route's dependant tree
            dep_names: set[str] = set()
            dependant = getattr(route, "dependant", None)
            if dependant:
                for dep in getattr(dependant, "dependencies", []):
                    call = getattr(dep, "call", None)
                    if call:
                        dep_names.add(getattr(call, "__name__", repr(call)))
            # Also check route-level deps
            for dep in getattr(route, "dependencies", []):
                call = getattr(dep, "dependency", None)
                if call:
                    dep_names.add(getattr(call, "__name__", repr(call)))
            # At least one auth guard must be present
            assert not dep_names.isdisjoint(AUTH_GUARD_NAMES), (
                f"Route {route.path} missing auth dependency guard; deps={sorted(dep_names)}"
            )

    def test_morning_briefing_endpoint_exists(self):
        """POST /api/nerve/briefing/morning is registered."""
        from maestro_api.routes.nerve import router
        paths = [r.path for r in router.routes]
        assert "/api/nerve/briefing/morning" in paths

    def test_evening_briefing_endpoint_exists(self):
        """POST /api/nerve/briefing/evening is registered."""
        from maestro_api.routes.nerve import router
        paths = [r.path for r in router.routes]
        assert "/api/nerve/briefing/evening" in paths

    def test_dashboard_endpoint_exists(self):
        """GET /api/nerve/dashboard is registered."""
        from maestro_api.routes.nerve import router
        paths = [r.path for r in router.routes]
        assert "/api/nerve/dashboard" in paths

    def test_agents_endpoint_exists(self):
        """GET /api/nerve/agents is registered."""
        from maestro_api.routes.nerve import router
        paths = [r.path for r in router.routes]
        assert "/api/nerve/agents" in paths

    def test_agent_insights_endpoint_exists(self):
        """POST /api/nerve/agent/{agent_name}/insights is registered."""
        from maestro_api.routes.nerve import router
        paths = [r.path for r in router.routes]
        assert "/api/nerve/agent/{agent_name}/insights" in paths

    def test_router_is_included_in_app(self):
        """The nerve router is included in create_app()."""
        import os
        os.environ.setdefault(
            "MAESTRO_APP_DIR",
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        )
        from maestro_api.main import create_app
        app = create_app()
        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert any("/api/nerve/" in p for p in paths), (
            "No /api/nerve/* routes registered in app"
        )

    def test_auth_inventory_still_passes_with_nerve_routes(self):
        """The auth inventory test must still pass with the 5 new nerve routes."""
        import os
        os.environ.setdefault(
            "MAESTRO_APP_DIR",
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        )
        from maestro_api.security.policy import AuthPolicy, get_route_policy
        from maestro_api.main import create_app
        from fastapi.routing import APIRoute, APIWebSocketRoute

        app = create_app()
        failures: list[str] = []
        for r in app.routes:
            if isinstance(r, (APIRoute, APIWebSocketRoute)):
                if r.path.startswith("/api/") or r.path.startswith("/ws/"):
                    policy = get_route_policy(r)
                    if policy is None:
                        failures.append(f"{r.path} missing @auth_policy")
        assert not failures, f"Auth inventory failures:\n{chr(10).join(failures)}"

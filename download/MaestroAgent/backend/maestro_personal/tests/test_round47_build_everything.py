"""
Round 47 — Build Everything Now. Test Suite.

Tests all 5 build blocks:
  Block 1: 4 enterprise features (Canvas, Per-Teammate, MCP, API Docs)
  Block 2: P1 deepening (personal swipe cards, memory conversation, contradiction cards, instant filter)
  Block 3: Mobile responsive + PWA
  Block 4: Polish (empty states, error states, loading states)
  Block 5: Pilot metrics (privacy-preserving)

Constitutional constraints that MUST hold:
  - No engagement tracking (dwell time, return frequency)
  - 4-item sidebar (V5 litmus)
  - humanize() called everywhere
  - Withdrawal path documented
  - Bright line holds (no third-party analysis)
  - Consent opt-in (defaults OFF)
"""

from __future__ import annotations

import os
import pathlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _clear_round47_state():
    """Clear all per-user settings + pilot metrics before each test."""
    from maestro_oem.user_settings import UserSettings
    from maestro_oem.pilot_metrics import PilotMetrics
    from maestro_personal.consent import ConsentStore
    from maestro_personal.mode import ModeManager
    from maestro_personal.incognito import IncognitoManager
    from maestro_personal.expiry import DataExpiry
    from maestro_personal.store import PersonalDataStore
    from maestro_personal.local import LocalFirstConfig
    UserSettings.clear()
    PilotMetrics.clear()
    ConsentStore.clear()
    ModeManager.clear()
    IncognitoManager.clear()
    DataExpiry.clear()
    PersonalDataStore.clear()
    LocalFirstConfig.clear()
    yield
    UserSettings.clear()
    PilotMetrics.clear()
    ConsentStore.clear()
    ModeManager.clear()
    IncognitoManager.clear()
    DataExpiry.clear()
    PersonalDataStore.clear()
    LocalFirstConfig.clear()


@pytest.fixture(scope="module")
def client():
    app_dir = str(pathlib.Path(__file__).resolve().parents[3])
    os.environ.setdefault("MAESTRO_APP_DIR", app_dir)
    os.environ.setdefault("MAESTRO_AUTH_DB", "/tmp/maestro_test_round47_auth.db")
    os.environ.setdefault("MAESTRO_ADMIN_PASSWORD", "test")
    from maestro_api.main import create_app
    app = create_app(db_path=":memory:")
    with TestClient(app) as c:
        yield c


def _read_static(path_parts: list[str]) -> str:
    """Read a static file."""
    import maestro_personal
    p = pathlib.Path(maestro_personal.__file__).resolve().parents[2]
    for part in path_parts:
        p = p / part
    return p.read_text()


# ============================================================
# Block 1.1 — Canvas
# ============================================================

class TestBlock1Canvas:
    """Canvas — visual decision mapping."""

    def test_canvas_backend_module_exists(self) -> None:
        from maestro_oem.canvas import build_decision_canvas
        assert callable(build_decision_canvas)

    def test_canvas_endpoint_exists(self, client) -> None:
        r = client.get("/api/oem/canvas/test-decision-id")
        assert r.status_code == 200
        data = r.json()
        assert "nodes" in data
        assert "edges" in data
        assert "assessment" in data

    def test_canvas_js_exists(self) -> None:
        source = _read_static(["static", "js", "canvas.js"])
        assert "loadCanvas" in source
        assert "renderCanvas" in source
        assert "maestro-card" in source  # Bumble styled
        assert "Montserrat" in source

    def test_canvas_js_has_withdrawal_path(self) -> None:
        source = _read_static(["static", "js", "canvas.js"])
        assert "whiteboard" in source.lower() or "withdrawal" in source.lower()

    def test_canvas_is_command_palette_only(self) -> None:
        """Canvas is NOT a sidebar item — it's command-palette only."""
        import maestro_personal
        app_html = (
            pathlib.Path(maestro_personal.__file__).resolve().parents[2]
            / "app.html"
        )
        source = app_html.read_text()
        # The surface exists
        assert 'id="surface-canvas"' in source
        # But it's NOT in the sidebar-v2-primary
        import re
        match = re.search(r'<div class="sidebar-v2-primary">(.*?)</div>\s*(?:<!--|<div class="sidebar-v2-divider">)', source, re.DOTALL)
        block = match.group(1)
        assert 'data-surface="canvas"' not in block, "Canvas must NOT be in sidebar (V5 litmus)"

    def test_canvas_has_draggable_nodes(self) -> None:
        source = _read_static(["static", "js", "canvas.js"])
        assert "_initCanvasDrag" in source or "cursor:move" in source


# ============================================================
# Block 1.2 — Per-Teammate
# ============================================================

class TestBlock1Teammate:
    """Per-Teammate view — tasks, commitments, attention, trust."""

    def test_teammate_backend_module_exists(self) -> None:
        from maestro_oem.teammate import build_teammate_view
        assert callable(build_teammate_view)

    def test_teammate_endpoint_exists(self, client) -> None:
        r = client.get("/api/oem/teammate/test@example.com")
        assert r.status_code == 200
        data = r.json()
        assert "email" in data
        assert "tasks" in data
        assert "commitments" in data
        assert "trust_score" in data
        assert "influence" in data
        assert "withdrawal_path" in data

    def test_teammate_js_exists(self) -> None:
        source = _read_static(["static", "js", "teammate.js"])
        assert "loadTeammate" in source
        assert "renderTeammate" in source
        assert "maestro-card" in source
        assert "Montserrat" in source

    def test_teammate_does_not_analyze_personal_life(self) -> None:
        """The teammate view uses only organizational data, not personal data."""
        from maestro_oem.teammate import build_teammate_view
        # The function signature takes (model, signals, email) — no personal data
        import inspect
        sig = inspect.signature(build_teammate_view)
        params = list(sig.parameters.keys())
        assert "email" in params
        assert "personal" not in str(params).lower()

    def test_teammate_is_command_palette_only(self) -> None:
        import maestro_personal
        app_html = (
            pathlib.Path(maestro_personal.__file__).resolve().parents[2]
            / "app.html"
        )
        source = app_html.read_text()
        assert 'id="surface-teammate"' in source
        # NOT in sidebar
        import re
        match = re.search(r'<div class="sidebar-v2-primary">(.*?)</div>\s*(?:<!--|<div class="sidebar-v2-divider">)', source, re.DOTALL)
        block = match.group(1)
        assert 'data-surface="teammate"' not in block


# ============================================================
# Block 1.3 — MCP Server
# ============================================================

class TestBlock1MCP:
    """MCP — Model Context Protocol integration (read-only)."""

    def test_mcp_backend_module_exists(self) -> None:
        from maestro_oem.mcp_server import list_tools, execute_tool, MCP_TOOLS
        assert len(MCP_TOOLS) >= 5

    def test_mcp_list_tools_endpoint(self, client) -> None:
        r = client.get("/api/oem/mcp/tools")
        assert r.status_code == 200
        data = r.json()
        assert "tools" in data
        assert len(data["tools"]) >= 5
        # All tools must be read-only
        for tool in data["tools"]:
            assert tool["read_only"] is True

    def test_mcp_execute_tool_endpoint(self, client) -> None:
        r = client.post("/api/oem/mcp/tool/get_laws", json={"args": {}})
        assert r.status_code == 200
        data = r.json()
        assert data["read_only"] is True
        assert data["verified_layer_applied"] is True

    def test_mcp_unknown_tool_returns_error(self, client) -> None:
        r = client.post("/api/oem/mcp/tool/nonexistent_tool", json={"args": {}})
        assert r.status_code == 200
        data = r.json()
        assert "error" in data
        assert "available_tools" in data

    def test_mcp_ask_organization_returns_verified_layer(self, client) -> None:
        r = client.post("/api/oem/mcp/tool/ask_organization", json={
            "args": {"question": "Should we hire more engineers?"}
        })
        assert r.status_code == 200
        data = r.json()
        assert data["read_only"] is True
        # The verified layer must be applied
        if "result" in data and "laws" in data["result"]:
            for law in data["result"]["laws"]:
                assert "layer" in law
                assert law["layer"] in ("fact", "candidate")

    def test_mcp_all_tools_read_only(self) -> None:
        from maestro_oem.mcp_server import MCP_TOOLS
        for name, spec in MCP_TOOLS.items():
            assert spec["read_only"] is True, f"MCP tool {name} must be read-only"


# ============================================================
# Block 1.4 — API Docs
# ============================================================

class TestBlock1APIDocs:
    """API documentation endpoint."""

    def test_docs_summary_endpoint_exists(self, client) -> None:
        r = client.get("/api/personal/docs-summary")
        assert r.status_code == 200
        data = r.json()
        assert "enterprise_endpoints" in data
        assert "personal_endpoints" in data
        assert "constitutional_notes" in data

    def test_docs_emphasize_consent(self, client) -> None:
        r = client.get("/api/personal/docs-summary")
        data = r.json()
        assert "consent" in str(data).lower()

    def test_docs_distinguish_enterprise_and_personal(self, client) -> None:
        r = client.get("/api/personal/docs-summary")
        data = r.json()
        assert data["enterprise_endpoints"]["base_url"] == "/api/oem/"
        assert data["personal_endpoints"]["base_url"] == "/api/personal/"


# ============================================================
# Block 2 — P1 Deepening
# ============================================================

class TestBlock2PersonalSwipeCards:
    """Block 2.1 — Personal briefing as swipe cards."""

    def test_personal_js_has_swipe_deck(self) -> None:
        source = _read_static(["static", "js", "personal.js"])
        assert "personal-swipe-deck-container" in source
        assert "_renderPersonalSwipeCard" in source
        assert "createSwipeCard" in source

    def test_personal_swipe_deck_max_7_cards(self) -> None:
        source = _read_static(["static", "js", "personal.js"])
        assert "slice(0, 7)" in source

    def test_personal_swipe_deck_has_summary_card(self) -> None:
        source = _read_static(["static", "js", "personal.js"])
        assert "personal-swipe-deck-summary" in source
        assert "That's your morning" in source

    def test_personal_swipe_deck_no_ritual_language(self) -> None:
        source = _read_static(["static", "js", "personal.js"])
        forbidden = ["streak broken", "don't lose progress", "celebration"]
        for pattern in forbidden:
            assert pattern not in source.lower(), f"personal.js has forbidden language: {pattern}"


class TestBlock2MemoryConversation:
    """Block 2.2 — Memory replay as conversation (follow-up chips)."""

    def test_follow_up_chips_exist(self) -> None:
        source = _read_static(["static", "js", "personal.js"])
        assert "_generateMemoryFollowUps" in source
        assert "follow-up-chip" in source

    def test_follow_up_chips_max_3(self) -> None:
        source = _read_static(["static", "js", "personal.js"])
        assert "slice(0, 3)" in source

    def test_follow_up_chips_not_llm_generated(self) -> None:
        """Follow-ups are derived from the memory graph, not an LLM."""
        source = _read_static(["static", "js", "personal.js"])
        # The function must not call an LLM endpoint
        assert "/explain" not in source or "follow" not in source.split("_generateMemoryFollowUps")[1][:200]

    def test_follow_up_css_exists(self) -> None:
        source = _read_static(["static", "css", "maestro-bumble.css"])
        assert ".follow-up-chip" in source


class TestBlock2ContradictionCards:
    """Block 2.3 — Contradictions as bold swipe cards (NOTICED not FAILED)."""

    def test_contradictions_use_noticed_not_failed(self) -> None:
        """Contradiction cards say NOTICED, not FAILED (as badge labels)."""
        source = _read_static(["static", "js", "personal.js"])
        # The card category must be NOTICED
        assert "category: 'NOTICED'" in source or 'category: "NOTICED"' in source
        # The card category must NOT be FAILED (as a badge label)
        assert "category: 'FAILED'" not in source
        assert 'category: "FAILED"' not in source

    def test_noticed_css_class_exists(self) -> None:
        source = _read_static(["static", "css", "maestro-bumble.css"])
        assert ".swipe-card-category.noticed" in source

    def test_contradiction_cards_have_reflect_and_dismiss(self) -> None:
        source = _read_static(["static", "js", "personal.js"])
        assert "REFLECT" in source
        assert "DISMISS 30D" in source


class TestBlock2InstantFilter:
    """Block 2.4 — Instant (optimistic) filter application."""

    def test_optimistic_filter_function_exists(self) -> None:
        source = _read_static(["static", "js", "mode-tabs.js"])
        assert "_optimisticFilterApply" in source

    def test_optimistic_filter_no_spinner(self) -> None:
        """The optimistic filter applies instantly without a loading spinner."""
        source = _read_static(["static", "js", "mode-tabs.js"])
        # The optimistic apply happens BEFORE the refetch
        assert "_optimisticFilterApply()" in source

    def test_filter_records_pilot_metrics(self) -> None:
        """Filter usage is recorded for pilot metrics (privacy-preserving)."""
        source = _read_static(["static", "js", "mode-tabs.js"])
        assert "/pilot/metrics/filter" in source


# ============================================================
# Block 3 — Mobile + PWA
# ============================================================

class TestBlock3MobilePWA:
    """Mobile responsive + PWA."""

    def test_mobile_responsive_css_exists(self) -> None:
        source = _read_static(["static", "css", "maestro-bumble.css"])
        assert "@media (max-width: 768px)" in source
        assert "@media (max-width: 375px)" in source

    def test_mobile_sidebar_hidden(self) -> None:
        source = _read_static(["static", "css", "maestro-bumble.css"])
        assert "#sidebar" in source
        assert "display: none" in source

    def test_pwa_manifest_exists(self) -> None:
        source = _read_static(["static", "manifest.json"])
        assert '"name"' in source
        assert '"short_name"' in source
        assert '"start_url"' in source
        assert '"display": "standalone"' in source

    def test_pwa_service_worker_exists(self) -> None:
        source = _read_static(["static", "sw.js"])
        assert "CACHE_NAME" in source
        assert "addEventListener" in source
        assert "install" in source
        assert "fetch" in source

    def test_app_html_has_manifest_link(self) -> None:
        import maestro_personal
        app_html = (
            pathlib.Path(maestro_personal.__file__).resolve().parents[2]
            / "app.html"
        )
        source = app_html.read_text()
        assert 'rel="manifest"' in source
        assert "manifest.json" in source

    def test_app_html_has_service_worker_registration(self) -> None:
        import maestro_personal
        app_html = (
            pathlib.Path(maestro_personal.__file__).resolve().parents[2]
            / "app.html"
        )
        source = app_html.read_text()
        assert "serviceWorker" in source
        assert "sw.js" in source


# ============================================================
# Block 4 — Polish (empty states, error states, loading states)
# ============================================================

class TestBlock4Polish:
    """Polish — empty states, error states, loading states."""

    def test_calm_empty_css_exists(self) -> None:
        source = _read_static(["static", "css", "maestro-bumble.css"])
        assert ".calm-empty" in source
        assert ".calm-empty-title" in source
        assert ".calm-empty-body" in source

    def test_loading_pulse_css_exists(self) -> None:
        source = _read_static(["static", "css", "maestro-bumble.css"])
        assert "@keyframes maestro-pulse" in source
        assert ".maestro-skeleton-card" in source

    def test_personal_today_has_warm_empty_state(self) -> None:
        source = _read_static(["static", "js", "personal.js"])
        assert "Connect a source" in source or "calm-empty" in source

    def test_canvas_has_warm_empty_state(self) -> None:
        source = _read_static(["static", "js", "canvas.js"])
        assert "No active decisions" in source or "calm-empty" in source

    def test_teammate_has_warm_empty_state(self) -> None:
        source = _read_static(["static", "js", "teammate.js"])
        assert "No tasks or commitments" in source or "calm-empty" in source


# ============================================================
# Block 5 — Pilot Metrics (privacy-preserving)
# ============================================================

class TestBlock5PilotMetrics:
    """Privacy-preserving pilot metrics."""

    def test_pilot_metrics_module_exists(self) -> None:
        from maestro_oem.pilot_metrics import PilotMetrics, ALLOWED_METRICS
        assert len(ALLOWED_METRICS) > 0

    def test_pilot_metrics_endpoint_exists(self, client) -> None:
        r = client.get("/api/oem/pilot/metrics")
        assert r.status_code == 200
        data = r.json()
        assert "daily_active_users" in data
        assert "cards_swiped" in data
        assert "actions_taken" in data
        assert "filter_usage" in data
        assert "feature_usage" in data
        assert "brier_score_trend" in data

    def test_pilot_metrics_no_forbidden_fields(self, client) -> None:
        """The metrics must NOT contain forbidden fields."""
        from maestro_oem.pilot_metrics import FORBIDDEN_METRIC_PATTERNS
        r = client.get("/api/oem/pilot/metrics")
        data = r.json()
        data_str = str(data).lower()
        for pattern in FORBIDDEN_METRIC_PATTERNS:
            assert pattern.lower() not in data_str, \
                f"Forbidden metric pattern in response: {pattern}"

    def test_pilot_metrics_no_dwell_time(self, client) -> None:
        r = client.get("/api/oem/pilot/metrics")
        data = r.json()
        assert "dwell_time" not in str(data).lower()
        assert "dwellTime" not in str(data)

    def test_pilot_metrics_no_return_frequency(self, client) -> None:
        r = client.get("/api/oem/pilot/metrics")
        data = r.json()
        assert "return_frequency" not in str(data).lower()
        assert "returnFrequency" not in str(data)

    def test_pilot_metrics_no_content_fields(self, client) -> None:
        """No message text, decision content, or personal data."""
        r = client.get("/api/oem/pilot/metrics")
        data = r.json()
        assert "message_text" not in str(data).lower()
        assert "decision_content" not in str(data).lower()
        assert "personal_data" not in str(data).lower()

    def test_record_card_swipe_endpoint(self, client) -> None:
        r = client.post("/api/oem/pilot/metrics/card-swipe", json={"direction": "right"})
        assert r.status_code == 200
        assert r.json()["recorded"] is True

    def test_record_action_endpoint(self, client) -> None:
        r = client.post("/api/oem/pilot/metrics/action", json={})
        assert r.status_code == 200
        assert r.json()["recorded"] is True

    def test_record_filter_endpoint(self, client) -> None:
        r = client.post("/api/oem/pilot/metrics/filter", json={"filter": "work"})
        assert r.status_code == 200
        assert r.json()["recorded"] is True

    def test_record_surface_open_endpoint(self, client) -> None:
        r = client.post("/api/oem/pilot/metrics/surface-open", json={"surface": "today"})
        assert r.status_code == 200
        assert r.json()["recorded"] is True

    def test_metrics_verify_no_forbidden_patterns(self) -> None:
        from maestro_oem.pilot_metrics import PilotMetrics
        # A payload with a forbidden pattern must fail verification
        bad_payload = {"dwell_time": 123, "cards_swiped": 5}
        assert PilotMetrics.verify_no_forbidden_metrics(bad_payload) is False
        # A clean payload must pass
        good_payload = {"cards_swiped": 5, "actions_taken": 2}
        assert PilotMetrics.verify_no_forbidden_metrics(good_payload) is True


# ============================================================
# Constitutional Invariants
# ============================================================

class TestConstitutionalInvariants:
    """The 8 constitutional constraints that MUST hold for every feature."""

    def test_v5_litmus_sidebar_4_items(self) -> None:
        """The sidebar still has exactly 4 items (V5 litmus)."""
        import maestro_personal
        app_html = (
            pathlib.Path(maestro_personal.__file__).resolve().parents[2]
            / "app.html"
        )
        source = app_html.read_text()
        import re
        match = re.search(r'<div class="sidebar-v2-primary">(.*?)</div>\s*(?:<!--|<div class="sidebar-v2-divider">)', source, re.DOTALL)
        block = match.group(1)
        link_count = len(re.findall(r'<div class="sidebar-link', block))
        assert link_count == 4, "V5 litmus: sidebar must have exactly 4 items"

    def test_no_engagement_tracking_anywhere(self) -> None:
        """No dwell time, return frequency, or engagement metrics in any JS file."""
        import maestro_personal
        static_dir = pathlib.Path(maestro_personal.__file__).resolve().parents[2] / "static" / "js"
        forbidden = ["dwell_time", "dwellTime", "return_frequency", "returnFrequency",
                     "engagement_score", "engagementScore", "session_length"]
        for js_file in static_dir.glob("*.js"):
            source = js_file.read_text()
            for pattern in forbidden:
                assert pattern not in source, \
                    f"{js_file.name} contains forbidden engagement metric: {pattern}"

    def test_bright_line_holds_in_teammate(self) -> None:
        """The teammate view does NOT analyze the teammate's personal life."""
        from maestro_oem.teammate import build_teammate_view
        import inspect
        source = inspect.getsource(build_teammate_view)
        # Must not import or reference personal-mode modules
        assert "maestro_personal" not in source
        assert "relationship_vault" not in source
        assert "ambient_context" not in source

    def test_mcp_all_tools_read_only(self) -> None:
        """All MCP tools are read-only (no modification of the model)."""
        from maestro_oem.mcp_server import MCP_TOOLS
        for name, spec in MCP_TOOLS.items():
            assert spec["read_only"] is True

    def test_withdrawal_path_in_canvas(self) -> None:
        source = _read_static(["static", "js", "canvas.js"])
        assert "whiteboard" in source.lower() or "withdrawal" in source.lower()

    def test_withdrawal_path_in_teammate(self) -> None:
        source = _read_static(["static", "js", "teammate.js"])
        assert "spreadsheet" in source.lower() or "withdrawal" in source.lower()

    def test_consent_toggle_still_defaults_off(self) -> None:
        from maestro_oem.user_settings import UserSettings
        assert UserSettings.is_personal_context_in_work_enabled("test-user") is False

    def test_humanize_called_in_new_features(self) -> None:
        """humanize() is called in canvas.js and teammate.js."""
        canvas_source = _read_static(["static", "js", "canvas.js"])
        teammate_source = _read_static(["static", "js", "teammate.js"])
        assert "humanize(" in canvas_source, "canvas.js must call humanize()"
        assert "humanize(" in teammate_source, "teammate.js must call humanize()"

    def test_no_addictive_framing(self) -> None:
        """No streaks, no 'don't lose progress', no engagement pressure."""
        import maestro_personal
        static_dir = pathlib.Path(maestro_personal.__file__).resolve().parents[2] / "static" / "js"
        forbidden = ["streak broken", "don't lose progress", "don't break your streak"]
        for js_file in static_dir.glob("*.js"):
            source = js_file.read_text().lower()
            for pattern in forbidden:
                assert pattern not in source, \
                    f"{js_file.name} contains addictive framing: {pattern}"

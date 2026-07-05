"""
Round 46 — One App, One Person. Test Suite.

Tests the 6-phase merger of Work Mode and Personal Mode into one unified app:

  Phase 0/6: Constitution amendment (One App, One Person)
  Phase 1: Mode tabs removed, filter pill added (All/Work/Personal, default All)
  Phase 2: Unified sidebar (Today/Memory/Ask/More — 4 items, no mode switching)
  Phase 3: Unified onboarding (no mode choice, separate work/personal tool screens)
  Phase 4: Unified Today surface (always unified deck, filter pill filters by mode dot)
  Phase 5: Backend — mode as filter parameter, not stored state

Constitutional invariants that MUST hold after the merger:
  - The bright line holds (no third-party analysis)
  - The dual-profile merge locking holds (Guideline P10)
  - The consent toggle holds (Personal Context in Work defaults OFF)
  - The 4-item sidebar holds (V5 litmus)
  - The withdrawal path holds (Guideline P9)
"""

from __future__ import annotations

import os
import pathlib
import warnings

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _clear_round46_state():
    """Clear all per-user settings + personal stores before each test."""
    from maestro_oem.user_settings import UserSettings
    from maestro_personal.consent import ConsentStore
    from maestro_personal.mode import ModeManager
    from maestro_personal.incognito import IncognitoManager
    from maestro_personal.expiry import DataExpiry
    from maestro_personal.store import PersonalDataStore
    from maestro_personal.local import LocalFirstConfig
    UserSettings.clear()
    ConsentStore.clear()
    ModeManager.clear()
    IncognitoManager.clear()
    DataExpiry.clear()
    PersonalDataStore.clear()
    LocalFirstConfig.clear()
    yield
    UserSettings.clear()
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
    os.environ.setdefault("MAESTRO_AUTH_DB", "/tmp/maestro_test_round46_auth.db")
    os.environ.setdefault("MAESTRO_ADMIN_PASSWORD", "test")
    from maestro_api.main import create_app
    app = create_app(db_path=":memory:")
    with TestClient(app) as c:
        yield c


def _read_static(filename: str) -> str:
    """Read a static frontend file."""
    import maestro_personal
    p = pathlib.Path(maestro_personal.__file__).resolve().parents[2] / "static" / filename
    return p.read_text()


# ============================================================
# Phase 0 — Constitution Amendment
# ============================================================

class TestPhase0ConstitutionAmendment:
    """The Round 46 amendment must be in CONSTITUTION.md."""

    def test_constitution_has_round46_amendment(self) -> None:
        import maestro_personal
        constitution_path = (
            pathlib.Path(maestro_personal.__file__).resolve().parents[2]
            / "CONSTITUTION.md"
        )
        text = constitution_path.read_text()
        assert "CONSTITUTIONAL AMENDMENT: ONE APP, ONE PERSON (Round 46)" in text
        assert "one app for one person" in text.lower()
        assert "filter, not a switch" in text.lower()

    def test_constitution_states_filter_principle(self) -> None:
        import maestro_personal
        constitution_path = (
            pathlib.Path(maestro_personal.__file__).resolve().parents[2]
            / "CONSTITUTION.md"
        )
        text = constitution_path.read_text()
        assert "Default: \"All\"" in text or 'Default: "All"' in text
        assert "filter pill" in text.lower()

    def test_constitution_states_unified_sidebar(self) -> None:
        import maestro_personal
        constitution_path = (
            pathlib.Path(maestro_personal.__file__).resolve().parents[2]
            / "CONSTITUTION.md"
        )
        text = constitution_path.read_text()
        # The constitution mentions all 4 unified sidebar items
        assert "Today" in text
        assert "Memory" in text
        assert "Ask" in text
        assert "More" in text
        assert "4-item sidebar" in text or "4 items" in text

    def test_constitution_what_does_not_change(self) -> None:
        """The 5 invariants that must NOT change after the merger."""
        import maestro_personal
        constitution_path = (
            pathlib.Path(maestro_personal.__file__).resolve().parents[2]
            / "CONSTITUTION.md"
        )
        text = constitution_path.read_text()
        assert "What Does NOT Change" in text
        assert "bright line holds" in text.lower()
        assert "dual-profile merge locking holds" in text.lower()
        assert "consent toggle holds" in text.lower()
        assert "4-item sidebar holds" in text.lower()
        assert "withdrawal path holds" in text.lower()


# ============================================================
# Phase 1 — Filter Pill (replaces mode tabs)
# ============================================================

class TestPhase1FilterPill:
    """The mode tabs are removed. A filter pill (All/Work/Personal) replaces them."""

    def test_mode_tabs_render_returns_empty(self) -> None:
        """renderModeTabs() must return an empty string (deprecated)."""
        source = _read_static("js/mode-tabs.js")
        assert "renderModeTabs" in source
        # The function must return '' (empty string)
        assert "return ''" in source

    def test_filter_pill_state_exists(self) -> None:
        """The _currentFilter state exists, defaulting to 'all'."""
        source = _read_static("js/mode-tabs.js")
        assert "_currentFilter" in source
        assert "'all'" in source

    def test_filter_pill_has_three_options(self) -> None:
        """The filter pill has 3 options: All, Work, Personal."""
        source = _read_static("js/mode-tabs.js")
        assert "renderFilterPill" in source
        assert "{ value: 'all', label: 'All' }" in source
        assert "{ value: 'work', label: 'Work' }" in source
        assert "{ value: 'personal', label: 'Personal' }" in source

    def test_filter_pill_default_is_all(self) -> None:
        """The default filter is 'all'."""
        source = _read_static("js/mode-tabs.js")
        # The initial state
        assert "let _currentFilter = 'all'" in source

    def test_filter_setter_validates_values(self) -> None:
        """setCurrentFilter only accepts valid values."""
        source = _read_static("js/mode-tabs.js")
        assert "setCurrentFilter" in source
        assert "['all', 'work', 'personal']" in source

    def test_switch_mode_deprecated(self) -> None:
        """switchMode() is deprecated and maps to setCurrentFilter."""
        source = _read_static("js/mode-tabs.js")
        assert "DEPRECATED" in source or "deprecated" in source
        assert "switchMode" in source


# ============================================================
# Phase 2 — Unified Sidebar (4 items, no mode switching)
# ============================================================

class TestPhase2UnifiedSidebar:
    """The sidebar is always Today/Memory/Ask/More. No mode switching."""

    def test_sidebar_has_4_unified_items(self) -> None:
        """app.html sidebar has exactly 4 items: Today, Memory, Ask, More."""
        import maestro_personal
        app_html = (
            pathlib.Path(maestro_personal.__file__).resolve().parents[2]
            / "app.html"
        )
        source = app_html.read_text()
        # Find the sidebar-v2-primary block — use a non-greedy match up to the
        # next "More" divider comment or the closing of sidebar-v2-primary.
        import re
        # Match from sidebar-v2-primary to the next sidebar-v2-divider
        match = re.search(
            r'<div class="sidebar-v2-primary">(.*?)</div>\s*(?:<!--|<div class="sidebar-v2-divider">)',
            source, re.DOTALL,
        )
        assert match, "sidebar-v2-primary block must exist"
        block = match.group(1)
        # Count the sidebar-link entries (each starts with <div class="sidebar-link)
        link_count = len(re.findall(r'<div class="sidebar-link', block))
        assert link_count == 4, f"Sidebar must have exactly 4 items; got {link_count}"

    def test_sidebar_has_today_memory_ask_more(self) -> None:
        """The 4 sidebar items are Today, Memory, Ask, More (not Work/Learn)."""
        import maestro_personal
        app_html = (
            pathlib.Path(maestro_personal.__file__).resolve().parents[2]
            / "app.html"
        )
        source = app_html.read_text()
        import re
        match = re.search(
            r'<div class="sidebar-v2-primary">(.*?)</div>\s*(?:<!--|<div class="sidebar-v2-divider">)',
            source, re.DOTALL,
        )
        block = match.group(1)
        assert 'data-surface="today"' in block
        assert 'data-surface="memory"' in block
        assert 'data-surface="ask-v2"' in block
        assert 'data-surface="more"' in block or 'openMoreMenu()' in block

    def test_sidebar_does_not_switch_based_on_mode(self) -> None:
        """The sidebar items are static — they don't change based on mode."""
        source = _read_static("js/mode-tabs.js")
        # renderBottomNav must use _unifiedNavItems (not _workNavItems / _personalNavItems)
        assert "_unifiedNavItems" in source
        # The old separate nav arrays should be gone or unused
        # (we check that _unifiedNavItems is the one used by renderBottomNav)
        assert "const items = _unifiedNavItems" in source

    def test_unified_nav_has_4_items(self) -> None:
        """_unifiedNavItems has exactly 4 items: Today/Memory/Ask/More."""
        source = _read_static("js/mode-tabs.js")
        import re
        match = re.search(r"_unifiedNavItems\s*=\s*\[(.*?)\]", source, re.DOTALL)
        assert match, "_unifiedNavItems must exist"
        items_block = match.group(1)
        item_count = len(re.findall(r"\{\s*id:", items_block))
        assert item_count == 4, f"Unified nav must have 4 items; got {item_count}"

    def test_memory_surface_exists_in_app_html(self) -> None:
        """app.html has a surface-memory section."""
        import maestro_personal
        app_html = (
            pathlib.Path(maestro_personal.__file__).resolve().parents[2]
            / "app.html"
        )
        source = app_html.read_text()
        assert 'id="surface-memory"' in source
        assert 'id="memory-content"' in source

    def test_loadUnifiedMemory_exists(self) -> None:
        """virtualization.js has loadUnifiedMemory function."""
        source = _read_static("js/virtualization.js")
        assert "loadUnifiedMemory" in source
        assert "case 'memory': loadUnifiedMemory" in source


# ============================================================
# Phase 3 — Unified Onboarding (no mode choice)
# ============================================================

class TestPhase3UnifiedOnboarding:
    """The onboarding has no mode-choice screen. Work and personal tools are separate."""

    def test_no_mode_choice_screen(self) -> None:
        """onboarding.js does NOT have a renderOnboardingMode function definition."""
        source = _read_static("js/onboarding.js")
        # Check that the function is not DEFINED (comments mentioning it are OK)
        import re
        # Look for 'function renderOnboardingMode' — the function definition
        assert not re.search(r'function\s+renderOnboardingMode\s*\(', source), \
            "onboarding.js must NOT define renderOnboardingMode function"
        assert not re.search(r'function\s+selectOnboardingMode\s*\(', source), \
            "onboarding.js must NOT define selectOnboardingMode function"
        assert not re.search(r'function\s+saveOnboardingMode\s*\(', source), \
            "onboarding.js must NOT define saveOnboardingMode function"
        # The _selectedMode state variable should not be declared
        assert not re.search(r'let\s+_selectedMode\s*=', source), \
            "onboarding.js must NOT declare _selectedMode state"

    def test_work_tools_screen_exists(self) -> None:
        """onboarding.js has renderOnboardingWorkTools (Screen 4)."""
        source = _read_static("js/onboarding.js")
        assert "renderOnboardingWorkTools" in source
        assert "Connect your work tools" in source
        assert "toggleWorkTool" in source
        assert "_workToolToggles" in source

    def test_personal_tools_screen_exists(self) -> None:
        """onboarding.js has renderOnboardingPersonalTools (Screen 5)."""
        source = _read_static("js/onboarding.js")
        assert "renderOnboardingPersonalTools" in source
        assert "Connect your personal tools" in source
        assert "togglePersonalTool" in source
        assert "_personalToolToggles" in source

    def test_work_tools_all_off_by_default(self) -> None:
        """All work tool toggles default to False."""
        source = _read_static("js/onboarding.js")
        # The _workToolToggles initialization must have all False values
        assert "jira: false" in source
        assert "slack: false" in source
        assert "github: false" in source

    def test_personal_tools_all_off_by_default(self) -> None:
        """All personal tool toggles default to False."""
        source = _read_static("js/onboarding.js")
        assert "personal_calendar: false" in source
        assert "personal_email: false" in source
        assert "photos: false" in source

    def test_work_and_personal_on_separate_screens(self) -> None:
        """Work tools (Screen 4) and personal tools (Screen 5) are separate."""
        source = _read_static("js/onboarding.js")
        # The screens dict must map 4 → WorkTools and 5 → PersonalTools
        assert "4: renderOnboardingWorkTools" in source
        assert "5: renderOnboardingPersonalTools" in source

    def test_no_mode_post_during_onboarding(self) -> None:
        """Onboarding does NOT POST to /mode (the mode concept is deprecated)."""
        source = _read_static("js/onboarding.js")
        # The old saveOnboardingMode posted to /mode — that function is gone
        assert "saveOnboardingMode" not in source
        # No reference to posting mode
        assert "postPersonal('/mode'" not in source


# ============================================================
# Phase 4 — Unified Today Surface (always unified deck)
# ============================================================

class TestPhase4UnifiedToday:
    """The Today surface always fetches both briefings. The filter pill filters at render."""

    def test_today_always_fetches_personal_briefing(self) -> None:
        """today.js always fetches /briefing (not just when mode==='both')."""
        source = _read_static("js/today.js")
        # The Round 46 comment must be present
        assert "Round 46" in source
        # Must NOT have the old 'if (currentMode === \'both\')' check
        # for fetching personal data
        assert "currentMode === 'both'" not in source or "Round 44" in source

    def test_today_has_filter_pill_container(self) -> None:
        """today.js renders a filter-pill-container."""
        source = _read_static("js/today.js")
        assert "filter-pill-container" in source
        assert "renderFilterPill" in source

    def test_today_applies_filter_at_render_time(self) -> None:
        """The filter is applied at render time (filteredItems), not fetch time."""
        source = _read_static("js/today.js")
        assert "filteredItems" in source
        assert "currentFilter === 'personal'" in source
        assert "currentFilter !== 'work'" in source

    def test_today_passes_filter_to_render(self) -> None:
        """renderMorningBrief receives currentFilter as a parameter."""
        source = _read_static("js/today.js")
        assert "currentFilter" in source
        # The render call must pass currentFilter
        assert "currentFilter)" in source

    def test_today_default_filter_is_all(self) -> None:
        """The default filter is 'all' (not 'work')."""
        source = _read_static("js/today.js")
        assert "currentFilter = 'all'" in source or "let currentFilter = 'all'" in source


# ============================================================
# Phase 5 — Backend: Mode as Filter, Not Stored State
# ============================================================

class TestPhase5BackendFilter:
    """The backend has a Filter enum and the mode is deprecated."""

    def test_filter_enum_exists(self) -> None:
        from maestro_personal.mode import Filter
        assert Filter.ALL.value == "all"
        assert Filter.WORK.value == "work"
        assert Filter.PERSONAL.value == "personal"

    def test_filter_from_param_defaults_to_all(self) -> None:
        from maestro_personal.mode import Filter
        assert Filter.from_param(None) == Filter.ALL
        assert Filter.from_param("") == Filter.ALL
        assert Filter.from_param("bogus") == Filter.ALL

    def test_filter_from_param_parses_valid_values(self) -> None:
        from maestro_personal.mode import Filter
        assert Filter.from_param("all") == Filter.ALL
        assert Filter.from_param("work") == Filter.WORK
        assert Filter.from_param("personal") == Filter.PERSONAL
        assert Filter.from_param("WORK") == Filter.WORK  # case-insensitive

    def test_set_mode_emits_deprecation_warning(self) -> None:
        """set_mode() must emit a DeprecationWarning (Round 46)."""
        from maestro_personal.mode import ModeManager, Mode
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            ModeManager.set_mode("test-user", Mode.WORK)
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "Round 46" in str(w[0].message) or "deprecated" in str(w[0].message).lower()

    def test_get_mode_defaults_to_both(self) -> None:
        """get_mode() defaults to BOTH (the unified experience), not WORK."""
        from maestro_personal.mode import ModeManager, Mode
        # Clear any state from previous tests
        ModeManager.clear()
        assert ModeManager.get_mode("never-set") == Mode.BOTH

    def test_unified_today_endpoint_exists(self, client) -> None:
        """GET /api/personal/today returns the unified deck."""
        r = client.get("/api/personal/today?user=default")
        assert r.status_code == 200
        data = r.json()
        assert "cards" in data
        assert "filter" in data
        assert "counts" in data
        assert data["filter"] == "all"  # default
        assert data["default_filter"] == "all"

    def test_unified_today_filter_work(self, client) -> None:
        """The work filter excludes personal cards."""
        r = client.get("/api/personal/today?user=default&filter=work")
        data = r.json()
        assert data["filter"] == "work"
        # All cards must be work mode
        for card in data["cards"]:
            assert card["_mode"] == "work"

    def test_unified_today_filter_personal(self, client) -> None:
        """The personal filter excludes work cards."""
        r = client.get("/api/personal/today?user=default&filter=personal")
        data = r.json()
        assert data["filter"] == "personal"
        # All cards must be personal mode (may be empty if no personal data)
        for card in data["cards"]:
            assert card["_mode"] == "personal"

    def test_unified_memory_endpoint_exists(self, client) -> None:
        """GET /api/personal/memory returns the unified memory feed."""
        r = client.get("/api/personal/memory?user=default")
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert "filter" in data
        assert "counts" in data

    def test_filter_options_endpoint_exists(self, client) -> None:
        """GET /api/personal/filter/options returns the 3 filter options."""
        r = client.get("/api/personal/filter/options")
        assert r.status_code == 200
        data = r.json()
        assert "options" in data
        assert len(data["options"]) == 3
        assert data["default"] == "all"
        values = [opt["value"] for opt in data["options"]]
        assert "all" in values
        assert "work" in values
        assert "personal" in values


# ============================================================
# Constitutional Invariants — What Does NOT Change
# ============================================================

class TestConstitutionalInvariants:
    """The 5 invariants that must NOT change after the Round 46 merger."""

    def test_bright_line_guard_still_exists(self) -> None:
        """The Round 44 bright-line guard still exists (no weakening)."""
        from maestro_personal.integration import _contains_third_party_intelligence
        assert _contains_third_party_intelligence("she values clear communication")
        assert _contains_third_party_intelligence("Sarah values punctuality")
        assert _contains_third_party_intelligence("your team's energy is low")
        assert not _contains_third_party_intelligence("you slept 6 hours")

    def test_consent_toggle_still_defaults_off(self) -> None:
        """The Personal Context in Work toggle still defaults to OFF."""
        from maestro_oem.user_settings import UserSettings
        assert UserSettings.is_personal_context_in_work_enabled("test-user") is False

    def test_dual_profile_merge_locking_still_works(self) -> None:
        """A contact can still have separate work + personal profiles (Guideline P10)."""
        from maestro_personal.mode import ModeManager, Mode
        ModeManager.clear()
        # Create separate profiles for the same person
        p_work = ModeManager.create_profile("sarah@x.com", Mode.WORK, name="Sarah")
        p_personal = ModeManager.create_profile("sarah@x.com", Mode.PERSONAL, name="Sarah")
        # Both profiles exist
        assert ModeManager.are_separated("sarah@x.com")
        profiles = ModeManager.get_profiles("sarah@x.com")
        assert len(profiles) == 2

    def test_v5_litmus_sidebar_4_items(self) -> None:
        """The sidebar still has exactly 4 items (V5 litmus)."""
        import maestro_personal
        app_html = (
            pathlib.Path(maestro_personal.__file__).resolve().parents[2]
            / "app.html"
        )
        source = app_html.read_text()
        import re
        match = re.search(
            r'<div class="sidebar-v2-primary">(.*?)</div>\s*(?:<!--|<div class="sidebar-v2-divider">)',
            source, re.DOTALL,
        )
        block = match.group(1)
        link_count = len(re.findall(r'<div class="sidebar-link', block))
        assert link_count == 4, "V5 litmus: sidebar must have exactly 4 items"

    def test_withdrawal_path_documented(self) -> None:
        """The constitution still documents the withdrawal path (Guideline P9)."""
        import maestro_personal
        constitution_path = (
            pathlib.Path(maestro_personal.__file__).resolve().parents[2]
            / "CONSTITUTION.md"
        )
        text = constitution_path.read_text()
        assert "withdrawal path" in text.lower()

    def test_incognito_still_suppresses_integration(self, client) -> None:
        """Incognito mode still suppresses all integration features."""
        # Enable the toggle
        client.post("/api/personal/settings/personal-context-in-work", json={
            "enabled": True, "user": "default",
        })
        # Start incognito
        client.post("/api/personal/incognito/start?user=default")
        # The CEO briefing's personal_context card must be suppressed
        r = client.get("/api/oem/ceo-briefing")
        pc = r.json().get("personal_context", {})
        assert pc == {}, "Incognito must suppress the personal context card"


# ============================================================
# V5 Litmus — No Engagement Tracking
# ============================================================

class TestV5LitmusNoEngagementTracking:
    """Round 46 must NOT introduce engagement tracking."""

    def test_no_engagement_metrics_in_today_js(self) -> None:
        source = _read_static("js/today.js")
        forbidden = ["dwell_time", "dwellTime", "return_frequency", "engagement_score"]
        for pattern in forbidden:
            assert pattern not in source, f"today.js must not track: {pattern}"

    def test_no_engagement_metrics_in_mode_tabs_js(self) -> None:
        source = _read_static("js/mode-tabs.js")
        forbidden = ["dwell_time", "dwellTime", "return_frequency", "engagement_score"]
        for pattern in forbidden:
            assert pattern not in source, f"mode-tabs.js must not track: {pattern}"

    def test_no_engagement_metrics_in_onboarding_js(self) -> None:
        source = _read_static("js/onboarding.js")
        forbidden = ["dwell_time", "dwellTime", "return_frequency", "engagement_score"]
        for pattern in forbidden:
            assert pattern not in source, f"onboarding.js must not track: {pattern}"

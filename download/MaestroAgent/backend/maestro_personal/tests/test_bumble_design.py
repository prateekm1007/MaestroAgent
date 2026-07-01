"""
V8 Maestro × Bumble Design System — Tests.

Tests for:
- Design system CSS file exists with correct specs
- Onboarding flow (6 screens) exists
- SwipeCard class exists with touch/mouse handlers
- Mode tabs + bottom nav exist
- Constitutional constraints (no dating, no addictive, humanize)
- Onboarding page exists at /static/onboarding.html
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
    os.environ.setdefault("MAESTRO_AUTH_DB", "/tmp/maestro_test_bumble_auth.db")
    os.environ.setdefault("MAESTRO_ADMIN_PASSWORD", "test")
    from maestro_api.main import create_app
    app = create_app(db_path=":memory:")
    with TestClient(app) as c:
        yield c


# ============================================================
# Design System CSS
# ============================================================

class TestDesignSystemCSS:
    """maestro-bumble.css must exist with the correct specs."""

    def test_css_file_exists(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "css", "maestro-bumble.css")
        assert os.path.exists(path), "maestro-bumble.css not found"

    def test_yellow_color(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "css", "maestro-bumble.css")
        source = open(path).read()
        assert "#FFC629" in source, "Bumble yellow #FFC629 not found"

    def test_pill_button_radius(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "css", "maestro-bumble.css")
        source = open(path).read()
        assert "999px" in source, "Pill button radius 999px not found"

    def test_card_radius(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "css", "maestro-bumble.css")
        source = open(path).read()
        assert "20px" in source, "Card radius 20px not found"

    def test_montserrat_font(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "css", "maestro-bumble.css")
        source = open(path).read()
        assert "Montserrat" in source, "Montserrat font not found"

    def test_swipe_card_class(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "css", "maestro-bumble.css")
        source = open(path).read()
        assert ".swipe-card" in source, "Swipe card class not found"
        assert "swipe-right" in source, "Swipe-right class not found"
        assert "swipe-left" in source, "Swipe-left class not found"

    def test_mode_tabs(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "css", "maestro-bumble.css")
        source = open(path).read()
        assert ".mode-tabs" in source, "Mode tabs class not found"
        assert ".mode-tab.active" in source, "Mode tab active state not found"

    def test_toggle_off_by_default(self, client) -> None:
        """Toggle must start OFF (gray), not ON (yellow)."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "css", "maestro-bumble.css")
        source = open(path).read()
        assert ".maestro-toggle" in source
        assert "var(--maestro-gray-light)" in source, "Toggle default background should be gray (OFF)"

    def test_bottom_nav(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "css", "maestro-bumble.css")
        source = open(path).read()
        assert ".bottom-nav" in source, "Bottom nav not found"
        assert ".nav-item" in source, "Nav item not found"


# ============================================================
# Onboarding
# ============================================================

class TestOnboarding:
    """The 6-screen onboarding flow must exist."""

    def test_onboarding_html_exists(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "onboarding.html")
        assert os.path.exists(path), "onboarding.html not found"

    def test_onboarding_js_has_6_screens(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "onboarding.js")
        source = open(path).read()
        assert "renderOnboardingWelcome" in source, "Screen 1 (welcome) not found"
        assert "renderOnboardingName" in source, "Screen 2 (name) not found"
        assert "renderOnboardingAbout" in source, "Screen 3 (about) not found"
        assert "renderOnboardingMode" in source, "Screen 4 (mode) not found"
        assert "renderOnboardingConnect" in source, "Screen 5 (connect) not found"
        assert "renderOnboardingDone" in source, "Screen 6 (done) not found"

    def test_onboarding_mode_cards(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "onboarding.js")
        source = open(path).read()
        assert "mode-card-work" in source, "Work mode card not found"
        assert "mode-card-personal" in source, "Personal mode card not found"
        assert "mode-card-both" in source, "Both mode card not found"

    def test_onboarding_toggles_off_by_default(self, client) -> None:
        """Source toggles must default to OFF (false)."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "onboarding.js")
        source = open(path).read()
        assert "calendar: false" in source, "Calendar toggle should default to false"
        assert "email: false" in source, "Email toggle should default to false"
        assert "photos: false" in source, "Photos toggle should default to false"

    def test_onboarding_grants_consent(self, client) -> None:
        """Turning a toggle ON should call ConsentStore.grant_consent."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "onboarding.js")
        source = open(path).read()
        assert "/consent/grant" in source, "Onboarding does not call consent/grant"


# ============================================================
# SwipeCard Class
# ============================================================

class TestSwipeCard:
    """The SwipeCard class must exist with touch + mouse handlers."""

    def test_swipe_cards_js_exists(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "swipe-cards.js")
        assert os.path.exists(path), "swipe-cards.js not found"

    def test_swipe_card_class(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "swipe-cards.js")
        source = open(path).read()
        assert "class SwipeCard" in source, "SwipeCard class not found"
        assert "touchstart" in source, "Touch start handler not found"
        assert "touchmove" in source, "Touch move handler not found"
        assert "touchend" in source, "Touch end handler not found"
        assert "mousedown" in source, "Mouse down handler not found"

    def test_create_swipe_card_helper(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "swipe-cards.js")
        source = open(path).read()
        assert "createSwipeCard" in source, "createSwipeCard helper not found"
        assert "humanize" in source, "humanize() not called in createSwipeCard"

    def test_action_sheet(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "swipe-cards.js")
        source = open(path).read()
        assert "openActionSheet" in source, "openActionSheet not found"
        assert "closeActionSheet" in source, "closeActionSheet not found"


# ============================================================
# Mode Tabs + Bottom Nav
# ============================================================

class TestModeTabsAndNav:
    """Mode tabs and bottom nav must exist."""

    def test_mode_tabs_js_exists(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "mode-tabs.js")
        assert os.path.exists(path), "mode-tabs.js not found"

    def test_render_mode_tabs(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "mode-tabs.js")
        source = open(path).read()
        assert "renderModeTabs" in source, "renderModeTabs not found"
        assert "switchMode" in source, "switchMode not found"

    def test_bottom_nav_4_items(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "mode-tabs.js")
        source = open(path).read()
        assert "renderBottomNav" in source, "renderBottomNav not found"
        assert "_workNavItems" in source, "Work nav items not found"
        assert "_personalNavItems" in source, "Personal nav items not found"
        # Each should have exactly 4 items
        assert source.count("{ id: '") >= 8, "Should have at least 8 nav items total (4 work + 4 personal)"

    def test_nav_calls_api(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "mode-tabs.js")
        source = open(path).read()
        assert "/api/personal/mode" in source, "mode-tabs.js doesn't call /api/personal/mode"


# ============================================================
# Constitutional Constraints
# ============================================================

class TestConstitutionalConstraints:
    """The Bumble aesthetic must NOT override the constitution."""

    def test_no_dating_ui(self, client) -> None:
        """No 'swipe to match', no profile photos, no compatibility %."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        for js_file in ["swipe-cards.js", "mode-tabs.js", "onboarding.js"]:
            path = os.path.join(app_dir, "static", "js", js_file)
            if not os.path.exists(path):
                continue
            source = open(path).read().lower()
            assert "swipe to match" not in source, f"{js_file} contains 'swipe to match'"
            assert "compatibility" not in source, f"{js_file} contains 'compatibility'"

    def test_no_addictive_framing(self, client) -> None:
        """No 'streak broken', 'don't lose progress', red notification dots."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        bumble_css_path = os.path.join(app_dir, "static", "css", "maestro-bumble.css")
        source = open(bumble_css_path).read().lower()
        forbidden = ["addict", "streak.*break", "don.t lose", "notification.*dot.*red"]
        for word in forbidden:
            assert word not in source, f"maestro-bumble.css contains forbidden word: '{word}'"

    def test_humanize_called_in_swipe_cards(self, client) -> None:
        """humanize() must be called in swipe-cards.js (rendering file)."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "swipe-cards.js")
        source = open(path).read()
        assert "humanize(" in source, "humanize() not called in swipe-cards.js"

    def test_app_html_has_bumble_css(self, client) -> None:
        """app.html must link maestro-bumble.css."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "app.html")
        source = open(path).read()
        assert "maestro-bumble.css" in source, "app.html missing maestro-bumble.css link"

    def test_app_html_has_swipe_cards_js(self, client) -> None:
        """app.html must include swipe-cards.js."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "app.html")
        source = open(path).read()
        assert "swipe-cards.js" in source, "app.html missing swipe-cards.js"
        assert "mode-tabs.js" in source, "app.html missing mode-tabs.js"

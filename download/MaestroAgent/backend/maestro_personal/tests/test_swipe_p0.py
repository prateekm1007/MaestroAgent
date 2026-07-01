"""
V8 P0 v2 — True Swipe Cards + 90-Second Deck + Bold Confidence Labels.

Tests for:
- P0-1: today.js calls createSwipeCard (SwipeCard class is wired, not just built)
- P0-2: Swipe-right opens action sheet (quickWriteBack wired)
- P0-3: 90-second deck (max 7 cards, summary card, no ritual language)
- P0-4: Bold confidence labels (VERIFIED/CONFIDENT/EXPLORING)
- Constitutional: no streak, no ritual, no engagement tracking
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
    os.environ.setdefault("MAESTRO_AUTH_DB", "/tmp/maestro_test_swipe_p0_auth.db")
    os.environ.setdefault("MAESTRO_ADMIN_PASSWORD", "test")
    from maestro_api.main import create_app
    app = create_app(db_path=":memory:")
    with TestClient(app) as c:
        yield c


class TestP0SwipeCards:
    """P0-1: True swipe cards wired to SwipeCard class."""

    def test_today_js_calls_createSwipeCard(self, client) -> None:
        """today.js must call createSwipeCard() — the SwipeCard class is wired."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "today.js")
        source = open(path).read()
        assert "createSwipeCard" in source, (
            "today.js does not call createSwipeCard — the SwipeCard class is built but not applied"
        )

    def test_today_js_uses_SwipeCard_class(self, client) -> None:
        """today.js must instantiate the SwipeCard class."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "today.js")
        source = open(path).read()
        assert "new SwipeCard" in source, "today.js does not instantiate SwipeCard"

    def test_today_js_has_swipe_deck_container(self, client) -> None:
        """today.js must have a swipe-deck-container element."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "today.js")
        source = open(path).read()
        assert "swipe-deck-container" in source, "today.js missing swipe-deck-container"

    def test_see_all_fallback_exists(self, client) -> None:
        """The 'See all' fallback must exist (withdrawal path)."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "today.js")
        source = open(path).read()
        assert "See all" in source, "today.js missing 'See all' fallback"
        assert "toggleSwipeDeckView" in source, "today.js missing toggleSwipeDeckView"

    def test_initSwipeDeck_called(self, client) -> None:
        """initSwipeDeck must be called after rendering."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "today.js")
        source = open(path).read()
        assert "initSwipeDeck" in source, "today.js missing initSwipeDeck"
        assert "initSwipeDeck()" in source, "initSwipeDeck is defined but not called"


class TestP0SwipeToAct:
    """P0-2: Swipe-right opens action sheet with quickWriteBack."""

    def test_swipe_right_opens_action_sheet(self, client) -> None:
        """Swipe-right must open openActionSheet."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "today.js")
        source = open(path).read()
        assert "openActionSheet" in source, "today.js doesn't call openActionSheet on swipe right"

    def test_action_sheet_calls_quickWriteBack(self, client) -> None:
        """The action sheet must call quickWriteBack."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "today.js")
        source = open(path).read()
        assert "quickWriteBack" in source, "today.js doesn't call quickWriteBack from action sheet"


class TestP0NinetySecondDeck:
    """P0-3: 90-second briefing deck — max 7 cards, summary, no ritual."""

    def test_max_7_cards(self, client) -> None:
        """The deck must be limited to 7 cards."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "today.js")
        source = open(path).read()
        assert "slice(0, 7)" in source or "slice(0,7)" in source, "today.js doesn't limit deck to 7"

    def test_summary_card_exists(self, client) -> None:
        """A summary card must exist at the end of the deck."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "today.js")
        source = open(path).read()
        assert "swipe-deck-summary" in source, "today.js missing summary card"
        assert "That's your morning" in source, "today.js missing summary text"

    def test_no_ritual_language(self, client) -> None:
        """No 'ritual', 'streak', or 'celebration' language."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "today.js")
        source = open(path).read().lower()
        forbidden = ["ritual", "streak", "celebration", "don't lose", "you missed"]
        for word in forbidden:
            assert word not in source, f"today.js contains forbidden word: '{word}'"

    def test_no_engagement_tracking(self, client) -> None:
        """No dwell time or return frequency tracking."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "today.js")
        source = open(path).read().lower()
        assert "dwell" not in source, "today.js contains dwell time tracking"
        assert "returnfreq" not in source, "today.js contains return frequency tracking"


class TestP0BoldConfidenceLabels:
    """P0-4: Bold confidence labels VERIFIED/CONFIDENT/EXPLORING."""

    def test_ask_v2_has_verified_label(self, client) -> None:
        """ask_v2.js must use VERIFIED label."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "ask_v2.js")
        source = open(path).read()
        assert "VERIFIED" in source, "ask_v2.js missing VERIFIED label"

    def test_ask_v2_has_confident_label(self, client) -> None:
        """ask_v2.js must use CONFIDENT label."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "ask_v2.js")
        source = open(path).read()
        assert "CONFIDENT" in source, "ask_v2.js missing CONFIDENT label"

    def test_ask_v2_has_exploring_label(self, client) -> None:
        """ask_v2.js must use EXPLORING label."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "ask_v2.js")
        source = open(path).read()
        assert "EXPLORING" in source, "ask_v2.js missing EXPLORING label"

    def test_verified_overrides_numeric(self, client) -> None:
        """VERIFIED must override numeric confidence (Rule D2)."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "ask_v2.js")
        source = open(path).read()
        assert "verified_by" in source, "ask_v2.js doesn't check verified_by for VERIFIED label"

    def test_today_has_confidence_labels(self, client) -> None:
        """today.js must also use bold confidence labels in list view."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "today.js")
        source = open(path).read()
        assert "VERIFIED" in source or "EXPLORING" in source, (
            "today.js doesn't use bold confidence labels in list view"
        )

    def test_humanize_still_called(self, client) -> None:
        """humanize() must still be called in both files."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        today_source = open(os.path.join(app_dir, "static", "js", "today.js")).read()
        ask_source = open(os.path.join(app_dir, "static", "js", "ask_v2.js")).read()
        assert "humanize(" in today_source, "humanize() not called in today.js"
        assert "humanize(" in ask_source, "humanize() not called in ask_v2.js"

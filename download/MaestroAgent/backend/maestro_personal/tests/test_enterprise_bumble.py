"""
V8 Bumble Design — Enterprise Surface Redesign Tests.

Tests that the enterprise Today and Ask surfaces use Bumble design system.
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
    os.environ.setdefault("MAESTRO_AUTH_DB", "/tmp/maestro_test_bumble_enterprise_auth.db")
    os.environ.setdefault("MAESTRO_ADMIN_PASSWORD", "test")
    from maestro_api.main import create_app
    app = create_app(db_path=":memory:")
    with TestClient(app) as c:
        yield c


class TestEnterpriseBumbleRedesign:
    """Enterprise Today and Ask surfaces must use Bumble design system."""

    def test_today_js_uses_maestro_card(self, client) -> None:
        """today.js must use maestro-card class for brief items."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "today.js")
        source = open(path).read()
        assert "maestro-card" in source, "today.js doesn't use maestro-card class"
        assert "swipe-card-category" in source, "today.js doesn't use swipe-card-category"

    def test_today_js_uses_montserrat(self, client) -> None:
        """today.js must use Montserrat font."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "today.js")
        source = open(path).read()
        assert "Montserrat" in source, "today.js doesn't use Montserrat font"

    def test_today_js_uses_maestro_btn(self, client) -> None:
        """today.js must use maestro-btn class for buttons."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "today.js")
        source = open(path).read()
        assert "maestro-btn" in source, "today.js doesn't use maestro-btn class"

    def test_ask_v2_js_uses_maestro_card(self, client) -> None:
        """ask_v2.js must use maestro-card class for answers."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "ask_v2.js")
        source = open(path).read()
        assert "maestro-card" in source, "ask_v2.js doesn't use maestro-card class"

    def test_ask_v2_js_has_swipe_to_rate(self, client) -> None:
        """ask_v2.js must have swipe-to-rate (Useful/Not useful buttons)."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "ask_v2.js")
        source = open(path).read()
        assert "rateAskAnswer" in source, "ask_v2.js missing rateAskAnswer function"
        assert "Useful" in source or "useful" in source, "ask_v2.js missing Useful button"
        assert "Not useful" in source or "not_useful" in source, "ask_v2.js missing Not useful button"

    def test_ask_v2_js_uses_maestro_input(self, client) -> None:
        """ask_v2.js must use maestro-input class."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "ask_v2.js")
        source = open(path).read()
        assert "maestro-input" in source, "ask_v2.js doesn't use maestro-input class"

    def test_ask_v2_feeds_attention_signals(self, client) -> None:
        """The rate buttons must call /attention/record."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "ask_v2.js")
        source = open(path).read()
        assert "/attention/record" in source, "ask_v2.js doesn't call /attention/record"

    def test_today_js_uses_bumble_yellow(self, client) -> None:
        """today.js must reference Bumble yellow color variables."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "today.js")
        source = open(path).read()
        assert "maestro-yellow" in source or "FFF4D1" in source, "today.js doesn't use Bumble yellow"

    def test_humanize_still_called_in_today(self, client) -> None:
        """humanize() must still be called in today.js."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "today.js")
        source = open(path).read()
        assert "humanize(" in source, "humanize() not called in today.js"

    def test_humanize_still_called_in_ask_v2(self, client) -> None:
        """humanize() must still be called in ask_v2.js."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "ask_v2.js")
        source = open(path).read()
        assert "humanize(" in source, "humanize() not called in ask_v2.js"

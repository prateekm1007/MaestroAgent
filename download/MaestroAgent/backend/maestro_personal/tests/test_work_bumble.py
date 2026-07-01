"""
V8 Bumble Design — Work Surface Redesign Tests.

Tests that work.js uses Bumble design system (maestro-card, Montserrat,
pill buttons, humanize still called).
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
    os.environ.setdefault("MAESTRO_AUTH_DB", "/tmp/maestro_test_work_bumble_auth.db")
    os.environ.setdefault("MAESTRO_ADMIN_PASSWORD", "test")
    from maestro_api.main import create_app
    app = create_app(db_path=":memory:")
    with TestClient(app) as c:
        yield c


class TestWorkBumbleRedesign:
    """work.js must use Bumble design system."""

    def test_work_js_uses_maestro_card(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "work.js")
        source = open(path).read()
        assert "maestro-card" in source, "work.js doesn't use maestro-card class"

    def test_work_js_uses_montserrat(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "work.js")
        source = open(path).read()
        assert "Montserrat" in source, "work.js doesn't use Montserrat font"

    def test_work_js_uses_maestro_btn(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "work.js")
        source = open(path).read()
        assert "maestro-btn" in source, "work.js doesn't use maestro-btn class"

    def test_work_js_uses_bumble_yellow(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "work.js")
        source = open(path).read()
        assert "maestro-yellow" in source or "FFF4D1" in source, "work.js doesn't use Bumble yellow"

    def test_humanize_still_called_in_work(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "work.js")
        source = open(path).read()
        assert "humanize(" in source, "humanize() not called in work.js"

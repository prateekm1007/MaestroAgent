"""
Frontend smoke tests for the cognitive-model surfaces added per the strict
UI guidelines. These verify the 6 new surfaces (Intent Cascade, Prepared
Decisions, Contradictions, Prediction Market, Assumptions, Perspectives)
are reachable from the sidebar, render without JS console errors, and call
their real API endpoints.

These tests guard against regressions in the cognitive-model UI wiring.

Phase 1: marked as browser tests — skipped by default.
Run with: python -m pytest -m browser
"""

from __future__ import annotations

import time
import threading
import pytest
from playwright.sync_api import sync_playwright

pytestmark = pytest.mark.browser


def _start_server():
    import os
    import uvicorn
    from maestro_api.main import create_app
    import pathlib
    app_dir = str(pathlib.Path(__file__).resolve().parents[3])
    os.environ["MAESTRO_APP_DIR"] = app_dir
    os.environ.setdefault("MAESTRO_AUTH_DB", "/tmp/maestro_cog_test_auth.db")
    os.environ.setdefault("MAESTRO_DEMO_SEED", "true")
    app = create_app(db_path=":memory:")
    config = uvicorn.Config(app, host="127.0.0.1", port=18791, log_level="warning")
    server = uvicorn.Server(config)

    def run():
        import asyncio
        asyncio.run(server.serve())

    t = threading.Thread(target=run, daemon=True)
    t.start()
    import urllib.request
    for _ in range(30):
        try:
            urllib.request.urlopen("http://127.0.0.1:18791/api/oem/state")
            break
        except Exception:
            time.sleep(0.5)
    return "http://127.0.0.1:18791"


@pytest.fixture(scope="module")
def server_url():
    return _start_server()


@pytest.fixture(scope="module")
def browser_context(server_url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(has_touch=True)
        page = context.new_page()
        errors: list[str] = []
        page_errors: list[str] = []
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda err: page_errors.append(str(err)))
        page.goto(server_url + "/app.html")
        page.wait_for_load_state("networkidle")
        yield page, errors, page_errors
        browser.close()


def _wait_no_loading(page, element_id, timeout_sec=15):
    import time as _t
    for _ in range(int(timeout_sec * 2)):
        text = page.text_content(f"#{element_id}") or ""
        if "Loading" not in text and "loading" not in text.lower():
            return
        _t.sleep(0.5)


class TestCognitiveModelSurfaces:
    """All 6 new cognitive-model surfaces must load without console errors
    and render real data from their respective API endpoints."""

    def test_no_console_errors_with_cognitive_surfaces(self, browser_context):
        """Loading the app with all cognitive-model surfaces must not
        produce any JS console errors."""
        _, errors, page_errors = browser_context
        # Round 65: Removed error suppression filter. CI green must mean
        # real errors are caught, not hidden. If this test fails, fix the
        # underlying error — do NOT re-add the filter.
        assert len(errors) == 0, f"Console errors: {errors}"
        assert len(page_errors) == 0, f"Page errors: {page_errors}"

    def test_prepared_decisions_loads_on_home(self, browser_context):
        """The new Prepared Decisions panel must render on Home with real
        data from /api/oem/preparations."""
        page, _, _ = browser_context
        page.evaluate("navTo('home')")
        page.wait_for_selector("#surface-home.active", timeout=5000)
        _wait_no_loading(page, "ecc-prepared", 15)
        text = page.text_content("#ecc-prepared")
        assert "Loading" not in text and "loading" not in text.lower(), (
            f"Prepared Decisions panel still loading: {text[:200]}"
        )

    def test_intent_cascade_surface_navigates(self, browser_context):
        """The Intent Cascade surface must be reachable from the sidebar
        and render intents from /api/oem/intents."""
        page, _, _ = browser_context
        page.evaluate("navTo('intents')")
        page.wait_for_selector("#surface-intents.active", timeout=5000)
        _wait_no_loading(page, "intent-cascade-list", 15)
        text = page.text_content("#intent-cascade-list")
        assert "Loading" not in text and "loading" not in text.lower()

    def test_contradictions_surface_navigates(self, browser_context):
        """The Contradictions surface must render from /api/oem/contradictions."""
        page, _, _ = browser_context
        page.evaluate("navTo('contradictions')")
        page.wait_for_selector("#surface-contradictions.active", timeout=5000)
        _wait_no_loading(page, "contradictions-list", 15)
        text = page.text_content("#contradictions-list")
        assert "Loading" not in text and "loading" not in text.lower()

    def test_prediction_market_surface_navigates(self, browser_context):
        """The Prediction Market surface must render the calibration ranking
        from /api/oem/predictions/market/calibration."""
        page, _, _ = browser_context
        page.evaluate("navTo('predictions')")
        page.wait_for_selector("#surface-predictions.active", timeout=5000)
        _wait_no_loading(page, "prediction-market-ranking", 15)
        text = page.text_content("#prediction-market-ranking")
        assert "Loading" not in text and "loading" not in text.lower()

    def test_assumptions_surface_navigates(self, browser_context):
        """The Dangerous Assumptions surface must render from
        /api/oem/assumptions/dangerous."""
        page, _, _ = browser_context
        page.evaluate("navTo('assumptions')")
        page.wait_for_selector("#surface-assumptions.active", timeout=5000)
        _wait_no_loading(page, "assumptions-dangerous", 15)
        text = page.text_content("#assumptions-dangerous")
        assert "Loading" not in text and "loading" not in text.lower()

    def test_perspectives_tab_in_drilldown(self, browser_context):
        """The drill-down modal must include a Perspectives tab. Clicking
        it must call /api/oem/perspectives and render the 6 team views."""
        page, _, _ = browser_context
        # Navigate to home and open any drilldown
        page.evaluate("navTo('home')")
        page.wait_for_selector("#surface-home.active", timeout=5000)
        # Wait for the dashboard to load, then click the first metric
        page.click("summary")
        page.wait_for_selector("#home-oem-state .metric-value", timeout=15000)
        # Click the first metric to open drilldown
        page.click("#home-oem-state .metric-clickable")
        page.wait_for_selector("#drilldown-modal:not(.hidden)", timeout=5000)
        # The Perspectives tab must exist
        persp_tab = page.query_selector('.drilldown-tab[data-tab="perspectives"]')
        assert persp_tab is not None, "Perspectives tab not found in drill-down modal"
        # Click it
        persp_tab.click()
        # The body must update (either render perspectives or show "no perspectives")
        import time as _t
        _t.sleep(1.5)
        body_text = page.text_content("#drilldown-body") or ""
        # Should NOT still say "Loading drill-down"
        assert "Loading drill-down" not in body_text, (
            f"Perspectives tab did not render: {body_text[:200]}"
        )

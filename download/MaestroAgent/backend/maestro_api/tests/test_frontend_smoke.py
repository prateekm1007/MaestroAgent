"""
Frontend smoke tests for the OEM-wired app.html.

Uses Playwright (sync API) to:
1. Load the app
2. Verify the OEM API is reachable
3. Verify every surface renders with real data
4. Verify no JS console errors
5. Verify no undefined function calls
6. Test the Ask flow end-to-end
7. Test navigation between surfaces
"""

from __future__ import annotations

import time
import threading
import pytest
from playwright.sync_api import sync_playwright


def _start_server():
    """Start the FastAPI server in a background thread. Returns the base URL."""
    import uvicorn
    from maestro_api.main import create_app

    app = create_app(db_path=":memory:")
    config = uvicorn.Config(app, host="127.0.0.1", port=18790, log_level="warning")
    server = uvicorn.Server(config)

    def run():
        import asyncio
        asyncio.run(server.serve())

    t = threading.Thread(target=run, daemon=True)
    t.start()
    # Wait for server
    import urllib.request
    for _ in range(30):
        try:
            urllib.request.urlopen("http://127.0.0.1:18790/api/oem/state")
            break
        except Exception:
            time.sleep(0.5)
    return "http://127.0.0.1:18790"


@pytest.fixture(scope="module")
def server_url():
    return _start_server()


@pytest.fixture(scope="module")
def browser_context(server_url):
    """Launch browser and open the app."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        errors: list[str] = []
        page_errors: list[str] = []
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda err: page_errors.append(str(err)))
        page.goto(server_url + "/app.html")
        page.wait_for_load_state("networkidle")
        yield page, errors, page_errors
        browser.close()


class TestAppLoads:
    def test_app_html_loads(self, browser_context):
        page, _, _ = browser_context
        assert page.title() == "Maestro — Executive Cognition Center"

    def test_no_console_errors(self, browser_context):
        _, errors, page_errors = browser_context
        # Filter out network errors
        js_errors = [e for e in errors if "Failed to fetch" not in e and "ERR_" not in e]
        assert len(js_errors) == 0, f"Console errors: {js_errors}"
        assert len(page_errors) == 0, f"Page errors: {page_errors}"

    def test_navTo_defined(self, browser_context):
        page, _, _ = browser_context
        result = page.evaluate("typeof navTo")
        assert result == "function", f"navTo is {result}"

    def test_onAskInput_defined(self, browser_context):
        page, _, _ = browser_context
        result = page.evaluate("typeof onAskInput")
        assert result == "function", f"onAskInput is {result}"

    def test_submitAsk_defined(self, browser_context):
        page, _, _ = browser_context
        result = page.evaluate("typeof submitAsk")
        assert result == "function", f"submitAsk is {result}"

    def test_home_surface_visible(self, browser_context):
        page, _, _ = browser_context
        surface = page.query_selector("#surface-home")
        assert surface is not None
        assert "active" in surface.get_attribute("class")


class TestOEMDataLoads:
    def test_dashboard_loads_real_data(self, browser_context):
        page, _, _ = browser_context
        page.wait_for_selector("#home-oem-state .metric-value", timeout=15000)
        text = page.text_content("#home-oem-state")
        assert "Loading" not in text, "Dashboard still loading"
        # The OEM seed data has 39 signals
        assert "39" in text, f"Expected 39 signals in dashboard, got: {text}"

    def test_overnight_changes_load(self, browser_context):
        page, _, _ = browser_context
        page.wait_for_selector("#home-changes", timeout=10000)
        text = page.text_content("#home-changes")
        assert "Loading" not in text

    def test_recommendations_load(self, browser_context):
        page, _, _ = browser_context
        page.wait_for_selector("#home-decisions", timeout=10000)
        text = page.text_content("#home-decisions")
        assert "Loading" not in text


class TestNavigation:
    def test_navigate_to_inbox(self, browser_context):
        page, _, _ = browser_context
        page.click('.sidebar-link[data-surface="inbox"]')
        page.wait_for_selector("#surface-inbox.active", timeout=5000)
        page.wait_for_selector("#inbox-owed", timeout=10000)
        text = page.text_content("#inbox-owed")
        assert "Loading" not in text

    def test_navigate_to_physics(self, browser_context):
        page, _, _ = browser_context
        page.click('.sidebar-link[data-surface="physics"]')
        page.wait_for_selector("#surface-physics.active", timeout=5000)
        # Wait for loading state to disappear
        page.wait_for_function(
            "!document.getElementById('physics-laws').textContent.includes('Loading')",
            timeout=15000
        )
        text = page.text_content("#physics-laws")
        assert "Loading" not in text

    def test_navigate_to_ask(self, browser_context):
        page, _, _ = browser_context
        page.click('.sidebar-link[data-surface="ask"]')
        page.wait_for_selector("#surface-ask.active", timeout=5000)

    def test_navigate_to_simulator(self, browser_context):
        page, _, _ = browser_context
        page.click('.sidebar-link[data-surface="simulator"]')
        page.wait_for_selector("#surface-simulator.active", timeout=5000)
        page.wait_for_selector("#simulator-scenario", timeout=10000)
        text = page.text_content("#simulator-scenario")
        assert "Loading" not in text

    def test_navigate_to_eng_signals(self, browser_context):
        page, _, _ = browser_context
        page.click('.sidebar-link[data-surface="eng-signals"]')
        page.wait_for_selector("#surface-eng-signals.active", timeout=5000)
        page.wait_for_function(
            "!document.getElementById('eng-signals-list').textContent.includes('Loading')",
            timeout=15000
        )
        text = page.text_content("#eng-signals-list")
        assert "Loading" not in text

    def test_breadcrumbs_update(self, browser_context):
        page, _, _ = browser_context
        page.click('.sidebar-link[data-surface="home"]')
        page.wait_for_selector("#surface-home.active", timeout=5000)
        bc = page.text_content("#bc-page")
        assert bc == "Home"


class TestAskFlow:
    def test_ask_returns_real_answer(self, browser_context):
        page, _, _ = browser_context
        page.click('.sidebar-link[data-surface="ask"]')
        page.wait_for_selector("#surface-ask.active", timeout=5000)
        page.fill("#ask-input", "bottleneck")
        page.press("#ask-input", "Enter")
        # Wait for the answer to load (not the loading state)
        page.wait_for_function(
            "document.getElementById('ask-answer-text') && !document.getElementById('ask-answer-text').textContent.includes('Asking the OEM')",
            timeout=20000
        )
        text = page.text_content("#ask-answer-text")
        assert "Asking the OEM" not in text, "Still loading"
        assert len(text) > 10, f"Answer too short: {text}"
        conf = page.text_content("#ask-confidence")
        assert "Confidence" in conf

    def test_autocomplete_appears(self, browser_context):
        page, _, _ = browser_context
        page.click('.sidebar-link[data-surface="ask"]')
        page.wait_for_selector("#surface-ask.active", timeout=5000)
        page.fill("#ask-input", "bottleneck")
        page.wait_for_selector("#exec-autocomplete.active", timeout=5000)
        assert page.query_selector("#exec-autocomplete.active") is not None


class TestNoHardcodedData:
    def test_no_askResponses_dict(self, browser_context):
        page, _, _ = browser_context
        result = page.evaluate("typeof askResponses")
        assert result == "undefined", f"askResponses still exists ({result}) — mock data not removed"

    def test_no_hardcoded_priya(self, browser_context):
        page, _, _ = browser_context
        content = page.content()
        assert "Priya M." not in content, "Hardcoded 'Priya M.' found — mock data not removed"

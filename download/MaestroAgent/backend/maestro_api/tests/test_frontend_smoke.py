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
    import os
    import uvicorn
    from maestro_api.main import create_app

    # Point to the app directory so /static/app.css and /static/js/*.js are served
        # Resolve app dir relative to this test file (works on any clone)
    import pathlib
    app_dir = str(pathlib.Path(__file__).resolve().parents[3])  # backend/../../ = app root
    os.environ["MAESTRO_APP_DIR"] = app_dir
    os.environ.setdefault("MAESTRO_AUTH_DB", "/tmp/maestro_test_auth.db")

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
    """Launch browser and open the app.

    has_touch=True enables touch events so page.tap() works for touch tests.
    """
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


class TestAppLoads:
    def test_app_html_loads(self, browser_context):
        page, _, _ = browser_context
        assert page.title() == "Maestro — Executive Cognition Center"

    def test_no_console_errors(self, browser_context):
        _, errors, page_errors = browser_context
        # Filter out network errors, 500/404 errors (slow OEM init, honest API
        # 404s from time-axis when domain has insufficient data), and CSP warnings
        # Round 61 C2 fix: do NOT suppress errors. The old code filtered out
        # "Failed to fetch", "ERR_", "500", "404", "Refused" — hiding real
        # failures behind a green CI. Now we report all errors. If there are
        # legitimate network errors in the test environment, they should be
        # fixed, not hidden.
        assert len(errors) == 0, f"Console errors: {errors}"
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
        # Constitution v2: 'home' is not in the sidebar anymore — navigate via navTo()
        page.evaluate("navTo('home')")
        page.wait_for_selector("#surface-home.active", timeout=5000)
        surface = page.query_selector("#surface-home")
        assert surface is not None
        assert "active" in surface.get_attribute("class")



def _wait_for_loading_done(page, element_id, timeout_sec=20):
    """Poll until element doesn't contain 'Loading' (CSP blocks wait_for_function)."""
    import time as _t
    for _ in range(int(timeout_sec * 2)):
        text = page.text_content(f"#{element_id}") or ""
        if "Loading" not in text:
            return
        _t.sleep(0.5)


class TestOEMDataLoads:
    def test_dashboard_loads_real_data(self, browser_context):
        page, _, _ = browser_context
        # Constitution v2: default surface is 'today', navigate to 'home' first
        page.evaluate("navTo('home')")
        page.wait_for_selector("#surface-home.active", timeout=5000)
        # OEM State is in a <details> element — expand it first
        page.click("summary")
        page.wait_for_selector("#home-oem-state .metric-value", timeout=15000)
        text = page.text_content("#home-oem-state")
        assert "Loading" not in text, "Dashboard still loading"
        # The OEM seed data has 65 signals (39 base + 26 customer from the
        # Customer Judgment Engine provider)
        assert "65" in text, f"Expected 65 signals in dashboard, got: {text}"

    def test_overnight_changes_load(self, browser_context):
        page, _, _ = browser_context
        # Constitution v2: navigate to 'home' first
        page.evaluate("navTo('home')")
        page.wait_for_selector("#surface-home.active", timeout=5000)
        page.wait_for_selector("#ecc-overnight", timeout=15000)
        # Wait for loading to finish
        _wait_for_loading_done(page, "ecc-overnight", 20)
        text = page.text_content("#ecc-overnight")
        assert "Loading" not in text

    def test_recommendations_load(self, browser_context):
        page, _, _ = browser_context
        # Constitution v2: navigate to 'home' first
        page.evaluate("navTo('home')")
        page.wait_for_selector("#surface-home.active", timeout=5000)
        page.wait_for_selector("#ecc-attention", timeout=15000)
        _wait_for_loading_done(page, "ecc-attention", 20)
        text = page.text_content("#ecc-attention")
        assert "Loading" not in text


class TestNavigation:
    def test_navigate_to_inbox(self, browser_context):
        page, _, _ = browser_context
        page.evaluate("navTo('inbox')")
        page.wait_for_selector("#surface-inbox.active", timeout=5000)
        # Poll until loading is done (CSP blocks wait_for_function)
        import time as _t
        for _ in range(40):
            text = page.text_content("#inbox-owed") or ""
            if "Loading" not in text:
                break
            _t.sleep(0.5)
        text = page.text_content("#inbox-owed")
        assert "Loading" not in text

    def test_navigate_to_physics(self, browser_context):
        page, _, _ = browser_context
        page.evaluate("navTo('physics')")
        page.wait_for_selector("#surface-physics.active", timeout=5000)
        # Wait for loading state to disappear
        _wait_for_loading_done(page, "physics-laws", 20)
        text = page.text_content("#physics-laws")
        assert "Loading" not in text

    def test_navigate_to_ask(self, browser_context):
        page, _, _ = browser_context
        page.evaluate("navTo('ask')")
        page.wait_for_selector("#surface-ask.active", timeout=5000)

    def test_navigate_to_customer(self, browser_context):
        """The Customer Judgment Engine surface must load and render real data."""
        page, _, _ = browser_context
        page.evaluate("navTo('customer')")
        page.wait_for_selector("#surface-customer.active", timeout=5000)
        # Morning brief must load
        _wait_for_loading_done(page, "customer-morning", 20)
        text = page.text_content("#customer-morning")
        assert "Loading" not in text, "Customer morning brief still loading"
        # Should mention at least one demo customer (Globex, Initech, or Hooli)
        assert any(name in text for name in ["Globex", "Initech", "Hooli"]), (
            f"Customer morning brief did not render demo customers: {text[:200]}"
        )
        # Customer list must load
        _wait_for_loading_done(page, "customer-list", 20)
        list_text = page.text_content("#customer-list")
        assert "Loading" not in list_text

    def test_customer_surface_keyboard_navigation(self, browser_context):
        """The Customer Judgment surface must be reachable via keyboard hotkey.

        Cmd/Ctrl+8 navigates to the 8th surface in the list (customer).
        """
        page, _, _ = browser_context
        # Navigate to home first (ensure we're not already on customer)
        page.evaluate("navTo('home')")
        page.wait_for_selector("#surface-home.active", timeout=10000)
        # Press Cmd/Ctrl+8 to navigate to customer (8th in the surfaces list)
        page.keyboard.press("Control+8")
        # Should now be on the customer surface
        page.wait_for_selector("#surface-customer.active", timeout=10000)
        assert page.query_selector("#surface-customer.active") is not None, (
            "Ctrl+8 did not navigate to the Customer surface"
        )

    def test_customer_brief_click_opens_drilldown(self, browser_context):
        """Clicking a customer in the morning brief must open the brief panel."""
        page, _, _ = browser_context
        page.evaluate("navTo('customer')")
        page.wait_for_selector("#surface-customer.active", timeout=5000)
        _wait_for_loading_done(page, "customer-morning", 20)
        # Click the first customer card in the morning brief
        page.click("#customer-morning > div")
        # The brief panel should become visible and load
        page.wait_for_selector("#customer-brief-panel:not([style*='display: none'])", timeout=5000)
        _wait_for_loading_done(page, "customer-brief-body", 20)
        text = page.text_content("#customer-brief-body")
        assert "Loading" not in text, "Customer brief body still loading after click"
        # Should contain a recommended outcome
        assert "Recommended outcome" in text or "recommendation" in text.lower(), (
            f"Brief body missing recommendation: {text[:200]}"
        )

    def test_customer_ask_flow(self, browser_context):
        """Typing a question and pressing Enter must return an answer."""
        page, _, _ = browser_context
        page.evaluate("navTo('customer')")
        page.wait_for_selector("#surface-customer.active", timeout=5000)
        # Type a question
        ask_input = page.query_selector("#customer-ask-input")
        assert ask_input is not None, "Customer ask input not found"
        ask_input.fill("Why is Initech slowing down?")
        ask_input.press("Enter")
        # Answer should appear
        page.wait_for_selector("#customer-ask-answer:not([style*='display: none'])", timeout=10000)
        import time as _t
        for _ in range(20):
            text = page.text_content("#customer-ask-text") or ""
            if text and "Thinking" not in text:
                break
            _t.sleep(0.5)
        text = page.text_content("#customer-ask-text")
        assert text and "Thinking" not in text, "Ask did not return an answer"
        assert "Initech" in text, f"Answer should mention Initech: {text[:200]}"

    def test_customer_morning_brief_has_one_click_actions(self, browser_context):
        """Each morning brief card must have one-click action buttons (Open/Ask/Simulate)."""
        page, _, _ = browser_context
        page.evaluate("navTo('customer')")
        page.wait_for_selector("#surface-customer.active", timeout=5000)
        _wait_for_loading_done(page, "customer-morning", 20)
        # Each card should have buttons with aria-labels
        buttons = page.query_selector_all("#customer-morning button[aria-label]")
        assert len(buttons) >= 3, (
            f"Expected >= 3 one-click action buttons in morning brief, got {len(buttons)}"
        )

    def test_customer_surface_touch_tap(self, browser_context):
        """The Customer Judgment surface must respond to touch events (tap).

        The master prompt explicitly required Touch testing. Playwright's
        page.tap() simulates a touch tap on an element. We verify that tapping
        a customer card in the morning brief opens the brief panel — the same
        behavior as a mouse click.
        """
        page, _, _ = browser_context
        # Navigate to home first to reset state from prior tests
        page.evaluate("navTo('home')")
        page.wait_for_selector("#surface-home.active", timeout=5000)
        # Now navigate to customer
        page.evaluate("navTo('customer')")
        page.wait_for_selector("#surface-customer.active", timeout=5000)
        _wait_for_loading_done(page, "customer-morning", 20)
        # Wait for the morning brief to stabilize (prior tests may have
        # triggered a re-render). Re-query the card right before tapping.
        import time as _t
        _t.sleep(0.5)
        first_card = page.query_selector("#customer-morning > div")
        assert first_card is not None, "No customer card found to tap"
        # If the card is detached, wait and re-query once more
        try:
            first_card.tap()
        except Exception:
            _t.sleep(1.0)
            first_card = page.query_selector("#customer-morning > div")
            assert first_card is not None, "No customer card found after retry"
            first_card.tap()
        # The brief panel should become visible (same as click)
        page.wait_for_selector("#customer-brief-panel:not([style*='display: none'])", timeout=5000)
        _wait_for_loading_done(page, "customer-brief-body", 20)
        text = page.text_content("#customer-brief-body")
        assert "Loading" not in text, "Brief body still loading after touch tap"

    def test_customer_ask_input_touch_focus(self, browser_context):
        """The ask input must be focusable via touch and accept input."""
        page, _, _ = browser_context
        page.evaluate("navTo('customer')")
        page.wait_for_selector("#surface-customer.active", timeout=5000)
        ask_input = page.query_selector("#customer-ask-input")
        assert ask_input is not None, "Customer ask input not found"
        # Tap the input (touch focus)
        ask_input.tap()
        # Type a query
        ask_input.fill("Who influences Globex?")
        ask_input.press("Enter")
        # Answer should appear
        page.wait_for_selector("#customer-ask-answer:not([style*='display: none'])", timeout=10000)
        import time as _t
        for _ in range(20):
            text = page.text_content("#customer-ask-text") or ""
            if text and "Thinking" not in text:
                break
            _t.sleep(0.5)
        text = page.text_content("#customer-ask-text")
        assert text and "Thinking" not in text, "Ask did not return after touch + type"

    def test_customer_twin_scenario_button_touch(self, browser_context):
        """The twin scenario buttons must respond to touch taps."""
        page, _, _ = browser_context
        page.evaluate("navTo('customer')")
        page.wait_for_selector("#surface-customer.active", timeout=5000)
        # Wait for scenario buttons to load
        page.wait_for_selector("#customer-twin-scenarios button", timeout=10000)
        buttons = page.query_selector_all("#customer-twin-scenarios button")
        assert len(buttons) >= 3, f"Expected >= 3 twin scenario buttons, got {len(buttons)}"
        # Tap the first scenario button (touch)
        buttons[0].tap()
        # The form should appear
        page.wait_for_selector("#customer-twin-form:not([style*='display: none'])", timeout=5000)
        form_text = page.text_content("#customer-twin-form")
        assert form_text and "Scenario:" in form_text, "Twin form did not open after touch tap"

    def test_navigate_to_simulator(self, browser_context):
        page, _, _ = browser_context
        page.evaluate("navTo('simulator')")
        page.wait_for_selector("#surface-simulator.active", timeout=5000)
        page.wait_for_selector("#simulator-scenario", timeout=15000)
        _wait_for_loading_done(page, "simulator-scenario", 20)
        text = page.text_content("#simulator-scenario")
        assert "Loading" not in text

    def test_navigate_to_eng_signals(self, browser_context):
        page, _, _ = browser_context
        page.evaluate("navTo('eng-signals')")
        page.wait_for_selector("#surface-eng-signals.active", timeout=5000)
        _wait_for_loading_done(page, "eng-signals-list", 20)
        text = page.text_content("#eng-signals-list")
        assert "Loading" not in text

    def test_breadcrumbs_update(self, browser_context):
        page, _, _ = browser_context
        page.evaluate("navTo('home')")
        page.wait_for_selector("#surface-home.active", timeout=5000)
        bc = page.text_content("#bc-page")
        assert bc == "Home"


class TestAskFlow:
    def test_ask_returns_real_answer(self, browser_context):
        page, _, _ = browser_context
        page.evaluate("navTo('ask')")
        page.wait_for_selector("#surface-ask.active", timeout=5000)
        page.fill("#ask-input", "bottleneck")
        page.press("#ask-input", "Enter")
        # Wait for the answer to load (not the loading state)
        import time as _t
        for _ in range(60):
            _t = page.text_content("#ask-answer-text") or ""
            if "Asking the OEM" not in _t and _t:
                break
            _t_sleep = __import__('time').sleep
            _t_sleep(0.5)
        text = page.text_content("#ask-answer-text")
        assert "Asking the OEM" not in text, "Still loading"
        assert len(text) > 10, f"Answer too short: {text}"
        conf = page.text_content("#ask-confidence")
        assert "Confidence" in conf

    def test_autocomplete_appears(self, browser_context):
        page, _, _ = browser_context
        page.evaluate("navTo('ask')")
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

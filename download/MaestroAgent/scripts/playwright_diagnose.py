"""
Playwright UI diagnostic — comprehensive frontend audit.

Starts the Maestro server, opens the browser, and tests every UI surface
the external auditor flagged. Captures screenshots + console errors +
network failures for each page.
"""
import os
import sys
import json
import time
import subprocess
import signal
from pathlib import Path

os.environ["MAESTRO_LOCAL_DEV"] = "true"
os.environ["MAESTRO_DEMO_SEED"] = "true"
os.environ["MAESTRO_APP_DIR"] = str(Path(__file__).resolve().parents[1])

# Start the server in background
print("=== Starting Maestro server ===")
proc = subprocess.Popen(
    [sys.executable, "-c", """
import os, sys
os.environ['MAESTRO_LOCAL_DEV'] = 'true'
os.environ['MAESTRO_DEMO_SEED'] = 'true'
os.environ['MAESTRO_APP_DIR'] = '""" + os.environ['MAESTRO_APP_DIR'] + """'
import uvicorn
from maestro_api.main import create_app
app = create_app(db_path=':memory:')
uvicorn.run(app, host='127.0.0.1', port=8765, log_level='warning')
"""],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    preexec_fn=os.setsid,
)

print("Waiting for server to start...")
time.sleep(5)

try:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        console_errors = []
        network_failures = []
        page.on("console", lambda msg: console_errors.append(f"[{msg.type}] {msg.text}") if msg.type in ("error", "warning") else None)
        page.on("requestfailed", lambda req: network_failures.append(f"{req.method} {req.url} - {req.failure}"))

        results = {}

        # TEST 1: Home page loads
        print("\n=== TEST 1: Home page loads ===")
        try:
            response = page.goto("http://127.0.0.1:8765/", wait_until="networkidle", timeout=15000)
            results["home_loads"] = {
                "status": response.status,
                "title": page.title(),
                "has_bundle": "bundle.min.js" in page.content(),
                "script_count": page.content().count("<script"),
            }
            print(f"  Status: {response.status}")
            print(f"  Title: {page.title()}")
            print(f"  Has bundle: {results['home_loads']['has_bundle']}")
            page.screenshot(path="/home/z/maestro_home.png")
            print(f"  Screenshot saved")
        except Exception as e:
            results["home_loads"] = {"error": str(e)}
            print(f"  ERROR: {e}")

        # TEST 2: Sidebar navigation
        print("\n=== TEST 2: Sidebar navigation ===")
        try:
            sidebar_links = page.query_selector_all("[data-surface]")
            results["sidebar"] = {
                "link_count": len(sidebar_links),
                "surfaces": [l.get_attribute("data-surface") for l in sidebar_links],
            }
            print(f"  Sidebar links: {len(sidebar_links)}")
            for l in sidebar_links:
                print(f"    data-surface: {l.get_attribute('data-surface')}")
        except Exception as e:
            results["sidebar"] = {"error": str(e)}
            print(f"  ERROR: {e}")

        # TEST 3: Onboarding flow (C-001 fix verify)
        print("\n=== TEST 3: Onboarding Screen 2 (C-001 fix verify) ===")
        try:
            page.goto("http://127.0.0.1:8765/onboarding", wait_until="networkidle", timeout=10000)
            time.sleep(1)
            onboarding_visible = page.query_selector(".onboarding-screen") is not None
            print(f"  Onboarding visible: {onboarding_visible}")

            if onboarding_visible:
                name_input = page.query_selector("#onboard-name")
                name_btn = page.query_selector("#onboard-name-btn")
                if name_input and name_btn:
                    name_input.fill("Test CEO")
                    time.sleep(0.5)
                    btn_disabled = name_btn.get_attribute("disabled")
                    print(f"  After typing 'Test CEO': button disabled = {btn_disabled}")
                    name_input.fill("")
                    time.sleep(0.5)
                    btn_disabled_empty = name_btn.get_attribute("disabled")
                    print(f"  After clearing: button disabled = {btn_disabled_empty}")
                    results["onboarding"] = {
                        "input_exists": True,
                        "button_exists": True,
                        "disabled_after_typing": btn_disabled,
                        "disabled_after_clearing": btn_disabled_empty,
                        "c001_fixed": btn_disabled != "true" and btn_disabled_empty == "true",
                    }
                    page.screenshot(path="/home/z/maestro_onboarding.png")
                else:
                    results["onboarding"] = {"error": "Name input or button not found"}
                    print("  Name input or button not found")
            else:
                results["onboarding"] = {"error": "Onboarding screen not visible"}
                print("  Onboarding screen not visible (may redirect to app)")
        except Exception as e:
            results["onboarding"] = {"error": str(e)}
            print(f"  ERROR: {e}")

        # TEST 4: Navigate to Today surface
        print("\n=== TEST 4: Today surface ===")
        try:
            page.goto("http://127.0.0.1:8765/", wait_until="networkidle", timeout=10000)
            time.sleep(2)
            today_link = page.query_selector('[data-surface="today"]')
            if today_link:
                today_link.click()
                time.sleep(2)
                results["today"] = {"clicked": True, "content_visible": len(page.content()) > 1000}
                page.screenshot(path="/home/z/maestro_today.png")
                print(f"  Clicked Today, content length: {len(page.content())}")
            else:
                results["today"] = {"error": "Today link not found"}
                print("  Today link not found")
        except Exception as e:
            results["today"] = {"error": str(e)}
            print(f"  ERROR: {e}")

        # TEST 5: Ask surface
        print("\n=== TEST 5: Ask surface ===")
        try:
            ask_link = page.query_selector('[data-surface="ask-v2"]')
            if ask_link:
                ask_link.click()
                time.sleep(2)
                ask_input = page.query_selector("#ask-input, .ask-input, [placeholder*='ask']") is not None
                results["ask"] = {"clicked": True, "input_exists": ask_input}
                page.screenshot(path="/home/z/maestro_ask.png")
                print(f"  Clicked Ask, input exists: {ask_input}")
            else:
                results["ask"] = {"error": "Ask link not found"}
                print("  Ask link not found")
        except Exception as e:
            results["ask"] = {"error": str(e)}
            print(f"  ERROR: {e}")

        # TEST 6: Autocomplete
        print("\n=== TEST 6: Autocomplete ===")
        try:
            ac_input = page.query_selector("#ask-input, .ask-input, input[placeholder*='ask'], input[placeholder*='type']")
            if ac_input:
                for q in ["we should", "hire", "payments", "security", "oauth"]:
                    ac_input.fill("")
                    time.sleep(0.3)
                    ac_input.fill(q)
                    time.sleep(0.8)
                    dropdown = page.query_selector(".autocomplete-results, .suggestions, [class*='autocomplete'], [class*='suggest']")
                    has_results = dropdown is not None
                    if not results.get("autocomplete"):
                        results["autocomplete"] = {}
                    results["autocomplete"][q] = has_results
                    print(f"  Query '{q}': dropdown = {has_results}")
            else:
                results["autocomplete"] = {"error": "Autocomplete input not found"}
                print("  Autocomplete input not found")
        except Exception as e:
            results["autocomplete"] = {"error": str(e)}
            print(f"  ERROR: {e}")

        # TEST 7: Console errors
        print("\n=== TEST 7: Console errors ===")
        results["console_errors"] = console_errors[:20]
        results["network_failures"] = network_failures[:10]
        print(f"  Console errors/warnings: {len(console_errors)}")
        for err in console_errors[:10]:
            print(f"    {err[:150]}")
        print(f"  Network failures: {len(network_failures)}")
        for fail in network_failures[:5]:
            print(f"    {fail[:150]}")

        # TEST 8: Keyboard navigation (a11y)
        print("\n=== TEST 8: Keyboard navigation ===")
        try:
            page.goto("http://127.0.0.1:8765/", wait_until="networkidle", timeout=10000)
            time.sleep(1)
            page.keyboard.press("Tab")
            time.sleep(0.3)
            focused = page.evaluate("document.activeElement ? document.activeElement.tagName + '.' + (document.activeElement.className || '') : 'none'")
            results["keyboard_nav"] = {"first_focus": focused}
            print(f"  First Tab focus: {focused}")
            for i in range(5):
                page.keyboard.press("Tab")
                time.sleep(0.2)
            focused2 = page.evaluate("document.activeElement ? document.activeElement.tagName + '.' + (document.activeElement.className || '') : 'none'")
            results["keyboard_nav"]["after_5_tabs"] = focused2
            print(f"  After 5 Tabs: {focused2}")
        except Exception as e:
            results["keyboard_nav"] = {"error": str(e)}
            print(f"  ERROR: {e}")

        # TEST 9: Dashboard widgets
        print("\n=== TEST 9: Dashboard widgets ===")
        try:
            page.goto("http://127.0.0.1:8765/", wait_until="networkidle", timeout=10000)
            time.sleep(2)
            widgets = page.query_selector_all("[class*='card'], [class*='widget'], [data-widget]")
            results["dashboard"] = {"widget_count": len(widgets)}
            print(f"  Widgets found: {len(widgets)}")
            page.screenshot(path="/home/z/maestro_dashboard.png")
        except Exception as e:
            results["dashboard"] = {"error": str(e)}
            print(f"  ERROR: {e}")

        # SUMMARY
        print("\n=== DIAGNOSTIC SUMMARY ===")
        print(json.dumps(results, indent=2, default=str))

        browser.close()

except Exception as e:
    print(f"FATAL: {e}")
finally:
    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    proc.wait()
    print("\n=== Server stopped ===")

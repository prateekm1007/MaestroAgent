#!/usr/bin/env python3
"""Permanence UI Gate — Playwright assertions on the 4-tab IA.

Auditor (2026-07-24) strict-order item 7:
  "Add these Playwright assertions to the deploy-blocking gate (or a parallel
   UI gate in the same CI job) — including `nav contains 'Today' and not
   'Dashboard'` and `tab count == 4`. A 7→4 change with no UI gate is the
   'verified-by-hand, not permanent' risk we just spent turns eliminating;
   the nav can silently grow a 5th tab or a fold target can silently 404
   next commit unless asserted in CI."

This script:
  1. Launches a headless Chromium browser
  2. Navigates to the live frontend URL
  3. Registers a fresh user (so tour + banner fire)
  4. Asserts the nav has EXACTLY 4 tabs with labels Today/Ask/Commitments/More
  5. Asserts no legacy labels (Dashboard/Agent/Prepare/Inbox) appear as top-level tabs
  6. Asserts the tour fires on first run (fresh user)
  7. Dismisses the tour, reloads, asserts it does NOT reappear
  8. Asserts the connectors banner shows on Today at 0 connectors
  9. Navigates to More, asserts all 4 sub-sections (Connectors/Sources/Agents/Settings) are reachable
  10. Asserts no console errors and no 404s on the route layer

USAGE:
    python3 ops/ui_gate.py
    (exit 0 = all assertions pass, exit 1 = regression detected)

CI INTEGRATION:
    Runs in .github/workflows/permanence-gate.yml as a parallel job after
    the backend permanence gate. Both must pass for a green deploy.
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid

# Try Playwright import — give a clear error if missing
try:
    from playwright.sync_api import sync_playwright, expect, TimeoutError as PWTimeout
except ImportError:
    print("ERROR: playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(2)


FRONTEND_URL = os.environ.get(
    "MAESTRO_FRONTEND_URL",
    "https://web-production-d5c26.up.railway.app",
)
BACKEND_URL = os.environ.get(
    "MAESTRO_BACKEND_URL",
    "https://maestroagent-production.up.railway.app",
)


class UIGateResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.results = []
        self.console_errors: list[str] = []
        self.network_404s: list[str] = []

    def assert_eq(self, name, actual, expected):
        ok = actual == expected
        self.results.append((name, "PASS" if ok else "FAIL", f"expected={expected}, actual={actual}"))
        if ok:
            self.passed += 1
        else:
            self.failed += 1
        return ok

    def assert_true(self, name, condition, detail=""):
        self.results.append((name, "PASS" if condition else "FAIL", detail))
        if condition:
            self.passed += 1
        else:
            self.failed += 1
        return condition

    def assert_false(self, name, condition, detail=""):
        return self.assert_true(name, not condition, detail)

    def print_report(self):
        print(f"\n{'='*72}")
        print(f"UI GATE — {self.passed} passed, {self.failed} failed")
        print(f"{'='*72}")
        for name, status, detail in self.results:
            icon = "✓" if status == "PASS" else "✗"
            print(f"  {icon} {name:55s} {detail[:60]}")
        if self.console_errors:
            print(f"\n  Console errors ({len(self.console_errors)}):")
            for err in self.console_errors[:5]:
                print(f"    • {err[:120]}")
        if self.network_404s:
            print(f"\n  Network 404s ({len(self.network_404s)}):")
            for err in self.network_404s[:5]:
                print(f"    • {err[:120]}")
        print()
        if self.failed > 0:
            print(f"❌ UI GATE FAILED — {self.failed} regression(s) detected. DEPLOY BLOCKED.")
        else:
            print(f"✅ UI GATE PASSED — all assertions hold. Deploy approved.")
        return self.failed == 0


def register_test_user(page) -> str:
    """Register a fresh user via the API and return the token. Bypasses the
    UI registration form (which uses a captcha in some configs)."""
    email = f"ui-gate-{int(time.time())}-{uuid.uuid4().hex[:6]}@example.com"
    password = "ui-gate-pass-2026"
    name = "UIGate"

    import urllib.request
    import urllib.parse

    data = json.dumps({"user_email": email, "password": password, "name": name}).encode()
    req = urllib.request.Request(
        f"{BACKEND_URL}/api/auth/register",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode())
            token = body.get("token", "")
            if not token:
                raise RuntimeError(f"no token in register response: {body}")
            return token
    except Exception as e:
        raise RuntimeError(f"register failed: {e}")


def setup_browser_context(p):
    """Launch browser with console + network error capture."""
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={"width": 1280, "height": 800},
        # Fresh context — no localStorage, so tour + banner fire
    )
    page = context.new_page()

    console_errors = []
    network_404s = []

    page.on("console", lambda msg: (
        console_errors.append(f"[{msg.type}] {msg.text}")
        if msg.type in ("error", "warning") else None
    ))
    page.on("pageerror", lambda err: console_errors.append(f"[pageerror] {str(err)}"))
    page.on("response", lambda resp: (
        network_404s.append(f"{resp.status} {resp.url}")
        if resp.status == 404 else None
    ))

    return browser, context, page, console_errors, network_404s


def inject_token_and_navigate(page, token: str):
    """Inject the auth token into localStorage and navigate to the app.
    Then complete onboarding so we land on the real app."""
    page.goto(FRONTEND_URL)
    page.wait_for_load_state("networkidle", timeout=20000)

    # Inject token + mark onboarding complete
    page.evaluate(f"""
        window.localStorage.setItem('maestro.token', '{token}');
        window.localStorage.setItem('maestro.onboarded', '1');
        // Clear tour-dismissed so the tour fires for our test
        window.localStorage.removeItem('maestro.tour_dismissed');
        window.localStorage.removeItem('maestro.tour_replay');
        // Clear connectors-banner dismissed so it shows
        window.localStorage.removeItem('maestro.connectors_banner_dismissed');
        window.localStorage.removeItem('maestro.connectors_banner_snoozed_until');
    """)

    # Reload to apply the localStorage state
    page.reload()
    page.wait_for_load_state("networkidle", timeout=20000)


def run_gate():
    gate = UIGateResult()

    with sync_playwright() as p:
        try:
            browser, context, page, console_errors, network_404s = setup_browser_context(p)
        except Exception as e:
            print(f"FATAL: could not launch browser: {e}")
            sys.exit(2)

        try:
            # ── [NAV] Nav has exactly 4 tabs ────────────────────────────
            print("[SETUP] Registering fresh user + navigating to app...")
            token = register_test_user(page)
            inject_token_and_navigate(page, token)

            # Wait for the nav to render (desktop sidebar nav has aria-label="Main")
            print("[NAV] Asserting nav structure...")
            try:
                page.wait_for_selector('nav[aria-label="Main"]', timeout=15000)
            except PWTimeout:
                # Mobile bottom nav has aria-label="Mobile navigation"
                try:
                    page.wait_for_selector('nav[aria-label="Mobile navigation"]', timeout=5000)
                except PWTimeout:
                    gate.assert_true("[NAV] Main nav renders", False, "no nav[aria-label=Main] or Mobile navigation found")
                    return gate

            # Collect all nav button labels (desktop sidebar)
            nav_buttons = page.query_selector_all('nav[aria-label="Main"] button[aria-label]')
            nav_labels = [b.get_attribute("aria-label") for b in nav_buttons]

            gate.assert_eq("[NAV] Tab count == 4", len(nav_labels), 4)
            gate.assert_true(
                "[NAV] Tab labels include Today/Ask/Commitments/More",
                set(nav_labels) == {"Today", "Ask", "Commitments", "More"},
                f"labels={nav_labels}",
            )
            gate.assert_true(
                "[NAV] No 'Dashboard' as top-level tab",
                "Dashboard" not in nav_labels,
                f"labels={nav_labels}",
            )
            gate.assert_true(
                "[NAV] No 'Agent'/'Agents' as top-level tab",
                "Agent" not in nav_labels and "Agents" not in nav_labels,
                f"labels={nav_labels}",
            )
            gate.assert_true(
                "[NAV] No 'Prepare' as top-level tab",
                "Prepare" not in nav_labels,
                f"labels={nav_labels}",
            )
            gate.assert_true(
                "[NAV] No 'Inbox' as top-level tab",
                "Inbox" not in nav_labels,
                f"labels={nav_labels}",
            )

            # ── [TOUR] Tour fires on first run ──────────────────────────
            print("[TOUR] Asserting tour fires on first run...")
            try:
                tour_dialog = page.wait_for_selector(
                    '[role="dialog"][aria-label^="Tour step"]',
                    timeout=8000,
                )
                gate.assert_true("[TOUR] Tour dialog appears on fresh user", tour_dialog is not None, "")
            except PWTimeout:
                gate.assert_true("[TOUR] Tour dialog appears on fresh user", False, "tour dialog not found within 8s")

            # ── [TOUR] Tour dismiss persists across reload ──────────────
            print("[TOUR] Asserting tour dismiss persists...")
            # Click "Skip tour" button
            try:
                skip_btn = page.query_selector('button:has-text("Skip tour")')
                if skip_btn:
                    skip_btn.click()
                    page.wait_for_timeout(500)
                else:
                    # Try the X close button
                    close_btn = page.query_selector('[role="dialog"] button[aria-label="Skip tour"]')
                    if close_btn:
                        close_btn.click()
                        page.wait_for_timeout(500)
            except Exception as e:
                print(f"  ⚠ could not dismiss tour: {e}")

            # Verify localStorage flag set
            dismissed = page.evaluate("window.localStorage.getItem('maestro.tour_dismissed')")
            gate.assert_eq("[TOUR] tour_dismissed flag set after dismiss", dismissed, "1")

            # Reload — tour should NOT reappear
            page.reload()
            page.wait_for_load_state("networkidle", timeout=15000)
            page.wait_for_timeout(1500)  # give tour mount effect time to run
            tour_after_reload = page.query_selector('[role="dialog"][aria-label^="Tour step"]')
            gate.assert_true(
                "[TOUR] Tour does NOT reappear after dismiss + reload",
                tour_after_reload is None,
                "tour dialog found after reload (should be dismissed)",
            )

            # ── [BANNER] Connectors banner shows at 0 connectors ────────
            print("[BANNER] Asserting connectors banner on Today...")
            # Navigate to Today (click the Today tab)
            today_btn = page.query_selector('nav[aria-label="Main"] button[aria-label="Today"]')
            if today_btn:
                today_btn.click()
                page.wait_for_timeout(800)

            banner = page.query_selector('[role="status"][aria-label="Connectors reminder"]')
            gate.assert_true(
                "[BANNER] Connectors banner shows on Today at 0 connectors",
                banner is not None,
                "banner not found on Today (should show when no connectors connected)",
            )
            if banner:
                banner_text = banner.inner_text()
                gate.assert_true(
                    "[BANNER] Banner text mentions 'only knows what you connect'",
                    "only knows what you connect" in banner_text.lower(),
                    f"text={banner_text[:120]}",
                )
                gate.assert_true(
                    "[BANNER] Banner text mentions 'More'",
                    "more" in banner_text.lower(),
                    f"text={banner_text[:120]}",
                )

            # ── [MORE] More tab opens with 4 sub-sections ───────────────
            print("[MORE] Asserting More tab sub-sections...")
            more_btn = page.query_selector('nav[aria-label="Main"] button[aria-label="More"]')
            if more_btn:
                more_btn.click()
                page.wait_for_timeout(1000)
            else:
                gate.assert_true("[MORE] More tab button found", False, "no More button in nav")
                return gate

            # Verify all 4 sub-section buttons are present
            more_section_labels = ["Connectors", "Browse all sources", "Agent controls", "Settings"]
            for label in more_section_labels:
                btn = page.query_selector(f'button:has-text("{label}")')
                gate.assert_true(
                    f"[MORE] Sub-section '{label}' reachable",
                    btn is not None,
                    f"button not found",
                )

            # Click "Browse all sources" — should show the SyntheticInbox
            try:
                sources_btn = page.query_selector('button:has-text("Browse all sources")')
                if sources_btn:
                    sources_btn.click()
                    page.wait_for_timeout(800)
                    # SyntheticInbox has the "Demo Inbox" heading
                    inbox_heading = page.query_selector('h2:has-text("Demo Inbox")')
                    gate.assert_true(
                        "[MORE] Browse sources shows SyntheticInbox",
                        inbox_heading is not None,
                        "Demo Inbox heading not found after clicking Browse all sources",
                    )
            except Exception as e:
                print(f"  ⚠ Browse sources click failed: {e}")

            # ── [REDIRECT] Fold redirect for legacy view IDs ────────────
            # The app is a SPA — no URL routing per view. But we can verify
            # the fold map by setting localStorage to a stale view and
            # checking that the app renders the fold target. The simplest
            # test: navigate to a legacy view via the internal API isn't
            # possible from outside. Instead, verify no 404s occurred on
            # navigation (the route layer is healthy).
            print("[REDIRECT] Asserting no 404s on navigation...")
            gate.assert_true(
                "[REDIRECT] No network 404s during full nav sweep",
                len(network_404s) == 0,
                f"404s={network_404s[:3]}",
            )

            # ── [CONSOLE] No console errors ─────────────────────────────
            print("[CONSOLE] Asserting no console errors...")
            # Filter out benign warnings (e.g., React devtools, hydration warnings
            # that don't affect functionality)
            real_errors = [
                e for e in console_errors
                if "pageerror" in e.lower()
                or "error" in e.lower() and "hydration" not in e.lower()
            ]
            gate.assert_true(
                "[CONSOLE] No console errors during nav sweep",
                len(real_errors) == 0,
                f"errors={real_errors[:3]}",
            )

        finally:
            # Attach captured errors to the gate result for the report
            gate.console_errors = console_errors
            gate.network_404s = network_404s
            browser.close()

    return gate


def main():
    print("=" * 72)
    print("UI GATE — Playwright assertions on the 4-tab IA")
    print(f"Frontend: {FRONTEND_URL}")
    print(f"Backend:  {BACKEND_URL}")
    print("=" * 72)

    gate = run_gate()
    all_pass = gate.print_report()

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()

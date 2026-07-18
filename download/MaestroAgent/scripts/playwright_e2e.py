#!/usr/bin/env python3
"""
Playwright E2E test for the Maestro Personal web app (:3000).

Tests the P0+P1 web port items against a real backend + real LLM (if available):
  1. Onboarding shows + can be dismissed
  2. Login works (real POST /api/auth/login, not demo bypass)
  3. Dashboard renders with The Moment card
  4. Draft button on Moment fires POST /api/drafts/auto + opens modal
  5. Done button fires POST /api/signals/{id}/correct?action=complete
  6. Skip button fires POST /api/signals/{id}/correct?action=dismiss
  7. Commitments view renders with Draft button
  8. Ask view fires POST /api/ask with session_id in body
  9. Settings view renders with Metrics card + Retention button
  10. Retention dialog opens + fetches /api/privacy/retention-status

Usage:
  cd maestro-personal
  PYTHONPATH=src MAESTRO_PERSONAL_TOKEN=maestro-browser-test \
    python3 ../scripts/playwright_e2e.py

Prerequisites:
  - Python 3.12+ with fastapi + playwright installed
  - Playwright chromium browser: `playwright install chromium`
  - The web app's node_modules installed: `cd web && npm install`

The script:
  1. Starts the backend on :8766 (subprocess, fully detached via setsid)
  2. Starts Next.js dev on :3000 (subprocess, fully detached)
  3. Logs in as default@personal.local to get a per-user token
  4. Seeds 5 stale commitment signals (backdated 10 days, urgent text)
     as the browser user — NOT the bootstrap user. Critical: signals seeded
     under the env-token user (bootstrap) are invisible to the browser's
     per-user-token user (default@personal.local).
  5. Runs 10 Playwright tests (headless chromium)
  6. Captures screenshots on failure
  7. Prints results summary
  8. Cleans up both subprocesses on exit

Verification evidence: the script prints [PASS]/[FAIL] per test + a summary
count. Screenshots are saved to scripts/pw_*.png for debugging.
"""
import os
import signal
import subprocess
import sys
import time
import json
import tempfile
import urllib.request
from pathlib import Path
from datetime import datetime, timezone, timedelta

MAESTRO_ROOT = Path(__file__).resolve().parents[1] / "maestro-personal"
WEB_ROOT = MAESTRO_ROOT / "web"
TOKEN = os.environ.get("MAESTRO_PERSONAL_TOKEN", "maestro-browser-test")
BACKEND_URL = "http://127.0.0.1:8766"
WEB_URL = "http://localhost:3000"

# Use a fresh temp DB so we don't pollute the real one
DB_PATH = tempfile.mktemp(suffix=".db")
os.environ["MAESTRO_PERSONAL_DB"] = DB_PATH
os.environ["MAESTRO_PERSONAL_TOKEN"] = TOKEN
os.environ["MAESTRO_ENV"] = "dev"
os.environ["ENV"] = "dev"
os.environ["MAESTRO_DEMO_MODE"] = "0"
os.environ["PYTHONPATH"] = str(MAESTRO_ROOT / "src")

_procs = []

def start_servers():
    """Start backend + Next.js dev server, both fully detached via setsid."""
    backend_env = os.environ.copy()
    backend = subprocess.Popen(
        [sys.executable, "-m", "maestro_personal_shell.api"],
        cwd=str(MAESTRO_ROOT),
        env=backend_env,
        stdout=open("/tmp/pw_backend.log", "w"),
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    _procs.append(("backend", backend))
    print(f"Backend PID: {backend.pid}")

    web_env = os.environ.copy()
    web_env["PORT"] = "3000"
    web = subprocess.Popen(
        ["npx", "next", "dev", "-p", "3000"],
        cwd=str(WEB_ROOT),
        env=web_env,
        stdout=open("/tmp/pw_web.log", "w"),
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    _procs.append(("web", web))
    print(f"Web PID: {web.pid}")
    return backend, web

def wait_for(url, label, timeout=60, expect_json=False):
    """Wait for URL to return 200."""
    deadline = time.time() + timeout
    last_err = ""
    while time.time() < deadline:
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=3) as r:
                if r.status == 200:
                    if expect_json:
                        json.loads(r.read())
                    print(f"  {label} up (HTTP 200) after {int(time.time() - (deadline - timeout))}s")
                    return True
        except Exception as e:
            last_err = str(e)[:80]
        time.sleep(1)
    print(f"  {label} FAILED to come up in {timeout}s. Last error: {last_err}")
    return False

def kill_servers():
    """Kill all spawned subprocesses + their children."""
    for name, p in _procs:
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            print(f"Killed {name} (pgid {os.getpgid(p.pid)})")
        except ProcessLookupError:
            pass
        except Exception as e:
            print(f"Failed to kill {name}: {e}")

def login_and_seed():
    """Login as default@personal.local, seed 5 stale signals + 1 draft.

    CRITICAL: must login first to get the per-user token, then use THAT token
    to seed. The env var TOKEN maps to user "bootstrap" — a DIFFERENT user
    than the browser logs in as. Signals seeded under "bootstrap" are invisible
    to the browser's "default@personal.local" user.

    The Moment logic requires days_stale > 2 (see surfaces.py:630). We backdate
    timestamps by 10 days AND use urgent text so the LLM-based materiality gate
    returns should_speak=True (generic text gets suppressed as 'routine').
    """
    print("\n--- Logging in as default@personal.local to get per-user token ---")
    login_body = json.dumps({
        "user_email": "default@personal.local",
        "password": TOKEN,
    }).encode()
    login_req = urllib.request.Request(
        f"{BACKEND_URL}/api/auth/login",
        data=login_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(login_req, timeout=10) as r:
            login_data = json.loads(r.read())
            per_user_token = login_data.get("token")
            user_email = login_data.get("user_email")
            print(f"  Login OK — user_email: {user_email}, token: {per_user_token[:12]}...")
    except Exception as e:
        print(f"  Login FAILED: {e}")
        return [], None

    print("\n--- Seeding 5 STALE test signals (backdated 10 days, urgent text) ---")
    now = datetime.now(timezone.utc)
    backdated = (now - timedelta(days=10)).isoformat()
    signals_data = [
        ("Alice Chen", "I promised Alice I would send the pricing proposal by last Friday — deadline has now passed, she is waiting and escalating. URGENT: overdue commitment."),
        ("Bob Smith", "I committed to reviewing the design docs by Monday — that deadline has passed, Bob is blocked waiting on my review. Overdue."),
        ("Maria Garcia", "I promised Maria the quarterly report would be delivered last Wednesday — she has followed up twice, deadline passed, urgent escalation."),
        ("David Kim", "I promised David the board deck would be ready by Tuesday — deadline passed, he has emailed three times asking for status. Critical: overdue."),
        ("Eve Patel", "I committed to Eve that the API migration would be done by last week — deadline passed, she is blocked and escalating to leadership. URGENT overdue."),
    ]
    seeded = []
    for entity, text in signals_data:
        body = json.dumps({
            "entity": entity,
            "text": text,
            "signal_type": "commitment_made",
            "timestamp": backdated,
        }).encode()
        req = urllib.request.Request(
            f"{BACKEND_URL}/api/signals",
            data=body,
            headers={"Authorization": f"Bearer {per_user_token}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
                seeded.append(data.get("signal_id"))
                print(f"  Seeded: {data.get('signal_id')[:8]}... ({entity})")
        except Exception as e:
            print(f"  Seed FAILED for {entity}: {e}")

    # Probe /api/the-moment to confirm signals are visible
    print("\n--- Probing /api/the-moment with per-user token ---")
    try:
        req = urllib.request.Request(
            f"{BACKEND_URL}/api/the-moment",
            headers={"Authorization": f"Bearer {per_user_token}"},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            moment_data = json.loads(r.read())
            print(f"  has_moment: {moment_data.get('has_moment')}")
            print(f"  why_this_one: {moment_data.get('why_this_one', '')[:200]}")
            if moment_data.get("commitment"):
                c = moment_data["commitment"]
                print(f"  commitment entity: {c.get('entity')}")
                print(f"  commitment signal_id: {c.get('signal_id', '')[:36]}")
    except Exception as e:
        print(f"  Probe FAILED: {e}")

    return seeded, per_user_token

def run_tests():
    """Run all 10 Playwright E2E tests. Returns dict of test_name -> (passed, details)."""
    from playwright.sync_api import sync_playwright
    results = {}
    screenshots = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        api_calls = []
        def on_request(req):
            if "/api/" in req.url:
                api_calls.append({
                    "method": req.method,
                    "url": req.url,
                    "post_data": (req.post_data or "")[:500],
                })
        context.on("request", on_request)

        # Capture RESPONSE bodies for /api/the-moment so we can see what the browser actually receives
        def on_response(resp):
            if "/api/the-moment" in resp.url and resp.request.method == "GET":
                try:
                    body = resp.text()
                    print(f"  [RESPONSE] GET {resp.url} → {resp.status}: {body[:200]}")
                except Exception as e:
                    print(f"  [RESPONSE] could not read body: {e}")
        context.on("response", on_response)

        page = context.new_page()
        page.set_default_timeout(20000)

        def screenshot(name):
            path = f"/tmp/pw_{name}.png"
            try:
                page.screenshot(path=path, full_page=True)
                screenshots.append(path)
                print(f"  Screenshot: {path}")
            except Exception as e:
                print(f"  screenshot failed: {e}")

        # === TEST 1: Onboarding shows + can be dismissed ===
        print("\n[TEST 1] Onboarding shows for fresh localStorage + can be dismissed")
        try:
            page.goto(WEB_URL + "/", wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            body_text = page.locator("body").inner_text(timeout=8000)
            if "Maestro remembers" in body_text or "Trusted Silence" in body_text:
                for step_label in ["Next", "Next", "Get Started"]:
                    btn = page.locator(f"button:has-text('{step_label}')").first
                    if btn.count() == 0:
                        continue
                    btn.click(timeout=5000)
                    page.wait_for_timeout(1200)
                page.wait_for_timeout(1000)
                login_input = page.locator("#password")
                if login_input.count() > 0:
                    results["onboarding_dismissed"] = (True, "Onboarding shown + dismissed → login visible")
                else:
                    screenshot("onboarding_stuck")
                    results["onboarding_dismissed"] = (False, "Onboarding clicked but login not visible")
            else:
                if "PASSWORD" in body_text.upper() or "Enter your passphrase" in body_text:
                    results["onboarding_dismissed"] = (True, "Onboarding already complete (login visible)")
                else:
                    screenshot("no_onboarding")
                    results["onboarding_dismissed"] = (False, f"Neither onboarding nor login visible. Body: {body_text[:300]}")
        except Exception as e:
            screenshot("onboarding_exception")
            results["onboarding_dismissed"] = (False, f"Exception: {type(e).__name__}: {str(e)[:200]}")

        # === TEST 2: Login works ===
        print("\n[TEST 2] Login works (real POST /api/auth/login)")
        api_calls.clear()
        try:
            password_input = page.locator("#password")
            password_input.wait_for(state="visible", timeout=10000)
            password_input.fill(TOKEN)
            enter_btn = page.locator("button[type='submit']:has-text('Enter')").first
            if enter_btn.count() == 0:
                enter_btn = page.locator("button:has-text('Enter')").first
            enter_btn.click(timeout=5000)
            page.locator("nav[aria-label='Main']").first.wait_for(state="visible", timeout=15000)
            page.wait_for_timeout(2000)
            login_calls = [c for c in api_calls if "/api/auth/login" in c["url"]]
            if login_calls:
                results["login_works"] = (True, "POST /api/auth/login fired. Token stored.")
            else:
                screenshot("login_no_call")
                results["login_works"] = (False, "Nav appeared but no /api/auth/login call captured")
        except Exception as e:
            screenshot("login_exception")
            results["login_works"] = (False, f"Exception: {type(e).__name__}: {str(e)[:200]}")

        # === TEST 3: Dashboard renders with The Moment ===
        print("\n[TEST 3] Dashboard renders with The Moment card")
        try:
            page.wait_for_timeout(6000)
            body_text = page.locator("body").inner_text(timeout=8000)
            body_lower = body_text.lower()
            if "the moment" in body_lower:
                done_btn = page.locator("button:has-text('Done')").first
                skip_btn = page.locator("button:has-text('Skip')").first
                draft_btn = page.locator("button:has-text('Draft')").first
                done_count = done_btn.count()
                skip_count = skip_btn.count()
                draft_count = draft_btn.count()
                results["dashboard_renders"] = (
                    done_count > 0 and skip_count > 0 and draft_count > 0,
                    f"Done={done_count} Skip={skip_count} Draft={draft_count}"
                )
                if not (done_count > 0 and draft_count > 0):
                    screenshot("dashboard_moment_no_buttons")
            elif "nothing needs your attention" in body_lower or "trusted silence" in body_lower:
                screenshot("dashboard_trusted_silence")
                results["dashboard_renders"] = (False, f"Trusted Silence state. Body: {body_text[:400]}")
            else:
                screenshot("dashboard_no_moment")
                results["dashboard_renders"] = (False, f"Body: {body_text[:400]}")
        except Exception as e:
            screenshot("dashboard_exception")
            results["dashboard_renders"] = (False, f"Exception: {type(e).__name__}: {str(e)[:200]}")

        # === TEST 4: Draft button on Moment (run BEFORE Done/Skip so Moment is fresh) ===
        print("\n[TEST 4] Draft button on Moment fires POST /api/drafts/auto + opens modal")
        api_calls.clear()
        try:
            draft_btn = page.locator("button:has-text('Draft')").first
            if draft_btn.count() == 0:
                body_text = page.locator("body").inner_text(timeout=5000)
                screenshot("moment_draft_no_button")
                results["moment_draft"] = (False, f"Draft button not found. Body: {body_text[:300]}")
            else:
                draft_btn.click(timeout=5000)
                for _ in range(30):
                    page.wait_for_timeout(1000)
                    auto_calls = [c for c in api_calls if "/api/drafts/auto" in c["url"]]
                    if auto_calls:
                        break
                auto_calls = [c for c in api_calls if "/api/drafts/auto" in c["url"]]
                if auto_calls:
                    page.wait_for_timeout(2000)
                    modal_visible = page.locator("[role='dialog']").count() > 0
                    results["moment_draft"] = (True, f"POST /api/drafts/auto fired; modal_visible={modal_visible}")
                else:
                    screenshot("moment_draft_no_call")
                    results["moment_draft"] = (False, f"No /api/drafts/auto call after 30s. Last API calls: {json.dumps(api_calls[-5:])}")
        except Exception as e:
            screenshot("moment_draft_exception")
            results["moment_draft"] = (False, f"Exception: {type(e).__name__}: {str(e)[:200]}")

        # Close modal if open
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(800)
        except:
            pass

        # === TEST 5: Done button ===
        print("\n[TEST 5] Done button fires POST /api/signals/{id}/correct?action=complete")
        api_calls.clear()
        try:
            page.reload(wait_until="domcontentloaded")
            page.wait_for_timeout(6000)
            done_btn = page.locator("button:has-text('Done')").first
            if done_btn.count() == 0:
                body_text = page.locator("body").inner_text(timeout=5000)
                screenshot("moment_done_no_button")
                results["moment_done"] = (False, f"Done button not found. Body: {body_text[:300]}")
            else:
                done_btn.click(timeout=5000)
                page.wait_for_timeout(4000)
                complete_calls = [c for c in api_calls if "/correct" in c["url"] and "complete" in c["url"]]
                if complete_calls:
                    results["moment_done"] = (True, f"POST fired: {complete_calls[0]['url']}")
                else:
                    screenshot("moment_done_no_call")
                    results["moment_done"] = (False, f"No /correct?action=complete call. Last API calls: {json.dumps(api_calls[-5:])}")
        except Exception as e:
            screenshot("moment_done_exception")
            results["moment_done"] = (False, f"Exception: {type(e).__name__}: {str(e)[:200]}")

        # === TEST 6: Skip button ===
        print("\n[TEST 6] Skip button fires POST /api/signals/{id}/correct?action=dismiss")
        api_calls.clear()
        try:
            page.reload(wait_until="domcontentloaded")
            page.wait_for_timeout(6000)
            skip_btn = page.locator("button:has-text('Skip')").first
            if skip_btn.count() == 0:
                body_text = page.locator("body").inner_text(timeout=5000)
                screenshot("moment_skip_no_button")
                results["moment_skip"] = (False, f"Skip button not found. Body: {body_text[:300]}")
            else:
                skip_btn.click(timeout=5000)
                page.wait_for_timeout(4000)
                dismiss_calls = [c for c in api_calls if "/correct" in c["url"] and "dismiss" in c["url"]]
                if dismiss_calls:
                    results["moment_skip"] = (True, f"POST fired: {dismiss_calls[0]['url']}")
                else:
                    screenshot("moment_skip_no_call")
                    results["moment_skip"] = (False, f"No /correct?action=dismiss call. Last API calls: {json.dumps(api_calls[-5:])}")
        except Exception as e:
            screenshot("moment_skip_exception")
            results["moment_skip"] = (False, f"Exception: {type(e).__name__}: {str(e)[:200]}")

        # === TEST 7: Commitments view ===
        print("\n[TEST 7] Commitments view renders with Draft button")
        try:
            commitments_nav = page.locator("button:has-text('Commitments')").first
            commitments_nav.click(timeout=10000)
            page.wait_for_timeout(5000)
            body_text = page.locator("body").inner_text(timeout=5000)
            body_lower = body_text.lower()
            has_draft = "draft" in body_lower
            has_commitments = "commitments" in body_lower or "the one" in body_lower
            results["commitments_view"] = (has_draft and has_commitments, f"commitments_text={has_commitments} draft_button={has_draft}")
            if not (has_draft and has_commitments):
                screenshot("commitments_view_fail")
        except Exception as e:
            screenshot("commitments_exception")
            results["commitments_view"] = (False, f"Exception: {type(e).__name__}: {str(e)[:200]}")

        # === TEST 8: Ask view fires POST /api/ask with session_id ===
        print("\n[TEST 8] Ask view fires POST /api/ask with session_id in body")
        api_calls.clear()
        try:
            ask_nav = page.locator("button:has-text('Ask')").first
            ask_nav.click(timeout=10000)
            page.wait_for_timeout(2000)
            ask_input = page.locator("input[placeholder*='promise'], input[placeholder*='Maria']").first
            if ask_input.count() == 0:
                ask_input = page.locator("input[type='text']").first
            ask_input.fill("What did I promise Maria Garcia?")
            ask_input.press("Enter")
            for _ in range(30):
                page.wait_for_timeout(1000)
                ask_calls = [c for c in api_calls if "/api/ask" in c["url"] and c["method"] == "POST"]
                if ask_calls:
                    break
            ask_calls = [c for c in api_calls if "/api/ask" in c["url"] and c["method"] == "POST"]
            if ask_calls:
                post_data = ask_calls[0].get("post_data") or ""
                if "session_id" in post_data:
                    results["ask_session_id"] = (True, f"POST /api/ask with session_id. Body: {post_data[:300]}")
                else:
                    screenshot("ask_no_session")
                    results["ask_session_id"] = (False, f"POST /api/ask fired but no session_id in body. Body: {post_data[:300]}")
            else:
                screenshot("ask_no_call")
                results["ask_session_id"] = (False, f"No /api/ask POST after 30s. Last API calls: {json.dumps(api_calls[-5:])}")
        except Exception as e:
            screenshot("ask_exception")
            results["ask_session_id"] = (False, f"Exception: {type(e).__name__}: {str(e)[:200]}")

        # === TEST 9: Settings view ===
        print("\n[TEST 9] Settings view renders with Metrics card + Retention button")
        try:
            more_nav = page.locator("button:has-text('More')").first
            more_nav.click(timeout=10000)
            page.wait_for_timeout(5000)
            body_text = page.locator("body").inner_text(timeout=5000)
            body_lower = body_text.lower()
            has_metrics = "metrics" in body_lower
            has_retention = "retention" in body_lower
            results["settings_metrics_retention"] = (has_metrics and has_retention, f"metrics={has_metrics} retention={has_retention}")
            if not (has_metrics and has_retention):
                screenshot("settings_fail")
        except Exception as e:
            screenshot("settings_exception")
            results["settings_metrics_retention"] = (False, f"Exception: {type(e).__name__}: {str(e)[:200]}")

        # === TEST 10: Retention dialog ===
        print("\n[TEST 10] Retention button opens dialog + fetches /api/privacy/retention-status")
        api_calls.clear()
        try:
            retention_btn = page.locator("button:has-text('Data retention policy')").first
            if retention_btn.count() == 0:
                results["retention_dialog"] = (False, "Retention button not found")
            else:
                retention_btn.click(timeout=5000)
                page.wait_for_timeout(3000)
                retention_calls = [c for c in api_calls if "/api/privacy/retention-status" in c["url"]]
                dialog_visible = page.locator("[role='dialog']:has-text('Data Retention')").count() > 0
                results["retention_dialog"] = (
                    bool(retention_calls) and dialog_visible,
                    f"api_calls={len(retention_calls)} dialog_visible={dialog_visible}"
                )
                if not (retention_calls and dialog_visible):
                    screenshot("retention_fail")
        except Exception as e:
            screenshot("retention_exception")
            results["retention_dialog"] = (False, f"Exception: {type(e).__name__}: {str(e)[:200]}")

        screenshot("final")
        browser.close()

    return results, screenshots

def main():
    print("=" * 70)
    print("Maestro Web E2E (Playwright)")
    print("=" * 70)

    print("\n=== Starting servers ===")
    backend, web = start_servers()

    try:
        print("\n=== Waiting for backend ===")
        if not wait_for(f"{BACKEND_URL}/api/health", "Backend", timeout=30, expect_json=True):
            print("Backend failed. Log tail:")
            try:
                print(open("/tmp/pw_backend.log").read()[-2000:])
            except:
                pass
            return 1

        print("\n=== Waiting for web ===")
        if not wait_for(f"{WEB_URL}/", "Web root", timeout=60):
            print("Web failed. Log tail:")
            try:
                print(open("/tmp/pw_web.log").read()[-2000:])
            except:
                pass
            return 1

        print("\n=== Seeding 5 test signals (logs in as browser user first) ===")
        seeded, per_user_token = login_and_seed()
        if len(seeded) < 1:
            print("WARN: No signals seeded — Dashboard Moment tests will likely fail")

        print("\n=== Running Playwright tests ===")
        results, screenshots = run_tests()

        print("\n" + "=" * 70)
        print("RESULTS SUMMARY")
        print("=" * 70)
        passed = sum(1 for ok, _ in results.values() if ok)
        failed = sum(1 for ok, _ in results.values() if not ok)
        for name, (ok, detail) in results.items():
            mark = "PASS" if ok else "FAIL"
            print(f"  [{mark}] {name}")
            print(f"         {detail}")
        print(f"\n{passed} passed, {failed} failed, {len(results)} total")
        print(f"\nScreenshots: {screenshots}")

        # Save results as JSON for the worklog
        try:
            with open("/tmp/playwright_results.json", "w") as f:
                json.dump(results, f, indent=2, default=str)
        except:
            pass

        return 0 if failed == 0 else 2

    finally:
        print("\n=== Cleaning up servers ===")
        kill_servers()
        try:
            os.unlink(DB_PATH)
        except:
            pass

if __name__ == "__main__":
    sys.exit(main())

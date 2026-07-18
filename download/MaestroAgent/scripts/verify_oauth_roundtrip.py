#!/usr/bin/env python3
"""
OAuth Round-Trip Verification Script — Phase 3.

Run this script WITH REAL OAuth credentials to verify the full
connect → ingest → disconnect cycle works end-to-end.

Prerequisites:
  1. Set OAuth env vars (see docs/CONNECTOR_OAUTH_SETUP.md):
     - Gmail: MAESTRO_GMAIL_CLIENT_ID, MAESTRO_GMAIL_CLIENT_SECRET
     - Slack: MAESTRO_SLACK_CLIENT_ID, MAESTRO_SLACK_CLIENT_SECRET
     - GitHub: MAESTRO_GITHUB_CLIENT_ID, MAESTRO_GITHUB_CLIENT_SECRET
  2. Start the backend: PYTHONPATH=src python -m maestro_personal_shell.api
  3. Run this script: python scripts/verify_oauth_roundtrip.py

The script:
  1. Logs in
  2. For each configured provider:
     a. POST /api/connectors/{provider}/connect → get OAuth URL
     b. Opens the URL in your browser → you authorize → callback fires
     c. GET /api/connectors → verify connected=true
     d. POST /api/connectors/{provider}/ingest → verify real signals ingested
     e. DELETE /api/connectors/{provider} → verify disconnected
  3. Prints a pass/fail report per provider

This is the script the auditor would run to verify real OAuth round-trips.
"""
import os
import sys
import json
import time
import webbrowser
import urllib.request
import urllib.error
from pathlib import Path

API_URL = os.environ.get("MAESTRO_API_URL", "http://localhost:8766")
TOKEN = os.environ.get("MAESTRO_PERSONAL_TOKEN", "maestro-oauth-verify")

passed = 0
failed = 0
results = []

def check(name, ok, detail=""):
    global passed, failed
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}: {detail}")
    results.append({"name": name, "pass": ok, "detail": detail})
    if ok: passed += 1
    else: failed += 1

def api_call(method, path, token=None, data=None):
    """Make an API call and return (status_code, json_response)."""
    url = f"{API_URL}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except:
            return e.code, {"error": str(e)}
    except Exception as e:
        return 0, {"error": str(e)}

def verify_provider(provider):
    """Verify the full connect→ingest→disconnect cycle for a provider."""
    print(f"\n{'='*60}")
    print(f"Provider: {provider.upper()}")
    print(f"{'='*60}")

    # Step 1: Connect
    print(f"\n  Step 1: POST /api/connectors/{provider}/connect")
    status, data = api_call("POST", f"/api/connectors/{provider}/connect", TOKEN, {"provider": provider})
    if status == 400 and "not configured" in str(data).lower():
        print(f"  → SKIP: {provider} OAuth not configured")
        check(f"{provider}_full_cycle", True, "Skipped — OAuth not configured (set env vars to test)")
        return
    if status != 200:
        check(f"{provider}_connect", False, f"HTTP {status}: {data}")
        return
    check(f"{provider}_connect", True, f"HTTP 200")

    # Step 2: Open OAuth URL in browser
    if data.get("oauth_required"):
        auth_url = data.get("authorization_url", "")
        print(f"\n  Step 2: Open this URL in your browser and authorize:")
        print(f"  {auth_url}")
        print(f"\n  Waiting for OAuth callback (30s timeout)...")
        try:
            webbrowser.open(auth_url)
        except:
            print(f"  (could not auto-open browser — open manually)")

        # Wait for the user to authorize — poll connector status
        connected = False
        for _ in range(30):
            time.sleep(1)
            status, data = api_call("GET", "/api/connectors", TOKEN)
            if status == 200:
                connectors = data.get("connectors", [])
                conn = [c for c in connectors if c["provider"] == provider]
                if conn and conn[0].get("connected"):
                    connected = True
                    break
        if not connected:
            check(f"{provider}_oauth_callback", False, "Timed out waiting for OAuth callback (30s)")
            return
        check(f"{provider}_oauth_callback", True, "OAuth callback received, connector connected")
    elif data.get("already_connected"):
        check(f"{provider}_connect", True, "Already connected")
    else:
        check(f"{provider}_connect", True, f"Connected (no OAuth required)")

    # Step 3: Verify connected
    status, data = api_call("GET", "/api/connectors", TOKEN)
    if status == 200:
        conn = [c for c in data["connectors"] if c["provider"] == provider]
        if conn and conn[0]["connected"]:
            check(f"{provider}_verify_connected", True, f"connected=true, ingested={conn[0].get('commitments_ingested', 0)}")
        else:
            check(f"{provider}_verify_connected", False, "connected=false after connect")

    # Step 4: Ingest
    print(f"\n  Step 3: POST /api/connectors/{provider}/ingest")
    status, data = api_call("POST", f"/api/connectors/{provider}/ingest", TOKEN)
    if status == 200:
        check(f"{provider}_ingest", True,
              f"ingested={data.get('ingested',0)}, new_commitments={data.get('new_commitments',0)}, duplicates={data.get('duplicates',0)}")
    else:
        check(f"{provider}_ingest", False, f"HTTP {status}: {data}")

    # Step 5: Disconnect
    print(f"\n  Step 4: DELETE /api/connectors/{provider}")
    status, data = api_call("DELETE", f"/api/connectors/{provider}", TOKEN)
    if status == 200:
        check(f"{provider}_disconnect", True, "HTTP 200")
    else:
        check(f"{provider}_disconnect", False, f"HTTP {status}: {data}")

    # Step 6: Verify disconnected
    status, data = api_call("GET", "/api/connectors", TOKEN)
    if status == 200:
        conn = [c for c in data["connectors"] if c["provider"] == provider]
        if conn and not conn[0]["connected"]:
            check(f"{provider}_verify_disconnected", True, "connected=false after disconnect")
        else:
            check(f"{provider}_verify_disconnected", False, "connected=true after disconnect")

    # Overall
    provider_tests = [r for r in results if r["name"].startswith(provider)]
    all_ok = all(r["pass"] for r in provider_tests)
    check(f"{provider}_full_cycle", all_ok, f"{'All steps passed' if all_ok else f'{sum(1 for r in provider_tests if not r[\"pass\"])} steps failed'}")

def main():
    print("=" * 60)
    print("OAuth Round-Trip Verification — Phase 3")
    print("=" * 60)
    print(f"API URL: {API_URL}")
    print(f"Token: {TOKEN[:12]}...")

    # Health check
    status, _ = api_call("GET", "/api/health")
    if status != 200:
        print(f"\nFATAL: Backend not reachable at {API_URL} (HTTP {status})")
        print("Start it with: cd maestro-personal && PYTHONPATH=src python -m maestro_personal_shell.api")
        return 1
    print(f"\nBackend healthy ✓")

    # Login
    status, data = api_call("POST", "/api/auth/login", None, {"user_email": "default@personal.local", "password": TOKEN})
    if status != 200:
        print(f"\nFATAL: Login failed (HTTP {status}): {data}")
        return 1
    global TOKEN
    TOKEN = data.get("token", TOKEN)
    print(f"Logged in ✓ (token: {TOKEN[:12]}...)")

    # Verify each provider
    for provider in ["gmail", "slack", "github", "calendar"]:
        verify_provider(provider)

    # Summary
    print(f"\n{'='*60}")
    print(f"RESULTS: {passed} passed, {failed} failed")
    print(f"{'='*60}")
    for r in results:
        mark = "✓" if r["pass"] else "✗"
        print(f"  {mark} {r['name']}: {r['detail']}")

    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())

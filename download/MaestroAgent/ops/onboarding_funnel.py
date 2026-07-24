#!/usr/bin/env python3
"""onboarding_funnel.py — Measure the activation funnel: signup → connect → sync → first commitment.

Sean Parker reframe (2026-07-24): "instrument the one metric that decides
whether this product grows: time-from-signup-to-first-commitment-surfaced.
Drive it to under 2 minutes."

This script:
  1. Registers a fresh user (signup)
  2. Seeds a synthetic signal (simulates "first email ingested" — in a real
     funnel this would be the user clicking "Connect Gmail" → OAuth → sync)
  3. Runs an Ask query ("What did I promise?")
  4. Asserts a commitment surfaces with evidence
  5. Reports the total time from signup to first commitment

The target: < 2 minutes (120 seconds). If the funnel takes longer, the
product is losing users at the top — the activation funnel is broken.

In production, this script would use a REAL Gmail connect (OAuth → sync →
real emails). For CI/gate purposes, it uses a synthetic signal to exercise
the funnel path without OAuth. The [CONN] gate assertion covers the real
Gmail connect; this script covers the FUNNEL TIMING.

USAGE:
    python3 ops/onboarding_funnel.py
    (exit 0 = funnel < 2 min, exit 1 = funnel too slow or commitment didn't surface)
"""
from __future__ import annotations

import json
import os
import sys
import time

# Use httpx (already installed in CI) for better timeout + error handling
try:
    import httpx
    USE_HTTPX = True
except ImportError:
    import urllib.request
    import urllib.error
    USE_HTTPX = False

BACKEND_URL = os.environ.get(
    "MAESTRO_BACKEND_URL",
    "https://maestroagent-production.up.railway.app",
)
TARGET_SECONDS = 120  # 2 minutes — the Sean Parker bar


def api(method: str, path: str, token: str = "", body: dict | None = None) -> dict:
    """Call the backend API with httpx (preferred) or urllib fallback."""
    url = f"{BACKEND_URL}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    if USE_HTTPX:
        try:
            if method == "GET":
                resp = httpx.request(method, url, headers=headers, timeout=60)
            else:
                resp = httpx.request(method, url, headers=headers, json=body, timeout=60)
            if resp.status_code >= 400:
                return {"error": f"HTTP {resp.status_code}", "body": resp.text[:200]}
            return resp.json()
        except Exception as e:
            return {"error": str(e)}
    else:
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            return {"error": f"HTTP {e.code}", "body": e.read().decode()[:200]}
        except Exception as e:
            return {"error": str(e)}


def measure_funnel() -> dict:
    """Run the full activation funnel and return timing + results."""
    report = {"steps": [], "total_seconds": 0, "commitment_surfaced": False}

    # ── Step 1: Signup ──────────────────────────────────────────────────
    t0 = time.time()
    email = f"funnel-{int(t0)}@example.com"
    signup_resp = api("POST", "/api/auth/register", body={
        "user_email": email, "password": "funnel-pass", "name": "Funnel",
    })
    token = signup_resp.get("token", "")
    if not token:
        signup_time = time.time() - t0
        report["steps"].append({"step": "signup", "seconds": round(signup_time, 2), "ok": False, "error": str(signup_resp)[:200]})
        report["total_seconds"] = signup_time
        return report
    signup_time = time.time() - t0
    report["steps"].append({"step": "signup", "seconds": round(signup_time, 2), "ok": True})

    # ── Step 2: Connect a source (simulated with a synthetic signal) ────
    # In production, this is: user clicks "Connect Gmail" → OAuth popup →
    # token stored → sync starts. For timing measurement, we simulate the
    # "first email ingested" by posting a signal directly.
    # NOTE: the signal POST can hit SQLite "database is locked" under
    # concurrent CI load. We retry up to 3 times with 1s delay.
    t1 = time.time()
    signal = {
        "signal_id": f"funnel-{int(t1)}",
        "entity": "Sarah Chen",
        "text": "I will send the Q4 report to Sarah by end of week.",
        "signal_type": "commitment_made",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "metadata": {
            "source": "gmail:inbox",  # simulates Gmail ingestion
            "is_commitment": True,
            "commitment_type": "commitment_made",
            "commitment_state": "active",
            "commitment_owner": "user",
            "commitment_confidence": 0.9,
        },
    }
    signal_resp = None
    for attempt in range(3):
        signal_resp = api("POST", "/api/signals", token=token, body=signal)
        if "error" not in signal_resp:
            break
        print(f"  ⚠ Signal post attempt {attempt+1} failed: {str(signal_resp)[:150]}")
        time.sleep(2)  # retry after SQLite lock
    connect_time = time.time() - t1
    # Check the signal was actually created (response should have signal_id or status)
    ok = "error" not in (signal_resp or {}) and bool(
        signal_resp.get("signal_id") or signal_resp.get("status") or signal_resp.get("id")
    )
    report["steps"].append({
        "step": "connect_source",
        "seconds": round(connect_time, 2),
        "ok": ok,
        "detail": f"resp={str(signal_resp)[:100]}" if not ok else "",
    })

    # If the signal didn't post, the funnel is broken — fail fast
    if not ok:
        report["total_seconds"] = round(time.time() - t0, 2)
        report["commitment_surfaced"] = False
        return report

    # ── Step 3: Wait for ledger to settle ───────────────────────────────
    t2 = time.time()
    time.sleep(2)  # ledger settle
    settle_time = time.time() - t2
    report["steps"].append({"step": "ledger_settle", "seconds": round(settle_time, 2), "ok": True})

    # ── Step 4: Ask "What did I promise?" → first commitment surfaces ───
    t3 = time.time()
    ask_resp = api("POST", "/api/ask", token=token, body={"query": "What did I promise Sarah?"})
    ask_time = time.time() - t3

    answer = ask_resp.get("answer", "")
    evidence = ask_resp.get("evidence_refs", [])
    confidence = ask_resp.get("confidence", 0)
    source = ask_resp.get("intelligence_source", "")

    # A commitment "surfaces" if:
    # - The answer mentions the entity (Sarah)
    # - There's at least 1 evidence_ref
    # - Confidence > 0
    commitment_surfaced = (
        "sarah" in answer.lower()
        and len(evidence) > 0
        and confidence > 0
    )
    report["commitment_surfaced"] = commitment_surfaced
    report["steps"].append({
        "step": "first_commitment",
        "seconds": round(ask_time, 2),
        "ok": commitment_surfaced,
        "detail": f"confidence={confidence}, evidence={len(evidence)}, source={source}, answer={answer[:100]}",
    })

    report["total_seconds"] = round(time.time() - t0, 2)
    return report


def main():
    print("=" * 60)
    print("ACTIVATION FUNNEL — time from signup to first commitment")
    print(f"Target: < {TARGET_SECONDS}s (2 minutes)")
    print(f"Backend: {BACKEND_URL}")
    print("=" * 60)

    report = measure_funnel()

    print("\nFunnel steps:")
    for step in report["steps"]:
        icon = "✓" if step["ok"] else "✗"
        detail = step.get("detail", "")
        print(f"  {icon} {step['step']:20s} {step['seconds']:6.2f}s  {detail[:80]}")

    print(f"\nTotal: {report['total_seconds']}s (target: <{TARGET_SECONDS}s)")
    print(f"Commitment surfaced: {report['commitment_surfaced']}")

    # Assert
    if not report["commitment_surfaced"]:
        print("\n❌ FAIL — commitment did not surface. The funnel is broken.")
        sys.exit(1)
    if report["total_seconds"] > TARGET_SECONDS:
        print(f"\n❌ FAIL — funnel took {report['total_seconds']}s, exceeding {TARGET_SECONDS}s target.")
        sys.exit(1)

    print(f"\n✅ PASS — funnel completed in {report['total_seconds']}s with commitment surfaced.")
    sys.exit(0)


if __name__ == "__main__":
    main()

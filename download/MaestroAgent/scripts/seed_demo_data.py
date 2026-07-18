#!/usr/bin/env python3
"""
Seed realistic demo data for investor demos.

Run this against a running backend to populate it with realistic
commitments, signals, and whispers so the app looks alive.

Usage:
  # Start backend first, then:
  python3 scripts/seed_demo_data.py --token your-token-here

  # Or with defaults (token=maestro-demo):
  python3 scripts/seed_demo_data.py
"""
import sys
import os
import json
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

API_URL = os.environ.get("MAESTRO_API_URL", "http://localhost:8766")
TOKEN = os.environ.get("MAESTRO_DEMO_TOKEN", "maestro-demo")

# Realistic demo data — synthetic names, realistic business scenarios
DEMO_SIGNALS = [
    # Stale commitments (will surface in The Moment)
    {
        "entity": "Sarah Chen",
        "text": "I promised Sarah I would send the Series A pitch deck by last Friday — she's followed up twice and the deadline has passed. URGENT: overdue.",
        "signal_type": "commitment_made",
        "days_ago": 12,
    },
    {
        "entity": "Marcus Rodriguez",
        "text": "I committed to reviewing the API migration PR by Monday — Marcus is blocked waiting on my review. Overdue commitment.",
        "signal_type": "commitment_made",
        "days_ago": 10,
    },
    {
        "entity": "Priya Patel",
        "text": "I told Priya I would deliver the quarterly analytics report last Wednesday — deadline passed, she's escalating to leadership.",
        "signal_type": "commitment_made",
        "days_ago": 8,
    },
    # Recent commitments (won't surface but show in list)
    {
        "entity": "David Kim",
        "text": "I will send the board update by end of day Friday.",
        "signal_type": "commitment_made",
        "days_ago": 1,
    },
    {
        "entity": "Eve Martinez",
        "text": "I promised Eve I'd schedule the security audit for next week.",
        "signal_type": "commitment_made",
        "days_ago": 2,
    },
    # Reported statements (context, not commitments)
    {
        "entity": "Alex Thompson",
        "text": "Alex said the Orion migration is 80% complete — on track for Q3 launch.",
        "signal_type": "reported_statement",
        "days_ago": 3,
    },
    {
        "entity": "Sarah Chen",
        "text": "Sarah mentioned the investor meeting went well — they're interested in the commitment tracking angle.",
        "signal_type": "reported_statement",
        "days_ago": 5,
    },
    {
        "entity": "Marcus Rodriguez",
        "text": "Marcus raised a concern about the API rate limiting — wants to discuss before the migration.",
        "signal_type": "material_objection",
        "days_ago": 4,
    },
    # Follow-up needed
    {
        "entity": "Priya Patel",
        "text": "Need to follow up with Priya on the analytics dashboard design — she asked for input last week.",
        "signal_type": "follow_up_required",
        "days_ago": 6,
    },
    # Outcome
    {
        "entity": "David Kim",
        "text": "David confirmed the board approved the Q3 budget — we're clear to hire 2 engineers.",
        "signal_type": "outcome",
        "days_ago": 7,
    },
    # More stale commitments for variety
    {
        "entity": "Jennifer Wu",
        "text": "I promised Jennifer the customer research findings by Tuesday — she's waiting to present to the exec team. Critical: overdue.",
        "signal_type": "commitment_made",
        "days_ago": 9,
    },
    {
        "entity": "Tom Bradley",
        "text": "I told Tom I'd review the partnership terms by last Thursday — Legal is waiting on my sign-off. Overdue.",
        "signal_type": "commitment_made",
        "days_ago": 11,
    },
]

DEMO_QUESTIONS = [
    "What did I promise Sarah Chen?",
    "What's overdue?",
    "What did Priya say about the analytics report?",
    "Who am I disappointing?",
    "What critical events need immediate attention?",
    "What did I commit to in the last 7 days?",
    "What did David confirm about the budget?",
]

def api_call(method, path, token, data=None):
    url = f"{API_URL}{path}"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
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

def main():
    print("=" * 60)
    print("MaestroAgent Demo Data Seeder")
    print("=" * 60)
    print(f"API: {API_URL}")
    print(f"Token: {TOKEN[:12]}...")

    # Health check
    status, _ = api_call("GET", "/api/health", TOKEN)
    if status != 200:
        print(f"\nFATAL: Backend not reachable at {API_URL}")
        print("Start it with: cd maestro-personal && PYTHONPATH=src python -m maestro_personal_shell.api")
        return 1
    print("Backend healthy ✓")

    # Login
    status, data = api_call("POST", "/api/auth/login", None, {
        "user_email": "default@personal.local",
        "password": TOKEN,
    })
    if status != 200:
        print(f"\nFATAL: Login failed (HTTP {status}): {data}")
        return 1
    token = data.get("token", TOKEN)
    print(f"Logged in ✓ (token: {token[:12]}...)")

    # Seed signals
    print(f"\nSeeding {len(DEMO_SIGNALS)} demo signals...")
    now = datetime.now(timezone.utc)
    seeded = 0
    for sig in DEMO_SIGNALS:
        ts = (now - timedelta(days=sig["days_ago"])).isoformat()
        status, data = api_call("POST", "/api/signals", token, {
            "entity": sig["entity"],
            "text": sig["text"],
            "signal_type": sig["signal_type"],
            "timestamp": ts,
        })
        if status == 200:
            seeded += 1
            print(f"  ✓ {sig['entity']:20s} ({sig['signal_type']:22s}) — {sig['text'][:60]}...")
        else:
            print(f"  ✗ {sig['entity']:20s} — HTTP {status}: {str(data)[:80]}")

    print(f"\nSeeded {seeded}/{len(DEMO_SIGNALS)} signals.")

    # Verify The Moment surfaces
    print("\nVerifying The Moment...")
    status, data = api_call("GET", "/api/the-moment", token)
    if status == 200:
        moment = data
        if moment.get("has_moment"):
            c = moment.get("commitment", {})
            print(f"  ✓ The Moment is active!")
            print(f"    Entity: {c.get('entity')}")
            print(f"    Text: {c.get('text', '')[:80]}...")
            print(f"    Why: {moment.get('why_this_one', '')[:100]}")
        else:
            print(f"  ⚠ The Moment is in Trusted Silence: {moment.get('why_this_one', '')[:100]}")
    else:
        print(f"  ✗ Failed to get The Moment: HTTP {status}")

    # Test a few questions
    print(f"\nTesting {len(DEMO_QUESTIONS)} demo questions...")
    for q in DEMO_QUESTIONS:
        status, data = api_call("POST", "/api/ask", token, {"query": q})
        if status == 200:
            answer = data.get("answer", "")[:100]
            llm = data.get("llm_active", False)
            conf = data.get("confidence", 0)
            src = data.get("intelligence_source", "?")
            print(f"  [{'LLM' if llm else 'rul'}] conf={conf:.1f} src={src:5s} Q: {q}")
            print(f"       A: {answer}...")
        else:
            print(f"  ✗ HTTP {status}: {q}")

    print(f"\n{'='*60}")
    print(f"Demo data ready! Open the web app and try:")
    print(f"  - Dashboard → The Moment card (should show a stale commitment)")
    print(f"  - Ask → 'What did I promise Sarah Chen?'")
    print(f"  - Commitments → see the full list + Draft buttons")
    print(f"  - More → Connectors, Settings, Metrics")
    print(f"{'='*60}")
    return 0

if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Lifecycle fixture — populates the commitment ledger through the REAL extraction pipeline.

The synthetic inbox (/api/inbox/synthetic/) creates signals but does NOT
populate the commitment ledger (the classification pipeline runs only on
/api/signals POST). This fixture posts signals through /api/signals with
the right metadata to create ledger entries with lifecycle states:

  1. Maria Garcia — active commitment (Q3 budget proposal by Friday)
  2. Maria Garcia — reschedule signal (move to Wednesday)
  3. Alex Chen — completed commitment (review the auth module)
  4. Jamie Lee — cancelled commitment (design mockups)

After running this, the ledger has non-zero entries with transitions,
and the RC2 fast path can be verified.

USAGE:
    python3 ops/lifecycle_fixture.py <TOKEN>
    (or it auto-registers a user if no token provided)
"""
from __future__ import annotations

import json
import sys
import time
import httpx

BACKEND_URL = "https://maestroagent-production.up.railway.app"


def create_lifecycle_fixture(token: str) -> dict:
    """Post signals through /api/signals to populate the ledger.

    Returns a report of what was created.
    """
    report = {"signals_posted": 0, "ledger_expected": 0, "details": []}

    signals = [
        # 1. Maria Garcia — active commitment
        {
            "signal_id": f"lc-maria-active-{int(time.time())}",
            "entity": "Maria Garcia",
            "text": "I will send the Q3 budget proposal to Maria by Friday.",
            "signal_type": "commitment_made",
            "timestamp": "2026-07-22T10:00:00Z",
            "metadata": {
                "source": "lifecycle_fixture",
                "is_commitment": True,
                "commitment_type": "commitment_made",
                "commitment_state": "active",
                "commitment_owner": "user",
                "commitment_confidence": 0.9,
            },
        },
        # 2. Maria Garcia — reschedule signal (NO manual superseded tag)
        #    The supersession detection in upsert_ledger_entry should detect
        #    the reschedule cue ("can we move it to") and transition the
        #    original active entry to superseded automatically.
        {
            "signal_id": f"lc-maria-reschedule-{int(time.time())}",
            "entity": "Maria Garcia",
            "text": "I know I said Friday, but can we move it to next Wednesday instead?",
            "signal_type": "commitment_updated",
            "timestamp": "2026-07-23T14:00:00Z",
            "metadata": {
                "source": "lifecycle_fixture",
                "is_commitment": True,
                "commitment_type": "commitment_updated",
                "commitment_state": "active",  # NOT superseded — detection should handle it
                "commitment_owner": "user",
                "commitment_confidence": 0.8,
            },
        },
        # 3. Alex Chen — completed commitment
        {
            "signal_id": f"lc-alex-completed-{int(time.time())}",
            "entity": "Alex Chen",
            "text": "I said I'd review the auth module by Tuesday, but I actually already reviewed it yesterday.",
            "signal_type": "commitment_completed",
            "timestamp": "2026-07-23T09:00:00Z",
            "metadata": {
                "source": "lifecycle_fixture",
                "is_commitment": True,
                "commitment_type": "commitment_completed",
                "commitment_state": "completed_claimed",
                "commitment_owner": "user",
                "commitment_confidence": 0.9,
            },
        },
        # 4. Jamie Lee — cancelled commitment
        {
            "signal_id": f"lc-jamie-cancelled-{int(time.time())}",
            "entity": "Jamie Lee",
            "text": "Actually, let's cancel the design mockups — we're going in a different direction.",
            "signal_type": "commitment_broken",
            "timestamp": "2026-07-22T16:00:00Z",
            "metadata": {
                "source": "lifecycle_fixture",
                "is_commitment": True,
                "commitment_type": "commitment_broken",
                "commitment_state": "cancelled",
                "commitment_owner": "user",
                "commitment_confidence": 0.85,
            },
        },
        # 5. Priya Patel — active commitment (CI pipeline)
        {
            "signal_id": f"lc-priya-active-{int(time.time())}",
            "entity": "Priya Patel",
            "text": "I will fix the CI pipeline by end of week.",
            "signal_type": "commitment_made",
            "timestamp": "2026-07-22T11:00:00Z",
            "metadata": {
                "source": "lifecycle_fixture",
                "is_commitment": True,
                "commitment_type": "commitment_made",
                "commitment_state": "active",
                "commitment_owner": "user",
                "commitment_confidence": 0.9,
            },
        },
    ]

    for sig in signals:
        try:
            resp = httpx.post(
                f"{BACKEND_URL}/api/signals",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=sig,
                timeout=30,
            )
            if resp.status_code == 200:
                report["signals_posted"] += 1
                report["ledger_expected"] += 1
                report["details"].append(
                    f"  ✓ {sig['entity']}: {sig['signal_type']} (state={sig['metadata']['commitment_state']})"
                )
                print(f"  ✓ Posted: {sig['entity']} — {sig['text'][:50]}...")
            else:
                report["details"].append(
                    f"  ✗ {sig['entity']}: HTTP {resp.status_code} — {resp.text[:100]}"
                )
                print(f"  ✗ Failed: {sig['entity']} — HTTP {resp.status_code}")
        except Exception as e:
            report["details"].append(f"  ✗ {sig['entity']}: {e}")
            print(f"  ✗ Error: {sig['entity']} — {e}")

    return report


def verify_ledger(token: str) -> dict:
    """Verify the ledger has entries after the fixture."""
    # Use the /api/commitments endpoint to check
    try:
        resp = httpx.get(
            f"{BACKEND_URL}/api/commitments",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        data = resp.json()
        comms = data if isinstance(data, list) else data.get("commitments", data.get("data", []))
        return {
            "total": len(comms),
            "commitments": [
                {
                    "entity": c.get("entity", "?"),
                    "state": c.get("state", "?"),
                    "action": str(c.get("action", c.get("text", "")))[:60],
                }
                for c in comms[:10]
            ],
        }
    except Exception as e:
        return {"error": str(e)}


def main():
    token = sys.argv[1] if len(sys.argv) > 1 else ""

    if not token:
        print("No token provided — registering a new user...")
        resp = httpx.post(
            f"{BACKEND_URL}/api/auth/register",
            json={
                "user_email": f"lifecycle-{int(time.time())}@example.com",
                "password": "lifecycle-pass",
                "name": "Lifecycle",
            },
            timeout=15,
        )
        token = resp.json().get("token", "")
        if not token:
            print(f"Register failed: {resp.json()}")
            sys.exit(1)
        print(f"  ✓ Registered: {resp.json().get('user_email', '')}")

    print("\n=== CREATING LIFECYCLE FIXTURE ===")
    print("Posting 5 signals through /api/signals (real extraction pipeline)...")
    report = create_lifecycle_fixture(token)

    print(f"\n=== RESULTS ===")
    print(f"Signals posted: {report['signals_posted']}")
    print(f"Ledger entries expected: {report['ledger_expected']}")
    for d in report["details"]:
        print(d)

    print(f"\n=== VERIFYING LEDGER ===")
    ledger = verify_ledger(token)
    print(f"Ledger total: {ledger.get('total', 'error')}")
    for c in ledger.get("commitments", []):
        print(f"  [{c['state']:20s}] {c['entity']} — {c['action']}")

    if ledger.get("total", 0) > 0:
        print(f"\n✓ LEDGER IS POPULATED — RC2 fast path can now be verified")
    else:
        print(f"\n✗ LEDGER IS EMPTY — the extraction pipeline didn't create entries")
        print("  (this means the /api/signals endpoint doesn't classify commitments")
        print("   the same way as the synthetic inbox. Need to investigate.)")

    # If ledger is populated, test the RC2 fast path
    if ledger.get("total", 0) > 0:
        print(f"\n=== TESTING RC2 FAST PATH ===")
        print("Query: 'What did I promise Maria?'")

        start = time.time()
        resp = httpx.post(
            f"{BACKEND_URL}/api/ask",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"query": "What did I promise Maria?"},
            timeout=60,
        )
        elapsed = time.time() - start

        data = resp.json()
        answer = data.get("answer", "")
        confidence = data.get("confidence", 0.0)
        source = data.get("intelligence_source", "")
        evidence = data.get("evidence_refs", [])
        entities = set(str(e.get("entity", "")) for e in evidence)

        print(f"  Latency: {elapsed:.3f}s")
        print(f"  Confidence: {confidence}")
        print(f"  Source: {source}")
        print(f"  Evidence: {len(evidence)} items, entities: {entities}")
        print(f"  Answer: {answer[:200]}")
        print(f"")
        print(f"  Source = ledger: {'YES ✓' if source == 'ledger' else 'NO ✗ (fast path did not fire)'}")
        print(f"  Latency < 2s: {'YES ✓' if elapsed < 2 else 'NO ⚠'}")
        print(f"  Maria in answer: {'YES ✓' if 'maria' in answer.lower() else 'NO ✗'}")

        # Also test the auditor's exact query
        print(f"\nQuery: 'What did I promise Maria? Give only evidence and account for whether the proposal was received or rescheduled.'")
        start = time.time()
        resp = httpx.post(
            f"{BACKEND_URL}/api/ask",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"query": "What did I promise Maria? Give only evidence and account for whether the proposal was received or rescheduled."},
            timeout=60,
        )
        elapsed = time.time() - start
        data = resp.json()
        print(f"  Latency: {elapsed:.3f}s")
        print(f"  Source: {data.get('intelligence_source', '')}")
        print(f"  Answer: {data.get('answer', '')[:200]}")
        print(f"  Surfaces reschedule: {'YES ✓' if 'reschedul' in data.get('answer', '').lower() or 'wednesday' in data.get('answer', '').lower() else 'NO ✗'}")


if __name__ == "__main__":
    main()

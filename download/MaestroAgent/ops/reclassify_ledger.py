#!/usr/bin/env python3
"""reclassify_ledger.py — Re-classify existing signals with the current classifier.

Auditor Principle 5 (2026-07-24): "A classifier change re-classifies the data.
The classifier code is fixed (the gold-set proves it), but the existing ledger
entries were classified by the old classifier and never re-classified — so
the audit reads uniform claim_type: commitment, confidence 0.28 from the
stored data. A classifier change must trigger a migration over existing data,
or the fix is only forward-looking and history stays wrong."

This script:
  1. Connects to the backend as an admin
  2. Fetches all signals for a user (or all users)
  3. Re-runs the current classifier on each signal's text
  4. Updates the signal_type + metadata with the new classification
  5. Reports how many signals were re-classified

USAGE (admin endpoint — requires MAESTRO_PERSONAL_TOKEN):
    curl -X POST -H "Authorization: Bearer maestro-demo" \
      https://maestroagent-production.up.railway.app/api/admin/reclassify-ledger

Or locally:
    python3 ops/reclassify_ledger.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import httpx

BACKEND_URL = os.environ.get(
    "MAESTRO_BACKEND_URL",
    "https://maestroagent-production.up.railway.app",
)
ADMIN_TOKEN = os.environ.get("MAESTRO_PERSONAL_TOKEN", "maestro-demo")


def main():
    print("=" * 60)
    print("RE-CLASSIFY LEDGER (Principle 5)")
    print("Re-running the current classifier over existing signals")
    print(f"Backend: {BACKEND_URL}")
    print("=" * 60)

    # Call the admin endpoint
    try:
        resp = httpx.post(
            f"{BACKEND_URL}/api/admin/reclassify-ledger",
            headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
            timeout=120,
        )
        if resp.status_code != 200:
            print(f"✗ HTTP {resp.status_code}: {resp.text[:300]}")
            sys.exit(1)
        data = resp.json()
        print(f"\n✓ Re-classification complete:")
        print(f"  Total signals: {data.get('total_signals', 0)}")
        print(f"  Re-classified: {data.get('reclassified', 0)}")
        print(f"  Unchanged: {data.get('unchanged', 0)}")
        print(f"  Failed: {data.get('failed', 0)}")
        print(f"\n  By type (before → after):")
        for transition, count in data.get("transitions", {}).items():
            print(f"    {transition}: {count}")
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

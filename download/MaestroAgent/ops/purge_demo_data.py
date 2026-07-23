#!/usr/bin/env python3
"""Purge demo_seed data from real users' stores.

P1 PERMANENT FIX: the product is now a real-data pilot. Demo data
masquerading as real is the entropy we're ending. This script:
  1. Deletes all demo_seed-sourced signals from ALL users
  2. Removes demo_seed signals from the FTS index
  3. Logs what was removed (governance: scoped deletion, logged)
  4. Does NOT touch real user data (Gmail-sourced signals stay)

Benchmark test users (benchmark-*@example.com) don't use demo_seed
(they seed via /api/inbox/synthetic/), so they're unaffected.

USAGE:
    python3 ops/purge_demo_data.py              # purge + report
    python3 ops/purge_demo_data.py --dry-run    # report only, no deletion
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

# Make the source importable
SRC = Path(__file__).resolve().parents[1] / "maestro-personal" / "src"
sys.path.insert(0, str(SRC))


def purge_demo_data(dry_run: bool = False) -> dict:
    """Purge all demo_seed-sourced signals. Returns a report dict."""
    from maestro_personal_shell.db_util import get_db_conn, default_sqlite_path

    db_path = default_sqlite_path()
    db = get_db_conn(db_path)
    db.row_factory = sqlite3.Row

    report = {
        "dry_run": dry_run,
        "db_path": str(db_path),
        "total_signals_before": 0,
        "demo_seed_signals_found": 0,
        "demo_seed_signals_deleted": 0,
        "users_affected": [],
        "real_signals_preserved": 0,
    }

    try:
        # Count total signals
        total = db.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        report["total_signals_before"] = total

        # Find all demo_seed signals (metadata contains "demo_seed")
        # The metadata column is JSON — search for "demo_seed" in it
        demo_rows = db.execute(
            "SELECT signal_id, user_email, entity, text, metadata FROM signals WHERE metadata LIKE '%demo_seed%'"
        ).fetchall()

        report["demo_seed_signals_found"] = len(demo_rows)

        # Group by user
        users_affected = set()
        for row in demo_rows:
            users_affected.add(row["user_email"])
        report["users_affected"] = list(users_affected)

        # Count real (non-demo) signals
        real_count = db.execute(
            "SELECT COUNT(*) FROM signals WHERE metadata NOT LIKE '%demo_seed%'"
        ).fetchone()[0]
        report["real_signals_preserved"] = real_count

        if dry_run:
            print(f"\n[DRY RUN] Would delete {len(demo_rows)} demo_seed signals from {len(users_affected)} user(s)")
            for row in demo_rows[:5]:
                print(f"  {row['user_email']}: [{row['signal_id']}] {row['entity']} — {row['text'][:50]}...")
            if len(demo_rows) > 5:
                print(f"  ... and {len(demo_rows) - 5} more")
            return report

        # Delete demo_seed signals
        if demo_rows:
            signal_ids = [row["signal_id"] for row in demo_rows]
            placeholders = ",".join("?" * len(signal_ids))
            db.execute(
                f"DELETE FROM signals WHERE signal_id IN ({placeholders})",
                signal_ids,
            )

            # Also remove from FTS index
            try:
                db.execute(
                    f"DELETE FROM signals_fts WHERE signal_id IN ({placeholders})",
                    signal_ids,
                )
            except Exception as e:
                print(f"  (FTS cleanup non-fatal: {e})")

            # Also clean up the commitment ledger
            try:
                db.execute(
                    f"DELETE FROM commitments_ledger WHERE signal_id IN ({placeholders})",
                    signal_ids,
                )
            except Exception as e:
                print(f"  (ledger cleanup non-fatal: {e})")

            db.commit()
            report["demo_seed_signals_deleted"] = len(demo_rows)

        # Verify: count remaining signals
        remaining = db.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        remaining_demo = db.execute(
            "SELECT COUNT(*) FROM signals WHERE metadata LIKE '%demo_seed%'"
        ).fetchone()[0]

        report["total_signals_after"] = remaining
        report["demo_seed_remaining"] = remaining_demo

    finally:
        db.close()

    return report


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Purge demo_seed data from real users")
    parser.add_argument("--dry-run", action="store_true", help="Report only, no deletion")
    args = parser.parse_args()

    print("=" * 72)
    print("PURGE DEMO DATA — P1 Permanent Fix")
    print("=" * 72)

    report = purge_demo_data(dry_run=args.dry_run)

    print(f"\nReport:")
    print(f"  DB path: {report['db_path']}")
    print(f"  Total signals before: {report['total_signals_before']}")
    print(f"  demo_seed signals found: {report['demo_seed_signals_found']}")
    print(f"  Users affected: {len(report['users_affected'])}")
    for user in report["users_affected"]:
        print(f"    - {user}")
    print(f"  Real signals preserved: {report['real_signals_preserved']}")

    if not args.dry_run:
        print(f"\n  demo_seed signals DELETED: {report['demo_seed_signals_deleted']}")
        print(f"  Total signals after: {report.get('total_signals_after', 'N/A')}")
        print(f"  demo_seed remaining: {report.get('demo_seed_remaining', 'N/A')}")

        if report.get("demo_seed_remaining", 0) == 0:
            print(f"\n✓ PERMANENT: demo_seed count = 0 for all users")
            print(f"  Real signals preserved: {report['real_signals_preserved']}")
            print(f"  The product is now real-data-only.")
        else:
            print(f"\n✗ demo_seed signals still remain — investigate")
    else:
        print(f"\n[DRY RUN] No data was deleted.")

    # Governance: log the action
    print(f"\n--- Governance Log ---")
    print(f"  Action: {'DRY_RUN' if args.dry_run else 'PURGE_DEMO_DATA'}")
    print(f"  Scope: signals with metadata LIKE '%demo_seed%'")
    print(f"  Real user data: PRESERVED (only demo_seed-sourced signals deleted)")
    print(f"  Benchmark test users: UNAFFECTED (they use /api/inbox/synthetic/, not demo_seed)")


if __name__ == "__main__":
    main()

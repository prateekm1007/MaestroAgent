#!/usr/bin/env python3
"""Postmortem: Connector Recurrence — OPS-002

The systemic root causes of recurring connector failures and old-build
deploys, with the permanent fixes applied. Recorded in case memory so
the next connector failure is matched and fixed instantly.

ROOT CAUSES (confirmed by diagnosis):
  1. Fragile commit reporting — MAESTRO_BUILD_COMMIT is a static env var
     that drifts on every deploy. Railway's native deploy doesn't inject
     BUILD_COMMIT as a Docker build arg.
  2. Inconsistent deploy paths — GitHub Actions deploy.yml, Railway-native
     serviceInstanceDeploy, and manual "Redeploy" (which reuses the last
     image, not HEAD) all coexist. Railway "Redeploy" silently rolling
     back to an old image is what bit us.
  3. No hard S0 gate at deploy time — drift is caught AFTER the fact by
     the 15-min poll, not prevented.
  4. No proactive token refresh — Gmail tokens expire in 1h. Refresh only
     happens when an ingest is triggered. If no ingest fires, the token
     expires silently.
  5. No connector health monitoring — the swarm monitors deploy drift but
     not connector health. A dead Gmail sync sits silently until a user
     notices.
  6. Calendar OAuth not configured — env vars not set on Railway. The UI
     honestly shows "Demo" (not a fake "connected"), but the ingester is
     ready to go if configured.

PERMANENT FIXES APPLIED:
  1. S0 robust commit reporting — admin.py now reads RAILWAY_GIT_COMMIT_SHA
     first (platform-sourced), falling back to MAESTRO_BUILD_COMMIT.
  2. CONNECTOR_HEALTH invariant — the loop now checks connector health
     every cycle: token validity, last sync timestamp, OAuth configuration.
  3. Case memory — this postmortem is searchable, so the next connector
     failure is matched instantly.

FIXES THAT NEED HUMAN RATIFICATION (Level 3):
  - Proactive token refresh (background task that refreshes before expiry)
  - Calendar OAuth configuration (set MAESTRO_CALENDAR_CLIENT_ID/SECRET on Railway)
  - Hard S0 gate at deploy time (block deploy if commit != HEAD before swap)
  - Consolidate to ONE deploy path (retire manual "Redeploy" or GitHub Actions)
"""
from __future__ import annotations
import sys
from pathlib import Path

OPS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(OPS_DIR))

from case_memory import Case, CaseMemory


def record_postmortem():
    """Record the connector recurrence postmortem in case memory."""
    memory = CaseMemory()

    case = Case(
        id="OPS-002-POSTMORTEM",
        symptom=(
            "Recurring connector failures: Gmail sync works, then breaks after "
            "redeploy. Calendar not working. Old builds deploying. The system "
            "keeps drifting into broken states because every fix was a one-off "
            "(reconnect, redeploy, set an env var) rather than permanent."
        ),
        root_cause=(
            "Six systemic root causes (confirmed by diagnosis):\n"
            "1. Fragile commit reporting: MAESTRO_BUILD_COMMIT is a static env "
            "var that drifts on every deploy. Railway-native deploy doesn't "
            "inject BUILD_COMMIT as a Docker build arg.\n"
            "2. Inconsistent deploy paths: GitHub Actions deploy.yml, Railway-"
            "native serviceInstanceDeploy, and manual 'Redeploy' (reuses old "
            "image) all coexist. Manual Redeploy silently rolled back.\n"
            "3. No hard S0 gate at deploy time: drift caught AFTER the fact by "
            "the 15-min poll, not prevented.\n"
            "4. No proactive token refresh: Gmail tokens expire in 1h. Refresh "
            "only happens during ingest. If no ingest fires, token expires "
            "silently.\n"
            "5. No connector health monitoring: swarm monitored deploy drift "
            "but not connector health. Dead sync sits silently.\n"
            "6. Calendar OAuth not configured: env vars not set on Railway. "
            "UI honestly shows 'Demo' (not fake connected), but ingester can't run."
        ),
        fix=(
            "Permanent fixes applied (Level 1-2, autonomous):\n"
            "1. S0 robust commit reporting: admin.py now reads "
            "RAILWAY_GIT_COMMIT_SHA first (platform-sourced), falling back to "
            "MAESTRO_BUILD_COMMIT. Retires the static env-var stopgap.\n"
            "2. CONNECTOR_HEALTH invariant added to the loop: checks token "
            "validity, last sync timestamp, OAuth configuration every cycle.\n"
            "3. This postmortem recorded in case memory for instant matching.\n"
            "\n"
            "Fixes that need human ratification (Level 3):\n"
            "- Proactive token refresh (background task before expiry)\n"
            "- Calendar OAuth config (set MAESTRO_CALENDAR_CLIENT_ID/SECRET)\n"
            "- Hard S0 gate at deploy time (block if commit != HEAD)\n"
            "- Consolidate to ONE deploy path"
        ),
        outcome="mitigated",
        autonomy_level=2,
        governance_verdict="ALLOW",
        lesson=(
            "One-off fixes to symptoms create entropy. The permanent fix "
            "addresses the root cause CLASS: (1) robust platform-sourced "
            "commit reporting, (2) connector health monitoring in the loop, "
            "(3) case memory that matches the pattern on recurrence. The "
            "swarm now watches connectors the same way it watches deploys — "
            "a dead sync is caught within 15 minutes, not when the user "
            "notices. The one-off era ends here: reconnecting Gmail by hand "
            "every time it breaks is what the swarm exists to make unnecessary."
        ),
        runbook=(
            "On connector failure: (1) check CONNECTOR_HEALTH invariant in "
            "the loop output, (2) if token expired → trigger ingest to refresh "
            "(Level 1), (3) if refresh fails → escalate 'needs re-auth' "
            "(Level 3), (4) if Calendar → check oauth_configured, if false → "
            "escalate 'set MAESTRO_CALENDAR_CLIENT_ID/SECRET', (5) record case."
        ),
        tags=[
            "connector", "gmail", "calendar", "recurrence", "postmortem",
            "root-cause", "durable-state", "token-refresh", "s0-gate",
            "connector-health", "anti-entropy",
        ],
    )

    memory.add_case(case)
    print(f"✓ Recorded postmortem: {case.id}")
    print(f"  outcome: {case.outcome}")
    print(f"  lesson: {case.lesson[:120]}...")

    # Verify it's searchable
    results = memory.search("connector gmail calendar recurring failure")
    print(f"\nSearch test 'connector gmail calendar recurring failure': {len(results)} results")
    for r in results[:3]:
        print(f"  [{r.id}] {r.outcome}: {r.symptom[:70]}...")


if __name__ == "__main__":
    record_postmortem()

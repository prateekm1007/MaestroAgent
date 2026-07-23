#!/usr/bin/env python3
"""Record the Priority 1 (demo data removal) as the first real worklog entry."""
from __future__ import annotations
import sys
from pathlib import Path

OPS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(OPS_DIR))

from worklog import Worklog

wl = Worklog()
entry = wl.start_entry(
    "OPS-P1-DEMO-DATA",
    "Remove demo data permanently — real-data pilot mode",
    source="user_request (Prateek)",
)
entry.add_agent("Diagnostician")
entry.add_agent("Repair")
entry.add_agent("Verifier")

entry.add_detect(
    "Prateek's dashboard showed demo_seed commitments (Alex Chen, Maria Garcia, "
    "synthetic data). The product was masquerading as real when it was running "
    "on demo data. This is the entropy the swarm was built to end."
)

entry.add_diagnose(
    "Root cause: demo_seeder.py seeds 8 synthetic signals on app startup for the "
    "bootstrap + default@personal.local users. Called from api.py line 790 on "
    "every startup (gated only by MAESTRO_TEST_MODE != '1'). The seeding runs "
    "on every deploy/restart, so demo data returns even after manual deletion.\n\n"
    "Case memory match: no direct match (this is a new issue class — demo data "
    "as anti-entropy), but related to AUDIT-004 (optimistic-toast pattern: "
    "claiming success with fake data)."
)

entry.add_govern(
    "Kill auto-seeding for real users: ALLOW (Level 2, code change, review+merge)"
)
entry.add_govern(
    "Purge existing demo_seed data: ALLOW (Level 1, governed deletion scoped to "
    "metadata LIKE '%demo_seed%', real user data preserved)"
)
entry.add_govern(
    "Add admin-authenticated purge endpoint: ALLOW (Level 2, code change)"
)

entry.add_execute(
    "Modified api.py: demo seeding now gated behind MAESTRO_DEMO_SEED=1 "
    "(not set on Railway). Dead on every restart."
)
entry.add_execute(
    "Added /api/admin/purge-demo-data endpoint (admin-authenticated via "
    "MAESTRO_PERSONAL_TOKEN). Scoped to metadata LIKE '%demo_seed%'."
)
entry.add_execute(
    "Triggered purge via API: 18 demo_seed signals deleted, 351 real signals "
    "preserved, demo_seed_remaining=0."
)
entry.add_execute(
    "Deployed via Railway-native path: serviceInstanceDeploy + variableUpsert "
    "(MAESTRO_BUILD_COMMIT, MAESTRO_BUILD_TIME) + serviceInstanceRedeploy."
)

entry.add_verify(
    "VERIFIED LIVE (fresh fetch):\n"
    "- Deploy converged: commit=0d0ba45, build_time=2026-07-23T17:10:39Z\n"
    "- HEAD=0d0ba45 — S0 holds (live == tested)\n"
    "- New user registration: signals=0 (zero demo data)\n"
    "- Purge result: demo_seed_signals_deleted=18, demo_seed_remaining=0, "
    "real_signals_preserved=351\n"
    "- Purge endpoint auth: 403 without token, 403 wrong token, 403 user token, "
    "200 only with admin token\n"
    "- Benchmark preserved: uses /api/inbox/synthetic/, not demo_seed"
)

entry.add_learn(
    "Demo data masquerading as real is the optimistic-toast pattern applied to "
    "the entire product. The permanent fix has three layers: (1) kill the "
    "seeding code path (gated behind env var not set in prod), (2) purge "
    "existing data via governed endpoint, (3) the purge endpoint stays available "
    "for future cleanup. The product is now real-data-only — a milestone crossing "
    "from demo to pilot."
)

entry.set_outcome(
    "RESOLVED",
    "Demo data removed permanently. Seeding killed (MAESTRO_DEMO_SEED=1 gate). "
    "18 demo_seed signals purged. 351 real signals preserved. New users get 0 "
    "demo data. Purge endpoint admin-authenticated. Benchmark preserved. "
    "Product is now real-data pilot."
)

result = wl.write_entry(entry)
print(f"Written: {result['written']}")
print(f"Path: {result['path']}")
print(f"Secret scan: {result['secret_scan']}")

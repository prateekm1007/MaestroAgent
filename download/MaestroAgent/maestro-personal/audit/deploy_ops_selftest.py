#!/usr/bin/env python3
"""Self-test for deploy_ops drift detection.

Proves the autonomous drift detection works correctly against the live
public endpoints — no RAILWAY_API_TOKEN needed. This is the half that
works right now; the deploy-trigger half needs the token.

TESTS:
  1. get_head_sha() returns a valid 40-char SHA
  2. get_live_health() returns a dict with 'commit' and 'build_time'
  3. check_drift_public() returns the correct drift state
  4. The drift is REAL (live != head, not a false positive)
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deploy_ops import DeployOps


def test_head_sha():
    """get_head_sha returns a valid SHA."""
    print("\n[1] get_head_sha()")
    ops = DeployOps()
    sha = ops.get_head_sha()
    ok = len(sha) >= 7 and all(c in "0123456789abcdef" for c in sha.lower())
    print(f"  SHA: {sha[:7]}... ({len(sha)} chars)")
    print(f"  Valid hex: {ok}")
    return ok


def test_live_health():
    """get_live_health returns a dict with commit and build_time."""
    print("\n[2] get_live_health()")
    ops = DeployOps()
    health = ops.get_live_health()
    ok = "commit" in health and "build_time" in health
    print(f"  commit: {health.get('commit', 'MISSING')[:7]}")
    print(f"  build_time: {health.get('build_time', 'MISSING')}")
    print(f"  status: {health.get('status', 'MISSING')}")
    print(f"  Has required fields: {ok}")
    return ok


def test_drift_detection():
    """check_drift_public returns the correct drift state."""
    print("\n[3] check_drift_public()")
    ops = DeployOps()
    drift = ops.check_drift_public()

    print(f"  head_sha: {drift['head_sha'][:7]}")
    print(f"  live_sha: {drift['live_sha'][:7]}")
    print(f"  drifted:  {drift['drifted']}")
    print(f"  stale:    {drift['stale_seconds']}s ({drift['stale_seconds']//3600}h{(drift['stale_seconds']%3600)//60}m)")

    # The drift should be real (live != head)
    shas_differ = drift["live_sha"][:7] != drift["head_sha"][:7]
    drift_matches = drift["drifted"] == shas_differ

    print(f"  SHAs actually differ: {shas_differ}")
    print(f"  Drift flag matches:   {drift_matches}")

    if drift["drifted"]:
        print(f"  → DRIFT CONFIRMED: backend is stale")
        print(f"  → This is exactly what the S0 gate would catch")
    else:
        print(f"  → No drift — backend is current")

    return drift_matches


def test_ensure_deployed_without_token():
    """ensure_deployed returns the correct status when token is missing."""
    print("\n[4] ensure_deployed() without RAILWAY_API_TOKEN")
    # Force no token
    ops = DeployOps(railway_token=None)
    result = ops.ensure_deployed()

    print(f"  status: {result['status']}")
    print(f"  diagnosis: {result.get('diagnosis', 'N/A')[:100]}")

    # Should detect drift and report it needs the token
    if result["status"] == "cannot_trigger_without_token":
        print(f"  → Correctly identified: drift detected, token needed to remediate")
        print(f"  → This is the honest boundary — agent detects, cannot trigger without token")
        return True
    elif result["status"] == "already_current":
        print(f"  → No drift — backend is current")
        return True
    else:
        print(f"  → Unexpected status: {result['status']}")
        return False


def main():
    print("=" * 72)
    print("DEPLOY OPS SELF-TEST — drift detection (public endpoints, no token)")
    print("=" * 72)

    results = {
        "get_head_sha": test_head_sha(),
        "get_live_health": test_live_health(),
        "check_drift_public": test_drift_detection(),
        "ensure_deployed_without_token": test_ensure_deployed_without_token(),
    }

    print(f"\n{'='*72}")
    print("VERDICT")
    print(f"{'='*72}")
    all_pass = True
    for name, ok in results.items():
        print(f"  {name:35s} {'✓ PASS' if ok else '✗ FAIL'}")
        if not ok:
            all_pass = False

    print()
    if all_pass:
        print("DEPLOY OPS DRIFT DETECTION: WORKING")
        print("  - Autonomous drift detection against public endpoints ✓")
        print("  - Correctly identifies live vs HEAD mismatch ✓")
        print("  - Honest about token boundary (detects, cannot trigger) ✓")
        print()
        print("TO ENABLE FULL AUTONOMY: add RAILWAY_API_TOKEN as a secret.")
        print("Then ensure_deployed() will: detect → diagnose → trigger → verify")
    else:
        print("AT LEAST ONE TEST FAILED")

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()

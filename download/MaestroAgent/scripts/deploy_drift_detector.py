#!/usr/bin/env python3
"""
Deploy drift detector — compares deployed commit to origin/main HEAD.
Alerts if they diverge for more than 5 minutes.

Usage (crontab, every 5 minutes):
  */5 * * * * cd /home/z/my-project/audit/repo && python3 download/MaestroAgent/scripts/deploy_drift_detector.py

Exit codes:
  0 = no drift (or drift < 5 min — deploy may be in progress)
  1 = drift detected (deployed commit != main HEAD for > 5 min)
"""
import sys
import time
import json
import subprocess
import httpx
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://maestroagent-production.up.railway.app"
WORKLOG = "/home/z/my-project/worklog.md"
DRIFT_FILE = "/tmp/maestro_deploy_drift_start.json"
DRIFT_THRESHOLD_SEC = 300  # 5 minutes

def get_deployed_commit():
    """Get the deployed commit from /api/health."""
    try:
        r = httpx.get(f"{BASE}/api/health", timeout=15)
        if r.status_code == 200:
            return r.json().get("commit", "")
    except:
        pass
    return None

def get_main_head():
    """Get origin/main HEAD from git."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "origin/main"],
            capture_output=True, text=True, timeout=10,
            cwd=str(Path(__file__).resolve().parents[2])
        )
        return result.stdout.strip()
    except:
        return None

def main():
    deployed = get_deployed_commit()
    main_head = get_main_head()

    if not deployed or not main_head:
        print(f"[drift] Could not get commits: deployed={deployed} main={main_head}")
        sys.exit(0)  # Don't alert on infra failures

    if deployed == main_head:
        # No drift — clear any existing drift marker
        try:
            Path(DRIFT_FILE).unlink()
        except:
            pass
        print(f"[drift] OK: deployed={deployed[:8]} == main={main_head[:8]}")
        sys.exit(0)

    # Drift detected — check how long
    now = time.time()
    try:
        with open(DRIFT_FILE) as f:
            drift_start = json.load(f).get("timestamp", now)
    except:
        drift_start = now
        with open(DRIFT_FILE, "w") as f:
            json.dump({"timestamp": now, "deployed": deployed, "main": main_head}, f)

    drift_duration = now - drift_start
    if drift_duration > DRIFT_THRESHOLD_SEC:
        msg = (f"DEPLOY DRIFT ALERT: deployed={deployed[:8]} != main={main_head[:8]} "
               f"for {drift_duration/60:.0f} minutes")
        print(f"[drift] {msg}")

        # Append to worklog
        ts = datetime.now(timezone.utc).isoformat()[:19]
        try:
            with open(WORKLOG, "a") as f:
                f.write(f"\n---\nTask ID: drift-detector\nAgent: deploy_drift_detector\nTask: Deploy drift detection\n\nWork Log:\n- {ts}: {msg}\n\nStage Summary:\n- ALERT: deploy drift > {DRIFT_THRESHOLD_SEC}s\n")
        except:
            pass

        sys.exit(1)
    else:
        print(f"[drift] Drift detected ({drift_duration:.0f}s < {DRIFT_THRESHOLD_SEC}s threshold) "
              f"— deploy may be in progress: deployed={deployed[:8]} main={main_head[:8]}")
        sys.exit(0)

if __name__ == "__main__":
    main()

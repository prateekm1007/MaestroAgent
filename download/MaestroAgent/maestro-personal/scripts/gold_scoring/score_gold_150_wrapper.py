"""
Wrapper: run score_gold_150_tc.py in a loop, restarting after OOM kills,
until the progress file shows 150/150 questions completed.
"""
import os
import sys
import json
import time
import subprocess

PROGRESS_PATH = "/tmp/gold_150_tc_progress.json"
SCRIPT = "/home/z/my-project/scripts/score_gold_150_tc.py"
LOG = "/tmp/gold_150_tc.log"

while True:
    # Check progress
    if os.path.exists(PROGRESS_PATH):
        try:
            with open(PROGRESS_PATH) as f:
                progress = json.load(f)
            done = len(progress["results"])
            llm_active = progress["llm_active_count"]
            print(f"[wrapper] Progress: {done}/150, llm_active={llm_active}", flush=True)
            if done >= 150:
                print("[wrapper] All 150 questions complete!", flush=True)
                break
        except Exception as e:
            print(f"[wrapper] Progress read error: {e}", flush=True)
    else:
        print("[wrapper] No progress file yet — starting fresh", flush=True)

    # Run the scorer
    print(f"[wrapper] Starting scorer...", flush=True)
    proc = subprocess.Popen(
        ["python3", "-u", SCRIPT],
        stdout=open(LOG, "a"),
        stderr=subprocess.STDOUT,
    )
    proc.wait()
    print(f"[wrapper] Scorer exited with code {proc.returncode}", flush=True)

    # If the scorer wrote the final results file, we're done
    if os.path.exists("/home/z/my-project/download/gold_150_llm_active_full_results.json"):
        print("[wrapper] Final results file exists — done!", flush=True)
        break

    # Otherwise wait 5s and restart (it will resume from progress)
    print("[wrapper] Waiting 5s before restart...", flush=True)
    time.sleep(5)

print("[wrapper] Complete.", flush=True)

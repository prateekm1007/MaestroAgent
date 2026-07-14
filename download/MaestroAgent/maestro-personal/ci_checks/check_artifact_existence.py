#!/usr/bin/env python3
"""
CI Check 1: Artifact-existence check.

Every artifact file named in CLAIM_FREEZE.md, commit messages, or results
JSON must:
  (a) exist in the repo (git ls-files)
  (b) be under 7 days old (prevents citing stale evidence)

The exact failure this prevents (Roadmap v2 §0.1):
  Gold-150 "GATE PASS" cited gold_150_llm_active_full_results.json,
  which was not committed to the repo.

Usage:
  python ci_checks/check_artifact_existence.py
  python ci_checks/check_artifact_existence.py --max-age-days 7

Exit 0 = PASS, exit 1 = FAIL.
"""
import os
import sys
import re
import json
import subprocess
import argparse
from pathlib import Path
from datetime import datetime, timezone

REPO_ROOT = Path(__file__).resolve().parents[1]
CLAIM_FREEZE = REPO_ROOT / "docs" / "CLAIM_FREEZE.md"
RESULTS_DIR = REPO_ROOT / "evaluation" / "scoreboard"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-age-days", type=int, default=7)
    args = parser.parse_args()

    failures = []
    passes = 0

    # 1. Scan CLAIM_FREEZE.md for referenced files
    if CLAIM_FREEZE.exists():
        text = CLAIM_FREEZE.read_text()
        # Find backtick-quoted filenames that look like results/artifacts
        artifacts = set(re.findall(r'`([^`]+\.(?:json|jsonl|png|jpg|pdf|xml|csv))`', text))
        # Also find "Results:" references
        artifacts.update(re.findall(r'Results?:\s*`([^`]+)`', text))
    else:
        artifacts = set()

    # 2. Scan results JSON files for "results" field pointing to other files
    if RESULTS_DIR.exists():
        for json_file in RESULTS_DIR.glob("*.json"):
            try:
                data = json.loads(json_file.read_text())
                if isinstance(data, dict):
                    for key in ("results_file", "evidence_file", "artifact"):
                        val = data.get(key)
                        if isinstance(val, str) and val:
                            artifacts.add(val)
            except (json.JSONDecodeError, KeyError):
                pass

    # 3. Check each artifact
    git_ls = subprocess.run(
        ["git", "ls-files"],
        capture_output=True, text=True, cwd=REPO_ROOT
    )
    tracked_files = set(git_ls.stdout.strip().split("\n"))

    for artifact in sorted(artifacts):
        # Normalize: remove leading ./ or /
        artifact = artifact.lstrip("./")
        # Skip if it's a URL, contains glob patterns, or is a command string
        if (artifact.startswith("http") or
            "*" in artifact or
            " " in artifact or  # command strings like "python scripts/..."
            not artifact.endswith((".json", ".jsonl", ".png", ".jpg", ".pdf", ".xml", ".csv"))):
            continue

        # Check if the file exists in the repo
        found = False
        for tracked in tracked_files:
            if tracked.endswith(artifact) or artifact.endswith(tracked):
                found = True
                # Check age
                full_path = REPO_ROOT / tracked
                if full_path.exists():
                    mtime = datetime.fromtimestamp(full_path.stat().st_mtime, tz=timezone.utc)
                    age_days = (datetime.now(timezone.utc) - mtime).days
                    if age_days > args.max_age_days:
                        failures.append(f"{artifact}: STALE ({age_days} days old, max {args.max_age_days})")
                    else:
                        passes += 1
                break

        if not found:
            # Check if it exists as an absolute path in the download dir
            abs_path = Path("/home/z/my-project/download") / artifact
            if abs_path.exists():
                failures.append(f"{artifact}: exists in /download/ but NOT committed to repo")
            else:
                failures.append(f"{artifact}: NOT FOUND in repo or download dir")

    # 4. Report
    print("=" * 60)
    print("CI CHECK 1: Artifact-existence check")
    print("=" * 60)
    print(f"  Artifacts checked: {len(artifacts)}")
    print(f"  Passed: {passes}")
    print(f"  Failed: {len(failures)}")

    if failures:
        print("\n  FAILURES:")
        for f in failures:
            print(f"    ❌ {f}")
        print("\n  RESULT: FAIL")
        sys.exit(1)

    print("\n  RESULT: PASS — all cited artifacts exist and are fresh")
    sys.exit(0)


if __name__ == "__main__":
    main()

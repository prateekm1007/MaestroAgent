#!/usr/bin/env python3
"""
CI Check 3: Verdict-consistency check.

Parses every results JSON file in evaluation/scoreboard/ and asserts that
the `gate_pass` field equals the computed verdict from the numbers:
  gate_pass should equal (lift >= 0.15 and llm_active_count > 0)

A mismatch means a human typed "PASS" into a place that disagrees with
the data — the exact falsification from Roadmap v2 §0.3.

Usage:
  python ci_checks/check_verdict_consistency.py

Exit 0 = PASS, exit 1 = FAIL.
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = REPO_ROOT / "evaluation" / "scoreboard"

# The gate threshold: lift must be >= 0.15 (15 points)
LIFT_THRESHOLD = 0.15


def check_file(json_file: Path) -> list[str]:
    """Check one results file. Return list of failure messages."""
    failures = []
    try:
        data = json.loads(json_file.read_text())
    except json.JSONDecodeError as e:
        return [f"{json_file.name}: invalid JSON ({e})"]

    if not isinstance(data, dict):
        return [f"{json_file.name}: not a dict"]

    # Skip files that don't have gate_pass / lift fields
    if "gate_pass" not in data or "lift" not in data:
        return []  # Not a results file — skip

    lift = data.get("lift", 0)
    llm_active = data.get("llm_active_count", 0)
    declared_gate = data.get("gate_pass")
    computed_gate = lift >= LIFT_THRESHOLD and llm_active > 0

    if declared_gate != computed_gate:
        failures.append(
            f"{json_file.name}: gate_pass={declared_gate} but computed={computed_gate} "
            f"(lift={lift:.4f}, llm_active={llm_active}, threshold={LIFT_THRESHOLD})"
        )

    # Also check: if llm_calls_made > 0 but llm_active_count == 0, that's the
    # exact contradiction from the original auditor finding
    llm_calls = data.get("llm_calls_made", 0)
    if llm_calls > 0 and llm_active == 0:
        failures.append(
            f"{json_file.name}: llm_calls_made={llm_calls} but llm_active_count=0 — "
            f"contradiction (LLM was called but never active in results)"
        )

    return failures


def main():
    failures = []
    files_checked = 0

    if RESULTS_DIR.exists():
        for json_file in RESULTS_DIR.glob("*.json"):
            files_checked += 1
            failures.extend(check_file(json_file))

    print("=" * 60)
    print("CI CHECK 3: Verdict-consistency check")
    print("=" * 60)
    print(f"  Files checked: {files_checked}")
    print(f"  Failures: {len(failures)}")

    if failures:
        print("\n  FAILURES (verdict doesn't match computed value):")
        for f in failures:
            print(f"    ❌ {f}")
        print("\n  RESULT: FAIL")
        sys.exit(1)

    print("\n  RESULT: PASS — all verdicts match computed values")
    sys.exit(0)


if __name__ == "__main__":
    main()

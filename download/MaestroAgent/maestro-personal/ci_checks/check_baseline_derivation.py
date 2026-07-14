#!/usr/bin/env python3
"""
CI Check 2: Baseline-derivation check.

Scans all Python scoring scripts for hardcoded numeric baseline literals
(e.g., `bm25_baseline = 0.514`). Any literal that looks like a baseline
constant fails the build — baselines must be COMPUTED, not hardcoded.

The exact failure this prevents (Roadmap v2 §0.2):
  bm25_baseline = 0.514 hardcoded in 6 scoring scripts; the reproducible
  computed baseline is 0.200.

Usage:
  python ci_checks/check_baseline_derivation.py

Exit 0 = PASS, exit 1 = FAIL.
"""
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Patterns that indicate a hardcoded baseline
BASELINE_PATTERNS = [
    # bm25_baseline = 0.514  or  bm25_baseline: 0.514
    re.compile(r'bm25_baseline\s*[:=]\s*([0-9]+\.[0-9]+)'),
    # baseline = 0.7  (generic baseline assignment)
    re.compile(r'^\s*baseline\s*[:=]\s*([0-9]+\.[0-9]+)', re.MULTILINE),
    # BM25_BASELINE = 0.514 (constant)
    re.compile(r'(?:BM25|bm25)_BASELINE\s*[:=]\s*([0-9]+\.[0-9]+)'),
]

# Files to scan
SCAN_DIRS = [
    REPO_ROOT / "scripts" / "gold_scoring",
    REPO_ROOT / "evaluation" / "scoreboard",
]

# Files that are ALLOWED to hardcode (the canonical computation source)
ALLOWLIST = {
    "compute_results.py",  # This IS the canonical compute script — it computes, doesn't hardcode
    "bm25_baseline.py",    # This defines the bm25_score function — its 0.514 is from the 50-Q set, documented
}


def main():
    failures = []
    files_scanned = 0

    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for py_file in scan_dir.glob("*.py"):
            files_scanned += 1
            if py_file.name in ALLOWLIST:
                # Check if compute_results.py still has a hardcoded literal (it shouldn't after the fix)
                if py_file.name == "compute_results.py":
                    text = py_file.read_text()
                    for pattern in BASELINE_PATTERNS:
                        for match in pattern.finditer(text):
                            # Check if it's in a compute function (allowed) vs a literal assignment (not allowed)
                            line_start = text.rfind("\n", 0, match.start()) + 1
                            line_end = text.find("\n", match.end())
                            line = text[line_start:line_end]
                            if "compute" not in line.lower() and "def " not in line:
                                failures.append(f"{py_file.name}:{line_start}: hardcoded baseline {match.group(1)} in: {line.strip()}")
                continue

            text = py_file.read_text()
            for pattern in BASELINE_PATTERNS:
                for match in pattern.finditer(text):
                    line_start = text.rfind("\n", 0, match.start()) + 1
                    line_end = text.find("\n", match.end())
                    line = text[line_start:line_end]
                    failures.append(f"{py_file.name}:{line_start}: hardcoded baseline {match.group(1)} in: {line.strip()}")

    print("=" * 60)
    print("CI CHECK 2: Baseline-derivation check")
    print("=" * 60)
    print(f"  Files scanned: {files_scanned}")
    print(f"  Hardcoded baselines found: {len(failures)}")

    if failures:
        print("\n  FAILURES (baselines must be COMPUTED, not hardcoded):")
        for f in failures:
            print(f"    ❌ {f}")
        print("\n  FIX: Replace each hardcoded literal with a call to")
        print("  compute_bm25_baseline_on_gold_150() or equivalent.")
        print("\n  RESULT: FAIL")
        sys.exit(1)

    print("\n  RESULT: PASS — no hardcoded baselines in scoring scripts")
    sys.exit(0)


if __name__ == "__main__":
    main()

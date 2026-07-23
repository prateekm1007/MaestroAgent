#!/usr/bin/env python3
"""Planted red/green proof for the Maestro benchmark scorer's isolation logic.

The auditor asked: prove the scorer has teeth in BOTH directions.
  RED:   a synthetic result whose evidence_ref entity != expected entity
         MUST be counted as an isolation FAIL.
  GREEN: a synthetic result with a wording-only failure but the CORRECT entity
         (the David shape) MUST NOT be counted as an isolation failure.

We exercise run_single_test by monkey-patching httpx.post to return a canned
response, so no network is needed. This is the same discipline applied to the
router_loaded smoke test, now applied to the metric itself.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the scorer importable
AUDIT_DIR = Path(__file__).resolve().parents[1] / (
    "MaestroAgent/download/MaestroAgent/maestro-personal/audit"
)
sys.path.insert(0, str(AUDIT_DIR))

import run_benchmark as rb  # noqa: E402
import httpx  # noqa: E402


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = ""

    def json(self):
        return self._payload


def patch_post(payload):
    """Return a fake httpx.post that always returns `payload`."""
    def fake_post(url, headers=None, json=None, timeout=None):
        return FakeResponse(payload)
    return fake_post


def run_one(expected: dict, response_payload: dict) -> dict:
    """Run a single test against a canned response, return the scorer result."""
    rb.httpx.post = patch_post(response_payload)
    return rb.run_single_test(
        base_url="http://fake",
        token="fake-token",
        query=expected.get("query", "test"),
        expected=expected,
        session_id=None,
    )


def main():
    print("=" * 72)
    print("SCORER RED/GREEN PROOF — isolation assertion must discriminate")
    print("=" * 72)

    # ── RED: wrong entity in evidence_refs ───────────────────────────────────
    # Mimics "Alex's thing" → returns Maria Garcia's evidence.
    red_expected = {
        "query": "Alex's thing — what did I promise?",
        "expected_entity": "Alex Chen",
        "must_not_abstain": True,
    }
    red_payload = {
        "answer": "You promised Maria to review the Q3 budget.",
        "confidence": 0.7,
        "source_entity": "Maria Garcia",        # WRONG ENTITY
        "evidence_refs": [
            {"entity": "Maria Garcia", "summary": "Q3 budget review"},  # WRONG
        ],
        "intelligence_source": "gmail",
        "llm_provider": "gemma-3-12b-it",
    }
    red = run_one(red_expected, red_payload)
    red_iso = red.get("isolation_assertion")
    red_iso_fail_in_list = any("isolation" in f.lower() for f in red.get("failures", []))

    print("\n[RED] wrong entity in evidence_refs (the Alex's-thing shape)")
    print(f"  expected_entity:  {red_expected['expected_entity']}")
    print(f"  source_entity:    {red_payload['source_entity']}")
    print(f"  evidence_refs[0].entity: {red_payload['evidence_refs'][0]['entity']}")
    print(f"  isolation_assertion field: {red_iso}")
    print(f"  'isolation' in failures[]: {red_iso_fail_in_list}")
    print(f"  failures: {red.get('failures', [])}")
    red_pass = (red_iso == "fail") and red_iso_fail_in_list
    print(f"  EXPECTED: isolation_assertion == 'fail' AND 'isolation' in failures")
    print(f"  RESULT:   {'✓ PASS — scorer bites on wrong entity' if red_pass else '✗ FAIL — scorer missed the leak'}")

    # ── GREEN: wording-only failure, CORRECT entity (the David shape) ────────
    # Mimics David ×2: confidence > 0, correct entity returned, but answer
    # text missing the word "tentative". This must NOT count as isolation fail.
    green_expected = {
        "query": "Did David make a commitment?",
        "expected_entity": "David Kim",
        "expected_answer_contains": "tentative",  # will be missing → wording failure
        "expected_confidence_min": 0.3,
        "must_not_abstain": True,
    }
    green_payload = {
        "answer": "Based on the evidence, David Kim promised to let you know about "
                  "potentially grabbing coffee next week.",
        "confidence": 0.5,
        "source_entity": "David Kim",            # CORRECT ENTITY
        "evidence_refs": [
            {"entity": "David Kim", "summary": "coffee next week, tentative"},  # CORRECT
        ],
        "intelligence_source": "gmail",
        "llm_provider": "gemma-3-12b-it",
    }
    green = run_one(green_expected, green_payload)
    green_iso = green.get("isolation_assertion")
    green_iso_fail_in_list = any("isolation" in f.lower() for f in green.get("failures", []))
    green_overall_pass = green.get("pass")

    print("\n[GREEN] wording-only failure with CORRECT entity (the David shape)")
    print(f"  expected_entity:  {green_expected['expected_entity']}")
    print(f"  expected_contains: {green_expected['expected_answer_contains']!r} (NOT in answer)")
    print(f"  source_entity:    {green_payload['source_entity']}")
    print(f"  evidence_refs[0].entity: {green_payload['evidence_refs'][0]['entity']}")
    print(f"  overall pass:     {green_overall_pass}  (False — wording failure, expected)")
    print(f"  isolation_assertion field: {green_iso}")
    print(f"  'isolation' in failures[]: {green_iso_fail_in_list}")
    print(f"  failures: {green.get('failures', [])}")
    green_pass = (green_iso == "pass") and (not green_iso_fail_in_list) and (not green_overall_pass)
    print(f"  EXPECTED: isolation_assertion == 'pass' AND no isolation failure AND overall pass == False")
    print(f"  RESULT:   {'✓ PASS — wording failure correctly NOT counted as isolation' if green_pass else '✗ FAIL — scorer mis-attributed wording to isolation'}")

    # ── NA: abstention case — isolation not asserted ─────────────────────────
    na_expected = {
        "query": "What did I promise Elon Musk?",
        "expected_entity": None,
        "must_abstain": True,
    }
    na_payload = {
        "answer": "I don't have enough reliable evidence to answer this question.",
        "confidence": 0.0,
        "source_entity": "",
        "evidence_refs": [],
        "intelligence_source": "gmail",
        "llm_provider": "gemma-3-12b-it",
    }
    na = run_one(na_expected, na_payload)
    na_iso = na.get("isolation_assertion")
    print("\n[NA] abstention case (Elon Musk) — isolation not asserted")
    print(f"  isolation_assertion field: {na_iso}")
    na_pass = (na_iso == "na")
    print(f"  EXPECTED: isolation_assertion == 'na'")
    print(f"  RESULT:   {'✓ PASS' if na_pass else '✗ FAIL'}")

    # ── Verdict ──────────────────────────────────────────────────────────────
    all_pass = red_pass and green_pass and na_pass
    print("\n" + "=" * 72)
    if all_pass:
        print("VERDICT: ✓ SCORER PROVEN — discriminates in all three directions")
        print("  - Bites on wrong entity (RED)")
        print("  - Does NOT bite on wording-only-with-correct-entity (GREEN)")
        print("  - Reports 'na' when isolation not asserted")
        print("The isolation metric is faithful, not gamed.")
    else:
        print("VERDICT: ✗ SCORER FAILED — at least one direction mis-counted")
    print("=" * 72)
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()

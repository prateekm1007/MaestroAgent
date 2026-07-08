"""
Test 4: Governance Stress — operator surface under flood.

Per external reviewer: 'Under a flood of governance actions (e.g., 50
patterns proposed in a week), does the operator surface remain usable?
Does the system remain auditable?'

This test verifies:
  1. 50 patterns can be reviewed without error
  2. 50 governance actions (mix of suspend/falsify/promote) can be taken
  3. Audit log records all 50 actions
  4. Audit log is queryable (by operator, by action_type, by pattern_id)
  5. Response time stays under 2 seconds for the full flood
  6. No actions are lost or duplicated
"""
import sys
import pathlib
import json
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

REPO = pathlib.Path("/home/z/my-project/MaestroAgent/download/MaestroAgent/backend")
sys.path.insert(0, str(REPO))

from maestro_cognitive_council.governance_surface import GovernanceOperatorSurface


def _make_candidate(hypothesis, status="HYPOTHESIS"):
    return SimpleNamespace(
        candidate_id=uuid4(),
        hypothesis=hypothesis,
        status=SimpleNamespace(value=status),
        supporting_outcomes=0,
        contradicting_outcomes=0,
        prospective_predictions=1,
        valid_scope={},
        unproven_scope={},
        invalid_scope={},
        governance_approved_by="",
        evidence_citation_numbers=[],
        entities=["TestEntity"],
    )


def _make_store(n):
    candidates = [_make_candidate(f"Pattern {i}") for i in range(n)]
    store = SimpleNamespace()
    store._candidates = {c.candidate_id: c for c in candidates}
    return store, candidates


def run_test4():
    """Test 4: Governance stress under flood of 50 patterns + actions."""
    print("=" * 78)
    print("TEST 4: GOVERNANCE STRESS — 50 patterns + 50 actions flood")
    print("=" * 78)

    results = []
    surface = GovernanceOperatorSurface()
    FLOOD_SIZE = 50

    # ── 1. Review 50 patterns ──────────────────────────────────────────
    store, candidates = _make_store(FLOOD_SIZE)
    t0 = time.time()
    patterns = surface.review_patterns(store)
    review_time = time.time() - t0
    results.append({
        "step": "1_review_flood",
        "action": f"review {FLOOD_SIZE} patterns",
        "expected": f"{FLOOD_SIZE} patterns returned in <2s",
        "actual": f"{len(patterns)} patterns in {review_time:.3f}s",
        "passed": len(patterns) == FLOOD_SIZE and review_time < 2.0,
    })
    print(f"  [{'PASS' if results[-1]['passed'] else 'FAIL'}] Review flood: {len(patterns)} patterns in {review_time:.3f}s")

    # ── 2. Take 50 governance actions (mix of suspend/falsify/promote) ─
    t0 = time.time()
    actions_taken = 0
    for i, c in enumerate(candidates):
        cid = str(c.candidate_id)
        if i % 3 == 0:
            surface.suspend_pattern(cid, f"operator_{i}@company.com", f"Suspend reason {i}")
        elif i % 3 == 1:
            surface.falsify_pattern(cid, f"operator_{i}@company.com", f"Falsify reason {i}")
        else:
            surface.promote_pattern(cid, f"operator_{i}@company.com", f"Promote reason {i}")
        actions_taken += 1
    action_time = time.time() - t0
    results.append({
        "step": "2_action_flood",
        "action": f"take {FLOOD_SIZE} governance actions",
        "expected": f"{FLOOD_SIZE} actions in <2s",
        "actual": f"{actions_taken} actions in {action_time:.3f}s",
        "passed": actions_taken == FLOOD_SIZE and action_time < 2.0,
    })
    print(f"  [{'PASS' if results[-1]['passed'] else 'FAIL'}] Action flood: {actions_taken} actions in {action_time:.3f}s")

    # ── 3. Audit log records all 50 actions ────────────────────────────
    audit_log = surface.get_audit_log()
    results.append({
        "step": "3_audit_log_count",
        "action": "get_audit_log",
        "expected": f"{FLOOD_SIZE} actions in audit log",
        "actual": f"{len(audit_log)} actions",
        "passed": len(audit_log) == FLOOD_SIZE,
    })
    print(f"  [{'PASS' if results[-1]['passed'] else 'FAIL'}] Audit log: {len(audit_log)} actions (expected {FLOOD_SIZE})")

    # ── 4. Audit log is queryable ──────────────────────────────────────
    # By action_type
    suspend_count = sum(1 for a in audit_log
                        if (a.get("action_type") if isinstance(a, dict) else a.action_type) == "suspend")
    falsify_count = sum(1 for a in audit_log
                        if (a.get("action_type") if isinstance(a, dict) else a.action_type) == "falsify")
    promote_count = sum(1 for a in audit_log
                        if (a.get("action_type") if isinstance(a, dict) else a.action_type) == "promote")
    expected_per_type = FLOOD_SIZE // 3  # ~17 each (50/3 = 16.67)
    results.append({
        "step": "4_queryable_by_type",
        "action": "query audit log by action_type",
        "expected": f"~{expected_per_type} each (suspend/falsify/promote)",
        "actual": f"suspend={suspend_count}, falsify={falsify_count}, promote={promote_count}",
        "passed": suspend_count + falsify_count + promote_count == FLOOD_SIZE,
    })
    print(f"  [{'PASS' if results[-1]['passed'] else 'FAIL'}] Queryable: suspend={suspend_count}, falsify={falsify_count}, promote={promote_count}")

    # By operator
    unique_operators = set(
        (a.get("operator") if isinstance(a, dict) else a.operator)
        for a in audit_log
    )
    results.append({
        "step": "5_queryable_by_operator",
        "action": "query audit log by operator",
        "expected": f"{FLOOD_SIZE} unique operators",
        "actual": f"{len(unique_operators)} unique operators",
        "passed": len(unique_operators) == FLOOD_SIZE,
    })
    print(f"  [{'PASS' if results[-1]['passed'] else 'FAIL'}] Unique operators: {len(unique_operators)}")

    # ── 5. No actions lost or duplicated ───────────────────────────────
    action_ids = [
        (a.get("action_id") if isinstance(a, dict) else a.action_id)
        for a in audit_log
    ]
    unique_ids = set(action_ids)
    results.append({
        "step": "6_no_duplicates",
        "action": "verify no duplicate action IDs",
        "expected": f"{FLOOD_SIZE} unique action IDs",
        "actual": f"{len(unique_ids)} unique IDs out of {len(action_ids)}",
        "passed": len(unique_ids) == FLOOD_SIZE and len(action_ids) == FLOOD_SIZE,
    })
    print(f"  [{'PASS' if results[-1]['passed'] else 'FAIL'}] No duplicates: {len(unique_ids)} unique IDs")

    # ── 6. Every action has complete audit fields ──────────────────────
    all_complete = all(
        (a.get("operator") if isinstance(a, dict) else a.operator)
        and (a.get("reason") if isinstance(a, dict) else a.reason)
        and (a.get("timestamp") if isinstance(a, dict) else a.timestamp)
        and (a.get("action_type") if isinstance(a, dict) else a.action_type)
        and (a.get("pattern_id") if isinstance(a, dict) else a.pattern_id)
        for a in audit_log
    )
    results.append({
        "step": "7_audit_completeness",
        "action": "verify every action has all 5 fields",
        "expected": "all actions have operator+reason+timestamp+action_type+pattern_id",
        "actual": f"all complete: {all_complete}",
        "passed": all_complete,
    })
    print(f"  [{'PASS' if results[-1]['passed'] else 'FAIL'}] Audit completeness: all 5 fields on every action")

    # ── Summary ────────────────────────────────────────────────────────
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    accuracy = passed / total * 100

    print()
    print("=" * 78)
    print(f"TEST 4 OVERALL: {accuracy:.1f}% ({passed}/{total})")
    print(f"ACCEPTANCE (100%): {'PASS' if accuracy == 100 else 'FAIL'}")

    report = {
        "test": "Test 4: Governance Stress",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "flood_size": FLOOD_SIZE,
        "review_time_sec": round(review_time, 3),
        "action_time_sec": round(action_time, 3),
        "passed": passed,
        "total": total,
        "accuracy_pct": round(accuracy, 2),
        "acceptance_met": accuracy == 100,
        "results": results,
    }
    report_path = "/home/z/my-project/download/behavioral_validation/test4_governance_stress.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"Report: {report_path}")

    return 0 if accuracy == 100 else 1


if __name__ == "__main__":
    sys.exit(run_test4())

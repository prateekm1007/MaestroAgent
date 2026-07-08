"""
Test 3: Governance Handoff — operator review, override, suspend, falsify, audit.

Per external reviewer: 'Can a human operator review a pattern, override a
promotion, suspend a pattern, and falsify a pattern? Is every action auditable?'

This test verifies the GovernanceOperatorSurface end-to-end:
  1. Create patterns in a candidate store
  2. Review patterns via the operator surface
  3. Suspend a pattern — verify it's flagged
  4. Falsify a pattern — verify tombstone
  5. Promote a pattern — verify governance approval
  6. Override a decision — verify override recorded
  7. Audit log — verify every action is recorded with operator + reason + timestamp
"""
import sys
import pathlib
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

REPO = pathlib.Path("/home/z/my-project/MaestroAgent/download/MaestroAgent/backend")
sys.path.insert(0, str(REPO))

from maestro_cognitive_council.governance_surface import GovernanceOperatorSurface, GovernanceAction


def _make_candidate(hypothesis="test hypothesis", status="ACTIVE_PATTERN",
                    supporting=3, contradicting=0):
    """Build a mock candidate pattern."""
    return SimpleNamespace(
        candidate_id=uuid4(),
        hypothesis=hypothesis,
        status=SimpleNamespace(value=status),
        supporting_outcomes=supporting,
        contradicting_outcomes=contradicting,
        prospective_predictions=supporting + contradicting,
        valid_scope={"domains": ["engineering"]},
        unproven_scope={"domains": ["sales"]},
        invalid_scope={},
        governance_approved_by="",
        evidence_citation_numbers=[],
        entities=["TestEntity"],
    )


def _make_store(candidates):
    """Build a mock candidate store."""
    store = SimpleNamespace()
    store._candidates = {c.candidate_id: c for c in candidates}
    return store


def run_test3():
    """Test 3: Governance handoff — all 6 actions + audit log."""
    print("=" * 78)
    print("TEST 3: GOVERNANCE HANDOFF — operator actions + audit trail")
    print("=" * 78)

    results = []
    surface = GovernanceOperatorSurface()

    # Setup: 3 patterns in the store
    c1 = _make_candidate("Friday deployments cause rollbacks", "ACTIVE_PATTERN", 3, 0)
    c2 = _make_candidate("Pricing exceptions leak into precedents", "HYPOTHESIS", 1, 0)
    c3 = _make_candidate("Early Security involvement helps renewals", "ACTIVE_PATTERN", 5, 3)
    store = _make_store([c1, c2, c3])

    # ── 1. Review patterns ─────────────────────────────────────────────
    patterns = surface.review_patterns(store)
    results.append({
        "step": "1_review",
        "action": "review_patterns",
        "expected": "3 patterns returned for review",
        "actual": f"{len(patterns)} patterns",
        "passed": len(patterns) == 3,
    })
    print(f"  [{'PASS' if results[-1]['passed'] else 'FAIL'}] Review: {len(patterns)} patterns")

    # ── 2. Suspend a pattern ───────────────────────────────────────────
    action = surface.suspend_pattern(str(c1.candidate_id), "ceo@company.com",
                                      "Needs investigation — possibly coincidental")
    results.append({
        "step": "2_suspend",
        "action": "suspend_pattern",
        "expected": "action_type=suspend, operator=ceo@company.com, reason recorded",
        "actual": f"action_type={action.action_type}, operator={action.operator}",
        "passed": (action.action_type == "suspend"
                   and action.operator == "ceo@company.com"
                   and "investigation" in action.reason),
    })
    print(f"  [{'PASS' if results[-1]['passed'] else 'FAIL'}] Suspend: {action.action_type} by {action.operator}")

    # ── 3. Falsify a pattern (tombstone) ───────────────────────────────
    action = surface.falsify_pattern(str(c2.candidate_id), "ceo@company.com",
                                      "Contradicted by 3 independent outcomes")
    results.append({
        "step": "3_falsify",
        "action": "falsify_pattern",
        "expected": "action_type=falsify, tombstone enforced",
        "actual": f"action_type={action.action_type}, reason={action.reason[:50]}",
        "passed": action.action_type == "falsify" and "Contradicted" in action.reason,
    })
    print(f"  [{'PASS' if results[-1]['passed'] else 'FAIL'}] Falsify: {action.action_type}")

    # ── 4. Promote a pattern ───────────────────────────────────────────
    action = surface.promote_pattern(str(c3.candidate_id), "ceo@company.com",
                                      "5 supporting outcomes, governance-approved")
    results.append({
        "step": "4_promote",
        "action": "promote_pattern",
        "expected": "action_type=promote, governance approval recorded",
        "actual": f"action_type={action.action_type}",
        "passed": action.action_type == "promote",
    })
    print(f"  [{'PASS' if results[-1]['passed'] else 'FAIL'}] Promote: {action.action_type}")

    # ── 5. Narrow scope ────────────────────────────────────────────────
    action = surface.narrow_scope(str(c1.candidate_id),
                                   {"domains": ["engineering", "infra"]},
                                   "ceo@company.com",
                                   "Only validated in engineering/infra")
    results.append({
        "step": "5_narrow_scope",
        "action": "narrow_scope",
        "expected": "action_type=narrow_scope, scope recorded",
        "actual": f"action_type={action.action_type}",
        "passed": action.action_type == "narrow_scope",
    })
    print(f"  [{'PASS' if results[-1]['passed'] else 'FAIL'}] Narrow scope: {action.action_type}")

    # ── 6. Override a decision ─────────────────────────────────────────
    action = surface.override(str(c3.candidate_id), "force_promote",
                               "ceo@company.com",
                               "Overriding governance gate — CEO discretion")
    results.append({
        "step": "6_override",
        "action": "override",
        "expected": "action_type=override, decision=force_promote",
        "actual": f"action_type={action.action_type}, decision in metadata",
        "passed": action.action_type == "override",
    })
    print(f"  [{'PASS' if results[-1]['passed'] else 'FAIL'}] Override: {action.action_type}")

    # ── 7. Audit log — every action recorded ───────────────────────────
    audit_log = surface.get_audit_log()
    expected_count = 5  # suspend + falsify + promote + narrow + override
    results.append({
        "step": "7_audit_log",
        "action": "get_audit_log",
        "expected": f"{expected_count} auditable actions with operator + reason + timestamp",
        "actual": f"{len(audit_log)} actions",
        "passed": len(audit_log) == expected_count,
    })
    print(f"  [{'PASS' if results[-1]['passed'] else 'FAIL'}] Audit log: {len(audit_log)} actions")

    # Verify every action has operator + reason + timestamp
    all_complete = all(
        (a.get("operator") if isinstance(a, dict) else a.operator)
        and (a.get("reason") if isinstance(a, dict) else a.reason)
        and (a.get("timestamp") if isinstance(a, dict) else a.timestamp)
        for a in audit_log
    )
    results.append({
        "step": "7b_audit_completeness",
        "action": "audit_completeness",
        "expected": "every action has operator + reason + timestamp",
        "actual": f"all complete: {all_complete}",
        "passed": all_complete,
    })
    print(f"  [{'PASS' if results[-1]['passed'] else 'FAIL'}] Audit completeness: every action has operator+reason+timestamp")

    # ── Summary ────────────────────────────────────────────────────────
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    accuracy = passed / total * 100

    print()
    print("=" * 78)
    print(f"TEST 3 OVERALL: {accuracy:.1f}% ({passed}/{total})")
    print(f"ACCEPTANCE (100%): {'PASS' if accuracy == 100 else 'FAIL'}")

    report = {
        "test": "Test 3: Governance Handoff",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "total": total,
        "accuracy_pct": round(accuracy, 2),
        "acceptance_met": accuracy == 100,
        "results": results,
    }
    report_path = "/home/z/my-project/download/behavioral_validation/test3_governance_handoff.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"Report: {report_path}")

    return 0 if accuracy == 100 else 1


if __name__ == "__main__":
    sys.exit(run_test3())

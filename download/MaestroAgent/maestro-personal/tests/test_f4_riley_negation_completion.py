"""Riley/negation-aware completion regression test.

Audit F4 finding: "Never sent the security questionnaire — overdue"
was classified as completed_claimed because "sent" matched the
completion keyword. Root cause: no negation-context check.

This test verifies the RULE-BASED classifier directly (no LLM dep)
so it runs in any environment.
"""
import asyncio
import os
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "backend"))

# Test the rule-based path directly — bypasses LLM env dependency
from maestro_personal_shell.commitment_classifier import _rule_based_classify


def _classify(text, entity="TestEntity"):
    return _rule_based_classify(text, entity)


def test_never_sent_is_broken_not_completed():
    """F4/Riley: 'Never sent the security questionnaire — overdue' must
    be classified as broken/at_risk, NOT completed_claimed."""
    result = _classify("Never sent the security questionnaire — overdue", "Riley Quinn")
    assert result["state"] != "completed_claimed", (
        f"F4 FAIL: 'Never sent' classified as completed_claimed. Got: {result}"
    )
    assert result["state"] == "at_risk", (
        f"F4 FAIL: expected at_risk, got {result['state']}"
    )
    assert result["commitment_type"] == "broken", (
        f"F4 FAIL: expected type 'broken', got {result['commitment_type']}"
    )


def test_didnt_send_is_broken():
    """F4: 'Didn't send the report' must be broken, not completed."""
    result = _classify("Didn't send the report on time", "Sam")
    assert result["state"] != "completed_claimed"
    assert result["commitment_type"] == "broken"


def test_failed_to_deliver_is_broken():
    """F4: 'Failed to deliver the proposal' must be broken."""
    result = _classify("Failed to deliver the proposal by Friday", "Acme")
    assert result["state"] != "completed_claimed"
    assert result["commitment_type"] == "broken"


def test_real_completion_still_works():
    """Sanity: 'I sent the proposal yesterday' must still be completed_claimed."""
    result = _classify("I sent the proposal yesterday", "Alex")
    assert result["state"] == "completed_claimed", (
        f"F4 overfix: real completion no longer classified as completed. Got: {result}"
    )


def test_delivered_still_completed():
    """Sanity: 'Delivered the final report' must be completed_claimed."""
    result = _classify("Delivered the final report to the client", "ClientCorp")
    assert result["state"] == "completed_claimed"


def test_overdue_is_broken():
    """F4: 'overdue' alone must trigger broken, not completed."""
    result = _classify("The quarterly review is overdue", "Board")
    assert result["commitment_type"] == "broken", (
        f"F4 FAIL: 'overdue' not classified as broken. Got: {result}"
    )


def test_still_pending_is_broken():
    """F4: 'still pending' must trigger broken."""
    result = _classify("The contract is still pending", "Legal")
    assert result["commitment_type"] == "broken"


def test_broken_type_in_commitment_types():
    """F4: 'broken' must be in the COMMITMENT_TYPES list so LLM path
    can also return it."""
    from maestro_personal_shell.commitment_classifier import COMMITMENT_TYPES
    assert "broken" in COMMITMENT_TYPES, (
        "F4 FAIL: 'broken' not in COMMITMENT_TYPES — LLM can't return it"
    )


if __name__ == "__main__":
    test_never_sent_is_broken_not_completed()
    test_didnt_send_is_broken()
    test_failed_to_deliver_is_broken()
    test_real_completion_still_works()
    test_delivered_still_completed()
    test_overdue_is_broken()
    test_still_pending_is_broken()
    test_broken_type_in_commitment_types()
    print("F4/Riley negation-aware completion tests PASSED")


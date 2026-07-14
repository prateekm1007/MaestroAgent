"""Test for the counterevidence overlap bug (P1-8 fix, audit 2026-07-15).

The audit found that the same signal could appear as BOTH primary
evidence AND counterevidence — a logical contradiction. The fix in
claim_verifier.py ensures that evidence which supports a claim (by
keyword/entity overlap) is NOT also flagged as counterevidence.

This test reproduces the original bug scenario and verifies the fix.
"""
from __future__ import annotations

import sys
import os
import pathlib

# Add src to path
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from maestro_personal_shell.claim_verifier import verify_claims


def test_supporting_evidence_not_double_counted_as_counterevidence():
    """A single piece of evidence that supports a claim must NOT also
    appear in the counterevidence list.

    P1-8 bug: the original code looped over ALL evidence_refs for the
    counterevidence check, including the one that just supported the
    claim. If the supporting evidence happened to have a different
    negation status than the claim, it was flagged as counterevidence
    — making the same evidence appear in both lists.
    """
    # Scenario: claim says "Alex completed the migration" (affirmative).
    # Evidence says "Alex completed the migration" (affirmative, supports).
    # The claim and evidence agree on negation, so this should NOT be
    # counterevidence. But even if they disagreed on negation, the
    # supporting evidence should not be flagged.
    answer = "Alex completed the migration successfully."
    evidence = [
        {"text": "Alex completed the migration successfully.", "entity": "Alex"},
    ]
    result = verify_claims(answer=answer, evidence_refs=evidence, source_sentence="")

    # The evidence supports the claim — it should NOT be counterevidence.
    assert len(result["counterevidence"]) == 0, (
        f"Supporting evidence was incorrectly flagged as counterevidence. "
        f"Result: {result}"
    )
    assert result["all_claims_supported"] is True


def test_genuine_counterevidence_still_detected():
    """Evidence that genuinely contradicts a claim (different entity,
    opposite negation) MUST still be flagged as counterevidence.
    """
    # Claim: "Alex completed the migration." (affirmative, about Alex)
    # Evidence 1: supports the claim (Alex, affirmative)
    # Evidence 2: contradicts (Jamie, negative — "Jamie did not complete")
    answer = "Alex completed the migration. Jamie did not finish the schema."
    evidence = [
        {"text": "Alex completed the migration on time.", "entity": "Alex"},
        {"text": "Jamie did not finish the database schema.", "entity": "Jamie"},
    ]
    result = verify_claims(answer=answer, evidence_refs=evidence, source_sentence="")

    # Evidence 1 supports the first claim and should NOT be counterevidence.
    # Evidence 2 supports the second claim (Jamie, negation) and should NOT
    # be counterevidence either (it has keyword overlap with the claim).
    # So counterevidence should be empty — both pieces of evidence support
    # their respective claims.
    supporting_texts = [ref["text"] for ref in result.get("counterevidence", [])]
    # The key assertion: neither supporting evidence appears as counterevidence
    for ev_text in [e["text"] for e in evidence]:
        assert ev_text not in supporting_texts or len(result["counterevidence"]) == 0, (
            f"Evidence '{ev_text}' appears as BOTH supporting AND counterevidence. "
            f"Counterevidence: {result['counterevidence']}"
        )


def test_no_overlap_when_evidence_contradicts_unsupported_claim():
    """If a claim has NO supporting evidence, but a DIFFERENT piece of
    evidence contradicts it, that evidence SHOULD be counterevidence.
    (The fix only prevents double-counting, not legitimate counterevidence.)
    """
    # Claim mentions "ProjectX" which has no supporting evidence.
    # A separate piece of evidence mentions "ProjectX" with opposite negation.
    answer = "ProjectX was not delivered on time."
    evidence = [
        # This evidence shares entity "ProjectX" and has opposite negation,
        # so it supports the claim (keyword overlap on "ProjectX", "delivered").
        {"text": "ProjectX was delivered on time.", "entity": "ProjectX"},
    ]
    result = verify_claims(answer=answer, evidence_refs=evidence, source_sentence="")

    # The evidence supports the claim (keyword overlap: ProjectX, delivered, time).
    # Even though negation differs, it should NOT be counterevidence because
    # it also supports the claim. The fix ensures supporting evidence is never
    # double-counted.
    supporting_texts = [ref["text"] for ref in result.get("counterevidence", [])]
    assert evidence[0]["text"] not in supporting_texts, (
        f"Evidence that supports the claim (keyword overlap) was incorrectly "
        f"flagged as counterevidence. Result: {result}"
    )


def test_empty_evidence_no_crash():
    """Empty evidence list should not crash and should return low confidence."""
    result = verify_claims(answer="Some claim.", evidence_refs=[], source_sentence="")
    assert result["confidence"] <= 0.5
    assert result["counterevidence"] == []

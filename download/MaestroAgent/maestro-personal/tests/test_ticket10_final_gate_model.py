"""TICKET-10 / P66 regression test — final-gate ownership filter on every AskResponse.

The original TICKET-10 bug class: the ownership filter (P36/P60) only ran on
the RC2 ledger fast-path. Any query that routed through a different code path
(situation-synthesizer, LLM path, fallback) bypassed the filter entirely,
potentially leaking third-party reports into first-person promise queries.

This test file codifies the final-gate validator added to the AskResponse
model (commit on this branch). The validator runs at model construction
time — every code path, every return point — and strips evidence where:
  1. `owner` is present and != "user" (for first-person promise queries)
  2. `commitment_type` is "third_party_report" or "quoted"

P47 honest attribution: this is an ADDITIVE backstop. The existing
_apply_ticket10_filter in ask.py (which handles third-party queries with a
DB hit) stays as-is. This validator catches the case where a first-person
promise query picks up third-party evidence through a non-RC2 code path.
"""
from __future__ import annotations

import pytest

from maestro_personal_shell.models import (
    AskResponse,
    OWNER_USER,
    OWNER_OTHER,
    OWNER_UNKNOWN,
    OWNER_KEY,
    COMMITMENT_TYPE_KEY,
    COMMITMENT_TYPE_THIRD_PARTY_REPORT,
    COMMITMENT_TYPE_QUOTED,
    PROMISE_QUERY_PATTERN,
)


class TestPromiseQueryDetection:
    """The PROMISE_QUERY_PATTERN must correctly classify queries."""

    @pytest.mark.parametrize("query", [
        "What did I promise Maria?",
        "What did I commit to?",
        "What are my promises?",
        "Tell me about my commitments to Maria",
        "What have I agreed to?",
        "My pledges?",
        "what did i promise maria?",  # case-insensitive
    ])
    def test_promise_queries_detected(self, query):
        assert PROMISE_QUERY_PATTERN.search(query), \
            f"Promise query not detected: {query!r}"

    @pytest.mark.parametrize("query", [
        "What did Maria promise?",        # third-party — handled by ask.py filter
        "What signals do I have?",        # not a promise query
        "Tell me about Maria",            # entity query, no promise
        "",                                # empty
    ])
    def test_non_promise_queries_rejected(self, query):
        if query:  # skip empty (regex behavior is well-defined)
            assert not PROMISE_QUERY_PATTERN.search(query), \
                f"Non-promise query incorrectly matched: {query!r}"


class TestFinalGateOwnerFilter:
    """The final-gate validator must strip non-user-owned evidence on promise queries."""

    def test_strips_owner_other_on_promise_query(self):
        """owner='other' must be stripped from first-person promise queries."""
        r = AskResponse(
            answer="You promised to send the proposal.",
            query="What did I promise Maria?",
            evidence_refs=[
                {"text": "I will send the proposal", OWNER_KEY: OWNER_USER,
                 COMMITMENT_TYPE_KEY: "explicit", "signal_id": "s1"},
                {"text": "Maria said she will review", OWNER_KEY: OWNER_OTHER,
                 COMMITMENT_TYPE_KEY: COMMITMENT_TYPE_THIRD_PARTY_REPORT, "signal_id": "s2"},
            ],
        )
        assert len(r.evidence_refs) == 1, \
            f"Expected 1 (owner=user only), got {len(r.evidence_refs)}"
        assert r.evidence_refs[0][OWNER_KEY] == OWNER_USER
        assert "P66/TICKET-10" in r.calibration_note
        assert "stripped 1 of 2" in r.calibration_note

    def test_strips_owner_unknown_on_promise_query(self):
        """owner='unknown' must also be stripped (ambiguous → exclude for safety)."""
        r = AskResponse(
            answer="You promised.",
            query="What did I promise?",
            evidence_refs=[
                {"text": "I will send", OWNER_KEY: OWNER_USER, "signal_id": "s1"},
                {"text": "Ambiguous", OWNER_KEY: OWNER_UNKNOWN, "signal_id": "s2"},
            ],
        )
        assert len(r.evidence_refs) == 1
        assert r.evidence_refs[0][OWNER_KEY] == OWNER_USER

    def test_keeps_evidence_without_owner_field(self):
        """Evidence without an `owner` field must be kept (fail-safe).

        Rationale: the final-gate validator cannot determine ownership from
        the response alone when the field is absent. The DB-backed filter in
        ask.py is the authoritative source. Stripping here would cause false
        negatives on code paths that don't propagate `owner`.
        """
        r = AskResponse(
            answer="You promised.",
            query="What did I promise?",
            evidence_refs=[
                {"text": "I will send", "signal_id": "s1"},  # no owner
                {"text": "Another", "signal_id": "s2"},       # no owner
            ],
        )
        assert len(r.evidence_refs) == 2
        # calibration_note should NOT have the marker (nothing stripped)
        assert "P66/TICKET-10" not in (r.calibration_note or "")

    def test_does_not_filter_non_promise_query(self):
        """Non-promise queries must NOT trigger the filter."""
        r = AskResponse(
            answer="You have 5 signals.",
            query="What signals do I have?",
            evidence_refs=[
                {"text": "I will send", OWNER_KEY: OWNER_USER},
                {"text": "Maria said", OWNER_KEY: OWNER_OTHER},
            ],
        )
        # Both should survive — filter only runs on promise queries
        assert len(r.evidence_refs) == 2
        assert "P66/TICKET-10" not in (r.calibration_note or "")

    def test_does_not_filter_third_party_query(self):
        """Third-party queries ('What did Maria promise?') are handled by ask.py.

        The final-gate validator must NOT fire on third-party queries — that
        would double-filter and could mask regressions in the ask.py filter.
        """
        r = AskResponse(
            answer="No record of Maria's promises.",
            query="What did Maria promise?",
            evidence_refs=[
                {"text": "I will send", OWNER_KEY: OWNER_USER},
                {"text": "Maria said", OWNER_KEY: OWNER_OTHER},
            ],
        )
        # Both should survive the final-gate (ask.py's filter handles this)
        assert len(r.evidence_refs) == 2
        assert "P66/TICKET-10" not in (r.calibration_note or "")


class TestFinalGateCommitmentTypeFilter:
    """The final-gate validator must strip non-user commitment_types on promise queries."""

    def test_strips_third_party_report_commitment_type(self):
        """commitment_type='third_party_report' must be stripped on promise queries."""
        r = AskResponse(
            answer="You promised.",
            query="What did I promise?",
            evidence_refs=[
                {"text": "I will send", OWNER_KEY: OWNER_USER,
                 COMMITMENT_TYPE_KEY: "explicit"},
                {"text": "Maria will review", OWNER_KEY: OWNER_USER,
                 COMMITMENT_TYPE_KEY: COMMITMENT_TYPE_THIRD_PARTY_REPORT},
            ],
        )
        assert len(r.evidence_refs) == 1
        assert r.evidence_refs[0][COMMITMENT_TYPE_KEY] == "explicit"

    def test_strips_quoted_commitment_type(self):
        """commitment_type='quoted' must be stripped on promise queries."""
        r = AskResponse(
            answer="You promised.",
            query="What are my promises?",
            evidence_refs=[
                {"text": "I will send", OWNER_KEY: OWNER_USER,
                 COMMITMENT_TYPE_KEY: "explicit"},
                {"text": "Quote: someone will do", OWNER_KEY: OWNER_USER,
                 COMMITMENT_TYPE_KEY: COMMITMENT_TYPE_QUOTED},
            ],
        )
        assert len(r.evidence_refs) == 1
        assert r.evidence_refs[0][COMMITMENT_TYPE_KEY] == "explicit"


class TestFinalGateThreeQueryPhrasings:
    """TICKET-10 acceptance: 3+ query phrasings through different code paths.

    The issue requires testing 3+ phrasings that route through different
    internal code paths. The final-gate validator is model-level, so it
    fires on ALL code paths. These tests verify the validator's behavior
    directly (without depending on which code path ask.py picks).
    """

    @pytest.mark.parametrize("query", [
        "What did I promise Maria?",                    # ledger fast-path style
        "Tell me about my commitments to Maria",        # general query style
        "What are my active promises?",                 # broad query style
        "What have I committed to?",                    # variant
        "My pledges to Maria?",                         # variant
    ])
    def test_all_promise_phrasings_strip_third_party(self, query):
        """All 5 promise-query phrasings must strip owner='other' evidence."""
        r = AskResponse(
            answer=f"Answer for: {query}",
            query=query,
            evidence_refs=[
                {"text": "I will send the proposal", OWNER_KEY: OWNER_USER,
                 COMMITMENT_TYPE_KEY: "explicit", "signal_id": "s1"},
                {"text": "Maria said she will review", OWNER_KEY: OWNER_OTHER,
                 COMMITMENT_TYPE_KEY: COMMITMENT_TYPE_THIRD_PARTY_REPORT, "signal_id": "s2"},
                {"text": "Quote: someone will do", OWNER_KEY: OWNER_USER,
                 COMMITMENT_TYPE_KEY: COMMITMENT_TYPE_QUOTED, "signal_id": "s3"},
            ],
        )
        # Only the user-owned, explicit-commitment evidence should survive
        assert len(r.evidence_refs) == 1, \
            f"Query {query!r}: expected 1 evidence (owner=user, explicit), got {len(r.evidence_refs)}"
        assert r.evidence_refs[0][OWNER_KEY] == OWNER_USER
        assert r.evidence_refs[0][COMMITMENT_TYPE_KEY] == "explicit"
        assert "P66/TICKET-10" in r.calibration_note
        assert "stripped 2 of 3" in r.calibration_note


class TestFinalGateEdgeCases:
    """Edge cases: empty evidence, missing query, malformed evidence."""

    def test_empty_evidence_no_op(self):
        """Empty evidence_refs → no-op, no calibration_note added."""
        r = AskResponse(
            answer="No data.",
            query="What did I promise?",
            evidence_refs=[],
        )
        assert r.evidence_refs == []
        assert "P66/TICKET-10" not in (r.calibration_note or "")

    def test_empty_query_no_op(self):
        """Empty query → no-op (can't classify)."""
        # AskRequest enforces min_length=1, but the model itself doesn't —
        # the validator must still fail safe.
        r = AskResponse(
            answer="No data.",
            query="",
            evidence_refs=[
                {"text": "x", OWNER_KEY: OWNER_OTHER},
            ],
        )
        assert len(r.evidence_refs) == 1  # unchanged
        assert "P66/TICKET-10" not in (r.calibration_note or "")

    def test_non_dict_evidence_rejected_by_pydantic(self):
        """Non-dict evidence entries are rejected by pydantic at schema level.

        This is a layering test: pydantic's `list[dict[str, Any]]` type
        rejects non-dict entries BEFORE the model_validator runs. The
        final-gate validator therefore never sees malformed entries —
        pydantic handles that. This test documents the contract.
        """
        with pytest.raises(Exception):  # pydantic.ValidationError
            AskResponse(
                answer="You promised.",
                query="What did I promise?",
                evidence_refs=[
                    "not a dict",  # malformed — pydantic rejects
                    {"text": "I will send", OWNER_KEY: OWNER_USER},
                ],
            )

    def test_preserves_existing_calibration_note(self):
        """If calibration_note already has content, the marker is appended."""
        r = AskResponse(
            answer="You promised.",
            query="What did I promise?",
            evidence_refs=[
                {"text": "I will send", OWNER_KEY: OWNER_USER},
                {"text": "Maria said", OWNER_KEY: OWNER_OTHER},
            ],
            calibration_note="Pre-existing note.",
        )
        assert r.calibration_note.startswith("Pre-existing note.")
        assert "P66/TICKET-10" in r.calibration_note
        assert "|" in r.calibration_note  # separator


class TestFinalGateIntegrationWithExistingP51P52:
    """The final-gate validator must coexist with the existing P51/P52 validator."""

    def test_p51_non_blank_still_fires(self):
        """P51 (non-blank answer) must still work alongside the final-gate."""
        r = AskResponse(
            answer="",  # blank — P51 must fill it
            query="What did I promise?",
            evidence_refs=[],
        )
        assert r.answer  # non-blank
        assert "P51" in r.calibration_note

    def test_p52_pii_redaction_still_fires(self):
        """P52 (PII redaction) must still work alongside the final-gate."""
        r = AskResponse(
            answer="PRATEEK MISRA promised to send.",
            query="What did I promise?",
            evidence_refs=[
                {"text": "PRATEEK will send", OWNER_KEY: OWNER_USER},
            ],
        )
        assert "PRATEEK" not in r.answer
        assert "REDACTED" in r.answer
        assert "PRATEEK" not in r.evidence_refs[0]["text"]

    def test_all_three_validators_fire_together(self):
        """P51 + P52 + final-gate must all fire on the same response."""
        r = AskResponse(
            answer="PRATEEK MISRA",
            query="What did I promise Maria?",
            evidence_refs=[
                {"text": "I will send", OWNER_KEY: OWNER_USER,
                 COMMITMENT_TYPE_KEY: "explicit"},
                {"text": "Maria said", OWNER_KEY: OWNER_OTHER,
                 COMMITMENT_TYPE_KEY: COMMITMENT_TYPE_THIRD_PARTY_REPORT},
            ],
        )
        # P52 fired: PII redacted
        assert "PRATEEK" not in r.answer
        assert "REDACTED" in r.answer
        # Final-gate fired: third-party evidence stripped
        assert len(r.evidence_refs) == 1
        assert r.evidence_refs[0][OWNER_KEY] == OWNER_USER
        # Calibration note has the marker
        assert "P66/TICKET-10" in r.calibration_note

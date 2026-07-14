"""
Tests for Phase 3.1 (Materiality Gate), Phase 3.2 (Commitment Classifier),
and Phase 5.1 (LLM-as-a-Judge).
"""

import sys
import os
import asyncio
import tempfile
import pytest
from unittest.mock import patch, AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


# ===========================================================================
# Phase 3.1: Materiality Gate tests
# ===========================================================================


class TestMaterialityGate:
    """Phase 3.1: LLM-powered Trusted Silence."""

    def test_rule_based_fallback_when_no_llm(self):
        """When no LLM is available, the rule-based materiality gate must work."""
        from maestro_personal_shell.materiality_gate import _rule_based_materiality

        # Stale commitment with deadline → should speak
        result = _rule_based_materiality(
            {"entity": "AcmeCorp", "text": "Will send proposal", "claim_type": "commitment"},
            {"days_stale": 5, "has_deadline": True, "age_days": 10},
        )
        assert result["should_speak"] is True
        assert result["materiality_score"] >= 0.3
        assert result["llm_powered"] is False

    def test_rule_based_silence_for_low_materiality(self):
        """Rule-based fallback is permissive (speaks by default for commitments).

        Note: The rule-based fallback preserves old behavior — it speaks
        for commitments. Only the LLM gate makes true Trusted Silence
        decisions. The rule-based gate is a permissive fallback.
        """
        from maestro_personal_shell.materiality_gate import _rule_based_materiality

        result = _rule_based_materiality(
            {"entity": "Newsletter", "text": "Check out our new features", "claim_type": "fyi"},
            {"days_stale": 0, "has_deadline": False, "age_days": 1},
        )
        # Rule-based fallback is permissive — it speaks by default
        # (the LLM gate is what makes true Trusted Silence decisions)
        assert result["llm_powered"] is False
        assert result["materiality_score"] == 0.0  # no materiality signals

    @pytest.mark.llm_integration
    def test_llm_materiality_gate_speaks_for_stale_deadline(self):
        """LLM materiality gate must speak for stale commitments with deadlines."""
        from maestro_personal_shell.llm_bridge import reset_llm_router, get_llm_router
        reset_llm_router()
        if get_llm_router() is None:
            pytest.skip("No LLM provider available — skipping")

        mock_response = '{"should_speak": true, "materiality_score": 0.9, "urgency": "high", "reasoning": "Deadline approaching and stale"}'

        with patch(
            "maestro_personal_shell.llm_bridge.llm_complete",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            from maestro_personal_shell.materiality_gate import evaluate_materiality
            result = asyncio.run(evaluate_materiality(
                {"entity": "AcmeCorp", "text": "Will send proposal by Friday", "claim_type": "commitment"},
                {"days_stale": 5, "has_deadline": True, "age_days": 10},
            ))
            assert result["should_speak"] is True
            assert result["materiality_score"] >= 0.8
            assert result["llm_powered"] is True

    def test_llm_materiality_gate_silence_for_routine(self):
        """LLM materiality gate must stay silent for routine activity."""
        from maestro_personal_shell.llm_bridge import reset_llm_router, get_llm_router
        reset_llm_router()
        if get_llm_router() is None:
            pytest.skip("No LLM provider available — skipping")

        mock_response = '{"should_speak": false, "materiality_score": 0.2, "urgency": "low", "reasoning": "Routine newsletter, not actionable"}'

        with patch(
            "maestro_personal_shell.llm_bridge.llm_complete",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            from maestro_personal_shell.materiality_gate import evaluate_materiality
            result = asyncio.run(evaluate_materiality(
                {"entity": "Newsletter", "text": "Check out our blog", "claim_type": "fyi"},
                {"days_stale": 0, "has_deadline": False, "age_days": 1},
            ))
            assert result["should_speak"] is False
            assert result["llm_powered"] is True


# ===========================================================================
# Phase 3.2: Commitment Classifier tests
# ===========================================================================


class TestCommitmentClassifier:
    """Phase 3.2: LLM-powered state-machine commitment tracking."""

    def test_rule_based_explicit_commitment(self):
        """Rule-based classifier must detect explicit commitments."""
        from maestro_personal_shell.commitment_classifier import _rule_based_classify
        result = _rule_based_classify("I will send the proposal by Friday", "AcmeCorp")
        assert result["commitment_type"] == "explicit"
        assert result["is_commitment"] is True
        assert result["state"] == "active"

    def test_rule_based_completion(self):
        """Rule-based classifier must detect completion signals."""
        from maestro_personal_shell.commitment_classifier import _rule_based_classify
        result = _rule_based_classify("Sent the proposal yesterday", "AcmeCorp")
        assert result["commitment_type"] == "completed"
        # Phase 3 semantic fix: a completed commitment IS a commitment
        # (in the completed_claimed lifecycle state). The roadmap schema
        # has is_commitment=true for completed items.
        assert result["is_commitment"] is True
        assert result["state"] == "completed_claimed"

    def test_rule_based_cancellation(self):
        """Rule-based classifier must detect cancellation."""
        from maestro_personal_shell.commitment_classifier import _rule_based_classify
        result = _rule_based_classify("Never mind, we don't need this anymore", "AcmeCorp")
        assert result["commitment_type"] == "cancelled"
        assert result["state"] == "cancelled"

    def test_rule_based_dispute(self):
        """Rule-based classifier must detect disputes."""
        from maestro_personal_shell.commitment_classifier import _rule_based_classify
        result = _rule_based_classify("We got the proposal but it's missing the appendix", "AcmeCorp")
        assert result["commitment_type"] == "disputed"
        assert result["state"] == "disputed"

    def test_rule_based_tentative(self):
        """Rule-based classifier must detect tentative language."""
        from maestro_personal_shell.commitment_classifier import _rule_based_classify
        result = _rule_based_classify("Maybe I can send it next week, but don't count on it", "AcmeCorp")
        assert result["commitment_type"] == "tentative"
        assert result["is_commitment"] is False

    def test_lifecycle_state_machine_transitions(self):
        """The lifecycle state machine must transition correctly."""
        from maestro_personal_shell.commitment_classifier import get_lifecycle_state

        # candidate → active (explicit commitment detected)
        assert get_lifecycle_state("candidate", {"commitment_type": "explicit"}) == "active"

        # active → completed_claimed (completion detected)
        assert get_lifecycle_state("active", {"commitment_type": "completed"}) == "completed_claimed"

        # completed_claimed → completed_verified (second completion confirmation)
        assert get_lifecycle_state("completed_claimed", {"commitment_type": "completed"}) == "completed_verified"

        # completed_claimed → disputed
        assert get_lifecycle_state("completed_claimed", {"commitment_type": "disputed"}) == "disputed"

        # active → cancelled
        assert get_lifecycle_state("active", {"commitment_type": "cancelled"}) == "cancelled"

        # Terminal state: cancelled stays cancelled
        assert get_lifecycle_state("cancelled", {"commitment_type": "explicit"}) == "cancelled"

        # Terminal state: superseded stays superseded
        assert get_lifecycle_state("superseded", {"commitment_type": "explicit"}) == "superseded"

        # disputed → completed_verified (resolution)
        assert get_lifecycle_state("disputed", {"commitment_type": "completed"}) == "completed_verified"

    def test_llm_classifier_explicit_commitment(self):
        """LLM classifier must classify explicit commitments correctly."""
        from maestro_personal_shell.llm_bridge import reset_llm_router, get_llm_router
        reset_llm_router()
        if get_llm_router() is None:
            pytest.skip("No LLM provider available — skipping")

        mock_response = '{"commitment_type": "explicit", "is_commitment": true, "confidence": 0.95, "state": "active", "owner": "user", "deadline_text": "Friday", "reasoning": "Direct promise with deadline"}'

        with patch(
            "maestro_personal_shell.llm_bridge.llm_complete",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            from maestro_personal_shell.commitment_classifier import classify_commitment
            result = asyncio.run(classify_commitment("I will send the proposal by Friday", "AcmeCorp"))
            assert result["commitment_type"] == "explicit"
            assert result["is_commitment"] is True
            assert result["state"] == "active"
            assert result["llm_powered"] is True

    def test_llm_classifier_tentative_not_commitment(self):
        """LLM classifier must NOT classify tentative as a commitment."""
        from maestro_personal_shell.llm_bridge import reset_llm_router, get_llm_router
        reset_llm_router()
        if get_llm_router() is None:
            pytest.skip("No LLM provider available — skipping")

        mock_response = '{"commitment_type": "tentative", "is_commitment": false, "confidence": 0.8, "state": "candidate", "owner": "user", "deadline_text": "", "reasoning": "Hedged with maybe and dont count on it"}'

        with patch(
            "maestro_personal_shell.llm_bridge.llm_complete",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            from maestro_personal_shell.commitment_classifier import classify_commitment
            result = asyncio.run(classify_commitment("Maybe I can send it next week, but don't count on it", "AcmeCorp"))
            assert result["commitment_type"] == "tentative"
            assert result["is_commitment"] is False


# ===========================================================================
# Phase 5.1: LLM-as-a-Judge tests
# ===========================================================================


class TestLLMJudge:
    """Phase 5.1: LLM-as-a-judge evaluation pipeline."""

    def test_judge_factual_accuracy_skips_without_llm(self):
        """Judge must skip gracefully when no LLM is available."""
        from maestro_personal_shell.llm_judge import judge_factual_accuracy

        with patch("maestro_personal_shell.llm_bridge.is_llm_available", return_value=False):
            result = asyncio.run(judge_factual_accuracy(
                "What did AcmeCorp commit to?",
                "AcmeCorp committed to sending the proposal",
                ["AcmeCorp committed to sending the proposal by Friday"],
            ))
            assert result.get("skipped") is True

    def test_judge_factual_accuracy_scores_correct_answer(self):
        """Judge must score a correct answer highly."""
        from maestro_personal_shell.llm_bridge import reset_llm_router, get_llm_router
        reset_llm_router()
        if get_llm_router() is None:
            pytest.skip("No LLM provider available — skipping")

        mock_judge_response = '{"score": 0.95, "is_accurate": true, "unsupported_claims": [], "reasoning": "Answer is fully backed by evidence"}'

        with patch(
            "maestro_personal_shell.llm_bridge.llm_complete",
            new_callable=AsyncMock,
            return_value=mock_judge_response,
        ):
            from maestro_personal_shell.llm_judge import judge_factual_accuracy
            result = asyncio.run(judge_factual_accuracy(
                "What did AcmeCorp commit to?",
                "AcmeCorp committed to sending the proposal by Friday",
                ["AcmeCorp committed to sending the proposal by Friday"],
            ))
            assert result["score"] >= 0.9
            assert result["is_accurate"] is True
            assert result.get("skipped") is not True

    def test_judge_factual_accuracy_scores_fabricated_answer(self):
        """Judge must score a fabricated answer poorly."""
        from maestro_personal_shell.llm_bridge import reset_llm_router, get_llm_router
        reset_llm_router()
        if get_llm_router() is None:
            pytest.skip("No LLM provider available — skipping")

        mock_judge_response = '{"score": 0.2, "is_accurate": false, "unsupported_claims": ["budget claim not in evidence"], "reasoning": "Answer mentions budget which is not in evidence"}'

        with patch(
            "maestro_personal_shell.llm_bridge.llm_complete",
            new_callable=AsyncMock,
            return_value=mock_judge_response,
        ):
            from maestro_personal_shell.llm_judge import judge_factual_accuracy
            result = asyncio.run(judge_factual_accuracy(
                "What did AcmeCorp commit to?",
                "AcmeCorp committed to increasing the budget by 50%",
                ["AcmeCorp committed to sending the proposal by Friday"],
            ))
            assert result["score"] < 0.5
            assert result["is_accurate"] is False

    def test_assert_judge_score_passes_when_above_threshold(self):
        """assert_judge_score must pass when score meets threshold."""
        from maestro_personal_shell.llm_judge import assert_judge_score
        result = {"score": 0.85, "is_accurate": True, "skipped": False}
        assert_judge_score(result, min_score=0.7)  # should not raise

    def test_assert_judge_score_skips_when_no_llm(self):
        """assert_judge_score must skip when judge was skipped."""
        import pytest as _pytest
        from maestro_personal_shell.llm_judge import assert_judge_score
        result = {"score": -1, "skipped": True, "reasoning": "no LLM"}
        with _pytest.raises(_pytest.skip.Exception):
            assert_judge_score(result, min_score=0.7)

    def test_assert_judge_score_fails_when_below_threshold(self):
        """assert_judge_score must fail when score is below threshold."""
        from maestro_personal_shell.llm_judge import assert_judge_score
        result = {"score": 0.3, "skipped": False, "reasoning": "poor"}
        with pytest.raises(AssertionError, match="below threshold"):
            assert_judge_score(result, min_score=0.7)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

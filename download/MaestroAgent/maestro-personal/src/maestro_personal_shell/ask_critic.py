"""Gated Ask critic — LLM-as-judge over Ask responses.

Extracted from maestro_verify/critic.py but standalone (no maestro_core dependency).
Uses the existing llm_bridge.llm_complete() instead of RunContext.

This is the in-house, request-time analogue of Onyx's "scored blind by two
independent LLM judges" discipline. A critic scores the Ask answer against
a rubric. If the score is below threshold, the original answer is returned
unchanged (never ship a worse answer).

Gated behind MAESTRO_VERIFY_CRITIC env var — OFF by default for zero
regression risk. Enable only after benchmark + real-inbox verification.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CriticResult:
    """Result of a critic evaluation."""
    score: float
    justification: str
    suggestions: list[str]


def is_critic_enabled() -> bool:
    """Check if the gated critic is enabled (OFF by default)."""
    return os.environ.get("MAESTRO_VERIFY_CRITIC", "").lower() in ("1", "true", "yes")


async def evaluate_answer(
    answer: str,
    query: str,
    evidence_texts: list[str],
) -> CriticResult:
    """Score an Ask answer against a rubric using an independent LLM call.

    The critic is a SEPARATE LLM call from the one that produced the answer.
    This separation is what makes the verdict independent: the agent cannot
    grade its own homework.

    Args:
        answer: The Ask response answer text
        query: The user's original query
        evidence_texts: List of evidence ref texts

    Returns:
        CriticResult with score (0.0-1.0), justification, and suggestions
    """
    if not answer.strip():
        return CriticResult(score=0.0, justification="empty output", suggestions=[])

    # Build the rubric — what a good commitment-intelligence answer looks like
    rubric = """Score this answer to a commitment-intelligence question.

A perfect answer (1.0):
- Directly answers the question
- Cites specific evidence (not vague references)
- Does not hallucinate commitments not in the evidence
- Does not attribute commitments to the wrong person
- Correctly identifies tentative vs firm commitments
- Abstains honestly when no evidence exists

A failing answer (0.0):
- Hallucinates commitments not in the evidence
- Attributes commitments to the wrong entity
- Presents tentative statements as firm commitments
- Dumps unrelated signals instead of answering the question
"""

    evidence_block = "\n".join(f"- {t[:200]}" for t in evidence_texts[:5]) if evidence_texts else "(no evidence provided)"

    from maestro_personal_shell.llm_bridge import llm_complete

    result = await llm_complete(
        system=(
            "You are an independent critic. Score the given answer against the rubric.\n"
            "Respond as JSON: "
            '{"score": <0.0-1.0>, "justification": "...", "suggestions": ["...", "..."]}\n'
            "Be strict. A score of 1.0 means perfect; 0.5 means partial; 0.0 means fails the rubric."
        ),
        user=(
            f"Rubric:\n{rubric}\n\n"
            f"User's question:\n{query}\n\n"
            f"Evidence available:\n{evidence_block}\n\n"
            f"Answer to evaluate:\n{answer[:4000]}"
        ),
        temperature=0.0,
        max_tokens=300,
    )

    if not result:
        logger.warning("Critic LLM call failed — returning neutral score")
        return CriticResult(score=0.5, justification="critic unavailable", suggestions=[])

    # Best-effort JSON parse — LLMs sometimes wrap JSON in prose
    text = result.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start:end])
            except json.JSONDecodeError:
                logger.warning("Critic returned non-JSON: %s", text[:200])
                return CriticResult(score=0.5, justification=text[:300], suggestions=[])
        else:
            return CriticResult(score=0.5, justification=text[:300], suggestions=[])

    score = float(data.get("score", 0.5))
    score = max(0.0, min(1.0, score))
    return CriticResult(
        score=score,
        justification=str(data.get("justification", "")),
        suggestions=list(data.get("suggestions", [])),
    )


async def maybe_refine_answer(
    answer: str,
    query: str,
    evidence_texts: list[str],
    confidence: float,
) -> tuple[str, float, CriticResult | None]:
    """Gated critic: evaluate the answer, return it unchanged if critic is off or score is good.

    Returns:
        (possibly_refined_answer, possibly_adjusted_confidence, critic_result_or_none)
    """
    if not is_critic_enabled():
        return answer, confidence, None

    try:
        result = await evaluate_answer(answer, query, evidence_texts)
        logger.info("Critic score: %.2f — %s", result.score, result.justification[:100])

        # If the critic scores low, log it but DON'T automatically rewrite —
        # just lower the confidence and append the justification.
        # We never ship a worse answer; the critic only adds information.
        if result.score < 0.5:
            new_confidence = min(confidence, result.score)
            critic_note = f"\n\n[Self-review: {result.justification[:100]}]"
            return answer + critic_note, new_confidence, result

        # Score is good — keep the answer, maybe boost confidence slightly
        return answer, confidence, result
    except Exception as e:
        logger.error("Critic evaluation failed (non-fatal): %s", e)
        return answer, confidence, None

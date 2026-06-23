"""Critic — LLM-as-judge scorer.

A critic is an independent LLM agent that scores an output against a
rubric. The score is a float in [0, 1]. The critic also returns a
short justification.

This is the building block for `CriticCondition` (loop exit condition)
and for the evaluator-optimizer loop.

We deliberately use a SEPARATE LLM call from the agent that produced
the output. This separation is what makes the verdict *independent*:
the agent cannot grade its own homework.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from maestro_core.context import RunContext

logger = logging.getLogger(__name__)


@dataclass
class CriticResult:
    score: float
    justification: str
    suggestions: list[str]


async def score_with_critic(
    ctx: "RunContext",
    rubric: str,
    output: str,
    agent_id: str = "critic",
    provider: str | None = None,
    model: str | None = None,
) -> float:
    """Score an output against a rubric. Returns a float in [0, 1]."""
    result = await evaluate_with_critic(
        ctx=ctx,
        rubric=rubric,
        output=output,
        agent_id=agent_id,
        provider=provider,
        model=model,
    )
    return result.score


async def evaluate_with_critic(
    ctx: "RunContext",
    rubric: str,
    output: str,
    agent_id: str = "critic",
    provider: str | None = None,
    model: str | None = None,
) -> CriticResult:
    """Full critic evaluation — score + justification + suggestions."""
    if not output.strip():
        return CriticResult(score=0.0, justification="empty output", suggestions=[])

    resp = await ctx.llm.complete(
        system=(
            "You are an independent critic. Score the given output against the rubric.\n"
            "Respond as JSON: "
            '{"score": <0.0-1.0>, "justification": "...", "suggestions": ["...", "..."]}\n'
            "Be strict. A score of 1.0 means perfect; 0.5 means partial; 0.0 means fails the rubric."
        ),
        user=(
            f"Rubric:\n{rubric}\n\n"
            f"Output to evaluate:\n{output[:6000]}"
        ),
        provider=provider,
        model=model,
        temperature=0.0,
        tools=[],
        run_id=ctx.config.run_id,
        agent_id=agent_id,
    )
    ctx.cost_so_far += resp.cost_usd

    # Best-effort parse — LLMs sometimes wrap JSON in prose.
    text = resp.text.strip()
    # Try direct parse.
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to find a JSON object in the text.
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

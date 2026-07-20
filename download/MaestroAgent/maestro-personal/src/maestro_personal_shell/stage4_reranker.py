#!/usr/bin/env python3
"""
stage4_reranker.py — LLM-based cross-encoder reranker for Stage 4.

Implements the "LLM-as-a-reranker" technique: uses the LLM to score
each evidence chunk's relevance to the query, then re-sorts by score.

Why LLM-based instead of a true cross-encoder (bge-reranker-v2-m3):
  - No hosted cross-encoder endpoint available via OpenRouter
  - No local Ollama in this sandbox to run bge-reranker
  - The LLM-as-a-reranker technique is well-established and works with
    existing infrastructure (qwen-plus via OpenRouter)
  - Trade-off: slower (1 LLM call per chunk) but uses existing infra

How it works:
  1. Takes the top-N RRF-fused evidence (e.g., 20 signals)
  2. For each signal, calls the LLM with: "Rate the relevance of this
     passage to the query on a scale of 0-10. Return ONLY the number."
  3. Re-sorts signals by LLM score (descending)
  4. Returns the top-K (e.g., 8) highest-scored signals

Cost estimate:
  - 20 signals × 1 LLM call each = 20 calls per query
  - At $0.0000068/call (qwen-plus) = $0.00014 per query
  - 100 questions = $0.014 total (effectively free)

Usage (integrated into retrieval_ensemble.py):
  from maestro_personal_shell.stage4_reranker import rerank_evidence
  reranked = await rerank_evidence(query, fused_evidence, top_k=8)
"""
from __future__ import annotations
import asyncio
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)


async def _score_single_signal(
    query: str,
    signal_text: str,
    signal_entity: str,
    llm_complete_fn,
) -> float:
    """Score a single signal's relevance to the query. Returns 0.0-10.0.

    Uses the LLM to rate relevance. Falls back to 5.0 (neutral) on error.
    """
    # Truncate signal text to keep the prompt short
    sig_short = signal_text[:300] if len(signal_text) > 300 else signal_text
    system = (
        "You are a relevance judge. Rate how relevant the passage is to the "
        "question on a scale of 0-10. 10 = perfectly answers the question, "
        "0 = completely irrelevant. Return ONLY the number, nothing else."
    )
    user = (
        f"Question: {query}\n\n"
        f"Passage: [{signal_entity}] {sig_short}\n\n"
        f"Relevance score (0-10):"
    )

    try:
        result = await llm_complete_fn(
            system=system,
            user=user,
            temperature=0.0,
            max_tokens=5,
        )
        if result:
            # Extract the first number from the response
            match = re.search(r'\b(\d+(?:\.\d+)?)\b', result.strip())
            if match:
                score = float(match.group(1))
                return max(0.0, min(10.0, score))
        return 5.0  # neutral fallback
    except Exception as e:
        logger.debug("LLM reranker score failed: %s", e)
        return 5.0


async def rerank_evidence(
    query: str,
    evidence: list[dict[str, Any]],
    top_k: int = 8,
    max_to_score: int = 20,
) -> list[dict[str, Any]]:
    """Rerank evidence using LLM-based relevance scoring.

    Args:
        query: The user's question.
        evidence: List of evidence dicts (from RRF fusion).
        top_k: Number of top-scored evidence to return.
        max_to_score: Max number of evidence to score (skip the rest).

    Returns:
        Re-sorted evidence list, top_k items, highest LLM score first.
    """
    if not evidence:
        return []

    # Only score the top max_to_score (RRF already did coarse ranking)
    to_score = evidence[:max_to_score]

    try:
        from maestro_personal_shell.llm_bridge import is_llm_available, llm_complete
    except ImportError:
        logger.warning("llm_bridge not available — skipping reranker")
        return evidence[:top_k]

    if not is_llm_available():
        logger.debug("LLM not available — skipping reranker")
        return evidence[:top_k]

    # Score all signals concurrently
    async def score_one(ev: dict) -> tuple[float, dict]:
        text = str(ev.get("text", ""))
        entity = str(ev.get("entity", ""))
        score = await _score_single_signal(query, text, entity, llm_complete)
        return (score, ev)

    try:
        scored = await asyncio.gather(*[score_one(ev) for ev in to_score])
    except Exception as e:
        logger.warning("Reranker gather failed: %s — returning unranked", e)
        return evidence[:top_k]

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    # Return top_k
    return [ev for score, ev in scored[:top_k]]


def rerank_evidence_sync(
    query: str,
    evidence: list[dict[str, Any]],
    top_k: int = 8,
    max_to_score: int = 20,
) -> list[dict[str, Any]]:
    """Synchronous wrapper for rerank_evidence.

    Used when the caller is not in an async context (e.g., the evaluation
    harness which calls retrieve() directly).
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're in an async context — create a new loop
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run,
                    rerank_evidence(query, evidence, top_k, max_to_score)
                )
                return future.result()
        else:
            return loop.run_until_complete(
                rerank_evidence(query, evidence, top_k, max_to_score)
            )
    except RuntimeError:
        return asyncio.run(rerank_evidence(query, evidence, top_k, max_to_score))

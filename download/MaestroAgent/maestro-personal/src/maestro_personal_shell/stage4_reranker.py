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
    method: str = "llm",
) -> list[dict[str, Any]]:
    """Rerank evidence using the specified method.

    Args:
        query: The user's question.
        evidence: List of evidence dicts (from RRF fusion).
        top_k: Number of top-scored evidence to return.
        max_to_score: Max number of evidence to score (skip the rest).
        method: "llm" (LLM-as-a-reranker, default) or "cohere"
            (true cross-encoder via Cohere Rerank API).

    Returns:
        Re-sorted evidence list, top_k items, highest score first.
    """
    if not evidence:
        return []

    # Only score the top max_to_score (RRF already did coarse ranking)
    to_score = evidence[:max_to_score]

    if method == "cohere":
        return _rerank_cohere(query, to_score, top_k)
    else:
        return await _rerank_llm(query, to_score, top_k)


def _rerank_cohere(
    query: str,
    evidence: list[dict[str, Any]],
    top_k: int,
) -> list[dict[str, Any]]:
    """Rerank using Cohere Rerank API (true cross-encoder).

    Uses rerank-multilingual-v3.0 by default (better than english-v3.0
    for diverse text — verified 2026-07-20). Falls back to unranked on
    any error (P6: fail closed).
    """
    import json as _json
    import urllib.request as _urllib

    api_key = os.environ.get("COHERE_API_KEY")
    if not api_key:
        logger.debug("COHERE_API_KEY not set — skipping Cohere reranker")
        return evidence[:top_k]

    model = os.environ.get("COHERE_RERANK_MODEL", "rerank-multilingual-v3.0")

    # Build documents list (entity + text for context)
    documents = []
    for ev in evidence:
        text = str(ev.get("text", ""))[:1000]  # Cohere doc limit
        entity = str(ev.get("entity", ""))
        documents.append(f"[{entity}] {text}" if entity else text)

    payload = _json.dumps({
        "model": model,
        "query": query,
        "documents": documents,
        "top_n": min(top_k, len(documents)),
    }).encode()

    req = _urllib.Request(
        "https://api.cohere.ai/v1/rerank",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with _urllib.urlopen(req, timeout=10) as resp:
            body = _json.loads(resp.read())
        # Cohere returns results as [{index, relevance_score}, ...] sorted by score desc
        results = body.get("results", [])
        reranked = [evidence[r["index"]] for r in results if r["index"] < len(evidence)]
        logger.info(
            "Cohere reranker: %d signals scored, top score=%.4f",
            len(results),
            results[0]["relevance_score"] if results else 0.0,
        )
        return reranked[:top_k]
    except Exception as e:
        logger.warning("Cohere reranker failed: %s — returning unranked", e)
        return evidence[:top_k]


async def _rerank_llm(
    query: str,
    evidence: list[dict[str, Any]],
    top_k: int,
) -> list[dict[str, Any]]:
    """Rerank using LLM-as-a-reranker technique (original method)."""
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
        scored = await asyncio.gather(*[score_one(ev) for ev in evidence])
    except Exception as e:
        logger.warning("LLM reranker gather failed: %s — returning unranked", e)
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
    method: str = "llm",
) -> list[dict[str, Any]]:
    """Synchronous wrapper for rerank_evidence.

    Used when the caller is not in an async context (e.g., the evaluation
    harness which calls retrieve() directly).

    Args:
        method: "llm" (default) or "cohere" (true cross-encoder).
    """
    if method == "cohere":
        # Cohere is synchronous (urllib) — no asyncio needed
        to_score = evidence[:max_to_score]
        return _rerank_cohere(query, to_score, top_k)
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're in an async context — create a new loop
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run,
                    _rerank_llm(query, evidence[:max_to_score], top_k)
                )
                return future.result()
        else:
            return loop.run_until_complete(
                _rerank_llm(query, evidence[:max_to_score], top_k)
            )
    except RuntimeError:
        return asyncio.run(_rerank_llm(query, evidence[:max_to_score], top_k))

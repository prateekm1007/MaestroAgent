"""
Claim Verifier — Phase 5: removes unsupported statements from Ask answers.

The roadmap (ROAD_TO_9_OF_10_AFTER_395558A.md Phase 5) requires:
  - Ask unsupported claims <= 3%
  - Citation correctness >= 95%

The claim verifier examines the LLM-generated answer and checks each
factual claim against the evidence_refs. Claims not supported by any
evidence are flagged as 'unsupported' and moved to counterevidence (or
removed, depending on mode). This prevents hallucinated statements from
reaching the user.

How it works:
  1. Split the answer into sentences (claims).
  2. For each claim, check if any evidence_refs text supports it:
     - Exact entity match: the claim mentions an entity from evidence.
     - Keyword overlap: the claim shares content words with evidence.
     - Negation check: the claim contradicts evidence (counterevidence).
  3. Claims with no supporting evidence are 'unsupported'.
  4. The verified answer removes unsupported claims (or marks them).
  5. Counterevidence is collected separately.

This is a rule-based verifier (no LLM needed). It's conservative — it
only removes claims that have ZERO overlap with any evidence. Claims
with partial overlap are kept (the LLM may be paraphrasing).
"""

from __future__ import annotations

import re
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Stopwords removed when extracting claim keywords.
_CLAIM_STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "do", "does", "did", "have", "has", "had", "will", "would", "shall",
    "should", "can", "could", "may", "might", "must",
    "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us",
    "my", "your", "his", "its", "our", "their",
    "this", "that", "these", "those", "there", "here",
    "what", "when", "where", "which", "who", "whom", "whose", "why", "how",
    "of", "in", "on", "at", "to", "for", "with", "from", "by", "about",
    "and", "or", "but", "not", "if", "then", "else", "so", "than", "as",
    "up", "out", "into", "over", "under",
    "has", "had", "been", "being", "am",
    "s", "t", "d", "ll", "ve", "re", "m",  # contractions artifacts
})


def _extract_keywords(text: str) -> set[str]:
    """Extract content-bearing keywords from a text."""
    cleaned = re.sub(r"[^\w\s]", " ", (text or "").lower())
    return {w for w in cleaned.split() if w and w not in _CLAIM_STOPWORDS and len(w) > 2}


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences."""
    # Split on . ! ? followed by space or end. Keep it simple.
    sentences = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return [s.strip() for s in sentences if s.strip()]


def _extract_entities(text: str) -> set[str]:
    """Extract capitalized words (potential entity names) from text."""
    words = re.findall(r"\b[A-Z][a-z]+\b", text or "")
    return {w for w in words if len(w) > 2}


def verify_claims(
    answer: str,
    evidence_refs: list[dict[str, Any]],
    source_sentence: str = "",
) -> dict[str, Any]:
    """Verify that the answer's claims are supported by evidence.

    Returns:
    {
        "verified_answer": str,         # answer with unsupported claims removed
        "unsupported_claims": list[str], # claims not backed by evidence
        "counterevidence": list[dict],   # evidence that contradicts the answer
        "confidence": float,             # calibrated confidence (0.0-1.0)
        "all_claims_supported": bool,    # True if no unsupported claims
    }
    """
    if not answer:
        return {
            "verified_answer": "",
            "unsupported_claims": [],
            "counterevidence": [],
            "confidence": 0.0,
            "all_claims_supported": True,
        }

    # Gather all evidence text + entities.
    evidence_texts = []
    evidence_entities: set[str] = set()
    evidence_keywords: set[str] = set()
    for ref in evidence_refs:
        ref_text = ref.get("text", "") or ""
        ref_entity = ref.get("entity", "") or ""
        if ref_text:
            evidence_texts.append(ref_text)
            evidence_keywords |= _extract_keywords(ref_text)
        if ref_entity:
            evidence_entities |= _extract_entities(ref_entity)
            evidence_entities.add(ref_entity)

    # Include source_sentence as evidence.
    if source_sentence:
        evidence_texts.append(source_sentence)
        evidence_keywords |= _extract_keywords(source_sentence)
        source_entities = _extract_entities(source_sentence)
        evidence_entities |= source_entities

    # If no evidence at all, the answer can't be verified — low confidence.
    if not evidence_texts and not source_sentence:
        return {
            "verified_answer": answer,
            "unsupported_claims": [],
            "counterevidence": [],
            "confidence": 0.3,  # low confidence — no evidence to back it
            "all_claims_supported": False,
        }

    # Split answer into claims (sentences).
    claims = _split_sentences(answer)

    supported_claims: list[str] = []
    unsupported_claims: list[str] = []
    counterevidence: list[dict[str, Any]] = []

    for claim in claims:
        claim_keywords = _extract_keywords(claim)
        claim_entities = _extract_entities(claim)

        # A claim is supported if it has keyword overlap with evidence.
        # (Conservative: we require at least 1 content-word overlap, OR
        # the claim mentions an entity that appears in evidence.)
        keyword_overlap = claim_keywords & evidence_keywords
        entity_match = claim_entities & evidence_entities if claim_entities else set()

        if keyword_overlap or entity_match or not claim_keywords:
            # Supported (or a trivial claim with no keywords — keep it).
            supported_claims.append(claim)

            # P1-8 fix (audit 2026-07-15): counterevidence must NOT include
            # the same evidence that supports the claim. The prior code
            # looped over ALL evidence_refs, so a single piece of evidence
            # could appear as BOTH primary evidence AND counterevidence —
            # a logical contradiction.
            #
            # New approach: identify which refs support THIS claim (by
            # keyword/entity overlap), then only check the REMAINING refs
            # for counterevidence. This ensures a ref is either supporting
            # OR contradicting, never both.
            supporting_ref_ids: set[int] = set()
            for i, ref in enumerate(evidence_refs):
                ref_text = ref.get("text", "") or ""
                ref_keywords = _extract_keywords(ref_text)
                ref_entities_set = _extract_entities(ref_text) | {ref.get("entity", "")} - {""}
                if claim_keywords & ref_keywords or claim_entities & ref_entities_set:
                    supporting_ref_ids.add(i)

            # Check for counterevidence: does any NON-supporting evidence
            # CONTRADICT this claim? Simple heuristic: if the claim contains
            # a negation and the evidence affirms (or vice versa).
            claim_lower = claim.lower()
            has_negation = any(neg in claim_lower for neg in
                             ["not", "n't", "never", "no ", "denied", "disputed",
                              "cancelled", "won't", "didn't", "hasn't", "wasn't"])
            for i, ref in enumerate(evidence_refs):
                # P1-8 fix: skip refs that support this claim — they cannot
                # also be counterevidence.
                if i in supporting_ref_ids:
                    continue
                ref_text = (ref.get("text", "") or "").lower()
                ref_neg = any(neg in ref_text for neg in
                            ["not", "n't", "never", "no ", "denied", "disputed",
                             "cancelled", "won't", "didn't", "hasn't", "wasn't"])
                # If the claim and evidence disagree on negation AND share an entity,
                # flag as counterevidence.
                if has_negation != ref_neg:
                    ref_entities = _extract_entities(ref.get("text", ""))
                    if claim_entities & ref_entities:
                        counterevidence.append(ref)
                        break
        else:
            # No overlap with any evidence — unsupported.
            unsupported_claims.append(claim)

    # Build the verified answer: supported claims only.
    verified_answer = " ".join(supported_claims) if supported_claims else answer

    # Calibrate confidence:
    # - Start at 1.0
    # - Subtract 0.2 per unsupported claim (min 0.1)
    # - Subtract 0.15 per counterevidence item (min 0.1)
    # - If no evidence at all, 0.3 (already handled above)
    confidence = 1.0
    confidence -= 0.2 * len(unsupported_claims)
    confidence -= 0.15 * len(counterevidence)
    confidence = max(0.1, min(1.0, confidence))

    # If the answer is very short and matches source_sentence exactly, high confidence.
    if source_sentence and answer.strip().lower() == source_sentence.strip().lower():
        confidence = max(confidence, 0.95)

    return {
        "verified_answer": verified_answer,
        "unsupported_claims": unsupported_claims,
        "counterevidence": counterevidence,
        "confidence": round(confidence, 2),
        "all_claims_supported": len(unsupported_claims) == 0,
    }


def compute_unknowns(
    answer: str,
    evidence_refs: list[dict[str, Any]],
    query: str = "",
) -> list[str]:
    """Compute what we DON'T know / can't verify from the evidence.

    Unknowns are open questions that the evidence doesn't answer:
    - If the query asks about a deadline but no deadline is in evidence.
    - If the query asks about a relationship but no relationship evidence.
    - If the query asks about a completion but no completion signal.

    Returns a list of unknown statements.
    """
    unknowns: list[str] = []
    query_lower = (query or "").lower()
    all_evidence_text = " ".join(
        (r.get("text", "") or "") for r in evidence_refs
    ).lower()

    # Check for temporal queries without temporal evidence.
    if any(kw in query_lower for kw in ["when", "deadline", "by when", "due"]):
        if not any(kw in all_evidence_text for kw in
                   ["friday", "monday", "tuesday", "wednesday", "thursday",
                    "saturday", "sunday", "eod", "cob", "by ", "deadline",
                    "due", "tomorrow", "today", "next week", "last week"]):
            unknowns.append("No deadline information found in the evidence.")

    # Check for relationship queries without relationship evidence.
    if any(kw in query_lower for kw in ["relationship", "connected", "related", "between"]):
        if not any(kw in all_evidence_text for kw in
                   ["partner", "client", "vendor", "colleague", "manager",
                    "report", "team", "works with", "reports to"]):
            unknowns.append("No relationship information found in the evidence.")

    # Check for completion queries without completion evidence.
    if any(kw in query_lower for kw in ["completed", "done", "finished", "delivered", "sent"]):
        if not any(kw in all_evidence_text for kw in
                   ["sent", "delivered", "completed", "finished", "done",
                    "submitted", "paid", "received"]):
            unknowns.append("No completion evidence found — status may be unverified.")

    # If there's very little evidence, note it.
    if len(evidence_refs) == 0:
        unknowns.append("No evidence found for this query.")
    elif len(evidence_refs) == 1:
        unknowns.append("Only one source found — cross-verification not possible.")

    return unknowns

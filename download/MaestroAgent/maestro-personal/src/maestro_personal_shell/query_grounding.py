"""Query grounding layer (P84 / P87).

Sits between the user's question and the LLM. Computes evidence from the
canonical ledger BEFORE invoking the LLM, so zero-evidence questions abstain
instead of hallucinating.

Root cause (P10): the Ask endpoint invoked the LLM with no evidence gate, so
zero-evidence questions ("What did I promise Elon Musk?") were answered by
free generation → hallucinated commitments ("I promise to buy Twitter again").
The fix is structural: compute evidence first, abstain if zero, only invoke
the LLM if evidence exists.

Authored by: CTO (intent detection by Kimi K3 via CTO↔K3 loop, P46 verified)
  Kimi K3 generation_id: gen-1785179155-<from phase3a dispatch>
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Intent detection (rule-based, P56) — authored by Kimi K3
# ---------------------------------------------------------------------------

_W = r"([A-Za-z][A-Za-z''-]*)"
_STOP = frozenset({
    "i", "me", "my", "we", "us", "our", "you", "your", "they", "them", "their",
    "he", "she", "it", "what", "who", "did", "do", "does", "has", "have", "had",
    "is", "are", "was", "the", "a", "an", "there", "everything", "anything",
    "all", "any", "someone", "anyone", "commitment", "commitments", "promise",
    "promises", "to", "with", "about",
})


def _name(tok: str | None) -> str | None:
    if not tok or tok.lower() in _STOP:
        return None
    return tok[0].upper() + tok[1:]


def detect_intent(question: str) -> dict:
    """Rule-based intent + entity detection (P56: no LLM).

    Returns {intent, entity, direction} where:
      intent ∈ {my_commitments, their_commitments, involving, state_query, general}
      entity is the extracted name or None
      direction ∈ {my-to-X, X-to-me, X's-promises, involving-X, any}
    """
    q = question.strip()
    low = q.lower()

    def grab(pattern: str) -> str | None:
        m = re.search(pattern, q, re.IGNORECASE)
        if not m:
            return None
        # With alternation, different groups may capture. Find the first non-None group.
        for g in m.groups():
            if g:
                return _name(g)
        return None

    # 1) my commitments: I -> X
    if re.search(
        r"\bi\s+(?:did\s+|do\s+|have\s+|had\s+)?(?:promise[sd]?|owe[sd]?|committed)\b"
        r"|\bmy\s+(?:commitments?|promises?|obligations?)\b",
        low,
    ):
        ent = grab(
            r"(?:commitments?|promises?|obligations?)\s+to\s+" + _W
            + r"|(?:promise[sd]?|owe[sd]?|committed)\s+to\s+" + _W
            + r"|(?:promise[sd]?|owe[sd]?)\s+" + _W
        )
        return {"intent": "my_commitments", "entity": ent, "direction": "my-to-X"}

    # 2) their commitments: X promised / X's promises
    for pat in (
        r"\b" + _W + r"['']s\s+(?:commitments?|promises?|obligations?|pledges?)\b",
        r"\b(?:did|has|does|had|is)\s+" + _W + r"\s+(?:promise[sd]?|owe[sd]?|committed)\b",
        r"\b" + _W + r"\s+(?:promised|promises|committed|owes)\b",
        r"\b(?:promises?|commitments?|obligations?)\s+(?:from|by)\s+" + _W,
    ):
        ent = grab(pat)
        if ent:
            return {"intent": "their_commitments", "entity": ent, "direction": "X's-promises"}

    # 3) involving X
    for pat in (
        r"\b(?:history|everything|anything|dealings|all)\s+(?:with|about)\s+" + _W,
        r"\b(?:happening|going\s+on|new|up)\s+with\s+" + _W,
        r"\binvolving\s+" + _W,
        r"\babout\s+" + _W,
        r"\bwith\s+" + _W,
    ):
        ent = grab(pat)
        if ent:
            return {"intent": "involving", "entity": ent, "direction": "involving-X"}

    # 4) state query (entity-less aggregate/status)
    if re.search(
        r"\b(how\s+many|how\s+much|count|total|number\s+of|active|open|pending"
        r"|cancell?ed|completed|fulfilled|broken|overdue|status|state|summary|update)\b",
        low,
    ):
        return {"intent": "state_query", "entity": None, "direction": "any"}

    # 5) fallback
    return {"intent": "general", "entity": None, "direction": "any"}


# ---------------------------------------------------------------------------
# Query grounding (P84 / P87) — authored by CTO
# ---------------------------------------------------------------------------


def ground_query(question: str, user_email: str, db_path: str | None = None) -> dict:
    """Ground a user question against the canonical ledger.

    Returns a dict with:
      question, intent, entity, direction, evidence_count, evidence,
      should_abstain, abstention_reason, state_assertion

    P84: if evidence_count == 0, should_abstain=True → caller MUST bypass
         the LLM and return a calibrated abstention.
    P85: never raises — returns a structured error dict on any failure.
    P87: for state queries, state_assertion matches the canonical ledger.
    P22: calls reduce_commitments (the production path), no mocks.
    """
    result: dict[str, Any] = {
        "question": question,
        "intent": "general",
        "entity": None,
        "direction": "any",
        "evidence_count": 0,
        "evidence": [],
        "should_abstain": True,
        "abstention_reason": "not yet computed",
        "state_assertion": None,
    }

    try:
        intent_info = detect_intent(question)
        result["intent"] = intent_info["intent"]
        result["entity"] = intent_info["entity"]
        result["direction"] = intent_info["direction"]

        # P84: retrieve evidence from the canonical ledger
        from maestro_personal_shell.canonical_ledger import (
            reduce_commitments,
            check_ledger_projection_consistency,
        )

        all_commitments = reduce_commitments(user_email, db_path=db_path)

        # Filter by entity + direction
        entity = intent_info["entity"]
        direction = intent_info["direction"]
        intent = intent_info["intent"]

        if intent == "state_query":
            # P87: state query — return counts from the consistency check
            report = check_ledger_projection_consistency(db_path=db_path)
            result["state_assertion"] = {
                "active": report.get("active_count", 0),
                "cancelled": report.get("cancelled_count", 0),
                "total_events": report.get("total_events", 0),
                "total_commitments": report.get("total_commitments", 0),
            }
            result["evidence_count"] = report.get("total_events", 0)
            result["evidence"] = []  # state queries don't return individual events
            result["should_abstain"] = result["evidence_count"] == 0
            result["abstention_reason"] = (
                None if not result["should_abstain"]
                else "no events in the ledger"
            )
        elif intent == "general":
            # General query — return all commitments as evidence
            result["evidence"] = all_commitments[:20]
            result["evidence_count"] = len(all_commitments)
            result["should_abstain"] = result["evidence_count"] == 0
            result["abstention_reason"] = (
                None if not result["should_abstain"]
                else "no commitments found in your ledger"
            )
        else:
            # Entity-specific query — filter by entity
            if entity:
                filtered = [
                    c for c in all_commitments
                    if entity.lower() in (c.get("entity", "") or "").lower()
                ]
            else:
                filtered = all_commitments

            # Direction filter (P79: semantic disambiguation)
            if direction == "my-to-X":
                # Only user's commitments (actor=user is already enforced by reduce_commitments)
                filtered = [c for c in filtered if c.get("actor") == "user"]
            elif direction == "X's-promises":
                # Third-party commitments — but reduce_commitments only returns user-active.
                # For their_commitments, we'd need to query the ledger directly for actor=entity_name.
                # For now, return empty (the user's active list doesn't include third-party).
                # Phase 3+: add a separate query for third-party commitments.
                filtered = []  # TODO: query ledger for actor=entity_name events
            # involving-X and any: no further filter

            result["evidence"] = filtered[:20]
            result["evidence_count"] = len(filtered)
            result["should_abstain"] = result["evidence_count"] == 0
            result["abstention_reason"] = (
                None if not result["should_abstain"]
                else f"no evidence found for {entity or 'this query'}"
            )

    except Exception as exc:
        logger.exception("ground_query failed for question=%r user=%s", question, user_email)
        result["should_abstain"] = True
        result["abstention_reason"] = f"query grounding failed: {exc}"
        result["evidence_count"] = 0
        result["evidence"] = []

    return result


def format_abstention_response(question: str, entity: str | None, reason: str) -> dict:
    """Format a calibrated abstention response (P84).

    The caller (Ask endpoint) returns this directly when should_abstain=True,
    bypassing the LLM entirely.
    """
    if entity:
        answer = (
            f"I don't have any records about {entity}. "
            f"If you've made a commitment to them that I should track, "
            f"please add it via /api/signals."
        )
    else:
        answer = (
            "I don't have any records matching that query. "
            "If you have a commitment you'd like me to track, please add it via /api/signals."
        )

    return {
        "answer": answer,
        "confidence": 0.0,
        "evidence_count": 0,
        "abstention": True,
        "abstention_reason": reason,
        "question": question,
    }

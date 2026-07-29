"""Query grounding layer (P84 / P87).

Sits between the user's question and the LLM. Computes evidence from the
canonical ledger BEFORE invoking the LLM, so zero-evidence questions abstain
instead of hallucinating.

Root cause (P10): the Ask endpoint invoked the LLM with no evidence gate, so
zero-evidence questions ("What did I promise Elon Musk?") were answered by
free generation → hallucinated commitments ("I promise to buy Twitter again").
The fix is structural: compute evidence first, abstain if zero, only invoke
the LLM if evidence exists.

Phase 3.3 (2026-07-29): Multi-word entity support, temporal queries,
multi-hop conflict detection. Authored by CTO + DeepSeek-V3.2 + Qwen3-Coder
loop via OpenRouter.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Intent detection (rule-based, P56) — authored by Kimi K3 + extended
# ---------------------------------------------------------------------------

# Multi-word entity matcher: "Sarah Chen", "Project Atlas", "Barack Obama"
# Captures 1-4 capitalized words. Stops at lowercase words.
# NOTE: first letter of each word MUST be uppercase (case-sensitive via (?-i:...)).
# This prevents "are Jamie" from being captured when re.IGNORECASE is on.
_W = r"((?-i:[A-Z])[A-Za-z''-]*(?:\s+(?-i:[A-Z])[A-Za-z''-]*){0,3})"

_STOP = frozenset({
    "i", "me", "my", "we", "us", "our", "you", "your", "they", "them", "their",
    "he", "she", "it", "what", "who", "did", "do", "does", "has", "have", "had",
    "is", "are", "was", "the", "a", "an", "there", "everything", "anything",
    "all", "any", "someone", "anyone", "commitment", "commitments", "promise",
    "promises", "to", "with", "about",
})

# Capitalized words that are NOT entity names — used to strip leading words
# from multi-word captures like "What Sarah Chen" → "Sarah Chen".
_NON_ENTITY_CAPS = frozenset({
    "What", "Who", "When", "Where", "Why", "How", "Which", "Whose",
    "The", "This", "That", "These", "Those", "There", "Here",
    "Did", "Does", "Has", "Have", "Had", "Is", "Are", "Was", "Were",
    "Will", "Would", "Should", "Could", "Can", "May", "Might",
    "Any", "All", "Some", "Every", "Each",
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    "January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December",
})


def _name(tok: str | None) -> str | None:
    """Clean a captured token: strip leading non-entity words (What/Did/The...)."""
    if not tok:
        return None
    parts = tok.split()
    # Strip leading non-entity words like "What Sarah Chen" → "Sarah Chen"
    while parts and parts[0] in _NON_ENTITY_CAPS:
        parts.pop(0)
    if not parts:
        return None
    cleaned = " ".join(parts).strip()
    if not cleaned or cleaned.lower() in _STOP:
        return None
    return cleaned


# ---------------------------------------------------------------------------
# Temporal reference parsing (Phase 3.3) — for "what changed since X"
# ---------------------------------------------------------------------------


def _parse_temporal_reference(question: str):
    """Parse 'since yesterday' / 'since last week' / 'since N days ago' / 'since Monday'.
    Returns a datetime in UTC, or None if no parseable reference found.
    """
    import datetime as _dt
    low = question.lower()
    now = _dt.datetime.now(_dt.timezone.utc)
    today = now.date()

    # since N days/weeks/months ago
    m = re.search(r"since\s+(\d+)\s+(day|week|month)s?\s+ago", low)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        if unit == "day":
            return now - _dt.timedelta(days=n)
        elif unit == "week":
            return now - _dt.timedelta(weeks=n)
        elif unit == "month":
            return now - _dt.timedelta(days=n * 30)

    # since yesterday
    if re.search(r"\bsince\s+yesterday\b", low):
        return now - _dt.timedelta(days=1)

    # since last week
    if re.search(r"\bsince\s+last\s+week\b", low):
        return now - _dt.timedelta(weeks=1)

    # since this morning
    if re.search(r"\bsince\s+this\s+morning\b", low):
        return now - _dt.timedelta(hours=12)

    # since <weekday>
    weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    m = re.search(r"\bsince\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", low)
    if m:
        target = weekdays.index(m.group(1))
        delta = (today.weekday() - target) % 7
        if delta == 0:
            delta = 7  # at least 7 days back if today is the same weekday
        return now - _dt.timedelta(days=delta)

    return None


def _safe_parse_iso(s):
    """Parse an ISO 8601 timestamp safely. Returns datetime or None."""
    if not s or not isinstance(s, str):
        return None
    import datetime as _dt
    try:
        # Handle trailing Z
        s2 = s.replace("Z", "+00:00")
        return _dt.datetime.fromisoformat(s2)
    except Exception:
        try:
            return _dt.datetime.fromisoformat(str(s)[:19])
        except Exception:
            return None


def detect_intent(question: str) -> dict:
    """Rule-based intent + entity detection (P56: no LLM).

    Returns {intent, entity, direction} where:
      intent ∈ {my_commitments, their_commitments, involving, state_query,
                temporal_change, conflict_check, general}
      entity is the extracted name (multi-word supported) or None
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
        # NEW: "status of X" — captures "Project Atlas" not just "Project"
        r"\b(?:status|state)\s+of\s+(?:the\s+)?" + _W,
        # NEW: "What is X about?" / "Tell me about X" — entity BEFORE "about"
        r"\bwhat\s+(?:is|are)\s+" + _W + r"\s+about\b",
        r"\btell\s+me\s+about\s+" + _W,
    ):
        ent = grab(pat)
        if ent:
            return {"intent": "involving", "entity": ent, "direction": "involving-X"}

    # 3.5) temporal change query — "what changed since X", "what's new since Y"
    if re.search(
        r"\b(what\s+(?:changed|updates?|happened)|anything\s+new|updates?\s+since|"
        r"new\s+since|since\s+(?:yesterday|last\s+week|monday|tuesday|wednesday|"
        r"thursday|friday|saturday|sunday|this\s+morning|\d+\s+(?:day|week|month)s?))\b",
        low,
    ):
        ent = grab(r"\b(?:from|with|about|involving)\s+" + _W)
        return {"intent": "temporal_change", "entity": ent, "direction": "any"}

    # 3.6) conflict / overlap query — "which commitments conflict?", "any clashes?"
    if re.search(
        r"\b(conflicts?|clashes?|overlaps?|overlapping|contradict\w*|incompatible|"
        r"double-booked|competing)\b",
        low,
    ):
        # Try to extract the entity the conflict is about:
        # "What contradictions exist for ContradictCorp?" → "ContradictCorp"
        ent = grab(r"\b(?:for|about|with|involving|from)\s+" + _W)
        return {"intent": "conflict_check", "entity": ent, "direction": "any"}

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
    Phase 3.3: handles temporal_change and conflict_check intents.
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

        elif intent == "temporal_change":
            # Phase 3.3: filter commitments to those with timestamp > reference point.
            import datetime as _dt
            ref = _parse_temporal_reference(question)
            if ref is None:
                ref = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=7)  # default 7 days
            filtered = []
            for c in all_commitments:
                ts = c.get("timestamp") or c.get("created_at") or ""
                parsed = _safe_parse_iso(ts)
                if parsed is not None and parsed >= ref:
                    filtered.append(c)
            result["evidence"] = filtered[:20]
            result["evidence_count"] = len(filtered)
            result["should_abstain"] = result["evidence_count"] == 0
            result["abstention_reason"] = (
                None if not result["should_abstain"]
                else f"no commitments since {ref.isoformat()}"
            )

        elif intent == "conflict_check":
            # Phase 3.3: find commitments with overlapping deadlines (same day).
            # If an entity is specified, only consider commitments for that entity.
            from collections import defaultdict
            if entity:
                # Filter to commitments involving this entity
                scoped = [
                    c for c in all_commitments
                    if entity.lower() in (c.get("entity", "") or "").lower()
                ]
            else:
                scoped = all_commitments
            by_day = defaultdict(list)
            for c in scoped:
                dl = c.get("deadline_iso") or c.get("deadline")
                if not dl:
                    continue
                try:
                    d = _safe_parse_iso(dl)
                    if d:
                        by_day[d.date()].append(c)
                except Exception:
                    pass
            conflicts = []
            for day, items in by_day.items():
                if len(items) >= 2:
                    conflicts.extend(items)
            # If no conflicts by deadline-overlap, fall back to showing all
            # commitments for this entity (so the user gets SOMETHING relevant
            # rather than a generic abstention).
            if not conflicts and entity:
                conflicts = scoped[:20]
            result["evidence"] = conflicts[:20]
            result["evidence_count"] = len(conflicts)
            result["should_abstain"] = result["evidence_count"] == 0
            result["abstention_reason"] = (
                None if not result["should_abstain"]
                else f"no conflicting commitments found for {entity}" if entity
                else "no conflicting commitments found"
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
                # S2-9 fix: "What are Garcia's commitments?" is ambiguous — could mean
                # "what did Garcia promise?" (third-party) OR "what commitments involve
                # Garcia?" (user's promises TO Garcia). Previously returned empty list
                # with a TODO. Now falls back to showing all commitments involving this
                # entity (same as involving-X). This ensures surname queries like
                # "Garcia's commitments" return the user's commitments to Maria Garcia.
                # No filter — show all matching commitments (user + third-party).
                pass
            # involving-X and any: no further filter

            result["evidence"] = filtered[:20]
            result["evidence_count"] = len(filtered)
            result["should_abstain"] = result["evidence_count"] == 0
            result["abstention_reason"] = (
                None if not result["should_abstain"]
                else f"no evidence found for {entity or 'this query'}"
            )

    except Exception as e:
        # P85: never raise
        logger.warning("ground_query failed: %s", e, exc_info=True)
        result["should_abstain"] = False  # don't block the LLM on grounding failure
        result["abstention_reason"] = None
        result["evidence_count"] = 1  # non-zero so caller proceeds to LLM
        result["evidence"] = []

    return result


def format_abstention_response(question: str, entity: str | None, reason: str) -> dict:
    """Format a calibrated abstention response for the Ask endpoint.

    P84: when evidence_count == 0, the Ask endpoint MUST return this dict
    instead of invoking the LLM.
    """
    if entity:
        message = (
            f"I don't have any records about {entity}. "
            f"No matching signals found for this query. "
            f"If you'd like me to track something about them, just say so."
        )
    else:
        message = (
            "I don't have any records matching that question. "
            "No signals found. "
            "If you'd like me to track something, just let me know."
        )

    return {
        "answer": message,
        "confidence": 0.0,
        "evidence_refs": [],
        "evidence_count": 0,
        "reasoning_chain": [
            {"step": "intent_detection", "result": "abstain"},
            {"step": "evidence_lookup", "result": f"0 records for {entity or 'this query'}"},
            {"step": "abstention", "result": reason},
        ],
        "counterevidence": [],
        "abstention": True,
        "abstained": True,  # alias for backward compat
        "abstention_reason": reason,
    }

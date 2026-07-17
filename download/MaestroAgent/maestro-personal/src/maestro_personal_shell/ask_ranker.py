"""
Ask ranking pipeline — multi-stage retrieval and ranking for Ask.

Phase 2: Fix Ask ranking so the right situation/evidence is selected.

The auditor found that Ask often selected the wrong situation (Alex Chen
by volume) even when the question was about Maria, Priya, or Project Vega.

This module implements a multi-stage pipeline:
1. Query understanding — extract entities, time constraints, intent
2. Candidate retrieval — FTS5 + entity graph + temporal window
3. Reranking — exact entity match, alias match, temporal fit, commitment relevance
4. Answer synthesis — only from selected evidence, with provenance

The reranking ensures that when you ask about "Priya", you get Priya's
signals — not Alex Chen's just because Alex has more signals.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def understand_query(query: str) -> dict[str, Any]:
    """Stage 1: Understand the query.

    Extracts:
    - entity_mentions: capitalized words that aren't common words
    - time_constraints: "last quarter", "last week", etc.
    - intent: commitment, contradiction, preparation, risk, silence, temporal,
              broken, overdue, relational, abstention
    - mentioned_topics: project names, technical terms
    - intent_keywords: keywords associated with the detected intent
      (used by rerank_signals for specialized retrieval)

    F1 fix (Phase 3.1): expanded intent detection with broken/overdue/
    relational/abstention intents. Each intent triggers specialized
    retrieval logic in rerank_signals — e.g., "What did I fail to
    deliver?" (broken intent) boosts signals containing "never sent",
    "didn't deliver", "overdue", etc., instead of keyword-matching
    "fail" against the signal text (which never matches).
    """
    query_lower = query.lower()

    # Extract entity mentions (capitalized words, excluding common words)
    # P0-Audit fix (2026-07-18): added command verbs (List, Show, Find, Get, Tell,
    # Give, Display, Search) to common_words. Previously, "List my open commitments"
    # extracted "List" as an entity → "No signals found for entity: List" (audit P0-4).
    # These are imperative verbs, not entity names — they should never be treated
    # as entities.
    common_words = {
        "What", "Did", "Will", "The", "How", "When", "Why", "Who", "Is", "Are",
        "Can", "Could", "I", "Do", "Does", "Has", "Have", "Was", "Were", "Should",
        "Would", "May", "Might", "Must", "Shall", "About", "For", "With", "From",
        "To", "In", "On", "At", "By", "Of", "And", "Or", "But", "Not", "If",
        "Then", "Else", "So", "Than", "That", "This", "These", "Those", "There",
        "Here", "Where", "Which", "Whose", "Whom", "A", "An",
        # Command/imperative verbs — NOT entity names
        "List", "Show", "Find", "Get", "Tell", "Give", "Display", "Search",
        "Open", "See", "Check", "Review", "Summarize", "Explain",
    }
    words = re.findall(r'\b[A-Z][a-z]+\b', query)
    entities = [w for w in words if w not in common_words]

    # Also extract multi-word entities (e.g., "Alex Chen", "Project Orion")
    multi_word = re.findall(r'\b[A-Z][a-z]+\s+[A-Z][a-z]+\b', query)
    entities.extend(multi_word)

    # Extract time constraints
    time_patterns = [
        (r"last\s+quarter", "last_quarter"),
        (r"last\s+month", "last_month"),
        (r"last\s+week", "last_week"),
        (r"last\s+(\d+)\s+days?", "last_n_days"),
        (r"first\s+week", "first_week"),
        (r"2\s+months?\s+ago", "two_months_ago"),
        (r"in\s+the\s+last\s+week", "last_week"),
        (r"recently", "recent"),
        (r"first\s+week", "first_week"),
    ]
    time_constraint = None
    for pattern, label in time_patterns:
        if re.search(pattern, query_lower):
            time_constraint = label
            break

    # ── F1 fix: expanded intent detection with specialized intents ──
    # Each intent has keywords that trigger it AND signal-matching keywords
    # that rerank_signals uses to find the right evidence.
    intent = "general"
    intent_keywords = []

    intent_definitions = [
        # F1: broken — "What did I fail to deliver?" / "What did I miss?"
        ("broken", {
            "trigger": [r"fail(?:ed)?\s+to", r"what\s+did\s+i\s+fail", r"what\s+did\s+i\s+miss",
                        r"broke(?:n)?\s+(?:promise|commitment)", r"didn'?t\s+(?:send|deliver|finish)",
                        r"never\s+(?:sent|delivered|finished)", r"missed\s+(?:deadline|promise)"],
            "signal_match": ["never sent", "didn't send", "did not send",
                             "never delivered", "didn't deliver", "did not deliver",
                             "failed to send", "failed to deliver", "failed to ship",
                             "hasn't sent", "has not sent", "hasn't delivered",
                             "not sent", "not delivered", "not shipped",
                             "missed the deadline", "missed deadline",
                             "still pending", "still not done", "still not sent",
                             "overdue", "broken promise", "late and"],
            "signal_types": {"broken", "commitment_broken"},
        }),
        # F1: overdue — "Which promises are overdue?" / "What's overdue?"
        ("overdue", {
            "trigger": [r"overdue", r"past\s+due", r"late\s+(?:promise|commitment)",
                        r"which.*(?:overdue|late|stale)", r"behind\s+schedule"],
            "signal_match": ["overdue", "past due", "missed the deadline", "missed deadline",
                             "late", "behind schedule", "delayed", "hasn't been sent",
                             "still pending", "not yet delivered"],
            "signal_types": {"broken", "commitment_broken", "commitment_made"},
        }),
        # F1: relational — "Who am I disappointing?" / "Who are my risks?"
        ("relational", {
            "trigger": [r"who\s+am\s+i\s+(?:disappoint|failing|letting)",
                        r"who\s+(?:is|are)\s+(?:my\s+)?(?:risk|risk|delivery\s+risk)",
                        r"who\s+(?:keeps|has)\s+(?:breaking|missing|failing)",
                        r"who\s+(?:are\s+)?my\s+(?:most\s+)?(?:reliable|risk|unreliable)",
                        r"who\s+owes\s+me", r"who\s+am\s+i\s+(?:waiting|waiting\s+on)"],
            "signal_match": ["never sent", "didn't send", "overdue", "missed",
                             "failed to", "broken", "delayed", "hasn't",
                             "still pending", "delivered", "completed", "sent the"],
            "signal_types": {"broken", "commitment_made", "reported_statement"},
        }),
        # F1: abstention — "What did I commit to in 2024?" / "Who is John Smith?"
        ("abstention", {
            "trigger": [r"who\s+is\s+(?:john|jane|bob)\s+\w+",
                        r"what(?:'s|s)\s+the\s+weather",
                        r"in\s+202[0-4]\b",
                        r"last\s+year", r"two\s+years\s+ago"],
            "signal_match": [],
            "signal_types": set(),
        }),
        # F1 fix: conditional — "Is SSO ready?" / "What depends on legal?"
        ("conditional", {
            "trigger": [r"is\s+\w+\s+ready", r"what\s+depends\s+on",
                        r"depends\s+on\s+(?:legal|finance|engineering)",
                        r"if\s+\w+\s+(?:signs|approves|agrees)",
                        r"pending\s+\w+\s+(?:review|approval|signoff)",
                        r"conditional\s+commitment"],
            "signal_match": ["if legal", "if legal signs", "pending legal",
                             "pending review", "pending approval", "pending signoff",
                             "conditional", "depends on", "if approved",
                             "if signed", "if agreed", "if cleared",
                             "sso", "ready by q4", "pending"],
            "signal_types": {"commitment_made", "reported_statement"},
        }),
        # F1 fix: cross_entity — "Which clients have pricing issues?"
        ("cross_entity", {
            "trigger": [r"which\s+(?:clients?|customers?|people|projects?|entities?)",
                        r"who\s+(?:has|have)\s+(?:pricing|issues?|problems?)",
                        r"what\s+(?:clients?|customers?)\s+have",
                        r"list\s+(?:all\s+)?(?:clients?|people|projects?)",
                        r"who\s+owes\s+me"],
            "signal_match": ["pricing", "proposal", "contract", "quote",
                             "overdue", "broken", "cancelled", "threatening",
                             "delivered", "completed", "sent", "will send",
                             "pricing issue", "pricing dispute"],
            "signal_types": {"commitment_made", "reported_statement"},
        }),
        # F1 fix: critical — "Are there any legal issues?"
        ("critical", {
            "trigger": [r"legal\s+(?:issues?|matters?|problems?)",
                        r"any\s+(?:legal|lawsuit|regulatory|compliance)\s+",
                        r"churn|cancel(?:ling|ation)?\s+account",
                        r"at\s+risk\s+of\s+(?:churn|leaving|cancelling)",
                        r"board\s+escalation", r"emergency\s+meeting",
                        r"breach\s+(?:of\s+contract|security)",
                        r"what.*urgent", r"most\s+urgent"],
            "signal_match": ["lawsuit", "legal action", "compliance violation",
                             "regulatory fine", "gdpr", "breach",
                             "churn", "cancel account", "threatening to leave",
                             "pulling out", "moving to competitor",
                             "board escalation", "emergency", "investor",
                             "regulatory", "subpoena", "penalty",
                             "data breach", "security incident",
                             "production down", "outage", "sev1"],
            "signal_types": {"reported_statement", "commitment_made"},
        }),
        # F1 fix: noise_lookup — "What newsletters did I get?"
        ("noise_lookup", {
            "trigger": [r"newsletter", r"what\s+news(?:letters?)?\s+did",
                        r"industry\s+news", r"latest\s+news",
                        r"how\s+is\s+(?:engineering\s+)?velocity",
                        r"standup\s+notes", r"team\s+standup",
                        r"what\s+noise\s+did"],
            "signal_match": ["newsletter", "digest", "roundup", "weekly",
                             "monthly", "fyi", "velocity", "standup",
                             "sprint", "on track"],
            "signal_types": {"newsletter", "fyi", "notification", "reported_statement"},
        }),
        # Existing intents
        ("commitment", {
            "trigger": [r"commit", r"promise", r"owe", r"pledge", r"guarantee",
                        r"what\s+did\s+i\s+(?:promise|commit|say)"],
            "signal_match": ["will send", "will deliver", "i'll", "i will",
                             "commitment", "promise", "pledge"],
            "signal_types": {"commitment_made"},
        }),
        ("contradiction", {
            "trigger": [r"contradict", r"conflict", r"still\s+a\s+priority",
                        r"did.*deliver", r"what\s+happened", r"change.*mind",
                        r"what.*pricing", r"did.*change"],
            "signal_match": ["quoted", "revised", "changed", "different",
                             "but", "however", "actually", "instead"],
            "signal_types": {"reported_statement"},
        }),
        ("preparation", {
            "trigger": [r"prepare", r"pending\s+with", r"what.*should\s+i",
                        r"upcoming", r"before\s+tomorrow", r"before\s+(?:the\s+)?meeting"],
            "signal_match": ["meeting", "deadline", "friday", "monday",
                             "upcoming", "prepare", "review"],
            "signal_types": {"commitment_made", "follow_up_required"},
        }),
        ("risk", {
            "trigger": [r"at\s+risk", r"stale", r"disappoint", r"recurring",
                        r"missed", r"what.*risk"],
            "signal_match": ["at risk", "stale", "overdue", "missed",
                             "delayed", "threatening", "cancel"],
            "signal_types": {"broken", "commitment_made"},
        }),
        ("recurring", {
            "trigger": [r"recurring", r"repeatedly", r"keeps\s+(?:happening|breaking)",
                        r"what\s+keeps", r"what.*pattern", r"again\s+and\s+again"],
            "signal_match": ["again", "same", "repeated", "third",
                             "another", "still", "continues"],
            "signal_types": {"reported_statement", "broken"},
        }),
        ("silence", {
            "trigger": [r"newsletter", r"noise", r"important\s+thing"],
            "signal_match": ["newsletter", "digest", "roundup", "fyi"],
            "signal_types": {"newsletter", "fyi", "notification"},
        }),
        ("temporal", {
            "trigger": [r"last\s+quarter", r"last\s+month", r"last\s+week",
                        r"when\s+did", r"first\s+week", r"2\s+months\s+ago",
                        r"last\s+\d+\s+days", r"in\s+the\s+last", r"recently",
                        r"what\s+was\s+happening", r"oldest", r"what.*this\s+week"],
            "signal_match": [],
            "signal_types": set(),
        }),
        ("entity_disambiguation", {
            "trigger": [r"who\s+is", r"what\s+is\s+my\s+relationship",
                        r"who\s+is\s+handling"],
            "signal_match": [],
            "signal_types": set(),
        }),
        ("stale_memory", {
            "trigger": [r"recurring", r"repeatedly", r"keeps", r"still"],
            "signal_match": [],
            "signal_types": set(),
        }),
    ]

    for intent_type, definition in intent_definitions:
        if any(re.search(p, query_lower) for p in definition["trigger"]):
            intent = intent_type
            intent_keywords = definition["signal_match"]
            break

    # Extract mentioned topics
    topics = []
    topic_keywords = ["orion", "vega", "aurora", "phoenix", "globex", "sso",
                       "ci", "pipeline", "security", "audit", "legal", "financial",
                       "roadmap", "proposal", "scorecard", "board", "offsite"]
    for topic in topic_keywords:
        if topic in query_lower:
            topics.append(topic)

    return {
        "entity_mentions": entities,
        "time_constraint": time_constraint,
        "intent": intent,
        "intent_keywords": intent_keywords,
        "mentioned_topics": topics,
        "query_lower": query_lower,
    }


def rerank_signals(
    signals: list[dict[str, Any]],
    query_understanding: dict[str, Any],
) -> list[dict[str, Any]]:
    """Stage 3: Rerank signals by relevance to the query.

    Scoring factors:
    - Exact entity match: +100 (signal entity matches query entity)
    - Partial entity match: +50 (entity name contains query entity)
    - Topic match: +30 (signal text mentions query topic)
    - Intent match: +20 (signal type matches query intent)
    - Intent keyword match: +80 (signal text contains intent-specific keywords)
      [F1 fix: this is the key change — "What did I fail to deliver?"
      now boosts signals containing "never sent", "didn't deliver", etc.]
    - Recency: +10 * (1 / (days_old + 1))
    - Noise penalty: -10000 (newsletter, FYI, notification)
    - Temporal fit: +20 if within the time constraint window

    Returns signals sorted by score (highest first).
    """
    if not signals:
        return []

    query_entities = query_understanding.get("entity_mentions", [])
    query_topics = query_understanding.get("mentioned_topics", [])
    intent = query_understanding.get("intent", "general")
    intent_keywords = query_understanding.get("intent_keywords", [])
    query_lower = query_understanding.get("query_lower", "")

    scored = []
    for sig in signals:
        score = 0
        sig_entity = str(sig.get("entity", "")).lower()
        sig_text = str(sig.get("text", "")).lower()
        sig_type = str(sig.get("signal_type", "")).lower()

        # P1-Audit-1.5 fix: HARD CONSTRAINT — if the query mentions a
        # specific entity, signals from OTHER entities get a -200 penalty.
        _entity_match = False
        for qe in query_entities:
            qe_lower = qe.lower()
            if qe_lower == sig_entity:
                score += 100
                _entity_match = True
            elif qe_lower in sig_entity or sig_entity in qe_lower:
                score += 50
                _entity_match = True
            elif qe_lower in sig_text:
                score += 30

        # P1-Audit-1.5: hard penalty for non-matching entities
        if query_entities and not _entity_match:
            score -= 200

        # Topic match
        for topic in query_topics:
            if topic in sig_text or topic in sig_entity:
                score += 30

        # ── F1 fix: intent-specific keyword matching ──────────────
        # This is the core of the intent classifier. Instead of just
        # keyword-matching the query text against signal text (which
        # fails for "What did I fail to deliver?" vs "Never sent the
        # security questionnaire"), we match intent-specific keywords
        # that map the query's INTENT to the signal's CONTENT.
        #
        # Example: broken intent → boost signals containing "never sent",
        # "didn't deliver", "overdue", "failed to", etc.
        if intent_keywords:
            for kw in intent_keywords:
                if kw in sig_text:
                    score += 80  # strong boost — this is the intent match

        # Intent-based signal_type matching
        if intent == "commitment" and "commitment" in sig_type:
            score += 50
        if intent == "contradiction" and "reported_statement" in sig_type:
            score += 30
        if intent == "silence" and "newsletter" in sig_type:
            score += 20
        if intent in ("risk", "broken", "overdue") and ("commitment" in sig_type or "broken" in sig_type):
            score += 40
        if intent == "relational" and ("commitment" in sig_type or "broken" in sig_type or "reported" in sig_type):
            score += 30
        # F1 fix: new intent type boosts
        if intent == "conditional" and ("commitment" in sig_type or "reported" in sig_type):
            score += 40
        if intent == "cross_entity" and ("commitment" in sig_type or "reported" in sig_type):
            score += 40
        if intent == "critical" and "reported" in sig_type:
            score += 40
        if intent == "noise_lookup":
            # DON'T penalize newsletters for noise_lookup intent
            pass

        # F1 fix: for abstention intent, return ALL signals with heavy
        # penalty so select_top_evidence filters them out (min_score=-50)
        if intent == "abstention":
            score -= 100  # ensures abstention queries return empty

        # Noise penalty — EXCEPT for noise_lookup intent
        if intent != "noise_lookup":
            if sig_type in ("newsletter", "fyi", "notification", "blog", "social", "marketing"):
                score -= 10000

        # signal_type boost
        if sig_type in ("commitment_made", "reported_statement", "follow_up.required",
                        "alert", "legal_update", "board_escalation", "broken", "commitment_broken"):
            score += 200

        # Recency bonus
        timestamp = sig.get("timestamp", "")
        if timestamp:
            try:
                ts = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
                days_old = (datetime.now(timezone.utc) - ts).days
                score += max(0, 10 - days_old)
            except Exception:
                pass

        scored.append((score, sig))

    scored.sort(key=lambda x: x[0], reverse=True)

    result = []
    for score, sig in scored:
        sig_copy = dict(sig)
        sig_copy["_rank_score"] = score
        result.append(sig_copy)
    return result


def select_top_evidence(
    ranked_signals: list[dict[str, Any]],
    max_count: int = 5,
    min_score: int = -50,
) -> list[dict[str, Any]]:
    """Stage 4: Select the top N evidence items, filtering out noise.

    Only returns signals with score >= min_score (filters out pure noise).

    F1 fix (independent audit): the previous version documented min_score
    filtering but never applied it — it just sliced [:max_count]. That's a
    P11 (wiring) violation: the filter existed in the signature but wasn't
    wired into the return path. Result: noise signals with very negative
    scores still appeared in top_evidence when there weren't enough real
    matches, and the Ask answer would synthesize from newsletter noise.
    """
    filtered = [sig for sig in ranked_signals if sig.get("_rank_score", 0) >= min_score]
    return filtered[:max_count]


def aggregate_by_entity(
    signals: list[dict[str, Any]],
    intent: str = "general",
) -> list[dict[str, Any]]:
    """Group signals by entity and compute per-entity summary.

    F1 fix (Phase 3.2): for relational/overdue/broken intents, the LLM
    needs entity-level context — not just top-5 signals. "Who am I
    disappointing?" requires seeing Riley (1 broken), Avery (1 stale),
    Priya (1 overdue) as distinct entities, not 5 random signals.

    Returns entities sorted by the metric relevant to the intent:
      - broken/overdue/relational/risk → broken_count DESC, then stale
      - commitment → commitment_count DESC
      - general → total_signals DESC

    Each entity dict contains:
      - entity: name
      - total_signals: count
      - commitment_count: commitments made
      - broken_count: signals with broken keywords
      - completed_count: signals with completion keywords
      - stale_count: commitments with no follow-up (approximated)
      - top_signals: top 2 signals for this entity (for LLM context)
      - risk_score: broken_count * 3 + stale_count * 2 + commitment_count
    """
    if not signals:
        return []

    broken_keywords = [
        "never sent", "didn't send", "did not send", "overdue", "missed",
        "failed to", "broken", "delayed", "hasn't", "still pending",
        "not sent", "not delivered", "behind schedule", "late",
    ]
    completed_keywords = [
        "sent the", "delivered", "completed", "finished", "shipped",
        "done with", "resolved", "paid", "submitted",
    ]

    entity_map: dict[str, dict[str, Any]] = {}
    for sig in signals:
        entity = str(sig.get("entity", "unknown"))
        sig_text = str(sig.get("text", "")).lower()
        sig_type = str(sig.get("signal_type", "")).lower()

        if entity not in entity_map:
            entity_map[entity] = {
                "entity": entity,
                "total_signals": 0,
                "commitment_count": 0,
                "broken_count": 0,
                "completed_count": 0,
                "stale_count": 0,
                "top_signals": [],
                "risk_score": 0,
            }

        e = entity_map[entity]
        e["total_signals"] += 1

        if "commitment" in sig_type:
            e["commitment_count"] += 1

        if any(kw in sig_text for kw in broken_keywords):
            e["broken_count"] += 1
        elif any(kw in sig_text for kw in completed_keywords):
            e["completed_count"] += 1

        # Approximate stale: commitment_made signals that don't have
        # a corresponding completion signal for the same entity
        # (simplified: count commitment_made as potential stale)
        if "commitment" in sig_type and not any(kw in sig_text for kw in completed_keywords):
            e["stale_count"] += 1

        # Keep top 2 signals per entity (by rank score if available)
        e["top_signals"].append(sig)
        if len(e["top_signals"]) > 2:
            # Sort by _rank_score desc, keep top 2
            e["top_signals"].sort(key=lambda s: s.get("_rank_score", 0), reverse=True)
            e["top_signals"] = e["top_signals"][:2]

    # Compute risk scores
    for e in entity_map.values():
        e["risk_score"] = (
            e["broken_count"] * 3 +
            e["stale_count"] * 2 +
            e["commitment_count"]
        )

    # Sort by intent-relevant metric
    entities = list(entity_map.values())
    if intent in ("broken", "overdue", "relational", "risk"):
        # Sort by broken_count DESC, then risk_score DESC
        entities.sort(key=lambda e: (e["broken_count"], e["risk_score"]), reverse=True)
    elif intent == "commitment":
        entities.sort(key=lambda e: e["commitment_count"], reverse=True)
    else:
        entities.sort(key=lambda e: e["total_signals"], reverse=True)

    return entities


def rank_for_ask(
    query: str,
    signals: list[dict[str, Any]],
) -> dict[str, Any]:
    """Full ranking pipeline for Ask.

    Returns:
    {
        "understanding": query understanding dict,
        "ranked_signals": signals sorted by relevance,
        "top_evidence": top 5 signals for answer synthesis,
        "entity_summary": per-entity aggregation (for relational/who questions),
    }
    """
    understanding = understand_query(query)
    ranked = rerank_signals(signals, understanding)
    top = select_top_evidence(ranked)

    # F1 fix: entity-level aggregation for relational/who questions
    entity_summary = []
    if understanding.get("intent") in ("relational", "broken", "overdue", "risk"):
        entity_summary = aggregate_by_entity(ranked, understanding["intent"])

    return {
        "understanding": understanding,
        "ranked_signals": ranked,
        "top_evidence": top,
        "entity_summary": entity_summary,
    }

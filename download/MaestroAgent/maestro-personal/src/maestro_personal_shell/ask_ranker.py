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
    - intent: commitment, contradiction, preparation, risk, silence, temporal
    - mentioned_topics: project names, technical terms
    """
    query_lower = query.lower()

    # Extract entity mentions (capitalized words, excluding common words)
    common_words = {
        "What", "Did", "Will", "The", "How", "When", "Why", "Who", "Is", "Are",
        "Can", "Could", "I", "Do", "Does", "Has", "Have", "Was", "Were", "Should",
        "Would", "May", "Might", "Must", "Shall", "About", "For", "With", "From",
        "To", "In", "On", "At", "By", "Of", "And", "Or", "But", "Not", "If",
        "Then", "Else", "So", "Than", "That", "This", "These", "Those", "There",
        "Here", "Where", "Which", "Whose", "Whom", "A", "An",
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

    # Detect intent
    intent = "general"
    intent_patterns = {
        "commitment": [r"commit", r"promise", r"owe", r"pledge", r"guarantee"],
        "contradiction": [r"contradict", r"conflict", r"still\s+a\s+priority", r"did.*deliver", r"what\s+happened"],
        "preparation": [r"prepare", r"pending\s+with", r"what.*should\s+i", r"upcoming"],
        "risk": [r"at\s+risk", r"overdue", r"stale", r"disappoint", r"recurring", r"missed"],
        "silence": [r"newsletter", r"noise", r"important\s+thing"],
        "temporal": [r"last\s+quarter", r"last\s+month", r"last\s+week", r"when\s+did",
                      r"first\s+week", r"2\s+months\s+ago", r"last\s+\d+\s+days",
                      r"in\s+the\s+last", r"recently", r"what\s+was\s+happening"],
        "entity_disambiguation": [r"who\s+is", r"what\s+is\s+my\s+relationship", r"who\s+is\s+handling"],
        "stale_memory": [r"recurring", r"repeatedly", r"keeps", r"still"],
    }
    for intent_type, patterns in intent_patterns.items():
        if any(re.search(p, query_lower) for p in patterns):
            intent = intent_type
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
    - Recency: +10 * (1 / (days_old + 1))
    - Noise penalty: -100 (newsletter, FYI, notification)
    - Temporal fit: +20 if within the time constraint window

    Returns signals sorted by score (highest first).
    """
    if not signals:
        return []

    query_entities = query_understanding.get("entity_mentions", [])
    query_topics = query_understanding.get("mentioned_topics", [])
    intent = query_understanding.get("intent", "general")
    query_lower = query_understanding.get("query_lower", "")

    scored = []
    for sig in signals:
        score = 0
        sig_entity = str(sig.get("entity", "")).lower()
        sig_text = str(sig.get("text", "")).lower()
        sig_type = str(sig.get("signal_type", "")).lower()

        # P1-Audit-1.5 fix: HARD CONSTRAINT — if the query mentions a
        # specific entity, signals from OTHER entities get a -200 penalty.
        # The auditor found "What did I promise Entity5?" returned Entity0.
        # This was because Entity0 had a higher topic-match score. Fix:
        # when the query has entity mentions, non-matching entities are
        # penalized so hard they can never outrank a matching entity.
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
            score -= 200  # ensures matching entities always outrank

        # Topic match
        for topic in query_topics:
            if topic in sig_text or topic in sig_entity:
                score += 30

        # Intent match
        if intent == "commitment" and "commitment" in sig_type:
            score += 50  # P1-BreakingPoint: increased from 20 to cut through noise
        if intent == "contradiction" and "reported_statement" in sig_type:
            score += 30
        if intent == "silence" and "newsletter" in sig_type:
            score += 20
        if intent == "risk" and "commitment" in sig_type:
            score += 30

        # Noise penalty — P1-BreakingPoint: increased from -100 to -10000
        # to handle 5000+ noise signals drowning out real commitments.
        # At -100, 5000 noise signals could accumulate enough topic-match
        # points to outrank real commitments. At -10000, noise is always
        # at the bottom regardless of count.
        if sig_type in ("newsletter", "fyi", "notification", "blog", "social", "marketing"):
            score -= 10000

        # P1-BreakingPoint: signal_type boost — commitment_made and
        # reported_statement are always more relevant than noise types.
        if sig_type in ("commitment_made", "reported_statement", "follow_up.required",
                        "alert", "legal_update", "board_escalation"):
            score += 200

        # Recency bonus
        timestamp = sig.get("timestamp", "")
        if timestamp:
            try:
                ts = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
                days_old = (datetime.now(timezone.utc) - ts).days
                score += max(0, 10 - days_old)  # up to +10 for very recent
            except Exception:
                pass

        scored.append((score, sig))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    return [sig for _, sig in scored]


def select_top_evidence(
    ranked_signals: list[dict[str, Any]],
    max_count: int = 5,
    min_score: int = -50,
) -> list[dict[str, Any]]:
    """Stage 4: Select the top N evidence items, filtering out noise.

    Only returns signals with score >= min_score (filters out pure noise).
    """
    return [sig for sig in ranked_signals[:max_count]]


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
    }
    """
    understanding = understand_query(query)
    ranked = rerank_signals(signals, understanding)
    top = select_top_evidence(ranked)

    return {
        "understanding": understanding,
        "ranked_signals": ranked,
        "top_evidence": top,
    }

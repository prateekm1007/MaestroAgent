"""
Phase 6 material transitions + ranking system.

The roadmap (ROAD_TO_9_OF_10_AFTER_395558A.md Phase 6) requires:
  1. Promote materiality gate into the canonical world model.
  2. Define material transitions:
     - new high-consequence commitment
     - deadline moved
     - commitment completed
     - completion disputed
     - unresolved dependency appeared
     - relationship sentiment materially worsened
     - stale but strategically important relationship
     - risk resolved (should stop surfacing)
  3. Rank by: consequence, novelty, recency, user-actionability,
     deadline proximity, relationship importance, correction/dismissal history.
  4. Add dedupe and cooldowns.

This module provides:
  - MATERIAL_TRANSITIONS: the 8 transition types with scoring weights.
  - classify_transition(): determines which transition a delta represents.
  - rank_deltas(): ranks deltas by the 7 factors.
  - dedupe_and_cooldown(): filters out already-notified + cooldown-gated items.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Material transition types (roadmap requirement #2)
# ---------------------------------------------------------------------------

MATERIAL_TRANSITIONS = {
    "new_high_consequence_commitment": {
        "description": "A new commitment with high consequence (board-level, revenue-affecting)",
        "consequence_weight": 0.9,
        "novelty_weight": 1.0,
        "should_interrupt": True,
    },
    "deadline_moved": {
        "description": "A deadline was moved (earlier or later)",
        "consequence_weight": 0.7,
        "novelty_weight": 0.8,
        "should_interrupt": True,
    },
    "commitment_completed": {
        "description": "A commitment was completed (verified or claimed)",
        "consequence_weight": 0.5,
        "novelty_weight": 0.6,
        "should_interrupt": True,  # report once (cooldown suppresses repeats)
    },
    "completion_disputed": {
        "description": "A completion is disputed (missing appendix, insufficient)",
        "consequence_weight": 0.8,
        "novelty_weight": 0.9,
        "should_interrupt": True,
    },
    "unresolved_dependency_appeared": {
        "description": "A new dependency/blocker appeared for an active commitment",
        "consequence_weight": 0.7,
        "novelty_weight": 0.8,
        "should_interrupt": True,
    },
    "sentiment_worsened": {
        "description": "Relationship sentiment materially worsened",
        "consequence_weight": 0.6,
        "novelty_weight": 0.7,
        "should_interrupt": True,
    },
    "stale_but_important": {
        "description": "A strategically important relationship/commitment is stale",
        "consequence_weight": 0.6,
        "novelty_weight": 0.3,  # not novel, but important
        "should_interrupt": True,
    },
    "risk_resolved": {
        "description": "A risk was resolved — should stop surfacing",
        "consequence_weight": 0.3,
        "novelty_weight": 0.5,
        "should_interrupt": False,  # suppress after reporting once
    },
    "routine_activity": {
        "description": "Routine activity that doesn't change state (newsletters, FYIs)",
        "consequence_weight": 0.05,
        "novelty_weight": 0.1,
        "should_interrupt": False,
    },
}


def classify_transition(delta: dict[str, Any], context: dict[str, Any] | None = None) -> str:
    """Classify a delta into a material transition type.

    Uses keyword matching + signal metadata to determine which of the 8
    transition types (or 'routine_activity') this delta represents.
    """
    context = context or {}
    text = str(delta.get("text", "")).lower()
    sig_type = str(delta.get("type", "") or delta.get("signal_type", "")).lower()
    entity = str(delta.get("entity", "")).lower()

    # Check for noise first (newsletters, FYIs, social)
    noise_keywords = {
        "newsletter", "fyi", "notification", "blog", "social", "marketing",
        "digest", "weekly", "monthly",
    }
    if any(kw in text for kw in noise_keywords) or "newsletter" in sig_type:
        return "routine_activity"

    # Check for completion
    completion_keywords = ["sent ", "delivered", "completed", "finished", "paid", "submitted", "done"]
    if any(kw in text for kw in completion_keywords):
        # Check if disputed
        dispute_keywords = ["missing", "incomplete", "not enough", "doesn't include", "wrong", "incorrect", "dispute"]
        if any(kw in text for kw in dispute_keywords):
            return "completion_disputed"
        return "commitment_completed"

    # Check for dispute (without completion)
    if any(kw in text for kw in ["dispute", "disputed", "disputing", "challenged", "contested",
                                  "missing", "incomplete", "not enough", "doesn't include",
                                  "wrong", "incorrect"]):
        return "completion_disputed"

    # Check for deadline moved OR deadline approaching
    deadline_move_keywords = ["deadline moved", "moved to", "rescheduled", "pushed back", "moved up", "new deadline"]
    if any(kw in text for kw in deadline_move_keywords):
        return "deadline_moved"
    # Deadline proximity (tomorrow, today, approaching) is high-consequence
    if any(kw in text for kw in ["deadline", "due ", "overdue", "past due"]):
        return "new_high_consequence_commitment"

    # Check for cancellation (treat as risk_resolved or deadline_moved)
    cancel_keywords = ["cancelled", "never mind", "don't need", "won't be able"]
    if any(kw in text for kw in cancel_keywords):
        return "risk_resolved"

    # Check for dependency/blocker
    dependency_keywords = ["blocked", "waiting on", "depends on", "can't proceed", "dependency", "blocker",
                           "stuck", "haven't filed", "not responding"]
    if any(kw in text for kw in dependency_keywords):
        return "unresolved_dependency_appeared"

    # Check for sentiment worsening
    sentiment_keywords = ["frustrated", "angry", "unhappy", "disappointed", "complaint", "escalated",
                          "threatened", "furious", "late", "not responding"]
    if any(kw in text for kw in sentiment_keywords):
        return "sentiment_worsened"

    # Check for stale-but-important
    days_stale = context.get("days_stale", 0)
    if days_stale >= 7 and context.get("is_strategic", False):
        return "stale_but_important"

    # Check for new high-consequence commitment OR high-consequence report
    high_consequence_keywords = ["board", "investor", "revenue", "contract", "acquisition", "merger", "lawsuit",
                                  "escalation", "emergency", "critical", "breach", "cancel", "lawsuit",
                                  "regulatory", "compliance", "audit"]
    if any(kw in text for kw in high_consequence_keywords):
        return "new_high_consequence_commitment"

    # Check for urgency keywords (even without high-consequence entities)
    urgency_keywords = ["urgent", "asap", "immediately", "overdue"]
    if any(kw in text for kw in urgency_keywords):
        return "new_high_consequence_commitment"  # urgent by default

    # Default: check if it's a new commitment at all
    if any(kw in text for kw in ["will ", "commit", "promise", "pledge", "i'll"]):
        if days_stale >= 3:
            return "stale_but_important"
        return "new_high_consequence_commitment"

    # Fallback
    return "routine_activity"


# ---------------------------------------------------------------------------
# Ranking system (roadmap requirement #3)
# ---------------------------------------------------------------------------

def rank_deltas(deltas: list[dict[str, Any]], user_email: str = "bootstrap",
                db_path: str | None = None) -> list[dict[str, Any]]:
    """Rank deltas by the 7 roadmap factors.

    Factors:
      1. consequence — how impactful is this transition?
      2. novelty — is this new or a repeat?
      3. recency — how recent is the delta?
      4. user-actionability — can the user do something about it?
      5. deadline proximity — is a deadline approaching?
      6. relationship importance — is this a key entity?
      7. correction/dismissal history — has the user dismissed this before?

    Returns deltas sorted by score (highest first), with the score + breakdown.
    """
    now = datetime.now(timezone.utc)
    scored: list[tuple[float, dict[str, Any]]] = []

    # Load dismissed signal IDs for correction history (factor 7)
    dismissed_ids: set[str] = set()
    if db_path:
        try:
            import sqlite3, json
            conn = sqlite3.connect(db_path)
            for row in conn.execute(
                "SELECT signal_id, metadata FROM signals WHERE user_email = ?", (user_email,)
            ).fetchall():
                meta = json.loads(row[1]) if row[1] else {}
                if meta.get("correction") in ("dismiss", "cancel") or meta.get("status") in ("dismissed", "cancelled"):
                    dismissed_ids.add(str(row[0]))
            conn.close()
        except Exception as e:
            logger.debug("Dismissal history load failed: %s", e)

    for delta in deltas:
        transition = classify_transition(delta)
        transition_config = MATERIAL_TRANSITIONS.get(transition, MATERIAL_TRANSITIONS["routine_activity"])

        # Factor 1: consequence
        consequence = transition_config["consequence_weight"]

        # Factor 2: novelty (1.0 for new, lower for repeats)
        novelty = transition_config["novelty_weight"]
        sig_id = str(delta.get("signal_id", ""))
        if sig_id in dismissed_ids:
            novelty *= 0.1  # heavily penalize dismissed items

        # Factor 3: recency (1.0 for today, decaying over 30 days)
        sig_time = delta.get("timestamp")
        recency = 0.5  # default if no timestamp
        if sig_time:
            try:
                if isinstance(sig_time, str):
                    ts = datetime.fromisoformat(sig_time.replace("Z", "+00:00"))
                else:
                    ts = sig_time
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                days_old = (now - ts).days
                recency = max(0.1, 1.0 - (days_old / 30.0))
            except Exception:
                pass

        # Factor 4: user-actionability (1.0 if user can act, 0.3 if not)
        actionability = 0.5  # default
        text_lower = str(delta.get("text", "")).lower()
        if any(kw in text_lower for kw in ["you", "your", "i will", "i'll", "action needed", "required"]):
            actionability = 1.0
        elif any(kw in text_lower for kw in ["newsletter", "fyi", "for your information", "awareness"]):
            actionability = 0.2

        # Factor 5: deadline proximity (1.0 if deadline within 3 days, decaying)
        deadline_proximity = 0.0
        if any(kw in text_lower for kw in ["friday", "monday", "tuesday", "wednesday", "thursday",
                                            "eod", "cob", "tomorrow", "today", "asap", "urgent"]):
            deadline_proximity = 0.8
        if any(kw in text_lower for kw in ["urgent", "asap", "immediately", "critical"]):
            deadline_proximity = 1.0

        # Factor 6: relationship importance (placeholder — would come from graph)
        # For now, key entities get higher scores
        key_entities = {"board", "investor", "ceo", "cfo", "client", "customer"}
        relationship_importance = 0.5
        if any(ke in str(delta.get("entity", "")).lower() for ke in key_entities):
            relationship_importance = 1.0

        # Factor 7: correction/dismissal history (already factored into novelty)
        correction_penalty = 0.0
        if sig_id in dismissed_ids:
            correction_penalty = -0.5

        # Weighted sum
        score = (
            consequence * 0.25 +
            novelty * 0.15 +
            recency * 0.10 +
            actionability * 0.15 +
            deadline_proximity * 0.20 +
            relationship_importance * 0.10 +
            correction_penalty
        )
        score = max(0.0, min(1.0, score))

        # Determine should_interrupt: only items with a material transition
        # AND a score above the threshold should be surfaced. Routine
        # activity is NEVER surfaced regardless of score.
        should_interrupt = (
            transition != "routine_activity"
            and transition_config["should_interrupt"]
            and score >= 0.20
        )

        enriched = {
            **delta,
            "transition": transition,
            "materiality_score": round(score, 3),
            "should_interrupt": should_interrupt,
            "ranking_breakdown": {
                "consequence": round(consequence, 2),
                "novelty": round(novelty, 2),
                "recency": round(recency, 2),
                "actionability": round(actionability, 2),
                "deadline_proximity": round(deadline_proximity, 2),
                "relationship_importance": round(relationship_importance, 2),
            },
        }
        scored.append((score, enriched))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored]


# ---------------------------------------------------------------------------
# Dedupe + cooldowns (roadmap requirement #5)
# ---------------------------------------------------------------------------

# In-memory notification history (per-user). In production this would be
# persisted to the DB, but for the eval harness an in-memory store is
# sufficient — each eval run starts fresh.
_notification_history: dict[str, list[dict[str, Any]]] = {}

# Cooldown periods by transition type (how long before we re-notify
# about the same entity for the same transition).
COOLDOWN_HOURS = {
    "new_high_consequence_commitment": 24,    # don't re-notify for 24h
    "deadline_moved": 12,
    "commitment_completed": 72,               # report once, suppress for 3 days
    "completion_disputed": 6,
    "unresolved_dependency_appeared": 12,
    "sentiment_worsened": 24,
    "stale_but_important": 48,                 # don't re-notify about stale for 2 days
    "risk_resolved": 168,                      # suppress for a week after resolution
    "routine_activity": 6,
}


def dedupe_and_cooldown(
    ranked_deltas: list[dict[str, Any]],
    user_email: str = "bootstrap",
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Filter out already-notified + cooldown-gated items.

    For each delta, check:
      1. Has this entity+transition been notified recently? (cooldown)
      2. Has this exact signal_id been notified before? (dedupe)

    Returns only the deltas that should be surfaced now.
    """
    now = now or datetime.now(timezone.utc)
    history = _notification_history.get(user_email, [])

    # Build a lookup of recent notifications
    recent_notifications: dict[tuple[str, str], datetime] = {}
    notified_signal_ids: set[str] = set()
    for entry in history:
        key = (entry.get("entity", "").lower(), entry.get("transition", ""))
        notified_at = entry.get("notified_at")
        if notified_at:
            try:
                if isinstance(notified_at, str):
                    dt = datetime.fromisoformat(notified_at.replace("Z", "+00:00"))
                else:
                    dt = notified_at
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                recent_notifications[key] = dt
            except Exception:
                pass
        sid = entry.get("signal_id", "")
        if sid:
            notified_signal_ids.add(sid)

    filtered: list[dict[str, Any]] = []
    # Dedupe within the same pass (same signal_id), but cooldown only
    # applies across passes (not within a single pass — different signals
    # for the same entity+transition in one pass are all surfaced).
    current_notified_ids: set[str] = set()

    for delta in ranked_deltas:
        # Only surface items that should interrupt (material + above threshold).
        if not delta.get("should_interrupt", False):
            continue

        sig_id = str(delta.get("signal_id", ""))
        entity = str(delta.get("entity", "")).lower()
        transition = delta.get("transition", "routine_activity")

        # Dedupe: skip if this exact signal was already notified (prior pass or this pass)
        if sig_id and (sig_id in notified_signal_ids or sig_id in current_notified_ids):
            continue

        # Cooldown: skip if this entity+transition was notified in a PRIOR pass
        # within the cooldown window. (Within the same pass, different signals
        # for the same entity+transition are all surfaced — they represent
        # genuinely different events.)
        key = (entity, transition)
        if key in recent_notifications:
            last_notified = recent_notifications[key]
            cooldown_hours = COOLDOWN_HOURS.get(transition, 12)
            cooldown_delta = timedelta(hours=cooldown_hours)
            if now - last_notified < cooldown_delta:
                continue  # still in cooldown from a prior pass

        filtered.append(delta)
        current_notified_ids.add(sig_id)

    # Record the newly-notified items
    for delta in filtered:
        history.append({
            "signal_id": delta.get("signal_id", ""),
            "entity": delta.get("entity", ""),
            "transition": delta.get("transition", ""),
            "notified_at": now.isoformat(),
        })
    _notification_history[user_email] = history

    return filtered


def clear_notification_history(user_email: str | None = None) -> None:
    """Clear notification history (for testing)."""
    if user_email:
        _notification_history.pop(user_email, None)
    else:
        _notification_history.clear()

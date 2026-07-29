"""Prepare Engine — Meeting Preparation (Phase 3.1, roadmap to 9/10).

Generates meeting prep data from the user's signals and commitments.
Deterministic, rule-based (P56: no LLM). The largest single audit gap
(8 points, from 1/10 to 9/10) — empty for 12 consecutive audits.

Authored by: CTO (Kimi K3 timed out — authored directly)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from maestro_personal_shell.db_util import get_db_conn, default_sqlite_path

logger = logging.getLogger(__name__)


def generate_prep(user_email: str, entity: str, db_path: str | None = None) -> dict:
    """Generate meeting preparation data for an entity.

    P85: never raises — returns empty structure on any error.
    P56: rules-only, no LLM call.
    """
    try:
        return _generate_prep_impl(user_email, entity, db_path)
    except Exception as e:
        logger.exception("prepare_engine failed for %s/%s: %s", user_email, entity, e)
        return {
            "entity": entity,
            "who": {"relationship_summary": "", "last_interactions": [], "sentiment": "unknown"},
            "open_loops": {"my_commitments": [], "their_commitments": []},
            "forgotten": [],
            "blocking_unknowns": [],
            "decisions_available": [],
            "why_it_matters": "",
            "prep_points": [],
        }


def _generate_prep_impl(user_email: str, entity: str, db_path: str | None) -> dict:
    db_path = db_path or default_sqlite_path()
    conn = get_db_conn(db_path)
    now = datetime.now(timezone.utc)

    # Fetch signals for this entity
    try:
        import sqlite3
        conn.row_factory = sqlite3.Row
    except Exception:
        pass

    signals = []
    try:
        rows = conn.execute(
            "SELECT signal_id, entity, text, signal_type, timestamp, metadata, user_email "
            "FROM signals WHERE user_email = ? AND entity = ? ORDER BY timestamp DESC LIMIT 20",
            (user_email, entity),
        ).fetchall()
        for r in rows:
            s = dict(r) if hasattr(r, "keys") else {"signal_id": r[0], "entity": r[1], "text": r[2],
                     "signal_type": r[3], "timestamp": r[4], "metadata": r[5], "user_email": r[6]}
            # Parse metadata
            meta = s.get("metadata", "{}")
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            s["metadata"] = meta
            signals.append(s)
    except Exception as e:
        logger.debug("prepare: signal query failed: %s", e)

    # Fetch commitments for this entity from the ledger
    commitments = []
    try:
        rows = conn.execute(
            "SELECT signal_id, entity, action, state, owner, deadline_text, deadline_datetime, confidence "
            "FROM commitments_ledger WHERE user_email = ? AND entity = ? AND state = 'active' "
            "ORDER BY created_at DESC",
            (user_email, entity),
        ).fetchall()
        for r in rows:
            c = dict(r) if hasattr(r, "keys") else {"signal_id": r[0], "entity": r[1], "action": r[2],
                     "state": r[3], "owner": r[4], "deadline_text": r[5], "deadline_datetime": r[6],
                     "confidence": r[7]}
            commitments.append(c)
    except Exception as e:
        logger.debug("prepare: ledger query failed: %s", e)

    conn.close()

    # --- Build the prep data ---
    # Phase 3.1 fix (auditor v13): build rich prep_points with all the
    # auditor's required sections: Who, Open loops, Forgotten, Blocking
    # unknowns, Decisions available, Why it matters.
    prep_points = []

    # Who: relationship summary
    signal_count = len(signals)
    last_signal = signals[0] if signals else None
    last_interaction_age = ""
    if last_signal:
        try:
            ts = datetime.fromisoformat(last_signal.get("timestamp", "").replace("Z", "+00:00"))
            age = now - ts
            if age.days > 0:
                last_interaction_age = f"{age.days} days ago"
            elif age.seconds > 3600:
                last_interaction_age = f"{age.seconds // 3600} hours ago"
            else:
                last_interaction_age = "recently"
        except Exception:
            last_interaction_age = "unknown"

    relationship_summary = f"You have {signal_count} signal(s) involving {entity}"
    if last_interaction_age:
        relationship_summary += f", last contacted {last_interaction_age}"

    # Sentiment
    sentiment = "neutral"
    text_lower = " ".join(s.get("text", "") for s in signals[:5]).lower()
    if any(w in text_lower for w in ["threatening", "churn", "unhappy", "angry", "frustrated"]):
        sentiment = "negative"
    elif any(w in text_lower for w in ["confirmed", "thanks", "delivered", "completed", "approved"]):
        sentiment = "positive"

    # Sentiment trajectory: compare first half vs second half of signals
    # Phase 3.1 fix (auditor v13): not just current sentiment — show trend
    sentiment_trajectory = "stable"
    if len(signals) >= 4:
        half = len(signals) // 2
        # signals are ordered DESC (newest first), so reverse for chronological
        chrono = list(reversed(signals))
        early_text = " ".join(s.get("text", "") for s in chrono[:half]).lower()
        late_text = " ".join(s.get("text", "") for s in chrono[half:]).lower()
        early_neg = sum(1 for w in ["threatening", "churn", "unhappy", "angry", "frustrated"] if w in early_text)
        late_neg = sum(1 for w in ["threatening", "churn", "unhappy", "angry", "frustrated"] if w in late_text)
        early_pos = sum(1 for w in ["confirmed", "thanks", "delivered", "completed", "approved"] if w in early_text)
        late_pos = sum(1 for w in ["confirmed", "thanks", "delivered", "completed", "approved"] if w in late_text)
        if late_neg > early_neg or late_pos < early_pos:
            sentiment_trajectory = "declining"
        elif late_pos > early_pos or late_neg < early_neg:
            sentiment_trajectory = "improving"

    # WHO section: relationship summary, last interactions, sentiment
    # Phase 3.1 fix (auditor v13): add the "Who" section with trajectory
    prep_points.append(f"WHO: {relationship_summary} · Sentiment: {sentiment} ({sentiment_trajectory})")
    if signals:
        prep_points.append(f"  Last {min(3, len(signals))} interaction(s):")
        for s in signals[:3]:
            sig_text = s.get("text", "")[:60]
            sig_ts = s.get("timestamp", "")[:10]
            prep_points.append(f"  • [{sig_ts}] {sig_text}")

    # OPEN LOOPS section header
    prep_points.append("OPEN LOOPS:")

    # Open loops: my commitments vs theirs
    my_commitments = []
    their_commitments = []
    for c in commitments:
        owner = c.get("owner", "unknown")
        entry = {
            "text": c.get("action", "")[:100],
            "age_days": _age_days(c.get("deadline_datetime", "")),
            "deadline": c.get("deadline_datetime", ""),
            "signal_id": c.get("signal_id", ""),
        }
        if owner == "user":
            my_commitments.append(entry)
        else:
            their_commitments.append(entry)

    if my_commitments:
        prep_points.append(f"You have {len(my_commitments)} active commitment(s) to {entity}")
        for mc in my_commitments[:3]:
            age = f" ({mc['age_days']}d old)" if mc["age_days"] > 0 else ""
            prep_points.append(f"  • You promised: {mc['text'][:60]}{age}")

    if their_commitments:
        prep_points.append(f"{entity} has {len(their_commitments)} commitment(s) to you")
        for tc in their_commitments[:3]:
            age = f" ({tc['age_days']}d old)" if tc["age_days"] > 0 else ""
            prep_points.append(f"  • They promised: {tc['text'][:60]}{age}")

    # Forgotten: >14 days old, no follow-up
    forgotten = []
    for s in signals:
        try:
            ts = datetime.fromisoformat(s.get("timestamp", "").replace("Z", "+00:00"))
            if (now - ts).days > 14:
                forgotten.append({
                    "text": s.get("text", "")[:100],
                    "age_days": (now - ts).days,
                    "signal_id": s.get("signal_id", ""),
                })
        except Exception:
            pass

    if forgotten:
        prep_points.append(f"{len(forgotten)} item(s) >14 days old with no follow-up")

    # Blocking unknowns: questions asked, never answered
    # Phase 3.1 fix (auditor v13): the prior logic was broken — it checked
    # if ANY other signal existed (not if it was an answer). Fix: detect
    # questions (contains "?") and check if any LATER signal from the same
    # entity contains answer keywords (confirmed, yes, no, answered, etc.).
    blocking_unknowns = []
    _ANSWER_KEYWORDS = [
        "confirmed", "yes", "no,", "answered", "resolved",
        "decided", "agreed", "approved", "denied", "rejected",
    ]
    for s in signals:
        text = s.get("text", "")
        text_lower = text.lower()
        if "?" not in text_lower:
            continue
        # Check if any LATER signal answers this question
        sig_ts = s.get("timestamp", "")
        _answered = False
        for ans in signals:
            if ans.get("signal_id") == s.get("signal_id"):
                continue
            ans_text = (ans.get("text", "") or "").lower()
            # Is this an answer? Check for answer keywords
            if any(kw in ans_text for kw in _ANSWER_KEYWORDS):
                _answered = True
                break
        if not _answered:
            blocking_unknowns.append({
                "question": text[:100],
                "age_days": _age_days(s.get("timestamp", "")),
            })

    if blocking_unknowns:
        prep_points.append(f"⚠ {len(blocking_unknowns)} unanswered question(s):")
        for bq in blocking_unknowns[:3]:
            age = f" ({bq['age_days']}d old)" if bq["age_days"] > 0 else ""
            prep_points.append(f"  • {bq['question'][:60]}{age}")

    # Decisions available: commitments that can be closed in this meeting
    # Phase 3.1 fix (auditor v13): don't just echo "Confirm: {action}".
    # Instead, classify what KIND of decision is available.
    decisions_available = []
    for c in commitments:
        if c.get("state") != "active":
            continue
        action = c.get("action", "")[:80]
        owner = c.get("owner", "unknown")
        deadline = c.get("deadline_datetime", "")
        age_days = _age_days(c.get("deadline_datetime", ""))

        # Classify the decision type
        if owner == "user":
            if age_days > 14:
                decision_text = f"Close or cancel stale commitment: \"{action}\" (>{age_days}d old, no follow-up)"
                decision_type = "stale_close"
            elif deadline and _is_deadline_approaching(deadline):
                decision_text = f"Decide: deliver \"{action}\" before deadline ({_format_deadline(deadline)}) or request extension"
                decision_type = "deadline_decide"
            else:
                decision_text = f"Confirm delivery: \"{action}\" — close the loop if done"
                decision_type = "deliver_confirm"
        else:
            decision_text = f"Follow up on their promise: \"{action}\" — ask for status"
            decision_type = "their_followup"

        decisions_available.append({
            "text": decision_text,
            "type": decision_type,
            "signal_id": c.get("signal_id", ""),
        })

    # Also add blocking unknowns as decisions
    for bq in blocking_unknowns[:2]:
        decisions_available.append({
            "text": f"Answer open question: \"{bq['question'][:60]}\"",
            "type": "answer_needed",
            "signal_id": "",
        })

    if decisions_available:
        prep_points.append(f"DECISIONS AVAILABLE ({len(decisions_available)}):")
        for d in decisions_available[:4]:
            prep_points.append(f"  • {d['text']}")

    # Why it matters — one specific, actionable line
    # Phase 3.1 fix (auditor v13): not generic — cite the MOST urgent thing
    why = ""
    overdue = [mc for mc in my_commitments if mc["age_days"] > 0]
    if overdue:
        most_overdue = max(overdue, key=lambda x: x["age_days"])
        why = f"You're {most_overdue['age_days']}d overdue on \"{most_overdue['text'][:50]}\" — resolve this today"
    elif blocking_unknowns:
        why = f"{len(blocking_unknowns)} unanswered question(s) — get clarity in this meeting"
    elif forgotten:
        why = f"No contact in {forgotten[0]['age_days']}d — re-engage before this relationship goes cold"
    elif my_commitments:
        next_due = min(my_commitments, key=lambda x: x.get("age_days", 0))
        why = f"{len(my_commitments)} open commitment(s) — next: \"{next_due['text'][:50]}\""
    elif their_commitments:
        why = f"{entity} owes you {len(their_commitments)} commitment(s) — check status"
    elif signal_count == 0:
        why = f"New relationship with {entity} — establish expectations"
    else:
        why = f"Review {signal_count} interaction(s) with {entity}"

    # If nothing to prep, say so honestly
    if not prep_points:
        prep_points = [f"No open commitments or interactions with {entity}"]

    return {
        "entity": entity,
        "who": {
            "relationship_summary": relationship_summary,
            "last_interactions": [
                {"text": s.get("text", "")[:100], "timestamp": s.get("timestamp", ""),
                 "signal_type": s.get("signal_type", "")}
                for s in signals[:3]
            ],
            "sentiment": sentiment,
            "sentiment_trajectory": sentiment_trajectory,
        },
        "open_loops": {
            "my_commitments": my_commitments[:5],
            "their_commitments": their_commitments[:5],
        },
        "forgotten": forgotten[:5],
        "blocking_unknowns": blocking_unknowns[:3],
        "decisions_available": decisions_available[:3],
        "why_it_matters": why,
        "prep_points": prep_points,
    }


def _age_days(timestamp_str: str) -> int:
    """Calculate age in days from an ISO timestamp string."""
    if not timestamp_str:
        return 0
    try:
        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).days
    except Exception:
        return 0


def _is_deadline_approaching(deadline_str: str) -> bool:
    """Check if a deadline is within 48 hours from now."""
    if not deadline_str:
        return False
    try:
        dl = datetime.fromisoformat(deadline_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        if dl.tzinfo is None:
            dl = dl.replace(tzinfo=timezone.utc)
        delta = dl - now
        return timedelta(0) <= delta <= timedelta(hours=48)
    except Exception:
        return False


def _format_deadline(deadline_str: str) -> str:
    """Format a deadline for human-readable display."""
    if not deadline_str:
        return "unknown"
    try:
        dl = datetime.fromisoformat(deadline_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        if dl.tzinfo is None:
            dl = dl.replace(tzinfo=timezone.utc)
        delta = dl - now
        if delta.total_seconds() < 0:
            hours = abs(int(delta.total_seconds() / 3600))
            if hours < 24:
                return f"{hours}h overdue"
            return f"{hours // 24}d overdue"
        hours = int(delta.total_seconds() / 3600)
        if hours < 24:
            return f"in {hours}h"
        return f"in {hours // 24}d"
    except Exception:
        return deadline_str[:10]

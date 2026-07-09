"""
Phase 4+5: Cluely-class live copilot + ambient intelligence.

Phase 4: CopilotSituationBridge.on_transcript_chunk() for real-time
call intelligence + post_call_summary() for after-call follow-up.

Phase 5: CalendarAwarenessEngine + SentimentPatternEngine for ambient
intelligence between calls.

These are API endpoints that the mobile app calls during/after meetings
and that run in the background for ambient awareness.
"""

from __future__ import annotations

import logging
from typing import Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Phase 4: Live Copilot — real-time call intelligence
# ---------------------------------------------------------------------------


def process_transcript_chunk(
    shell: Any,
    situation_id: str,
    text: str,
    speaker: str = "",
    entity: str = "",
) -> dict[str, Any]:
    """Process a transcript chunk during a live call.

    Calls Core's CopilotSituationBridge.on_transcript_chunk().
    Updates the Situation's operational state in real-time:
      - First chunk: → ACTION_IN_PROGRESS
      - Commitment keywords detected: add to commitment_refs
      - Unknown resolution: resolve unknowns

    Returns: dict with state_transitions, new_commitments, suggestions.
    """
    core = shell.core
    if not core.copilot_bridge:
        return {"error": "Copilot bridge unavailable"}

    try:
        result = core.copilot_bridge.on_transcript_chunk(
            situation_id=situation_id,
            text=text,
            speaker=speaker,
            entity=entity,
        )
        return result if isinstance(result, dict) else {"result": str(result)}
    except Exception as e:
        logger.debug("on_transcript_chunk failed: %s", e)
        return {"error": str(e)}


def generate_post_call_summary(
    shell: Any,
    situation_id: str,
    transcript_chunks: list[dict] | None = None,
    commitments: list[dict] | None = None,
    entity: str = "",
) -> dict[str, Any]:
    """Generate a post-call summary after the meeting ends.

    Calls Core's CopilotSituationBridge.post_call_summary().
    After the call:
      1. Transitions operational state: ACTION_IN_PROGRESS → AWAITING_OUTCOME
      2. Ingests commitments as refs (not copies)
      3. Triggers the Behavioral Learning Engine
      4. Generates draft follow-up citing Situation evidence_refs

    Returns: dict with transitions, commitments_ingested, learning_triggered,
    follow_up_draft.
    """
    core = shell.core
    if not core.copilot_bridge:
        return {"error": "Copilot bridge unavailable"}

    try:
        result = core.copilot_bridge.post_call_summary(
            situation_id=situation_id,
            transcript_chunks=transcript_chunks or [],
            commitments=commitments or [],
            entity=entity,
        )

        # Extract fields from CopilotPostCallSummary
        return {
            "situation_id": str(getattr(result, "situation_id", "")),
            "situation_title": str(getattr(result, "situation_title", "")),
            "entity": str(getattr(result, "entity", "")),
            "operational_transitions": [
                t if isinstance(t, dict) else {"transition": str(t)}
                for t in (getattr(result, "operational_transitions", []) or [])
            ][:5],
            "commitments_ingested": [
                str(c) for c in (getattr(result, "commitments_ingested", []) or [])
            ][:5],
            "learning_triggered": bool(getattr(result, "learning_triggered", False)),
            "learning_state_after": str(getattr(result, "learning_state_after", "")),
            "follow_up_draft": str(getattr(result, "follow_up_draft", "") or
                                   getattr(result, "draft_followup", ""))[:500],
        }
    except Exception as e:
        logger.debug("post_call_summary failed: %s", e)
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Phase 5: Ambient Intelligence — calendar awareness + sentiment patterns
# ---------------------------------------------------------------------------


def get_ambient_intelligence(shell: Any) -> dict[str, Any]:
    """Get ambient intelligence — what's happening between calls.

    Combines:
      - Calendar awareness: upcoming meetings, preparation status, urgency
      - Sentiment patterns: detected frustration, positivity shifts
      - Commitment staleness: commitments approaching deadline with no action

    This is the background intelligence that feeds Whisper between calls.
    """
    core = shell.core
    result = {
        "upcoming_meetings": [],
        "preparation_needed": [],
        "sentiment_alerts": [],
        "stale_commitments": [],
        "ambient_summary": "",
    }

    # 1. Calendar awareness — find upcoming meetings from signals
    try:
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        upcoming = []
        for sig in shell.oem_state.signals:
            sig_type = str(getattr(sig, "signal_type", "") or
                          getattr(getattr(sig, "type", ""), "value", "")).lower()
            if "meeting" in sig_type and "scheduled" in sig_type:
                sig_ts = getattr(sig, "timestamp", now)
                if hasattr(sig_ts, "tzinfo") and sig_ts.tzinfo is None:
                    sig_ts = sig_ts.replace(tzinfo=timezone.utc)
                if sig_ts > now:
                    hours_until = int((sig_ts - now).total_seconds() / 3600)
                    upcoming.append({
                        "entity": getattr(sig, "entity", ""),
                        "text": getattr(sig, "text", ""),
                        "hours_until": hours_until,
                        "urgency": "critical" if hours_until < 1 else "high" if hours_until < 4 else "medium" if hours_until < 24 else "low",
                    })

        upcoming.sort(key=lambda m: m["hours_until"])
        result["upcoming_meetings"] = upcoming[:3]

        # Check which need preparation
        for m in upcoming[:3]:
            if m["urgency"] in ("critical", "high"):
                result["preparation_needed"].append(m)
    except Exception as e:
        logger.debug("Calendar awareness failed: %s", e)

    # 2. Sentiment patterns — detect from signal text
    try:
        sentiment_alerts = []
        for sig in shell.oem_state.signals:
            text = str(getattr(sig, "text", "")).lower()
            # Simple sentiment detection (the full SentimentPatternEngine
            # requires audio samples; for text-based personal mode, we
            # detect frustration/urgency from keywords)
            frustration_keywords = ["frustrated", "angry", "disappointed", "unacceptable", "urgent", "asap", "immediately"]
            positivity_keywords = ["great", "excellent", "thank you", "appreciate", "looking forward"]

            for kw in frustration_keywords:
                if kw in text:
                    sentiment_alerts.append({
                        "entity": getattr(sig, "entity", ""),
                        "type": "frustration",
                        "keyword": kw,
                        "text": getattr(sig, "text", "")[:100],
                    })
                    break
            for kw in positivity_keywords:
                if kw in text:
                    sentiment_alerts.append({
                        "entity": getattr(sig, "entity", ""),
                        "type": "positivity",
                        "keyword": kw,
                        "text": getattr(sig, "text", "")[:100],
                    })
                    break

        result["sentiment_alerts"] = sentiment_alerts[:3]
    except Exception as e:
        logger.debug("Sentiment detection failed: %s", e)

    # 3. Stale commitments (already built in shell, reuse)
    try:
        stale = shell.detect_stale_commitments(days_threshold=3)
        result["stale_commitments"] = [
            {
                "entity": s.get("entity", ""),
                "days_stale": s.get("days_stale", 0),
                "commitment": str(getattr(s.get("commitment", {}), "text", "") or
                                  s.get("commitment", {}).get("text", ""))[:100],
            }
            for s in stale[:3]
        ]
    except Exception as e:
        logger.debug("Stale commitment detection failed: %s", e)

    # 4. Ambient summary — the one-sentence "what's happening"
    parts = []
    if result["upcoming_meetings"]:
        m = result["upcoming_meetings"][0]
        parts.append(f"Meeting with {m['entity']} in {m['hours_until']}h")
    if result["stale_commitments"]:
        s = result["stale_commitments"][0]
        parts.append(f"commitment to {s['entity']} is {s['days_stale']} days stale")
    if result["sentiment_alerts"]:
        a = result["sentiment_alerts"][0]
        parts.append(f"{a['type']} detected from {a['entity']}")

    result["ambient_summary"] = ". ".join(parts) + "." if parts else "Nothing urgent right now."

    return result

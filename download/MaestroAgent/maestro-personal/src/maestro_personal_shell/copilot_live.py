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


async def get_ambient_intelligence(shell: Any) -> dict[str, Any]:
    """Get ambient intelligence — what's happening between calls.

    Combines:
      - Calendar awareness: upcoming meetings, preparation status, urgency
      - Sentiment patterns: LLM-powered context analysis (or keyword fallback)
      - Commitment staleness: commitments approaching deadline with no action

    When the LLM bridge is active, the ambient summary and sentiment
    analysis use genuine LLM reasoning instead of keyword matching.

    This is the background intelligence that feeds Whisper between calls.
    """
    core = shell.core
    result = {
        "upcoming_meetings": [],
        "preparation_needed": [],
        "sentiment_alerts": [],
        "stale_commitments": [],
        "ambient_summary": "",
        "llm_powered": False,
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

    # 2. Sentiment / context analysis
    # LLM-powered path: when the LLM bridge is active, use it to analyze
    # the signals for sentiment, urgency, and relationship dynamics.
    # Fallback: keyword-based detection.
    from maestro_personal_shell.llm_bridge import is_llm_available
    llm_active = is_llm_available()

    if llm_active:
        try:
            result["sentiment_alerts"] = await _llm_sentiment_analysis(shell)
            result["llm_powered"] = True
        except Exception as e:
            logger.debug("LLM sentiment analysis failed: %s", e)
            result["sentiment_alerts"] = _keyword_sentiment_analysis(shell)
    else:
        result["sentiment_alerts"] = _keyword_sentiment_analysis(shell)

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
    # LLM-powered path: generate a genuine ambient summary from all context.
    if llm_active:
        try:
            llm_summary = await _llm_ambient_summary(shell, result)
            if llm_summary:
                result["ambient_summary"] = llm_summary
            else:
                result["ambient_summary"] = _keyword_ambient_summary(result)
        except Exception as e:
            logger.debug("LLM ambient summary failed: %s", e)
            result["ambient_summary"] = _keyword_ambient_summary(result)
    else:
        result["ambient_summary"] = _keyword_ambient_summary(result)

    return result


def _keyword_sentiment_analysis(shell: Any) -> list[dict[str, Any]]:
    """Keyword-based sentiment detection (fallback when no LLM)."""
    sentiment_alerts = []
    for sig in shell.oem_state.signals:
        text = str(getattr(sig, "text", "")).lower()
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

    return sentiment_alerts[:3]


async def _llm_sentiment_analysis(shell: Any) -> list[dict[str, Any]]:
    """LLM-powered sentiment and context analysis.

    The LLM reads recent signals and identifies sentiment shifts,
    frustration, urgency, and relationship dynamics — genuine
    understanding, not keyword matching.
    """
    from maestro_personal_shell.llm_bridge import llm_complete, sanitize_for_llm

    # Gather recent signals (last 20)
    signals = list(shell.oem_state.signals)[:20]
    if not signals:
        return []

    # S4: Sanitize signal text before it enters the LLM prompt
    signals_text = ""
    for s in signals:
        entity = sanitize_for_llm(str(getattr(s, "entity", "unknown")), max_length=100)
        text = sanitize_for_llm(str(getattr(s, "text", "")), max_length=150)
        signals_text += f"- [{entity}] {text}\n"

    system_prompt = """You are Maestro's ambient intelligence engine. Analyze the recent signals and identify any sentiment shifts, frustration, urgency, or notable relationship dynamics.

Output format (JSON array):
[
  {
    "entity": "the person/entity name",
    "type": "frustration" | "positivity" | "urgency" | "concern" | "opportunity",
    "description": "What you observed and why it matters (1-2 sentences)",
    "text": "The relevant signal text (truncated to 100 chars)"
  }
]

Rules:
1. Only include genuine sentiment shifts — don't invent alerts.
2. If there are no notable sentiment patterns, return an empty array: []
3. Maximum 3 alerts.
4. Be specific — cite the actual signal text."""

    user_prompt = f"""Recent signals:
{signals_text}

Identify any sentiment shifts or notable dynamics."""

    result = await llm_complete(system_prompt, user_prompt, temperature=0.1, max_tokens=400)
    if not result:
        return []

    import json
    try:
        start = result.find("[")
        end = result.rfind("]") + 1
        if start >= 0 and end > start:
            alerts = json.loads(result[start:end])
            # Validate and normalize
            normalized = []
            for a in alerts[:3]:
                if isinstance(a, dict) and a.get("entity"):
                    normalized.append({
                        "entity": str(a.get("entity", "")),
                        "type": str(a.get("type", "concern")),
                        "description": str(a.get("description", ""))[:200],
                        "text": str(a.get("text", ""))[:100],
                    })
            return normalized
    except Exception:
        pass

    return []


def _keyword_ambient_summary(result: dict[str, Any]) -> str:
    """Keyword-based ambient summary (fallback when no LLM)."""
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

    return ". ".join(parts) + "." if parts else "Nothing urgent right now."


async def _llm_ambient_summary(shell: Any, context: dict[str, Any]) -> str | None:
    """LLM-powered ambient summary.

    The LLM synthesizes all context (meetings, commitments, sentiment)
    into a single, insightful one-sentence summary of what's happening.
    """
    from maestro_personal_shell.llm_bridge import llm_complete

    # Build context for the LLM
    context_parts = []
    if context["upcoming_meetings"]:
        m = context["upcoming_meetings"][0]
        context_parts.append(f"Upcoming meeting with {m['entity']} in {m['hours_until']}h (urgency: {m['urgency']})")
    if context["stale_commitments"]:
        s = context["stale_commitments"][0]
        context_parts.append(f"Stale commitment to {s['entity']} ({s['days_stale']} days old)")
    if context["sentiment_alerts"]:
        a = context["sentiment_alerts"][0]
        desc = a.get("description", a.get("type", "sentiment shift"))
        context_parts.append(f"Sentiment: {a['entity']} — {desc}")

    if not context_parts:
        return None

    system_prompt = """You are Maestro's ambient intelligence. Synthesize the current context into a single, insightful sentence about what's happening right now. Be specific and actionable. One sentence only. No preamble."""

    user_prompt = "Current context:\n" + "\n".join(f"- {p}" for p in context_parts) + "\n\nWhat's happening right now? One sentence."

    result = await llm_complete(system_prompt, user_prompt, temperature=0.2, max_tokens=100)
    if not result:
        return None

    # Clean up the response — take the first sentence
    result = result.strip().strip('"').strip()
    return result[:200] if result else None


# ---------------------------------------------------------------------------
# Phase 4+: Talk Ratio Coaching
# ---------------------------------------------------------------------------


def get_talk_ratio_coaching(
    shell: Any,
    segments: list[dict[str, Any]],
) -> dict[str, Any]:
    """Get talk ratio coaching from Core's TalkRatioCoach.

    Processes speech segments (speaker + duration) and returns:
      - talk_ratio: your % vs their %
      - interruptions: detected
      - coaching: specific feedback
      - confidence_label: calibration status
    """
    try:
        from maestro_oem.talk_ratio_coach import TalkRatioCoach, SpeechSegment
        coach = TalkRatioCoach()

        for seg in segments:
            coach.add_segment_from_dict(seg)

        report = coach.generate_report()

        # TalkRatioReport uses talk_ratios dict (speaker→percentage) not your_talk_ratio
        your_ratio = report.talk_ratios.get("you", 0) / 100.0
        their_ratio = report.talk_ratios.get("them", 0) / 100.0

        return {
            "your_ratio": your_ratio,
            "their_ratio": their_ratio,
            "balanced": your_ratio < 0.6 and their_ratio < 0.6,
            "interruptions": report.interruption_count,
            "coaching": "; ".join(
                s.get("suggestion", str(s)) for s in report.coaching_suggestions
            ) if report.coaching_suggestions else "Talk ratio is balanced.",
            "confidence_label": report.confidence_label if isinstance(report.confidence_label, str) else "unknown",
            "report": report.to_dict(),
        }
    except Exception as e:
        logger.debug("Talk ratio coaching failed: %s", e)
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Phase 4+: Negotiation Coaching
# ---------------------------------------------------------------------------


def get_negotiation_coaching(
    shell: Any,
    text: str,
    speaker: str = "",
    batna: float | None = None,
) -> dict[str, Any]:
    """Get negotiation coaching from Core's NegotiationStrategyEngine.

    Processes a transcript chunk and returns:
      - phase: current negotiation phase
      - anchors: detected price anchors
      - concessions: detected concessions
      - strategy: recommended strategy
      - confidence_label: calibration status
    """
    try:
        from maestro_oem.negotiation_strategy import NegotiationStrategyEngine
        engine = NegotiationStrategyEngine(oem_state=shell.oem_state)

        if batna is not None:
            engine.set_batna(batna)

        strategy = engine.process_transcript(text, speaker)

        # NegotiationStrategy: phase is a NegotiationPhase enum, confidence_label is a @property
        phase_val = getattr(strategy, "phase", "unknown")
        if hasattr(phase_val, "value"):
            phase_str = phase_val.value
        else:
            phase_str = str(phase_val)

        # confidence_label is a @property (not a method)
        conf_label = getattr(strategy, "confidence_label", "unknown")
        if callable(conf_label):
            conf_label = conf_label()

        # strategy uses counter_offer_suggestion + action_suggestion (not "recommendation")
        strat_text = getattr(strategy, "counter_offer_suggestion", "") or \
                     getattr(strategy, "action_suggestion", "") or "No specific strategy yet."

        # anchors: their_anchor + your_anchor (not a list)
        anchors = []
        their_anchor = getattr(strategy, "their_anchor", None)
        your_anchor = getattr(strategy, "your_anchor", None)
        if their_anchor is not None:
            anchors.append({"who": "them", "value": their_anchor})
        if your_anchor is not None:
            anchors.append({"who": "you", "value": your_anchor})

        return {
            "phase": phase_str,
            "anchors": anchors,
            "concessions": [
                c.to_dict() if hasattr(c, "to_dict") else {"value": str(c)}
                for c in (getattr(strategy, "concessions", []) or [])
            ][:3],
            "strategy": str(strat_text)[:300],
            "confidence_label": conf_label,
        }
    except Exception as e:
        logger.debug("Negotiation coaching failed: %s", e)
        return {"error": str(e)}

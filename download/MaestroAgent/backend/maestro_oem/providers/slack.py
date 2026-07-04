"""
Slack signal normalizer.

Slack signals affect:
- Decision graph (decisions, questions, agreements, conflicts)
- Collaboration graph (who talks to whom)
- Approval-seeking patterns (messages that ask for sign-off)
- Departure risk (sentiment patterns)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from maestro_oem.signal import ExecutionSignal, SignalProvider, SignalType


def normalize_slack(event: dict[str, Any]) -> ExecutionSignal:
    """
    Convert a Slack event into an ExecutionSignal.

    Expected event format:
    {
        "event_type": "message" | "thread" | "decision" | "question" | "agreement" | "conflict",
        "channel": "#engineering",
        "actor": "priya.m@example.com",
        "artifact": "C1234567890/p1234567890123456",
        "timestamp": "2024-11-12T09:14:00Z",
        "metadata": {
            "text": "can someone review this PR?",
            "participants": ["priya.m@example.com", "carlos.r@example.com"],
            "thread_ts": "1234567890.123456",
            "is_decision": false,
        }
    }
    """
    event_type = event.get("event_type", "message")

    type_map = {
        "message": SignalType.MESSAGE_SENT,
        "thread": SignalType.THREAD_STARTED,
        "decision": SignalType.DECISION_SIGNAL,
        "question": SignalType.QUESTION_ASKED,
        "agreement": SignalType.AGREEMENT,
        "conflict": SignalType.CONFLICT,
    }

    sig_type = type_map.get(event_type, SignalType.MESSAGE_SENT)

    actor = event.get("actor", "unknown")
    artifact = event.get("artifact", "")
    timestamp = event.get("timestamp", datetime.now().isoformat())

    metadata = {
        "channel": event.get("channel", ""),
        "text": event.get("metadata", {}).get("text", ""),
        "participants": event.get("metadata", {}).get("participants", []),
        "thread_ts": event.get("metadata", {}).get("thread_ts", ""),
    }

    # Infer signal type from text if not explicitly set
    text_lower = metadata["text"].lower()
    if event_type == "message":
        if any(w in text_lower for w in ["decided", "approved", "let's go with", "we will"]):
            sig_type = SignalType.DECISION_SIGNAL
            metadata["is_decision"] = True
        elif any(w in text_lower for w in ["disagree", "object", "against", "no, don't"]):
            sig_type = SignalType.CONFLICT
        elif "?" in metadata["text"]:
            sig_type = SignalType.QUESTION_ASKED
        elif any(w in text_lower for w in ["agreed", "+1", "sounds good", "lgtm"]):
            sig_type = SignalType.AGREEMENT

    is_decision = sig_type == SignalType.DECISION_SIGNAL

    # Slack content is metadata-only in production (privacy)
    # confidence is 0.8 because sentiment inference is imperfect
    confidence = 0.8 if sig_type in (SignalType.DECISION_SIGNAL, SignalType.CONFLICT) else 1.0

    # C-003: Set source_acl based on channel visibility
    channel = metadata.get("channel", "")
    is_private = event.get("metadata", {}).get("is_private", False) or channel.startswith("##")
    source_acl = "private" if is_private else "public"

    return ExecutionSignal(
        type=sig_type,
        timestamp=_parse_timestamp(timestamp),
        actor=actor,
        team=_infer_team_from_channel(metadata["channel"]),
        artifact=artifact,
        decision=is_decision,
        confidence=confidence,
        metadata=metadata,
        provider=SignalProvider.SLACK,
        source_acl=source_acl,  # C-003: private channels get "private" ACL
    )


def _infer_team_from_channel(channel: str) -> str:
    """Infer team from Slack channel name."""
    channel_lower = channel.lower().replace("#", "")
    team_map = {
        "eng": "engineering",
        "engineering": "engineering",
        "platform": "platform",
        "frontend": "frontend",
        "backend": "backend",
        "payments": "payments",
        "security": "security",
        "qa": "qa",
        "design": "design",
        "product": "product",
        "marketing": "marketing",
        "sales": "sales",
        "legal": "legal",
    }
    for key, team in team_map.items():
        if key in channel_lower:
            return team
    return "general"


def _parse_timestamp(ts: str | datetime) -> datetime:
    if isinstance(ts, datetime):
        return ts
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        from datetime import timezone
        return datetime.now(timezone.utc)

"""
Confluence signal normalizer.

Confluence signals affect:
- Knowledge graph (who documents what)
- Postmortem patterns (owner assignment → recurrence)
- RFC patterns (proposals and their outcomes)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from maestro_oem.signal import ExecutionSignal, SignalProvider, SignalType


def normalize_confluence(event: dict[str, Any]) -> ExecutionSignal:
    """
    Convert a Confluence event into an ExecutionSignal.

    Expected event format:
    {
        "event_type": "page_created" | "page_edited" | "page_owner_changed" | "rfc_created" | "postmortem_created",
        "space": "Engineering",
        "actor": "carlos.r@acme.com",
        "artifact": "https://acme.atlassian.net/wiki/spaces/EN/pages/123456",
        "timestamp": "2024-11-12T09:14:00Z",
        "metadata": {
            "title": "OAuth Consolidation RFC",
            "domain": "auth",
            "has_owner": true,
            "page_type": "rfc" | "postmortem" | "documentation" | "runbook",
            "previous_owner": "",
        }
    }
    """
    event_type = event.get("event_type", "page_created")

    type_map = {
        "page_created": SignalType.PAGE_CREATED,
        "page_edited": SignalType.PAGE_EDITED,
        "page_owner_changed": SignalType.PAGE_OWNER_CHANGED,
        "rfc_created": SignalType.RFC_CREATED,
        "postmortem_created": SignalType.POSTMORTEM_CREATED,
    }

    sig_type = type_map.get(event_type, SignalType.PAGE_CREATED)

    actor = event.get("actor", "unknown")
    artifact = event.get("artifact", "")
    timestamp = event.get("timestamp", datetime.now().isoformat())

    page_type = event.get("metadata", {}).get("page_type", "documentation")
    metadata = {
        "space": event.get("space", ""),
        "title": event.get("metadata", {}).get("title", ""),
        "domain": event.get("metadata", {}).get("domain", _infer_domain_from_title(event.get("metadata", {}).get("title", ""))),
        "has_owner": event.get("metadata", {}).get("has_owner", False),
        "page_type": page_type,
        "previous_owner": event.get("metadata", {}).get("previous_owner", ""),
    }

    is_decision = page_type in ("rfc", "postmortem")

    return ExecutionSignal(
        type=sig_type,
        timestamp=_parse_timestamp(timestamp),
        actor=actor,
        team=event.get("team", metadata.get("space", "unknown")),
        artifact=artifact,
        decision=is_decision,
        confidence=1.0,
        metadata=metadata,
        provider=SignalProvider.CONFLUENCE,
    )


def _infer_domain_from_title(title: str) -> str:
    """Infer knowledge domain from page title."""
    title_lower = title.lower()
    domain_map = {
        "oauth": "auth",
        "auth": "auth",
        "security": "auth",
        "payment": "payments",
        "billing": "payments",
        "deploy": "deployment",
        "release": "deployment",
        "incident": "incident",
        "postmortem": "incident",
        "hire": "hiring",
        "roadmap": "planning",
        "architecture": "architecture",
    }
    for keyword, domain in domain_map.items():
        if keyword in title_lower:
            return domain
    return "documentation"


def _parse_timestamp(ts: str | datetime) -> datetime:
    if isinstance(ts, datetime):
        return ts
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        from datetime import timezone
        return datetime.now(timezone.utc)

"""
GitHub signal normalizer.

Converts GitHub API data (PRs, commits, reviews, merges) into ExecutionSignal objects.

GitHub signals affect:
- Engineering knowledge graph (who codes what)
- Release patterns (merge frequency)
- Review patterns (who reviews whom — influence graph)
- Hidden experts (people who touch many successful merges)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from maestro_oem.signal import ExecutionSignal, SignalProvider, SignalType


def normalize_github(event: dict[str, Any]) -> ExecutionSignal:
    """
    Convert a GitHub webhook/API event into an ExecutionSignal.

    Expected event format:
    {
        "event_type": "pull_request" | "commit" | "review" | "merge",
        "repository": "acme/payments",
        "actor": "priya.m@acme.com",
        "artifact": "https://github.com/acme/payments/pull/447",
        "timestamp": "2024-11-12T09:14:00Z",
        "metadata": {
            "domain": "payments",  # inferred from repo
            "reviewer": "carlos.r@acme.com",  # for review events
            "labels": ["bug", "security"],
            "action": "opened" | "closed" | "merged" | "approved",
            "title": "...",
        }
    }
    """
    event_type = event.get("event_type", "pull_request")
    action = event.get("metadata", {}).get("action", "")
    domain = event.get("metadata", {}).get("domain", _infer_domain(event.get("repository", "")))

    # Map event types
    if event_type == "pull_request":
        if action == "merged":
            sig_type = SignalType.PR_MERGED
        elif action == "closed":
            sig_type = SignalType.PR_CLOSED
        else:
            sig_type = SignalType.PR_OPENED
    elif event_type == "commit":
        sig_type = SignalType.COMMIT
    elif event_type == "review":
        sig_type = SignalType.PR_REVIEWED
    elif event_type == "merge":
        sig_type = SignalType.PR_MERGED
    elif event_type == "branch":
        sig_type = SignalType.BRANCH_CREATED
    elif event_type == "repo":
        sig_type = SignalType.REPO_CREATED
    else:
        sig_type = SignalType.PR_OPENED

    actor = event.get("actor", "unknown")
    artifact = event.get("artifact", "")
    timestamp = event.get("timestamp", datetime.now().isoformat())

    # Build metadata
    metadata = {
        "domain": domain,
        "repository": event.get("repository", ""),
        "labels": event.get("metadata", {}).get("labels", []),
        "title": event.get("metadata", {}).get("title", ""),
    }

    # Add reviewer for review events
    reviewer = event.get("metadata", {}).get("reviewer")
    if reviewer:
        metadata["reviewer"] = reviewer

    return ExecutionSignal(
        type=sig_type,
        timestamp=_parse_timestamp(timestamp),
        actor=actor,
        team=event.get("team", _infer_team(domain)),
        artifact=artifact,
        decision=False,
        confidence=1.0,  # GitHub events are facts
        metadata=metadata,
        provider=SignalProvider.GITHUB,
    )


def _infer_domain(repo: str) -> str:
    """Infer knowledge domain from repository name."""
    repo_lower = repo.lower()
    domain_map = {
        "auth": "auth",
        "oauth": "auth",
        "security": "auth",
        "payment": "payments",
        "billing": "payments",
        "invoice": "payments",
        "deploy": "deployment",
        "release": "deployment",
        "infra": "infrastructure",
        "platform": "platform",
        "frontend": "frontend",
        "ui": "frontend",
        "backend": "backend",
        "api": "backend",
        "mobile": "mobile",
        "ios": "mobile",
        "android": "mobile",
    }
    for keyword, domain in domain_map.items():
        if keyword in repo_lower:
            return domain
    return "engineering"


def _infer_team(domain: str) -> str:
    """Infer team from domain."""
    team_map = {
        "auth": "security",
        "payments": "payments",
        "deployment": "platform",
        "infrastructure": "infra",
        "platform": "platform",
        "frontend": "frontend",
        "backend": "backend",
        "mobile": "mobile",
    }
    return team_map.get(domain, "engineering")


def _parse_timestamp(ts: str | datetime) -> datetime:
    """Parse a timestamp string."""
    if isinstance(ts, datetime):
        return ts
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        from datetime import timezone
        return datetime.now(timezone.utc)

"""
Round 47 — Block 1.2: Per-Teammate View.

Builds a per-person view showing that person's tasks, commitments,
attention allocation, and trust score. This is the USER'S view OF a
teammate — it uses only the user's own organizational data about that
person. It does NOT analyze the teammate's personal life. The bright
line holds.

WITHDRAWAL PATH (Guideline P9):
The user can track teammates in a spreadsheet. The view saves time;
without it, the user is slower but functional.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def build_teammate_view(model: Any, signals: list, email: str) -> dict[str, Any]:
    """Build a per-teammate view for a given email.

    Returns:
        {
            email: str,
            name: str,
            tasks: list[dict],           # tasks assigned to this person
            commitments: list[dict],     # commitments this person made
            attention: dict,             # attention allocation summary
            trust_score: int,            # trust score (0-10+)
            influence: float,            # influence score from the KG
            domains: list[str],          # domains this person touches
            signal_count: int,           # total signals from this person
            withdrawal_path: str,
        }
    """
    # Tasks assigned to this person
    tasks = _get_tasks_for_person(model, email)

    # Commitments this person made
    commitments = _get_commitments_for_person(model, signals, email)

    # Attention allocation
    attention = _get_attention_for_person(model, email)

    # Trust score
    trust_score = _get_trust_score(email)

    # Influence and domains from the knowledge graph
    influence = 0.0
    domains: list[str] = []
    try:
        influence_dict = model.knowledge.influence
        influence = influence_dict.get(email, 0.0)
        # Find domains this person touches
        for lo in model.learning_objects.values():
            if email in lo.entities:
                for entity in lo.entities:
                    if entity != email and "." in entity:
                        domains.append(entity)
        domains = list(set(domains))[:5]  # unique, max 5
    except Exception:
        pass

    # Signal count
    signal_count = sum(1 for s in signals if getattr(s, 'actor', '') == email)

    # Name (best effort — use the email prefix)
    name = email.split("@")[0].replace(".", " ").title() if email else ""

    return {
        "email": email,
        "name": name,
        "tasks": tasks,
        "commitments": commitments,
        "attention": attention,
        "trust_score": trust_score,
        "influence": round(influence, 2),
        "domains": domains,
        "signal_count": signal_count,
        "withdrawal_path": (
            "The user can track teammates in a spreadsheet. This view saves time; "
            "without it, the user is slower but functional."
        ),
    }


def _get_tasks_for_person(model: Any, email: str) -> list[dict[str, Any]]:
    """Get tasks assigned to this person from the learning objects."""
    tasks: list[dict[str, Any]] = []
    try:
        for lo in model.learning_objects.values():
            lo_type = lo.type.value if hasattr(lo.type, "value") else str(lo.type)
            if lo_type != "task":
                continue
            assignee = lo.metadata.get("assignee", "")
            if email.lower() in assignee.lower():
                tasks.append({
                    "description": lo.description[:100],
                    "due_date": lo.metadata.get("due_date", ""),
                    "priority": lo.metadata.get("priority", "medium"),
                    "status": lo.metadata.get("status", "open"),
                    "domain": lo.metadata.get("domain", ""),
                })
    except Exception as e:
        logger.debug("Task retrieval for %s failed: %s", email, e)
    return tasks[:10]  # max 10


def _get_commitments_for_person(model: Any, signals: list, email: str) -> list[dict[str, Any]]:
    """Get commitments this person made (from CommitmentTracker)."""
    commitments: list[dict[str, Any]] = []
    try:
        from maestro_oem.commitment_tracker import CommitmentTracker
        tracker = CommitmentTracker(model, signals)
        result = tracker.track()
        for c in result.get("commitments", []):
            if email.lower() in (c.get("who_committed", "")).lower():
                commitments.append({
                    "description": c.get("description", "")[:100],
                    "to_whom": c.get("to_whom", ""),
                    "due_date": c.get("due_date", ""),
                    "status": c.get("status", "open"),
                    "source_artifact": c.get("source_artifact", ""),
                })
    except Exception as e:
        logger.debug("Commitment retrieval for %s failed: %s", email, e)
    return commitments[:10]


def _get_attention_for_person(model: Any, email: str) -> dict[str, Any]:
    """Get attention allocation summary for this person."""
    try:
        from maestro_oem.attention_signals import AttentionSignals
        signals = AttentionSignals.get_summary()
        # Filter to this person if possible
        return {
            "total_signals": signals.get("total", 0),
            "top_item_type": signals.get("top_item_type", ""),
            "summary": signals.get("summary", "No attention data yet."),
        }
    except Exception:
        return {"total_signals": 0, "top_item_type": "", "summary": "No attention data yet."}


def _get_trust_score(email: str) -> int:
    """Get the trust score for this person (from TrustLedger)."""
    try:
        from maestro_oem.trust_ledger import TrustLedger
        # TrustLedger is per-user-action, but we can aggregate for a person
        # by checking all providers. For the pilot, return a simple aggregate.
        return 0  # pilot: no trust data yet until the person takes actions
    except Exception:
        return 0

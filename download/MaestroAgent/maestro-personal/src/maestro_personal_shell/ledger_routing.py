"""
Ledger-first routing for overdue/commitment queries.

Phase 1.2 of Roadmap to 9/10:
  'Route overdue questions to structured ledger state before semantic
   retrieval. FTS may retrieve evidence, but it must not determine
   overdue status.'

This module queries the commitment ledger directly for:
  - overdue: entries in 'at_risk' state
  - broken: entries in 'disputed' state or with broken keywords
  - completed: entries in 'completed_claimed' or 'completed_verified'
  - active: entries in 'active' or 'at_risk' state

The Ask endpoint calls these BEFORE FTS retrieval so the ledger — not
FTS keyword matching — determines which commitments are overdue/broken.
FTS still provides the evidence text, but the ledger provides the state.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def get_overdue_commitments(
    user_email: str,
    db_path: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Get commitments in 'at_risk' state (overdue) from the ledger.

    Phase 1.2: this is the AUTHORITATIVE source for overdue status.
    FTS retrieval may provide evidence text, but the ledger determines
    WHICH commitments are overdue — not keyword matching.
    """
    from maestro_personal_shell.commitment_ledger import get_ledger_entries
    return get_ledger_entries(user_email, db_path, state="at_risk", limit=limit)


def get_broken_commitments(
    user_email: str,
    db_path: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Get commitments in 'disputed' state (broken) from the ledger."""
    from maestro_personal_shell.commitment_ledger import get_ledger_entries
    return get_ledger_entries(user_email, db_path, state="disputed", limit=limit)


def get_active_commitments(
    user_email: str,
    db_path: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Get commitments in 'active' state from the ledger."""
    from maestro_personal_shell.commitment_ledger import get_ledger_entries
    return get_ledger_entries(user_email, db_path, state="active", limit=limit)


def get_completed_commitments(
    user_email: str,
    db_path: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Get completed commitments from the ledger."""
    from maestro_personal_shell.commitment_ledger import get_ledger_entries
    completed = get_ledger_entries(user_email, db_path, state="completed_claimed", limit=limit)
    verified = get_ledger_entries(user_email, db_path, state="completed_verified", limit=limit)
    return completed + verified


def get_all_commitments(
    user_email: str,
    db_path: str,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Get ALL ledger entries for a user (all states)."""
    from maestro_personal_shell.commitment_ledger import get_ledger_entries
    return get_ledger_entries(user_email, db_path, limit=limit)


def route_to_ledger(
    intent: str,
    user_email: str,
    db_path: str,
) -> list[dict[str, Any]] | None:
    """Route an intent to the appropriate ledger query.

    Phase 1.2: for overdue/broken/commitment/relational intents, query
    the ledger FIRST. Returns ledger entries (with state, action, entity,
    deadline) or None if the intent doesn't route to the ledger.

    The caller (Ask endpoint) uses these entries as the PRIMARY evidence
    for the LLM. FTS retrieval augments with raw signal text, but the
    ledger's state field is authoritative for overdue/broken/active status.
    """
    if intent == "overdue":
        entries = get_overdue_commitments(user_email, db_path)
        # Also include active commitments that might be stale
        entries.extend(get_active_commitments(user_email, db_path))
        return entries
    elif intent == "broken":
        entries = get_broken_commitments(user_email, db_path)
        # Also include at_risk (overdue = broken in practice)
        entries.extend(get_overdue_commitments(user_email, db_path))
        return entries
    elif intent == "relational":
        # For "who am I disappointing?" — get all at_risk + disputed
        entries = get_overdue_commitments(user_email, db_path)
        entries.extend(get_broken_commitments(user_email, db_path))
        return entries
    elif intent == "commitment":
        # For "what did I promise?" — get active + at_risk
        entries = get_active_commitments(user_email, db_path)
        entries.extend(get_overdue_commitments(user_email, db_path))
        return entries
    elif intent == "risk":
        entries = get_overdue_commitments(user_email, db_path)
        entries.extend(get_broken_commitments(user_email, db_path))
        return entries

    # For other intents, don't route to ledger
    return None


def ledger_entries_to_evidence(entries: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Convert ledger entries to evidence_refs format for the LLM.

    Each entry becomes:
      {
        "text": "[LEDGER state=at_risk] entity: action (deadline: ...)",
        "entity": entity,
      }
    """
    evidence = []
    for e in entries:
        state = e.get("state", "unknown")
        entity = e.get("entity", "unknown")
        action = e.get("action", e.get("evidence_quote", ""))
        deadline = e.get("deadline_text", "")
        commitment_type = e.get("commitment_type", "")

        text = f"[LEDGER state={state}] {entity}: {action}"
        if deadline:
            text += f" (deadline: {deadline})"
        if commitment_type:
            text += f" [{commitment_type}]"

        evidence.append({"text": text, "entity": entity})

    return evidence

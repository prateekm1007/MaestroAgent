"""
Signal Classes — the canonical taxonomy that makes the OEM provider-agnostic.

Every ExecutionSignal has a SignalType (provider-specific, e.g. 'github.pr_opened').
Every SignalType maps to a SignalClass (canonical, e.g. 'execution').

The OEM engine dispatches on SignalClass, not SignalType. This means:
  - GitHub and GitLab both produce EXECUTION signals — the OEM doesn't care which
  - Slack and Teams both produce COMMUNICATION signals — the OEM doesn't care which
  - Adding a new provider only requires mapping to signal classes

This is the architectural foundation for the Organizational Cognitive Model.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from maestro_oem.signal import SignalType


class SignalClass(str, Enum):
    """Canonical signal classes that any provider can emit.

    These are the categories the OEM reasons over. A provider-specific
    SignalType (e.g. 'github.pr_opened') maps to one of these classes.
    The OEM's _generate_learning_objects() dispatches on SignalClass.
    """
    DECISION = "decision"              # A choice was made
    COMMUNICATION = "communication"    # Information was exchanged
    KNOWLEDGE = "knowledge"            # Something was learned/documented
    EXECUTION = "execution"            # Work was done
    PLANNING = "planning"              # Future work was intended
    CUSTOMER = "customer"              # Customer relationship changed
    LEARNING = "learning"              # The org learned from an outcome
    COMMITMENT = "commitment"          # A promise was made
    OBJECTION = "objection"            # Someone pushed back
    APPROVAL = "approval"              # Someone signed off
    INCIDENT = "incident"              # Something went wrong
    RISK = "risk"                      # A risk signal was detected


# ─── SignalType → SignalClass mapping ───────────────────────────────────────
# Every SignalType must map to exactly one SignalClass. This is the single
# source of truth for the mapping. When a new provider is added, its
# SignalTypes are added to this map.

_SIGNAL_TYPE_TO_CLASS: dict[SignalType, SignalClass] = {
    # GitHub → EXECUTION, KNOWLEDGE, APPROVAL
    SignalType.PR_OPENED: SignalClass.EXECUTION,
    SignalType.PR_MERGED: SignalClass.EXECUTION,
    SignalType.PR_CLOSED: SignalClass.EXECUTION,
    SignalType.PR_REVIEWED: SignalClass.APPROVAL,
    SignalType.COMMIT: SignalClass.EXECUTION,
    SignalType.BRANCH_CREATED: SignalClass.PLANNING,
    SignalType.REPO_CREATED: SignalClass.PLANNING,

    # Jira → EXECUTION, PLANNING
    SignalType.ISSUE_CREATED: SignalClass.EXECUTION,
    SignalType.ISSUE_TRANSITIONED: SignalClass.EXECUTION,
    SignalType.ISSUE_ASSIGNED: SignalClass.COMMITMENT,
    SignalType.SPRINT_STARTED: SignalClass.PLANNING,
    SignalType.SPRINT_COMPLETED: SignalClass.EXECUTION,

    # Slack → COMMUNICATION, DECISION, OBJECTION, APPROVAL
    SignalType.MESSAGE_SENT: SignalClass.COMMUNICATION,
    SignalType.THREAD_STARTED: SignalClass.COMMUNICATION,
    SignalType.DECISION_SIGNAL: SignalClass.DECISION,
    SignalType.QUESTION_ASKED: SignalClass.COMMUNICATION,
    SignalType.AGREEMENT: SignalClass.APPROVAL,
    SignalType.CONFLICT: SignalClass.OBJECTION,

    # Confluence → KNOWLEDGE, PLANNING
    SignalType.PAGE_CREATED: SignalClass.KNOWLEDGE,
    SignalType.PAGE_EDITED: SignalClass.KNOWLEDGE,
    SignalType.PAGE_OWNER_CHANGED: SignalClass.KNOWLEDGE,
    SignalType.RFC_CREATED: SignalClass.PLANNING,
    SignalType.POSTMORTEM_CREATED: SignalClass.LEARNING,

    # Gmail / Calendar → COMMUNICATION, PLANNING, DECISION
    SignalType.MEETING_SCHEDULED: SignalClass.PLANNING,
    SignalType.MEETING_COMPLETED: SignalClass.DECISION,
    SignalType.EMAIL_SENT: SignalClass.COMMUNICATION,
    SignalType.EMAIL_RECEIVED: SignalClass.COMMUNICATION,

    # Generic → INCIDENT, EXECUTION
    SignalType.INCIDENT: SignalClass.INCIDENT,
    SignalType.DEPLOYMENT: SignalClass.EXECUTION,
    SignalType.RELEASE: SignalClass.EXECUTION,

    # Customer Judgment Engine → CUSTOMER, COMMITMENT, RISK, LEARNING
    SignalType.CUSTOMER_MEETING: SignalClass.CUSTOMER,
    SignalType.CUSTOMER_EMAIL: SignalClass.CUSTOMER,
    SignalType.CUSTOMER_STAGE_CHANGE: SignalClass.CUSTOMER,
    SignalType.CUSTOMER_COMMITMENT_MADE: SignalClass.COMMITMENT,
    SignalType.CUSTOMER_COMMITMENT_KEPT: SignalClass.LEARNING,
    SignalType.CUSTOMER_COMMITMENT_BROKEN: SignalClass.RISK,
    SignalType.CUSTOMER_SUPPORT_TICKET: SignalClass.CUSTOMER,
    SignalType.CUSTOMER_CONTRACT_SIGNED: SignalClass.CUSTOMER,
    SignalType.CUSTOMER_CONTRACT_RENEWED: SignalClass.CUSTOMER,
    SignalType.CUSTOMER_CONTRACT_CHURNED: SignalClass.RISK,
    SignalType.CUSTOMER_DECISION: SignalClass.DECISION,
    SignalType.CUSTOMER_OBJECTION: SignalClass.OBJECTION,
    SignalType.CUSTOMER_CHAMPION_ACTIVE: SignalClass.CUSTOMER,
    SignalType.CUSTOMER_CHAMPION_QUIET: SignalClass.RISK,
}


def get_signal_class(signal_type: SignalType) -> SignalClass:
    """Get the canonical SignalClass for a SignalType.

    Every SignalType must map to exactly one SignalClass. If a new
    SignalType is added without a mapping, this raises ValueError —
    the developer must add the mapping to _SIGNAL_TYPE_TO_CLASS.
    """
    cls = _SIGNAL_TYPE_TO_CLASS.get(signal_type)
    if cls is None:
        raise ValueError(
            f"SignalType {signal_type} has no SignalClass mapping. "
            f"Add it to _SIGNAL_TYPE_TO_CLASS in signal_classes.py."
        )
    return cls


def get_signals_by_class(model: Any, signal_class: SignalClass) -> list[Any]:
    """Get all processed signals that belong to a given SignalClass.

    This is the provider-agnostic query: "give me all execution signals"
    returns PR merges, issue transitions, deployments, and releases —
    regardless of whether they came from GitHub, Jira, or a custom provider.
    """
    from maestro_oem.signal import SignalProvider
    results = []
    for signal in getattr(model, '_all_signals', []):
        st = signal.type if hasattr(signal, 'type') else None
        if st and get_signal_class(st) == signal_class:
            results.append(signal)
    return results


def all_signal_types_mapped() -> bool:
    """Verify that every SignalType has a SignalClass mapping.

    Used by the test suite to ensure no SignalType is orphaned.
    """
    return all(st in _SIGNAL_TYPE_TO_CLASS for st in SignalType)


def get_unmapped_signal_types() -> list[SignalType]:
    """Return any SignalTypes that don't have a SignalClass mapping."""
    return [st for st in SignalType if st not in _SIGNAL_TYPE_TO_CLASS]

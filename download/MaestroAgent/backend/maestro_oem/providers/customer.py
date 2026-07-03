"""
Customer signal normalizer — the Customer Judgment Engine's signal provider.

Converts CRM / meeting / email / support / contract events into ExecutionSignal
objects. This is the SAME architecture as normalize_github / normalize_jira /
normalize_slack — the Customer Judgment Engine is just another OEM signal
provider, not a parallel intelligence system.

What this normalizer does NOT do:
  - Store personal information about customer employees (no LinkedIn, no
    hobbies, no family). Only business-relationship metadata.
  - Build a "who is this person" profile. It models the organizational
    relationship (internal employee × customer account), not the person.

Signal taxonomy (all map to SignalType enum values):
  - customer.meeting          — internal × customer meeting completed
  - customer.email            — internal × customer email exchanged
  - customer.stage_change     — pipeline stage transition (relationship milestone)
  - customer.commitment_made  — a promise was made to the customer
  - customer.commitment_kept  — a promise was fulfilled
  - customer.commitment_broken— a promise was missed
  - customer.support_ticket   — support interaction
  - customer.contract_signed  — legal milestone
  - customer.contract_renewed — renewal milestone
  - customer.contract_churned — churn event
  - customer.decision         — the customer made a buying/renewal decision
  - customer.objection        — the customer raised a concern
  - customer.champion_active  — champion is engaged (positive signal)
  - customer.champion_quiet   — champion has gone silent (drift signal)

Every signal carries:
  - actor: the INTERNAL employee (e.g. "jane.d@example.com")
  - metadata.customer: the customer account name (e.g. "<customer>")
  - metadata.contact: the customer-side person (e.g. "raj@example.com")
  - metadata.arr_impact: estimated ARR at stake (float, may be 0)
  - metadata.role: inferred committee role of the contact (champion,
    economic_buyer, technical_buyer, legal, security, procurement,
    executive_sponsor, blocker)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from maestro_oem.signal import ExecutionSignal, SignalProvider, SignalType


# Map raw event_type strings to SignalType enum values.
_TYPE_MAP: dict[str, SignalType] = {
    "meeting": SignalType.CUSTOMER_MEETING,
    "customer_meeting": SignalType.CUSTOMER_MEETING,
    "email": SignalType.CUSTOMER_EMAIL,
    "customer_email": SignalType.CUSTOMER_EMAIL,
    "stage_change": SignalType.CUSTOMER_STAGE_CHANGE,
    "commitment_made": SignalType.CUSTOMER_COMMITMENT_MADE,
    "commitment_kept": SignalType.CUSTOMER_COMMITMENT_KEPT,
    "commitment_broken": SignalType.CUSTOMER_COMMITMENT_BROKEN,
    "support_ticket": SignalType.CUSTOMER_SUPPORT_TICKET,
    "contract_signed": SignalType.CUSTOMER_CONTRACT_SIGNED,
    "contract_renewed": SignalType.CUSTOMER_CONTRACT_RENEWED,
    "contract_churned": SignalType.CUSTOMER_CONTRACT_CHURNED,
    "decision": SignalType.CUSTOMER_DECISION,
    "objection": SignalType.CUSTOMER_OBJECTION,
    "champion_active": SignalType.CUSTOMER_CHAMPION_ACTIVE,
    "champion_quiet": SignalType.CUSTOMER_CHAMPION_QUIET,
}

# Signal types that represent a decision milestone — these nudge
# decision_velocity_days in ExecutionHealth.
_DECISION_TYPES = {
    SignalType.CUSTOMER_DECISION,
    SignalType.CUSTOMER_CONTRACT_SIGNED,
    SignalType.CUSTOMER_CONTRACT_RENEWED,
    SignalType.CUSTOMER_CONTRACT_CHURNED,
    SignalType.CUSTOMER_STAGE_CHANGE,
}

# Signal types that represent risk accumulation — these feed the risk surface.
_RISK_TYPES = {
    SignalType.CUSTOMER_COMMITMENT_BROKEN,
    SignalType.CUSTOMER_OBJECTION,
    SignalType.CUSTOMER_CHAMPION_QUIET,
    SignalType.CUSTOMER_CONTRACT_CHURNED,
}


def normalize_customer(event: dict[str, Any]) -> ExecutionSignal:
    """Convert a customer-relationship event into an ExecutionSignal.

    Expected event format:
        {
            "event_type": "meeting" | "email" | "stage_change" |
                          "commitment_made" | "commitment_kept" | "commitment_broken" |
                          "support_ticket" | "contract_signed" | "contract_renewed" |
                          "contract_churned" | "decision" | "objection" |
                          "champion_active" | "champion_quiet",
            "actor": "jane.d@example.com",        # internal employee
            "artifact": "crm:globex-opp-447",  # CRM opportunity / ticket / contract ID
            "timestamp": "2024-11-12T09:14:00Z",
            "metadata": {
                "customer": "<customer>",            # customer account name
                "contact": "raj@example.com",     # customer-side person (business role only)
                "role": "champion",              # inferred committee role
                "arr_impact": 3200000,           # estimated ARR at stake
                "stage": "negotiation",          # pipeline stage (for stage_change)
                "commitment": "Deliver SSO by Q1",  # for commitment_* events
                "due_date": "2025-01-15",        # for commitment_* events
                "subject": "Q4 renewal discussion",  # for meeting/email events
                "participants": ["jane.d@example.com", "raj@example.com"],
                "sentiment": "positive",         # optional inferred sentiment
            }
        }
    """
    event_type = event.get("event_type", "meeting")
    sig_type = _TYPE_MAP.get(event_type, SignalType.CUSTOMER_MEETING)

    actor = event.get("actor", "unknown")
    artifact = event.get("artifact", "")
    timestamp = event.get("timestamp", datetime.now().isoformat())
    meta_in = event.get("metadata", {}) or {}

    # Build metadata — only business-relationship fields. No personal data.
    metadata: dict[str, Any] = {
        "customer": meta_in.get("customer", "unknown"),
        "contact": meta_in.get("contact", ""),
        "role": meta_in.get("role", ""),  # champion, economic_buyer, etc.
        "arr_impact": float(meta_in.get("arr_impact", 0) or 0),
        "sentiment": meta_in.get("sentiment", ""),
        "participants": meta_in.get("participants", []),
    }

    # Optional fields per event type
    if "stage" in meta_in:
        metadata["stage"] = meta_in["stage"]
    if "commitment" in meta_in:
        metadata["commitment"] = meta_in["commitment"]
    if "due_date" in meta_in:
        metadata["due_date"] = meta_in["due_date"]
    if "subject" in meta_in:
        metadata["subject"] = meta_in["subject"]
    if "ticket_id" in meta_in:
        metadata["ticket_id"] = meta_in["ticket_id"]
    if "contract_value" in meta_in:
        metadata["contract_value"] = float(meta_in["contract_value"] or 0)
    if "decision_outcome" in meta_in:
        metadata["decision_outcome"] = meta_in["decision_outcome"]
    if "objection_type" in meta_in:
        metadata["objection_type"] = meta_in["objection_type"]

    # Decision milestone signals are flagged as decisions.
    is_decision = sig_type in _DECISION_TYPES

    # Confidence: contract events are verified facts (1.0). Inferred signals
    # like champion_quiet are lower (0.7) because "quiet" is an inference
    # from absence-of-activity, not a direct observation.
    if sig_type in (SignalType.CUSTOMER_CONTRACT_SIGNED,
                    SignalType.CUSTOMER_CONTRACT_RENEWED,
                    SignalType.CUSTOMER_CONTRACT_CHURNED):
        confidence = 1.0
    elif sig_type == SignalType.CUSTOMER_CHAMPION_QUIET:
        confidence = 0.7
    elif sig_type == SignalType.CUSTOMER_CHAMPION_ACTIVE:
        confidence = 0.85
    else:
        confidence = 0.95

    return ExecutionSignal(
        type=sig_type,
        timestamp=_parse_timestamp(timestamp),
        actor=actor,
        team=event.get("team", "customer_success"),
        artifact=artifact,
        decision=is_decision,
        confidence=confidence,
        metadata=metadata,
        provider=SignalProvider.CUSTOMER,
    )


def _parse_timestamp(ts: str | datetime) -> datetime:
    if isinstance(ts, datetime):
        return ts
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        from datetime import timezone
        return datetime.now(timezone.utc)


def is_risk_signal(signal: ExecutionSignal) -> bool:
    """True if this customer signal represents risk accumulation."""
    return signal.type in _RISK_TYPES


def is_decision_signal(signal: ExecutionSignal) -> bool:
    """True if this customer signal represents a decision milestone."""
    return signal.type in _DECISION_TYPES

"""
Maestro Cognitive Council — C2 Fix: ACL on Derived Intelligence.

Per the audit (C2): "Summaries generated from restricted evidence can
expose the substance of the restriction. This is the most common privacy
failure mode in retrieval-augmented systems."

This module propagates ACL restrictions from source evidence to derived
intelligence (judgments, briefings, whispers, preparations). If ANY
source evidence is restricted, the derived intelligence inherits that
restriction.

The barrier is enforced at the bridge layer — every bridge must call
`propagate_acl_restrictions()` before returning derived intelligence.

Usage:
    from maestro_cognitive_council.acl_barrier import propagate_acl_restrictions

    # Before returning a judgment/briefing/whisper:
    result = propagate_acl_restrictions(result, source_evidence, user_email)
    if result["acl_restricted"]:
        # Redact or suppress restricted content
        result = redact_restricted_content(result)
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def propagate_acl_restrictions(
    derived_intelligence: dict[str, Any],
    source_evidence: list[Any],
    user_email: str = "",
) -> dict[str, Any]:
    """Propagate ACL restrictions from source evidence to derived intelligence.

    Per C2: if ANY source evidence is restricted (private, limited audience),
    the derived intelligence inherits that restriction. This prevents
    summaries from exposing the substance of restricted evidence.

    Args:
        derived_intelligence: the judgment/briefing/whisper dict
        source_evidence: list of source evidence objects (signals)
        user_email: the requesting user's email (for ACL check)

    Returns:
        The same dict with ACL fields added:
          - acl_restricted: True if any source is restricted
          - acl_restricted_sources: list of restricted source IDs
          - acl_redacted: True if content was redacted
    """
    restricted_sources: list[str] = []
    is_restricted = False

    for evidence in source_evidence:
        # Check if this evidence is ACL-restricted
        metadata = getattr(evidence, "metadata", None) or {}
        source_acl = metadata.get("source_acl", "public")

        if source_acl != "public":
            # Check if the user has access
            if not _user_has_access(evidence, user_email):
                is_restricted = True
                evidence_id = (
                    getattr(evidence, "signal_id", "")
                    or getattr(evidence, "evidence_id", "")
                    or str(id(evidence))
                )
                restricted_sources.append(evidence_id)

    derived_intelligence["acl_restricted"] = is_restricted
    derived_intelligence["acl_restricted_sources"] = restricted_sources
    derived_intelligence["acl_redacted"] = False  # always set, even if not restricted

    if is_restricted:
        logger.info(
            "C2 BARRIER: Derived intelligence restricted — %d source(s) "
            "inaccessible to user %s",
            len(restricted_sources),
            user_email or "anonymous",
        )

    return derived_intelligence


def redact_restricted_content(
    derived_intelligence: dict[str, Any],
) -> dict[str, Any]:
    """Redact content that derives from restricted evidence.

    When derived intelligence is ACL-restricted and the user doesn't have
    access to all sources, the content must be redacted — not hidden
    entirely (the user should know something exists), but the substance
    must be removed.

    Args:
        derived_intelligence: the dict to redact

    Returns:
        The same dict with restricted content redacted.
    """
    if not derived_intelligence.get("acl_restricted", False):
        derived_intelligence["acl_redacted"] = False
        return derived_intelligence

    # Redact text fields that might contain restricted substance
    text_fields = [
        "answer", "insight", "situation_context", "why_surfaced",
        "central_claim", "strongest_reason_to_act", "strongest_reason_not_to_act",
        "recommended_next_step", "smallest_useful_next_step",
        "belief", "why_belief",
    ]

    for field in text_fields:
        if field in derived_intelligence and derived_intelligence[field]:
            derived_intelligence[field] = (
                "[RESTRICTED] This content derives from evidence you don't "
                "have access to. Contact an administrator if you need access."
            )

    # Redact nested text fields
    if "judgment" in derived_intelligence and isinstance(derived_intelligence["judgment"], dict):
        for field in ["central_claim", "strongest_reason_to_act", "recommended_next_step"]:
            if field in derived_intelligence["judgment"]:
                derived_intelligence["judgment"][field] = "[RESTRICTED]"

    if "decision_boundary" in derived_intelligence and isinstance(derived_intelligence["decision_boundary"], dict):
        for field in ["can_decide_now", "cannot_decide_yet", "why", "smallest_useful_next_step"]:
            if field in derived_intelligence["decision_boundary"]:
                if isinstance(derived_intelligence["decision_boundary"][field], list):
                    derived_intelligence["decision_boundary"][field] = ["[RESTRICTED]"]
                else:
                    derived_intelligence["decision_boundary"][field] = "[RESTRICTED]"

    # Redact whisper cards
    if "whispers" in derived_intelligence and isinstance(derived_intelligence["whispers"], list):
        for whisper in derived_intelligence["whispers"]:
            if isinstance(whisper, dict):
                for field in ["insight", "action", "why_surfaced", "situation_context"]:
                    if field in whisper:
                        whisper[field] = "[RESTRICTED]"

    # Redact talking points
    if "talking_points" in derived_intelligence and isinstance(derived_intelligence["talking_points"], list):
        derived_intelligence["talking_points"] = [
            {"text": "[RESTRICTED]", "priority": "high"} if isinstance(tp, dict) else "[RESTRICTED]"
            for tp in derived_intelligence["talking_points"]
        ]

    # Redact evidence_refs (don't expose the IDs of restricted evidence)
    if "evidence_refs" in derived_intelligence:
        derived_intelligence["evidence_refs"] = ["[RESTRICTED]"]

    derived_intelligence["acl_redacted"] = True

    return derived_intelligence


def _user_has_access(evidence: Any, user_email: str) -> bool:
    """Check if a user has access to a piece of evidence.

    Args:
        evidence: the signal/evidence object
        user_email: the user's email

    Returns:
        True if the user has access, False if the evidence is restricted
        from this user.
    """
    metadata = getattr(evidence, "metadata", None) or {}
    source_acl = metadata.get("source_acl", "public")

    if source_acl == "public":
        return True

    if not user_email:
        return False  # fail-closed: no user = no access to restricted

    # Check if user is the actor (check both attribute and metadata)
    actor = getattr(evidence, "actor", "")
    if not actor or not isinstance(actor, str):
        actor = metadata.get("actor", "")
    if actor and isinstance(actor, str) and actor.lower() == user_email.lower():
        return True

    # Check if user is in the viewers list
    viewers = metadata.get("viewers", [])
    if user_email.lower() in [v.lower() for v in viewers]:
        return True

    # Check if user is in the audience
    audience = metadata.get("audience", [])
    if user_email.lower() in [a.lower() for a in audience]:
        return True

    return False

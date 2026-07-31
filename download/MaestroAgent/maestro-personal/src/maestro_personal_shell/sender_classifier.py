"""Sender classifier — suppress machine-generated content (Phase 3.2).

66% of ambient alerts are noise (AWS, GitHub, LinkedIn, Product Hunt).
Machine senders must never become commitments. This module classifies
senders at ingestion time and rejects machine content before the
commitment classifier runs.

P56: rules-only, no LLM. P85: never raises.
"""
from __future__ import annotations

import re
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Known machine sender entities (case-insensitive substring match)
_MACHINE_ENTITIES = {
    "aws billing", "aws", "github", "linkedin", "product hunt", "producthunt",
    "vercel", "railway", "spotify", "kotak", "zerodha", "polsia",
    "notion", "slack", "discord", "stripe", "google cloud", "google",
    "microsoft", "azure", "digitalocean", "heroku", "netlify",
    "cloudflare", "github notifications", "github actions",
    "the athletic", "washington post", "dalal street",
    "communications", "communications team", "noreply", "no-reply",
}

# Machine text patterns (indicates automated content, not a personal commitment)
_MACHINE_TEXT_PATTERNS = [
    r"\bprocessed automatically\b",
    r"\bno action (is )?needed\b",
    r"\bdo not reply\b",
    r"\bunsubscribe\b",
    r"\byour (monthly )?bill\b",
    r"\binvoice #?\d",
    r"\breceipt\b",
    r"\bverification code\b",
    r"\bsecurity alert\b",
    r"\byour (account|subscription|plan)\b",
    r"\bwas (successfully )?(processed|charged|renewed)\b",
    r"\bthank you for your (payment|purchase|subscription)\b",
    r"\bprivacy (policy|notice|update)\b",
    r"\bterms of service\b",
    r"\bcopyright\b",
    r"\ball rights reserved\b",
]

# Machine sender email patterns (from metadata)
_MACHINE_SENDER_PATTERNS = [
    r"^noreply@",
    r"^no-reply@",
    r"^notifications@",
    r"^notification@",
    r"^billing@",
    r"^alerts@",
    r"^alert@",
    r"^automated@",
    r"^donotreply@",
    r"^do-not-reply@",
    r"^updates@",
    r"^newsletter@",
    r"^marketing@",
    r"^noreply\.",
]

# Signal types that are automatically machine
_MACHINE_SIGNAL_TYPES = {
    "notification", "newsletter", "billing", "marketing",
    "notification_digest", "automated", "system",
}

_PATTERN_COMPILED = [re.compile(p, re.IGNORECASE) for p in _MACHINE_TEXT_PATTERNS]
_SENDER_COMPILED = [re.compile(p, re.IGNORECASE) for p in _MACHINE_SENDER_PATTERNS]


def classify_sender(entity: str, text: str, metadata: dict | None = None) -> dict:
    """Classify whether a signal is from a machine sender.

    Returns:
        {is_machine: bool, sender_type: str, should_skip: bool, reason: str}

    P85: never raises — returns human classification on any error.
    """
    try:
        entity_lower = (entity or "").lower().strip()
        text_lower = (text or "").lower()
        meta = metadata or {}
        if isinstance(meta, str):
            try:
                import json
                meta = json.loads(meta) if meta else {}
            except Exception:
                meta = {}

        # 1. Check entity against known machine entities
        for machine_entity in _MACHINE_ENTITIES:
            if machine_entity in entity_lower:
                sender_type = "machine_billing" if any(w in entity_lower for w in ["billing", "invoice", "kotak", "zerodha"]) else \
                             "machine_notification" if any(w in entity_lower for w in ["github", "notifications", "alerts"]) else \
                             "machine_marketing" if any(w in entity_lower for w in ["product hunt", "spotify", "athletic", "washington"]) else \
                             "machine_social" if any(w in entity_lower for w in ["linkedin", "slack", "discord"]) else \
                             "machine_notification"
                return {
                    "is_machine": True,
                    "sender_type": sender_type,
                    "should_skip": True,
                    "reason": f"Known machine sender: {entity[:50]}",
                }

        # 2. Check sender email from metadata
        sender_email = ""
        for key in ("sender", "from", "sender_email", "source_email"):
            val = meta.get(key, "")
            if val:
                sender_email = str(val).lower()
                break

        if sender_email:
            for pattern in _SENDER_COMPILED:
                if pattern.search(sender_email):
                    return {
                        "is_machine": True,
                        "sender_type": "machine_notification",
                        "should_skip": True,
                        "reason": f"Machine sender email pattern: {sender_email[:50]}",
                    }

        # 3. Check text for machine content patterns
        for pattern in _PATTERN_COMPILED:
            if pattern.search(text_lower):
                return {
                    "is_machine": True,
                    "sender_type": "machine_notification",
                    "should_skip": True,
                    "reason": f"Machine text pattern matched in content",
                }

        # 4. Check signal_type from metadata
        signal_type = str(meta.get("signal_type", "") or "").lower()
        if signal_type in _MACHINE_SIGNAL_TYPES:
            return {
                "is_machine": True,
                "sender_type": "machine_notification",
                "should_skip": True,
                "reason": f"Machine signal_type: {signal_type}",
            }

        # Not a machine sender
        return {
            "is_machine": False,
            "sender_type": "human",
            "should_skip": False,
            "reason": "Human sender",
        }

    except Exception as e:
        logger.warning("sender_classifier failed: %s", e)
        return {
            "is_machine": False,
            "sender_type": "human",
            "should_skip": False,
            "reason": f"classification failed: {e}",
        }

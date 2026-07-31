"""Signal-to-noise classifier (P74).

Rejects newsletters, billing notices, security alerts, and automated
notifications at ingestion — not flagged for user dismissal.

Root cause (P10): 80% dismissal rate because no noise filter at ingestion.
Every newsletter, billing notice, and GitHub notification became a "signal"
that the user then had to dismiss manually.

P56: rules-only, no LLM.
P74: >90% precision on noise rejection.
P85: never raises — returns is_noise=False on any error.

Authored by: CTO (direct — Kimi K3 output truncated; pattern was clear
  from K3's start with 216 noise domains organized by category)
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["classify_noise", "filter_noise_signals", "NOISE_DOMAINS", "NOISE_SENDER_PATTERNS"]

THRESHOLD = 0.6

# Known noise domains organized by category.
# Each category maps to a noise_type in the output.
NOISE_DOMAINS: dict[str, set[str]] = {
    "newsletter": {
        "mailchimp.com", "substack.com", "beehiiv.com", "convertkit.com",
        "mailerlite.com", "constantcontact.com", "aweber.com", "getresponse.com",
        "campaignmonitor.com", "klaviyo.com", "braze.com", "iterable.com",
        "customer.io", "sendgrid.com", "sendinblue.com", "brevo.com",
        "hubspot.com", "marketo.com", "activedemand.com", "drip.com",
        "moosend.com", "omnisend.com", " MailerLite.com",
    },
    "billing": {
        "aws-billing.com", "billing.stripe.com", "billing.amazonaws.com",
        "invoices@quickbooks.com", "billing@freshbooks.com", "xero.com",
        "quickbooks.intuit.com", "receipts@apple.com", "billing@google.com",
        "aws.amazon.com", "azure.com", "digitalocean.com",
    },
    "notification": {
        "github.com", "gitlab.com", "bitbucket.org", "atlassian.com",
        "jira.com", "trello.com", "asana.com", "linear.app", "clickup.com",
        "notion.so", "slack.com", "discord.com", "teams.microsoft.com",
        "notifications@google.com", "noreply@medium.com",
        "producthunt.com", "hunter.io", "intercom.io", "zendesk.com",
        "freshdesk.com", "helpscout.net",
    },
    "social": {
        "facebook.com", "twitter.com", "instagram.com", "linkedin.com",
        "tiktok.com", "reddit.com", "pinterest.com", "snapchat.com",
        "youtube.com", "twitch.tv",
    },
    "security_alert": {
        "security@github.com", "noreply@accounts.google.com",
        "security@google.com", "alert@azure.com", "aws-security.com",
        "cloudflare.com", "sucuri.net", "wordfence.com",
        "security@cloudflare.com", "letsencrypt.org",
    },
}

# Flatten for O(1) lookup
_NOISE_DOMAIN_INDEX: dict[str, str] = {}
for _cat, _domains in NOISE_DOMAINS.items():
    for _d in _domains:
        _NOISE_DOMAIN_INDEX[_d.lower().strip()] = _cat

# Sender patterns that indicate automated/noise email
NOISE_SENDER_PATTERNS = [
    (re.compile(r"^noreply@", re.I), "notification"),
    (re.compile(r"^no-reply@", re.I), "notification"),
    (re.compile(r"^notifications@", re.I), "notification"),
    (re.compile(r"^billing@", re.I), "billing"),
    (re.compile(r"^automated@", re.I), "notification"),
    (re.compile(r"^alerts@", re.I), "security_alert"),
    (re.compile(r"^security@", re.I), "security_alert"),
    (re.compile(r"^donotreply@", re.I), "notification"),
    (re.compile(r"^do-not-reply@", re.I), "notification"),
]

# Content patterns that indicate noise
_UNSUBSCRIBE_RE = re.compile(
    r"(unsubscribe|opt.out|manage.preferences|click.here.to.stop)",
    re.I,
)
_BILLING_AMOUNT_RE = re.compile(
    r"\$\d{1,4}[.,]\d{2}\s*(USD|EUR|GBP)?",
    re.I,
)
_SECURITY_CODE_RE = re.compile(
    r"(verification.code|security.code|one.time.code|2FA|MFA|OTP)",
    re.I,
)
_ORDER_CONFIRMATION_RE = re.compile(
    r"(order.confirmation|receipt.your.order|your.receipt|invoice.#)",
    re.I,
)

# Source types that are automatically noise
_NOISE_SOURCE_TYPES = {"newsletter", "notification", "billing", "social"}


def _extract_sender(signal: dict) -> str:
    """Extract sender email from signal metadata or fields."""
    # Try metadata first
    meta = signal.get("metadata", {})
    if isinstance(meta, str):
        try:
            import json
            meta = json.loads(meta) if meta else {}
        except Exception:
            meta = {}
    if isinstance(meta, dict):
        sender = meta.get("sender") or meta.get("from") or meta.get("sender_email")
        if sender:
            return str(sender)
    # Try direct fields
    for key in ("sender", "from", "sender_email", "source_email"):
        val = signal.get(key)
        if val:
            return str(val)
    return ""


def _extract_domain(email: str) -> str:
    """Extract the domain from an email address."""
    if "@" not in email:
        return ""
    return email.rsplit("@", 1)[-1].lower().strip()


def _extract_text(signal: dict) -> str:
    """Extract text content from signal."""
    for key in ("text", "content", "body", "snippet"):
        val = signal.get(key)
        if val:
            return str(val)
    return ""


def classify_noise(signal: dict | Any) -> dict:
    """Classify whether a signal is noise (P74).

    Returns:
        {is_noise: bool, noise_type: str|None, confidence: float, reasoning: str}

    P56: rules-only, no LLM.
    P85: never raises — returns is_noise=False on any error.
    """
    try:
        if not isinstance(signal, dict):
            return {"is_noise": False, "noise_type": None, "confidence": 0.0,
                    "reasoning": "non-dict signal, cannot classify"}

        # 1. Check source_type — if already labeled as noise, auto-classify
        source_type = signal.get("source_type") or signal.get("source") or ""
        if isinstance(source_type, str) and source_type.lower() in _NOISE_SOURCE_TYPES:
            return {
                "is_noise": True,
                "noise_type": source_type.lower(),
                "confidence": 0.95,
                "reasoning": f"source_type={source_type} is a known noise category",
            }

        # 2. Check sender domain against known noise domains
        sender = _extract_sender(signal)
        domain = _extract_domain(sender)
        if domain and domain in _NOISE_DOMAIN_INDEX:
            noise_cat = _NOISE_DOMAIN_INDEX[domain]
            return {
                "is_noise": True,
                "noise_type": noise_cat,
                "confidence": 0.9,
                "reasoning": f"sender domain {domain} is a known {noise_cat} domain",
            }

        # 3. Check sender pattern (noreply@, billing@, etc.)
        if sender:
            for pattern, noise_cat in NOISE_SENDER_PATTERNS:
                if pattern.search(sender):
                    return {
                        "is_noise": True,
                        "noise_type": noise_cat,
                        "confidence": 0.85,
                        "reasoning": f"sender matches noise pattern {pattern.pattern}",
                    }

        # 4. Check content patterns
        text = _extract_text(signal)
        if text:
            noise_signals = []
            if _UNSUBSCRIBE_RE.search(text):
                noise_signals.append("unsubscribe link")
            if _BILLING_AMOUNT_RE.search(text):
                noise_signals.append("billing amount")
            if _SECURITY_CODE_RE.search(text):
                noise_signals.append("security code")
            if _ORDER_CONFIRMATION_RE.search(text):
                noise_signals.append("order confirmation")

            if len(noise_signals) >= 2:
                return {
                    "is_noise": True,
                    "noise_type": "notification",
                    "confidence": 0.8,
                    "reasoning": f"content matches {', '.join(noise_signals)}",
                }
            elif len(noise_signals) == 1:
                # Single signal — lower confidence, might be a real email that mentions unsubscribe
                return {
                    "is_noise": True,
                    "noise_type": "notification",
                    "confidence": 0.65,
                    "reasoning": f"content matches {noise_signals[0]}",
                }

        # 5. Not noise — appears to be a real signal
        return {
            "is_noise": False,
            "noise_type": None,
            "confidence": 0.7,
            "reasoning": "no noise patterns matched",
        }
    except Exception as exc:
        logger.exception("classify_noise failed: %s", exc)
        return {"is_noise": False, "noise_type": None, "confidence": 0.0,
                "reasoning": f"classification failed: {exc}"}


def filter_noise_signals(signals: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split a list of signals into (clean, noise).

    Used at ingestion to reject noise before it enters the ledger.
    P85: never raises — on error, returns (signals, []) (treat all as clean).
    """
    try:
        clean = []
        noise = []
        for sig in signals:
            result = classify_noise(sig)
            if result["is_noise"] and result["confidence"] >= THRESHOLD:
                noise.append({**sig, "_noise_classification": result})
            else:
                clean.append(sig)
        return clean, noise
    except Exception as exc:
        logger.exception("filter_noise_signals failed: %s", exc)
        return signals, []  # safe default: treat all as clean

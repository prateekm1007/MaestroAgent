"""Honest fallback labels for T3 walled gardens.

Personal WhatsApp/Instagram/Facebook/LinkedIn DMs have NO official third-party
read API. The category leader (Onyx) doesn't have them either. This module
provides the honest product surface: clear labels explaining what's legible
and what isn't, plus the legit workarounds.

This is the moat: a vendor that says per source exactly what's legible and
what isn't — with a graceful, honest fallback for each walled garden.
"""
from __future__ import annotations

import logging
from typing import Any

from maestro_personal_shell.connector_framework import Signal
from maestro_personal_shell.connector_framework.base import BaseConnector, SyncCursor
from maestro_personal_shell.connector_framework.registry import register_adapter

logger = logging.getLogger(__name__)


# Honest labels for the Connectors UI — never a fake "connected"
HONEST_LABELS: dict[str, dict[str, str]] = {
    "whatsapp": {
        "status": "not_supported_personal",
        "label": "Personal WhatsApp: no third-party read API",
        "description": (
            "WhatsApp does not allow third-party apps to read personal chat history. "
            "WhatsApp Business Cloud API is supported for business numbers. "
            "For personal use: forward messages to your Maestro ingest email."
        ),
        "business_api": "WhatsApp Business Cloud API (requires business verification + dedicated number)",
        "personal_workaround": "Forward-to-Maestro: forward WhatsApp messages to your ingest email address",
    },
    "instagram": {
        "status": "partial",
        "label": "Instagram: business/creator accounts only",
        "description": (
            "Instagram Graph API supports business/creator accounts for comments, mentions, "
            "and DMs with your business. Personal DMs are not readable via API. "
            "Instagram notification emails are parsed automatically (source:instagram)."
        ),
        "business_api": "Instagram Graph API (business/creator accounts)",
        "personal_workaround": "Email parser active — IG notifications parsed from your inbox",
    },
    "facebook": {
        "status": "partial",
        "label": "Facebook: Pages/Messenger only",
        "description": (
            "Facebook Messenger Platform supports conversations with your Page (business). "
            "Personal messages are not readable via API. "
            "Facebook notification emails are parsed automatically (source:facebook)."
        ),
        "business_api": "Messenger Platform + Pages API (business accounts)",
        "personal_workaround": "Email parser active — FB notifications parsed from your inbox",
    },
    "linkedin": {
        "status": "partial",
        "label": "LinkedIn: limited API, email parser active",
        "description": (
            "LinkedIn's personal DMs are not available to third-party consumer apps. "
            "Limited API for posts/activity where permitted. "
            "LinkedIn notification emails are parsed automatically (source:linkedin)."
        ),
        "business_api": "LinkedIn API (limited — posts, share, marketing)",
        "personal_workaround": "Email parser active — LinkedIn notifications parsed from your inbox",
    },
}


def get_honest_label(source: str) -> dict[str, str] | None:
    """Get the honest label for a walled-garden source."""
    return HONEST_LABELS.get(source)


def is_walled_garden(source: str) -> bool:
    """Check if a source is a walled garden (no personal read API)."""
    return source in HONEST_LABELS


@register_adapter("whatsapp_business")
class WhatsAppBusinessAdapter(BaseConnector):
    """WhatsApp Business Cloud API — legit B2B inbound connector.

    Requires business verification + dedicated phone number.
    Receives messages sent to your business number via webhooks.

    Personal WhatsApp history: NO official read API. Do NOT use grey
    libraries (whatsapp-web.js/Baileys) as a "supported" feature —
    they violate ToS and get numbers banned.
    """

    connector_name = "whatsapp_business"

    def __init__(self) -> None:
        self.access_token: str | None = None
        self.phone_number_id: str | None = None
        self.verify_token: str | None = None

    def load_credentials(self, credentials: dict[str, Any]) -> None:
        self.access_token = credentials.get("access_token")
        self.phone_number_id = credentials.get("phone_number_id")
        self.verify_token = credentials.get("verify_token")

    def load_from_state(self, user_email: str) -> list[Signal]:
        """WhatsApp Business uses webhooks, not polling. Return empty."""
        return []

    def poll_source(self, user_email: str, cursor: SyncCursor) -> tuple[list[Signal], SyncCursor]:
        """WhatsApp Business uses webhooks. Return empty."""
        return [], cursor

    def slim_check(self, user_email: str) -> list[str]:
        return []

    def process_webhook(self, webhook_data: dict) -> list[Signal]:
        """Process a WhatsApp Business webhook payload.

        Called by the webhook endpoint when a message is received.
        """
        signals: list[Signal] = []
        try:
            for entry in webhook_data.get("entry", []):
                for change in entry.get("changes", []):
                    messages = change.get("value", {}).get("messages", [])
                    for msg in messages:
                        from_phone = msg.get("from", "")
                        text = msg.get("text", {}).get("body", "")
                        msg_id = msg.get("id", "")
                        timestamp = msg.get("timestamp", "")

                        if text:
                            signals.append(Signal(
                                source="whatsapp",
                                source_id=msg_id,
                                thread_id=from_phone,
                                entity=f"WhatsApp +{from_phone}",
                                text=text,
                                timestamp=datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
                                if timestamp else datetime.now(timezone.utc),
                                direction="inbound",
                                metadata={
                                    "source": "whatsapp",
                                    "from": from_phone,
                                    "message_id": msg_id,
                                    "type": "whatsapp_business",
                                },
                                confidence=0.7,
                            ))
        except Exception as e:
            logger.error("WhatsAppBusinessAdapter.process_webhook failed: %s", e)

        return signals


@register_adapter("forward_to_maestro")
class ForwardToMaestroAdapter(BaseConnector):
    """Honest fallback: user forwards messages to Maestro's ingest email.

    For platforms with no API (personal WhatsApp, IG DMs, FB messages):
    the user forwards the message to ingest@maestro... and Maestro ingests
    it as a signal with source:"forwarded".

    This is the honest workaround — clearly labeled, never pretending to
    be a native API integration.
    """

    connector_name = "forward_to_maestro"

    def __init__(self) -> None:
        pass

    def load_credentials(self, credentials: dict[str, Any]) -> None:
        pass

    def load_from_state(self, user_email: str) -> list[Signal]:
        return []

    def poll_source(self, user_email: str, cursor: SyncCursor) -> tuple[list[Signal], SyncCursor]:
        return [], cursor

    def slim_check(self, user_email: str) -> list[str]:
        return []

    def ingest_forwarded_message(
        self,
        user_email: str,
        from_header: str,
        subject: str,
        body: str,
        original_source: str = "unknown",
    ) -> Signal:
        """Create a signal from a forwarded message.

        Args:
            user_email: The Maestro user who forwarded the message
            from_header: The From header of the original message
            subject: The subject line
            body: The message body
            original_source: What platform it was forwarded from (e.g., "whatsapp")
        """
        entity = from_header
        if "<" in from_header:
            entity = from_header.split("<")[0].strip().strip('"')

        return Signal(
            source=original_source,
            source_id=f"forwarded_{datetime.now(timezone.utc).timestamp()}",
            thread_id=None,
            entity=entity,
            text=f"{subject} — {body[:500]}" if subject else body[:500],
            timestamp=datetime.now(timezone.utc),
            direction="inbound",
            metadata={
                "source": original_source,
                "type": "forwarded",
                "from": from_header,
                "subject": subject,
                "ingest_method": "forward_to_maestro",
            },
            confidence=0.6,
        )

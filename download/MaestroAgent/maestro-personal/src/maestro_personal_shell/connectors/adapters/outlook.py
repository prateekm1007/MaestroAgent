"""Outlook/M365 adapter — T1 connector with Graph delta sync + IMAP fallback.

Outlook is the B2B moat multiplier — corporate mail is Exchange/M365.
Microsoft Graph's delta query is exactly PipesHub's sync-point, native to
the API: first call returns all + a deltaLink; subsequent calls return only
changes (new/updated/deleted). That's incremental sync with deletion handling.

For non-M365 work mail (self-hosted, Zoho, etc.), supports IMAP with
app-passwords as a fallback — the "customer provides work email" path
with zero OAuth.

Gate: connect a real M365 mailbox → delta-sync → Ask returns source:"outlook"
with a real work email; reconnect after deploy → cursor resumes (no re-pull).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from maestro_personal_shell.connectors import Signal
from maestro_personal_shell.connectors.base import BaseConnector, SyncCursor
from maestro_personal_shell.connectors.registry import register_adapter

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


@register_adapter("outlook")
class OutlookAdapter(BaseConnector):
    """Outlook/M365 connector using Microsoft Graph + delta query.

    Auth: Microsoft identity platform OAuth2
    Cursor: {"deltaLink": "..."} — the Graph delta token
    Idempotency: message id (unique per mailbox)
    Realtime: webhooks (/subscriptions, changeType: created,updated)
    """

    connector_name = "outlook"

    def __init__(self) -> None:
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self.client_id: str = os.environ.get("MAESTRO_OUTLOOK_CLIENT_ID", "")
        self.client_secret: str = os.environ.get("MAESTRO_OUTLOOK_CLIENT_SECRET", "")

    def load_credentials(self, credentials: dict[str, Any]) -> None:
        self.access_token = credentials.get("access_token")
        self.refresh_token = credentials.get("refresh_token")

    def _is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _get_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
        }

    def load_from_state(self, user_email: str) -> list[Signal]:
        """Bulk load — fetch recent messages via Graph API."""
        if not self.access_token:
            return []

        signals: list[Signal] = []
        try:
            import httpx

            # Fetch recent messages (top 50)
            resp = httpx.get(
                f"{GRAPH_BASE}/me/messages",
                params={"$top": 50, "$select": "id,subject,body,from,receivedDateTime,conversationId"},
                headers=self._get_headers(),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            for msg in data.get("value", []):
                sig = self._message_to_signal(msg)
                if sig:
                    signals.append(sig)

            logger.info("OutlookAdapter.load_from_state: %d signals", len(signals))
        except Exception as e:
            logger.error("OutlookAdapter.load_from_state failed: %s", e)

        return signals

    def poll_source(self, user_email: str, cursor: SyncCursor) -> tuple[list[Signal], SyncCursor]:
        """Incremental sync using Graph delta query — the PipesHub sync-point native to M365.

        First call: returns all messages + a deltaLink
        Subsequent calls with deltaLink: returns only changes (new/updated/deleted)
        """
        if not self.access_token:
            return [], cursor

        try:
            import httpx

            delta_link = cursor.cursor_data.get("deltaLink")
            url = delta_link or f"{GRAPH_BASE}/me/messages/delta"

            signals: list[Signal] = []

            while url:
                resp = httpx.get(
                    url,
                    params={"$select": "id,subject,body,from,receivedDateTime,conversationId"},
                    headers=self._get_headers(),
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()

                for msg in data.get("value", []):
                    # Skip deleted messages (delta returns tombstones)
                    if msg.get("@removed"):
                        continue
                    sig = self._message_to_signal(msg)
                    if sig:
                        signals.append(sig)

                # Check for next page
                url = data.get("@odata.nextLink")

            # Save the deltaLink for next sync
            cursor.cursor_data["deltaLink"] = data.get("@odata.deltaLink", "")
            cursor.last_sync = datetime.now(timezone.utc)
            cursor.total_synced += len(signals)

            return signals, cursor
        except Exception as e:
            logger.error("OutlookAdapter.poll_source failed: %s", e)
            return [], cursor

    def slim_check(self, user_email: str) -> list[str]:
        """Return IDs of all Outlook messages that still exist."""
        if not self.access_token:
            return []

        try:
            import httpx

            resp = httpx.get(
                f"{GRAPH_BASE}/me/messages",
                params={"$top": 1000, "$select": "id"},
                headers=self._get_headers(),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            return [msg["id"] for msg in data.get("value", []) if msg.get("id")]
        except Exception:
            return []

    def _message_to_signal(self, msg: dict) -> Signal | None:
        """Convert a Graph message to a Signal."""
        try:
            from_data = msg.get("from", {}).get("emailAddress", {})
            entity = from_data.get("name", from_data.get("address", "unknown"))
            subject = msg.get("subject", "")
            body = msg.get("body", {}).get("content", "")
            # Strip HTML tags from body
            import re
            body_text = re.sub(r"<[^>]+>", "", body)[:500] if body else ""

            text = f"{subject} — {body_text}" if subject else body_text

            return Signal(
                source="outlook",
                source_id=msg.get("id", ""),
                thread_id=msg.get("conversationId"),
                entity=entity,
                text=text,
                timestamp=datetime.fromisoformat(
                    msg.get("receivedDateTime", "").replace("Z", "+00:00")
                ) if msg.get("receivedDateTime") else datetime.now(timezone.utc),
                direction="inbound",
                metadata={
                    "source": "outlook",
                    "from": from_data.get("address", ""),
                    "subject": subject,
                    "message_id": msg.get("id", ""),
                },
                confidence=0.5,
            )
        except Exception as e:
            logger.debug("OutlookAdapter._message_to_signal failed: %s", e)
            return None

    def get_authorization_url(self, redirect_uri: str, state: str) -> str:
        """Get the Microsoft OAuth2 authorization URL."""
        from urllib.parse import urlencode

        scopes = [
            "https://graph.microsoft.com/Mail.Read",
            "https://graph.microsoft.com/Mail.Send",
            "offline_access",
        ]

        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": " ".join(scopes),
            "state": state,
            "response_mode": "query",
        }

        return f"https://login.microsoftonline.com/common/oauth2/v2.0/authorize?{urlencode(params)}"

    def exchange_code_for_tokens(self, code: str, redirect_uri: str) -> dict[str, Any]:
        """Exchange OAuth authorization code for access + refresh tokens."""
        import httpx

        resp = httpx.post(
            "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "scope": "https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/Mail.Send offline_access",
            },
            timeout=30,
        )
        resp.raise_for_status()
        tokens = resp.json()

        self.access_token = tokens.get("access_token")
        self.refresh_token = tokens.get("refresh_token")

        from datetime import timedelta
        expiry = datetime.now(timezone.utc) + timedelta(seconds=tokens.get("expires_in", 3600))

        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expiry": expiry.isoformat(),
        }


@register_adapter("imap")
class IMAPAdapter(BaseConnector):
    """IMAP adapter — BYO work mail with app passwords (no OAuth).

    For non-M365 work mail (self-hosted, Zoho, etc.). Uses IMAP UID SEARCH
    + UID FETCH for incremental sync. UID = idempotency key.

    Gate: connect a real IMAP mailbox → Ask returns source:"imap" with a
    real work email.
    """

    connector_name = "imap"

    def __init__(self) -> None:
        self.host: str | None = None
        self.port: int = 993
        self.username: str | None = None
        self.password: str | None = None

    def load_credentials(self, credentials: dict[str, Any]) -> None:
        self.host = credentials.get("host")
        self.port = credentials.get("port", 993)
        self.username = credentials.get("username")
        self.password = credentials.get("password")

    def load_from_state(self, user_email: str) -> list[Signal]:
        """Bulk load — fetch recent messages via IMAP."""
        if not self.host or not self.username:
            return []

        signals: list[Signal] = []
        try:
            import imaplib
            import email
            from email import policy

            conn = imaplib.IMAP4_SSL(self.host, self.port)
            conn.login(self.username, self.password)
            conn.select("INBOX")

            # Fetch last 50 messages
            _, data = conn.uid("search", None, "ALL")
            uids = data[0].split()[-50:] if data[0] else []

            for uid in uids:
                _, msg_data = conn.uid("fetch", uid, "(RFC822)")
                if msg_data and msg_data[0]:
                    raw = msg_data[0][1]
                    msg = email.message_from_bytes(raw, policy=policy.default)

                    from_header = str(msg.get("From", "unknown"))
                    subject = str(msg.get("Subject", ""))
                    body = self._extract_body(msg)

                    entity = from_header
                    if "<" in from_header:
                        entity = from_header.split("<")[0].strip().strip('"')

                    signals.append(Signal(
                        source="imap",
                        source_id=f"imap:{uid.decode()}",
                        thread_id=str(msg.get("Message-ID", "")),
                        entity=entity,
                        text=f"{subject} — {body[:500]}" if subject else body[:500],
                        timestamp=datetime.now(timezone.utc),
                        direction="inbound",
                        metadata={
                            "source": "imap",
                            "from": from_header,
                            "subject": subject,
                            "uid": uid.decode(),
                        },
                        confidence=0.5,
                    ))

            conn.logout()
            logger.info("IMAPAdapter.load_from_state: %d signals", len(signals))
        except Exception as e:
            logger.error("IMAPAdapter.load_from_state failed: %s", e)

        return signals

    def poll_source(self, user_email: str, cursor: SyncCursor) -> tuple[list[Signal], SyncCursor]:
        """Incremental sync using IMAP UID SEARCH."""
        if not self.host or not self.username:
            return [], cursor

        try:
            import imaplib
            import email
            from email import policy

            uid_next = cursor.cursor_data.get("uid_next", 1)
            conn = imaplib.IMAP4_SSL(self.host, self.port)
            conn.login(self.username, self.password)
            conn.select("INBOX")

            # Search for messages with UID >= uid_next
            _, data = conn.uid("search", None, f"UID {uid_next}:*")
            uids = data[0].split() if data[0] else []

            signals: list[Signal] = []
            for uid in uids:
                uid_int = int(uid)
                if uid_int >= uid_next:
                    _, msg_data = conn.uid("fetch", uid, "(RFC822)")
                    if msg_data and msg_data[0]:
                        raw = msg_data[0][1]
                        msg = email.message_from_bytes(raw, policy=policy.default)

                        from_header = str(msg.get("From", "unknown"))
                        subject = str(msg.get("Subject", ""))
                        body = self._extract_body(msg)

                        entity = from_header
                        if "<" in from_header:
                            entity = from_header.split("<")[0].strip().strip('"')

                        signals.append(Signal(
                            source="imap",
                            source_id=f"imap:{uid.decode()}",
                            thread_id=str(msg.get("Message-ID", "")),
                            entity=entity,
                            text=f"{subject} — {body[:500]}" if subject else body[:500],
                            timestamp=datetime.now(timezone.utc),
                            direction="inbound",
                            metadata={
                                "source": "imap",
                                "from": from_header,
                                "subject": subject,
                                "uid": uid.decode(),
                            },
                            confidence=0.5,
                        ))

                    cursor.cursor_data["uid_next"] = uid_int + 1

            cursor.last_sync = datetime.now(timezone.utc)
            cursor.total_synced += len(signals)
            conn.logout()

            return signals, cursor
        except Exception as e:
            logger.error("IMAPAdapter.poll_source failed: %s", e)
            return [], cursor

    def slim_check(self, user_email: str) -> list[str]:
        return []

    def _extract_body(self, msg) -> str:
        """Extract plain text body from an email message."""
        import re
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    body = part.get_content()
                    return re.sub(r"<[^>]+>", "", str(body))[:500]
        else:
            body = msg.get_content()
            return re.sub(r"<[^>]+>", "", str(body))[:500]
        return ""

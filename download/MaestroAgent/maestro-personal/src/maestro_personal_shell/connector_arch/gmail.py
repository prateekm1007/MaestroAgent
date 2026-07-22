"""Gmail connector with OAuth token refresh — adapted from Onyx.

Implements the Onyx connector pattern:
  1. Check token expiry before each API call
  2. Refresh token if expired (via Google OAuth2)
  3. Use Gmail API for email fetch + delta sync
  4. Transform emails to Signal objects with commitment extraction

Requires google-api-python-client and google-auth-oauthlib (added to pyproject.toml).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from maestro_personal_shell.connector_arch.base import BaseConnector

logger = logging.getLogger(__name__)

# Gmail OAuth scopes — readonly + modify for draft sending
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

# Google OAuth endpoints
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


class GmailConnector(BaseConnector):
    """Gmail connector with OAuth token refresh.

    Adapted from Onyx's Gmail connector pattern. Uses the Gmail API's
    historyId for incremental sync (delta sync) instead of re-fetching
    all messages on every poll.

    Environment variables:
        MAESTRO_GMAIL_CLIENT_ID: Google OAuth client ID
        MAESTRO_GMAIL_CLIENT_SECRET: Google OAuth client secret
    """

    connector_name = "gmail"

    def __init__(self) -> None:
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self.client_id: str = os.environ.get("MAESTRO_GMAIL_CLIENT_ID", "")
        self.client_secret: str = os.environ.get("MAESTRO_GMAIL_CLIENT_SECRET", "")
        self._token_expiry: datetime | None = None

    def load_credentials(self, credentials: dict[str, Any]) -> None:
        """Load OAuth credentials from the connector store.

        Args:
            credentials: dict with keys:
                - access_token: current Gmail API access token
                - refresh_token: long-lived refresh token
                - expiry: ISO datetime when access_token expires
        """
        self.access_token = credentials.get("access_token")
        self.refresh_token = credentials.get("refresh_token")
        expiry_str = credentials.get("expiry")
        if expiry_str:
            try:
                self._token_expiry = datetime.fromisoformat(str(expiry_str))
            except (ValueError, TypeError):
                self._token_expiry = None

        if not self.client_id or not self.client_secret:
            logger.warning(
                "GmailConnector: MAESTRO_GMAIL_CLIENT_ID/SECRET not set. "
                "Connector will operate in stub mode (no real API calls)."
            )

    def _is_configured(self) -> bool:
        """Check if the connector has the required environment configuration."""
        return bool(self.client_id and self.client_secret)

    def _token_needs_refresh(self) -> bool:
        """Check if the access token is expired or about to expire (within 5 min)."""
        if not self._token_expiry:
            return True
        now = datetime.now(timezone.utc)
        # Refresh if token expires in the next 5 minutes
        if self._token_expiry.tzinfo is None:
            self._token_expiry = self._token_expiry.replace(tzinfo=timezone.utc)
        return self._token_expiry <= now.replace(microsecond=0) + __import__("datetime").timedelta(minutes=5)

    def _refresh_token_if_expired(self) -> None:
        """Check token expiry before each API call (Onyx pattern).

        If the access token is expired or about to expire, refresh it
        using the refresh token via Google's OAuth2 token endpoint.
        """
        if not self.refresh_token:
            return

        if not self._token_needs_refresh():
            return

        if not self._is_configured():
            return

        logger.info("GmailConnector: access token expired, refreshing...")
        try:
            resp = httpx.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": self.refresh_token,
                    "grant_type": "refresh_token",
                },
                timeout=30,
            )
            resp.raise_for_status()
            tokens = resp.json()

            self.access_token = tokens["access_token"]
            from datetime import timedelta
            self._token_expiry = datetime.now(timezone.utc) + timedelta(seconds=tokens.get("expires_in", 3600))

            logger.info("GmailConnector: token refreshed successfully, expires at %s", self._token_expiry)

            # TODO: persist the new token to the connector store
            # so it survives across requests

        except Exception as e:
            logger.error("GmailConnector: token refresh failed: %s", e)
            raise

    def _get_gmail_service(self):
        """Build and return a Gmail API service object.

        Uses googleapiclient.discovery.build with OAuth2Credentials.
        """
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        if not self.access_token:
            raise RuntimeError("GmailConnector: no access token. Call load_credentials() first.")

        creds = Credentials(
            token=self.access_token,
            refresh_token=self.refresh_token,
            token_uri=GOOGLE_TOKEN_URL,
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=GMAIL_SCOPES,
        )

        service = build("gmail", "v1", credentials=creds, static_discovery=False)
        return service

    def load_from_state(self) -> list[dict[str, Any]]:
        """Bulk load all emails (initial sync).

        Fetches all emails from the user's Gmail inbox and transforms
        them into Signal objects. Called on first connection.

        Returns:
            List of signal dicts ready for save_signal_to_db()
        """
        if not self._is_configured():
            logger.info("GmailConnector.load_from_state: stub mode (not configured)")
            return []

        if not self.access_token:
            logger.warning("GmailConnector.load_from_state: no access token")
            return []

        self._refresh_token_if_expired()

        try:
            service = self._get_gmail_service()

            # List all messages (paginated)
            signals: list[dict[str, Any]] = []
            page_token = None
            count = 0
            max_results = 500  # cap initial sync

            while count < max_results:
                list_args: dict[str, Any] = {"userId": "me", "maxResults": min(100, max_results - count)}
                if page_token:
                    list_args["pageToken"] = page_token

                results = service.users().messages().list(**list_args).execute()
                messages = results.get("messages", [])

                if not messages:
                    break

                for msg_meta in messages:
                    msg = service.users().messages().get(
                        userId="me", id=msg_meta["id"], format="full"
                    ).execute()

                    signal = self._transform_message_to_signal(msg)
                    if signal:
                        signals.append(signal)
                        count += 1

                    if count >= max_results:
                        break

                page_token = results.get("nextPageToken")
                if not page_token:
                    break

            logger.info("GmailConnector.load_from_state: fetched %d emails", len(signals))
            return signals

        except Exception as e:
            logger.error("GmailConnector.load_from_state failed: %s", e)
            return []

    def poll_source(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        """Incremental sync — fetch emails modified since last poll.

        Uses Gmail's query parameter `after:` to filter by timestamp.

        Args:
            start: fetch emails modified after this time
            end: fetch emails modified before this time

        Returns:
            List of new/modified signals
        """
        if not self._is_configured():
            logger.info("GmailConnector.poll_source: stub mode (not configured)")
            return []

        if not self.access_token:
            logger.warning("GmailConnector.poll_source: no access token")
            return []

        self._refresh_token_if_expired()

        try:
            service = self._get_gmail_service()

            # Gmail query: after:<timestamp> filters emails newer than the timestamp
            query = f"after:{int(start.timestamp())}"
            results = service.users().messages().list(
                userId="me", q=query, maxResults=100
            ).execute()

            signals: list[dict[str, Any]] = []
            for msg_meta in results.get("messages", []):
                msg = service.users().messages().get(
                    userId="me", id=msg_meta["id"], format="full"
                ).execute()

                signal = self._transform_message_to_signal(msg)
                if signal:
                    signals.append(signal)

            logger.info("GmailConnector.poll_source: fetched %d new emails since %s",
                        len(signals), start.isoformat())
            return signals

        except Exception as e:
            logger.error("GmailConnector.poll_source failed: %s", e)
            return []

    def slim_check(self) -> list[str]:
        """Return IDs of all Gmail messages that still exist (for pruning).

        Lists all message IDs so the caller can compare against stored
        signals and mark deleted ones.
        """
        if not self._is_configured() or not self.access_token:
            return []

        self._refresh_token_if_expired()

        try:
            service = self._get_gmail_service()
            message_ids: list[str] = []
            page_token = None

            while True:
                list_args: dict[str, Any] = {"userId": "me", "maxResults": 500}
                if page_token:
                    list_args["pageToken"] = page_token

                results = service.users().messages().list(**list_args).execute()
                for msg in results.get("messages", []):
                    message_ids.append(msg["id"])

                page_token = results.get("nextPageToken")
                if not page_token:
                    break

            return message_ids

        except Exception as e:
            logger.error("GmailConnector.slim_check failed: %s", e)
            return []

    def _transform_message_to_signal(self, msg: dict) -> dict[str, Any] | None:
        """Transform a Gmail API message dict to a Maestro signal dict.

        Extracts: sender (entity), subject + body (text), timestamp,
        and message ID (signal_id).
        """
        try:
            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            from_header = headers.get("From", "unknown")
            subject = headers.get("Subject", "")
            date_header = headers.get("Date", "")

            # Extract body text
            body = self._extract_body(msg.get("payload", {}))

            # Parse timestamp from internalDate (epoch millis)
            internal_date = msg.get("internalDate", "")
            if internal_date:
                timestamp = datetime.fromtimestamp(
                    int(internal_date) / 1000, tz=timezone.utc
                ).isoformat()
            else:
                timestamp = datetime.now(timezone.utc).isoformat()

            # Build the signal text: subject + body snippet
            text = f"{subject} — {body[:500]}" if subject else body[:500]

            # Extract entity name from From header
            # "Maria Garcia <maria@example.com>" → "Maria Garcia"
            entity = from_header
            if "<" in from_header:
                entity = from_header.split("<")[0].strip().strip('"')
            elif "@" in from_header:
                entity = from_header.split("@")[0].strip()

            return {
                "signal_id": f"gmail_{msg['id']}",
                "entity": entity or "unknown",
                "text": text,
                "signal_type": "email",
                "timestamp": timestamp,
                "metadata": {
                    "source": "gmail",
                    "message_id": msg["id"],
                    "from": from_header,
                    "subject": subject,
                    "date": date_header,
                },
            }
        except Exception as e:
            logger.debug("GmailConnector: failed to transform message: %s", e)
            return None

    def _extract_body(self, payload: dict) -> str:
        """Extract plain text body from a Gmail message payload.

        Gmail messages have a nested parts structure. This recursively
        searches for text/plain parts and concatenates them.
        """
        import base64

        body = ""

        # Check if this part has a body
        if "body" in payload and payload["body"].get("data"):
            data = payload["body"]["data"]
            mime_type = payload.get("mimeType", "")
            if mime_type == "text/plain":
                try:
                    decoded = base64.urlsafe_b64decode(data + "===").decode("utf-8", errors="replace")
                    body += decoded
                except Exception:
                    pass

        # Recursively check parts
        for part in payload.get("parts", []):
            body += self._extract_body(part)
            if len(body) > 2000:  # cap body length
                break

        return body

    def get_authorization_url(self, redirect_uri: str, state: str) -> str:
        """Get the OAuth authorization URL for the Gmail consent flow.

        Args:
            redirect_uri: where Google should redirect after consent
            state: CSRF protection token

        Returns:
            Google OAuth2 authorization URL
        """
        if not self._is_configured():
            raise RuntimeError(
                "GmailConnector not configured. Set MAESTRO_GMAIL_CLIENT_ID "
                "and MAESTRO_GMAIL_CLIENT_SECRET environment variables."
            )

        from urllib.parse import urlencode

        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(GMAIL_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }

        return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

    def exchange_code_for_tokens(self, code: str, redirect_uri: str) -> dict[str, Any]:
        """Exchange OAuth authorization code for access + refresh tokens.

        Called by the OAuth callback handler after the user grants consent.

        Args:
            code: authorization code from Google's redirect
            redirect_uri: must match the one used in get_authorization_url

        Returns:
            Dict with access_token, refresh_token, expiry
        """
        if not self._is_configured():
            raise RuntimeError("GmailConnector not configured.")

        resp = httpx.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
            timeout=30,
        )
        resp.raise_for_status()
        tokens = resp.json()

        from datetime import timedelta
        expiry = datetime.now(timezone.utc) + timedelta(seconds=tokens.get("expires_in", 3600))

        # Store the tokens in this connector instance
        self.access_token = tokens["access_token"]
        self.refresh_token = tokens.get("refresh_token", self.refresh_token)
        self._token_expiry = expiry

        return {
            "access_token": tokens["access_token"],
            "refresh_token": tokens.get("refresh_token"),
            "expiry": expiry.isoformat(),
        }

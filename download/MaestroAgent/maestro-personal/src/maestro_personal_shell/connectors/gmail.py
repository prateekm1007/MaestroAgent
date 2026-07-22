"""Gmail connector with OAuth token refresh — adapted from Onyx.

Onyx's Gmail connector pattern:
  1. Check token expiry before each API call
  2. Refresh token if expired (via Google OAuth2)
  3. Use Gmail API's historyId for delta sync (not full re-fetch)
  4. Transform emails to Signal objects with commitment extraction

This implementation provides the structure. The actual Gmail API calls
require google-api-python-client and google-auth, which are not yet
in pyproject.toml. The connector works in "stub mode" until those
dependencies are added — it returns empty lists, which is safe for
the demo environment.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from maestro_personal_shell.connectors.base import BaseConnector, SyncPoint

logger = logging.getLogger(__name__)


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
                self._token_expiry = datetime.fromisoformat(expiry_str)
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

    def _refresh_token_if_expired(self) -> None:
        """Check token expiry before each API call (Onyx pattern).

        If the access token is expired or about to expire, refresh it
        using the refresh token via Google's OAuth2 token endpoint.

        TODO: Implement actual token refresh via httpx POST to
        https://oauth2.googleapis.com/token with grant_type=refresh_token.
        For now, this is a no-op stub.
        """
        if not self._token_expiry:
            return

        now = datetime.now(timezone.utc)
        # Refresh if token expires in the next 5 minutes
        if self._token_expiry <= now:
            logger.info("GmailConnector: access token expired, refreshing...")
            # TODO: Implement token refresh
            # POST https://oauth2.googleapis.com/token
            # Body: client_id, client_secret, refresh_token, grant_type=refresh_token
            # Parse response: access_token, expires_in
            # Update self.access_token and self._token_expiry
            # Persist new token via connector store
            pass

    def load_from_state(self) -> list[dict[str, Any]]:
        """Bulk load all emails (initial sync).

        Fetches all emails from the user's Gmail account and transforms
        them into Signal objects. This is called on first connection.

        TODO: Implement using Gmail API:
        1. List all messages (paginated)
        2. Fetch each message's metadata + body
        3. Transform to Signal dict with entity extraction
        4. Run commitment classifier on each

        Returns:
            List of signal dicts (empty in stub mode)
        """
        if not self._is_configured():
            logger.info("GmailConnector.load_from_state: stub mode (not configured)")
            return []

        self._refresh_token_if_expired()

        # TODO: Implement actual Gmail API fetch
        # from googleapiclient.discovery import build
        # service = build('gmail', 'v1', credentials=...)
        # results = service.users().messages().list(userId='me').execute()
        # ...

        logger.info("GmailConnector.load_from_state: not yet implemented (stub)")
        return []

    def poll_source(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        """Incremental sync — fetch emails modified since last poll.

        Uses Gmail's historyId for delta sync (more efficient than
        re-listing all messages). The historyId is stored in the SyncPoint.

        Args:
            start: fetch emails modified after this time
            end: fetch emails modified before this time

        Returns:
            List of new/modified signals (empty in stub mode)
        """
        if not self._is_configured():
            logger.info("GmailConnector.poll_source: stub mode (not configured)")
            return []

        self._refresh_token_if_expired()

        # TODO: Implement delta sync using Gmail historyId
        # service.users().history().list(userId='me', startHistoryId=...).execute()

        logger.info("GmailConnector.poll_source: not yet implemented (stub)")
        return []

    def slim_check(self) -> list[str]:
        """Return IDs of all Gmail messages that still exist (for pruning).

        TODO: Implement by listing all message IDs and comparing against
        stored signals. Messages that no longer exist in Gmail should be
        marked as deleted in the signal store.

        Returns:
            List of Gmail message IDs (empty in stub mode)
        """
        if not self._is_configured():
            return []

        # TODO: Implement
        return []

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

        scopes = [
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.modify",
        ]

        # Build Google OAuth2 authorization URL
        # https://accounts.google.com/o/oauth2/v2/auth?
        #   client_id=...&redirect_uri=...&response_type=code&
        #   scope=...&access_type=offline&prompt=consent&state=...

        from urllib.parse import urlencode, quote

        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes),
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

        TODO: Implement using httpx POST to https://oauth2.googleapis.com/token
        """
        if not self._is_configured():
            raise RuntimeError("GmailConnector not configured.")

        # TODO: Implement token exchange
        # resp = httpx.post("https://oauth2.googleapis.com/token", data={
        #     "client_id": self.client_id,
        #     "client_secret": self.client_secret,
        #     "code": code,
        #     "grant_type": "authorization_code",
        #     "redirect_uri": redirect_uri,
        # })
        # tokens = resp.json()
        # return {
        #     "access_token": tokens["access_token"],
        #     "refresh_token": tokens.get("refresh_token"),
        #     "expiry": datetime.now(timezone.utc) + timedelta(seconds=tokens["expires_in"]),
        # }

        raise NotImplementedError("Token exchange not yet implemented")

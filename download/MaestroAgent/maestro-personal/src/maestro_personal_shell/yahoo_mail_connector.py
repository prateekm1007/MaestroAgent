"""Yahoo Mail OAuth2 connector — one-click OAuth (replaces IMAP+app-password).

Auditor (2026-07-24) strict-order item 2: "Build the work-email OAuth
redesign — Google / Microsoft / Yahoo as one-click OAuth cards (Yahoo Mail
has an OAuth2 mail scope; the app-password path is the wrong default)".

Yahoo Mail supports OAuth2 via the Yahoo Developer Portal. The mail-ro
scope grants read-only access to a user's mailbox through the Yahoo Mail
API. This connector implements the authorization-code flow:

  1. User clicks "Connect Yahoo" in the UI
  2. We redirect to Yahoo's consent page (mail-ro scope)
  3. Yahoo redirects back with an authorization code
  4. We exchange the code for access + refresh tokens
  5. We use the access token to call the Yahoo Mail API to ingest messages

Configuration (env vars):
  - MAESTRO_YAHOO_CLIENT_ID: Yahoo app client ID
  - MAESTRO_YAHOO_CLIENT_SECRET: Yahoo app client secret
  - MAESTRO_YAHOO_REDIRECT_URI: must be whitelisted in the Yahoo app

When NOT set, is_yahoo_configured() returns False and the connector card
shows a "Not configured" state — no fake "connected" ever.
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Yahoo OAuth2 endpoints (https://developer.yahoo.com/oauth/)
YAHOO_AUTH_URL = "https://api.login.yahoo.com/oauth2/request_auth"
YAHOO_TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"

# Yahoo Mail API base — the /Mail/v1/messages endpoint
YAHOO_MAIL_API_BASE = "https://api.mail.yahoo.com/ws/v3"

# mail-ro = read-only mail access (the auditor-specified scope)
YAHOO_MAIL_SCOPES = ["mail-ro"]


def _get_yahoo_config() -> dict[str, str]:
    """Get Yahoo OAuth2 config from env."""
    return {
        "client_id": os.environ.get("MAESTRO_YAHOO_CLIENT_ID", ""),
        "client_secret": os.environ.get("MAESTRO_YAHOO_CLIENT_SECRET", ""),
        "redirect_uri": os.environ.get(
            "MAESTRO_YAHOO_REDIRECT_URI",
            # Default: same single-callback host as Gmail (uses
            # /api/connectors/yahoo_mail/oauth/callback). Set
            # MAESTRO_YAHOO_REDIRECT_URI explicitly in production.
            "https://maestroagent-production.up.railway.app/api/connectors/yahoo_mail/oauth/callback",
        ),
    }


def is_yahoo_configured() -> bool:
    """Check if real Yahoo Mail OAuth credentials are configured."""
    config = _get_yahoo_config()
    return bool(config["client_id"] and config["client_secret"])


# ---------------------------------------------------------------------------
# Yahoo Mail OAuth2 Client
# ---------------------------------------------------------------------------


class YahooMailOAuthClient:
    """Yahoo Mail OAuth2 authorization-code flow + token refresh.

    Uses urllib (not requests) to avoid a hard dependency — the app works
    in demo mode without Yahoo credentials, and only needs this code path
    when real OAuth is configured.
    """

    def __init__(self):
        self.config = _get_yahoo_config()

    def get_authorization_url(self, state: str = "") -> str:
        """Generate the Yahoo OAuth2 authorization URL."""
        if not self.config["client_id"]:
            raise ValueError(
                "Yahoo OAuth not configured (MAESTRO_YAHOO_CLIENT_ID missing)"
            )

        params = {
            "client_id": self.config["client_id"],
            "redirect_uri": self.config["redirect_uri"],
            "response_type": "code",
            "scope": " ".join(YAHOO_MAIL_SCOPES),
            "state": state,
        }
        return f"{YAHOO_AUTH_URL}?{urlencode(params)}"

    def exchange_code_for_tokens(self, code: str) -> dict[str, Any]:
        """Exchange authorization code for access + refresh tokens.

        Returns: {access_token, refresh_token, expires_in, token_type, expires_at}
        """
        data = urlencode({
            "code": code,
            "client_id": self.config["client_id"],
            "client_secret": self.config["client_secret"],
            "redirect_uri": self.config["redirect_uri"],
            "grant_type": "authorization_code",
        }).encode()

        req = urllib.request.Request(
            YAHOO_TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                token_data = json.loads(resp.read().decode())
                token_data["expires_at"] = (
                    datetime.now(timezone.utc)
                    + timedelta(seconds=token_data.get("expires_in", 3600))
                ).isoformat()
                return token_data
        except Exception as e:
            logger.error("Yahoo OAuth token exchange failed: %s", e)
            return {"error": str(e)}

    def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        """Refresh an expired access token using the refresh token."""
        data = urlencode({
            "client_id": self.config["client_id"],
            "client_secret": self.config["client_secret"],
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }).encode()

        req = urllib.request.Request(
            YAHOO_TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                token_data = json.loads(resp.read().decode())
                token_data["expires_at"] = (
                    datetime.now(timezone.utc)
                    + timedelta(seconds=token_data.get("expires_in", 3600))
                ).isoformat()
                return token_data
        except Exception as e:
            logger.error("Yahoo token refresh failed: %s", e)
            return {"error": str(e)}

    def get_valid_access_token(self, stored_token_json: str) -> tuple[str, str]:
        """Get a valid access token, refreshing if necessary.

        Returns: (access_token, updated_token_json)
        """
        try:
            token_data = json.loads(stored_token_json)
        except Exception:
            return "", stored_token_json

        expires_at_str = token_data.get("expires_at", "")
        if expires_at_str:
            try:
                expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) < (expires_at - timedelta(minutes=5)):
                    return token_data.get("access_token", ""), stored_token_json
            except Exception:
                pass

        refresh_token = token_data.get("refresh_token", "")
        if not refresh_token:
            return "", stored_token_json

        refreshed = self.refresh_access_token(refresh_token)
        if "error" in refreshed:
            return "", stored_token_json

        token_data["access_token"] = refreshed["access_token"]
        token_data["expires_at"] = refreshed["expires_at"]
        updated_json = json.dumps(token_data)
        return token_data["access_token"], updated_json


# ---------------------------------------------------------------------------
# Yahoo Mail API Client (ingestion)
# ---------------------------------------------------------------------------


class YahooMailAPIClient:
    """Calls the Yahoo Mail REST API using an access token."""

    def __init__(self, access_token: str):
        self.access_token = access_token

    def list_messages(self, max_results: int = 50) -> list[dict[str, Any]]:
        """List recent messages. Returns list of message metadata dicts."""
        url = f"{YAHOO_MAIL_API_BASE}/messages?maxResults={max_results}"
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {self.access_token}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
                return data.get("messages", [])
        except Exception as e:
            logger.error("Yahoo Mail list_messages failed: %s", e)
            return []

    def get_message(self, message_id: str) -> dict[str, Any]:
        """Get a single message with body."""
        url = f"{YAHOO_MAIL_API_BASE}/messages/{message_id}"
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {self.access_token}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            logger.error("Yahoo Mail get_message %s failed: %s", message_id, e)
            return {}


# ---------------------------------------------------------------------------
# Yahoo Mail Ingester — pulls messages, extracts commitments
# ---------------------------------------------------------------------------


class YahooMailIngester:
    """Pulls messages from Yahoo Mail and extracts commitments."""

    def __init__(self, access_token: str):
        self.api = YahooMailAPIClient(access_token)

    def ingest_recent(self, max_messages: int = 50) -> dict[str, Any]:
        """Ingest recent messages.

        Returns: {messages_scanned, commitments_found, signals, errors}
        """
        messages = self.api.list_messages(max_results=max_messages)
        commitments_found = 0
        signals: list[dict[str, Any]] = []
        errors: list[str] = []

        for msg_meta in messages:
            try:
                msg_id = msg_meta.get("messageId", "")
                if not msg_id:
                    continue
                msg = self.api.get_message(msg_id)
                if not msg:
                    continue

                body = msg.get("body", "") or msg.get("snippet", "")
                if not body:
                    continue

                from_header = msg.get("from", {}).get("email", "") or str(msg.get("from", ""))
                entity = self._extract_name(from_header)
                timestamp = self._parse_date(msg.get("date", ""))

                # Reuse the same keyword detection as Gmail ingester
                commitments = self._keyword_commitment_detection(body, entity, timestamp)
                for c in commitments:
                    commitments_found += 1
                    signals.append(c)

            except Exception as e:
                errors.append(f"Message {msg_meta}: {e}")

        return {
            "messages_scanned": len(messages),
            "commitments_found": commitments_found,
            "signals": signals,
            "errors": errors,
        }

    def _keyword_commitment_detection(
        self, body: str, entity: str, timestamp: str
    ) -> list[dict[str, Any]]:
        body_lower = body.lower()
        patterns = [
            r"i will (.+?)(?:[.\n]|$)",
            r"i'll (.+?)(?:[.\n]|$)",
            r"i promise to (.+?)(?:[.\n]|$)",
            r"i need to (.+?)(?:[.\n]|$)",
            r"let me (.+?)(?:[.\n]|$)",
            r"i'm going to (.+?)(?:[.\n]|$)",
        ]
        commitments = []
        for pattern in patterns:
            matches = re.findall(pattern, body_lower, re.MULTILINE)
            for match in matches[:2]:
                commitments.append({
                    "entity": entity,
                    "text": match.strip()[:200],
                    "signal_type": "commitment_made",
                    "timestamp": timestamp,
                    "source": "yahoo_mail:inbox",
                })
        return commitments[:5]

    def _extract_name(self, header: str) -> str:
        if not header:
            return ""
        match = re.match(r'"?([^"<]+?)"?\s*<', header)
        if match:
            return match.group(1).strip()
        match = re.match(r"([^\s@]+)@", header)
        if match:
            return match.group(1)
        return header[:50]

    def _parse_date(self, date_str: str) -> str:
        if not date_str:
            return datetime.now(timezone.utc).isoformat()
        try:
            dt = parsedate_to_datetime(date_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except Exception:
            return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Factory — used by ConnectorStore._fetch_messages
# ---------------------------------------------------------------------------


def fetch_real_yahoo_messages(
    stored_token_json: str,
    oauth_client: YahooMailOAuthClient,
    max_messages: int = 50,
) -> tuple[list[dict[str, Any]], str]:
    """Fetch real messages from Yahoo Mail using stored OAuth tokens.

    Returns: (signals, updated_token_json)
    """
    access_token, updated_token_json = oauth_client.get_valid_access_token(stored_token_json)
    if not access_token:
        return [], stored_token_json

    ingester = YahooMailIngester(access_token)
    result = ingester.ingest_recent(max_messages=max_messages)
    return result.get("signals", []), updated_token_json

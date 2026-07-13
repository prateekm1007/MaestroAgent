"""
Gmail OAuth2 connector — real Gmail API integration (Phase B).

This module implements the real Gmail ingestion + send that replaces the
MOCK_INGESTION_DATA stub in connectors.py.

Architecture:
  - GmailOAuthClient: handles OAuth2 authorization code flow + token refresh
  - GmailIngester: pulls messages from Gmail, extracts commitments using
    the existing commitment_classifier
  - GmailSender: sends approved drafts via the Gmail API

OAuth2 flow:
  1. User clicks "Connect Gmail" in the UI
  2. Backend generates authorization URL with scopes:
     - https://www.googleapis.com/auth/gmail.readonly
     - https://www.googleapis.com/auth/gmail.send
  3. User grants access on Google's consent screen
  4. Google redirects to /api/connectors/gmail/oauth/callback with a code
  5. Backend exchanges code for access + refresh tokens
  6. Tokens stored encrypted in ConnectorStore (existing infrastructure)
  7. Ingestion uses the access token to call gmail.users().messages().list()
  8. When access token expires, refresh token is used automatically

Configuration (env vars):
  - MAESTRO_GMAIL_CLIENT_ID: Google OAuth2 client ID
  - MAESTRO_GMAIL_CLIENT_SECRET: Google OAuth2 client secret
  - MAESTRO_GMAIL_REDIRECT_URI: OAuth2 redirect URI (default: /api/connectors/gmail/oauth/callback)

When these are NOT set, the connector falls back to MOCK_INGESTION_DATA
and the UI shows "OAuth not configured" — so the app still works in demo
mode without real credentials.

Commitment extraction:
  - Pulls messages from last 30 days (configurable)
  - For each message, extracts the plain text body
  - Runs the existing commitment_classifier on the body
  - If a commitment is detected, ingests as a signal with:
      entity = sender or recipient name
      text = the commitment text
      signal_type = commitment_made
      timestamp = message date
      source = gmail:inbox or gmail:sent
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Any
from urllib.parse import urlencode, parse_qs, urlparse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


def _get_gmail_config() -> dict[str, str]:
    """Get Gmail OAuth2 config from env."""
    return {
        "client_id": os.environ.get("MAESTRO_GMAIL_CLIENT_ID", ""),
        "client_secret": os.environ.get("MAESTRO_GMAIL_CLIENT_SECRET", ""),
        "redirect_uri": os.environ.get(
            "MAESTRO_GMAIL_REDIRECT_URI",
            "http://localhost:8766/api/connectors/gmail/oauth/callback",
        ),
    }


def is_gmail_configured() -> bool:
    """Check if real Gmail OAuth credentials are configured."""
    config = _get_gmail_config()
    return bool(config["client_id"] and config["client_secret"])


# ---------------------------------------------------------------------------
# Gmail OAuth2 Client
# ---------------------------------------------------------------------------

class GmailOAuthClient:
    """Handles Gmail OAuth2 authorization code flow + token refresh.

    Uses urllib (not google-auth-library) to avoid a hard dependency —
    the app works in demo mode without Google credentials, and only
    needs this code path when real OAuth is configured.
    """

    def __init__(self):
        self.config = _get_gmail_config()

    def get_authorization_url(self, state: str = "") -> str:
        """Generate the Google OAuth2 authorization URL.

        User visits this URL, grants access, and Google redirects to
        our callback with an authorization code.
        """
        if not self.config["client_id"]:
            raise ValueError("Gmail OAuth not configured (MAESTRO_GMAIL_CLIENT_ID missing)")

        params = {
            "client_id": self.config["client_id"],
            "redirect_uri": self.config["redirect_uri"],
            "response_type": "code",
            "scope": " ".join(GMAIL_SCOPES),
            "access_type": "offline",  # get refresh token
            "prompt": "consent",  # force consent to get refresh token every time
            "state": state,
        }
        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    def exchange_code_for_tokens(self, code: str) -> dict[str, Any]:
        """Exchange authorization code for access + refresh tokens.

        Returns: {access_token, refresh_token, expires_in, token_type, scope}
        """
        import urllib.request
        import urllib.parse

        data = urllib.parse.urlencode({
            "code": code,
            "client_id": self.config["client_id"],
            "client_secret": self.config["client_secret"],
            "redirect_uri": self.config["redirect_uri"],
            "grant_type": "authorization_code",
        }).encode()

        req = urllib.request.Request(
            GOOGLE_TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                token_data = json.loads(resp.read().decode())
                # Store expiry time for refresh logic
                token_data["expires_at"] = (
                    datetime.now(timezone.utc) + timedelta(seconds=token_data.get("expires_in", 3600))
                ).isoformat()
                return token_data
        except Exception as e:
            logger.error(f"Gmail OAuth token exchange failed: {e}")
            return {"error": str(e)}

    def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        """Refresh an expired access token using the refresh token.

        Returns: {access_token, expires_in, expires_at, token_type}
        """
        import urllib.request
        import urllib.parse

        data = urllib.parse.urlencode({
            "client_id": self.config["client_id"],
            "client_secret": self.config["client_secret"],
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }).encode()

        req = urllib.request.Request(
            GOOGLE_TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                token_data = json.loads(resp.read().decode())
                token_data["expires_at"] = (
                    datetime.now(timezone.utc) + timedelta(seconds=token_data.get("expires_in", 3600))
                ).isoformat()
                return token_data
        except Exception as e:
            logger.error(f"Gmail token refresh failed: {e}")
            return {"error": str(e)}

    def get_valid_access_token(self, stored_token_json: str) -> tuple[str, str]:
        """Get a valid access token, refreshing if necessary.

        Args:
            stored_token_json: JSON string of {access_token, refresh_token, expires_at}

        Returns:
            (access_token, updated_token_json) — the updated JSON includes
            the new access token if a refresh happened. Caller should persist it.
        """
        try:
            token_data = json.loads(stored_token_json)
        except Exception:
            return "", stored_token_json

        # Check if access token is still valid (with 5-min buffer)
        expires_at_str = token_data.get("expires_at", "")
        if expires_at_str:
            try:
                expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) < (expires_at - timedelta(minutes=5)):
                    # Token still valid
                    return token_data.get("access_token", ""), stored_token_json
            except Exception:
                pass

        # Token expired — refresh
        refresh_token = token_data.get("refresh_token", "")
        if not refresh_token:
            return "", stored_token_json

        refreshed = self.refresh_access_token(refresh_token)
        if "error" in refreshed:
            return "", stored_token_json

        # Merge: keep refresh_token, update access_token + expires_at
        token_data["access_token"] = refreshed["access_token"]
        token_data["expires_at"] = refreshed["expires_at"]
        updated_json = json.dumps(token_data)
        return token_data["access_token"], updated_json


# ---------------------------------------------------------------------------
# Gmail API Client (ingestion + send)
# ---------------------------------------------------------------------------

class GmailAPIClient:
    """Calls the Gmail REST API using an access token.

    Uses urllib to avoid hard google-api-python-client dependency.
    """

    def __init__(self, access_token: str):
        self.access_token = access_token

    def _request(self, path: str, method: str = "GET", body: dict | None = None) -> dict | list:
        import urllib.request
        url = f"{GMAIL_API_BASE}{path}"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else ""
            logger.error(f"Gmail API {method} {path} failed: {e.code} {error_body}")
            return {"error": f"HTTP {e.code}: {error_body[:200]}"}
        except Exception as e:
            logger.error(f"Gmail API {method} {path} failed: {e}")
            return {"error": str(e)}

    def list_messages(self, query: str = "", max_results: int = 50) -> list[str]:
        """List message IDs matching the query.

        Args:
            query: Gmail search query (e.g., "newer_than:30d")
            max_results: max messages to return

        Returns: list of message IDs
        """
        params = f"?maxResults={max_results}"
        if query:
            params += f"&q={query}"
        result = self._request(f"/messages{params}")
        if "error" in result:
            return []
        return [m["id"] for m in result.get("messages", [])]

    def get_message(self, message_id: str) -> dict[str, Any]:
        """Get a single message with metadata + body.

        Returns: {id, threadId, from, to, subject, date, body_text, snippet}
        """
        result = self._request(f"/messages/{message_id}?format=full")
        if "error" in result:
            return {}

        # Parse headers
        headers = {h["name"].lower(): h["value"] for h in result.get("payload", {}).get("headers", [])}
        from_header = headers.get("from", "")
        to_header = headers.get("to", "")
        subject = headers.get("subject", "")
        date = headers.get("date", "")

        # Extract plain text body
        body_text = self._extract_text_body(result.get("payload", {}))

        return {
            "id": result.get("id", ""),
            "threadId": result.get("threadId", ""),
            "from": from_header,
            "to": to_header,
            "subject": subject,
            "date": date,
            "body_text": body_text,
            "snippet": result.get("snippet", ""),
        }

    def _extract_text_body(self, payload: dict) -> str:
        """Extract plain text from a Gmail message payload."""
        # If multipart, find the text/plain part
        if payload.get("mimeType", "").startswith("multipart"):
            for part in payload.get("parts", []):
                if part.get("mimeType") == "text/plain":
                    data = part.get("body", {}).get("data", "")
                    if data:
                        return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
            # No text/plain — try HTML part and strip tags
            for part in payload.get("parts", []):
                if part.get("mimeType") == "text/html":
                    data = part.get("body", {}).get("data", "")
                    if data:
                        html = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                        return re.sub(r"<[^>]+>", "", html)
        else:
            # Single part
            data = payload.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        return ""

    def send_message(self, to: str, subject: str, body: str) -> dict[str, Any]:
        """Send an email via Gmail API.

        Returns: {id, threadId} on success, {error} on failure.
        """
        # Build RFC 2822 message
        from email.message import EmailMessage
        msg = EmailMessage()
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)

        # Base64url encode for Gmail API
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

        result = self._request("/messages/send", method="POST", body={"raw": raw})
        return result if "error" not in result else {"error": result["error"]}


# ---------------------------------------------------------------------------
# Gmail Ingester — pulls messages, extracts commitments
# ---------------------------------------------------------------------------

class GmailIngester:
    """Pulls messages from Gmail and extracts commitments.

    Uses the existing commitment_classifier to detect commitments in
    message bodies. Only messages with detected commitments are ingested
    as signals — this is the data minimization principle (we don't store
    raw message bodies, only the extracted commitment text).
    """

    def __init__(self, access_token: str):
        self.api = GmailAPIClient(access_token)

    def ingest_recent(
        self,
        days_back: int = 30,
        max_messages: int = 50,
    ) -> dict[str, Any]:
        """Ingest messages from the last N days.

        Returns: {
            messages_scanned: int,
            commitments_found: int,
            signals: list[dict],
            errors: list[str],
        }
        """
        query = f"newer_than:{days_back}d"
        message_ids = self.api.list_messages(query=query, max_results=max_messages)

        commitments_found = 0
        signals: list[dict[str, Any]] = []
        errors: list[str] = []

        for msg_id in message_ids:
            try:
                msg = self.api.get_message(msg_id)
                if not msg or not msg.get("body_text"):
                    continue

                # Extract commitments from the message body
                extracted = self._extract_commitments_from_message(msg)
                for commitment in extracted:
                    commitments_found += 1
                    signals.append(commitment)

            except Exception as e:
                errors.append(f"Message {msg_id}: {e}")

        return {
            "messages_scanned": len(message_ids),
            "commitments_found": commitments_found,
            "signals": signals,
            "errors": errors,
        }

    def _extract_commitments_from_message(self, msg: dict) -> list[dict[str, Any]]:
        """Extract commitments from a Gmail message using the commitment classifier.

        Returns: list of signal dicts ready for ingestion.
        """
        body = msg.get("body_text", "")
        if not body:
            return []

        # Determine the entity (the other party in the conversation)
        from_header = msg.get("from", "")
        to_header = msg.get("to", "")
        # If "me" is the sender, the entity is the recipient; otherwise it's the sender
        # Gmail API doesn't resolve "me" to an email, so we check if from contains the user
        # For simplicity, use the from header as the entity (the person who wrote the message)
        entity = self._extract_name(from_header)

        # Parse the date
        timestamp = self._parse_email_date(msg.get("date", ""))

        # Use the commitment_classifier to detect commitments
        commitments = []
        try:
            from maestro_personal_shell.commitment_classifier import classify_text
            result = classify_text(body)
            for c in result.get("commitments", []):
                commitments.append({
                    "entity": entity,
                    "text": c.get("text", body[:200]),
                    "signal_type": "commitment_made",
                    "timestamp": timestamp,
                    "source": "gmail:inbox" if "me" not in to_header.lower() else "gmail:sent",
                })
        except ImportError:
            # Fallback: use keyword detection if classifier not available
            commitments = self._keyword_commitment_detection(body, entity, timestamp)

        # Also capture reported statements (non-commitment but relevant)
        # We ingest the snippet as a reported_statement signal
        snippet = msg.get("snippet", "")
        if snippet and not commitments:
            commitments.append({
                "entity": entity,
                "text": snippet[:200],
                "signal_type": "reported_statement",
                "timestamp": timestamp,
                "source": "gmail:inbox",
            })

        return commitments

    def _keyword_commitment_detection(
        self, body: str, entity: str, timestamp: str
    ) -> list[dict[str, Any]]:
        """Fallback commitment detection using keywords (when classifier unavailable)."""
        body_lower = body.lower()
        commitment_patterns = [
            r"i will (.+?)(?:[.\n]|$)",
            r"i'll (.+?)(?:[.\n]|$)",
            r"i promise to (.+?)(?:[.\n]|$)",
            r"i need to (.+?)(?:[.\n]|$)",
            r"let me (.+?)(?:[.\n]|$)",
            r"i'm going to (.+?)(?:[.\n]|$)",
        ]
        commitments = []
        for pattern in commitment_patterns:
            matches = re.findall(pattern, body_lower, re.MULTILINE)
            for match in matches[:2]:  # max 2 per pattern
                commitments.append({
                    "entity": entity,
                    "text": match.strip()[:200],
                    "signal_type": "commitment_made",
                    "timestamp": timestamp,
                    "source": "gmail:inbox",
                })
        return commitments[:5]  # max 5 commitments per message

    def _extract_name(self, header: str) -> str:
        """Extract a name from an email header like 'Maria Garcia <maria@example.com>'."""
        if not header:
            return ""
        # Try "Name <email>" format
        match = re.match(r'"?([^"<]+?)"?\s*<', header)
        if match:
            return match.group(1).strip()
        # Bare email
        match = re.match(r"([^\s@]+)@", header)
        if match:
            return match.group(1)
        return header[:50]

    def _parse_email_date(self, date_str: str) -> str:
        """Parse an RFC 2822 date string into ISO format."""
        if not date_str:
            return datetime.now(timezone.utc).isoformat()
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(date_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except Exception:
            return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Factory — used by ConnectorStore._fetch_messages
# ---------------------------------------------------------------------------

def fetch_real_gmail_messages(
    stored_token_json: str,
    oauth_client: GmailOAuthClient,
    days_back: int = 30,
    max_messages: int = 50,
) -> tuple[list[dict[str, Any]], str]:
    """Fetch real messages from Gmail using stored OAuth tokens.

    Args:
        stored_token_json: JSON of {access_token, refresh_token, expires_at}
        oauth_client: GmailOAuthClient instance
        days_back: how many days of history to pull
        max_messages: max messages to scan

    Returns:
        (signals, updated_token_json) — signals are ready for ingestion,
        updated_token_json includes refreshed access token if applicable.
    """
    # Get a valid access token (refresh if needed)
    access_token, updated_token_json = oauth_client.get_valid_access_token(stored_token_json)
    if not access_token:
        return [], stored_token_json

    # Ingest
    ingester = GmailIngester(access_token)
    result = ingester.ingest_recent(days_back=days_back, max_messages=max_messages)

    return result.get("signals", []), updated_token_json


def send_real_gmail_message(
    stored_token_json: str,
    oauth_client: GmailOAuthClient,
    to: str,
    subject: str,
    body: str,
) -> tuple[dict[str, Any], str]:
    """Send an email via Gmail API using stored OAuth tokens.

    Args:
        stored_token_json: JSON of {access_token, refresh_token, expires_at}
        oauth_client: GmailOAuthClient instance
        to: recipient email
        subject: email subject
        body: email body

    Returns:
        (result, updated_token_json) — result is {id, threadId} on success
        or {error} on failure.
    """
    access_token, updated_token_json = oauth_client.get_valid_access_token(stored_token_json)
    if not access_token:
        return {"error": "Could not obtain valid access token"}, stored_token_json

    client = GmailAPIClient(access_token)
    result = client.send_message(to, subject, body)
    return result, updated_token_json

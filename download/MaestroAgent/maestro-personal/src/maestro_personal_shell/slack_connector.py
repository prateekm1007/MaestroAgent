"""
Slack OAuth2 connector — real Slack API integration (Phase C).

Same pattern as gmail_connector.py (Phase B):
  - SlackOAuthClient: OAuth2 authorization code flow + token refresh
  - SlackAPIClient: Slack Web API calls (conversations.history, im.history, chat.postMessage)
  - SlackIngester: pulls DMs + channel mentions, extracts commitments

OAuth2 flow:
  1. User clicks "Connect Slack" in the UI
  2. Backend generates authorization URL with scopes:
     - channels:read (list public channels)
     - groups:read (list private channels the user is in)
     - im:read (DMs)
     - im:history (DM message history)
     - chat:write (send messages)
  3. User grants access on Slack's consent screen
  4. Slack redirects to /api/connectors/slack/oauth/callback with a code
  5. Backend exchanges code for access token
  6. Token stored encrypted in ConnectorStore (existing infrastructure)
  7. Ingestion uses the access token to call conversations.history() + im.history()
  8. Send uses chat.postMessage()

Configuration (env vars):
  - MAESTRO_SLACK_CLIENT_ID: Slack app client ID
  - MAESTRO_SLACK_CLIENT_SECRET: Slack app client secret
  - MAESTRO_SLACK_REDIRECT_URI: OAuth2 redirect URI

When these are NOT set, the connector falls back to MOCK_INGESTION_DATA
and the UI shows "OAuth not configured" — so the app still works in demo
mode without real credentials.

Commitment extraction:
  - Pulls DMs from last 30 days (configurable)
  - For each message, extracts the plain text
  - Runs keyword commitment detection on the text
  - If a commitment is detected, ingests as a signal with:
      entity = sender name
      text = the commitment text
      signal_type = commitment_made
      timestamp = message timestamp
      source = slack:dm or slack:channel
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Any
from urllib.parse import urlencode
from email.utils import parsedate_to_datetime

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SLACK_SCOPES = [
    "channels:read",
    "groups:read",
    "im:read",
    "im:history",
    "chat:write",
]

SLACK_AUTH_URL = "https://slack.com/oauth/v2/authorize"
SLACK_TOKEN_URL = "https://slack.com/api/oauth.v2.access"
SLACK_API_BASE = "https://slack.com/api"


def _get_slack_config() -> dict[str, str]:
    """Get Slack OAuth2 config from env."""
    return {
        "client_id": os.environ.get("MAESTRO_SLACK_CLIENT_ID", ""),
        "client_secret": os.environ.get("MAESTRO_SLACK_CLIENT_SECRET", ""),
        "redirect_uri": os.environ.get(
            "MAESTRO_SLACK_REDIRECT_URI",
            "http://localhost:8766/api/connectors/slack/oauth/callback",
        ),
    }


def is_slack_configured() -> bool:
    """Check if real Slack OAuth credentials are configured."""
    config = _get_slack_config()
    return bool(config["client_id"] and config["client_secret"])


# ---------------------------------------------------------------------------
# Slack OAuth2 Client
# ---------------------------------------------------------------------------

class SlackOAuthClient:
    """Handles Slack OAuth2 authorization code flow + token refresh.

    Uses urllib (not slack_sdk) to avoid a hard dependency —
    the app works in demo mode without Slack credentials.
    """

    def __init__(self):
        self.config = _get_slack_config()

    def get_authorization_url(self, state: str = "") -> str:
        """Generate the Slack OAuth2 authorization URL."""
        if not self.config["client_id"]:
            raise ValueError("Slack OAuth not configured (MAESTRO_SLACK_CLIENT_ID missing)")

        params = {
            "client_id": self.config["client_id"],
            "redirect_uri": self.config["redirect_uri"],
            "response_type": "code",
            "scope": ",".join(SLACK_SCOPES),
            "state": state,
        }
        return f"{SLACK_AUTH_URL}?{urlencode(params)}"

    def exchange_code_for_tokens(self, code: str) -> dict[str, Any]:
        """Exchange authorization code for an access token.

        Slack returns a bot token (xoxb-) + optional user token (xoxp-).
        We store the access token for API calls.

        Returns: {access_token, token_type, scope, bot_user_id, ...}
        """
        import urllib.request
        import urllib.parse

        data = urllib.parse.urlencode({
            "code": code,
            "client_id": self.config["client_id"],
            "client_secret": self.config["client_secret"],
            "redirect_uri": self.config["redirect_uri"],
        }).encode()

        req = urllib.request.Request(
            SLACK_TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                token_data = json.loads(resp.read().decode())
                if not token_data.get("ok"):
                    return {"error": token_data.get("error", "unknown_slack_error")}
                # Slack tokens don't expire by default, but we store an expiry
                # for consistency with the Gmail pattern (far future)
                token_data["expires_at"] = (
                    datetime.now(timezone.utc) + timedelta(days=365)
                ).isoformat()
                return token_data
        except Exception as e:
            logger.error(f"Slack OAuth token exchange failed: {e}")
            return {"error": str(e)}

    def get_valid_access_token(self, stored_token_json: str) -> tuple[str, str]:
        """Get a valid access token.

        Slack tokens don't expire by default (no refresh needed), but we
        keep this method for interface consistency with GmailOAuthClient.

        Returns: (access_token, unchanged_token_json)
        """
        try:
            token_data = json.loads(stored_token_json)
        except Exception:
            return "", stored_token_json

        access_token = token_data.get("access_token", "")
        if not access_token:
            return "", stored_token_json

        return access_token, stored_token_json


# ---------------------------------------------------------------------------
# Slack API Client (ingestion + send)
# ---------------------------------------------------------------------------

class SlackAPIClient:
    """Calls the Slack Web API using an access token.

    Uses urllib to avoid hard slack_sdk dependency.
    """

    def __init__(self, access_token: str):
        self.access_token = access_token

    def _request(self, method_name: str, params: dict | None = None) -> dict:
        """Call a Slack Web API method.

        Slack uses POST with form-encoded params for most methods.
        Returns the parsed JSON response.
        """
        import urllib.request
        import urllib.parse

        url = f"{SLACK_API_BASE}/{method_name}"
        data = urllib.parse.urlencode(params or {}).encode()
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode())
                if not result.get("ok"):
                    return {"error": result.get("error", "unknown_error")}
                return result
        except Exception as e:
            logger.error(f"Slack API {method_name} failed: {e}")
            return {"error": str(e)}

    def list_dm_channels(self, limit: int = 50) -> list[str]:
        """List DM channel IDs for the user.

        Returns: list of channel IDs (DMs)
        """
        result = self._request("conversations.list", {
            "types": "im",  # DMs only
            "limit": str(limit),
        })
        if "error" in result:
            return []
        return [ch["id"] for ch in result.get("channels", [])]

    def get_dm_history(self, channel_id: str, oldest: str = "", limit: int = 50) -> list[dict]:
        """Get message history for a DM channel.

        Args:
            channel_id: the DM channel ID
            oldest: Unix timestamp (as string) — only messages after this
            limit: max messages to return

        Returns: list of message dicts {text, user, ts}
        """
        params = {"channel": channel_id, "limit": str(limit)}
        if oldest:
            params["oldest"] = oldest
        result = self._request("conversations.history", params)
        if "error" in result:
            return []
        return result.get("messages", [])

    def get_user_info(self, user_id: str) -> dict[str, str]:
        """Get user info (name, real_name, email) by user ID."""
        result = self._request("users.info", {"user": user_id})
        if "error" in result:
            return {"name": user_id, "real_name": user_id}
        user = result.get("user", {})
        return {
            "name": user.get("name", user_id),
            "real_name": user.get("real_name", user.get("name", user_id)),
            "email": user.get("profile", {}).get("email", ""),
        }

    def send_message(self, channel: str, text: str) -> dict[str, Any]:
        """Send a message to a channel or DM.

        Returns: {ok, channel, ts, message} on success, {error} on failure.
        """
        result = self._request("chat.postMessage", {
            "channel": channel,
            "text": text,
        })
        return result


# ---------------------------------------------------------------------------
# Slack Ingester — pulls messages, extracts commitments
# ---------------------------------------------------------------------------

class SlackIngester:
    """Pulls DMs from Slack and extracts commitments.

    Same data-minimization principle as Gmail: extracts commitments only,
    doesn't store raw message bodies.
    """

    def __init__(self, access_token: str):
        self.api = SlackAPIClient(access_token)
        # Cache user info to avoid repeated API calls
        self._user_cache: dict[str, dict[str, str]] = {}

    def ingest_recent(
        self,
        days_back: int = 30,
        max_channels: int = 20,
        max_messages_per_channel: int = 50,
    ) -> dict[str, Any]:
        """Ingest DMs from the last N days.

        Returns: {
            channels_scanned: int,
            messages_scanned: int,
            commitments_found: int,
            signals: list[dict],
            errors: list[str],
        }
        """
        # Calculate oldest timestamp (Slack uses Unix epoch as string)
        oldest = str((datetime.now(timezone.utc) - timedelta(days=days_back)).timestamp())

        dm_channels = self.api.list_dm_channels(limit=max_channels)

        commitments_found = 0
        messages_scanned = 0
        signals: list[dict[str, Any]] = []
        errors: list[str] = []

        for channel_id in dm_channels:
            try:
                messages = self.api.get_dm_history(channel_id, oldest=oldest, limit=max_messages_per_channel)
                messages_scanned += len(messages)

                for msg in messages:
                    extracted = self._extract_commitments_from_message(msg)
                    for commitment in extracted:
                        commitments_found += 1
                        signals.append(commitment)
            except Exception as e:
                errors.append(f"Channel {channel_id}: {e}")

        return {
            "channels_scanned": len(dm_channels),
            "messages_scanned": messages_scanned,
            "commitments_found": commitments_found,
            "signals": signals,
            "errors": errors,
        }

    def _extract_commitments_from_message(self, msg: dict) -> list[dict[str, Any]]:
        """Extract commitments from a Slack message.

        Returns: list of signal dicts ready for ingestion.
        """
        text = msg.get("text", "")
        if not text:
            return []

        # Strip Slack mentions (<@U12345> → name)
        text_clean = self._strip_mentions(text)
        if not text_clean.strip():
            return []

        # Get the sender's name
        user_id = msg.get("user", "")
        entity = self._get_user_name(user_id)

        # Parse timestamp (Slack uses Unix epoch as string)
        timestamp = self._parse_slack_ts(msg.get("ts", ""))

        # Keyword commitment detection (same patterns as Gmail)
        commitments = self._keyword_commitment_detection(text_clean, entity, timestamp)

        # If no commitment but message is substantive, capture as reported_statement
        if not commitments and len(text_clean) > 20:
            commitments.append({
                "entity": entity,
                "text": text_clean[:200],
                "signal_type": "reported_statement",
                "timestamp": timestamp,
                "source": "slack:dm",
            })

        return commitments

    def _strip_mentions(self, text: str) -> str:
        """Replace Slack <@U12345> mentions with plain text."""
        def replace_mention(match):
            user_id = match.group(1)
            name = self._get_user_name(user_id)
            return f"@{name}"

        return re.sub(r"<@([UW][A-Z0-9]+)>", replace_mention, text)

    def _get_user_name(self, user_id: str) -> str:
        """Get a user's name, with caching."""
        if not user_id:
            return "unknown"
        if user_id in self._user_cache:
            return self._user_cache[user_id].get("real_name", user_id)

        info = self.api.get_user_info(user_id)
        self._user_cache[user_id] = info
        return info.get("real_name", user_id)

    def _keyword_commitment_detection(
        self, body: str, entity: str, timestamp: str
    ) -> list[dict[str, Any]]:
        """Commitment detection using keywords (same as Gmail fallback)."""
        body_lower = body.lower()
        commitment_patterns = [
            r"i will (.+?)(?:[.\n!?]|$)",
            r"i'll (.+?)(?:[.\n!?]|$)",
            r"i promise to (.+?)(?:[.\n!?]|$)",
            r"i need to (.+?)(?:[.\n!?]|$)",
            r"let me (.+?)(?:[.\n!?]|$)",
            r"i'm going to (.+?)(?:[.\n!?]|$)",
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
                    "source": "slack:dm",
                })
        return commitments[:5]  # max 5 commitments per message

    def _parse_slack_ts(self, ts: str) -> str:
        """Parse a Slack timestamp (Unix epoch as string) into ISO format."""
        if not ts:
            return datetime.now(timezone.utc).isoformat()
        try:
            # Slack ts is like "1625000000.000123"
            epoch = float(ts)
            return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
        except Exception:
            return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Factory — used by ConnectorStore._fetch_messages
# ---------------------------------------------------------------------------

def fetch_real_slack_messages(
    stored_token_json: str,
    oauth_client: SlackOAuthClient,
    days_back: int = 30,
) -> tuple[list[dict[str, Any]], str]:
    """Fetch real messages from Slack using stored OAuth tokens.

    Args:
        stored_token_json: JSON of {access_token, ...}
        oauth_client: SlackOAuthClient instance
        days_back: how many days of history to pull

    Returns:
        (signals, updated_token_json) — signals are ready for ingestion,
        updated_token_json is unchanged (Slack tokens don't expire).
    """
    access_token, updated_token_json = oauth_client.get_valid_access_token(stored_token_json)
    if not access_token:
        return [], stored_token_json

    ingester = SlackIngester(access_token)
    result = ingester.ingest_recent(days_back=days_back)

    return result.get("signals", []), updated_token_json


def send_real_slack_message(
    stored_token_json: str,
    oauth_client: SlackOAuthClient,
    channel: str,
    text: str,
) -> tuple[dict[str, Any], str]:
    """Send a message via Slack API using stored OAuth tokens.

    Args:
        stored_token_json: JSON of {access_token, ...}
        oauth_client: SlackOAuthClient instance
        channel: channel ID or DM channel ID
        text: message text

    Returns:
        (result, updated_token_json) — result is {ok, ts, channel} on success
        or {error} on failure.
    """
    access_token, updated_token_json = oauth_client.get_valid_access_token(stored_token_json)
    if not access_token:
        return {"error": "Could not obtain valid access token"}, stored_token_json

    client = SlackAPIClient(access_token)
    result = client.send_message(channel, text)
    return result, updated_token_json

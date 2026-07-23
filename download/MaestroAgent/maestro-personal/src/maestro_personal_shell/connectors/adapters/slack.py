"""Slack adapter — T1 connector with OAuth + conversations.history poll.

Slack has the highest commitment density of any platform ("I'll have the PR up
by EOD", "@here standup at 10", thread resolutions). This adapter wraps the
existing slack_connector.py in the BaseConnector pattern.

Realtime: Socket Mode (websocket, no public URL needed — great for Railway).
Outbound: chat.postMessage (for draft sending).

Gate (definition of done): connect a real Slack workspace → Ask "what did I
promise in #eng?" returns source:"slack" with a real message you recognize.
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


@register_adapter("slack")
class SlackAdapter(BaseConnector):
    """Slack connector using OAuth2 + conversations.history.

    Scopes: channels:history, groups:history, im:history, mpim:history,
            users:read, reactions:read
    Cursor: {channel_id: latest_ts} per channel
    Idempotency: f"{channel_id}:{message_ts}"
    """

    connector_name = "slack"

    def __init__(self) -> None:
        self.access_token: str | None = None
        self.bot_token: str | None = None
        self.client_id: str = os.environ.get("MAESTRO_SLACK_CLIENT_ID", "")
        self.client_secret: str = os.environ.get("MAESTRO_SLACK_CLIENT_SECRET", "")

    def load_credentials(self, credentials: dict[str, Any]) -> None:
        self.access_token = credentials.get("access_token")
        self.bot_token = credentials.get("bot_token", self.access_token)

    def _is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _get_client(self):
        """Get a SlackAPIClient from the existing slack_connector module."""
        from maestro_personal_shell.slack_connector import SlackAPIClient
        if not self.access_token:
            raise RuntimeError("SlackAdapter: no access token. Call load_credentials() first.")
        return SlackAPIClient(self.access_token)

    def load_from_state(self, user_email: str) -> list[Signal]:
        """Bulk load — fetch recent messages from all channels."""
        if not self.access_token:
            logger.info("SlackAdapter.load_from_state: no access token")
            return []

        try:
            from maestro_personal_shell.slack_connector import (
                fetch_real_slack_messages, SlackOAuthClient,
            )
            # Use the existing ingester to fetch messages
            client = self._get_client()
            messages = client.list_channels()
            signals: list[Signal] = []

            for channel in messages[:10]:  # cap at 10 channels for initial sync
                channel_id = channel.get("id", "")
                channel_name = channel.get("name", "")
                history = client.get_channel_history(channel_id, limit=50)

                for msg in history:
                    sig = self._message_to_signal(msg, channel_id, channel_name)
                    if sig:
                        signals.append(sig)

            logger.info("SlackAdapter.load_from_state: fetched %d signals from %d channels",
                        len(signals), len(messages))
            return signals
        except Exception as e:
            logger.error("SlackAdapter.load_from_state failed: %s", e)
            return []

    def poll_source(self, user_email: str, cursor: SyncCursor) -> tuple[list[Signal], SyncCursor]:
        """Incremental sync — fetch only new messages since the cursor."""
        if not self.access_token:
            return [], cursor

        try:
            client = self._get_client()
            channels = client.list_channels()
            signals: list[Signal] = []
            cursor_data = dict(cursor.cursor_data)

            for channel in channels:
                channel_id = channel.get("id", "")
                channel_name = channel.get("name", "")
                latest_ts = cursor_data.get(channel_id, "0")

                history = client.get_channel_history(channel_id, oldest=latest_ts, limit=200)

                for msg in history:
                    msg_ts = msg.get("ts", "")
                    if msg_ts > latest_ts:
                        latest_ts = msg_ts

                    sig = self._message_to_signal(msg, channel_id, channel_name)
                    if sig:
                        signals.append(sig)

                cursor_data[channel_id] = latest_ts

            cursor.cursor_data = cursor_data
            cursor.last_sync = datetime.now(timezone.utc)
            cursor.total_synced += len(signals)

            logger.info("SlackAdapter.poll_source: %d new signals from %d channels",
                        len(signals), len(channels))
            return signals, cursor
        except Exception as e:
            logger.error("SlackAdapter.poll_source failed: %s", e)
            return [], cursor

    def slim_check(self, user_email: str) -> list[str]:
        """Return IDs of all Slack messages that still exist."""
        if not self.access_token:
            return []

        try:
            client = self._get_client()
            channels = client.list_channels()
            ids: list[str] = []

            for channel in channels:
                channel_id = channel.get("id", "")
                history = client.get_channel_history(channel_id, limit=1000)
                for msg in history:
                    ids.append(f"{channel_id}:{msg.get('ts', '')}")

            return ids
        except Exception as e:
            logger.error("SlackAdapter.slim_check failed: %s", e)
            return []

    def _message_to_signal(self, msg: dict, channel_id: str, channel_name: str) -> Signal | None:
        """Convert a Slack message dict to a Signal."""
        try:
            text = msg.get("text", "")
            if not text or msg.get("subtype") in ("bot_message", "channel_join", "channel_leave"):
                return None

            ts = msg.get("ts", "")
            user_id = msg.get("user", "")
            thread_ts = msg.get("thread_ts")

            # Resolve user ID to name (cached in the client)
            entity = f"Slack user {user_id}"
            try:
                client = self._get_client()
                user_info = client.get_user_info(user_id)
                if user_info:
                    entity = user_info.get("real_name", user_info.get("name", entity))
            except Exception:
                pass

            return Signal(
                source="slack",
                source_id=f"{channel_id}:{ts}",
                thread_id=f"{channel_id}:{thread_ts}" if thread_ts else f"{channel_id}:{ts}",
                entity=entity,
                text=text,
                timestamp=datetime.fromtimestamp(float(ts), tz=timezone.utc) if ts else datetime.now(timezone.utc),
                direction="outbound" if msg.get("bot_id") else "inbound",
                metadata={
                    "source": "slack",
                    "channel": channel_name,
                    "channel_id": channel_id,
                    "user_id": user_id,
                    "thread_ts": thread_ts,
                },
                confidence=0.5,
            )
        except Exception as e:
            logger.debug("SlackAdapter._message_to_signal failed: %s", e)
            return None

    def get_authorization_url(self, redirect_uri: str, state: str) -> str:
        """Get the Slack OAuth2 authorization URL."""
        from urllib.parse import urlencode

        scopes = [
            "channels:history", "groups:history", "im:history", "mpim:history",
            "users:read", "reactions:read", "channels:read", "groups:read",
        ]

        params = {
            "client_id": self.client_id,
            "scope": " ".join(scopes),
            "redirect_uri": redirect_uri,
            "state": state,
        }

        return f"https://slack.com/oauth/v2/authorize?{urlencode(params)}"

    def exchange_code_for_tokens(self, code: str, redirect_uri: str) -> dict[str, Any]:
        """Exchange OAuth authorization code for access token."""
        import httpx

        resp = httpx.post(
            "https://slack.com/api/oauth.v2.access",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        if not data.get("ok"):
            raise RuntimeError(f"Slack OAuth failed: {data.get('error', 'unknown')}")

        self.access_token = data.get("access_token")
        self.bot_token = data.get("bot_token", self.access_token)

        return {
            "access_token": self.access_token,
            "bot_token": self.bot_token,
            "team": data.get("team", {}).get("name", ""),
            "user": data.get("authed_user", {}).get("name", ""),
        }

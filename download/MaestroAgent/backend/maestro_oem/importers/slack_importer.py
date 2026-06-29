"""
Slack historical importer.

Fetches:
  - Channel list (public + private the bot is in)
  - Messages per channel (cursor pagination via conversations.history)
  - Thread replies (via conversations.replies)
  - Reactions

Pagination:
  - Slack uses cursor-based pagination with `next_cursor` in response.metadata
  - has_more flag indicates end
  - Page size: 200 (max for conversations.history)

Rate limits:
  - Tier 2: 20+/min for most methods
  - Tier 3: 50+/min for conversations.history
  - Retry-After header on 429

OAuth scopes:
  - channels:history, channels:read
  - groups:history, groups:read
  - im:history, im:read
  - mpim:history, mpim:read
  - users:read, team:read
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from maestro_oem.importers.base import BaseProviderFetcher
from maestro_oem.ingestion import PageResult, PageStatus
from maestro_oem.oauth_manager import OAuthError

logger = logging.getLogger(__name__)

SLACK_API = "https://slack.com/api"


class SlackPageFetcher(BaseProviderFetcher):
    """Fetches Slack messages across all channels the bot can see.

    org_id is the Slack team_id (optional — auto-detected from auth.test).
    """

    provider = "slack"
    base_url = SLACK_API
    page_size = 200

    def __init__(
        self,
        oauth,
        http_client: httpx.AsyncClient | None = None,
        page_size: int | None = None,
        org_id: str | None = None,
    ) -> None:
        super().__init__(oauth, http_client, page_size, org_id)
        self._channels: list[dict[str, Any]] | None = None
        self._users: dict[str, str] | None = None  # user_id → email

    # ─── Discovery ───

    async def _discover_channels(self) -> list[dict[str, Any]]:
        if self._channels is not None:
            return self._channels
        channels: list[dict[str, Any]] = []
        cursor = ""
        while True:
            params: dict[str, Any] = {"limit": 200, "types": "public_channel,private_channel"}
            if cursor:
                params["cursor"] = cursor
            try:
                resp = await self._request("GET", f"{SLACK_API}/conversations.list", params=params)
            except Exception as e:
                logger.warning("Slack channel discovery failed: %s", e)
                break
            if resp.status_code != 200:
                break
            data = resp.json()
            if not data.get("ok"):
                logger.warning("Slack conversations.list error: %s", data.get("error"))
                break
            channels.extend(data.get("channels", []))
            cursor = data.get("response_metadata", {}).get("next_cursor", "")
            if not cursor or not data.get("channels"):
                break
        self._channels = channels
        logger.info("Discovered %d Slack channels", len(channels))
        return channels

    async def _get_user_email(self, user_id: str) -> str:
        if self._users is None:
            self._users = {}
            cursor = ""
            while True:
                params: dict[str, Any] = {"limit": 200}
                if cursor:
                    params["cursor"] = cursor
                try:
                    resp = await self._request("GET", f"{SLACK_API}/users.list", params=params)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("ok"):
                            for u in data.get("members", []):
                                email = (u.get("profile") or {}).get("email")
                                if email:
                                    self._users[u["id"]] = email
                            cursor = data.get("response_metadata", {}).get("next_cursor", "")
                            if not cursor:
                                break
                            continue
                except Exception as e:
                    logger.warning("Slack users.list failed: %s", e)
                    break
                break
        return self._users.get(user_id, f"{user_id}@slack.local")

    # ─── PageFetcher interface ───

    async def estimate_total_pages(self, since: datetime | None = None) -> int:
        channels = await self._discover_channels()
        # ~50 pages per channel (Slack has high throughput)
        return max(1, len(channels) * 50)

    async def fetch_page(
        self,
        page: int = 1,
        cursor: str = "",
        since: datetime | None = None,
    ) -> PageResult:
        """Fetch one page of Slack messages.

        Cursor format: "<channel_idx>:<next_cursor>:<oldest_ts>"
        """
        channels = await self._discover_channels()
        if not channels:
            return PageResult(page_number=page, status=PageStatus.SUCCESS, items=[], items_count=0)

        # Parse cursor
        try:
            parts = cursor.split(":", 2)
            channel_idx = int(parts[0]) if parts[0] else 0
            next_cursor = parts[1] if len(parts) > 1 else ""
            oldest_ts = parts[2] if len(parts) > 2 else ""
        except (ValueError, IndexError):
            channel_idx, next_cursor, oldest_ts = 0, "", ""

        if channel_idx >= len(channels):
            return PageResult(page_number=page, status=PageStatus.SUCCESS, items=[], items_count=0)

        if since and not oldest_ts:
            oldest_ts = str(since.timestamp())

        channel = channels[channel_idx]
        channel_id = channel["id"]

        params: dict[str, Any] = {"channel": channel_id, "limit": self.page_size}
        if next_cursor:
            params["cursor"] = next_cursor
        if oldest_ts:
            params["oldest"] = oldest_ts

        try:
            resp = await self._request("GET", f"{SLACK_API}/conversations.history", params=params)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                return self._rate_limited_result(e.response, page)
            return self._error_result(page, f"Slack HTTP {e.response.status_code}: {e}")
        except Exception as e:
            return self._error_result(page, str(e))

        if resp.status_code == 429:
            return self._rate_limited_result(resp, page)
        if resp.status_code != 200:
            return self._error_result(page, f"Slack {resp.status_code}")

        data = resp.json()
        if not data.get("ok"):
            error = data.get("error", "unknown")
            if error == "ratelimited":
                return self._rate_limited_result(resp, page)
            return self._error_result(page, f"Slack API error: {error}")

        messages = data.get("messages", [])
        has_more = data.get("has_more", False)
        new_cursor = data.get("response_metadata", {}).get("next_cursor", "")

        items: list[dict[str, Any]] = []
        for msg in messages:
            user_id = msg.get("user", msg.get("bot_id", "unknown"))
            actor_email = await self._get_user_email(user_id)
            items.append({
                "event_type": "message",
                "channel": channel.get("name", channel_id),
                "actor": actor_email,
                "artifact": f"slack:{channel_id}/p{msg.get('ts', '').replace('.', '')}",
                "timestamp": datetime.fromtimestamp(
                    float(msg.get("ts", 0)), tz=timezone.utc
                ).isoformat(),
                "metadata": {
                    "text": (msg.get("text", "") or "")[:1000],
                    "participants": [actor_email],
                    "thread_ts": msg.get("thread_ts"),
                    "reactions": [r.get("name") for r in msg.get("reactions", [])],
                    "channel_id": channel_id,
                },
            })

        # Build next cursor
        if has_more and new_cursor:
            next_cursor_str = f"{channel_idx}:{new_cursor}:{oldest_ts}"
        elif channel_idx + 1 < len(channels):
            # Move to next channel
            next_cursor_str = f"{channel_idx + 1}::{oldest_ts}"
        else:
            next_cursor_str = ""

        return PageResult(
            page_number=page,
            status=PageStatus.SUCCESS,
            items=items,
            items_count=len(items),
            next_cursor=next_cursor_str,
            rate_limit_remaining=None,
        )

    def normalize_item(self, item: dict[str, Any]) -> dict[str, Any]:
        return item

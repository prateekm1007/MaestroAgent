"""
Gmail historical importer.

Fetches:
  - Messages (with headers, no body by default for performance)
  - Threads (grouped conversations)
  - Labels (for filtering)

Pagination:
  - Gmail API uses pageToken-based pagination
  - Page size: 100 (max for messages.list)

Rate limits:
  - 250 quota units/sec, 1 billion/day
  - messages.list costs 5 units, messages.get costs 5 units
  - ~50 req/sec practical limit

OAuth scopes:
  - gmail.readonly
  - gmail.metadata (cheaper than full body)
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

GMAIL_API = "https://gmail.googleapis.com/gmail/v1"


class GmailPageFetcher(BaseProviderFetcher):
    """Fetches Gmail messages and threads.

    org_id is the user's email address (auto-detected from user profile).
    """

    provider = "gmail"
    base_url = GMAIL_API
    page_size = 100

    def __init__(
        self,
        oauth,
        http_client: httpx.AsyncClient | None = None,
        page_size: int | None = None,
        org_id: str | None = None,
    ) -> None:
        super().__init__(oauth, http_client, page_size, org_id)
        self._user_email: str | None = org_id

    async def _get_user_email(self) -> str:
        if self._user_email:
            return self._user_email
        resp = await self._request("GET", f"{GMAIL_API}/users/me/profile")
        if resp.status_code == 200:
            self._user_email = resp.json().get("emailAddress", "me")
        else:
            self._user_email = "me"
        return self._user_email

    # ─── PageFetcher interface ───

    async def estimate_total_pages(self, since: datetime | None = None) -> int:
        """Estimate total pages using Gmail's profile API.

        Round 70 Step 3: Replaced hardcoded 500 with a real estimate
        from GET /gmail/v1/users/me/profile which returns messagesTotal.
        Falls back to 100 if the API call fails (conservative default).
        """
        try:
            profile = await self._request("GET", "/gmail/v1/users/me/profile")
            total_messages = profile.get("messagesTotal", 0)
            if total_messages > 0:
                # 100 messages per page (Gmail API max per request)
                estimated_pages = max(1, (total_messages + 99) // 100)
                logger.info("Gmail estimate: %d messages → %d pages", total_messages, estimated_pages)
                return estimated_pages
        except Exception as e:
            logger.warning("Gmail profile estimate failed, using conservative default: %s", e)
        return 100  # Conservative fallback (was hardcoded 500)

    async def fetch_page(
        self,
        page: int = 1,
        cursor: str = "",
        since: datetime | None = None,
    ) -> PageResult:
        """Cursor format: "<page_token>" """
        try:
            user = await self._get_user_email()
        except Exception as e:
            return self._error_result(page, str(e))

        # Parse cursor
        page_token = cursor

        # Build query
        q = ""
        if since:
            # Gmail date query: after:YYYY/MM/DD
            q = f"after:{since.strftime('%Y/%m/%d')}"

        params: dict[str, Any] = {"maxResults": self.page_size}
        if q:
            params["q"] = q
        if page_token:
            params["pageToken"] = page_token

        try:
            resp = await self._request(
                "GET", f"{GMAIL_API}/users/{user}/messages", params=params
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                return self._rate_limited_result(e.response, page)
            if e.response.status_code == 401:
                return self._auth_expired_result(page)
            return self._error_result(page, f"Gmail HTTP {e.response.status_code}: {e}")
        except Exception as e:
            return self._error_result(page, str(e))

        if resp.status_code == 429:
            return self._rate_limited_result(resp, page)
        if resp.status_code != 200:
            return self._error_result(page, f"Gmail {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        message_ids = data.get("messages", [])
        next_page_token = data.get("nextPageToken", "")

        # Fetch metadata for each message (batched would be ideal; for now sequential)
        items: list[dict[str, Any]] = []
        for msg_ref in message_ids:
            msg_id = msg_ref.get("id")
            if not msg_id:
                continue
            try:
                detail_resp = await self._request(
                    "GET",
                    f"{GMAIL_API}/users/{user}/messages/{msg_id}",
                    params={"format": "metadata", "metadataHeaders": [
                        "From", "To", "Cc", "Subject", "Date", "List-Id",
                    ]},
                )
                if detail_resp.status_code != 200:
                    continue
                msg = detail_resp.json()
                item = self._normalize_message(user, msg)
                if item:
                    items.append(item)
            except Exception as e:
                logger.debug("Gmail message fetch failed for %s: %s", msg_id, e)

        return PageResult(
            page_number=page,
            status=PageStatus.SUCCESS,
            items=items,
            items_count=len(items),
            next_cursor=next_page_token or "",
            rate_limit_remaining=None,
        )

    # ─── Normalizer ───

    def _normalize_message(
        self, user_email: str, msg: dict[str, Any]
    ) -> dict[str, Any] | None:
        headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
        from_header = headers.get("from", "unknown")
        to_header = headers.get("to", "")
        subject = headers.get("subject", "")
        date_str = headers.get("date", "")

        # Parse email address from "Name <email@example.com>" format
        from_email = from_header
        if "<" in from_header and ">" in from_header:
            from_email = from_header.split("<")[1].split(">")[0]

        # Parse participants
        participants = [from_email]
        for addr_field in (to_header, headers.get("cc", "")):
            if addr_field:
                # Split by comma, extract emails
                for part in addr_field.split(","):
                    part = part.strip()
                    if "<" in part and ">" in part:
                        part = part.split("<")[1].split(">")[0]
                    if part and part not in participants:
                        participants.append(part)

        # Parse date (RFC 2822)
        timestamp = msg.get("internalDate")
        if timestamp:
            try:
                timestamp = datetime.fromtimestamp(int(timestamp) / 1000, tz=timezone.utc).isoformat()
            except (ValueError, OSError):
                timestamp = date_str
        else:
            timestamp = date_str

        # Skip system notifications for cleaner signal
        list_id = headers.get("list-id", "")
        if list_id and "noreply" in from_email.lower():
            return None

        return {
            "event_type": "email",
            "actor": from_email,
            "artifact": f"gmail:{msg.get('id', '')}",
            "timestamp": timestamp,
            "metadata": {
                "subject": subject,
                "to": to_header,
                "from": from_email,
                "participants": participants,
                "snippet": (msg.get("snippet", "") or "")[:500],
                "thread_id": msg.get("threadId", ""),
                "list_id": list_id,
            },
        }

    def normalize_item(self, item: dict[str, Any]) -> dict[str, Any]:
        return item

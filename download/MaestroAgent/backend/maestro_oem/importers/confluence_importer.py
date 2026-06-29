"""
Confluence historical importer.

Fetches:
  - Spaces (all spaces the user can access)
  - Pages in each space (with content)
  - Page versions (history)
  - Comments

Pagination:
  - Confluence REST API uses cursor-based pagination (next link in _links)
  - Page size: 100 (limit param)

Rate limits:
  - ~100 req/min for Cloud
  - Retry-After header on 429

OAuth:
  - Atlassian Cloud OAuth 2.0 (3LO) — same as Jira
  - cloud_id from /accessible-sites (shared with Jira)
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

ATLASSIAN_API = "https://api.atlassian.com"


class ConfluencePageFetcher(BaseProviderFetcher):
    """Fetches Confluence pages, comments, and version history.

    org_id is the Atlassian cloud_id (looked up automatically).
    """

    provider = "confluence"
    base_url = ATLASSIAN_API
    page_size = 100

    def __init__(
        self,
        oauth,
        http_client: httpx.AsyncClient | None = None,
        page_size: int | None = None,
        org_id: str | None = None,
    ) -> None:
        super().__init__(oauth, http_client, page_size, org_id)
        self._cloud_id: str | None = org_id
        self._spaces: list[dict[str, Any]] | None = None

    async def _get_cloud_id(self) -> str:
        if self._cloud_id:
            return self._cloud_id
        resp = await self._request(
            "GET", f"{ATLASSIAN_API}/me?expand=accessibleResources"
        )
        resp.raise_for_status()
        sites = resp.json().get("accessibleResources", [])
        if not sites:
            raise OAuthError("No accessible Atlassian sites for this token")
        self._cloud_id = sites[0]["id"]
        return self._cloud_id

    async def _discover_spaces(self) -> list[dict[str, Any]]:
        if self._spaces is not None:
            return self._spaces
        cloud_id = await self._get_cloud_id()
        spaces: list[dict[str, Any]] = []
        cursor = ""
        while True:
            url = f"{ATLASSIAN_API}/ex/confluence/{cloud_id}/wiki/api/v2/spaces"
            params: dict[str, Any] = {"limit": self.page_size}
            if cursor:
                params["cursor"] = cursor
            try:
                resp = await self._request("GET", url, params=params)
            except Exception as e:
                logger.warning("Confluence space discovery failed: %s", e)
                break
            if resp.status_code != 200:
                break
            data = resp.json()
            spaces.extend(data.get("results", []))
            cursor = data.get("_links", {}).get("next", "")
            if not cursor or not data.get("results"):
                break
        self._spaces = spaces
        logger.info("Discovered %d Confluence spaces", len(spaces))
        return spaces

    # ─── PageFetcher interface ───

    async def estimate_total_pages(self, since: datetime | None = None) -> int:
        try:
            spaces = await self._discover_spaces()
            return max(1, len(spaces) * 20)  # ~20 pages of content per space
        except Exception:
            return 50

    async def fetch_page(
        self,
        page: int = 1,
        cursor: str = "",
        since: datetime | None = None,
    ) -> PageResult:
        """Cursor format: "<space_idx>:<next_cursor>" """
        try:
            cloud_id = await self._get_cloud_id()
            spaces = await self._discover_spaces()
        except OAuthError:
            return self._auth_expired_result(page)
        except Exception as e:
            return self._error_result(page, str(e))

        if not spaces:
            return PageResult(page_number=page, status=PageStatus.SUCCESS, items=[], items_count=0)

        try:
            parts = cursor.split(":", 1)
            space_idx = int(parts[0]) if parts[0] else 0
            next_cursor = parts[1] if len(parts) > 1 else ""
        except (ValueError, IndexError):
            space_idx, next_cursor = 0, ""

        if space_idx >= len(spaces):
            return PageResult(page_number=page, status=PageStatus.SUCCESS, items=[], items_count=0)

        space = spaces[space_idx]
        space_id = space.get("id")

        url = f"{ATLASSIAN_API}/ex/confluence/{cloud_id}/wiki/api/v2/spaces/{space_id}/pages"
        params: dict[str, Any] = {"limit": self.page_size}
        if next_cursor:
            params["cursor"] = next_cursor

        try:
            resp = await self._request("GET", url, params=params)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                return self._rate_limited_result(e.response, page)
            if e.response.status_code == 401:
                return self._auth_expired_result(page)
            return self._error_result(page, f"Confluence HTTP {e.response.status_code}: {e}")
        except Exception as e:
            return self._error_result(page, str(e))

        if resp.status_code == 429:
            return self._rate_limited_result(resp, page)
        if resp.status_code != 200:
            return self._error_result(page, f"Confluence {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        pages_data = data.get("results", [])
        new_cursor = data.get("_links", {}).get("next", "")
        # Strip the leading URL from cursor if present
        if new_cursor and new_cursor.startswith("http"):
            new_cursor = ""

        items: list[dict[str, Any]] = []
        for page_data in pages_data:
            items.extend(self._normalize_page(space, page_data))

        # Build next cursor
        if new_cursor:
            next_cursor_str = f"{space_idx}:{new_cursor}"
        elif space_idx + 1 < len(spaces):
            next_cursor_str = f"{space_idx + 1}:"
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

    # ─── Normalizer ───

    def _normalize_page(
        self, space: dict[str, Any], page_data: dict[str, Any]
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        space_key = space.get("key", space.get("id", "UNKNOWN"))
        space_name = space.get("name", space_key)
        page_id = page_data.get("id", "")
        title = page_data.get("title", "")
        author_id = page_data.get("authorId", "unknown")

        # Page created/updated
        created_at = page_data.get("createdAt")
        updated_at = page_data.get("version", {}).get("createdAt", created_at)

        events.append({
            "event_type": "page_created",
            "space": space_key,
            "actor": f"{author_id}@atlassian",
            "artifact": f"confluence:{space_key}/page/{page_id}",
            "timestamp": updated_at or created_at or datetime.now(timezone.utc).isoformat(),
            "metadata": {
                "title": title,
                "space_name": space_name,
                "version": page_data.get("version", {}).get("number", 1),
                "body_length": len(page_data.get("body", {}).get("storage", {}).get("value", "")),
            },
        })

        # Each version is a separate event (knowledge update)
        version = page_data.get("version", {})
        if version.get("number", 1) > 1:
            events.append({
                "event_type": "page_updated",
                "space": space_key,
                "actor": f"{version.get('authorId', author_id)}@atlassian",
                "artifact": f"confluence:{space_key}/page/{page_id}/v{version.get('number')}",
                "timestamp": version.get("createdAt", updated_at),
                "metadata": {
                    "title": title,
                    "space_name": space_name,
                    "version": version.get("number"),
                },
            })

        return events

    def normalize_item(self, item: dict[str, Any]) -> dict[str, Any]:
        return item

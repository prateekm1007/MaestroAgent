"""
Jira historical importer.

Fetches:
  - Issues (with changelog)
  - Comments
  - Transitions (from changelog)
  - Sprints (via agile API)

Pagination:
  - Jira REST API uses startAt + maxResults for pagination
  - Some endpoints support cursor-based pagination (newer API)
  - Default page size: 50 (we use 100)

Rate limits:
  - Varies by plan (Cloud: ~1000/hr for Standard)
  - Retry-After header on 429

OAuth:
  - Atlassian Cloud OAuth 2.0 (3LO)
  - Requires cloud_id for API calls (looked up from /accessible-sites)
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


class JiraPageFetcher(BaseProviderFetcher):
    """Fetches Jira issues, comments, and transitions.

    org_id is the Atlassian cloud_id (looked up automatically on first call).
    """

    provider = "jira"
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

    async def _get_cloud_id(self) -> str:
        """Look up the Atlassian cloud_id from /accessible-sites."""
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

    @property
    def _jira_base(self) -> str:
        assert self._cloud_id, "cloud_id not loaded"
        return f"{ATLASSIAN_API}/ex/jira/{self._cloud_id}"

    # ─── PageFetcher interface ───

    async def estimate_total_pages(self, since: datetime | None = None) -> int:
        # JQL count query
        try:
            cloud_id = await self._get_cloud_id()
            jql = f"updated >= '{(since or datetime(2020, 1, 1, tzinfo=timezone.utc)).strftime('%Y-%m-%d')}'"
            resp = await self._request(
                "POST",
                f"{ATLASSIAN_API}/ex/jira/{cloud_id}/rest/api/3/search",
                json_body={"jql": jql, "maxResults": 0, "fields": []},
            )
            if resp.status_code == 200:
                total = resp.json().get("total", 0)
                return max(1, (total + self.page_size - 1) // self.page_size)
        except Exception as e:
            logger.warning("Jira estimate failed: %s", e)
        return 100  # Fallback

    async def fetch_page(
        self,
        page: int = 1,
        cursor: str = "",
        since: datetime | None = None,
    ) -> PageResult:
        """Fetch a page of Jira issues.

        Cursor format: "<start_at>:<since_iso>"
        """
        try:
            cloud_id = await self._get_cloud_id()
        except OAuthError as e:
            return self._auth_expired_result(page)
        except Exception as e:
            return self._error_result(page, f"Failed to get cloud_id: {e}")

        # Parse cursor
        try:
            parts = cursor.split(":", 1)
            start_at = int(parts[0]) if parts[0] else (page - 1) * self.page_size
            since_str = parts[1] if len(parts) > 1 else ""
        except (ValueError, IndexError):
            start_at = (page - 1) * self.page_size
            since_str = ""

        if since and not since_str:
            since_str = since.strftime("%Y-%m-%d")

        jql = f"updated >= '{since_str}'" if since_str else "ORDER BY updated DESC"

        try:
            resp = await self._request(
                "POST",
                f"{ATLASSIAN_API}/ex/jira/{cloud_id}/rest/api/3/search",
                json_body={
                    "jql": jql,
                    "startAt": start_at,
                    "maxResults": self.page_size,
                    "fields": [
                        "summary", "status", "assignee", "reporter",
                        "priority", "issuetype", "created", "updated",
                        "comment", "changelog",
                    ],
                    "expand": ["changelog"],
                },
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                return self._rate_limited_result(e.response, page)
            if e.response.status_code == 401:
                return self._auth_expired_result(page)
            return self._error_result(page, f"Jira HTTP {e.response.status_code}: {e}")
        except Exception as e:
            return self._error_result(page, str(e))

        if resp.status_code == 429:
            return self._rate_limited_result(resp, page)
        if resp.status_code != 200:
            return self._error_result(page, f"Jira {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        issues = data.get("issues", [])
        total = data.get("total", 0)

        items: list[dict[str, Any]] = []
        for issue in issues:
            items.extend(self._normalize_issue(issue))

        # Next cursor
        next_start = start_at + len(issues)
        has_next = next_start < total and len(issues) == self.page_size
        next_cursor = f"{next_start}:{since_str}" if has_next else ""

        return PageResult(
            page_number=page,
            status=PageStatus.SUCCESS,
            items=items,
            items_count=len(items),
            next_cursor=next_cursor,
            rate_limit_remaining=None,
        )

    # ─── Normalizer ───

    def _normalize_issue(self, issue: dict[str, Any]) -> list[dict[str, Any]]:
        """Convert one Jira issue into multiple events (create, transitions, comments)."""
        events: list[dict[str, Any]] = []
        key = issue.get("key", "")
        fields = issue.get("fields", {})

        project = key.split("-")[0] if "-" in key else "UNKNOWN"
        reporter = (fields.get("reporter") or {}).get("emailAddress") or \
                   f"{(fields.get('reporter') or {}).get('accountId', 'unknown')}@atlassian"
        assignee = (fields.get("assignee") or {}).get("emailAddress")
        priority = (fields.get("priority") or {}).get("name", "P2")
        issue_type = (fields.get("issuetype") or {}).get("name", "Task")
        created = fields.get("created")
        updated = fields.get("updated")

        # Issue created event
        events.append({
            "event_type": "issue_created",
            "project": project,
            "actor": reporter,
            "artifact": f"jira:{key}",
            "timestamp": created or updated or datetime.now(timezone.utc).isoformat(),
            "metadata": {
                "priority": priority,
                "issue_type": issue_type,
                "title": fields.get("summary", ""),
                "state": (fields.get("status") or {}).get("name", "Open"),
            },
        })

        # Transitions (from changelog)
        changelog = issue.get("changelog", {})
        for hist in changelog.get("histories", []):
            for item in hist.get("items", []):
                if item.get("field") == "status":
                    actor = hist.get("author", {}).get("emailAddress") or \
                            f"{hist.get('author', {}).get('accountId', 'unknown')}@atlassian"
                    events.append({
                        "event_type": "issue_transitioned",
                        "project": project,
                        "actor": actor,
                        "artifact": f"jira:{key}",
                        "timestamp": hist.get("created", updated),
                        "metadata": {
                            "transition": item.get("toString", ""),
                            "from": item.get("fromString", ""),
                            "to": item.get("toString", ""),
                            "assignee": assignee or actor,
                        },
                    })

        # Comments
        comments = fields.get("comment", {})
        for comment in comments.get("comments", []):
            author = comment.get("author", {}).get("emailAddress") or \
                     f"{comment.get('author', {}).get('accountId', 'unknown')}@atlassian"
            events.append({
                "event_type": "issue_commented",
                "project": project,
                "actor": author,
                "artifact": f"jira:{key}/comment/{comment.get('id', '')}",
                "timestamp": comment.get("created", updated),
                "metadata": {
                    "text": comment.get("body", "")[:500] if isinstance(comment.get("body"), str) else "",
                    "issue_type": issue_type,
                    "priority": priority,
                },
            })

        return events

    def normalize_item(self, item: dict[str, Any]) -> dict[str, Any]:
        return item

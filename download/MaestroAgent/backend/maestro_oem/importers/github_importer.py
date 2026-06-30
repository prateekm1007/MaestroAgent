"""
GitHub historical importer.

Fetches:
  - Pull requests (with reviews and commits via the timeline endpoint)
  - Issues (with comments)
  - Commits (paginated by SHA)
  - Reviews on PRs

Pagination:
  - GitHub REST API uses Link headers with rel="next"
  - Page size: 100 (max)
  - Per-page: ?page=N&per_page=100

Rate limits:
  - 5000 req/hr for authenticated users
  - 15000 req/hr for GitHub Apps
  - X-RateLimit-Remaining and X-RateLimit-Reset headers

OAuth scopes:
  - repo (private repos)
  - read:org
  - read:user
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

from maestro_oem.importers.base import BaseProviderFetcher
from maestro_oem.ingestion import PageResult, PageStatus

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


class GitHubPageFetcher(BaseProviderFetcher):
    """Fetches GitHub PRs, issues, commits, and reviews.

    org_id is the GitHub org or user login (e.g. "octocat" or "microsoft").
    If not set, fetches from all repositories the user has access to.
    """

    provider = "github"
    base_url = GITHUB_API
    page_size = 100

    def __init__(
        self,
        oauth,
        http_client: httpx.AsyncClient | None = None,
        page_size: int | None = None,
        org_id: str | None = None,
        repos: list[str] | None = None,
    ) -> None:
        super().__init__(oauth, http_client, page_size, org_id)
        # repos is an explicit list of "owner/repo" to import
        self.repos = repos or []
        self._repos_discovered: list[str] | None = None

    # ─── Repository discovery ───

    async def _discover_repos(self) -> list[str]:
        """If org_id is set, list its repos. Otherwise list user's repos."""
        if self._repos_discovered is not None:
            return self._repos_discovered

        if self.repos:
            self._repos_discovered = list(self.repos)
            return self._repos_discovered

        repos: list[str] = []
        page = 1
        while True:
            if self.org_id:
                url = f"{GITHUB_API}/orgs/{self.org_id}/repos"
            else:
                url = f"{GITHUB_API}/user/repos"
            params = {"page": page, "per_page": 100, "sort": "updated", "direction": "desc"}
            try:
                resp = await self._request("GET", url, params=params)
            except Exception as e:
                logger.warning("Repo discovery failed: %s", e)
                break

            if resp.status_code == 403:
                # Rate limited
                logger.warning("Rate limited during repo discovery")
                break
            if resp.status_code != 200:
                logger.warning("Repo discovery returned %d", resp.status_code)
                break

            data = resp.json()
            if not data:
                break
            for repo in data:
                repos.append(repo["full_name"])
            if len(data) < 100:
                break
            page += 1

        self._repos_discovered = repos
        logger.info("Discovered %d GitHub repos for org_id=%s", len(repos), self.org_id)
        return repos

    # ─── PageFetcher interface ───

    async def estimate_total_pages(self, since: datetime | None = None) -> int:
        """Estimate total pages across all repos.

        Conservative: assume each repo has ~50 pages of activity (5000 items).
        For orgs with many repos, this can be large; the pipeline handles it.
        """
        repos = await self._discover_repos()
        # 4 resource types per repo (pulls, issues, commits, reviews) × ~50 pages each
        return max(1, len(repos) * 4 * 50)

    async def fetch_page(
        self,
        page: int = 1,
        cursor: str = "",
        since: datetime | None = None,
    ) -> PageResult:
        """Fetch one page of GitHub activity.

        Cursor format: "<repo_idx>:<resource>:<page>:<since_iso>"
        Example: "3:pulls:2:2024-01-01T00:00:00Z"
        """
        repos = await self._discover_repos()
        if not repos:
            return PageResult(page_number=page, status=PageStatus.SUCCESS, items=[], items_count=0)

        # Parse cursor
        try:
            repo_idx, resource, sub_page, since_str = (cursor.split(":", 3) + ["", "", "", ""])[:4]
            repo_idx = int(repo_idx) if repo_idx else 0
            sub_page = int(sub_page) if sub_page else 1
        except (ValueError, IndexError):
            repo_idx, resource, sub_page = 0, "pulls", 1

        if not resource:
            resource = "pulls"

        # Reset to start of next repo if we've finished this one
        if repo_idx >= len(repos):
            return PageResult(page_number=page, status=PageStatus.SUCCESS, items=[], items_count=0)

        repo = repos[repo_idx]
        since_param = since_str or (since.isoformat() if since else "")

        try:
            if resource == "pulls":
                items, has_next, next_sub_page = await self._fetch_pulls(
                    repo, sub_page, since_param
                )
                next_resource = "issues"
                next_sub_page_for_next = 1
            elif resource == "issues":
                items, has_next, next_sub_page = await self._fetch_issues(
                    repo, sub_page, since_param
                )
                next_resource = "commits"
                next_sub_page_for_next = 1
            elif resource == "commits":
                items, has_next, next_sub_page = await self._fetch_commits(
                    repo, sub_page, since_param
                )
                next_resource = "reviews"
                next_sub_page_for_next = 1
            elif resource == "reviews":
                items, has_next, next_sub_page = await self._fetch_reviews(
                    repo, sub_page, since_param
                )
                # Move to next repo
                next_resource = "pulls"
                next_sub_page_for_next = 1
                repo_idx += 1
            else:
                return self._error_result(page, f"Unknown resource: {resource}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                return self._rate_limited_result(e.response, page)
            if e.response.status_code == 401:
                return self._auth_expired_result(page)
            return self._error_result(page, f"HTTP {e.response.status_code}: {e}")
        except Exception as e:
            return self._error_result(page, str(e))

        # Build next cursor
        if has_next:
            next_cursor = f"{repo_idx}:{next_resource}:{next_sub_page}:{since_param}"
        elif repo_idx < len(repos):
            # Finished this resource for this repo, move on
            next_cursor = f"{repo_idx}:{next_resource}:{next_sub_page_for_next}:{since_param}"
        else:
            next_cursor = ""

        remaining, _ = self._parse_rate_limit_headers(
            getattr(self, "_last_resp", httpx.Response(200))
        )

        return PageResult(
            page_number=page,
            status=PageStatus.SUCCESS,
            items=items,
            items_count=len(items),
            next_cursor=next_cursor,
            rate_limit_remaining=remaining,
        )

    # ─── Resource fetchers ───

    async def _fetch_pulls(
        self, repo: str, page: int, since: str
    ) -> tuple[list[dict[str, Any]], bool, int]:
        url = f"{GITHUB_API}/repos/{repo}/pulls"
        params: dict[str, Any] = {
            "page": page, "per_page": self.page_size,
            "state": "all", "sort": "updated", "direction": "desc",
        }
        if since:
            params["since"] = since
        resp = await self._request("GET", url, params=params)
        self._last_resp = resp
        resp.raise_for_status()
        data = resp.json()
        items = [self._normalize_pr(repo, pr) for pr in data]
        has_next = len(data) == self.page_size
        return items, has_next, page + 1

    async def _fetch_issues(
        self, repo: str, page: int, since: str
    ) -> tuple[list[dict[str, Any]], bool, int]:
        url = f"{GITHUB_API}/repos/{repo}/issues"
        params: dict[str, Any] = {
            "page": page, "per_page": self.page_size,
            "state": "all", "since": since or None,
        }
        resp = await self._request("GET", url, params=params)
        self._last_resp = resp
        resp.raise_for_status()
        data = resp.json()
        # GitHub returns PRs in the issues endpoint; filter them out
        items = [self._normalize_issue(repo, i) for i in data if "pull_request" not in i]
        has_next = len(data) == self.page_size
        return items, has_next, page + 1

    async def _fetch_commits(
        self, repo: str, page: int, since: str
    ) -> tuple[list[dict[str, Any]], bool, int]:
        url = f"{GITHUB_API}/repos/{repo}/commits"
        params: dict[str, Any] = {"page": page, "per_page": self.page_size}
        if since:
            params["since"] = since
        resp = await self._request("GET", url, params=params)
        self._last_resp = resp
        resp.raise_for_status()
        data = resp.json()
        items = [self._normalize_commit(repo, c) for c in data]
        has_next = len(data) == self.page_size
        return items, has_next, page + 1

    async def _fetch_reviews(
        self, repo: str, page: int, since: str
    ) -> tuple[list[dict[str, Any]], bool, int]:
        # Reviews are per-PR; we fetch them lazily by listing recent PRs and
        # then their reviews. To keep this simple, we fetch reviews for the
        # N most recent PRs.
        url = f"{GITHUB_API}/repos/{repo}/pulls"
        params: dict[str, Any] = {
            "page": page, "per_page": 20,
            "state": "all", "sort": "updated", "direction": "desc",
        }
        resp = await self._request("GET", url, params=params)
        self._last_resp = resp
        resp.raise_for_status()
        prs = resp.json()
        items: list[dict[str, Any]] = []
        for pr in prs:
            pr_number = pr["number"]
            reviews_url = f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}/reviews"
            try:
                rev_resp = await self._request("GET", reviews_url, params={"per_page": 50})
                if rev_resp.status_code == 200:
                    for rev in rev_resp.json():
                        items.append(self._normalize_review(repo, pr, rev))
            except Exception as e:
                logger.debug("Failed to fetch reviews for PR %d: %s", pr_number, e)
        has_next = len(prs) == 20
        return items, has_next, page + 1

    # ─── Normalizers ───

    @staticmethod
    def _parse_timestamp(ts: str | None) -> str:
        if not ts:
            return datetime.now(timezone.utc).isoformat()
        # GitHub returns ISO timestamps with Z; ensure consistent format
        return ts.replace("Z", "+00:00") if ts.endswith("Z") else ts

    @staticmethod
    def _extract_email(login: str, repo: str) -> str:
        """GitHub API doesn't always expose emails; synthesize one for tracking."""
        return f"{login}@users.noreply.github.com"

    def _normalize_pr(self, repo: str, pr: dict[str, Any]) -> dict[str, Any]:
        user_login = (pr.get("user") or {}).get("login", "unknown")
        merged_at = pr.get("merged_at")
        action = "merged" if merged_at else ("closed" if pr.get("closed_at") else "opened")
        return {
            "event_type": "pull_request",
            "repository": repo,
            "actor": self._extract_email(user_login, repo),
            "artifact": f"github:{repo}/pull/{pr.get('number', 0)}",
            "timestamp": self._parse_timestamp(pr.get("updated_at") or pr.get("created_at")),
            "metadata": {
                "action": action,
                "title": pr.get("title", ""),
                "domain": self._infer_domain(repo, pr.get("title", "")),
                "merged_at": merged_at,
                "additions": pr.get("additions", 0),
                "deletions": pr.get("deletions", 0),
                "review_comments": pr.get("review_comments", 0),
            },
        }

    def _normalize_issue(self, repo: str, issue: dict[str, Any]) -> dict[str, Any]:
        user_login = (issue.get("user") or {}).get("login", "unknown")
        labels = [l.get("name", "") for l in issue.get("labels", []) if isinstance(l, dict)]
        priority = "P1" if any("p1" in l.lower() or "critical" in l.lower() for l in labels) else "P2"
        return {
            "event_type": "issue_created",
            "repository": repo,
            "project": repo,
            "actor": self._extract_email(user_login, repo),
            "artifact": f"github:{repo}/issues/{issue.get('number', 0)}",
            "timestamp": self._parse_timestamp(issue.get("updated_at") or issue.get("created_at")),
            "metadata": {
                "priority": priority,
                "issue_type": "Bug" if "bug" in labels else "Task",
                "title": issue.get("title", ""),
                "labels": labels,
                "state": issue.get("state", "open"),
                "domain": self._infer_domain(repo, issue.get("title", "")),
            },
        }

    def _normalize_commit(self, repo: str, commit: dict[str, Any]) -> dict[str, Any]:
        author = commit.get("commit", {}).get("author", {}) or {}
        author_email = author.get("email") or self._extract_email(
            (commit.get("author") or {}).get("login", "unknown"), repo
        )
        message = commit.get("commit", {}).get("message", "")
        return {
            "event_type": "commit",
            "repository": repo,
            "actor": author_email,
            "artifact": f"github:{repo}/commit/{commit.get('sha', '')[:7]}",
            "timestamp": self._parse_timestamp(author.get("date")),
            "metadata": {
                "message": message,
                "domain": self._infer_domain(repo, message),
            },
        }

    def _normalize_review(
        self, repo: str, pr: dict[str, Any], review: dict[str, Any]
    ) -> dict[str, Any]:
        reviewer = (review.get("user") or {}).get("login", "unknown")
        state = review.get("state", "COMMENTED").lower()
        return {
            "event_type": "review",
            "repository": repo,
            "actor": self._extract_email(reviewer, repo),
            "artifact": f"github:{repo}/pull/{pr.get('number', 0)}",
            "timestamp": self._parse_timestamp(review.get("submitted_at")),
            "metadata": {
                "reviewer": self._extract_email(reviewer, repo),
                "action": "approved" if state == "approved" else (
                    "changes_requested" if state == "changes_requested" else "reviewed"
                ),
                "domain": self._infer_domain(repo, pr.get("title", "")),
            },
        }

    @staticmethod
    def _infer_domain(repo: str, text: str) -> str:
        """Heuristic domain inference for OEM routing."""
        repo_lower = repo.lower()
        text_lower = (text or "").lower()
        for keyword, domain in [
            ("payment", "payments"),
            ("auth", "auth"),
            ("oauth", "auth"),
            ("security", "security"),
            ("legal", "legal"),
            ("infra", "platform"),
            ("platform", "platform"),
            ("data", "data"),
            ("ml", "ml"),
            ("ui", "frontend"),
            ("frontend", "frontend"),
            ("backend", "backend"),
            ("api", "backend"),
            ("test", "qa"),
            ("qa", "qa"),
        ]:
            if keyword in repo_lower or keyword in text_lower:
                return domain
        return "engineering"

    def normalize_item(self, item: dict[str, Any]) -> dict[str, Any]:
        """Items are already normalized to event-dict shape in _normalize_*."""
        return item

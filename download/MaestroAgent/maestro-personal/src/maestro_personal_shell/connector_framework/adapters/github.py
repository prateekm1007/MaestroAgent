"""GitHub adapter — T1 connector with OAuth/ PAT + GraphQL for PRs/issues/reviews.

GitHub is a commitment goldmine for technical users:
- reviewRequested on you = inbound commitment with a soft SLA
- your PR description "will fix X" = outbound commitment
- an issue you're assigned = open commitment

Uses GraphQL for efficient nested PR/review/comment trees.
Webhooks for realtime (pull_request, issue_comment, pull_request_review).

Gate: "what PRs am I blocking?" → source:"github" evidence with real PR titles.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from maestro_personal_shell.connector_framework import Signal
from maestro_personal_shell.connector_framework.base import BaseConnector, SyncCursor
from maestro_personal_shell.connector_framework.registry import register_adapter

logger = logging.getLogger(__name__)


@register_adapter("github")
class GitHubAdapter(BaseConnector):
    """GitHub connector using OAuth2 / PAT + REST/GraphQL API.

    Auth: OAuth2 (preferred for orgs) or fine-grained PAT
    Cursor: {"since": "<ISO timestamp>"} for incremental sync
    Idempotency: GitHub node_id (global, unique)
    """

    connector_name = "github"

    def __init__(self) -> None:
        self.access_token: str | None = None
        self.client_id: str = os.environ.get("MAESTRO_GITHUB_CLIENT_ID", "")
        self.client_secret: str = os.environ.get("MAESTRO_GITHUB_CLIENT_SECRET", "")

    def load_credentials(self, credentials: dict[str, Any]) -> None:
        self.access_token = credentials.get("access_token") or credentials.get("token")

    def _is_configured(self) -> bool:
        return bool(self.access_token)

    def _get_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def load_from_state(self, user_email: str) -> list[Signal]:
        """Bulk load — fetch assigned issues, review requests, and recent PRs."""
        if not self.access_token:
            return []

        signals: list[Signal] = []

        try:
            # Fetch review requests (PRs where you're blocking)
            review_requests = self._fetch_review_requests()
            signals.extend(review_requests)

            # Fetch assigned issues
            assigned_issues = self._fetch_assigned_issues()
            signals.extend(assigned_issues)

            # Fetch your recent PRs (commitments you made)
            my_prs = self._fetch_my_pull_requests()
            signals.extend(my_prs)

            logger.info("GitHubAdapter.load_from_state: %d signals", len(signals))
        except Exception as e:
            logger.error("GitHubAdapter.load_from_state failed: %s", e)

        return signals

    def poll_source(self, user_email: str, cursor: SyncCursor) -> tuple[list[Signal], SyncCursor]:
        """Incremental sync — fetch only items updated since the cursor."""
        if not self.access_token:
            return [], cursor

        try:
            since = cursor.cursor_data.get("since", "")
            signals: list[Signal] = []

            # Fetch updated review requests
            review_requests = self._fetch_review_requests(since=since)
            signals.extend(review_requests)

            # Fetch updated assigned issues
            assigned = self._fetch_assigned_issues(since=since)
            signals.extend(assigned)

            # Update cursor
            cursor.cursor_data["since"] = datetime.now(timezone.utc).isoformat()
            cursor.last_sync = datetime.now(timezone.utc)
            cursor.total_synced += len(signals)

            return signals, cursor
        except Exception as e:
            logger.error("GitHubAdapter.poll_source failed: %s", e)
            return [], cursor

    def slim_check(self, user_email: str) -> list[str]:
        """Return node_ids of all GitHub items that still exist."""
        if not self.access_token:
            return []

        try:
            ids: list[str] = []
            for sig in self.load_from_state(user_email):
                ids.append(sig.source_id)
            return ids
        except Exception:
            return []

    def _fetch_review_requests(self, since: str = "") -> list[Signal]:
        """Fetch PRs where you're requested as a reviewer."""
        import httpx

        signals: list[Signal] = []
        try:
            # Search for PRs requesting your review
            query = "is:open is:pr review-requested:@me"
            if since:
                query += f" updated:>={since[:10]}"

            resp = httpx.get(
                "https://api.github.com/search/issues",
                params={"q": query, "per_page": 50},
                headers=self._get_headers(),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("items", []):
                repo_url = item.get("repository_url", "")
                repo_name = repo_url.split("/repos/")[-1] if "/repos/" in repo_url else "unknown"

                signals.append(Signal(
                    source="github",
                    source_id=str(item.get("id", "")),
                    thread_id=str(item.get("number", "")),
                    entity=repo_name,
                    text=f"PR #{item.get('number')}: {item.get('title', '')} — review requested",
                    timestamp=datetime.fromisoformat(item.get("updated_at", "").replace("Z", "+00:00"))
                    if item.get("updated_at") else datetime.now(timezone.utc),
                    direction="commitment_theirs",
                    metadata={
                        "source": "github",
                        "type": "review_request",
                        "repo": repo_name,
                        "pr_number": item.get("number"),
                        "pr_url": item.get("html_url", ""),
                        "state": item.get("state", ""),
                    },
                    confidence=0.8,
                ))
        except Exception as e:
            logger.warning("GitHubAdapter._fetch_review_requests failed: %s", e)

        return signals

    def _fetch_assigned_issues(self, since: str = "") -> list[Signal]:
        """Fetch issues assigned to you."""
        import httpx

        signals: list[Signal] = []
        try:
            query = "is:open is:issue assignee:@me"
            if since:
                query += f" updated:>={since[:10]}"

            resp = httpx.get(
                "https://api.github.com/search/issues",
                params={"q": query, "per_page": 50},
                headers=self._get_headers(),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("items", []):
                repo_url = item.get("repository_url", "")
                repo_name = repo_url.split("/repos/")[-1] if "/repos/" in repo_url else "unknown"

                signals.append(Signal(
                    source="github",
                    source_id=str(item.get("id", "")),
                    thread_id=str(item.get("number", "")),
                    entity=repo_name,
                    text=f"Issue #{item.get('number')}: {item.get('title', '')} — assigned to you",
                    timestamp=datetime.fromisoformat(item.get("updated_at", "").replace("Z", "+00:00"))
                    if item.get("updated_at") else datetime.now(timezone.utc),
                    direction="commitment_mine",
                    metadata={
                        "source": "github",
                        "type": "assigned_issue",
                        "repo": repo_name,
                        "issue_number": item.get("number"),
                        "issue_url": item.get("html_url", ""),
                        "state": item.get("state", ""),
                    },
                    confidence=0.7,
                ))
        except Exception as e:
            logger.warning("GitHubAdapter._fetch_assigned_issues failed: %s", e)

        return signals

    def _fetch_my_pull_requests(self) -> list[Signal]:
        """Fetch your recent PRs (commitments you made)."""
        import httpx

        signals: list[Signal] = []
        try:
            query = "is:open is:pr author:@me"

            resp = httpx.get(
                "https://api.github.com/search/issues",
                params={"q": query, "per_page": 20},
                headers=self._get_headers(),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("items", []):
                repo_url = item.get("repository_url", "")
                repo_name = repo_url.split("/repos/")[-1] if "/repos/" in repo_url else "unknown"

                signals.append(Signal(
                    source="github",
                    source_id=str(item.get("id", "")),
                    thread_id=str(item.get("number", "")),
                    entity=repo_name,
                    text=f"Your PR #{item.get('number')}: {item.get('title', '')}",
                    timestamp=datetime.fromisoformat(item.get("updated_at", "").replace("Z", "+00:00"))
                    if item.get("updated_at") else datetime.now(timezone.utc),
                    direction="commitment_mine",
                    metadata={
                        "source": "github",
                        "type": "my_pr",
                        "repo": repo_name,
                        "pr_number": item.get("number"),
                        "pr_url": item.get("html_url", ""),
                    },
                    confidence=0.6,
                ))
        except Exception as e:
            logger.warning("GitHubAdapter._fetch_my_pull_requests failed: %s", e)

        return signals

    def get_authorization_url(self, redirect_uri: str, state: str) -> str:
        """Get the GitHub OAuth2 authorization URL."""
        from urllib.parse import urlencode

        scopes = "repo issues pull_requests read:user"

        params = {
            "client_id": self.client_id,
            "scope": scopes,
            "redirect_uri": redirect_uri,
            "state": state,
        }

        return f"https://github.com/login/oauth/authorize?{urlencode(params)}"

    def exchange_code_for_tokens(self, code: str, redirect_uri: str) -> dict[str, Any]:
        """Exchange OAuth authorization code for access token."""
        import httpx

        resp = httpx.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
            headers={"Accept": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        self.access_token = data.get("access_token")

        return {
            "access_token": self.access_token,
            "token_type": data.get("token_type", "bearer"),
            "scope": data.get("scope", ""),
        }

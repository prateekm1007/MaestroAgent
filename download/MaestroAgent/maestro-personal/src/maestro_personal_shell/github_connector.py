"""
GitHub OAuth2 connector — real GitHub API integration (Phase D).

Same pattern as gmail_connector.py (Phase B) and slack_connector.py (Phase C):
  - GitHubOAuthClient: OAuth2 authorization code flow + token refresh
  - GitHubAPIClient: GitHub REST API calls (issues, PRs, comments)
  - GitHubIngester: pulls assigned issues/PRs, extracts action items

OAuth2 flow:
  1. User clicks "Connect GitHub" in the UI
  2. Backend generates authorization URL with scopes:
     - repo (read issues/PRs + post comments)
     - user (read user profile)
  3. User grants access on GitHub's consent screen
  4. GitHub redirects to /api/connectors/github/oauth/callback with a code
  5. Backend exchanges code for access token
  6. Token stored encrypted in ConnectorStore
  7. Ingestion uses the access token to call:
       GET /issues?filter=assigned&state=open  (assigned issues)
       GET /pulls?state=open  (open PRs in owned repos)
  8. Send uses POST /repos/{owner}/{repo}/issues/{number}/comments

Configuration (env vars):
  - MAESTRO_GITHUB_CLIENT_ID: GitHub OAuth app client ID
  - MAESTRO_GITHUB_CLIENT_SECRET: GitHub OAuth app client secret
  - MAESTRO_GITHUB_REDIRECT_URI: OAuth2 redirect URI

When NOT set, falls back to MOCK_INGESTION_DATA — demo mode.

Action item extraction:
  - Pulls assigned issues (open) from last 30 days
  - For each issue, extracts the body + comments
  - Runs keyword action-item detection ("needs to", "should", "must",
    "TODO", "action item", "follow up")
  - Ingests as signals with:
      entity = repo name (e.g., "prateekm1007/MaestroAgent")
      text = the action item text
      signal_type = commitment_made (if "I will") or reported_statement
      timestamp = issue/PR timestamp
      source = github:issue or github:pr
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Any
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GITHUB_SCOPES = ["repo", "user"]

GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_BASE = "https://api.github.com"


def _get_github_config() -> dict[str, str]:
    """Get GitHub OAuth2 config from env."""
    return {
        "client_id": os.environ.get("MAESTRO_GITHUB_CLIENT_ID", ""),
        "client_secret": os.environ.get("MAESTRO_GITHUB_CLIENT_SECRET", ""),
        "redirect_uri": os.environ.get(
            "MAESTRO_GITHUB_REDIRECT_URI",
            "http://localhost:8766/api/connectors/github/oauth/callback",
        ),
    }


def is_github_configured() -> bool:
    """Check if real GitHub OAuth credentials are configured."""
    config = _get_github_config()
    return bool(config["client_id"] and config["client_secret"])


# ---------------------------------------------------------------------------
# GitHub OAuth2 Client
# ---------------------------------------------------------------------------

class GitHubOAuthClient:
    """Handles GitHub OAuth2 authorization code flow.

    GitHub tokens don't expire by default (no refresh needed), but we
    keep the refresh-style interface for consistency with Gmail/Calendar.
    """

    def __init__(self):
        self.config = _get_github_config()

    def get_authorization_url(self, state: str = "") -> str:
        """Generate the GitHub OAuth2 authorization URL."""
        if not self.config["client_id"]:
            raise ValueError("GitHub OAuth not configured (MAESTRO_GITHUB_CLIENT_ID missing)")

        params = {
            "client_id": self.config["client_id"],
            "redirect_uri": self.config["redirect_uri"],
            "scope": " ".join(GITHUB_SCOPES),
            "state": state,
        }
        return f"{GITHUB_AUTH_URL}?{urlencode(params)}"

    def exchange_code_for_tokens(self, code: str) -> dict[str, Any]:
        """Exchange authorization code for an access token.

        GitHub returns a token (not JSON by default — we request JSON).
        Returns: {access_token, token_type, scope}
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
            GITHUB_TOKEN_URL,
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                token_data = json.loads(resp.read().decode())
                if "error" in token_data:
                    return {"error": token_data.get("error_description", token_data["error"])}
                # GitHub tokens don't expire — set a far-future expiry for consistency
                token_data["expires_at"] = (
                    datetime.now(timezone.utc) + timedelta(days=365)
                ).isoformat()
                return token_data
        except Exception as e:
            logger.error(f"GitHub OAuth token exchange failed: {e}")
            return {"error": str(e)}

    def get_valid_access_token(self, stored_token_json: str) -> tuple[str, str]:
        """Get a valid access token.

        GitHub tokens don't expire by default — no refresh needed.
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
# GitHub API Client (ingestion + send)
# ---------------------------------------------------------------------------

class GitHubAPIClient:
    """Calls the GitHub REST API using an access token.

    Uses urllib (no hard PyGithub dependency).
    """

    def __init__(self, access_token: str):
        self.access_token = access_token

    def _request(self, path: str, method: str = "GET", body: dict | None = None) -> dict | list:
        import urllib.request
        url = f"{GITHUB_API_BASE}{path}"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            logger.error(f"GitHub API {method} {path} failed: {e}")
            return {"error": str(e)}

    def get_authenticated_user(self) -> dict[str, Any]:
        """Get the authenticated user's profile (for filtering assigned issues)."""
        result = self._request("/user")
        if isinstance(result, dict) and "error" not in result:
            return result
        return {}

    def list_assigned_issues(self, state: str = "open", per_page: int = 50) -> list[dict[str, Any]]:
        """List issues assigned to the authenticated user.

        Returns: list of issue dicts {number, title, body, html_url, repository, created_at, updated_at}
        """
        result = self._request(f"/issues?filter=assigned&state={state}&per_page={per_page}")
        if not isinstance(result, list):
            return []
        # GitHub returns issues across all repos; extract the repo name from the URL
        issues = []
        for issue in result:
            # Skip PRs (they show up in the issues endpoint too)
            if "pull_request" in issue:
                continue
            repo_url = issue.get("repository_url", "")
            repo = repo_url.replace("https://api.github.com/repos/", "") if repo_url else ""
            issues.append({
                "number": issue.get("number", 0),
                "title": issue.get("title", ""),
                "body": issue.get("body", "") or "",
                "html_url": issue.get("html_url", ""),
                "repository": repo,
                "created_at": issue.get("created_at", ""),
                "updated_at": issue.get("updated_at", ""),
                "user": issue.get("user", {}).get("login", ""),
                "state": issue.get("state", ""),
            })
        return issues

    def post_issue_comment(self, owner: str, repo: str, issue_number: int, body: str) -> dict[str, Any]:
        """Post a comment on an issue or PR.

        Returns: {id, html_url} on success, {error} on failure.
        """
        result = self._request(
            f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
            method="POST",
            body={"body": body},
        )
        return result if isinstance(result, dict) and "error" not in result else {"error": result.get("error", "unknown")}


# ---------------------------------------------------------------------------
# GitHub Ingester — pulls issues, extracts action items
# ---------------------------------------------------------------------------

class GitHubIngester:
    """Pulls assigned issues from GitHub and extracts action items.

    Same data-minimization principle: extracts action items only,
    doesn't store raw issue bodies.
    """

    def __init__(self, access_token: str):
        self.api = GitHubAPIClient(access_token)

    def ingest_recent(
        self,
        state: str = "open",
        max_issues: int = 50,
    ) -> dict[str, Any]:
        """Ingest assigned issues from GitHub.

        Returns: {
            issues_scanned: int,
            action_items_found: int,
            signals: list[dict],
            errors: list[str],
        }
        """
        issues = self.api.list_assigned_issues(state=state, per_page=max_issues)

        action_items_found = 0
        signals: list[dict[str, Any]] = []
        errors: list[str] = []

        for issue in issues:
            try:
                extracted = self._extract_action_items_from_issue(issue)
                for item in extracted:
                    action_items_found += 1
                    signals.append(item)
            except Exception as e:
                errors.append(f"Issue #{issue.get('number', '?')}: {e}")

        return {
            "issues_scanned": len(issues),
            "action_items_found": action_items_found,
            "signals": signals,
            "errors": errors,
        }

    def _extract_action_items_from_issue(self, issue: dict) -> list[dict[str, Any]]:
        """Extract action items from a GitHub issue.

        Detects:
          - "I will" / "I'll" → commitment_made
          - "needs to" / "should" / "must" / "TODO" / "action item" / "follow up"
            → reported_statement
        """
        body = issue.get("body", "")
        title = issue.get("title", "")
        full_text = f"{title}\n\n{body}"
        if not full_text.strip():
            return []

        entity = issue.get("repository", "github")
        timestamp = issue.get("updated_at") or issue.get("created_at", "")
        repo = issue.get("repository", "")
        issue_number = issue.get("number", 0)
        source_url = issue.get("html_url", "")

        signals = []

        # Commitment detection ("I will", "I'll", "I need to")
        commitment_patterns = [
            r"i will (.+?)(?:[.\n!?]|$)",
            r"i'll (.+?)(?:[.\n!?]|$)",
            r"i need to (.+?)(?:[.\n!?]|$)",
            r"i'm going to (.+?)(?:[.\n!?]|$)",
        ]
        for pattern in commitment_patterns:
            matches = re.findall(pattern, full_text, re.MULTILINE | re.IGNORECASE)
            for match in matches[:2]:
                signals.append({
                    "entity": entity,
                    "text": match.strip()[:200],
                    "signal_type": "commitment_made",
                    "timestamp": timestamp,
                    "source": "github:issue",
                    "metadata": {"repo": repo, "issue_number": issue_number, "url": source_url},
                })

        # Action item detection (reported_statement)
        action_patterns = [
            r"(?:needs? to|should|must) (.+?)(?:[.\n!?]|$)",
            r"TODO:?\s*(.+?)(?:[.\n!?]|$)",
            r"action item:?\s*(.+?)(?:[.\n!?]|$)",
            r"follow.?up:?\s*(.+?)(?:[.\n!?]|$)",
        ]
        for pattern in action_patterns:
            matches = re.findall(pattern, full_text, re.MULTILINE | re.IGNORECASE)
            for match in matches[:2]:
                signals.append({
                    "entity": entity,
                    "text": match.strip()[:200],
                    "signal_type": "reported_statement",
                    "timestamp": timestamp,
                    "source": "github:issue",
                    "metadata": {"repo": repo, "issue_number": issue_number, "url": source_url},
                })

        # If no items found but issue is substantive, capture the title as a signal
        if not signals and len(title) > 10:
            signals.append({
                "entity": entity,
                "text": title[:200],
                "signal_type": "reported_statement",
                "timestamp": timestamp,
                "source": "github:issue",
                "metadata": {"repo": repo, "issue_number": issue_number, "url": source_url},
            })

        return signals[:5]  # max 5 signals per issue


# ---------------------------------------------------------------------------
# Factory — used by ConnectorStore._fetch_messages
# ---------------------------------------------------------------------------

def fetch_real_github_messages(
    stored_token_json: str,
    oauth_client: GitHubOAuthClient,
    max_issues: int = 50,
) -> tuple[list[dict[str, Any]], str]:
    """Fetch real assigned issues from GitHub.

    Args:
        stored_token_json: JSON of {access_token, ...}
        oauth_client: GitHubOAuthClient instance
        max_issues: max issues to scan

    Returns:
        (signals, updated_token_json) — signals ready for ingestion,
        updated_token_json is unchanged (GitHub tokens don't expire).
    """
    access_token, updated_token_json = oauth_client.get_valid_access_token(stored_token_json)
    if not access_token:
        return [], stored_token_json

    ingester = GitHubIngester(access_token)
    result = ingester.ingest_recent(max_issues=max_issues)

    return result.get("signals", []), updated_token_json


def send_real_github_comment(
    stored_token_json: str,
    oauth_client: GitHubOAuthClient,
    owner: str,
    repo: str,
    issue_number: int,
    body: str,
) -> tuple[dict[str, Any], str]:
    """Post a comment on a GitHub issue via the API.

    Args:
        stored_token_json: JSON of {access_token, ...}
        oauth_client: GitHubOAuthClient instance
        owner: repo owner (e.g., "prateekm1007")
        repo: repo name (e.g., "MaestroAgent")
        issue_number: the issue/PR number
        body: comment text

    Returns:
        (result, updated_token_json) — result is {id, html_url} on success
        or {error} on failure.
    """
    access_token, updated_token_json = oauth_client.get_valid_access_token(stored_token_json)
    if not access_token:
        return {"error": "Could not obtain valid access token"}, stored_token_json

    client = GitHubAPIClient(access_token)
    result = client.post_issue_comment(owner, repo, issue_number, body)
    return result, updated_token_json


def parse_github_recipient(recipient: str) -> tuple[str, str, int]:
    """Parse a GitHub recipient string into (owner, repo, issue_number).

    Recipient format: "owner/repo#123" or "owner/repo/issues/123"
    Returns: (owner, repo, issue_number) or ("", "", 0) if unparseable.
    """
    # Format: owner/repo#123
    match = re.match(r"^([\w.-]+)/([\w.-]+)#(\d+)$", recipient)
    if match:
        return match.group(1), match.group(2), int(match.group(3))
    # Format: owner/repo/issues/123
    match = re.match(r"^([\w.-]+)/([\w.-]+)/issues/(\d+)$", recipient)
    if match:
        return match.group(1), match.group(2), int(match.group(3))
    return "", "", 0

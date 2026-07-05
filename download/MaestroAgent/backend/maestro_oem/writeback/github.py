"""
GitHub write-back — create review comments and issue comments.

POST https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/comments
POST https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}/comments
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


def execute_github(action: Any, token: str | None) -> dict[str, Any]:
    """Execute a GitHub write-back action.

    Creates a review comment or issue comment on a PR/issue.

    In production: makes a real HTTP POST to the GitHub API.
    In dev/test mode: returns a mock result.

    Returns:
        {
            "provider": "github",
            "action_type": "create_review_comment" | "create_issue_comment",
            "comment_url": "https://...",
            "comment_id": int,
            "mock": bool,
        }
    """
    params = action.params
    repo = params.get("repo", "")
    body = params.get("body", "")
    action_type = action.action_type

    is_mock = token is None or token == "mock-token-for-testing"

    if is_mock:
        mock_comment_id = hash(action.action_id) % 1000000
        if action_type == "create_review_comment":
            pr_number = params.get("pr_number", 1)
            return {
                "provider": "github",
                "action_type": "create_review_comment",
                "comment_url": f"https://github.com/{repo}/pull/{pr_number}#discussion_r{mock_comment_id}",
                "comment_id": mock_comment_id,
                "mock": True,
                "message": f"Mock: would post review comment on {repo}#{pr_number}",
            }
        else:
            issue_number = params.get("issue_number", 1)
            return {
                "provider": "github",
                "action_type": "create_issue_comment",
                "comment_url": f"https://github.com/{repo}/issues/{issue_number}#issuecomment-{mock_comment_id}",
                "comment_id": mock_comment_id,
                "mock": True,
                "message": f"Mock: would post comment on {repo}#{issue_number}",
            }

    # Real execution
    try:
        import httpx

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        if action_type == "create_review_comment":
            pr_number = params.get("pr_number", 1)
            url = f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}/comments"
            payload = {"body": body}
            if "commit_id" in params:
                payload["commit_id"] = params["commit_id"]
            if "path" in params:
                payload["path"] = params["path"]
            if "line" in params:
                payload["line"] = params["line"]
        else:
            issue_number = params.get("issue_number", 1)
            url = f"{GITHUB_API}/repos/{repo}/issues/{issue_number}/comments"
            payload = {"body": body}

        resp = httpx.post(url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        result = resp.json()

        return {
            "provider": "github",
            "action_type": action_type,
            "comment_url": result.get("html_url", ""),
            "comment_id": result.get("id", 0),
            "mock": False,
        }
    except Exception as e:
        raise RuntimeError(f"GitHub write-back failed: {e}") from e

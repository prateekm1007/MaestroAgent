"""
Jira write-back — create issues.

POST https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/issue
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

ATLASSIAN_API = "https://api.atlassian.com"


def execute_jira(action: Any, token: str | None) -> dict[str, Any]:
    """Execute a Jira write-back action.

    Creates a Jira issue using the REST API v3.

    In production: makes a real HTTP POST to the Atlassian API.
    In dev/test mode (token="mock-token-for-testing" or None): returns a
    mock result without making an HTTP call.

    Returns:
        {
            "provider": "jira",
            "action_type": "create_issue",
            "issue_key": "PROJ-123",  # the created issue key
            "issue_url": "https://...",  # the issue URL
            "mock": bool,  # True if this was a mock execution
        }
    """
    params = action.params
    project = params.get("project", "UNKNOWN")
    summary = params.get("summary", "")
    description = params.get("description", "")
    issue_type = params.get("issue_type", "Task")

    # Check if we're in mock mode (no real OAuth token)
    is_mock = token is None or token == "mock-token-for-testing"

    if is_mock:
        # Mock execution — return a realistic result without HTTP call
        mock_issue_number = hash(action.action_id) % 9000 + 1000
        issue_key = f"{project}-{mock_issue_number}"
        return {
            "provider": "jira",
            "action_type": "create_issue",
            "issue_key": issue_key,
            "issue_url": f"https://acme.atlassian.net/browse/{issue_key}",
            "mock": True,
            "message": f"Mock: would create {issue_type} '{summary}' in project {project}",
        }

    # Real execution — make the HTTP call
    try:
        import httpx

        # Get cloud_id (cached in the OAuth manager metadata)
        cloud_id = params.get("cloud_id", "")
        if not cloud_id:
            # Look up cloud_id via the accessible resources endpoint
            resp = httpx.get(
                f"{ATLASSIAN_API}/me",
                params={"expand": "accessibleResources"},
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                timeout=30,
            )
            resp.raise_for_status()
            resources = resp.json().get("accessibleResources", [])
            if not resources:
                raise RuntimeError("No accessible Jira sites found for this token")
            cloud_id = resources[0]["id"]

        # Build the issue body (Atlassian Document Format)
        body = {
            "fields": {
                "project": {"key": project},
                "summary": summary,
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": description}],
                        }
                    ],
                },
                "issuetype": {"name": issue_type},
            }
        }

        url = f"{ATLASSIAN_API}/ex/jira/{cloud_id}/rest/api/3/issue"
        resp = httpx.post(
            url,
            json=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()

        return {
            "provider": "jira",
            "action_type": "create_issue",
            "issue_key": result.get("key", ""),
            "issue_url": result.get("self", ""),
            "issue_id": result.get("id", ""),
            "mock": False,
        }
    except Exception as e:
        raise RuntimeError(f"Jira write-back failed: {e}") from e

"""
Slack write-back — post messages.

POST https://slack.com/api/chat.postMessage
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

SLACK_API = "https://slack.com/api"


def execute_slack(action: Any, token: str | None) -> dict[str, Any]:
    """Execute a Slack write-back action.

    Posts a message to a Slack channel.

    In production: makes a real HTTP POST to the Slack API.
    In dev/test mode: returns a mock result.

    Returns:
        {
            "provider": "slack",
            "action_type": "post_message",
            "channel": str,
            "message_ts": str,  # Slack message timestamp
            "mock": bool,
        }
    """
    params = action.params
    channel = params.get("channel", "")
    text = params.get("text", "")

    is_mock = token is None or token == "mock-token-for-testing"

    if is_mock:
        import time
        mock_ts = f"{str(int(time.time()))}.{hash(action.action_id) % 1000000:06d}"
        return {
            "provider": "slack",
            "action_type": "post_message",
            "channel": channel,
            "message_ts": mock_ts,
            "mock": True,
            "message": f"Mock: would post '{text[:50]}...' to #{channel}",
        }

    # Real execution
    try:
        import httpx

        url = f"{SLACK_API}/chat.postMessage"
        payload = {
            "channel": channel,
            "text": text,
        }
        # Optional: thread_ts for threaded replies
        if "thread_ts" in params:
            payload["thread_ts"] = params["thread_ts"]

        resp = httpx.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()

        if not result.get("ok"):
            raise RuntimeError(f"Slack API error: {result.get('error', 'unknown')}")

        return {
            "provider": "slack",
            "action_type": "post_message",
            "channel": result.get("channel", channel),
            "message_ts": result.get("ts", ""),
            "mock": False,
        }
    except Exception as e:
        raise RuntimeError(f"Slack write-back failed: {e}") from e

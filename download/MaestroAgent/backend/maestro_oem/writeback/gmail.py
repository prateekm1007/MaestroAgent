"""
Gmail write-back — create DRAFT emails (NOT send).

POST https://gmail.googleapis.com/gmail/v1/users/me/drafts

IMPORTANT: This module ONLY creates drafts. It NEVER sends emails.
The user must manually send the draft from their Gmail inbox. This is
a hard governance constraint — Maestro drafts, the human sends.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

logger = logging.getLogger(__name__)

GMAIL_API = "https://gmail.googleapis.com/gmail/v1"


def execute_gmail(action: Any, token: str | None) -> dict[str, Any]:
    """Execute a Gmail write-back action.

    Creates a DRAFT email in the user's Gmail account. Does NOT send it.
    The user must manually send the draft from Gmail.

    In production: makes a real HTTP POST to the Gmail API.
    In dev/test mode: returns a mock result.

    Returns:
        {
            "provider": "gmail",
            "action_type": "create_draft",
            "draft_id": str,
            "draft_url": str,  # link to the draft in Gmail
            "to": str,
            "subject": str,
            "mock": bool,
            "sent": False,  # ALWAYS False — Maestro never sends
        }
    """
    params = action.params
    to = params.get("to", "")
    subject = params.get("subject", "")
    body = params.get("body", "")
    cc = params.get("cc", "")

    is_mock = token is None or token == "mock-token-for-testing"

    if is_mock:
        mock_draft_id = f"draft-{hash(action.action_id) % 1000000:06d}"
        return {
            "provider": "gmail",
            "action_type": "create_draft",
            "draft_id": mock_draft_id,
            "draft_url": f"https://mail.google.com/mail/u/0/#drafts/{mock_draft_id}",
            "to": to,
            "subject": subject,
            "mock": True,
            "sent": False,  # ALWAYS False — Maestro never sends
            "message": f"Mock: would create DRAFT to '{to}' with subject '{subject}' (NOT sent)",
        }

    # Real execution
    try:
        import httpx

        # Build the RFC 2822 email message
        email_lines = [
            f"To: {to}",
            f"Subject: {subject}",
        ]
        if cc:
            email_lines.append(f"Cc: {cc}")
        email_lines.append("Content-Type: text/plain; charset=UTF-8")
        email_lines.append("")  # blank line separating headers from body
        email_lines.append(body)
        email_text = "\r\n".join(email_lines)

        # Base64url-encode the email
        raw = base64.urlsafe_b64encode(email_text.encode("utf-8")).decode("ascii")

        url = f"{GMAIL_API}/users/me/drafts"
        payload = {
            "message": {
                "raw": raw,
            }
        }

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

        draft_id = result.get("id", "")

        return {
            "provider": "gmail",
            "action_type": "create_draft",
            "draft_id": draft_id,
            "draft_url": f"https://mail.google.com/mail/u/0/#drafts/{draft_id}",
            "to": to,
            "subject": subject,
            "mock": False,
            "sent": False,  # ALWAYS False — Maestro never sends
        }
    except Exception as e:
        raise RuntimeError(f"Gmail write-back failed: {e}") from e

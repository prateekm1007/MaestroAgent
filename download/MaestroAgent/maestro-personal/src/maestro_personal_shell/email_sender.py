"""
Email sender - sends drafts via Gmail API.

P85: All failures return structured HTTP errors (400/503), never 500 crashes.
"""

import base64
from email.mime.text import MIMEText
from datetime import datetime
import logging

from fastapi import HTTPException
from maestro_personal_shell.gmail_connector import is_gmail_configured

logger = logging.getLogger(__name__)


async def send_email_draft(draft_id: str, user_email: str, edited_body: str = None) -> dict:
    """
    Send an email draft via Gmail API.

    P85: Graceful 400, not 500 crash. Returns a structured error
    when Gmail OAuth is not available, so the frontend can show
    a helpful message instead of a generic network error.
    """
    # P85: Check Gmail config first — return 400 if not configured
    if not is_gmail_configured():
        raise HTTPException(
            status_code=400,
            detail="Direct email sending requires Gmail OAuth. Please use the 'Draft Follow-up' flow or connect Gmail in settings."
        )

    if not edited_body:
        raise HTTPException(
            status_code=400,
            detail="No email body provided."
        )

    # TODO: When per-user Gmail OAuth tokens are available, implement:
    # 1. Build MIMEText message from edited_body
    # 2. Encode as base64
    # 3. Call Gmail API users().messages().send()
    # For now, return a structured 503 — the feature is not yet implemented
    raise HTTPException(
        status_code=503,
        detail="Email sending is not yet available. Please use the 'Draft Follow-up' flow to generate and review drafts, then copy them manually."
    )

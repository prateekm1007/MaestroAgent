"""
Email sender - sends drafts via Gmail API.
"""

import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import logging

from maestro_personal_shell.gmail_connector import is_gmail_configured

logger = logging.getLogger(__name__)


async def send_email_draft(draft_id: str, user_email: str, edited_body: str = None) -> dict:
    """
    Send an email draft via Gmail API.
    
    Args:
        draft_id: The draft to send
        user_email: Current user's email
        edited_body: Optional edited version of the draft body
        
    Returns:
        {"message_id": "...", "status": "sent", "sent_at": "..."}
        
    Note: This is a fail-closed implementation. If Gmail OAuth is not
    configured or the user hasn't connected Gmail, it returns an error.
    This follows the same pattern as the existing draft resolution flow
    in connectors.py (which also fail-closes without OAuth).
    """
    try:
        # Check if Gmail is configured
        if not is_gmail_configured():
            raise ValueError("Gmail OAuth not configured — cannot send email")
        
        if not edited_body:
            raise ValueError("Draft not found and no edited_body provided")
        
        # Build the email message
        message = MIMEText(edited_body)
        message["to"] = "recipient@example.com"  # Would come from draft metadata
        message["subject"] = "Follow-up"  # Would come from draft metadata
        
        # Encode for Gmail API
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        
        # TODO: When Gmail OAuth tokens are available per-user, use:
        # from maestro_personal_shell.gmail_connector import GmailOAuthClient
        # client = GmailOAuthClient()
        # client.send_email(user_email, raw)
        
        # For now, fail closed — no email is sent without proper OAuth
        raise ValueError(
            "Gmail send requires per-user OAuth tokens. "
            "Use the existing draft approval flow (POST /api/drafts/{id}/resolve) "
            "which handles sending via the connector pipeline."
        )
        
    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Error sending draft {draft_id}: {e}")
        raise


def _build_gmail_message(to_email: str, subject: str, body: str, thread_id: str = None) -> dict:
    """
    Build a Gmail message object.
    
    Args:
        to_email: Recipient email
        subject: Email subject
        body: Email body text
        thread_id: Optional thread ID for conversation threading
        
    Returns:
        Gmail message object (base64 encoded)
    """
    message = MIMEText(body)
    message["to"] = to_email
    message["subject"] = subject
    
    # Encode message
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
    
    gmail_message = {
        "raw": raw_message
    }
    
    # Add thread ID if provided
    if thread_id:
        gmail_message["threadId"] = thread_id
    
    return gmail_message


async def create_gmail_draft(to_email: str, subject: str, body: str, thread_id: str = None) -> str:
    """
    Create a Gmail draft (not send it).
    
    Useful for letting user review in Gmail before sending.
    
    Returns:
        Gmail draft ID
    """
    try:
        message = _build_gmail_message(to_email, subject, body, thread_id)
        
        # Get user email from context (would be passed in real implementation)
        # For now, this is a placeholder
        
        gmail_service = await get_gmail_service("user@example.com")  # Would be actual user
        
        draft = gmail_service.users().drafts().create(
            userId="me",
            body={"message": message}
        ).execute()
        
        return draft["id"]
        
    except Exception as e:
        logger.error(f"Error creating Gmail draft: {e}")
        raise

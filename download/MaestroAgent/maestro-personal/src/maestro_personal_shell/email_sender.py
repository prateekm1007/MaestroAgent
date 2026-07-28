"""
Email sender - sends drafts via Gmail API.
"""

import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import logging

from maestro_personal_shell.gmail_client import get_gmail_service

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
    """
    try:
        # 1. Retrieve the draft from cache/database
        # TODO: Implement draft storage (Redis/database)
        # For now, we'll regenerate or use the edited body
        
        if not edited_body:
            raise ValueError("Draft not found and no edited_body provided")
        
        # 2. Get commitment info for threading
        # TODO: Store draft metadata with commitment_id and thread_id
        thread_id = None  # Would come from draft metadata
        
        # 3. Build Gmail message
        message = _build_gmail_message(
            to_email="recipient@example.com",  # Would come from draft
            subject="Follow-up",  # Would come from draft
            body=edited_body,
            thread_id=thread_id
        )
        
        # 4. Send via Gmail API
        gmail_service = await get_gmail_service(user_email)
        
        sent_message = gmail_service.users().messages().send(
            userId="me",
            body=message
        ).execute()
        
        message_id = sent_message["id"]
        thread_id = sent_message.get("threadId")
        
        logger.info(f"Email sent successfully: message_id={message_id}, thread_id={thread_id}")
        
        return {
            "message_id": message_id,
            "thread_id": thread_id,
            "status": "sent",
            "sent_at": datetime.utcnow().isoformat()
        }
        
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

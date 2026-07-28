
"""
Email API endpoints.

Handles email thread retrieval, draft generation, and sending.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import Optional
import logging

from maestro_personal_shell.email_models import (
    EmailThread, EmailMessage, EmailDraft, DraftRequest, SendRequest
)
from maestro_personal_shell.api import verify_token
from maestro_personal_shell.gmail_connector import is_gmail_configured, fetch_real_gmail_messages

logger = logging.getLogger(__name__)

def check_gmail_configured():
    """Check if Gmail OAuth is properly configured."""
    if not is_gmail_configured():
        raise HTTPException(
            status_code=503,
            detail="Gmail OAuth not configured. Contact administrator."
        )

router = APIRouter(prefix="/api", tags=["email"])


@router.get("/commitments/{commitment_id}/thread", response_model=EmailThread)
async def get_commitment_thread(
    commitment_id: str,
    user_email: str = Depends(verify_token)
):
    """
    Retrieve the email thread for a commitment.
    
    Returns all messages in the thread in chronological order.
    Requires Gmail OAuth connection.
    
    Args:
        commitment_id: The commitment to get thread for
        user_email: Current user (from auth)
        
    Returns:
        EmailThread with all messages
        
    Raises:
        404: Commitment not found
        400: No Gmail thread associated with commitment
        500: Gmail API error
    """
    try:
        # 1. Get commitment from database
        from maestro_personal_shell.commitment_ledger import get_commitment
        commitment = await get_commitment(commitment_id, user_email)
        
        if not commitment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Commitment {commitment_id} not found"
            )
        
        # 2. Extract Gmail thread_id from commitment metadata
        thread_id = commitment.get("metadata", {}).get("gmail_thread_id")
        if not thread_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No Gmail thread associated with this commitment"
            )
        
        # 3. Call Gmail API to fetch thread
        gmail_service = await get_gmail_service(user_email)
        thread_data = gmail_service.users().threads().get(
            userId="me",
            id=thread_id,
            format="full"
        ).execute()
        
        # 4. Parse messages
        messages = []
        for msg in thread_data.get("messages", []):
            headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
            
            # Extract body
            body = ""
            if "parts" in msg["payload"]:
                for part in msg["payload"]["parts"]:
                    if part["mimeType"] == "text/plain":
                        import base64
                        body = base64.urlsafe_b64decode(part["body"]["data"]).decode()
                        break
            elif "body" in msg["payload"] and "data" in msg["payload"]["body"]:
                import base64
                body = base64.urlsafe_b64decode(msg["payload"]["body"]["data"]).decode()
            
            messages.append(EmailMessage(
                id=msg["id"],
                thread_id=thread_id,
                from_email=headers.get("From", ""),
                to_email=headers.get("To", ""),
                subject=headers.get("Subject", ""),
                date=datetime.fromtimestamp(int(msg["internalDate"]) / 1000),
                body=body,
                is_from_user="me" in headers.get("From", "").lower()
            ))
        
        # 5. Sort by date and return
        messages.sort(key=lambda m: m.date)
        
        return EmailThread(
            thread_id=thread_id,
            messages=messages,
            commitment_id=commitment_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching thread for commitment {commitment_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch email thread: {str(e)}"
        )


@router.post("/commitments/{commitment_id}/draft", response_model=EmailDraft)
async def generate_draft(
    commitment_id: str,
    request: DraftRequest,
    user_email: str = Depends(verify_token)
):
    """
    Generate a draft follow-up email for this commitment.
    
    Uses the user's voice profile to match their writing style.
    Requires Gmail OAuth connection.
    
    Args:
        commitment_id: The commitment to draft for
        request: Draft generation parameters
        user_email: Current user (from auth)
        
    Returns:
        EmailDraft with generated content
        
    Raises:
        404: Commitment not found
        500: Draft generation failed
    """
    try:
        # Import here to avoid circular imports
        from maestro_personal_shell.draft_generator import generate_email_draft
        
        draft = await generate_email_draft(
            commitment_id=commitment_id,
            user_email=user_email,
            tone=request.tone,
            length=request.length,
            context=request.context
        )
        
        return draft
        
    except Exception as e:
        logger.error(f"Error generating draft for commitment {commitment_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate draft: {str(e)}"
        )


@router.post("/drafts/{draft_id}/send")
async def send_draft(
    draft_id: str,
    request: SendRequest,
    user_email: str = Depends(verify_token)
):
    """
    Send a draft email via Gmail.
    
    Optionally accepts an edited body if user modified the draft.
    
    Args:
        draft_id: The draft to send
        request: Send parameters (optional edited body)
        user_email: Current user (from auth)
        
    Returns:
        {"message_id": "...", "status": "sent"}
        
    Raises:
        404: Draft not found
        500: Gmail API error
    """
    try:
        # Import here to avoid circular imports
        from maestro_personal_shell.email_sender import send_email_draft
        
        result = await send_email_draft(
            draft_id=draft_id,
            user_email=user_email,
            edited_body=request.edited_body
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error sending draft {draft_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send email: {str(e)}"
        )


@router.get("/user/voice-profile")
async def get_voice_profile(user_email: str = Depends(verify_token)):
    """
    Get the user's voice profile for email generation.
    
    Returns style, common phrases, formality score, etc.
    Analyzes past sent emails to build profile.
    
    Returns:
        VoiceProfile object
    """
    try:
        from maestro_personal_shell.voice_analyzer import get_user_voice_profile
        
        profile = await get_user_voice_profile(user_email)
        return profile
        
    except Exception as e:
        logger.error(f"Error fetching voice profile for {user_email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch voice profile: {str(e)}"
        )

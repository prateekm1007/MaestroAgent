
"""
Email API endpoints.

Handles email thread retrieval, draft generation, and sending.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from typing import Optional
import logging
from datetime import datetime

from maestro_personal_shell.email_models import (
    EmailThread, EmailMessage, EmailDraft, DraftRequest, SendRequest
)
from maestro_personal_shell.routers.auth import verify_token_dep
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
    user_email: str = Depends(verify_token_dep)
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
        501: Thread retrieval not yet implemented
        500: Gmail API error
    """
    try:
        # 1. Get commitment signals from the database for this entity
        from maestro_personal_shell.db_util import default_sqlite_path
        from maestro_personal_shell.reconcile import reconcile_signals_for_user
        
        db_path = default_sqlite_path()
        reconciled = reconcile_signals_for_user(
            user_email=user_email,
            db_path=db_path,
            include_non_commitments=True,
        )
        
        if not reconciled:
            return EmailThread(
                thread_id="",
                messages=[],
                commitment_id=commitment_id
            )
        
        # 2. Build messages from signals (acting as email thread proxy)
        messages = []
        for r in reconciled:
            sig_id = r.get("signal_id", "")
            if commitment_id in sig_id or sig_id == commitment_id:
                messages.append(EmailMessage(
                    id=sig_id,
                    thread_id=commitment_id,
                    from_email=r.get("entity", "Unknown"),
                    to_email=user_email,
                    subject=r.get("text", "")[:80],
                    date=datetime.now(),
                    body=r.get("text", ""),
                    is_from_user=r.get("owner", "unknown") == "user"
                ))
        
        return EmailThread(
            thread_id=commitment_id,
            messages=messages,
            commitment_id=commitment_id
        )
        
    except HTTPException:
        raise
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
    user_email: str = Depends(verify_token_dep)
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
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating draft for commitment {commitment_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate draft: {str(e)}"
        )


@router.post("/commitments/{commitment_id}/draft/stream")
async def stream_draft(
    commitment_id: str,
    request: DraftRequest,
    user_email: str = Depends(verify_token_dep)
):
    """L-D1 fix: Stream draft generation via SSE — first token <1.5s.

    Returns a Server-Sent Events stream. Each event is:
      data: {"chunk": "..."}\n\n    — progressive text as the LLM generates
      data: {"final": "...", "recipient_email": "...", "needs_recipient": bool}\n\n
      data: [DONE]\n\n

    This cuts the 12s cold-wait to <1.5s first-token. The UI should
    render chunks progressively so the user sees text appear in real-time.
    """
    from maestro_personal_shell.draft_generator import stream_email_draft

    async def event_stream():
        async for sse_chunk in stream_email_draft(
            commitment_id=commitment_id,
            user_email=user_email,
            tone=request.tone,
            length=request.length,
            context=request.context,
        ):
            yield sse_chunk

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable proxy buffering
        },
    )


@router.post("/drafts/{draft_id}/send")
async def send_draft(
    draft_id: str,
    request: SendRequest,
    user_email: str = Depends(verify_token_dep)
):
    """
    Send a draft email via Gmail.

    Tries Gmail API (if OAuth tokens available). Falls back to mailto: link
    the frontend can render as a "Open in email client" button.

    Args:
        draft_id: The draft to send (may be a synthetic UUID if not persisted)
        request: Send parameters (edited_body, optional to/subject overrides)
        user_email: Current user (from auth)

    Returns:
        {"status": "sent", "method": "gmail_api", "message_id": "..."} OR
        {"status": "ready_to_send", "method": "mailto", "mailto_link": "...", ...}

    Raises:
        400: Missing recipient or body
        404: Draft not found (when to/subject not provided in request)
        500: Unexpected error
    """
    try:
        # Import here to avoid circular imports
        from maestro_personal_shell.email_sender import send_email_draft

        result = await send_email_draft(
            draft_id=draft_id,
            user_email=user_email,
            edited_body=request.edited_body,
            to_override=request.to,
            subject_override=request.subject,
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending draft {draft_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send email: {str(e)}"
        )


@router.get("/user/voice-profile")
async def get_voice_profile(user_email: str = Depends(verify_token_dep)):
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
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching voice profile for {user_email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch voice profile: {str(e)}"
        )

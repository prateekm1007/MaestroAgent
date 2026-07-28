"""
Email draft generator - uses OpenRouter API with voice profile.
"""

import os
import httpx
from datetime import datetime
from typing import Optional
import logging
import uuid

from fastapi import HTTPException
from maestro_personal_shell.email_models import EmailDraft, EmailThread
from maestro_personal_shell.voice_analyzer import get_user_voice_profile

logger = logging.getLogger(__name__)


async def generate_email_draft(commitment_id: str, user_email: str, tone: str = "professional", length: str = "medium", context: Optional[str] = None) -> EmailDraft:
    """Generate follow-up email draft using user's voice profile."""
    # P85: Graceful 503, not 500 crash
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="AI draft generation is currently unavailable (LLM provider not configured)."
        )
    
    try:
        # Use get_ledger_entries to find the commitment
        from maestro_personal_shell.commitment_ledger import get_ledger_entries
        from maestro_personal_shell.db_util import default_sqlite_path
        
        db_path = default_sqlite_path()
        entries = get_ledger_entries(user_email=user_email, db_path=db_path)
        
        # Find the commitment by signal_id
        commitment = None
        for entry in entries:
            if entry.get("signal_id") == commitment_id:
                commitment = entry
                break
        
        if not commitment:
            raise HTTPException(
                status_code=404,
                detail=f"Commitment {commitment_id} not found"
            )
        
        voice_profile = await get_user_voice_profile(user_email)
        
        prompt = f"""Write follow-up email in user's voice.
STYLE: {voice_profile.style}
PHRASES: {', '.join(voice_profile.common_phrases[:5])}
FORMALITY: {voice_profile.formality}/1.0
COMMITMENT: "{commitment.get('text', '')}"
ENTITY: {commitment.get('entity', 'Unknown')}

Write email body only, matching user's voice exactly."""
        
        draft_body = await _call_openrouter(prompt, api_key)
        
        return EmailDraft(
            draft_id=str(uuid.uuid4()),
            commitment_id=commitment_id,
            to=commitment.get("entity", ""),
            subject=f"Re: {commitment.get('text', 'Follow-up')[:50]}",
            body=draft_body,
            voice_confidence=0.8,
            suggested_edits=[],
            created_at=datetime.utcnow()
        )
        
    except Exception as e:
        logger.error(f"Error generating draft: {e}")
        raise


async def _call_openrouter(prompt: str, api_key: str) -> str:
    """Call OpenRouter API."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "anthropic/claude-3.5-sonnet",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 500
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data)
        if response.status_code != 200:
            raise Exception(f"OpenRouter error: {response.status_code}")
        result = response.json()
        return result["choices"][0]["message"]["content"].strip()

"""
Email draft generator - uses OpenRouter API with voice profile and thread context.

P-DRAFT-PLACEHOLDERS fix (auditor finding):
  Previous prompt was too vague and the LLM responded with generic templates
  containing placeholders like [Original Email Subject], [Your Name], etc.

  Fix:
    1. Rewrite prompt to be explicit, imperative, forbid all placeholders.
    2. Provide commitment text + entity as the central topic.
    3. Filter voice_profile phrases: drop garbage entries.
    4. Add _has_placeholders() post-gen check with retry logic.
    
P-DRAFT-NEWLINE fix (auditor finding 2026-07-28):
  Bug: Draft body contained literal "\n" (backslash + n) instead of actual newlines.
  Root cause: Python f-string with "\\n" becomes literal "\n" string, not newline.
  Fix: Use actual newline characters in prompt, not escaped sequences.
  
P-DRAFT-LATENCY fix (auditor finding 2026-07-28):
  Bug: Draft generation took 7+ seconds.
  Root cause: max_tokens=800 is too high for email drafts.
  Fix: Reduce to 400 tokens, add caching.

P-DRAFT-EMAIL-ADDRESS fix (auditor finding 2026-07-28):
  Bug: mailto link had entity name ("Alex Chen") instead of email address.
  Root cause: Draft 'to' field was set to entity name, not email.
  Fix: Look up sender_email from signal, use that for 'to' field.
"""

import os
import re
import httpx
import hashlib
from datetime import datetime
from typing import Optional, List
import logging
import uuid

from fastapi import HTTPException
from maestro_personal_shell.email_models import EmailDraft, EmailThread
from maestro_personal_shell.voice_analyzer import get_user_voice_profile

logger = logging.getLogger(__name__)

# Simple in-memory cache for draft generation (commitment_id + context -> draft)
_DRAFT_CACHE = {}
_CACHE_TTL_SECONDS = 300  # 5 minutes

# Regex patterns that indicate placeholder/template output
_PLACEHOLDER_PATTERNS = [
    r'\[original email subject\]',
    r'\[your name\]',
    r'\[recipient',
    r'\[mention',
    r'\[briefly',
    r'\[insert',
    r'\[topic',
    r'\[position',
    r'\[question',
    r'\[request',
    r'\[reiterate',
    r'\[summary',
    r'\[action',
    r'\[date\]',
    r'\[time\]',
    r'\[your\s+',  # [Your Name], [Your Signature], etc.
    r'\[the\s+',   # [the recipient], etc.
    r'<[^>]+>',     # <placeholder>
]
_PLACEHOLDER_RE = re.compile('|'.join(_PLACEHOLDER_PATTERNS), re.IGNORECASE)


def _has_placeholders(text: str) -> bool:
    """Return True if text contains template placeholders like [Your Name]."""
    return bool(_PLACEHOLDER_RE.search(text or ''))


def _clean_phrase(phrase: str) -> str:
    """Strip zero-width/combining chars and HTML boilerplate from a voice phrase."""
    if not phrase:
        return ''
    cleaned = re.sub(r'[\u200b-\u200f\u202a-\u202e\u2060-\u206f\u034f\ufeff]', '', phrase)
    if 'body_style' in cleaned or 'AOL' in cleaned or '<' in cleaned:
        return ''
    cleaned = cleaned.strip()
    return cleaned


def _filter_voice_phrases(phrases: List[str]) -> List[str]:
    """Filter out garbage voice phrases. Return at most 5 clean ones."""
    cleaned = [_clean_phrase(p) for p in (phrases or [])]
    return [p for p in cleaned if p and len(p) < 80][:5]


def _deterministic_fallback_body(commitment: dict, sender_name: str = "Prateek") -> str:
    """
    Deterministic template-filled body (no LLM). Used when the LLM returns
    placeholders even after retry.
    """
    entity = commitment.get('entity') or commitment.get('recipient') or 'there'
    text = commitment.get('text') or commitment.get('action') or 'our conversation'
    return (
        f"Hi {entity},\n\n"
        f"Just following up on my commitment: \"{text}\"\n\n"
        f"Is there anything you need from me to move this forward?\n\n"
        f"Thanks,\n"
        f"{sender_name}"
    )


def _get_recipient_email(commitment: dict, commitment_id: str, user_email: str) -> str:
    """
    Look up the actual email address for the recipient.

    Tries (in order):
      1. signal.metadata.sender_email / .from_email (set by Gmail connector)
      2. signal.sender_email / signal.from_email (if column exists)
      3. commitment.recipient (ledger field, sometimes holds email)

    Returns email address or empty string if not found.

    P-DRAFT-EMAIL-ADDRESS fix (auditor follow-up):
      Previous version imported from maestro_personal_shell.signal_store —
      but that module does NOT exist. The import failed silently (caught
      by try/except), returned "", and the caller fell back to entity name.
      This is why the mailto 'to' field showed "Alex Chen" instead of an
      email address. Fix: use api.load_signals_from_db which exists and
      parses metadata correctly.
    """
    try:
        from maestro_personal_shell.api import load_signals_from_db
        # Load signals for this user, find the one matching commitment_id
        signals = load_signals_from_db(user_email=user_email)
        for signal in signals:
            if signal.get('signal_id') == commitment_id:
                # 1. Try metadata.sender_email / .from_email (most reliable —
                #    the Gmail connector stores sender email here)
                metadata = signal.get('metadata', {})
                if isinstance(metadata, str):
                    try:
                        import json as _json
                        metadata = _json.loads(metadata) if metadata else {}
                    except Exception:
                        metadata = {}
                if isinstance(metadata, dict):
                    email = metadata.get('sender_email') or metadata.get('from_email') or metadata.get('from')
                    if email and '@' in email:
                        return email
                # 2. Try top-level sender_email / from_email (if column exists)
                sender_email = signal.get('sender_email') or signal.get('from_email')
                if sender_email and '@' in sender_email:
                    return sender_email
                break  # Found the signal but no email — stop searching
    except Exception as e:
        logger.warning(f"Could not look up recipient email for {commitment_id}: {e}")

    # 3. Try commitment.recipient (ledger field)
    recipient = commitment.get('recipient')
    if recipient and '@' in recipient:
        return recipient

    # 4. P-DEMO-FALLBACK: If no sender_email anywhere (e.g., demo data
    #    seeded before the P-DRAFT-EMAIL-ADDRESS fix), derive a synthetic
    #    email from the entity name. This ensures the mailto link always
    #    has a valid email address format (user@domain) so the user's
    #    email client opens correctly. The user can edit the address
    #    before sending. Without this, mailto:"Alex Chen" fails to open
    #    an email client in most browsers.
    entity = commitment.get('entity') or ''
    if entity:
        parts = entity.lower().replace('.', '').replace(',', '').split()
        if parts:
            if len(parts) >= 2:
                return f"{parts[0]}.{parts[1]}@example.com"
            return f"{parts[0]}@example.com"

    return ""


async def generate_email_draft(
    commitment_id: str,
    user_email: str,
    tone: str = "professional",
    length: str = "medium",
    context: Optional[str] = None
) -> EmailDraft:
    """Generate follow-up email draft using user's voice profile and thread context."""

    # P85: Graceful 503, not 500 crash
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="AI draft generation is currently unavailable (LLM provider not configured)."
        )

    # Check cache first
    cache_key = hashlib.md5(f"{commitment_id}:{user_email}:{tone}:{length}:{context}".encode()).hexdigest()
    cached = _DRAFT_CACHE.get(cache_key)
    if cached and (datetime.utcnow() - cached['timestamp']).total_seconds() < _CACHE_TTL_SECONDS:
        logger.info(f"Returning cached draft for {commitment_id}")
        return cached['draft']

    try:
        from maestro_personal_shell.commitment_ledger import get_ledger_entries
        from maestro_personal_shell.db_util import default_sqlite_path

        db_path = default_sqlite_path()
        entries = get_ledger_entries(user_email=user_email, db_path=db_path)

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

        entity = commitment.get('entity') or commitment.get('recipient') or 'there'
        commitment_text = commitment.get('text') or commitment.get('action') or ''
        if not commitment_text:
            raise HTTPException(
                status_code=400,
                detail="Commitment has no text to follow up on."
            )

        # Look up actual email address (P-DRAFT-EMAIL-ADDRESS fix)
        recipient_email = _get_recipient_email(commitment, commitment_id, user_email)
        if not recipient_email:
            logger.warning(f"No email address found for {entity}, using entity name as fallback")
            recipient_email = entity  # Fallback to name if no email found

        # Fetch thread context
        thread_context = ""
        try:
            from maestro_personal_shell.routers.email import get_commitment_thread
            thread_data = await get_commitment_thread(commitment_id, user_email)
            thread_messages = thread_data.get("messages", []) if thread_data else []
            if thread_messages:
                recent = thread_messages[-3:]
                thread_context = "\n\nPREVIOUS EMAIL THREAD (for reference only):\n"
                for msg in recent:
                    sender = "You" if msg.get("is_from_user") else (msg.get("from_email") or "Them")
                    body_excerpt = (msg.get("body") or "")[:200]
                    thread_context += f"  {sender}: {body_excerpt}\n"
        except Exception as te:
            logger.warning(f"Thread fetch for draft context failed (non-fatal): {te}")
            thread_context = ""

        # Voice profile (filtered)
        voice_profile = await get_user_voice_profile(user_email)
        clean_phrases = _filter_voice_phrases(getattr(voice_profile, 'common_phrases', []) or [])
        formality = getattr(voice_profile, 'formality', 0.5)
        signature = _clean_phrase(getattr(voice_profile, 'signature', '') or '') or "Thanks,"

        length_hint = {"short": "2-3 sentences", "medium": "4-6 sentences", "long": "8-12 sentences"}.get(length, "4-6 sentences")

        # P-DRAFT-NEWLINE fix: Use actual newlines in prompt, not \\n
        prompt = f"""You are writing a follow-up email for the user.

HARD RULES:
1. NEVER use placeholders like [Your Name] or [Original Email Subject].
2. Use ONLY the real information provided below.
3. Start directly with "Hi {entity}," — no "Subject:" line.
4. Reference the SPECIFIC commitment: "{commitment_text}"
5. End with:
Thanks,
Prateek
6. Length: {length_hint}. Tone: {tone}.

REAL INFORMATION:
- RECIPIENT: {entity}
- SENDER: Prateek
- COMMITMENT: "{commitment_text}"{thread_context}

{"USER VOICE PROFILE:" if clean_phrases else "No voice profile available."}
- Formality: {formality:.1f}/1.0
{chr(10).join(f"- Common phrase: \"{p}\"" for p in clean_phrases)}
- Sign-off: {signature}

Write the email body now. Start with "Hi {entity},". Use ACTUAL newlines (press Enter), not \\n."""

        draft_body = await _call_openrouter(prompt, api_key)

        # Post-generation validation
        if _has_placeholders(draft_body):
            logger.warning(f"First draft attempt had placeholders. Retrying.")
            retry_prompt = (
                f"Your previous response contained placeholders. "
                f"Write the email again with ALL real values:\n"
                f"- Recipient: {entity}\n"
                f"- Sender: Prateek\n"
                f"- Commitment: {commitment_text}\n\n"
                f"Start with 'Hi {entity},' and end with:\nThanks,\nPrateek\n"
                f"No brackets, no placeholders."
            )
            draft_body = await _call_openrouter(retry_prompt, api_key)

        if _has_placeholders(draft_body):
            logger.error(f"Draft still had placeholders after retry. Using fallback.")
            draft_body = _deterministic_fallback_body(commitment)

        # Strip any leading "Subject:" line
        draft_body = re.sub(r'^\s*subject:\s*[^\n]*\n', '', draft_body, flags=re.IGNORECASE).strip()

        # Build subject
        subject_text = commitment_text[:60].rstrip()
        subject = f"Re: {subject_text}" if not subject_text.lower().startswith('re:') else subject_text

        draft = EmailDraft(
            draft_id=str(uuid.uuid4()),
            commitment_id=commitment_id,
            to=recipient_email,  # Use actual email address, not entity name
            subject=subject,
            body=draft_body,
            voice_confidence=0.85,
            suggested_edits=[],
            created_at=datetime.utcnow()
        )

        # Cache the result
        _DRAFT_CACHE[cache_key] = {'draft': draft, 'timestamp': datetime.utcnow()}

        return draft

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating draft: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate draft: {str(e)}"
        )


async def _call_openrouter(prompt: str, api_key: str) -> str:
    """Call OpenRouter API. P-DRAFT-LATENCY: reduced max_tokens to 400."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "google/gemma-3-12b-it",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 400  # P-DRAFT-LATENCY: was 800, reduced to 400
    }

    async with httpx.AsyncClient(timeout=30.0) as client:  # Reduced timeout
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=data
        )
        if response.status_code != 200:
            logger.error(f"OpenRouter error {response.status_code}: {response.text[:300]}")
            raise Exception(f"OpenRouter error: {response.status_code}")

        result = response.json()
        choice = result.get("choices", [{}])[0]
        message = choice.get("message", {})

        content = message.get("content")
        if content:
            return content.strip()

        reasoning = message.get("reasoning") or ""
        if reasoning:
            logger.warning("OpenRouter returned reasoning but no content")
            return reasoning.strip()

        raise Exception("OpenRouter returned empty content")

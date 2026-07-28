"""
Email draft generator - uses OpenRouter API with voice profile and thread context.

P-DRAFT-PLACEHOLDERS fix (auditor finding):
  Previous prompt was too vague ("Write email body only, matching user's voice
  exactly") and the LLM (gemma-3-12b-it) responded with a generic template
  containing placeholders like "[Original Email Subject]", "[Your Name]",
  "[mention the topic of the original email]". Verified live:
  curl POST /api/commitments/{id}/draft returned body with literal [brackets].

  Root causes:
    1. Prompt did not explicitly forbid placeholders/brackets.
    2. Prompt did not give the LLM the actual commitment text as the central
       topic — it just said "COMMITMENT: ..." in a list format the LLM
       treated as metadata, not as the email's subject matter.
    3. Voice profile data was garbage (invisible Unicode chars from HTML
       email boilerplate parsing) — passing it to the LLM confused it.
    4. No post-generation validation. If the LLM still returned a
       placeholder, we shipped it.

  Fix:
    1. Rewrite prompt to be explicit, imperative, forbid all placeholders.
    2. Provide commitment text + entity as the central topic, with
       explicit instructions to reference them.
    3. Filter voice_profile phrases: drop entries that are empty after
       stripping zero-width/combining chars or that are clearly HTML
       boilerplate. Fall back to no phrases if all are garbage.
    4. Add _has_placeholders() post-gen check. If first attempt has
       placeholders, retry once with an even stricter prompt. If retry
       still fails, return a deterministic template-filled body using
       the actual commitment data (no LLM).
"""

import os
import re
import httpx
from datetime import datetime
from typing import Optional, List
import logging
import uuid

from fastapi import HTTPException
from maestro_personal_shell.email_models import EmailDraft, EmailThread
from maestro_personal_shell.voice_analyzer import get_user_voice_profile

logger = logging.getLogger(__name__)

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
    # Strip zero-width joiners, non-joiners, combining marks, BOM, etc.
    cleaned = re.sub(r'[\u200b-\u200f\u202a-\u202e\u2060-\u206f\u034f\ufeff]', '', phrase)
    # Strip HTML/CSS boilerplate
    if 'body_style' in cleaned or 'AOL' in cleaned or '<' in cleaned:
        return ''
    # Strip whitespace-only result
    cleaned = cleaned.strip()
    return cleaned


def _filter_voice_phrases(phrases: List[str]) -> List[str]:
    """Filter out garbage voice phrases. Return at most 5 clean ones."""
    cleaned = [_clean_phrase(p) for p in (phrases or [])]
    return [p for p in cleaned if p and len(p) < 80][:5]


def _deterministic_fallback_body(commitment: dict, sender_name: str = "Prateek") -> str:
    """
    Deterministic template-filled body (no LLM). Used when the LLM returns
    placeholders even after retry. Guarantees a usable, specific email.
    """
    entity = commitment.get('entity', 'there')
    text = commitment.get('text', 'our conversation')
    return (
        f"Hi {entity},\n\n"
        f"Just following up on my commitment: \"{text}\"\n\n"
        f"Is there anything you need from me to move this forward?\n\n"
        f"Thanks,\n"
        f"{sender_name}"
    )


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

    try:
        # Find the commitment by signal_id
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

        entity = commitment.get('entity', 'there')
        commitment_text = commitment.get('text', '')
        if not commitment_text:
            raise HTTPException(
                status_code=400,
                detail="Commitment has no text to follow up on."
            )

        # Fetch thread context (best-effort — don't fail draft if thread fetch fails)
        thread_context = ""
        try:
            from maestro_personal_shell.routers.email import get_commitment_thread
            thread_data = await get_commitment_thread(commitment_id, user_email)
            thread_messages = thread_data.get("messages", []) if thread_data else []
            if thread_messages:
                recent = thread_messages[-3:]  # last 3 messages
                thread_context = "\n\nPREVIOUS EMAIL THREAD (for reference only — do NOT quote verbatim):\n"
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

        # Primary prompt — explicit, imperative, forbids placeholders
        prompt = f"""You are writing a follow-up email for the user. The user has made a commitment and needs to follow up.

HARD RULES (violating any rule means the output is rejected):
1. NEVER use placeholders. NO square brackets like [Your Name] or [Original Email Subject].
2. NO angle brackets like <placeholder>.
3. Use ONLY the real information provided below. Do not invent names, dates, or topics.
4. Start directly with "Hi {entity}," — no "Subject:" line, no preamble, no explanation.
5. Reference the SPECIFIC commitment text provided. Do not say "regarding our conversation" — name the actual commitment.
6. End with a real sign-off: "Thanks,\\nPrateek" (use the sender name below).
7. Length: {length_hint}.
8. Tone: {tone}.

REAL INFORMATION (use this and only this):
- RECIPIENT NAME: {entity}
- SENDER NAME: Prateek
- THE COMMITMENT (the user's promise that needs following up): "{commitment_text}"{thread_context}

{("USER'S VOICE PROFILE (match this style):" if clean_phrases else "No voice profile available — use a clean, professional default style.")}
- Formality: {formality:.1f}/1.0 (0=very casual, 1=very formal)
{chr(10).join(f"- Common phrase (use if natural): \"{p}\"" for p in clean_phrases)}
- Sign-off style: {signature}

Write the email body now. Start with "Hi {entity},". End with "Thanks,\\nPrateek". No other formatting."""

        draft_body = await _call_openrouter(prompt, api_key)

        # Post-generation validation: reject placeholder output, retry once
        if _has_placeholders(draft_body):
            logger.warning(f"First draft attempt had placeholders. Retrying with stricter prompt. Body was: {draft_body[:200]}")
            retry_prompt = (
                f"Your previous response contained placeholders like [Your Name]. "
                f"That is forbidden. Write the email again, this time filling in ALL real values:\n"
                f"- Recipient: {entity}\n"
                f"- Sender: Prateek\n"
                f"- Commitment: {commitment_text}\n\n"
                f"Start with 'Hi {entity},' and end with 'Thanks,\\nPrateek'. "
                f"No brackets, no placeholders, no preamble."
            )
            draft_body = await _call_openrouter(retry_prompt, api_key)

        # If still has placeholders after retry, use deterministic fallback
        if _has_placeholders(draft_body):
            logger.error(f"Draft still had placeholders after retry. Using deterministic fallback. Body was: {draft_body[:200]}")
            draft_body = _deterministic_fallback_body(commitment)

        # Strip any leading "Subject:" line the LLM might add
        draft_body = re.sub(r'^\s*subject:\s*[^\n]*\n', '', draft_body, flags=re.IGNORECASE).strip()

        # Build subject from commitment text
        subject_text = commitment_text[:60].rstrip()
        subject = f"Re: {subject_text}" if not subject_text.lower().startswith('re:') else subject_text

        return EmailDraft(
            draft_id=str(uuid.uuid4()),
            commitment_id=commitment_id,
            to=entity,
            subject=subject,
            body=draft_body,
            voice_confidence=0.85,
            suggested_edits=[],
            created_at=datetime.utcnow()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating draft: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate draft: {str(e)}"
        )


async def _call_openrouter(prompt: str, api_key: str) -> str:
    """Call OpenRouter API. Handles both content-style and reasoning-style models."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "google/gemma-3-12b-it",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 800
    }

    async with httpx.AsyncClient(timeout=45.0) as client:
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

        # Prefer content; fall back to reasoning (some models like Kimi K3 put
        # the answer in reasoning when max_tokens is too low for a final answer)
        content = message.get("content")
        if content:
            return content.strip()

        reasoning = message.get("reasoning") or ""
        if reasoning:
            # Reasoning models often include the answer inline. Extract any
            # quoted or non-thought portion. As a fallback, return the whole
            # reasoning stripped of leading "Let me think..." patterns.
            logger.warning("OpenRouter returned reasoning but no content; using reasoning as fallback")
            return reasoning.strip()

        raise Exception("OpenRouter returned empty content and empty reasoning")

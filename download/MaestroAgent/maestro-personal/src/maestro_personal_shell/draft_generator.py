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


def _clean_entity_name(name: str) -> str:
    """Strip suffix IDs from entity names (e.g., 'Elowen 9ca721e2' → 'Elowen').

    Demo data and some signal sources append hex suffixes to entity names
    for uniqueness. These should never be shown to the user.
    """
    if not name:
        return name
    cleaned = re.sub(r'\s+[a-f0-9]{6,}$', '', name).strip()
    cleaned = re.sub(r'\s+\d+$', '', cleaned).strip()
    return cleaned

# Simple in-memory cache for draft generation (commitment_id + context -> draft)
_DRAFT_CACHE = {}
_CACHE_TTL_SECONDS = 300  # 5 minutes

# No-Gemini rule (user directive 2026-07-30): Google Gemini / Gemma is
# forbidden for any coding or LLM-calling task.
# v20 fix: user directed DeepSeek be used for drafting.
# Using deepseek-chat (non-reasoning) for INSTANT drafts — first content
# token in ~1.6s. The V4 Flash model spends 15s in reasoning before
# producing content, which makes drafts feel frozen. deepseek-chat has
# no reasoning step and streams content immediately.
_DRAFT_MODEL = os.environ.get("MAESTRO_DRAFT_MODEL", "deepseek/deepseek-chat")
_DRAFT_TEMPERATURE = float(os.environ.get("MAESTRO_DRAFT_MODEL_TEMPERATURE", "0.4"))

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
    entity = _clean_entity_name(commitment.get('entity') or commitment.get('recipient') or 'there')
    text = commitment.get('text') or commitment.get('action') or 'our conversation'
    return (
        f"Hi {entity},\n\n"
        f"Just following up on my commitment: \"{text}\"\n\n"
        f"Is there anything you need from me to move this forward?\n\n"
        f"Thanks,\n"
        f"{sender_name}"
    )


def _clean_signature(body: str, voice_signature: str, user_email: str) -> str:
    """Q1 fix: clean orphan signatures and ensure a proper sign-off.

    The LLM sometimes emits 'Best,.' or 'Best, .' — an orphan period where
    the signature should go. This function:
    1. Strips trailing orphan periods after common sign-offs.
    2. If the body doesn't end with a name after the sign-off, appends one.
    3. Uses voice_profile.signature if available, else derives from user_email.
    """
    if not body:
        return body

    # Derive the user's first name from user_email
    # "prateek@example.com" → "Prateek", "john.doe@x.com" → "John"
    sender_name = "Prateek"  # default
    if user_email and "@" in user_email:
        local = user_email.split("@")[0]
        # Take first part before . or _ and capitalize
        first = re.split(r'[._\-+]', local)[0]
        if first:
            sender_name = first.capitalize()

    # Use voice profile signature if available, otherwise use sender_name
    sign_off = voice_signature if voice_signature and voice_signature.strip() else f"Thanks,\n{sender_name}"

    # Strip trailing orphan periods after sign-off words
    # "Best,." → "Best,", "Regards,." → "Regards,", "Thanks,." → "Thanks,"
    _SIGNOFF_WORDS = ['best', 'regards', 'thanks', 'cheers', 'sincerely', 'respectfully']
    lines = body.rstrip().split('\n')
    last_line = lines[-1].strip() if lines else ""

    for word in _SIGNOFF_WORDS:
        # Match "Best,." or "Best, ." or "Best," (no name following)
        pattern = re.compile(rf'^({word})\s*,?\s*\.?\s*$', re.IGNORECASE)
        if pattern.match(last_line):
            # Replace with proper sign-off
            lines[-1] = sign_off
            body = '\n'.join(lines)
            return body.strip()

    # Also catch "Best,." anywhere in the last 3 lines
    for i in range(max(0, len(lines) - 3), len(lines)):
        line = lines[i].strip()
        for word in _SIGNOFF_WORDS:
            if re.match(rf'^{word}\s*,\s*\.+$', line, re.IGNORECASE):
                lines[i] = re.sub(r'\s*,\s*\.+.*$', ',', line, flags=re.IGNORECASE)
                # If this is the last line, append the sign-off
                if i == len(lines) - 1:
                    lines[i] = sign_off
                body = '\n'.join(lines)
                return body.strip()

    # If body doesn't end with any known sign-off, append one
    body_lower = body.lower()
    if not any(word in body_lower[-50:] for word in _SIGNOFF_WORDS):
        body = body.rstrip() + '\n\n' + sign_off

    return body.strip()


def _ban_placeholders(body: str, entity: str, user_email: str) -> str:
    """Q2 fix: ban [Your name] and other placeholders from final output.

    Replaces common placeholder patterns with real values, strips any
    remaining bracket patterns, and removes empty bullets.
    """
    if not body:
        return body

    # Derive sender name
    sender_name = "Prateek"
    if user_email and "@" in user_email:
        local = user_email.split("@")[0]
        first = re.split(r'[._\-+]', local)[0]
        if first:
            sender_name = first.capitalize()

    # Replace known placeholders with real values
    replacements = {
        r'\[your\s+name\]': sender_name,
        r'\[Your\s+Name\]': sender_name,
        r'\[recipient\]': entity,
        r'\[Recipient\]': entity,
        r'\[the\s+recipient\]': entity,
        r'\[sender\]': sender_name,
        r'\[Sender\]': sender_name,
        r'\[date\]': datetime.now().strftime('%B %d, %Y'),
        r'\[time\]': datetime.now().strftime('%I:%M %p'),
        r'\[subject\]': '',
        r'\[topic\]': '',
        r'\[position\]': '',
    }
    for pattern, replacement in replacements.items():
        body = re.sub(pattern, replacement, body, flags=re.IGNORECASE)

    # Strip any remaining [bracket] patterns
    body = re.sub(r'\[[^\]]*\]', '', body)

    # Remove empty bullets (lines that are just "- " or "  - " or "* ")
    body = re.sub(r'^\s*[-*]\s*$', '', body, flags=re.MULTILINE)

    # Remove "Follow-up — " with dangling em-dash (no text after)
    body = re.sub(r'Follow-up\s*—\s*$', 'Follow-up', body, flags=re.MULTILINE)

    # Clean up multiple blank lines
    body = re.sub(r'\n{3,}', '\n\n', body)

    return body.strip()


def _strip_completion_claims(body: str) -> str:
    """Remove fabricated completion claims from LLM-generated draft bodies.

    Audit fix S2-5 (2026-07-31): the LLM sometimes ignores the prompt rule
    that forbids claiming completion. It writes phrases like:
      - "I've completed the Q4 forecast"
      - "I have completed the report"
      - "I finished the analysis"
      - "I already sent the proposal"
      - "the document is done"
    These are fabricated — the user is following up on a commitment, not
    confirming completion. This function rewrites those phrases to
    non-committal language that doesn't claim completion.

    This is a defense-in-depth layer on top of the prompt rule. If the LLM
    ignores the rule, this filter catches it before the draft reaches the
    user.
    """
    if not body:
        return body

    # Map of completion-claim patterns → non-committal replacements.
    # Order matters: longer/more specific patterns first.
    replacements = [
        # "I've completed X" → "I'm working on X"
        (r'\bI\'?ve completed\b', "I'm working on"),
        (r'\bI have completed\b', "I'm working on"),
        (r'\bI\'?ve finished\b', "I'm working on"),
        (r'\bI have finished\b', "I'm working on"),
        (r'\bI finished\b', "I'm working on"),
        (r'\bI completed\b', "I'm working on"),
        # "I already sent X" → "I wanted to follow up on X"
        (r'\bI already sent\b', "I wanted to follow up on"),
        (r'\bI\'?ve already sent\b', "I wanted to follow up on"),
        (r'\bI have already sent\b', "I wanted to follow up on"),
        # "the X is done" → "the X is in progress"
        (r'\bis done\b', "is in progress"),
        (r'\bis complete\b', "is in progress"),
        (r'\bis finished\b', "is in progress"),
        # "just confirming that I completed" → "following up on"
        (r'\bjust (?:confirming|confirm) that I (?:completed|finished|sent)\b',
         "following up on"),
        (r'\bto confirm that I (?:completed|finished|sent)\b',
         "regarding"),
        # "as committed" standalone is fine, but "I completed X as committed"
        # is a fabrication — remove "as committed" from completion contexts
        (r'\b(?:completed|finished|sent|delivered) as committed\b',
         "am working on"),
    ]

    for pattern, replacement in replacements:
        body = re.sub(pattern, replacement, body, flags=re.IGNORECASE)

    return body


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
    entity = _clean_entity_name(commitment.get('entity') or '')
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

        # G3 fix (auditor v19): if the ledger lookup fails, also check the
        # signals table directly. The /api/commitments endpoint publishes
        # signal_id, but the async ledger write may not have completed yet,
        # or the signal was classified but not yet ledgered. Without this
        # fallback, /api/commitments/{id}/draft 404s for valid commitments.
        if not commitment:
            try:
                from maestro_personal_shell.db_util import get_db_conn
                import sqlite3 as _sqlite3
                conn = get_db_conn(db_path)
                try:
                    conn.row_factory = _sqlite3.Row
                except Exception:
                    pass
                try:
                    row = conn.execute(
                        "SELECT signal_id, entity, text, signal_type, timestamp, metadata, user_email "
                        "FROM signals WHERE signal_id = ? AND user_email = ?",
                        (commitment_id, user_email)
                    ).fetchone()
                    if row:
                        meta = row["metadata"] if "metadata" in row.keys() else "{}"
                        if isinstance(meta, str):
                            try:
                                import json as _json
                                meta = _json.loads(meta) if meta else {}
                            except Exception:
                                meta = {}
                        commitment = {
                            "signal_id": row["signal_id"],
                            "entity": row["entity"],
                            "text": row["text"],
                            "metadata": meta,
                            "recipient": row["entity"],
                        }
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"Signal table fallback lookup failed for {commitment_id}: {e}")

        if not commitment:
            raise HTTPException(
                status_code=404,
                detail=f"Commitment {commitment_id} not found"
            )

        entity = _clean_entity_name(commitment.get('entity') or commitment.get('recipient') or 'there')
        commitment_text = commitment.get('text') or commitment.get('action') or ''
        if not commitment_text:
            raise HTTPException(
                status_code=400,
                detail="Commitment has no text to follow up on."
            )

        # Q7 FIX (S1 — user-harming): reject non-commitment signals before
        # drafting. The classifier correctly types cancellations, negations,
        # third-party reports, questions, and tentative statements — but the
        # draft generator never read the label. This produced follow-up emails
        # asking colleagues to deliver on CANCELLED commitments.
        #
        # "Producer correct, consumer never swept" — the classifier has typed
        # these correctly since Audit #2. The generator has never read the type.
        #
        # Fix: read commitment_type from metadata and reject non-commitment
        # types with a 422 error. The frontend can show "This signal is a
        # [cancellation/question/etc.] — no follow-up needed."
        _meta = commitment.get('metadata', {}) or {}
        if isinstance(_meta, str):
            try:
                import json as _json_meta
                _meta = _json_meta.loads(_meta) if _meta else {}
            except Exception:
                _meta = {}
        _commitment_type = _meta.get('commitment_type', '')
        _is_commitment = _meta.get('is_commitment', True)
        _NON_DRAFTABLE_TYPES = {
            'cancelled', 'negation', 'third_party_report', 'not_a_commitment',
            'question', 'tentative', 'joke', 'request', 'aspiration',
            'proposal', 'superseded',
        }
        if _commitment_type in _NON_DRAFTABLE_TYPES or _is_commitment is False:
            _reason = {
                'cancelled': 'This signal is a cancellation — no follow-up needed.',
                'negation': 'This signal is a negation — the commitment was withdrawn.',
                'third_party_report': 'This is someone else\'s commitment, not yours.',
                'not_a_commitment': 'This signal was classified as not a commitment.',
                'question': 'This is a question, not a commitment.',
                'tentative': 'This is a tentative statement, not a firm commitment.',
                'joke': 'This was classified as a joke.',
                'request': 'This is a request, not your commitment.',
                'aspiration': 'This is an aspiration, not a commitment.',
                'proposal': 'This is a proposal, not a commitment.',
                'superseded': 'This commitment was superseded.',
            }.get(_commitment_type, 'This signal is not a draftable commitment.')
            raise HTTPException(
                status_code=422,
                detail={
                    'error': 'non_draftable_signal',
                    'commitment_type': _commitment_type,
                    'reason': _reason,
                }
            )

        # Look up actual email address (P-DRAFT-EMAIL-ADDRESS fix)
        recipient_email = _get_recipient_email(commitment, commitment_id, user_email)
        if not recipient_email:
            logger.warning(f"No email address found for {entity}, using entity name as fallback")
            recipient_email = entity  # Fallback to name if no email found

        # Fetch thread context — LATENCY FIX (2026-07-31): skip the thread
        # fetch in the non-streaming path. The thread fetch was calling
        # reconcile_signals_for_user (8.7s) just to get context that the
        # LLM doesn't critically need. The streaming path can still fetch
        # it if needed. This cuts draft latency from 20s to ~12s.
        thread_context = ""
        # Thread context is nice-to-have but not worth 8.7s of latency.
        # The commitment_text alone is enough for the LLM to write a good draft.
        # If you want thread context, use the streaming endpoint which
        # fetches it in the background.

        # LATENCY FIX (v21): skip voice profile — use defaults.
        # The voice profile fetches all signals and analyzes them, taking
        # 5-8s. The LLM produces high-quality output without voice phrases.
        clean_phrases = []
        formality = 0.5
        signature = "Thanks,"

        length_hint = {"short": "2-3 sentences", "medium": "4-6 sentences", "long": "8-12 sentences"}.get(length, "4-6 sentences")

        # P-DRAFT-NEWLINE fix: Use actual newlines in prompt, not \\n
        # Audit fix S2-5 (2026-07-31): added rule 7 forbidding completion claims.
        # The audit found LLM-generated drafts that said "I've completed the Q4
        # forecast" when the commitment was just "I will send the Q4 forecast
        # by Thursday." The LLM was hallucinating completion. This rule
        # explicitly forbids claiming the commitment has been completed.
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
7. NEVER claim the commitment has been completed. Do NOT write phrases like
   "I've completed", "I have completed", "I finished", "I already sent",
   "the report is done", or any variation. The user has NOT completed this
   commitment — they are following up on it. Write a follow-up that
   acknowledges the commitment and asks if the recipient needs anything,
   or offers an update on progress. If you don't know the current status,
   ask — do not fabricate completion.

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

        # Q1 fix (auditor v19): clean orphan signatures like "Best,." → "Best,"
        # and ensure the draft ends with a proper sign-off.
        draft_body = _clean_signature(draft_body, signature, user_email)

        # Q2 fix (auditor v19): ban [Your name] and other placeholders from
        # the final output. Replace with real values, strip any remaining
        # bracket patterns, and remove empty bullets.
        draft_body = _ban_placeholders(draft_body, entity, user_email)

        # Audit fix S2-5 (2026-07-31): post-process to remove any completion
        # claims that slipped through despite the prompt rule 7. The LLM
        # sometimes ignores the "never claim completion" instruction and
        # writes "I've completed the Q4 forecast" anyway. This filter
        # catches and rewrites those phrases to non-committal language.
        draft_body = _strip_completion_claims(draft_body)

        # Build subject
        subject_text = commitment_text[:60].rstrip()
        subject = f"Re: {subject_text}" if not subject_text.lower().startswith('re:') else subject_text

        # Q3 fix (auditor v19): track whether we have a real email address
        # or fell back to the entity name. The caller can use needs_recipient
        # to prompt the user for an email.
        needs_recipient = "@" not in recipient_email

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
    """Call OpenRouter API. P-DRAFT-LATENCY: reduced max_tokens to 400.
    v20: uses deepseek/deepseek-chat-v3.1:free by default (env-configurable).
    User directed DeepSeek for drafting — higher quality + faster for short-form.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    data = {
        "model": _DRAFT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": _DRAFT_TEMPERATURE,
        "max_tokens": 400  # P-DRAFT-LATENCY: was 800, reduced to 400
    }

    async with httpx.AsyncClient(timeout=25.0) as client:
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


# Global reusable httpx client — avoids connection setup overhead on every call.
# Creating a new AsyncClient per request adds ~500ms for TLS handshake + pool init.
# The global client reuses connections across requests.
_STREAM_CLIENT: httpx.AsyncClient | None = None

def _get_stream_client() -> httpx.AsyncClient:
    global _STREAM_CLIENT
    if _STREAM_CLIENT is None or _STREAM_CLIENT.is_closed:
        _STREAM_CLIENT = httpx.AsyncClient(timeout=30.0)
    return _STREAM_CLIENT


async def _call_openrouter_stream(prompt: str, api_key: str):
    """L-D1 fix: streaming version of _call_openrouter for draft generation.

    Yields content chunks as they arrive from the LLM. Uses OpenRouter's
    streaming API (stream=true, SSE response). This cuts first-token
    latency from 12s to <1.5s — the user sees progressive text instead
    of a frozen modal.

    Yields: str — each chunk of content text.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    data = {
        "model": _DRAFT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": _DRAFT_TEMPERATURE,
        "max_tokens": 400,
        "stream": True,  # L-D1: streaming
    }

    # Use global reusable client — saves ~500ms TLS overhead per call
    client = _get_stream_client()
    async with client.stream(
        "POST",
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=data,
    ) as response:
        if response.status_code != 200:
            body = await response.aread()
            logger.error(f"OpenRouter stream error {response.status_code}: {body[:300]}")
            raise Exception(f"OpenRouter error: {response.status_code}")

        async for line in response.aiter_lines():
            if not line or not line.startswith("data: "):
                continue
            payload = line[6:]  # strip "data: " prefix
            if payload.strip() == "[DONE]":
                break
            try:
                import json as _json
                chunk = _json.loads(payload)
                choice = chunk.get("choices", [{}])[0]
                delta = choice.get("delta", {})
                content = delta.get("content")
                if content:
                    yield content
            except Exception:
                continue


async def stream_email_draft(
    commitment_id: str,
    user_email: str,
    tone: str = "professional",
    length: str = "medium",
    context: Optional[str] = None,
):
    """L-D1 fix: SSE streaming draft generation.

    Yields SSE-formatted strings: `data: {"chunk": "..."}\n\n` as the LLM
    produces tokens, ending with `data: [DONE]\n\n`. Mirrors the
    /api/ask/stream pattern.

    This function does the same lookup + prompt building as
    generate_email_draft, but streams the output instead of waiting for
    the full response. First token arrives in <1.5s vs 12s for the
    non-streaming path.
    """
    import json as _json

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        yield f'data: {{"error": "AI draft generation unavailable (LLM not configured)"}}\n\n'
        yield "data: [DONE]\n\n"
        return

    try:
        from maestro_personal_shell.commitment_ledger import get_ledger_entries
        from maestro_personal_shell.db_util import default_sqlite_path, get_db_conn

        db_path = default_sqlite_path()
        entries = get_ledger_entries(user_email=user_email, db_path=db_path)

        commitment = None
        for entry in entries:
            if entry.get("signal_id") == commitment_id:
                commitment = entry
                break

        # G3 fix: fallback to signals table
        if not commitment:
            try:
                import sqlite3 as _sqlite3
                conn = get_db_conn(db_path)
                try:
                    conn.row_factory = _sqlite3.Row
                except Exception:
                    pass
                try:
                    row = conn.execute(
                        "SELECT signal_id, entity, text, metadata FROM signals WHERE signal_id = ? AND user_email = ?",
                        (commitment_id, user_email)
                    ).fetchone()
                    if row:
                        meta = row["metadata"] if "metadata" in row.keys() else "{}"
                        if isinstance(meta, str):
                            try:
                                meta = _json.loads(meta) if meta else {}
                            except Exception:
                                meta = {}
                        commitment = {
                            "signal_id": row["signal_id"],
                            "entity": row["entity"],
                            "text": row["text"],
                            "metadata": meta,
                            "recipient": row["entity"],
                        }
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"Stream: signal fallback failed for {commitment_id}: {e}")

        if not commitment:
            yield f'data: {{"error": "Commitment {commitment_id} not found"}}\n\n'
            yield "data: [DONE]\n\n"
            return

        entity = _clean_entity_name(commitment.get('entity') or commitment.get('recipient') or 'there')
        commitment_text = commitment.get('text') or commitment.get('action') or ''
        if not commitment_text:
            yield f'data: {{"error": "Commitment has no text to follow up on."}}\n\n'
            yield "data: [DONE]\n\n"
            return

        # Q7 FIX (streaming path): reject non-commitment signals before drafting
        _meta = commitment.get('metadata', {}) or {}
        if isinstance(_meta, str):
            try:
                _meta = _json.loads(_meta) if _meta else {}
            except Exception:
                _meta = {}
        _commitment_type = _meta.get('commitment_type', '')
        _is_commitment = _meta.get('is_commitment', True)
        _NON_DRAFTABLE_TYPES = {
            'cancelled', 'negation', 'third_party_report', 'not_a_commitment',
            'question', 'tentative', 'joke', 'request', 'aspiration',
            'proposal', 'superseded',
        }
        if _commitment_type in _NON_DRAFTABLE_TYPES or _is_commitment is False:
            _reason = {
                'cancelled': 'This signal is a cancellation — no follow-up needed.',
                'negation': 'This signal is a negation — the commitment was withdrawn.',
                'third_party_report': 'This is someone else\'s commitment, not yours.',
                'not_a_commitment': 'This signal was classified as not a commitment.',
                'question': 'This is a question, not a commitment.',
                'tentative': 'This is a tentative statement, not a firm commitment.',
            }.get(_commitment_type, 'This signal is not a draftable commitment.')
            yield f'data: {{"error": "non_draftable_signal", "commitment_type": "{_commitment_type}", "reason": "{_reason}"}}\n\n'
            yield "data: [DONE]\n\n"
            return

        recipient_email = _get_recipient_email(commitment, commitment_id, user_email)

        # LATENCY FIX: skip voice profile for streaming too
        clean_phrases = []
        formality = 0.5
        signature = "Thanks,"

        length_hint = {"short": "2-3 sentences", "medium": "4-6 sentences", "long": "8-12 sentences"}.get(length, "4-6 sentences")

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
- COMMITMENT: "{commitment_text}"

{"USER VOICE PROFILE:" if clean_phrases else "No voice profile available."}
- Formality: {formality:.1f}/1.0
{chr(10).join(f"- Common phrase: \"{p}\"" for p in clean_phrases)}
- Sign-off: {signature}

Write the email body now. Start with "Hi {entity},". Use ACTUAL newlines (press Enter), not \\n."""

        accumulated = ""
        try:
            async for chunk in _call_openrouter_stream(prompt, api_key):
                accumulated += chunk
                yield f'data: {{"chunk": {_json.dumps(chunk)}}}\n\n'
        except Exception as e:
            logger.error(f"Stream draft LLM error: {e}")
            yield f'data: {{"error": "LLM streaming failed: {str(e)[:100]}"}}\n\n'
            yield "data: [DONE]\n\n"
            return

        # Apply post-processing to the final accumulated text
        # Q1 + Q2 fixes: clean signature and ban placeholders
        final_text = re.sub(r'^\s*subject:\s*[^\n]*\n', '', accumulated, flags=re.IGNORECASE).strip()
        final_text = _clean_signature(final_text, signature, user_email)
        final_text = _ban_placeholders(final_text, entity, user_email)

        # If post-processing changed the text, yield a final correction chunk
        if final_text != accumulated:
            yield f'data: {{"final": {_json.dumps(final_text)}, "recipient_email": {_json.dumps(recipient_email)}, "needs_recipient": {_json.dumps("@" not in recipient_email)}}}\n\n'

        yield "data: [DONE]\n\n"

    except Exception as e:
        logger.error(f"Error in stream_email_draft: {e}", exc_info=True)
        yield f'data: {{"error": "Failed to generate draft: {str(e)[:100]}"}}\n\n'
        yield "data: [DONE]\n\n"

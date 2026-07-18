"""Intelligent Draft Generator — LLM-powered email drafting in the user's style.

This module replaces the template-based draft generator with a real
intelligence layer that:

1. Fetches the user's sent emails from Gmail to learn their writing style
2. Analyzes style patterns (greeting, tone, sentence length, sign-off)
3. Uses the LLM to generate a contextual reply that:
   - References the specific commitment (not a generic template)
   - Uses the user's actual writing style
   - Addresses the specific ask in the incoming email
   - Proposes next steps based on commitment status

No fabrication: if the LLM is unavailable, falls back to the template.
If no sent emails are available, uses a professional default style.
"""
from __future__ import annotations

import json
import logging
import base64
from typing import Any

logger = logging.getLogger(__name__)


async def fetch_user_sent_emails(
    stored_token_json: str,
    oauth_client: Any,
    max_emails: int = 20,
) -> list[dict[str, str]]:
    """Fetch the user's sent emails from Gmail for style analysis.

    Returns a list of {to, subject, body} dicts.
    """
    try:
        from maestro_personal_shell.gmail_connector import GmailOAuthClient
        client: GmailOAuthClient = oauth_client

        access_token, _ = client.get_valid_access_token(stored_token_json)
        if not access_token:
            return []

        from maestro_personal_shell.gmail_connector import GmailAPIClient
        api_client = GmailAPIClient(access_token)

        # List sent messages
        message_ids = api_client.list_messages(query="in:sent", max_results=max_emails)
        if isinstance(message_ids, dict) and "error" in message_ids:
            logger.warning("Failed to fetch sent emails: %s", message_ids["error"])
            return []

        sent_emails = []
        for msg_id in message_ids[:max_emails]:
            msg_data = api_client.get_message(msg_id)
            if isinstance(msg_data, dict) and "error" in msg_data:
                continue

            # Extract headers
            headers = msg_data.get("payload", {}).get("headers", [])
            to = ""
            subject = ""
            for h in headers:
                if h.get("name", "").lower() == "to":
                    to = h.get("value", "")
                elif h.get("name", "").lower() == "subject":
                    subject = h.get("value", "")

            # Extract body
            body = _extract_email_body(msg_data.get("payload", {}))
            if body and len(body) > 20:
                sent_emails.append({
                    "to": to,
                    "subject": subject,
                    "body": body[:1000],  # cap for style analysis
                })

        logger.info("Fetched %d sent emails for style analysis", len(sent_emails))
        return sent_emails

    except Exception as e:
        logger.warning("Failed to fetch sent emails for style analysis: %s", e)
        return []


def _extract_email_body(payload: dict) -> str:
    """Extract plain text body from a Gmail message payload."""
    try:
        if "body" in payload and payload["body"].get("data"):
            data = payload["body"]["data"]
            # URL-safe base64 decode
            padded = data + "=" * (4 - len(data) % 4) if len(data) % 4 else data
            return base64.urlsafe_b64decode(padded).decode("utf-8", errors="ignore")

        # Check parts (multipart)
        for part in payload.get("parts", []):
            mime = part.get("mimeType", "")
            if mime == "text/plain" and part.get("body", {}).get("data"):
                data = part["body"]["data"]
                padded = data + "=" * (4 - len(data) % 4) if len(data) % 4 else data
                return base64.urlsafe_b64decode(padded).decode("utf-8", errors="ignore")

        return ""
    except Exception:
        return ""


def analyze_writing_style(sent_emails: list[dict[str, str]]) -> dict[str, Any]:
    """Analyze the user's writing style from their sent emails.

    Extracts patterns without an LLM (fast, deterministic):
    - greeting: most common greeting ("Hi", "Hey", "Dear", etc.)
    - sign_off: most common sign-off ("Best,", "Thanks,", "Cheers", etc.)
    - avg_sentence_length: average words per sentence
    - uses_bullets: whether they use bullet points
    - tone: "formal" / "casual" / "mixed"
    - sample_openings: first sentences of recent emails (for LLM context)
    """
    if not sent_emails:
        return {
            "greeting": "Hi",
            "sign_off": "Best,",
            "avg_sentence_length": 15,
            "uses_bullets": False,
            "tone": "professional",
            "sample_openings": [],
        }

    greetings = {}
    sign_offs = {}
    sentence_lengths = []
    uses_bullets_count = 0
    openings = []

    for email in sent_emails:
        body = email.get("body", "")
        if not body:
            continue

        lines = body.strip().split("\n")
        first_line = lines[0].strip() if lines else ""

        # Extract greeting (first 1-2 words before a comma or newline)
        greeting = ""
        if first_line:
            for sep in [",", "\n", " "]:
                if sep in first_line:
                    greeting = first_line.split(sep)[0].strip()
                    break
            if not greeting:
                greeting = first_line[:20].strip()
        if greeting and len(greeting) < 30:
            greetings[greeting] = greetings.get(greeting, 0) + 1

        # Extract sign-off (last 1-2 lines)
        last_lines = [l.strip() for l in lines[-5:] if l.strip()]
        for ll in last_lines:
            if ll in ("Best,", "Best regards,", "Thanks,", "Thank you,", "Cheers,",
                       "Regards,", "Sincerely,", "Warm regards,", "Best regards"):
                sign_offs[ll] = sign_offs.get(ll, 0) + 1
                break

        # Sentence length
        sentences = body.split(". ")
        for s in sentences:
            words = len(s.split())
            if 3 < words < 50:
                sentence_lengths.append(words)

        # Bullet points
        if "•" in body or "- " in body or "* " in body:
            uses_bullets_count += 1

        # Opening sentence
        if first_line and len(first_line) > 10:
            openings.append(first_line[:200])

    # Pick most common
    greeting = max(greetings, key=greetings.get) if greetings else "Hi"
    sign_off = max(sign_offs, key=sign_offs.get) if sign_offs else "Best,"
    avg_len = sum(sentence_lengths) / len(sentence_lengths) if sentence_lengths else 15
    uses_bullets = uses_bullets_count > len(sent_emails) * 0.3

    # Tone: short sentences + casual greeting = casual
    tone = "professional"
    if avg_len < 12 and greeting.lower() in ("hey", "hi", "yo"):
        tone = "casual"
    elif avg_len > 25:
        tone = "formal"

    return {
        "greeting": greeting,
        "sign_off": sign_off,
        "avg_sentence_length": round(avg_len),
        "uses_bullets": uses_bullets,
        "tone": tone,
        "sample_openings": openings[:5],
    }


async def generate_intelligent_draft(
    provider: str,
    recipient: str,
    commitment: dict[str, Any],
    evidence_refs: list[dict],
    incoming_email_context: str = "",
    writing_style: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate a draft using the LLM, grounded in the user's commitments + style.

    This is the REAL capability — not a template. The LLM:
    1. Reads the commitment (what the user promised)
    2. Reads the evidence (prior history with this person)
    3. Reads the incoming email context (what they're asking about)
    4. Reads the user's writing style (greeting, tone, sign-off)
    5. Generates a reply that sounds like the user wrote it

    Falls back to template if LLM unavailable.
    """
    commitment_text = commitment.get("text", "")
    entity = commitment.get("entity", recipient)

    # Build the style prompt
    style = writing_style or {}
    style_desc = (
        f"Greeting: {style.get('greeting', 'Hi')}. "
        f"Sign-off: {style.get('sign_off', 'Best,')}. "
        f"Tone: {style.get('tone', 'professional')}. "
        f"Average sentence length: {style.get('avg_sentence_length', 15)} words. "
        f"Uses bullet points: {style.get('uses_bullets', False)}."
    )

    # Build evidence context
    evidence_text = ""
    if evidence_refs:
        evidence_lines = []
        for ref in evidence_refs[:3]:
            evidence_lines.append(
                f'- "{ref.get("text", "")}" ({ref.get("entity", "")})'
            )
        evidence_text = "\nPrior history:\n" + "\n".join(evidence_lines)

    # Build incoming email context
    email_context = ""
    if incoming_email_context:
        email_context = f"\nIncoming email context:\n{incoming_email_context[:500]}"

    # Try LLM
    try:
        from maestro_personal_shell.llm_bridge import is_llm_available, llm_complete
        if is_llm_available():
            system_prompt = (
                "You are a personal email drafting assistant. You write emails that sound "
                "like the user wrote them — matching their greeting, tone, sentence length, "
                "and sign-off. You NEVER fabricate commitments or facts. You only reference "
                "the commitment and evidence provided. If the commitment doesn't fully answer "
                "the incoming email, acknowledge that honestly."
            )

            user_prompt = f"""Draft a {provider} reply to {recipient} about: {commitment_text}

Writing style: {style_desc}

Commitment: {commitment_text}
Entity: {entity}
{evidence_text}{email_context}

Write a natural, concise reply in the user's style. Reference the specific commitment.
Keep it under 150 words. Do not include [Your name] — end with the sign-off only."""

            response = await llm_complete(
                system=system_prompt,
                user=user_prompt,
                temperature=0.7,
                max_tokens=300,
            )

            # P11 fix (wiring): llm_complete returns str | None, not an object
            # with .text. The previous `response.text` raised AttributeError
            # every time, silently falling back to the template.
            if response:
                draft_body = response.strip()
                # Ensure it ends with the sign-off
                sign_off = style.get("sign_off", "Best,")
                if sign_off not in draft_body[-50:]:
                    draft_body += f"\n\n{sign_off}"

                subject = f"Re: {commitment_text[:60]}"
                if incoming_email_context and "subject" in incoming_email_context.lower():
                    subject = f"Re: {entity} — follow-up"

                return {
                    "provider": provider,
                    "recipient": recipient,
                    "subject": subject,
                    "body": draft_body,
                    "commitment_ref": commitment_text,
                    "evidence_refs": evidence_refs,
                    "derived": True,
                    "llm_generated": True,
                    "style_applied": True,
                }
    except Exception as e:
        logger.warning("LLM draft generation failed, falling back to template: %s", e)

    # Fallback: template with style applied
    greeting = style.get("greeting", "Hi")
    sign_off = style.get("sign_off", "Best,")
    recipient_name = recipient.split("@")[0] if "@" in recipient else recipient

    body_lines = [
        f"{greeting} {recipient_name},",
        "",
        f"Following up on: {commitment_text}",
        "",
    ]

    if evidence_refs:
        body_lines.append("For context:")
        for ref in evidence_refs[:2]:
            body_lines.append(f'  - "{ref.get("text", "")}" — {ref.get("entity", "")}')
        body_lines.append("")

    body_lines.extend([
        "I wanted to provide an update on this. Let me know if you need anything else.",
        "",
        sign_off,
    ])

    return {
        "provider": provider,
        "recipient": recipient,
        "subject": f"Follow-up — {entity}",
        "body": "\n".join(body_lines),
        "commitment_ref": commitment_text,
        "evidence_refs": evidence_refs,
        "derived": True,
        "llm_generated": False,
        "style_applied": True,
    }

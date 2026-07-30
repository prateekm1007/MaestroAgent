"""
Email sender - sends drafts via Gmail API or mailto fallback.

P-SEND-503 fix (auditor finding):
  Previous implementation raised HTTP 503 "Email sending is not yet available"
  on every call. The TODO said "implement when per-user Gmail OAuth tokens
  are available" — but that blocked ALL users from any form of sending.

  Fix:
    1. If Gmail OAuth is configured AND user has tokens → send via Gmail API.
    2. If Gmail not configured OR no tokens → return a mailto: link the
       frontend can render as a clickable "Open in email client" button.
       The user's email client (Gmail, Outlook, Apple Mail) opens with
       To/Subject/Body pre-filled. User reviews and clicks send.
    3. Never return 503 "not available" — there is always a path (mailto).

  P85 compliance: structured errors only, no 500 crashes on read paths.
"""

import base64
import logging
import urllib.parse
from email.mime.text import MIMEText
from typing import Optional

from fastapi import HTTPException

from maestro_personal_shell.gmail_connector import is_gmail_configured

logger = logging.getLogger(__name__)


async def send_email_draft(
    draft_id: str,
    user_email: str,
    edited_body: Optional[str] = None,
    to_override: Optional[str] = None,
    subject_override: Optional[str] = None,
) -> dict:
    """
    Send an email draft.

    Tries Gmail API first (if user has OAuth tokens). Falls back to mailto:
    link so the user can send via their own email client.

    Args:
        draft_id: Draft UUID (may not be persisted — caller provides overrides)
        user_email: Authenticated user
        edited_body: User-edited email body (required if no draft in DB)
        to_override: Recipient email (required if no draft in DB)
        subject_override: Subject line (optional, falls back to "Follow-up")

    Returns one of:
      {"status": "sent", "method": "gmail_api", "message_id": "..."}
      {"status": "ready_to_send", "method": "mailto",
       "mailto_link": "mailto:...", "to": "...", "subject": "...", "body": "..."}

    P85: Never 500. 400 for client errors, 503 only if a configured service
    is genuinely down.
    """
    # Look up the draft in DB (best-effort). If not found, use overrides.
    draft = await _get_draft_by_id(draft_id, user_email)

    body = (edited_body or (draft.get("body") if draft else None) or "").strip()
    to_email = (to_override or (draft.get("to") if draft else None) or "").strip()
    subject = (subject_override or (draft.get("subject") if draft else None) or "Follow-up").strip()

    if not to_email:
        raise HTTPException(
            status_code=400,
            detail="No recipient email address. Provide 'to' in the request body."
        )
    # F-36 fix (auditor v18): recipient must be a real email address, not a
    # person's name. The drafts table can store a name in `recipient` (when
    # the draft was derived from a commitment whose entity is "Aurelio
    # Bonvicini" with no email). Reject early so the user sees a clear
    # error instead of a silently-malformed mailto link.
    if "@" not in to_email or " " in to_email.strip():
        raise HTTPException(
            status_code=400,
            detail=f"Recipient '{to_email}' is not a valid email address. Set a valid 'to' field in the request body."
        )
    if not body:
        raise HTTPException(
            status_code=400,
            detail="No email body provided."
        )

    # Try Gmail API if globally configured AND user has OAuth tokens
    if is_gmail_configured():
        oauth_tokens = await _get_user_oauth_tokens(user_email)
        if oauth_tokens:
            try:
                message_id = await _send_via_gmail_api(
                    to_email=to_email,
                    subject=subject,
                    body=body,
                    tokens=oauth_tokens,
                )
                logger.info(f"Email sent via Gmail API for user {user_email}: {message_id}")
                return {
                    "status": "sent",
                    "method": "gmail_api",
                    "message_id": message_id,
                    "to": to_email,
                    "subject": subject,
                }
            except Exception as e:
                # Gmail API failed (token expired, quota, etc.) — fall through
                # to mailto rather than 500. Log for investigation.
                logger.warning(f"Gmail API send failed for {user_email}, falling back to mailto: {e}")

    # Fallback: return a mailto: link the frontend can render as a button.
    # The user's email client opens with To/Subject/Body pre-filled.
    mailto_link = _build_mailto_link(to_email, subject, body)

    return {
        "status": "ready_to_send",
        "method": "mailto",
        "mailto_link": mailto_link,
        "to": to_email,
        "subject": subject,
        "body": body,
        "message": "Click the link to open this email in your email client. Review and send from there."
    }


async def _get_draft_by_id(draft_id: str, user_email: str) -> Optional[dict]:
    """Look up a draft by ID. Returns dict with to/subject/body or None.

    F-34 v2 fix (auditor v19): the prior version used sqlite3.connect()
    directly, which bypassed get_db_conn()'s Postgres detection. On
    Railway (Postgres), this created a fresh empty SQLite file and
    never found the draft — causing every /drafts/{id}/send to 400.
    Fix: use get_db_conn() so the lookup hits the same database the
    ConnectorStore wrote to.
    """
    try:
        from maestro_personal_shell.db_util import get_db_conn
        import sqlite3
        conn = get_db_conn()
        try:
            conn.row_factory = sqlite3.Row
        except Exception:
            pass  # PostgresConnection handles row_factory via DictCursor
        try:
            row = conn.execute(
                "SELECT draft_id, user_email, provider, recipient, subject, body, commitment_ref, evidence_refs, status, created_at, resolved_at, sent_message_id "
                "FROM drafts WHERE draft_id = ? AND user_email = ?",
                (draft_id, user_email)
            ).fetchone()
            if not row:
                return None
            return {
                "draft_id": row["draft_id"],
                "to": row["recipient"] or "",
                "subject": row["subject"] or "",
                "body": row["body"] or "",
                "commitment_id": row["commitment_ref"],
            }
        finally:
            try:
                conn.close()
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"_get_draft_by_id DB lookup failed: {e}. Returning None.")
        return None


async def _get_user_oauth_tokens(user_email: str) -> Optional[dict]:
    """
    Look up the user's Gmail OAuth tokens from the database.
    Returns None if not connected or table doesn't exist.

    F-34 v2 fix: use get_db_conn() (Postgres-aware) instead of
    sqlite3.connect() directly.
    """
    try:
        from maestro_personal_shell.db_util import get_db_conn
        import sqlite3
        conn = get_db_conn()
        try:
            conn.row_factory = sqlite3.Row
        except Exception:
            pass
        try:
            row = conn.execute(
                "SELECT access_token, refresh_token, expires_at "
                "FROM user_oauth_tokens WHERE user_email = ? AND provider = 'gmail'",
                (user_email,)
            ).fetchone()
            if not row:
                return None
            return {
                "access_token": row["access_token"],
                "refresh_token": row["refresh_token"],
                "expires_at": row["expires_at"],
            }
        finally:
            try:
                conn.close()
            except Exception:
                pass
    except Exception as e:
        # Table doesn't exist or schema differs — most users have no OAuth
        logger.debug(f"OAuth token lookup failed (likely no tokens table): {e}")
        return None


async def _send_via_gmail_api(
    to_email: str, subject: str, body: str, tokens: dict
) -> str:
    """
    Send via Gmail API using the user's OAuth access token.

    Returns the Gmail message_id. Raises on failure.
    """
    # Build RFC 2822 message
    message = MIMEText(body)
    message["to"] = to_email
    message["subject"] = subject
    # Encode as base64url for Gmail API
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

    # Use httpx to call Gmail API
    import httpx
    headers = {
        "Authorization": f"Bearer {tokens['access_token']}",
        "Content-Type": "application/json",
    }
    payload = {"raw": raw}

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            headers=headers,
            json=payload,
        )
        if resp.status_code not in (200, 201):
            raise Exception(f"Gmail API returned {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        return data.get("id", "unknown")


def _build_mailto_link(to: str, subject: str, body: str) -> str:
    """Build a mailto: link with proper URL encoding."""
    # Use quote_plus for query string encoding (spaces become +)
    params = urllib.parse.urlencode({
        "subject": subject,
        "body": body,
    })
    return f"mailto:{to}?{params}"

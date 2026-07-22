"""
Synthetic Inbox router — /api/inbox/synthetic

Provides 20 mutable demo emails for beta users to experience the full
commitment lifecycle without Gmail OAuth.

Endpoints:
  GET  /api/inbox/synthetic           — list all 20 emails
  POST /api/inbox/synthetic/{id}/receive  — ingest email as signal (triggers extraction)
  GET  /api/inbox/synthetic/status     — summary of received emails + effects
"""
from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/inbox", tags=["inbox"])


async def verify_token_dep(authorization: str = Header(None)) -> str:
    """Auth proxy — same pattern as other routers."""
    from maestro_personal_shell.api import verify_token
    return await verify_token(authorization=authorization)


@router.get("/synthetic")
async def list_synthetic_emails():
    """List all 20 synthetic emails."""
    from maestro_personal_shell.synthetic_inbox import get_synthetic_emails
    emails = get_synthetic_emails()
    return {
        "total": len(emails),
        "categories": {
            "new_commitment": sum(1 for e in emails if e["category"] == "new_commitment"),
            "completion": sum(1 for e in emails if e["category"] == "completion"),
            "cancellation": sum(1 for e in emails if e["category"] == "cancellation"),
            "fyi": sum(1 for e in emails if e["category"] == "fyi"),
            "contradiction": sum(1 for e in emails if e["category"] == "contradiction"),
            "ambiguous": sum(1 for e in emails if e["category"] == "ambiguous"),
        },
        "emails": emails,
    }


@router.post("/synthetic/{email_id}/receive")
async def receive_synthetic_email(email_id: str, token: str = Depends(verify_token_dep)):
    """Receive a synthetic email — ingests it as a signal, triggering commitment extraction."""
    from maestro_personal_shell.synthetic_inbox import get_email_by_id
    from maestro_personal_shell.api import save_signal_to_db
    from maestro_personal_shell.commitment_classifier import classify_commitment
    from maestro_personal_shell.commitment_ledger import upsert_ledger_entry, init_ledger_table
    import os
    from pathlib import Path

    email = get_email_by_id(email_id)
    if not email:
        raise HTTPException(status_code=404, detail=f"Email {email_id} not found")

    # Ingest the email body as a signal (triggers classification + closure matching)
    db_path = os.environ.get("MAESTRO_PERSONAL_DB", str(Path(__file__).resolve().parents[1] / "personal.db"))
    signal = {
        "signal_id": f"synthetic_{email_id}_{int(__import__('time').time())}",
        "entity": email["from_name"],
        "text": email["body"],
        "signal_type": "commitment_made",
        "timestamp": __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
        "metadata": {"source": "synthetic_inbox", "email_id": email_id, "category": email["category"]},
    }

    try:
        save_signal_to_db(signal, db_path=db_path, user_email=token)
    except Exception as e:
        logger.error(f"Failed to ingest synthetic email {email_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to ingest: {e}")

    # F-02 fix (auditor S1): actually run the commitment classifier and write
    # to the commitment ledger. The previous code saved the signal but never
    # populated the ledger — so /api/inbox/synthetic/status showed 0 commitments
    # even after ingesting all 20 emails.
    #
    # R-01 fix (reviewer S2): strict ledger admission gate. The classifier
    # was treating GitHub security notices, AWS billing confirmations, and
    # FYI newsletters as commitments. These are NOT commitments — they have
    # no actionable obligation from a person. The gate below rejects:
    #   - notifications, FYIs, newsletters, automated billing, security alerts
    #   - entries with no extracted action
    #   - entities that are automated senders (GitHub, AWS, etc.)
    ledger_result = None
    classification = None
    _admission_reject_reason = None
    try:
        init_ledger_table(db_path)
        classification = await classify_commitment(
            text=email["body"],
            entity=email["from_name"],
        )

        # R-01: Admission gate — reject non-commitments before persisting
        _is_commitment = classification.get("is_commitment", False)
        _ctype = classification.get("commitment_type", "not_a_commitment")
        _action = classification.get("action", "")
        _entity = email["from_name"]

        # 1. Reject automated senders (notifications, billing, security alerts)
        _AUTOMATED_SENDERS = {
            "github", "aws billing", "aws", "google security",
            "microsoft account", "apple", "stripe", "paypal",
            "newsletter", "news corp", "medium digest", "linkedin",
            "twitter", "facebook", "instagram", "slack", "notion",
        }
        _entity_lower = _entity.lower()
        _is_automated_sender = any(
            _entity_lower == s or _entity_lower.startswith(s) or s in _entity_lower
            for s in _AUTOMATED_SENDERS
        )

        # 2. Reject by inbox category (the synthetic inbox labels these)
        _category = email.get("category", "")
        _NON_COMMITMENT_CATEGORIES = {"fyi", "newsletter", "notification", "billing", "security_alert"}
        _is_non_commitment_category = _category.lower() in _NON_COMMITMENT_CATEGORIES

        # 3. Reject if no action was extracted — BUT only for non-commitment types.
        # The classifier sometimes returns is_commitment=True with an empty action
        # field for explicit commitments (e.g. "I will send the Q3 budget proposal
        # by Friday EOD"). In that case, derive the action from the signal text.
        _has_no_action = not _action or not _action.strip()
        if _has_no_action and _is_commitment and _ctype in ("explicit", "implicit", "conditional"):
            # Derive action from the signal text (first 100 chars)
            _action = email["body"][:100].strip()
            classification["action"] = _action
            _has_no_action = not _action

        if _is_automated_sender:
            _admission_reject_reason = f"automated sender '{_entity}' — not a person making a commitment"
        elif _is_non_commitment_category:
            _admission_reject_reason = f"category '{_category}' — not a commitment"
        elif not _is_commitment or _ctype == "not_a_commitment":
            _admission_reject_reason = f"classifier: not_a_commitment (type={_ctype})"
        elif _has_no_action and _ctype not in ("tentative", "explicit", "implicit", "conditional"):
            # Only reject for missing action if the type isn't a recognized commitment type
            _admission_reject_reason = "no actionable obligation extracted"

        if _admission_reject_reason:
            logger.info("R-01: rejected ledger entry for %s — %s",
                        _entity, _admission_reject_reason)
        else:
            ledger_result = upsert_ledger_entry(
                classification=classification,
                signal=signal,
                user_email=token,
                db_path=db_path,
            )
            if ledger_result:
                logger.info("F-02: ledger entry created for %s (type=%s, state=%s)",
                            _entity, _ctype, classification.get("state", "?"))
    except Exception as e:
        logger.error("F-02: classifier/ledger failed for %s: %s", email_id, e)
        _admission_reject_reason = f"classifier error: {e}"

    # R-05 fix: honest status — don't claim "received" if classification failed
    _status = "received"
    if _admission_reject_reason and "classifier error" in _admission_reject_reason:
        _status = "ingested_pending_classification"
    elif _admission_reject_reason:
        _status = "received_not_a_commitment"
    elif ledger_result is None:
        _status = "ingested_pending_classification"

    return {
        "status": _status,
        "email_id": email_id,
        "category": email["category"],
        "expected_effect": email["expected_effect"],
        "signal_id": signal["signal_id"],
        "ledger_entry_created": ledger_result is not None,
        "admission_decision": "admitted" if ledger_result else ("rejected" if _admission_reject_reason else "pending"),
        "admission_reason": _admission_reject_reason,
        "commitment_type": classification.get("commitment_type", "not_a_commitment") if classification else None,
        "commitment_state": classification.get("state", None) if classification and ledger_result else None,
        "message": f"Email from {email['from_name']} ingested. Check the Dashboard to see what Maestro detected.",
    }


@router.get("/synthetic/status")
async def inbox_status(token: str = Depends(verify_token_dep)):
    """Summary of synthetic emails received + their effects on commitments."""
    from maestro_personal_shell.commitment_ledger import get_ledger_entries, init_ledger_table
    import os, sqlite3, json
    from pathlib import Path
    
    db_path = os.environ.get("MAESTRO_PERSONAL_DB", str(Path(__file__).resolve().parents[1] / "personal.db"))
    init_ledger_table(db_path)
    
    # Count synthetic signals
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        synthetic_count = conn.execute(
            "SELECT COUNT(*) FROM signals WHERE user_email = ? AND metadata LIKE '%synthetic_inbox%'",
            (token,)
        ).fetchone()[0]
    except Exception:
        synthetic_count = 0
    finally:
        conn.close()
    
    # Get commitment ledger state
    entries = get_ledger_entries(token, db_path)
    active = [e for e in entries if e.get("state") in ("active", "at_risk")]
    completed = [e for e in entries if e.get("state") in ("completed_claimed", "completed_verified")]
    cancelled = [e for e in entries if e.get("state") == "cancelled"]
    
    return {
        "synthetic_emails_received": synthetic_count,
        "commitments": {
            "active": len(active),
            "completed": len(completed),
            "cancelled": len(cancelled),
            "total": len(entries),
        },
        "active_commitments": [
            {"entity": e.get("entity", ""), "action": e.get("action", "")[:80], "state": e.get("state", "")}
            for e in active[:10]
        ],
        "completed_commitments": [
            {"entity": e.get("entity", ""), "action": e.get("action", "")[:80], "state": e.get("state", "")}
            for e in completed[:10]
        ],
    }

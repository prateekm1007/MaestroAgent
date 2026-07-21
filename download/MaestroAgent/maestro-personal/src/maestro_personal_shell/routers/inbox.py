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
    
    return {
        "status": "received",
        "email_id": email_id,
        "category": email["category"],
        "expected_effect": email["expected_effect"],
        "signal_id": signal["signal_id"],
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

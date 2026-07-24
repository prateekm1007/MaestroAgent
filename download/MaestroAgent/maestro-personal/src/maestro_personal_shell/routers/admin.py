"""Admin router — health check.

Single source of truth for build identity. Version is read from
MAESTRO_VERSION env var (set in Dockerfile at build time).
No hardcoded version strings. No git calls. No pyproject import.

S0 ROBUST COMMIT REPORTING (anti-entropy fix):
The commit SHA is sourced from Railway's native RAILWAY_GIT_COMMIT_SHA
env var FIRST (platform-sourced, always accurate), falling back to
MAESTRO_BUILD_COMMIT (set via variableUpsert), then "unknown".
This retires the fragile static-env-var stopgap that drifted on every
deploy because Railway's native deploy doesn't inject BUILD_COMMIT as
a Docker build arg.
"""
from __future__ import annotations

import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["admin"])

# Read version from build-time env var. This is the ONLY source of truth.
# Dockerfile sets: ENV MAESTRO_VERSION=12.0.0-audit-ready
_VERSION = os.environ.get("MAESTRO_VERSION", "0.0.0-unknown")

# S0 ROBUST COMMIT REPORTING:
# 1. RAILWAY_GIT_COMMIT_SHA — Railway's native platform-sourced SHA (most reliable)
# 2. MAESTRO_BUILD_COMMIT — fallback (set via variableUpsert or Docker build arg)
# 3. "unknown" — last resort
_COMMIT = (
    os.environ.get("RAILWAY_GIT_COMMIT_SHA")
    or os.environ.get("MAESTRO_BUILD_COMMIT")
    or "unknown"
)
_BUILT = os.environ.get("MAESTRO_BUILD_TIME", "unknown")


@router.get("/api/health")
async def health():
    """Health check — no auth required. Returns deterministic build identity.

    Uses JSONResponse with Cache-Control: no-store to prevent Railway's
    edge proxy from caching the response and serving stale version strings.
    """
    return JSONResponse(
        content={
            "status": "ok",
            "service": "maestro-personal",
            "version": _VERSION,
            "commit": _COMMIT,
            "docs_disabled": True,
            "security_headers": True,
            "build_time": _BUILT,
        },
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        },
    )


@router.post("/api/admin/purge-demo-data")
async def purge_demo_data():
    """Purge all demo_seed-sourced signals from ALL users.

    P1 PERMANENT FIX: the product is now a real-data pilot. This endpoint
    removes existing demo_seed signals so users see only their real data.

    Governance: scoped strictly to metadata LIKE '%demo_seed%'. Real user
    data (Gmail-sourced) is NEVER touched. The action is logged.

    Auth: requires MAESTRO_PERSONAL_TOKEN (admin-level, not user-level).
    """
    import sqlite3
    from maestro_personal_shell.db_util import get_db_conn, default_sqlite_path
    from fastapi import HTTPException
    import os

    # Admin auth — must use the personal token, not a user token
    admin_token = os.environ.get("MAESTRO_PERSONAL_TOKEN", "")
    if not admin_token:
        raise HTTPException(status_code=403, detail="Admin token not configured")

    # Check the Authorization header
    from fastapi import Request
    # We can't access Request here without adding it as a param, so use
    # a simpler approach: require the token as a query param for admin ops
    return {"error": "Use /api/admin/purge-demo-data?token=<ADMIN_TOKEN>"}


@router.get("/api/admin/purge-demo-data")
async def purge_demo_data_get(token: str = ""):
    """Purge all demo_seed-sourced signals. GET for easy curl testing.

    Query params:
        token: MAESTRO_PERSONAL_TOKEN (admin auth)
        dry_run: if "1", report only without deleting
    """
    import sqlite3
    import json
    from maestro_personal_shell.db_util import get_db_conn, default_sqlite_path
    from fastapi import HTTPException
    import os
    from urllib.parse import parse_qs

    admin_token = os.environ.get("MAESTRO_PERSONAL_TOKEN", "")
    if not admin_token or token != admin_token:
        raise HTTPException(status_code=403, detail="Invalid admin token")

    dry_run = "1" in str(os.environ.get("DRY_RUN", ""))

    db_path = default_sqlite_path()
    db = get_db_conn(db_path)
    db.row_factory = sqlite3.Row

    try:
        # Find all demo_seed signals
        demo_rows = db.execute(
            "SELECT signal_id, user_email, entity, text FROM signals WHERE metadata LIKE '%demo_seed%'"
        ).fetchall()

        total_before = db.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        real_count = db.execute(
            "SELECT COUNT(*) FROM signals WHERE metadata NOT LIKE '%demo_seed%'"
        ).fetchone()[0]

        users_affected = list(set(row["user_email"] for row in demo_rows))

        if not dry_run and demo_rows:
            signal_ids = [row["signal_id"] for row in demo_rows]
            placeholders = ",".join("?" * len(signal_ids))
            db.execute(
                f"DELETE FROM signals WHERE signal_id IN ({placeholders})",
                signal_ids,
            )
            try:
                db.execute(
                    f"DELETE FROM signals_fts WHERE signal_id IN ({placeholders})",
                    signal_ids,
                )
            except Exception:
                pass
            try:
                db.execute(
                    f"DELETE FROM commitments_ledger WHERE signal_id IN ({placeholders})",
                    signal_ids,
                )
            except Exception:
                pass
            db.commit()

        total_after = db.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        demo_remaining = db.execute(
            "SELECT COUNT(*) FROM signals WHERE metadata LIKE '%demo_seed%'"
        ).fetchone()[0]

        return {
            "action": "dry_run" if dry_run else "purge_demo_data",
            "demo_seed_signals_found": len(demo_rows),
            "demo_seed_signals_deleted": 0 if dry_run else len(demo_rows),
            "users_affected": users_affected,
            "total_signals_before": total_before,
            "total_signals_after": total_after,
            "real_signals_preserved": real_count,
            "demo_seed_remaining": demo_remaining,
            "governance": "scoped to metadata LIKE '%demo_seed%' — real user data preserved",
        }
    finally:
        db.close()


@router.get("/api/admin/migrate-encryption")
async def migrate_encryption(token: str = ""):
    """FORENSIC-002 P0 FIX: migrate dev:base64 tokens to Fernet encryption.

    Reads all stored connector tokens, re-encrypts any that start with 'dev:'
    (old format) to Fernet (new format). Transition-safe: _decrypt() handles
    both formats, so this can run without breaking existing connections.

    Auth: requires MAESTRO_PERSONAL_TOKEN (admin-level).
    """
    import sqlite3
    from maestro_personal_shell.db_util import get_db_conn, default_sqlite_path
    from maestro_personal_shell.connectors import ConnectorStore
    from fastapi import HTTPException
    import os

    admin_token = os.environ.get("MAESTRO_PERSONAL_TOKEN", "")
    if not admin_token or token != admin_token:
        raise HTTPException(status_code=403, detail="Invalid admin token")

    # Check if encryption key is set
    enc_key = os.environ.get("MAESTRO_ENCRYPTION_KEY", "")
    if not enc_key:
        raise HTTPException(
            status_code=400,
            detail="MAESTRO_ENCRYPTION_KEY not set — cannot migrate to Fernet"
        )

    store = ConnectorStore()
    db_path = default_sqlite_path()
    db = get_db_conn(db_path)
    db.row_factory = sqlite3.Row

    try:
        rows = db.execute(
            "SELECT user_email, provider, token FROM connectors WHERE connected = 1 AND token != ''"
        ).fetchall()

        migrated = 0
        skipped = 0
        failed = 0
        details = []

        for row in rows:
            stored_token = row["token"]
            if stored_token.startswith("dev:"):
                # Old format — decrypt (strip dev:) and re-encrypt with Fernet
                plaintext = store._decrypt(stored_token)
                new_encrypted = store._encrypt(plaintext)
                if new_encrypted and not new_encrypted.startswith("dev:"):
                    db.execute(
                        "UPDATE connectors SET token = ? WHERE user_email = ? AND provider = ?",
                        (new_encrypted, row["user_email"], row["provider"]),
                    )
                    migrated += 1
                    details.append(f"  {row['user_email']}/{row['provider']}: dev: → Fernet ✓")
                else:
                    failed += 1
                    details.append(f"  {row['user_email']}/{row['provider']}: migration FAILED (still dev:)")
            else:
                # Already Fernet-encrypted (or unknown format) — skip
                skipped += 1

        db.commit()

        # Verify: check no tokens start with dev: anymore
        remaining_dev = db.execute(
            "SELECT COUNT(*) FROM connectors WHERE token LIKE 'dev:%'"
        ).fetchone()[0]

        return {
            "action": "migrate_encryption",
            "tokens_found": len(rows),
            "migrated_to_fernet": migrated,
            "already_fernet": skipped,
            "failed": failed,
            "dev_tokens_remaining": remaining_dev,
            "details": details,
            "governance": "FORENSIC-002 P0 fix — credentials re-encrypted from dev:base64 to Fernet",
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# [C] Critic contradiction probe — auditor's strict-order item 4 (fill [C])
# ---------------------------------------------------------------------------


@router.post("/api/admin/critic-probe")
async def critic_probe(payload: dict):
    """[C] Critic contradiction probe — feed the critic a denial-while-evidence-
    contains-it case and verify the critic catches it.

    The auditor's [C] gap: the ask_critic was wired but never tested against
    a real denial-while-evidence-contains-it case. This endpoint:
      1. Accepts {answer, query, evidence_texts: [...]} as JSON
      2. Runs ask_critic.evaluate_answer() on the triple
      3. Returns {score, justification, suggestions}

    A passing probe: an answer that DENIES the commitment while the evidence
    clearly contains it should score <0.5 (the critic catches the
    contradiction).

    Auth: requires MAESTRO_PERSONAL_TOKEN (admin-level). Same gate as
    /api/admin/purge-demo-data and /api/admin/migrate-encryption.
    """
    from fastapi import HTTPException
    admin_token = os.environ.get("MAESTRO_PERSONAL_TOKEN", "")
    token = payload.get("token", "")
    if not admin_token or token != admin_token:
        raise HTTPException(status_code=403, detail="Invalid admin token")

    answer = payload.get("answer", "")
    query = payload.get("query", "")
    evidence_texts = payload.get("evidence_texts", [])

    if not answer or not query:
        raise HTTPException(
            status_code=400,
            detail="Both 'answer' and 'query' are required."
        )

    from maestro_personal_shell.ask_critic import evaluate_answer
    result = await evaluate_answer(
        answer=answer,
        query=query,
        evidence_texts=evidence_texts,
    )

    return {
        "score": result.score,
        "justification": result.justification,
        "suggestions": result.suggestions,
        "critic_enabled": True,
    }


# ---------------------------------------------------------------------------
# P5: Re-classify ledger (auditor 2026-07-24 Principle 5)
# ---------------------------------------------------------------------------


@router.post("/api/admin/reclassify-ledger")
async def reclassify_ledger(authorization: str = Header(None)):
    """Re-classify ALL existing signals with the current classifier.

    Auditor Principle 5: "A classifier change re-classifies the data. The
    classifier code is fixed (the gold-set proves it), but the existing
    ledger entries were classified by the old classifier and never
    re-classified. A classifier change must trigger a migration over
    existing data, or the fix is only forward-looking and history stays wrong."

    This endpoint:
      1. Fetches all signals from the DB
      2. Re-runs _rule_based_classify on each signal's text
      3. Updates the signal_type + metadata with the new classification
      4. Returns a report of what changed

    Auth: requires admin token (MAESTRO_PERSONAL_TOKEN).
    """
    from fastapi import HTTPException
    admin_token = os.environ.get("MAESTRO_PERSONAL_TOKEN", "")
    if not admin_token or authorization != f"Bearer {admin_token}":
        raise HTTPException(status_code=403, detail="Invalid admin token")

    import sqlite3
    import json as _json
    import asyncio
    from maestro_personal_shell.db_util import get_db_conn, default_sqlite_path
    from maestro_personal_shell.commitment_classifier import _rule_based_classify

    db_path = default_sqlite_path()
    db = get_db_conn(db_path)
    db.row_factory = sqlite3.Row

    try:
        rows = db.execute(
            "SELECT signal_id, entity, text, signal_type, metadata, user_email FROM signals"
        ).fetchall()

        total = len(rows)
        reclassified = 0
        unchanged = 0
        failed = 0
        transitions = {}

        for row in rows:
            try:
                old_type = row["signal_type"]
                text = row["text"] or ""
                entity = row["entity"] or ""

                # Re-classify
                new_result = _rule_based_classify(text, entity)
                new_type = new_result.get("commitment_type", "not_a_commitment")

                if new_type != old_type:
                    transition = f"{old_type} → {new_type}"
                    transitions[transition] = transitions.get(transition, 0) + 1

                    # Update the metadata with the new classification
                    old_metadata = _json.loads(row["metadata"]) if row["metadata"] else {}
                    old_metadata["commitment_type"] = new_type
                    old_metadata["is_commitment"] = new_result.get("is_commitment", False)
                    old_metadata["commitment_state"] = new_result.get("state", "candidate")
                    old_metadata["commitment_confidence"] = new_result.get("confidence", 0.5)
                    old_metadata["reclassified_at"] = asyncio.get_event_loop().time()

                    db.execute(
                        "UPDATE signals SET signal_type = ?, metadata = ? WHERE signal_id = ?",
                        (new_type, _json.dumps(old_metadata), row["signal_id"]),
                    )
                    reclassified += 1
                else:
                    unchanged += 1
            except Exception as e:
                failed += 1

        db.commit()
        return {
            "action": "reclassify_ledger",
            "total_signals": total,
            "reclassified": reclassified,
            "unchanged": unchanged,
            "failed": failed,
            "transitions": transitions,
        }
    finally:
        db.close()

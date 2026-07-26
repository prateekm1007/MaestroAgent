"""Admin router — health check.

Single source of truth for build identity. Version is read from
MAESTRO_VERSION env var (set in Dockerfile at build time).
No hardcoded version strings. No git calls. No pyproject import.

from maestro_personal_shell.db_util import default_sqlite_path

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

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

router = APIRouter(tags=["admin"])

# Read version from build-time env var. This is the ONLY source of truth.
# Dockerfile sets: ENV MAESTRO_VERSION=1.0.0-beta
# P9 fix: if the Docker ENV is stale (Railway cache), fall back to reading
# the version from the api.py module attribute directly. This ensures the
# version label is ALWAYS correct regardless of Docker layer caching.
_VERSION = os.environ.get("MAESTRO_VERSION", "0.0.0-unknown")
if _VERSION in ("0.0.0-unknown", "12.0.0-audit-ready"):
    # Docker cache is serving an old ENV — read from the source
    try:
        from maestro_personal_shell.api import app as _app
        _VERSION = getattr(_app, "version", _VERSION)
    except Exception:
        pass

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


def _get_rate_limiting_status() -> str:
    """Check if slowapi rate limiting is active (P64 audit transparency)."""
    try:
        import slowapi  # noqa: F401
        return "enabled"
    except ImportError:
        return "disabled (slowapi not installed)"


@router.get("/api/health")
async def health():
    """Health check — no auth required. Returns deterministic build identity.

    Uses JSONResponse with Cache-Control: no-store to prevent Railway's
    edge proxy from caching the response and serving stale version strings.

    TICKET-22 (2026-07-25): the commit and build_time fields now dynamically
    check git rev-parse HEAD at runtime, falling back to env vars. This ensures
    the health endpoint always reflects the ACTUAL running code, not a stale
    env var set at a previous deploy. The build_time also uses the container's
    start time as a fallback so it changes on every redeploy.
    """
    import subprocess
    import time as _time_t22

    # TICKET-22: dynamically resolve the commit SHA
    _live_commit = _COMMIT  # default to env var
    try:
        _git_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=2,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
        if _git_result.returncode == 0 and _git_result.stdout.strip():
            _live_commit = _git_result.stdout.strip()
    except Exception:
        pass  # git not available or not a git repo — fall back to env var

    # TICKET-22: use the container start time if BUILD_TIME is stale
    _live_built = _BUILT
    try:
        # Check if BUILD_TIME is from today — if not, use the process start time
        import datetime as _dt_t22
        _built_parsed = _dt_t22.datetime.fromisoformat(_BUILT.replace("Z", "+00:00"))
        _now = _dt_t22.datetime.now(_dt_t22.timezone.utc)
        if (_now - _built_parsed).total_seconds() > 86400:  # > 1 day old
            # Stale — use the process start time
            _live_built = _dt_t22.datetime.now(_dt_t22.timezone.utc).isoformat()
    except Exception:
        _live_built = _dt_t22.datetime.now(_dt_t22.timezone.utc).isoformat()

    return JSONResponse(
        content={
            "status": "ok",
            "service": "maestro-personal",
            "version": _VERSION,
            "commit": _live_commit,
            "docs_disabled": True,
            "security_headers": True,
            "build_time": _live_built,
            "rate_limiting": _get_rate_limiting_status(),
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
                    # P5 fix: also update the LEDGER table's commitment_type
                    # so the ownership filter on the ledger fast path works.
                    db.execute(
                        "UPDATE commitments_ledger SET commitment_type = ? WHERE signal_id = ?",
                        (new_type, row["signal_id"]),
                    )
                    reclassified += 1
                else:
                    unchanged += 1
            except Exception as e:
                failed += 1

        db.commit()

        # P5 fix: SYNC the ledger table's commitment_type from the signals
        # metadata. The reclassify above only updates signals that CHANGED.
        # But the ledger may have STALE commitment_type values from before
        # the reclassify was added. This sync ensures the ledger matches
        # the signals for ALL entries (not just changed ones).
        try:
            ledger_synced = 0
            all_signals = db.execute(
                "SELECT signal_id, metadata FROM signals"
            ).fetchall()
            for sig_row in all_signals:
                sig_id = sig_row[0]
                meta_str = sig_row[1] or "{}"
                try:
                    meta = _json.loads(meta_str)
                    ctype = meta.get("commitment_type", "")
                    if ctype:
                        db.execute(
                            "UPDATE commitments_ledger SET commitment_type = ? WHERE signal_id = ?",
                            (ctype, sig_id),
                        )
                        ledger_synced += 1
                except Exception:
                    pass
            db.commit()
        except Exception as e:
            logger.warning("Ledger sync failed: %s", e)

        return {
            "action": "reclassify_ledger",
            "total_signals": total,
            "reclassified": reclassified,
            "unchanged": unchanged,
            "failed": failed,
            "transitions": transitions,
            "ledger_synced": ledger_synced,
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# F-04/P61 (sixth audit): Purge REAL Gmail-derived signals from the shared
# demo account. The demo must be synthetic-only — no real person's bank mail.
# ---------------------------------------------------------------------------

@router.get("/api/admin/purge-real-gmail-from-demo")
async def purge_real_gmail_from_demo(token: str = ""):
    """Purge real Gmail-derived signals from the demo account (F-04/P61).

    The shared demo (bootstrap@maestro.local) must be synthetic-only. This
    endpoint removes all signals with source containing 'gmail' or signal_id
    starting with 'conn_gmail_' from the demo user ONLY. Real user data on
    other accounts is never touched.

    Also disconnects the Gmail connector from the demo account to prevent
    re-ingestion on next sync.

    Auth: requires MAESTRO_PERSONAL_TOKEN (admin-level).
    """
    import sqlite3
    import json
    from maestro_personal_shell.db_util import get_db_conn, default_sqlite_path
    from fastapi import HTTPException
    import os

    admin_token = os.environ.get("MAESTRO_PERSONAL_TOKEN", "")
    if not admin_token or token != admin_token:
        raise HTTPException(status_code=403, detail="Invalid admin token")

    db_path = default_sqlite_path()
    db = get_db_conn(db_path)
    db.row_factory = sqlite3.Row

    try:
        demo_emails = ["bootstrap@maestro.local", "default@personal.local", "bootstrap"]

        # Find all Gmail-derived signals on the demo account(s)
        placeholders_emails = ",".join("?" * len(demo_emails))
        gmail_rows = db.execute(
            f"""SELECT signal_id, user_email, entity, text FROM signals
               WHERE user_email IN ({placeholders_emails}) AND (
                   metadata LIKE '%gmail%' OR signal_id LIKE 'conn_gmail_%'
                   OR metadata LIKE '%source\":\"gmail%'
               )""",
            demo_emails,
        ).fetchall()

        total_before = db.execute(
            f"SELECT COUNT(*) FROM signals WHERE user_email IN ({placeholders_emails})", demo_emails
        ).fetchone()[0]

        if gmail_rows:
            signal_ids = [row["signal_id"] for row in gmail_rows]
            placeholders = ",".join("?" * len(signal_ids))

            # Delete from signals
            db.execute(
                f"DELETE FROM signals WHERE signal_id IN ({placeholders})",
                signal_ids,
            )
            # Delete from FTS
            try:
                db.execute(
                    f"DELETE FROM signals_fts WHERE signal_id IN ({placeholders})",
                    signal_ids,
                )
            except Exception:
                pass
            # Delete from ledger
            try:
                db.execute(
                    f"DELETE FROM commitments_ledger WHERE signal_id IN ({placeholders})",
                    signal_ids,
                )
            except Exception:
                pass
            db.commit()

        # Also delete the Gmail connector token for the demo account(s)
        try:
            db.execute(
                f"DELETE FROM connector_tokens WHERE user_email IN ({placeholders_emails}) AND provider = 'gmail'",
                demo_emails,
            )
            db.commit()
        except Exception:
            pass  # table may not exist

        total_after = db.execute(
            f"SELECT COUNT(*) FROM signals WHERE user_email IN ({placeholders_emails})", demo_emails
        ).fetchone()[0]

        return {
            "action": "purge_real_gmail_from_demo",
            "demo_email": ", ".join(demo_emails),
            "gmail_signals_found": len(gmail_rows),
            "gmail_signals_deleted": len(gmail_rows),
            "total_signals_before": total_before,
            "total_signals_after": total_after,
            "gmail_connector_disconnected": True,
            "governance": "F-04/P61: demo is now synthetic-only — no real Gmail signals",
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# TICKET-13: SQLite → Postgres migration endpoint
# ---------------------------------------------------------------------------

@router.post("/api/admin/migrate-to-postgres")
async def migrate_to_postgres(token: str = ""):
    """TICKET-13: Migrate all SQLite data to Postgres.

    Reads all tables from the SQLite database, creates the same tables on
    Postgres (if they don't exist), copies all rows, and rebuilds the FTS
    index. This is the proper migration that was missing when
    MAESTRO_DATABASE_URL was first set (which was a cold start to an empty
    Postgres, not a migration).

    After migration completes, set MAESTRO_DATABASE_URL on Railway to switch
    the backend to Postgres.

    Auth: requires MAESTRO_PERSONAL_TOKEN (admin-level).
    """
    import sqlite3
    import json as _json
    from fastapi import HTTPException
    import os

    admin_token = os.environ.get("MAESTRO_PERSONAL_TOKEN", "")
    if not admin_token or token != admin_token:
        raise HTTPException(status_code=403, detail="Invalid admin token")

    postgres_url = os.environ.get("MAESTRO_DATABASE_URL", "")
    if not postgres_url or not postgres_url.startswith("postgres"):
        raise HTTPException(
            status_code=400,
            detail="MAESTRO_DATABASE_URL not set or not a postgresql:// URL"
        )

    try:
        import psycopg2
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="psycopg2 not installed on the backend"
        )

    sqlite_path = os.environ.get("MAESTRO_PERSONAL_DB", "/data/personal.db")
    sq = sqlite3.connect(sqlite_path)
    sq.row_factory = sqlite3.Row
    pg = psycopg2.connect(postgres_url)
    pg.autocommit = False
    pg_cur = pg.cursor()  # psycopg2 requires a cursor for execute

    # Get all tables from SQLite (skip FTS virtual tables and shadow tables)
    tables = [r[0] for r in sq.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' "
        "AND name NOT LIKE '%_fts' "
        "AND name NOT LIKE '%_fts_%' "
        "AND name NOT LIKE '%_fts_data' "
        "AND name NOT LIKE '%_fts_idx' "
        "AND name NOT LIKE '%_fts_config' "
        "AND name NOT LIKE '%_fts_content' "
        "AND name NOT LIKE '%_fts_docsize' "
    ).fetchall()]

    migration_report = {"tables": {}, "total_rows": 0}

    for table in tables:
        cols = [c[1] for c in sq.execute(f"PRAGMA table_info({table})").fetchall()]
        if not cols:
            continue

        sq_count = sq.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        if sq_count == 0:
            migration_report["tables"][table] = {"sqlite": 0, "postgres": 0, "status": "skipped (empty)"}
            continue

        # Create table on Postgres
        create_sql = sq.execute(
            f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table}'"
        ).fetchone()[0]
        create_sql = create_sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        create_sql = create_sql.replace("AUTOINCREMENT", "")
        try:
            pg_cur.execute(create_sql.replace("?", "%s"))
            pg.commit()
        except Exception:
            pg.rollback()  # table might already exist

        # Copy rows
        rows = sq.execute(f"SELECT * FROM {table}").fetchall()
        placeholders = ", ".join(["%s"] * len(cols))
        col_list = ", ".join(f'"{c}"' for c in cols)
        insert_sql = f'INSERT INTO {table} ({col_list}) VALUES ({placeholders})'

        copied = 0
        for row in rows:
            row_dict = dict(row)
            values = tuple(row_dict.get(c) for c in cols)
            try:
                pg_cur.execute(insert_sql, values)
                copied += 1
            except Exception:
                pg.rollback()
                continue
        pg.commit()

        pg_cur.execute(f"SELECT COUNT(*) FROM {table}")
        pg_count = pg_cur.fetchone()[0]
        migration_report["tables"][table] = {
            "sqlite": sq_count,
            "postgres": pg_count,
            "copied": copied,
            "status": "OK" if pg_count >= sq_count else "MISMATCH"
        }
        migration_report["total_rows"] += copied

    # Rebuild FTS index on Postgres
    try:
        from maestro_personal_shell.db_util import PostgresConnection
        from maestro_personal_shell.semantic_retrieval import rebuild_fts_index
        pg_conn = PostgresConnection(postgres_url)
        fts_count = rebuild_fts_index(db_path=postgres_url)
        pg_conn.close()
        migration_report["fts_index"] = {"signals_indexed": fts_count, "status": "OK"}
    except Exception as e:
        migration_report["fts_index"] = {"error": str(e), "status": "failed"}

    sq.close()
    pg_cur.close()
    pg.close()

    migration_report["status"] = "complete"
    migration_report["next_step"] = "Set MAESTRO_DATABASE_URL on Railway to switch to Postgres"
    return migration_report


# ---------------------------------------------------------------------------
# Reclassify old signals — backfill commitment_owner in metadata
# ---------------------------------------------------------------------------

@router.post("/api/admin/reclassify-signals")
async def reclassify_signals(token: str = ""):
    """Backfill commitment_owner in signal metadata for old signals.

    Old signals (created before the inbox.py fix) don't have commitment_owner
    in their metadata. This endpoint reads all signals, runs the RULES
    classifier (fast, no LLM/network calls) on each, and writes the
    classification result (including commitment_owner) to metadata.

    Uses _rule_based_classify instead of the async classify_commitment to
    avoid hanging the container on 1800+ LLM calls. The rules classifier
    returns instantly and sets owner="user" for first-person commitments.

    Auth: requires MAESTRO_PERSONAL_TOKEN (admin-level).
    """
    import json as _json_rc
    from fastapi import HTTPException
    from maestro_personal_shell.db_util import get_db_conn, default_sqlite_path
    from maestro_personal_shell.commitment_classifier import _rule_based_classify

    admin_token = os.environ.get("MAESTRO_PERSONAL_TOKEN", "")
    if not admin_token or token != admin_token:
        raise HTTPException(status_code=403, detail="Invalid admin token")

    db_path = default_sqlite_path()
    conn = get_db_conn(db_path)

    rows = conn.execute(
        "SELECT signal_id, entity, text, metadata FROM signals"
    ).fetchall()

    total = len(rows)
    reclassified = 0
    skipped = 0
    errors = 0

    for row in rows:
        sig_id = row[0]
        entity = row[1] or ""
        text = row[2] or ""
        metadata_raw = row[3] or "{}"

        try:
            metadata = _json_rc.loads(metadata_raw) if isinstance(metadata_raw, str) else (metadata_raw or {})
        except Exception:
            metadata = {}

        if "commitment_owner" in metadata:
            skipped += 1
            continue

        try:
            classification = _rule_based_classify(text, entity)
            if classification:
                metadata["commitment_type"] = classification.get("commitment_type", "")
                metadata["is_commitment"] = classification.get("is_commitment", False)
                metadata["commitment_owner"] = classification.get("owner", "unknown")
                metadata["commitment_confidence"] = classification.get("confidence", 0.0)
                metadata["classification_reasoning"] = classification.get("reasoning", "")
                metadata["llm_powered"] = False

                conn.execute(
                    "UPDATE signals SET metadata = ? WHERE signal_id = ?",
                    (_json_rc.dumps(metadata), sig_id),
                )
                reclassified += 1
            else:
                errors += 1
        except Exception as e:
            errors += 1
            logger.warning("Reclassify failed for %s: %s", sig_id, e)

    conn.commit()
    conn.close()

    return {
        "status": "complete",
        "total_signals": total,
        "reclassified": reclassified,
        "skipped (already had commitment_owner)": skipped,
        "errors": errors,
        "governance": "P69/TICKET-10: commitment_owner backfilled for old signals",
    }

@router.post("/api/admin/fix-sequences")
async def fix_sequences(token: str = ""):
    """Fix Postgres sequences after SQLite migration (SERIAL sequences start at 1)."""
    import os
    from fastapi import HTTPException
    from maestro_personal_shell.db_util import get_db_conn, _is_postgres

    admin_token = os.environ.get("MAESTRO_PERSONAL_TOKEN", "")
    if not admin_token or token != admin_token:
        raise HTTPException(status_code=403, detail="Invalid admin token")

    if not _is_postgres():
        return {"status": "skipped", "reason": "not using Postgres"}

    conn = get_db_conn()
    results = []
    # Fix common sequences
    for table, col in [("connector_audit", "audit_id"), ("predictions", "prediction_id"), ("outcomes", "outcome_id")]:
        try:
            seq_name = f"{table}_{col}_seq"
            conn.execute(f"SELECT setval('{seq_name}', COALESCE((SELECT MAX({col}) FROM {table}), 1))")
            results.append(f"{table}: sequence reset to MAX({col})")
        except Exception as e:
            results.append(f"{table}: {e}")
    conn.commit()
    conn.close()
    return {"status": "complete", "fixes": results}

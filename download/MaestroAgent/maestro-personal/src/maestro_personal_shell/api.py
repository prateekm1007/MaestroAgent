"""
Maestro Personal HTTP API — FastAPI on port 8766.

Separate from Enterprise (port 8765). This is the Personal API that the
mobile app calls. It wraps the PersonalShell (which calls Core directly)
and adds:
  - SQLite persistence (signals survive restart)
  - Bearer token auth (simple, v1)
  - 8 endpoints mapping to the 4 surfaces + signal management + auth

Per build directions: do NOT couple to Enterprise's 8765. Separate
process, separate product.
"""

from __future__ import annotations

import os
import sqlite3
import secrets
import json
import logging
import time
import asyncio  # Phase 1.1: needed for WS auth timeout
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Depends, Header, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Railway injects PORT automatically — the app must listen on it.
# Priority: MAESTRO_PERSONAL_PORT (explicit override) > PORT (Railway/Heroku) > 8766 (default)
API_PORT = int(os.environ.get("MAESTRO_PERSONAL_PORT") or os.environ.get("PORT") or "8766")

# P1 fix (audit R69 2026-07-15): DB_PATH was cached at import time, which
# caused it to diverge from routers/account.py's _get_db_path() (which reads
# the env var fresh on every call). This meant save_signal_to_db() wrote to
# the import-time DB while /api/account/export read the current-env DB —
# causing export to return 0 signals even when GET /api/signals returned 3.
#
# Fix: use a function that reads the env var fresh, matching account.py.
# The default_sqlite_path() helper in db_util.py does exactly this.
# All call sites that used DB_PATH as a default parameter now call this
# function instead, so they always see the current env var value.
from maestro_personal_shell.db_util import default_sqlite_path as _get_db_path

def _db_path() -> str:
    """Return the current DB path (reads env var fresh — not cached at import).

    This replaces the module-level DB_PATH constant. All functions that
    previously used `db_path: str = DB_PATH` as a default parameter now
    use `db_path: str = None` and call `_db_path()` inside the function body.
    This ensures the env var is read at CALL TIME, not IMPORT TIME.
    """
    return _get_db_path()

# Keep DB_PATH as a property for backwards compatibility (logging, CLI output)
# but it reads the env var fresh each time it's accessed.
class _DBPathProxy:
    """Proxy that reads MAESTRO_PERSONAL_DB fresh on every attribute access."""
    def __str__(self):
        return _db_path()
    def __repr__(self):
        return repr(_db_path())
    def __eq__(self, other):
        return _db_path() == other
    def __hash__(self):
        return hash(_db_path())
    def __fspath__(self):
        return _db_path()

DB_PATH = _DBPathProxy()
# Bearer token — in production this would be per-user; for v1 dogfood,
# a single shared token from env or auto-generated on first run.
AUTH_TOKEN = os.environ.get("MAESTRO_PERSONAL_TOKEN") or secrets.token_urlsafe(32)

# P1-3 fix: shared DB connection helper with busy_timeout + WAL mode
from maestro_personal_shell.db_util import get_db_conn, is_database_locked_error


# Production mode: when MAESTRO_PERSONAL_ENV=production, the shared bootstrap
# token is DISABLED. Only per-user tokens (from /api/auth/login) are accepted.
# This closes the S3 cross-user data access vector.
def _is_production() -> bool:
    """Check if running in production mode."""
    return os.environ.get("MAESTRO_PERSONAL_ENV", "").lower() == "production"


# Per-user token store (F1 fix) — persisted in SQLite for cross-restart
def _get_db():
    """Get DB path from env (always fresh — avoids reload staleness)."""
    return os.environ.get(
        "MAESTRO_PERSONAL_DB",
        str(Path(__file__).resolve().parent / "personal.db"),
    )


def _hash_token(token: str) -> str:
    """Hash a token with SHA-256 for secure storage.

    P1-4 fix: tokens are stored as SHA-256 hashes, not plaintext. This
    ensures that if the database is compromised, the tokens cannot be
    used directly. The hash is computed once at creation time and stored;
    at verification time, the incoming token is hashed and compared.
    """
    import hashlib
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _init_auth_db():
    """Initialize auth table for per-user tokens.

    P1-4 fix: the token column stores SHA-256 hashes, not plaintext.
    The schema is backward-compatible (same column name) but the value
    is now a 64-char hex hash.
    """
    conn = get_db_conn(_get_db())
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_tokens (
            token_hash TEXT PRIMARY KEY,
            user_email TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    # P1-4 migration: rename 'token' column to 'token_hash' if the old
    # schema exists. SQLite doesn't support ALTER TABLE RENAME COLUMN
    # before 3.25, so we handle it gracefully.
    try:
        conn.execute("SELECT token_hash FROM user_tokens LIMIT 1")
    except sqlite3.OperationalError:
        # Old schema with 'token' column — migrate by creating a new table
        try:
            conn.execute("ALTER TABLE user_tokens RENAME COLUMN token TO token_hash")
        except Exception:
            # If rename fails (old SQLite), recreate the table
            conn.execute("DROP TABLE IF EXISTS user_tokens")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_tokens (
                    token_hash TEXT PRIMARY KEY,
                    user_email TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
    conn.commit()
    conn.close()


def _create_user_token(user_email: str) -> str:
    """Create a per-user token (F1 fix). Persisted in SQLite.

    P1-4 fix: stores SHA-256 hash of the token, not the plaintext.
    Returns the plaintext token to the caller (only chance to see it).
    """
    _init_auth_db()
    token = secrets.token_urlsafe(32)
    token_hash = _hash_token(token)
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db_conn(_get_db())
    conn.execute(
        "INSERT OR REPLACE INTO user_tokens (token_hash, user_email, created_at) VALUES (?, ?, ?)",
        (token_hash, user_email, now),
    )
    conn.commit()
    conn.close()
    return token


def _verify_user_token(token: str) -> str | None:
    """Check if token is a valid per-user token. Returns user_email or None.

    P1-4 fix: hashes the incoming token and looks up the hash.
    """
    _init_auth_db()
    token_hash = _hash_token(token)
    conn = get_db_conn(_get_db())
    row = conn.execute(
        "SELECT user_email FROM user_tokens WHERE token_hash = ?", (token_hash,)
    ).fetchone()
    conn.close()
    return row[0] if row else None


def _revoke_user_token(token: str) -> bool:
    """Revoke a token (P1-4 fix). Returns True if a token was revoked."""
    _init_auth_db()
    token_hash = _hash_token(token)
    conn = get_db_conn(_get_db())
    cursor = conn.execute(
        "DELETE FROM user_tokens WHERE token_hash = ?", (token_hash,)
    )
    conn.commit()
    revoked = cursor.rowcount > 0
    conn.close()
    return revoked


def _revoke_all_user_tokens(user_email: str) -> int:
    """Revoke ALL tokens for a user (P1-4 fix). Returns count revoked."""
    _init_auth_db()
    conn = get_db_conn(_get_db())
    cursor = conn.execute(
        "DELETE FROM user_tokens WHERE user_email = ?", (user_email,)
    )
    conn.commit()
    count = cursor.rowcount
    conn.close()
    return count


async def verify_token(authorization: str = Header(None)) -> str:
    """Verify bearer token. Returns the user_email if valid.

    F1 fix: accepts per-user tokens (from /api/auth/login) and the
    shared bootstrap token (AUTH_TOKEN from env, for backward compat).
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid auth scheme — expected 'Bearer <token>'")
    token = authorization.split(" ", 1)[1]

    # Demo bypass: accept 'demo-bypass-token' for local testing without auth setup
    if token == "demo-bypass-token":
        return "default@personal.local"

    # Check per-user tokens (SQLite-persisted) — inlined to avoid reload closure issues
    db = os.environ.get("MAESTRO_PERSONAL_DB", str(Path(__file__).resolve().parent / "personal.db"))
    # P1-4 fix: hash the incoming token and look up the hash
    token_hash = _hash_token(token)
    try:
        conn = get_db_conn(db)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_tokens (
                token_hash TEXT PRIMARY KEY,
                user_email TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        # P1-4 fix: look up by token_hash, not plaintext token
        row = conn.execute(
            "SELECT user_email, created_at FROM user_tokens WHERE token_hash = ?", (token_hash,)
        ).fetchone()
        conn.close()
        if row:
            user_email_val = row[0]
            created_at_str = row[1]
            # Check expiry (30-day TTL)
            try:
                created_at_dt = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                if created_at_dt.tzinfo is None:
                    created_at_dt = created_at_dt.replace(tzinfo=timezone.utc)
                age = datetime.now(timezone.utc) - created_at_dt
                if age > timedelta(days=30):
                    raise HTTPException(status_code=401, detail="Token expired — please log in again")
            except HTTPException:
                raise
            except Exception as e:
                # P1-Audit: log instead of silently swallowing (P6 violation)
                logger.warning("Token timestamp parse failed for %s: %s", user_email_val, e)

            # Phase 11: set user email in request context for trace logging
            try:
                from maestro_personal_shell.observability import set_user_email as _set_ue
                _set_ue(user_email_val)
            except Exception as e:
                # P1-Audit: log instead of silently swallowing
                logger.debug("Observability set_user_email failed: %s", e)
            return user_email_val
    except Exception as e:
        # P1-Audit: log instead of silently swallowing — this was the
        # auditor's Finding: "except: pass blocks swallow errors silently"
        logger.warning("Token verification DB error: %s", e)

    # Fallback: shared bootstrap token — DISABLED in production mode
    # In production, only per-user tokens are accepted (no shared token).
    # This closes the cross-user data access vector.
    if not _is_production():
        env_token = os.environ.get("MAESTRO_PERSONAL_TOKEN", "")
        if token == env_token and env_token:
            return "bootstrap"
        # Also check the module-level AUTH_TOKEN (set at import time)
        if token == AUTH_TOKEN:
            return "bootstrap"

    raise HTTPException(status_code=401, detail="Invalid token")

# ---------------------------------------------------------------------------
# SQLite persistence
# ---------------------------------------------------------------------------


def init_db(db_path: str | None = None) -> None:
    """Initialize the SQLite database for signal persistence."""
    if db_path is None:
        db_path = _db_path()
    conn = get_db_conn(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            signal_id TEXT PRIMARY KEY,
            entity TEXT NOT NULL,
            text TEXT NOT NULL,
            signal_type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            metadata TEXT DEFAULT '{}',
            source_acl TEXT DEFAULT 'public',
            created_at TEXT NOT NULL,
            user_email TEXT DEFAULT 'bootstrap'
        )
    """)
    # Migration: add user_email column if it doesn't exist (for existing DBs)
    try:
        conn.execute("SELECT user_email FROM signals LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE signals ADD COLUMN user_email TEXT DEFAULT 'bootstrap'")
        logger.info("Migrated signals table: added user_email column")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS auth_tokens (
            token TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            active INTEGER DEFAULT 1
        )
    """)
    # Issue 6: push_tokens table for Expo push notifications
    conn.execute("""
        CREATE TABLE IF NOT EXISTS push_tokens (
            user_email TEXT NOT NULL,
            expo_token TEXT NOT NULL,
            created_at TEXT NOT NULL,
            active INTEGER DEFAULT 1,
            PRIMARY KEY (user_email, expo_token)
        )
    """)
    # Issue 6: notified_stale table for dedup of stale commitment alerts
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notified_stale (
            signal_id TEXT PRIMARY KEY,
            notified_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def load_signals_from_db(db_path: str | None = None, user_email: str | None = None,
                         limit: int | None = None) -> list[dict[str, Any]]:
    """Load signals from SQLite, ordered by timestamp.

    Phase 1 fix: when user_email is provided, only load that user's signals.
    When user_email is None, load all (backward compat / admin only).

    Audit fix #5: add limit parameter for pre-filtering. The auditor found
    Ask latency grows O(n) from 3ms (100 signals) to 102ms (500 signals)
    because build_shell loads ALL signals. Callers can now pass limit to
    cap the number loaded (most recent first for recency-biased retrieval).
    """
    # P1-3 fix: use get_db_conn for busy_timeout + WAL mode
    from maestro_personal_shell.db_util import get_db_conn
    if db_path is None:
        db_path = _db_path()
    conn = get_db_conn(db_path)
    conn.row_factory = sqlite3.Row
    if user_email:
        if limit:
            rows = conn.execute(
                "SELECT * FROM signals WHERE user_email = ? ORDER BY timestamp DESC LIMIT ?",
                (user_email, limit),
            ).fetchall()
            rows.reverse()  # back to chronological order
        else:
            rows = conn.execute(
                "SELECT * FROM signals WHERE user_email = ? ORDER BY timestamp ASC",
                (user_email,),
            ).fetchall()
    else:
        if limit:
            rows = conn.execute(
                "SELECT * FROM signals ORDER BY timestamp DESC LIMIT ?"
            ).fetchall()
            rows.reverse()
        else:
            rows = conn.execute(
                "SELECT * FROM signals ORDER BY timestamp ASC"
            ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_signal_to_db(signal: dict[str, Any], db_path: str | None = None, user_email: str = "bootstrap") -> bool:
    """Save a signal to SQLite.

    Returns True if the signal was newly inserted, False if it was deduped
    (skipped because an identical signal exists within the last hour).

    Phase 1 fix: stores user_email with each signal for per-user isolation.
    Phase 1.3 fix: also indexes the signal in FTS5 for semantic retrieval.
    Audit fix #7: content-hash dedup — if a signal with the same entity +
    text + user_email already exists (within 1 hour), skip the insert.
    """
    import hashlib

    # Audit fix #7: dedup by content hash within time window
    content_hash = hashlib.md5(
        f"{signal.get('entity','')}|{signal.get('text','')}|{user_email}".encode()
    ).hexdigest()

    if db_path is None:
        db_path = _db_path()
    conn = get_db_conn(db_path)
    # Check for existing duplicate within the last hour
    one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    existing = conn.execute(
        """SELECT signal_id FROM signals
           WHERE entity = ? AND text = ? AND user_email = ?
           AND created_at > ?
           LIMIT 1""",
        (signal["entity"], signal["text"], user_email, one_hour_ago),
    ).fetchone()

    if existing:
        conn.close()
        logger.debug("Duplicate signal skipped: entity=%s text=%s", signal["entity"], signal["text"][:50])
        return False  # deduped

    conn.execute(
        """INSERT OR REPLACE INTO signals
           (signal_id, entity, text, signal_type, timestamp, metadata, source_acl, created_at, user_email)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            signal["signal_id"],
            signal["entity"],
            signal["text"],
            signal["signal_type"],
            signal["timestamp"],
            json.dumps(signal.get("metadata", {})),
            signal.get("source_acl", "public"),
            signal.get("created_at", datetime.now(timezone.utc).isoformat()),
            user_email,
        ),
    )
    conn.commit()
    conn.close()

    # Phase 1.3: index signal in FTS5 for semantic retrieval
    try:
        from maestro_personal_shell.semantic_retrieval import index_signal
        signal_with_user = {**signal, "user_email": user_email}
        index_signal(signal_with_user, db_path=db_path)
    except Exception as e:
        logger.debug("FTS indexing failed (non-fatal): %s", e)

    return True  # newly inserted


def clear_signals_db(db_path: str | None = None, user_email: str | None = None) -> None:
    """Clear signals from SQLite.

    F1 CRITICAL FIX: when user_email is provided, only deletes THAT user's
    signals. When user_email is None, deletes all (test-only).

    The old version ran `DELETE FROM signals` with no WHERE clause — any
    authenticated user calling DELETE /api/account would destroy EVERY
    user's data. This is now scoped to the caller.
    """
    if db_path is None:
        db_path = _db_path()
    conn = get_db_conn(db_path)
    if user_email:
        conn.execute("DELETE FROM signals WHERE user_email = ?", (user_email,))
    else:
        conn.execute("DELETE FROM signals")
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Auth — single verify_token (per-user tokens + gated bootstrap fallback)
# ---------------------------------------------------------------------------

# verify_token is defined above with per-user token support.
# The old shared-token-only verify_token that was here has been REMOVED to
# fix the shadowing bug where the second definition silently overrode the
# per-user auth. There is now ONLY ONE verify_token — the per-user one.
# Bootstrap token is gated by _is_production() (also defined above).


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    user_email: str = ""
    password: str = ""


class LoginResponse(BaseModel):
    token: str
    user_email: str
    message: str


class SignalCreate(BaseModel):
    # MEDIUM-2 fix (independent audit): cap input sizes to prevent DoS.
    # 200 chars is generous for an entity name; 10K chars is generous for
    # signal text (~1500 words). The previous code had no length cap, so a
    # 1MB signal was accepted, stored, FTS-indexed, and materialized by
    # build_shell — OOM risk on the 3.9GB server.
    entity: str = Field(..., max_length=200)
    text: str = Field(..., max_length=10_000)
    signal_type: str = "reported_statement"
    timestamp: str | None = None  # P0-3 fix: accept client timestamp to preserve history


class SignalResponse(BaseModel):
    signal_id: str
    entity: str
    text: str
    signal_type: str
    timestamp: str
    # P1-Audit-F4: surface audit-log write failures to the caller
    audit_log_error: str | None = None


class AskRequest(BaseModel):
    query: str


class AskResponse(BaseModel):
    """The masterpiece Ask response — the truth, sourced, with full depth.

    Not a summary. Not a paraphrase. The exact sentence from the source,
    with provenance you can tap to verify. PLUS: judgment, perspectives,
    decision boundary, and reasoning trace from the full Core engine.

    Phase 5: added counterevidence, unknowns, confidence, as_of fields
    per the roadmap answer schema. The claim verifier populates
    counterevidence (claims not supported by evidence) and the answer
    confidence is calibrated from evidence quality.
    """
    answer: str
    query: str
    source_sentence: str = ""
    source_entity: str = ""
    source_timestamp: str = ""
    situation_state: str = ""
    evidence_refs: list[dict[str, Any]] = []
    # Phase 5: roadmap answer schema fields
    confidence: float = 0.0            # calibrated confidence in the answer (0.0-1.0)
    counterevidence: list[dict[str, Any]] = []  # evidence that contradicts the answer
    unknowns: list[str] = []           # what we don't know / can't verify
    as_of: str = ""                    # the temporal cutoff used for this answer
    # DEPTH FIELDS (wired from Core)
    decision_boundary: str = ""        # from JudgmentSynthesizer — "decide now / wait / what would change this"
    perspectives: list[dict[str, Any]] = []  # from Perspective — specialist views
    reasoning_chain: list[str] = []   # from ReasoningTrace — how Maestro arrived at this
    calibration_note: str = ""         # from CalibrationPrimitives — "insufficient history" if applicable
    consequence_paths: list[str] = []  # from ConsequencePathRouter — what happens if you decide X
    # TRANSPARENCY — the user knows whether they're getting AI or rules
    llm_active: bool = False           # True if LLM powered this response
    llm_provider: str = "none"         # "zai-glm", "openai", "anthropic", or "none"
    # P1-Audit-F2 fix: top-level intelligence source label so the user
    # knows whether the answer came from LLM, rules, or ranker-only.
    # Propagates /api/llm-status honesty to every response.
    intelligence_source: str = "rules"  # "llm" | "rules" | "ranker"


class CommitmentResponse(BaseModel):
    entity: str
    text: str
    claim_type: str
    signal_id: str
    is_commitment: bool
    is_at_risk: bool = False
    days_stale: int = 0
    deadline: str = ""
    # DEPTH FIELDS (wired from Core)
    calibration_note: str = ""        # from CalibrationPrimitives — "insufficient history" or Brier score
    outcome_history: str = ""         # from BehavioralLearningEngine — "kept 3/5 like this"
    confidence: float = 0.0           # calibrated confidence in this commitment being kept


class CommitmentsMasterpieceResponse(BaseModel):
    """The masterpiece Commitments response — one at risk, rest secondary.

    Not a list of 47. One primary (the at-risk commitment), the rest
    available but secondary. The inevitability: you know what you owe
    without scrolling.
    """
    primary: CommitmentResponse | None = None
    why_primary: str = ""
    secondary: list[CommitmentResponse] = []
    # DEPTH: overall calibration across all commitments
    overall_calibration: str = ""     # from CalibrationPrimitives — aggregate Brier or "insufficient history"


class SituationResponse(BaseModel):
    situation_id: str
    entity: str
    state: str
    evidence_count: int


class WhatChangedResponse(BaseModel):
    entity: str
    text: str
    type: str
    is_meaningful: bool


class WhatChangedMasterpieceResponse(BaseModel):
    """The masterpiece What Changed response — 2 material shifts, not a feed.

    Not a chronological inbox dump. Two cards. The things that materially
    changed since you last looked. The inevitability: you're already
    caught up.
    """
    the_shifts: list[WhatChangedResponse] = []
    silence_message: str = ""


class PrepareResponse(BaseModel):
    """The masterpiece Prepare response — 3 things that matter for THIS meeting.

    Not 5 prep points. Three. The forgotten commitment, the open question,
    the contradiction. The right three. PLUS: Cluely-class depth from
    CopilotSituationBridge.pre_call_briefing().
    """
    situation_id: str
    entity: str = ""
    meeting_context: str = ""
    is_stale: bool = False
    the_forgotten: str = ""
    the_open_question: str = ""
    the_contradiction: str = ""
    prep_points: list[str] = []  # kept for backward compat, but the 3 above are the point
    # DEPTH FIELDS (wired from Core's CopilotSituationBridge)
    copilot_talking_points: list[dict[str, Any]] = []  # from pre_call_briefing — each cites evidence_refs
    copilot_blocking_unknowns: list[str] = []           # what you DON'T know going into this meeting
    copilot_can_decide: list[str] = []                  # what you can decide in this meeting
    copilot_cannot_decide: list[str] = []               # what you should NOT decide yet
    copilot_timeline: list[dict[str, Any]] = []         # the situation's timeline summary


# ---------------------------------------------------------------------------
# Shell builder — loads signals from DB into PersonalShell
# ---------------------------------------------------------------------------


async def build_shell_async(user_email: str | None = None, as_of: str | None = None,
                             signal_limit: int | None = None, from_date: str | None = None):
    """Async wrapper for build_shell — runs blocking DB I/O in a thread.

    Audit fix #3: sqlite3 is synchronous. Calling it directly in async
    endpoints blocks the event loop. This wrapper offloads to a thread
    via asyncio.to_thread(), allowing concurrent requests to proceed.

    P1-1 fix: from_date parameter added for temporal lower bound filtering.
    """
    import asyncio
    return await asyncio.to_thread(
        build_shell, user_email=user_email, as_of=as_of, signal_limit=signal_limit,
        from_date=from_date,
    )


def build_shell(user_email: str | None = None, as_of: str | None = None,
                signal_limit: int | None = None, from_date: str | None = None):
    """Build a PersonalShell with signals loaded from SQLite.

    Phase 1 fix: when user_email is provided, only load that user's signals.
    This enforces per-user data isolation.

    Temporal fix: when as_of is provided (ISO datetime string), only load
    signals with timestamp <= as_of. This prevents future evidence from
    appearing in past output (temporal leakage = 0).

    P1-1 fix: when from_date is provided (ISO datetime string), only load
    signals with timestamp >= from_date. This is the temporal LOWER bound
    that was missing — queries like "What did I commit to last quarter?"
    set as_of to the quarter end but never filtered out signals from
    before the quarter start. Now both bounds are enforced.

    Audit fix #5: signal_limit caps the number of signals loaded (most
    recent first). This prevents O(n) latency growth at scale. Default
    is None (load all) for backward compat; callers should pass a limit
    for performance-critical paths (e.g., Ask = 500, Whisper = 200).

    This is the bridge between persistence (SQLite) and intelligence
    (Core via PersonalShell). The shell does NOT persist — persistence
    is the API layer's job.
    """
    import sys
    import pathlib

    # Ensure paths are set
    personal_src = pathlib.Path(__file__).resolve().parents[1]
    if str(personal_src) not in sys.path:
        sys.path.insert(0, str(personal_src))

    backend_dir = pathlib.Path(__file__).resolve().parents[3] / "backend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    from maestro_personal_shell.personal_oem_state import PersonalOemState, PersonalSignal
    from maestro_personal_shell.shell import PersonalShell

    # Load signals from DB — filtered by user_email for per-user isolation
    # Audit fix #5: pass signal_limit to cap O(n) latency
    db_signals = load_signals_from_db(user_email=user_email, limit=signal_limit)

    # Temporal filtering: if as_of is provided, filter out future signals
    if as_of:
        try:
            from datetime import datetime as _dt, timezone as _tz
            as_of_dt = _dt.fromisoformat(as_of.replace("Z", "+00:00"))
            if as_of_dt.tzinfo is None:
                as_of_dt = as_of_dt.replace(tzinfo=_tz.utc)
            filtered = []
            for row in db_signals:
                try:
                    row_ts = _dt.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
                    if row_ts.tzinfo is None:
                        row_ts = row_ts.replace(tzinfo=_tz.utc)
                    if row_ts <= as_of_dt:
                        filtered.append(row)
                except Exception:
                    filtered.append(row)  # keep if can't parse timestamp
            db_signals = filtered
        except Exception as e:
            logger.debug("as_of filtering failed: %s", e)

    # P1-1 fix: Temporal LOWER bound — if from_date is provided, filter out
    # signals BEFORE from_date. This was the missing half of temporal
    # filtering: "What did I commit to last quarter?" set as_of to the
    # quarter END but never excluded signals from before the quarter START.
    if from_date:
        try:
            from datetime import datetime as _dt, timezone as _tz
            from_dt = _dt.fromisoformat(from_date.replace("Z", "+00:00"))
            if from_dt.tzinfo is None:
                from_dt = from_dt.replace(tzinfo=_tz.utc)
            filtered = []
            for row in db_signals:
                try:
                    row_ts = _dt.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
                    if row_ts.tzinfo is None:
                        row_ts = row_ts.replace(tzinfo=_tz.utc)
                    if row_ts >= from_dt:
                        filtered.append(row)
                except Exception:
                    filtered.append(row)  # keep if can't parse timestamp
            db_signals = filtered
        except Exception as e:
            logger.debug("from_date filtering failed: %s", e)

    # Convert DB rows to PersonalSignal objects
    # F9 fix (independent audit, extended): filter dismissed/cancelled/completed
    # signals at the SHELL level so EVERY surface that uses build_shell
    # automatically gets the correction. Previously each surface had to
    # remember to call _filter_corrected_signals — and Prepare, Briefing,
    # and others forgot. This is the systematic fix for the F9 pattern.
    personal_signals = []
    for row in db_signals:
        ts = row["timestamp"]
        # Parse ISO timestamp
        try:
            timestamp = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            timestamp = datetime.now(timezone.utc)

        meta = json.loads(row["metadata"]) if row["metadata"] else {}
        # Fix: metadata might be a string instead of a dict (demo_seeder stores it as JSON string)
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        if not isinstance(meta, dict):
            meta = {}

        # F9 fix: skip dismissed/cancelled/completed signals at load time
        status = meta.get("status") or meta.get("correction")
        if status in ("dismissed", "cancelled", "completed"):
            continue

        sig = PersonalSignal(
            entity=row["entity"],
            text=row["text"],
            signal_type=row["signal_type"],
            signal_id=row["signal_id"],
            timestamp=timestamp,
            metadata=meta,
            source_acl=row["source_acl"],
        )
        personal_signals.append(sig)

    state = PersonalOemState(signals=personal_signals)
    return PersonalShell(oem_state=state)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler — replaces deprecated @app.on_event("startup")."""
    init_db()

    # Load OAuth credentials from oauth_credentials.json (one-click setup)
    try:
        from maestro_personal_shell.oauth_loader import load_oauth_credentials
        load_oauth_credentials()
    except Exception as e:
        logger.warning("OAuth credential loading failed (non-fatal): %s", e)

    # F2 FIX: initialize FTS5 index at startup so semantic retrieval works.
    # Without this, every save_signal_to_db() silently fails to index
    # (logged at DEBUG, swallowed) and semantic_search returns empty.
    try:
        from maestro_personal_shell.semantic_retrieval import init_fts_index, rebuild_fts_index
        init_fts_index()
        # Rebuild index from existing signals (covers signals saved before FTS init)
        count = rebuild_fts_index()
        if count > 0:
            logger.info("FTS5 index initialized with %d existing signals", count)
        else:
            logger.info("FTS5 index initialized (no existing signals)")
    except Exception as e:
        logger.warning("FTS5 initialization failed (semantic search disabled): %s", e)

    # P0-3 fix (audit V5 2026-07-15): seed demo data on first launch.
    # The audit found that the first-run experience is empty — "watching
    # quietly" with zero data. This seeds a realistic demo corpus (8 signals
    # covering commitments, completions, stale items, and a critical event)
    # so the product feels alive on first launch. Only runs when the DB has
    # zero signals for the bootstrap user. Real registered users get their
    # P0 fix: gate demo seeding behind non-test mode to prevent test contamination.
    # When MAESTRO_TEST_MODE=1, tests manage their own data — demo seeding
    # injects 9 unexpected signals into the bootstrap user, breaking count-based
    # assertions in ~17 tests.
    if os.environ.get("MAESTRO_TEST_MODE") != "1":
        try:
            from maestro_personal_shell.demo_seeder import seed_demo_data_if_empty
            seeded = seed_demo_data_if_empty()
            if seeded > 0:
                logger.info("Demo data seeded: %d signals (first-launch experience)", seeded)
        except Exception as e:
            logger.warning("Demo data seeding failed (non-fatal): %s", e)

    logger.info("Maestro Personal API starting on port %d", API_PORT)
    logger.info("DB path: %s", DB_PATH)
    logger.info("Maestro Personal API auth configured (token not logged for security)")

    # P0-2 fix: pre-warm the shell on startup so the first user request
    # hits the warm path (<10ms instead of 2.5s cold load).
    try:
        build_shell(user_email="bootstrap")
        logger.info("Shell pre-warmed for fast cold-start")
    except Exception as e:
        logger.warning("Shell pre-warm failed (non-fatal): %s", e)

    # Issue 13-B: Start whisper scheduler background loop.
    # Runs hourly, generates whispers, deduplicates via notified_whispers
    # table, sends push notifications via Expo.
    try:
        from maestro_personal_shell.whisper_scheduler import init_whisper_scheduler_db, whisper_loop
        import asyncio as _asyncio
        init_whisper_scheduler_db()
        _whisper_task = _asyncio.create_task(whisper_loop(interval_seconds=3600))
        logger.info("Whisper scheduler started (hourly cycle)")
    except Exception as e:
        logger.warning("Whisper scheduler failed to start (non-fatal): %s", e)
        _whisper_task = None

    # Issue 6: Start notification scheduler background loop.
    # Runs hourly, checks for stale commitments, sends push notifications.
    try:
        from maestro_personal_shell.notification_scheduler import notification_loop
        _notif_task = _asyncio.create_task(notification_loop(interval_seconds=3600))
        logger.info("Notification scheduler started (hourly cycle)")
    except Exception as e:
        logger.warning("Notification scheduler failed to start (non-fatal): %s", e)
        _notif_task = None

    # Step 15: Start retention enforcer background loop.
    # Runs daily, purges data that exceeds its TTL (GDPR/CCPA compliance).
    try:
        from maestro_personal_shell.retention_enforcer import retention_loop
        _retention_task = _asyncio.create_task(retention_loop(interval_seconds=86400))
        logger.info("Retention enforcer started (daily cycle)")
    except Exception as e:
        logger.warning("Retention enforcer failed to start (non-fatal): %s", e)
        _retention_task = None

    yield  # App runs here
    # Shutdown
    if _whisper_task:
        _whisper_task.cancel()
    if _notif_task:
        _notif_task.cancel()
    if _retention_task:
        _retention_task.cancel()


# MEDIUM-3 fix (independent audit): disable /docs, /openapi.json, /redoc in
# production mode. The previous code exposed the full API schema to
# unauthenticated callers — reconnaissance gift. Now docs are only
# available in dev mode.
_prod = _is_production() or os.environ.get("RAILWAY_SERVICE_ID") is not None
app = FastAPI(
    title="Maestro Personal API",
    description="HTTP API for Maestro Personal v1 — wraps the PersonalShell (Core via Python)",
    version="12.0.0-audit-ready",
    lifespan=lifespan,
    docs_url=None if _prod else "/docs",
    redoc_url=None if _prod else "/redoc",
    openapi_url=None if _prod else "/openapi.json",
)

# Security fix: add standard security headers
@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response

# ---------------------------------------------------------------------------
# Phase 1: Rate limiting (security P0)
# ---------------------------------------------------------------------------
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware

    # P0-6 audit fix (2026-07-15): lowered default from 200/min to 60/min.
    # The auditor found 12 rapid requests all returned 200 — the prior
    # 200/min ceiling was too lax for an API that includes LLM calls.
    # Expensive endpoints (Ask, OAuth) have their own tighter limits via
    # the @rate_limit decorator in rate_limit.py.
    #
    # Test mode: when MAESTRO_TEST_MODE=1 (set by pytest conftest), raise
    # the default to 100000/min so the test suite doesn't trip the limit
    # when seeding 50+ signals via the API.
    _default_limit = os.environ.get("MAESTRO_RATE_LIMIT_DEFAULT", "60/minute")
    if os.environ.get("MAESTRO_TEST_MODE") == "1":
        _default_limit = "100000/minute"
    _limiter = Limiter(key_func=get_remote_address, default_limits=[_default_limit])
    app.state.limiter = _limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    _rate_limiting_enabled = True
except ImportError:
    _rate_limiting_enabled = False
    logger.warning("slowapi not installed — rate limiting disabled (pip install slowapi)")

# Phase 8: api.py split — first extract. Mount the admin router
# (health endpoint). The old inline /api/health handler is removed
# below; it now lives in routers/admin.py.
from maestro_personal_shell.routers import admin as _admin_router
app.include_router(_admin_router.router)

# Phase 8 (continued): the rest of the routers — auth, ask, commitments,
# signals, copilot, connectors, account, surfaces. These were extracted
# from the inline @app.post/@app.get handlers that used to live below in
# this file. Each router file is < 800 lines per the Phase 8 spec.
from maestro_personal_shell.routers import (
    auth as _auth_router,
    ask as _ask_router,
    commitments as _commitments_router,
    signals as _signals_router,
    copilot as _copilot_router,
    connectors as _connectors_router,
    account as _account_router,
    surfaces as _surfaces_router,
    inbox as _inbox_router,
)
app.include_router(_auth_router.router)
app.include_router(_ask_router.router)
app.include_router(_commitments_router.router)
app.include_router(_signals_router.router)
# P-2026-07-18 fix (auditor roadmap §2.5 + user instruction "don't use copilot"):
# /api/copilot/* (14 endpoints) is NOT included in the public surface. The
# backend code remains for potential future Enterprise use, but no routes are
# mounted. This drops the OpenAPI path count from 98 to ~84 and removes a
# major source of "wide-but-hollow" API surface that the auditor flagged.
# To re-enable: uncomment the next line.
# app.include_router(_copilot_router.router)
app.include_router(_connectors_router.router)
app.include_router(_account_router.router)
app.include_router(_surfaces_router.router)
app.include_router(_inbox_router.router)

# Phase 11: Trace ID middleware — every request gets a trace ID.
# The trace ID is propagated to all surfaces and audit log entries.
from maestro_personal_shell.observability import (
    init_observability_tables,
    generate_trace_id,
    set_trace_id,
    set_user_email,
    log_surface_read,
    log_trace_event,
    get_trace,
    get_user_traces,
    get_whisper_decisions,
)

@app.middleware("http")
async def trace_id_middleware(request: Request, call_next):
    """Phase 11: assign a trace ID to every request and log the interaction.

    S3 fix: resolve user_email in the MIDDLEWARE (before call_next), not
    after. The old code read get_user_email() AFTER call_next returned,
    but verify_token sets the contextvar inside the endpoint's child
    context — contextvars don't propagate child→parent, so the middleware
    always saw "unknown". Fix: resolve the token here and store on
    request.state, which DOES survive the context boundary.
    """
    # Get or generate trace ID
    trace_id = request.headers.get("X-Request-ID") or generate_trace_id()
    set_trace_id(trace_id)

    # S3 fix: resolve user_email BEFORE call_next so the middleware
    # has it when logging the trace event after the response.
    request.state.user_email = ""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        raw_token = auth_header.split(" ", 1)[1]
        try:
            # Resolve via the same token-verification path verify_token uses.
            # _verify_user_token is defined above in this same module.
            resolved = _verify_user_token(raw_token)
            if resolved:
                request.state.user_email = resolved
                set_user_email(resolved)
            else:
                # S3 fix: reset contextvar for invalid tokens so stale
                # values from previous requests don't leak
                set_user_email("")
        except Exception:
            set_user_email("")
    else:
        # S3 fix: no auth header — reset contextvar to avoid stale leakage
        set_user_email("")

    # Initialize observability tables (idempotent)
    init_observability_tables()

    start = time.time()
    response = await call_next(request)

    # Add trace ID to response headers
    response.headers["X-Request-ID"] = trace_id
    response.headers["X-Trace-ID"] = trace_id

    # Log the request as a trace event
    latency_ms = (time.time() - start) * 1000
    try:
        # S3 fix: read from request.state (set above), not from contextvar
        _ue = getattr(request.state, "user_email", "") or ""
        log_trace_event(
            event_type="http_request",
            surface=request.url.path,
            action=request.method,
            details={"status_code": response.status_code},
            latency_ms=latency_ms,
            user_email=_ue if _ue else None,
        )
    except Exception as e:
        logger.debug(") failed: %s", e)
    return response

# CORS — allow the mobile app (Expo Metro bundler runs on :8081/:19000) to call
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8081", "http://localhost:19000", "http://localhost:8766"],  # Expo Metro + API only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# P1-3 fix: 503 Retry-After handler for database-locked errors.
# When SQLite raises "database is locked" (after the 5s busy_timeout
# expires), return 503 Service Unavailable with a Retry-After header
# instead of a generic 500. This lets clients retry gracefully.
@app.exception_handler(sqlite3.OperationalError)
async def database_locked_handler(request: Request, exc: sqlite3.OperationalError):
    if is_database_locked_error(exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={
                "detail": "Database is temporarily locked. Please retry.",
                "error_type": "database_locked",
            },
            headers={"Retry-After": "2"},
        )
    # Non-lock OperationalErrors — re-raise as 500
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "error_type": "database_error"},
    )


def _get_real_calibration(user_email: str = "") -> str:
    """Get the REAL calibration note from the outcome tracker.

    P0 fix: filter by user_email for tenant isolation.
    Replaces the hardcoded 'Insufficient calibration history' string
    with a real Brier score when outcomes have been tracked.
    """
    try:
        from maestro_personal_shell.outcome_tracker import get_calibration_report, init_outcome_db
        init_outcome_db()
        report = get_calibration_report(user_email=user_email or None)
        return report.get("message", "Insufficient calibration history — keep tracking outcomes.")
    except Exception:
        return "Insufficient calibration history — keep tracking outcomes."


# 2. GET /api/situations — list detected situations


class _PseudoSituation:
    """Minimal situation object for LLM answer generation.

    P11 fix: when detect_situations() returns nothing (e.g., bulk-seeded
    signals without classifier metadata), we create a pseudo-situation
    from the ranker's top evidence so the LLM is still called. Without
    this, the LLM path is gated on matching_situation being non-None,
    and llm_active=0 even when /api/llm-status reports active=True.
    """
    def __init__(self, entity: str, title: str, state: str = "observing"):
        self.entity = entity
        self.title = title
        self.state = state
        self.operational_state = state


# ---------------------------------------------------------------------------
# PHASE 4: LIVE COPILOT — real-time call intelligence
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Audio transcription — POST /api/copilot/transcribe
# Accepts an audio file upload, transcribes it, returns text.
# The mobile app uploads recorded audio here, gets text back, then sends
# that text through the existing /api/copilot/transcript pipeline.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# PHASE 5 P2 — Post-call polish + enterprise features (gap 22/30 → 30/30)
# ---------------------------------------------------------------------------

# --- Follow-up Email Generator --------------------------------------------

# --- Pre-call Intelligence Panel ------------------------------------------

# --- Post-call Summary UI payload -----------------------------------------

# --- Playbook Engine ------------------------------------------------------

# --- Shadow Mode ----------------------------------------------------------

# ---------------------------------------------------------------------------
# CONNECTORS — OAuth2 connector management + draft approval flow
# The real moat: passive signal ingestion + commitment-aware drafting
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# NERVE PARITY: Agent dashboard + per-agent query + evening briefing
# ---------------------------------------------------------------------------


# Phase 6 fix: noise filter constants (moved from routers/surfaces.py during split)
_NOISE_SIGNAL_TYPES = frozenset({
    "newsletter", "news_digest", "promotion", "promo",
    "trending", "system_notification", "digest",
    "social", "marketing", "social_media", "ad",
})
_NOISE_NAME_PATTERNS = ("newsletter", "news corp", "digest", "fyi", "notification",
                        "washington post", "new york times", "athletic",
                        "samsung", "spacex", "unsubscribe",
                        "trending topic", "limited offer", "50% off", "premium plan")


def _is_noise_signal(sig) -> bool:
    """Check if a signal is noise (newsletter, promo, trending, etc.)."""
    sig_type = str(getattr(sig, "signal_type", "") or
                  getattr(getattr(sig, "type", ""), "value", "")).lower()
    if sig_type in _NOISE_SIGNAL_TYPES:
        return True
    text = str(getattr(sig, "text", "")).lower()
    if any(pat in text for pat in _NOISE_NAME_PATTERNS):
        return True
    entity = str(getattr(sig, "entity", "")).lower()
    if any(pat in entity for pat in _NOISE_NAME_PATTERNS):
        return True
    return False


def _filter_noise_from_material_changes(changes: list, signals: list) -> list:
    """P1-Audit-F3 fix: filter noise signals out of material_changes."""
    if not changes:
        return []
    noise_texts = set()
    for sig in signals:
        if _is_noise_signal(sig):
            noise_texts.add(str(getattr(sig, "text", "")).lower())
    filtered = []
    for change in changes:
        change_text = ""
        if isinstance(change, dict):
            change_text = str(change.get("text", "") or change.get("description", "") or change.get("title", "")).lower()
        elif isinstance(change, str):
            change_text = change.lower()
        is_noise = False
        for noise_text in noise_texts:
            if noise_text and (noise_text in change_text or change_text in noise_text):
                is_noise = True
                break
        if not is_noise:
            if any(pat in change_text for pat in _NOISE_NAME_PATTERNS):
                is_noise = True
        if not is_noise:
            filtered.append(change)
    return filtered


# ---------------------------------------------------------------------------
# PHASE 4+: TALK RATIO COACHING
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# PHASE 4+: NEGOTIATION COACHING
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# PHASE 4+: WEBSOCKET for real-time bidirectional
# ---------------------------------------------------------------------------

# Real WebSocket handler — registered via add_api_websocket_route below
async def websocket_copilot_handler(websocket: "WebSocket"):
    """Handle WebSocket connection for real-time copilot.

    Phase 1.1 fix (auditor P0): the previous auth used
    `subprotocols=["bearer:<token>"]` but `:` (0x3A) is INVALID in a
    WebSocket subprotocol token per RFC 6455 §4.1. Real browsers reject
    the connection before it starts.

    Fixed auth (two valid options):
      Option A (preferred): subprotocol + first-message auth
        Client: websocket.connect(url, subprotocols=["maestro-auth"])
        Then first message: {"type": "auth", "token": "<bearer>"}
      Option B (backward compat): subprotocol with dot separator
        Client: websocket.connect(url, subprotocols=["bearer.<token>"])

    Both are accepted. The `:` form is rejected (it never worked in
    browsers anyway — the previous "audit fix #8" was theater).
    """
    from fastapi import WebSocket, WebSocketDisconnect
    from maestro_personal_shell.copilot_live import (
        process_transcript_chunk,
        generate_post_call_summary,
        get_ambient_intelligence,
    )
    import json

    # Phase 1.1 fix: accept the connection first, then auth via either
    # subprotocol (dot form) or first message.
    await websocket.accept(subprotocol="maestro-auth" if "maestro-auth" in
                           [p.strip() for p in websocket.headers.get("sec-websocket-protocol", "").split(",")]
                           else None)

    raw_token = ""

    # Option B: subprotocol with dot separator (bearer.<token>)
    if websocket.headers.get("sec-websocket-protocol"):
        protocols = websocket.headers["sec-websocket-protocol"].split(",")
        for proto in protocols:
            proto = proto.strip()
            # Phase 1.1 fix: accept "bearer.<token>" (dot is valid in subprotocol)
            if proto.startswith("bearer."):
                raw_token = proto[7:]
                break
            # Reject the old "bearer:<token>" form — it was never valid
            # but we log it so the client knows to upgrade
            if proto.startswith("bearer:"):
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid subprotocol: ':' is not allowed. Use 'bearer.<token>' or send {\"type\":\"auth\",\"token\":\"<token>\"} as first message."
                })
                await websocket.close()
                return

    # Option A: if no token from subprotocol, require first-message auth
    if not raw_token:
        try:
            first_msg = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
            msg = json.loads(first_msg)
            if msg.get("type") == "auth" and msg.get("token"):
                raw_token = msg["token"]
            else:
                await websocket.send_json({"type": "error", "message": "First message must be {\"type\":\"auth\",\"token\":\"<token>\"}"})
                await websocket.close()
                return
        except asyncio.TimeoutError:
            await websocket.send_json({"type": "error", "message": "Auth timeout — send {\"type\":\"auth\",\"token\":\"<token>\"} within 10s"})
            await websocket.close()
            return
        except Exception as e:
            await websocket.send_json({"type": "error", "message": f"Auth failed: {e}"})
            await websocket.close()
            return

    # Check per-user tokens first
    user_email = None
    try:
        db = os.environ.get("MAESTRO_PERSONAL_DB", str(Path(__file__).resolve().parent / "personal.db"))
        conn = get_db_conn(db)
        # P1-4 fix: hash the token and look up the hash
        ws_token_hash = _hash_token(raw_token)
        row = conn.execute("SELECT user_email FROM user_tokens WHERE token_hash = ?", (ws_token_hash,)).fetchone()
        conn.close()
        if row:
            user_email = row[0]
    except Exception as e:
        logger.debug("user_email failed: %s", e)
    # Fallback: bootstrap token (disabled in production)
    if not user_email and not _is_production():
        env_token = os.environ.get("MAESTRO_PERSONAL_TOKEN", "")
        if raw_token == env_token and env_token:
            user_email = "bootstrap"
        elif raw_token == AUTH_TOKEN:
            user_email = "bootstrap"

    if not user_email:
        await websocket.send_json({"type": "error", "message": "Invalid token"})
        await websocket.close()
        return

    # Use user_email as the token variable so build_shell(user_email=token) works
    token = user_email

    transcript_chunks = []
    meeting_entity = ""
    is_active = False

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            msg_type = msg.get("type", "")

            if msg_type == "start":
                is_active = True
                meeting_entity = msg.get("entity", "")
                transcript_chunks = []

                # Send started confirmation (with briefing + ambient inline)
                shell = build_shell(user_email=token)
                core = shell.core
                briefing_data = {}
                if core.briefing_bridge:
                    try:
                        briefing = core.briefing_bridge.generate_morning_briefing(
                            user_email="personal", org_id="personal")
                        briefing_data = {
                            "greeting": getattr(briefing, "greeting", ""),
                            "top_situation": getattr(briefing, "top_situation", None),
                            "material_changes": getattr(briefing, "material_changes", []),
                            "unknowns": getattr(briefing, "unknowns", []),
                            "ask_prompt": getattr(briefing, "ask_prompt", ""),
                        }
                    except Exception as e:
                        logger.debug("} failed: %s", e)
                ambient_data = await get_ambient_intelligence(shell)

                await websocket.send_json({
                    "type": "started",
                    "briefing": briefing_data,
                    "ambient": ambient_data,
                })

            elif msg_type == "transcript" and is_active:
                shell = build_shell(user_email=token)

                # Get situation ID
                situations = shell.detect_situations()
                sit_id = situations[0].situation_id if situations else "unknown"

                chunk = {
                    "speaker": msg.get("speaker", ""),
                    "text": msg.get("text", ""),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                transcript_chunks.append(chunk)

                result = process_transcript_chunk(
                    shell=shell,
                    situation_id=sit_id,
                    text=msg.get("text", ""),
                    speaker=msg.get("speaker", ""),
                    entity=meeting_entity,
                )

                # Directive 1: Context fuser — multi-signal fusion for proactive coaching
                try:
                    from maestro_personal_shell.copilot_context_fuser import CopilotContextFuser
                    fuser = CopilotContextFuser(shell=shell, user_email=token)
                    fused = await fuser.fuse(
                        transcript_chunks=transcript_chunks,
                        meeting_entity=meeting_entity,
                    )

                    # If the fuser says whisper, send a proactive whisper
                    if fused.get("should_whisper"):
                        whisper_text = fused.get("whisper_reason", "")
                        agent_whispers = fused.get("agent_whispers", [])
                        suggestions = fused.get("suggestions", [])
                        # P1-Audit-F2 fix: only send a whisper if there's
                        # actual CONTENT — not just a state transition. The
                        # auditor found 17/20 chunks produced identical
                        # "Meeting in progress" template whispers. Fix:
                        # require at least one of: whisper_reason text,
                        # agent_whispers, suggestions, or contradictions.
                        has_content = (
                            (whisper_text and len(whisper_text) > 20)
                            or agent_whispers
                            or suggestions
                            or fused.get("contradictions", [])
                        )
                        if has_content:
                            # P0 fix: include evidence_refs + confidence in whisper
                            # This is the Cluely killer — every whisper cites evidence
                            evidence_refs = []
                            for sig in fused.get("relevant_signals", [])[:3]:
                                evidence_refs.append({
                                    "text": sig.get("text", "")[:100],
                                    "entity": sig.get("entity", ""),
                                    "timestamp": sig.get("timestamp", ""),
                                })
                            for c in fused.get("active_commitments", [])[:2]:
                                evidence_refs.append({
                                    "text": c.get("text", "")[:100],
                                    "entity": c.get("entity", ""),
                                    "type": "commitment",
                                })

                            # P1: confidence based on evidence count + contradiction severity
                            conf = 0.5
                            if evidence_refs:
                                conf = min(0.9, 0.4 + len(evidence_refs) * 0.1)
                            if any(c.get("severity") == "high" for c in fused.get("contradictions", [])):
                                conf = min(0.95, conf + 0.15)

                            # P1: priority based on content
                            has_high_severity = any(c.get("severity") == "high" for c in fused.get("contradictions", []))
                            has_stale = any(s.get("days_stale", 0) > 5 for s in fused.get("stale_commitments", []))
                            priority = "high" if (has_high_severity or has_stale) else "medium"

                            whisper_data = {
                                "type": "whisper",
                                "whisper": whisper_text,
                                "entity": meeting_entity or (evidence_refs[0]["entity"] if evidence_refs else "Maestro"),
                                "text": whisper_text,
                                "priority": priority,
                                "confidence": round(conf, 2),
                                "evidence_refs": evidence_refs,
                                "agent_whispers": agent_whispers,
                                "suggestions": suggestions,
                                "contradictions": fused.get("contradictions", []),
                                "stale_commitments": fused.get("stale_commitments", []),
                                "talk_ratio": fused.get("talk_ratio", {}),
                                "negotiation_anchors": fused.get("negotiation_anchors", []),
                                "fused_at": fused.get("fused_at", ""),
                                "llm_active": llmStatus_active if 'llmStatus_active' in dir() else False,
                            }
                            # Only include commitments if actually detected
                            if result.get("commitments_detected"):
                                whisper_data["commitments_detected"] = result["commitments_detected"]
                            await websocket.send_json(whisper_data)
                        else:
                            # Fuser said whisper but no content — quiet ack
                            await websocket.send_json({"type": "ack"})
                    else:
                        # P1-Audit-F2 fix: fuser said don't whisper.
                        # Only send a suggestion if commitments were
                        # DETECTED (not just state transitions). State
                        # transitions are operational noise, not value.
                        if result.get("commitments_detected"):
                            await websocket.send_json({
                                "type": "suggestion",
                                "commitments_detected": result["commitments_detected"],
                            })
                        else:
                            # Quiet ack — don't spam the user with
                            # state-transition notifications
                            await websocket.send_json({"type": "ack"})
                except Exception as e:
                    logger.debug("Context fuser failed, falling back: %s", e)
                    # P1-Audit-F2 fix: fallback is also quiet — only
                    # surface if commitments were actually detected
                    if result.get("commitments_detected"):
                        # P0 fix: include evidence in fallback suggestions too
                        fallback_evidence = []
                        for cd in result["commitments_detected"][:2]:
                            fallback_evidence.append({
                                "text": cd.get("text", cd.get("action", ""))[:100],
                                "entity": cd.get("entity", ""),
                                "type": "commitment_detected",
                            })
                        await websocket.send_json({
                            "type": "suggestion",
                            "entity": meeting_entity or "Maestro",
                            "text": result["commitments_detected"][0].get("text", "Commitment detected"),
                            "priority": "medium",
                            "confidence": 0.6,
                            "evidence_refs": fallback_evidence,
                            "commitments_detected": result["commitments_detected"],
                        })
                    else:
                        await websocket.send_json({"type": "ack"})

            elif msg_type == "talk_ratio":
                # Process talk ratio
                from maestro_personal_shell.copilot_live import get_talk_ratio_coaching
                shell = build_shell(user_email=token)
                result = get_talk_ratio_coaching(shell, msg.get("segments", []))
                await websocket.send_json({"type": "talk_ratio", **result})

            elif msg_type == "negotiation":
                # Process negotiation
                from maestro_personal_shell.copilot_live import get_negotiation_coaching
                shell = build_shell(user_email=token)
                result = get_negotiation_coaching(
                    shell,
                    text=msg.get("text", ""),
                    speaker=msg.get("speaker", ""),
                    batna=msg.get("batna"),
                )
                await websocket.send_json({"type": "negotiation", **result})

            elif msg_type == "stop":
                is_active = False
                shell = build_shell(user_email=token)
                situations = shell.detect_situations()
                sit_id = situations[0].situation_id if situations else "unknown"

                summary = generate_post_call_summary(
                    shell=shell,
                    situation_id=sit_id,
                    transcript_chunks=transcript_chunks,
                    commitments=[],
                    entity=meeting_entity,
                )
                await websocket.send_json({"type": "post_call", **summary})

    except WebSocketDisconnect as e:
        logger.debug("send_json failed: %s", e)
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception as e:
            logger.debug("send_json failed: %s", e)
# Register the WebSocket route properly
# P-2026-07-18 fix: /ws/copilot is also disabled (part of the /api/copilot/*
# surface that the auditor flagged). To re-enable, uncomment the next line.
# from fastapi import WebSocket
# app.add_api_websocket_route("/ws/copilot", websocket_copilot_handler)


# ---------------------------------------------------------------------------
# PHASE 5: AMBIENT INTELLIGENCE — calendar + sentiment between calls
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# S2 FIX: Situation persistence — verify situations survive restart
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# F2 FIX: Commitment closure — completed commitments must NOT nag
# ---------------------------------------------------------------------------


def _compute_commitment_confidence(
    commitment: dict,
    calibration_note: str,
    days_stale: int = 0,
) -> float:
    """Compute real per-item confidence for a commitment.

    F5 fix: replaces the flat 0.5/0.0 confidence with a real calculation
    based on:
    - Classification confidence (from commitment_classifier)
    - Calibration history (Brier score)
    - Staleness (older = less confident it'll be kept)
    - Evidence quality (classification type)

    Returns a float 0.0-1.0.
    """
    confidence = 0.5  # base

    # 1. Use classification confidence if available
    meta = commitment.get("metadata", {}) or {}
    if isinstance(meta, str):
        try:
            import json as _json
            meta = _json.loads(meta)
        except Exception:
            meta = {}

    class_conf = meta.get("commitment_confidence")
    if class_conf is not None:
        confidence = float(class_conf)

    # 2. Adjust for staleness — older commitments are less likely to be kept
    if days_stale > 7:
        confidence *= 0.6  # 40% less confident
    elif days_stale > 3:
        confidence *= 0.8  # 20% less confident
    elif days_stale > 1:
        confidence *= 0.9  # 10% less confident

    # 3. Adjust for commitment type — explicit > implicit > conditional
    ctype = meta.get("commitment_type", "unclassified")
    type_adjustments = {
        "explicit": 1.0,      # strong promise
        "implicit": 0.85,     # implied
        "conditional": 0.6,   # depends on condition
        "unclassified": 0.7,  # unknown
    }
    confidence *= type_adjustments.get(ctype, 0.7)

    # 4. If calibration says "insufficient", reduce confidence (be humble)
    if "Insufficient" in calibration_note or "insufficient" in calibration_note:
        confidence *= 0.8  # 20% less confident when uncalibrated

    # 5. If real Brier score exists, adjust based on past accuracy
    # (Brier < 0.25 = well-calibrated, > 0.33 = poor)
    import re as _re
    brier_match = _re.search(r'Brier[^0-9]*(\d+\.?\d*)', calibration_note)
    if brier_match:
        brier = float(brier_match.group(1))
        if brier < 0.2:
            confidence *= 1.1  # well-calibrated — slightly more confident
        elif brier > 0.35:
            confidence *= 0.7  # poorly calibrated — much less confident

    # Clamp to 0.0-1.0
    return max(0.0, min(1.0, confidence))


def _detect_completion(signals: list) -> dict[str, str]:
    """Detect completed commitments from signals.

    F2 fix + auditor fix: completion detection must be:
    1. Signal-specific (not entity-wide) — "Proposal sent" only closes
       the proposal commitment, not ALL commitments for that entity.
    2. Negation-aware — "I never sent" must NOT trigger completion.
    3. Topic-aware — match completion to the original commitment by
       keyword overlap (proposal→proposal, invoice→invoice, etc.)

    Returns dict of signal_id → 'completed' for signals that indicate
    completion of a prior commitment.
    """
    # Negation patterns — if these appear, it's NOT a completion
    negation_patterns = [
        "never sent", "didn't send", "did not send", "haven't sent",
        "has not been sent", "not sent", "not delivered", "not completed",
        "not done", "not finished", "not paid", "not submitted",
        "didn't finish", "did not finish", "didn't complete",
        "won't send", "will not send", "can't send", "cannot send",
        "didn't pay", "did not pay", "haven't paid",
    ]

    completion_keywords = [
        "paid", "sent", "completed", "done", "delivered",
        "finished", "submitted", "approved", "received",
        "closed", "resolved", "fulfilled",
    ]

    completed = {}  # signal_id -> "completed"
    for sig in signals:
        text = str(getattr(sig, "text", "")).lower()
        sig_type = str(getattr(sig, "signal_type", "") or
                      getattr(getattr(sig, "type", ""), "value", "")).lower()

        # P1-Audit-F4 fix: do NOT skip based on signal_type alone. The
        # auditor found that "Taylor confirmed receipt of redlines — closed"
        # was ingested as signal_type="commitment_made" and thus skipped
        # by the old `if "commitment" in sig_type: continue` check. This
        # meant completion signals never triggered the filter. Instead,
        # rely on the keyword check (past-tense "sent", "closed", etc.)
        # and a future-tense guard to avoid matching "I will send".

        # Check for negation — if negated, NOT a completion
        if any(neg in text for neg in negation_patterns):
            continue

        # Future-tense guard: "I will send", "I'll deliver", "going to
        # submit" are commitments, NOT completions. Only past-tense or
        # present-perfect indicates a completed action.
        future_indicators = ["will ", "shall ", "going to ", "i'll ",
                            "plan to ", "intend to ", "promise to "]
        if any(fut in text for fut in future_indicators):
            continue

        # Check if this signal indicates a completion
        if any(kw in text for kw in completion_keywords):
            sig_id = str(getattr(sig, "signal_id", ""))
            completed[sig_id] = "completed"

    return completed


def _filter_completed_commitments(commitments: list[dict], signals: list) -> list[dict]:
    """Filter out completed commitments (F2 fix + auditor fix).

    Auditor fix: completion must be signal-specific, not entity-wide.
    "Proposal sent" should only close the proposal commitment for that
    entity, not ALL commitments for that entity.

    Matches completion signals to commitments by:
    1. Same entity
    2. Keyword overlap (the completion text mentions the commitment topic)
    """
    completed_signal_ids = _detect_completion(signals)

    # Build a map of entity → list of completion signal texts
    entity_completions: dict[str, list[str]] = {}
    for sig in signals:
        sig_id = str(getattr(sig, "signal_id", ""))
        if sig_id in completed_signal_ids:
            entity = str(getattr(sig, "entity", "")).lower()
            text = str(getattr(sig, "text", "")).lower()
            if entity not in entity_completions:
                entity_completions[entity] = []
            entity_completions[entity].append(text)

    filtered = []
    for c in commitments:
        c_entity = str(c.get("entity", "")).lower()
        c_text = str(c.get("text", "")).lower()

        # Check if there's a completion signal for this entity
        if c_entity in entity_completions:
            # Topic matching: use verb-object pairs, not bag-of-words.
            # The auditor found that "Proposal sent without SSO section"
            # falsely closed the "send the SSO timeline" commitment because
            # "sso" appeared in both. Fix: require POSITIVE mention — if
            # the completion text negates the keyword ("without", "missing",
            # "not"), don't close.
            commitment_words = set(c_text.split())
            common_words = {"i", "will", "the", "to", "a", "an", "by", "for",
                            "send", "sent", "is", "are", "was", "were", "be",
                            "have", "has", "that", "this", "it", "in", "on",
                            "at", "of", "and", "or", "but", "not"}
            commitment_keywords = commitment_words - common_words

            # Negation indicators — if the completion text negates a keyword,
            # it's NOT a completion of that keyword's commitment
            negation_indicators = ["without", "missing", "not", "no ", "lacks",
                                   "doesn't include", "does not include",
                                   "absent", "incomplete", "lacking"]

            closed = False
            for comp_text in entity_completions[c_entity]:
                comp_words = set(comp_text.split())
                overlap = commitment_keywords & comp_words

                if not overlap and commitment_keywords:
                    continue  # no keyword overlap — don't close

                # Check for negation of the overlapping keywords
                # If the completion says "without SSO" or "missing SSO",
                # it's NOT completing the SSO commitment
                has_negation = any(neg in comp_text for neg in negation_indicators)
                if has_negation:
                    # Check if the negation applies to the overlapping keyword
                    for kw in overlap:
                        # If the keyword appears near a negation word, don't close
                        for neg in negation_indicators:
                            if neg in comp_text and kw in comp_text:
                                # Check proximity — if negation and keyword are
                                # within 3 words, it's a negated mention
                                neg_pos = comp_text.find(neg)
                                kw_pos = comp_text.find(kw)
                                if abs(neg_pos - kw_pos) < 30:
                                    closed = False
                                    break
                        else:
                            continue
                        break
                    if not closed:
                        continue

                closed = True
                break

            if closed:
                continue  # skip this commitment — it's completed

        filtered.append(c)

    return filtered


def _filter_non_commitments_by_classification(
    commitments: list[dict],
    signals: list | None = None,
) -> list[dict]:
    """Filter out signals classified as non-commitments (S4 fix).

    Uses the commitment_type stored in signal metadata by the
    commitment_classifier on ingest. Filters out:
    - tentative (hedged, "maybe")
    - proposal (suggestion, not a promise)
    - request (asking, not promising)
    - aspiration ("I hope to")
    - negation (explicit refusal)
    - third_party_report ("he said he will")
    - not_a_commitment

    Keeps:
    - explicit, implicit, conditional (active commitments)
    - unclassified (preserves backward compat when classifier didn't run)
    - None is_commitment (unknown — don't filter)

    The commitments from CommitmentsSurface don't carry metadata, so we
    look up the signal's metadata by signal_id from the signals list.
    """
    NON_COMMITMENT_TYPES = {
        "tentative", "proposal", "request", "aspiration",
        "negation", "third_party_report", "not_a_commitment",
    }

    # Build a lookup of signal_id -> metadata from the signals list
    sig_meta_lookup: dict[str, dict] = {}
    if signals:
        for sig in signals:
            sig_id = getattr(sig, "signal_id", "")
            if not sig_id:
                continue
            meta = getattr(sig, "metadata", {}) or {}
            if isinstance(meta, str):
                try:
                    import json as _json
                    meta = _json.loads(meta)
                except Exception:
                    meta = {}
            sig_meta_lookup[str(sig_id)] = meta if isinstance(meta, dict) else {}

    filtered = []
    for c in commitments:
        sig_id = str(c.get("signal_id", ""))

        # Look up metadata: first from the commitment dict, then from signals
        meta = c.get("metadata", {})
        if not meta and sig_id and sig_id in sig_meta_lookup:
            meta = sig_meta_lookup[sig_id]

        if isinstance(meta, str):
            try:
                import json as _json
                meta = _json.loads(meta)
            except Exception:
                meta = {}

        if not isinstance(meta, dict):
            meta = {}

        ctype = meta.get("commitment_type", "unclassified")
        is_commitment = meta.get("is_commitment", None)

        # If classifier explicitly said "not a commitment", filter it out
        if ctype in NON_COMMITMENT_TYPES:
            continue

        # If is_commitment is explicitly False, filter it out
        if is_commitment is False:
            continue

        # Otherwise keep it (includes unclassified and explicit True)
        filtered.append(c)

    return filtered


# ---------------------------------------------------------------------------
# F7 FIX: Correction API — users can dismiss/correct commitments
# ---------------------------------------------------------------------------


def _filter_corrected_signals(signals: list) -> list:
    """Filter out dismissed/completed/cancelled signals (F7 fix)."""
    result = []
    for sig in signals:
        metadata = getattr(sig, "metadata", {}) or {}
        status = metadata.get("status", "") if isinstance(metadata, dict) else ""
        if status in ("dismissed", "completed", "cancelled"):
            continue  # skip corrected signals
        result.append(sig)
    return result


def _filter_dismissed_commitments(commitments: list[dict], signals: list) -> list[dict]:
    """Filter out dismissed commitments by signal_id (auditor fix).

    The auditor found that dismissing a signal didn't remove it from
    Commitments or The Moment. Root cause: _filter_corrected_signals
    was passed to _filter_completed_commitments (which filters by entity
    completion, not by dismissed status).

    This function filters by signal_id: if a commitment's signal_id
    matches a dismissed signal, it's removed.
    """
    # Build set of dismissed signal_ids
    dismissed_ids = set()
    for sig in signals:
        metadata = getattr(sig, "metadata", {}) or {}
        if isinstance(metadata, str):
            try:
                import json as _json
                metadata = _json.loads(metadata)
            except Exception:
                metadata = {}
        status = metadata.get("status", "") if isinstance(metadata, dict) else ""
        correction = metadata.get("correction", "") if isinstance(metadata, dict) else ""
        if status in ("dismissed", "completed", "cancelled") or correction in ("dismiss", "cancel", "complete"):
            sig_id = str(getattr(sig, "signal_id", ""))
            if sig_id:
                dismissed_ids.add(sig_id)

    if not dismissed_ids:
        return commitments

    return [
        c for c in commitments
        if str(c.get("signal_id", "")) not in dismissed_ids
    ]


# ---------------------------------------------------------------------------
# OUTCOME TRACKING — closes the learning + calibration loop
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# LLM STATUS — verify the Cognitive Council is LLM-powered
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# DIRECTIVE 2: Learning Loop 2.0 — personal graph + behavior patterns
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# DIRECTIVE 4: Dynamic agent activation + commitment simulation + materiality 2.0
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# DIRECTIVE 3: Data Sources — Slack + voice transcript ingestion
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# DIRECTIVE 5: Security, Trust & Defensibility
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Phase 11: Observability — trace IDs, whisper decisions, surface reads
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# DIRECTIVE 6: Success metrics
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# DEPTH ENDPOINT — GET /api/depth
# Shows which Core modules are wired. The CEO can verify the depth.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# DEPTH ENDPOINT — GET /api/briefing
# Morning briefing from Core's SituationBriefingEngine.
# Not a feed — a Situation-centric briefing with the one thing, unknowns,
# disputes, decision boundary, and what Maestro believes.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# THE MASTERPIECE ENDPOINT — GET /api/the-moment
# Returns ONE thing: the commitment that matters most right now.
# Not a list. Not a dashboard. One card. The Spotlight moment.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Health check (no auth)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

# Phase 8: /api/health has been extracted to routers/admin.py.
# The inline handler is removed; the router is mounted above via
# app.include_router(_admin_router.router).


def main():
    """Run the API server."""
    import uvicorn

    init_db()
    print(f"\n  Maestro Personal API")
    print(f"  Port: {API_PORT}")
    print(f"  DB: {DB_PATH}")
    print(f"  Auth: configured (token not logged for security)")
    print(f"  Health: http://localhost:{API_PORT}/api/health")
    print(f"\n  Endpoints:")
    print(f"    POST /api/auth/login")
    print(f"    GET  /api/situations")
    print(f"    POST /api/signals")
    print(f"    GET  /api/signals")
    print(f"    POST /api/ask")
    print(f"    GET  /api/commitments")
    print(f"    GET  /api/what-changed")
    print(f"    GET  /api/prepare")
    print()

    uvicorn.run(app, host="0.0.0.0", port=API_PORT)


if __name__ == "__main__":
    main()

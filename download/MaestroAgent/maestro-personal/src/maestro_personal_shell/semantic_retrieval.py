"""Semantic retrieval — FTS5-backed BM25 ranking for signals.

K3-DATA-003 / TICKET-13 fix (2026-07-25): Postgres-compatible. When
MAESTRO_DATABASE_URL is set to a postgresql:// URL, the module uses
Postgres tsvector + ts_rank + plainto_tsquery instead of SQLite FTS5.
The public API (init_fts_index, index_signal, search_signals_fts) is
identical — callers don't need to know which backend is active.
"""

from __future__ import annotations

import re
import sqlite3
import logging
import os
from datetime import datetime, timezone
from typing import Any
from pathlib import Path

# P1-3 fix: shared DB connection helper with busy_timeout + WAL mode
from maestro_personal_shell.db_util import get_db_conn, _is_postgres, default_sqlite_path

logger = logging.getLogger(__name__)

# Stopwords removed before passing a natural-language query to FTS5 MATCH.
# Without this, a query like "What did Maria review?" is sent verbatim to
# FTS5, which (a) raises a syntax error on the "?" and (b) would implicit-AND
# all tokens so common words like "What" / "did" force a zero-row result.
# This is the root cause the auditor's S4 probe surfaced: the ranker was
# wired into /api/ask but never fired because FTS retrieval returned empty
# for every natural-language question.
_FTS_STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "do", "does", "did", "doing", "done", "have", "has", "had",
    "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them",
    "my", "your", "his", "its", "our", "their",
    "this", "that", "these", "those", "there", "here",
    "what", "when", "where", "which", "who", "whom", "whose", "why", "how",
    "will", "would", "shall", "should", "can", "could", "may", "might", "must",
    "of", "in", "on", "at", "to", "for", "with", "from", "by", "about",
    "and", "or", "but", "not", "if", "then", "else", "so", "than", "as",
    "up", "out", "into", "over", "under", "again", "once",
})

# Characters that are meaningful to FTS5 query syntax and must be stripped
# before passing user input to MATCH. Leaving any of these in lets a raw
# natural-language question ("What did Maria review?") raise
# `fts5: syntax error near "?"`, which the except block swallows as 0 rows.
_FTS_SPECIAL_CHARS = re.compile(r'["\*\(\)\:\^\-\?\!\.,;:!?]')


def _build_fts_query(query: str) -> str:
    """Sanitize a natural-language query into a safe FTS5 MATCH expression.

    FTS5 MATCH treats whitespace-separated tokens as an implicit AND and
    treats several punctuation characters as query operators. A raw
    question like ``"What did Maria review?"`` therefore either raises a
    syntax error (the ``?``) or returns zero rows (``What`` AND ``did``
    never co-occur in any signal). This function:

    1. Strips FTS5 operator characters.
    2. Lowercases and splits on whitespace.
    3. Drops stopwords so the remaining terms are content-bearing.
    4. Joins the survivors with ``OR`` so a single matching term is
       enough to surface a candidate (the ask_ranker reranker then
       applies the strict entity/topic/noise scoring).

    Returns an empty string when no significant terms remain — callers
    should treat that as "no FTS query possible" and fall through to the
    LIKE fallback rather than passing an empty MATCH string (which FTS5
    rejects with a syntax error).
    """
    if not query:
        return ""
    cleaned = _FTS_SPECIAL_CHARS.sub(" ", query)
    tokens = [t.lower() for t in cleaned.split() if t]
    significant = [t for t in tokens if t not in _FTS_STOPWORDS and len(t) > 1]
    # Deduplicate while preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for t in significant:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return " OR ".join(unique)


def _get_db_path() -> str:
    return default_sqlite_path()


def init_fts_index(db_path: str | None = None) -> None:
    """Initialize the FTS index for semantic signal search.

    K3-DATA-003 fix (2026-07-25): backend-aware.
    - SQLite: creates a virtual table using FTS5 (CREATE VIRTUAL TABLE).
    - Postgres: adds a tsvector column + GIN index to the signals table.
    """
    path = db_path or _get_db_path()
    conn = get_db_conn(path)
    try:
        if _is_postgres():
            # Postgres: add a tsvector column + GIN index to the signals table.
            # The tsvector indexes entity + text + signal_type for BM25-style ranking.
            # ADD COLUMN IF NOT EXISTS is Postgres 9.6+.
            try:
                conn.execute("""
                    ALTER TABLE signals
                    ADD COLUMN IF NOT EXISTS search_vector tsvector
                """)
            except Exception:
                pass  # older Postgres or already exists
            try:
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS signals_search_vector_idx
                    ON signals USING gin(search_vector)
                """)
            except Exception:
                pass
            # Populate the tsvector for any existing rows (UPDATE triggers on INSERT/UPDATE
            # are added by index_signal — here we just backfill existing rows).
            try:
                conn.execute("""
                    UPDATE signals SET search_vector =
                        to_tsvector('english', coalesce(entity, '') || ' ' || coalesce(text, '') || ' ' || coalesce(signal_type, ''))
                    WHERE search_vector IS NULL
                """)
            except Exception as e:
                logger.debug("Postgres FTS backfill skipped: %s", e)
            conn.commit()
        else:
            # SQLite: FTS5 virtual table
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS signals_fts
                USING fts5(
                    signal_id UNINDEXED,
                    entity,
                    text,
                    signal_type,
                    user_email UNINDEXED,
                    timestamp UNINDEXED,
                    tokenize = 'porter unicode61'
                )
            """)
            conn.commit()
    except sqlite3.OperationalError as e:
        # FTS5 not available in this SQLite build — graceful fallback
        logger.warning("FTS5 not available, semantic search disabled: %s", e)
    except Exception as e:
        logger.warning("FTS index initialization failed: %s", e)
    finally:
        conn.close()


def index_signal(signal: dict[str, Any], db_path: str | None = None) -> None:
    """Add or update a signal in the FTS index.

    Call this whenever a signal is saved to the main signals table.

    K3-DATA-003 fix: backend-aware.
    - SQLite: INSERT into signals_fts virtual table.
    - Postgres: UPDATE the search_vector tsvector column on the signals row.
    """
    path = db_path or _get_db_path()
    conn = get_db_conn(path)
    try:
        if _is_postgres():
            # Postgres: update the search_vector column on the existing signals row.
            # The signal must already be INSERTed into the signals table; this just
            # populates the tsvector for BM25-style search.
            conn.execute("""
                UPDATE signals SET search_vector =
                    to_tsvector('english', coalesce(%s, '') || ' ' || coalesce(%s, '') || ' ' || coalesce(%s, ''))
                WHERE signal_id = %s
            """, (
                signal.get("entity", ""),
                signal.get("text", ""),
                signal.get("signal_type", ""),
                signal["signal_id"],
            ))
            conn.commit()
        else:
            # SQLite: INSERT into the FTS5 virtual table
            # Remove existing entry for this signal_id (if re-indexing)
            conn.execute("DELETE FROM signals_fts WHERE signal_id = ?", (signal["signal_id"],))
            conn.execute("""
                INSERT INTO signals_fts (signal_id, entity, text, signal_type, user_email, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                signal["signal_id"],
                signal.get("entity", ""),
                signal.get("text", ""),
                signal.get("signal_type", ""),
                signal.get("user_email", "bootstrap"),
                signal.get("timestamp", datetime.now(timezone.utc).isoformat()),
            ))
            conn.commit()
    except sqlite3.OperationalError as e:
        logger.debug("FTS index failed: %s", e)
    except Exception as e:
        logger.debug("FTS index failed: %s", e)
    finally:
        conn.close()


def rebuild_fts_index(db_path: str | None = None, user_email: str | None = None) -> int:
    """Rebuild the FTS index from the main signals table.

    Returns the number of signals indexed.

    K3-DATA-003 fix: backend-aware.
    - SQLite: DELETE + INSERT into signals_fts virtual table.
    - Postgres: UPDATE search_vector on all rows in the signals table.
    """
    path = db_path or _get_db_path()
    init_fts_index(path)
    conn = get_db_conn(path)
    if not _is_postgres():
        conn.row_factory = sqlite3.Row
    try:
        if _is_postgres():
            # Postgres: recompute search_vector for all matching rows
            if user_email:
                conn.execute("""
                    UPDATE signals SET search_vector =
                        to_tsvector('english', coalesce(entity, '') || ' ' || coalesce(text, '') || ' ' || coalesce(signal_type, ''))
                    WHERE user_email = %s
                """, (user_email,))
                count = conn.execute("SELECT COUNT(*) FROM signals WHERE user_email = %s", (user_email,)).fetchone()[0]
            else:
                conn.execute("""
                    UPDATE signals SET search_vector =
                        to_tsvector('english', coalesce(entity, '') || ' ' || coalesce(text, '') || ' ' || coalesce(signal_type, ''))
                """)
                count = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
            conn.commit()
            logger.info("Rebuilt Postgres FTS index: %d signals", count)
            return count

        # SQLite: clear + re-insert into FTS5 virtual table
        conn.execute("DELETE FROM signals_fts")

        # Load all signals from main table
        if user_email:
            rows = conn.execute(
                "SELECT * FROM signals WHERE user_email = ?",
                (user_email,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM signals").fetchall()

        count = 0
        for row in rows:
            row_dict = dict(row)
            conn.execute("""
                INSERT INTO signals_fts (signal_id, entity, text, signal_type, user_email, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                row_dict["signal_id"],
                row_dict["entity"],
                row_dict["text"],
                row_dict["signal_type"],
                row_dict.get("user_email", "bootstrap"),
                row_dict["timestamp"],
            ))
            count += 1

        conn.commit()
        logger.info("Rebuilt FTS index: %d signals", count)
        return count
    except sqlite3.OperationalError as e:
        logger.warning("FTS rebuild failed: %s", e)
        return 0
    except Exception as e:
        logger.warning("FTS rebuild failed: %s", e)
        return 0
    finally:
        conn.close()


def semantic_search(
    query: str,
    user_email: str | None = None,
    limit: int = 10,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    """Search signals by semantic relevance using BM25 ranking.

    K3-DATA-003 fix: backend-aware.
    - SQLite: FTS5 MATCH + bm25() function.
    - Postgres: tsvector @@ plainto_tsquery + ts_rank() function.
    """
    path = db_path or _get_db_path()
    init_fts_index(path)

    # Sanitize the natural-language query into a safe FTS5 MATCH expression.
    fts_query = _build_fts_query(query)
    if not fts_query:
        # No content-bearing tokens — let the caller's LIKE fallback handle it.
        return []

    conn = get_db_conn(path)
    if not _is_postgres():
        conn.row_factory = sqlite3.Row
    try:
        effective_limit = limit * 10

        if _is_postgres():
            # Postgres: use the search_vector tsvector column on the signals table.
            # plainto_tsquery handles natural-language input safely (no FTS5 syntax).
            # ts_rank returns a relevance score (higher = more relevant, unlike bm25
            # which is lower = more relevant — we handle the ORDER BY direction below).
            if user_email:
                fts_rows = conn.execute(
                    """
                    SELECT signal_id, ts_rank(search_vector, plainto_tsquery('english', %s)) as relevance_score
                    FROM signals
                    WHERE search_vector @@ plainto_tsquery('english', %s) AND user_email = %s
                    ORDER BY relevance_score DESC
                    LIMIT %s
                    """,
                    (query, query, user_email, effective_limit),
                ).fetchall()
            else:
                fts_rows = conn.execute(
                    """
                    SELECT signal_id, ts_rank(search_vector, plainto_tsquery('english', %s)) as relevance_score
                    FROM signals
                    WHERE search_vector @@ plainto_tsquery('english', %s)
                    ORDER BY relevance_score DESC
                    LIMIT %s
                    """,
                    (query, query, effective_limit),
                ).fetchall()
        else:
            # SQLite: FTS5 MATCH + bm25()
            if user_email:
                fts_rows = conn.execute(
                    """
                    SELECT signal_id, bm25(signals_fts) as relevance_score
                    FROM signals_fts
                    WHERE signals_fts MATCH ? AND user_email = ?
                    ORDER BY relevance_score
                    LIMIT ?
                    """,
                    (fts_query, user_email, effective_limit),
                ).fetchall()
            else:
                fts_rows = conn.execute(
                    """
                    SELECT signal_id, bm25(signals_fts) as relevance_score
                    FROM signals_fts
                    WHERE signals_fts MATCH ?
                    ORDER BY relevance_score
                    LIMIT ?
                    """,
                    (fts_query, effective_limit),
                ).fetchall()

        if not fts_rows:
            return []

        # Look up full signal data from the main signals table.
        signal_ids = [r["signal_id"] for r in fts_rows]
        if _is_postgres():
            placeholders = ",".join(["%s"] * len(signal_ids))
        else:
            placeholders = ",".join(["?"] * len(signal_ids))

        try:
            main_rows = conn.execute(
                f"SELECT * FROM signals WHERE signal_id IN ({placeholders})",
                signal_ids,
            ).fetchall()
            main_map = {r["signal_id"]: dict(r) for r in main_rows}
        except Exception:
            main_map = {}

        results = []
        for fts_row in fts_rows:
            sid = fts_row["signal_id"]
            if sid in main_map:
                entry = main_map[sid]
            else:
                # Fallback: get data directly from FTS
                fts_data = conn.execute(
                    "SELECT signal_id, entity, text, signal_type, user_email, timestamp FROM signals_fts WHERE signal_id = ?",
                    (sid,),
                ).fetchone()
                if fts_data:
                    entry = dict(fts_data)
                else:
                    entry = {"signal_id": sid, "entity": "", "text": "", "signal_type": "", "user_email": "", "timestamp": ""}
            entry["relevance_score"] = fts_row["relevance_score"]
            results.append(entry)

        return results
    except sqlite3.OperationalError as e:
        logger.debug("FTS search failed, falling back to empty: %s", e)
        return []
    finally:
        conn.close()


def get_relevant_signals(
    query_or_entity: str,
    user_email: str | None = None,
    limit: int = 10,
    db_path: str | None = None,
    as_of: str | None = None,
    from_date: str | None = None,
) -> list[dict[str, Any]]:
    """Get signals relevant to a query or entity."""
    if not query_or_entity or not query_or_entity.strip():
        return []

    # Try FTS5 semantic search first
    results = semantic_search(
        query_or_entity,
        user_email=user_email,
        limit=limit,
        db_path=db_path,
    )

    # Temporal filtering: if as_of is provided, filter out future signals
    if as_of and results:
        try:
            from datetime import datetime as _dt, timezone as _tz
            as_of_dt = _dt.fromisoformat(as_of.replace("Z", "+00:00"))
            if as_of_dt.tzinfo is None:
                as_of_dt = as_of_dt.replace(tzinfo=_tz.utc)
            filtered = []
            for r in results:
                ts = r.get("timestamp", "")
                if not ts:
                    filtered.append(r)
                    continue
                try:
                    row_ts = _dt.fromisoformat(ts.replace("Z", "+00:00"))
                    if row_ts.tzinfo is None:
                        row_ts = row_ts.replace(tzinfo=_tz.utc)
                    if row_ts <= as_of_dt:
                        filtered.append(r)
                except Exception:
                    filtered.append(r)
            results = filtered
        except Exception as e:
            logger.debug("as_of filtering in get_relevant_signals failed: %s", e)

    # P1-1 fix: Temporal LOWER bound — if from_date is provided, filter out
    # signals BEFORE from_date. "What did I commit to last quarter?" must
    # not return commitments from 6 months ago.
    if from_date and results:
        try:
            from datetime import datetime as _dt, timezone as _tz
            from_dt = _dt.fromisoformat(from_date.replace("Z", "+00:00"))
            if from_dt.tzinfo is None:
                from_dt = from_dt.replace(tzinfo=_tz.utc)
            filtered = []
            for r in results:
                ts = r.get("timestamp", "")
                if not ts:
                    filtered.append(r)
                    continue
                try:
                    row_ts = _dt.fromisoformat(ts.replace("Z", "+00:00"))
                    if row_ts.tzinfo is None:
                        row_ts = row_ts.replace(tzinfo=_tz.utc)
                    if row_ts >= from_dt:
                        filtered.append(r)
                except Exception:
                    filtered.append(r)
            results = filtered
        except Exception as e:
            logger.debug("from_date filtering in get_relevant_signals failed: %s", e)

    if results:
        return results

    # Fallback: entity/text substring matching (when FTS5 unavailable or
    # returned nothing). The previous implementation passed the FULL query
    # string as a single LIKE pattern, which only matched signals that
    # literally contained the entire question — effectively never. Split
    # into significant terms and match on ANY of them, mirroring the OR
    # semantics the FTS path now uses.
    path = db_path or _get_db_path()
    fts_query = _build_fts_query(query_or_entity)
    terms = [t for t in fts_query.split(" OR ") if t] if fts_query else []
    if not terms:
        # No content-bearing terms at all — nothing to match.
        return []
    conn = get_db_conn(path)
    conn.row_factory = sqlite3.Row
    try:
        # Build a WHERE clause that ORs each significant term across both
        # entity and text columns. Each term is parameterized to avoid
        # SQL injection.
        or_clauses: list[str] = []
        params: list[Any] = []
        for term in terms:
            pat = f"%{term}%"
            or_clauses.append("LOWER(entity) LIKE ? OR LOWER(text) LIKE ?")
            params.extend([pat, pat])
        where_clause = " OR ".join(f"({c})" for c in or_clauses)
        if user_email:
            sql = (
                f"SELECT * FROM signals WHERE user_email = ? AND ({where_clause}) "
                f"ORDER BY timestamp DESC LIMIT ?"
            )
            params = [user_email] + params + [limit]
        else:
            sql = (
                f"SELECT * FROM signals WHERE {where_clause} "
                f"ORDER BY timestamp DESC LIMIT ?"
            )
            params = params + [limit]
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_signal_from_fts(signal_id: str, db_path: str | None = None) -> None:
    """Remove a signal from the FTS index (when a signal is deleted)."""
    path = db_path or _get_db_path()
    conn = get_db_conn(path)
    try:
        conn.execute("DELETE FROM signals_fts WHERE signal_id = ?", (signal_id,))
        conn.commit()
    except sqlite3.OperationalError as e:
        logger.debug("commit failed: %s", e)
    finally:
        conn.close()

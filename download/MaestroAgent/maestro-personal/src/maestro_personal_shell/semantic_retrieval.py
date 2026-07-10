"""
Semantic retrieval — FTS5-backed BM25 ranking for signals.

Phase 1.3 fix: replaces the raw `SELECT * FROM signals` dump with
semantic retrieval. The LLM now receives only the signals relevant
to the query/situation, not every signal in the database.

Uses SQLite FTS5 (Full-Text Search 5) which is built into Python's
sqlite3 module — no external vector DB or embedding service needed.
FTS5 provides BM25 ranking, which is the standard relevance ranking
algorithm used by search engines.

Benefits:
1. Solves context-window bloat — only relevant signals sent to LLM
2. Solves temporal relevance — most relevant signals ranked first
3. Reduces LLM latency — smaller context = faster generation
4. Improves factual accuracy — LLM grounds in relevant evidence, not noise
"""

from __future__ import annotations

import sqlite3
import logging
import os
from datetime import datetime, timezone
from typing import Any
from pathlib import Path

logger = logging.getLogger(__name__)


def _get_db_path() -> str:
    return os.environ.get(
        "MAESTRO_PERSONAL_DB",
        str(Path(__file__).resolve().parent / "personal.db"),
    )


def init_fts_index(db_path: str | None = None) -> None:
    """Initialize the FTS5 virtual table for semantic signal search.

    Creates a virtual table that mirrors the signals table and supports
    BM25-ranked full-text search over entity + text + signal_type.
    """
    path = db_path or _get_db_path()
    conn = sqlite3.connect(path)
    try:
        # FTS5 virtual table — stores a search index alongside the main signals table
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
    finally:
        conn.close()


def index_signal(signal: dict[str, Any], db_path: str | None = None) -> None:
    """Add or update a signal in the FTS index.

    Call this whenever a signal is saved to the main signals table.
    """
    path = db_path or _get_db_path()
    conn = sqlite3.connect(path)
    try:
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
    finally:
        conn.close()


def rebuild_fts_index(db_path: str | None = None, user_email: str | None = None) -> int:
    """Rebuild the FTS index from the main signals table.

    Returns the number of signals indexed.
    """
    path = db_path or _get_db_path()
    init_fts_index(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        # Clear existing index
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
    finally:
        conn.close()


def semantic_search(
    query: str,
    user_email: str | None = None,
    limit: int = 10,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    """Search signals by semantic relevance using BM25 ranking.

    This is the core Phase 1.3 function. Instead of loading ALL signals,
    it retrieves only the signals most relevant to the query, ranked by
    BM25 (the standard search-engine relevance algorithm).

    Args:
        query: The search query (e.g., "What did AcmeCorp commit to?")
        user_email: If provided, only search this user's signals (isolation)
        limit: Maximum number of results (default 10)
        db_path: Database path

    Returns: List of signal dicts, ranked by relevance (most relevant first)
    """
    path = db_path or _get_db_path()
    init_fts_index(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        if user_email:
            # BM25-ranked search, scoped to user
            rows = conn.execute(
                """
                SELECT signal_id, entity, text, signal_type, user_email, timestamp,
                       bm25(signals_fts) as relevance_score
                FROM signals_fts
                WHERE signals_fts MATCH ? AND user_email = ?
                ORDER BY relevance_score
                LIMIT ?
                """,
                (query, user_email, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT signal_id, entity, text, signal_type, user_email, timestamp,
                       bm25(signals_fts) as relevance_score
                FROM signals_fts
                WHERE signals_fts MATCH ?
                ORDER BY relevance_score
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()

        return [dict(r) for r in rows]
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
) -> list[dict[str, Any]]:
    """Get signals relevant to a query or entity.

    This is the function build_shell and Ask should call instead of
    load_signals_from_db(). It returns only the signals that are
    semantically relevant to the current context.

    If FTS5 is unavailable, falls back to entity-prefix matching (still
    better than loading all signals).

    Args:
        query_or_entity: The query string or entity name to search for
        user_email: If provided, only return this user's signals
        limit: Maximum results

    Returns: List of relevant signal dicts, ranked by relevance
    """
    if not query_or_entity or not query_or_entity.strip():
        # No query — return empty (don't dump everything)
        return []

    # Try FTS5 semantic search first
    results = semantic_search(
        query_or_entity,
        user_email=user_email,
        limit=limit,
        db_path=db_path,
    )

    if results:
        return results

    # Fallback: entity-prefix matching (when FTS5 unavailable)
    path = db_path or _get_db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        entity_lower = query_or_entity.lower()
        if user_email:
            rows = conn.execute(
                """SELECT * FROM signals
                   WHERE user_email = ? AND (
                       LOWER(entity) LIKE ? OR LOWER(text) LIKE ?
                   )
                   ORDER BY timestamp DESC LIMIT ?""",
                (user_email, f"%{entity_lower}%", f"%{entity_lower}%", limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM signals
                   WHERE LOWER(entity) LIKE ? OR LOWER(text) LIKE ?
                   ORDER BY timestamp DESC LIMIT ?""",
                (f"%{entity_lower}%", f"%{entity_lower}%", limit),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_signal_from_fts(signal_id: str, db_path: str | None = None) -> None:
    """Remove a signal from the FTS index (when a signal is deleted)."""
    path = db_path or _get_db_path()
    conn = sqlite3.connect(path)
    try:
        conn.execute("DELETE FROM signals_fts WHERE signal_id = ?", (signal_id,))
        conn.commit()
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()

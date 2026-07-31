"""Signal deduplication by content hash (P76).

Root cause (P10): save_signal_to_db() had no dedup check — every ingestion
created a new row, so N syncs of the same email produced N duplicate signals.
Fix: deterministic hash over (source_id, normalized_text, entity); repeat
content updates last_seen in metadata on the existing row instead of
inserting a new one.

Authored by: Kimi K3 (engineering lead) via CTO↔K3 loop (P46 verified)
  Generation ID: gen-1785183089-yLbYAWTGx4WErQWbXJkn
CTO fix: replaced sqlite3.connect() with get_db_conn() from db_util.py
  (production runs on PostgreSQL; direct sqlite3 calls don't work there).
  Replaced `id` column references with `signal_id` (the actual PK).
  Removed `last_seen`/`updated_at` column writes (those columns don't exist
  in the signals table; last_seen is stored in metadata JSON only).
"""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
import re
from datetime import datetime, timezone

from maestro_personal_shell.db_util import get_db_conn, default_sqlite_path

logger = logging.getLogger(__name__)

_WS_RE = re.compile(r"\s+")
_TRAIL_PUNCT_RE = re.compile(r"[\s\.,;:!?\-–—…'\"')\]}>]+$")
_SEP = "\x1f"  # unit separator: avoids ("ab","c") vs ("a","bc") collisions


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(text: str) -> str:
    """Lowercase, strip, collapse whitespace, remove trailing punctuation."""
    t = _WS_RE.sub(" ", (text or "").lower().strip())
    return _TRAIL_PUNCT_RE.sub("", t)


def compute_content_hash(source_id: str, text: str, entity: str) -> str:
    """Compute a deterministic content hash for deduplication (P76).

    Hash = sha256(source_id + normalized_text + entity) where
    normalized_text = lowercase, strip, collapse whitespace, remove
    trailing punctuation. Same email ingested 10x → same hash → 1 signal;
    different text or different entity → different hash.
    """
    payload = _SEP.join([source_id or "", _normalize_text(text), entity or ""])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _extract_fields(signal: dict) -> tuple[str, str, str]:
    source_id = str(signal.get("source_id") or signal.get("source") or signal.get("signal_id") or "")
    text = str(signal.get("text") or signal.get("content") or "")
    entity = str(signal.get("entity") or "")
    return source_id, text, entity


def check_duplicate(
    content_hash: str, user_email: str, db_path: str | None = None
) -> dict | None:
    """Return the existing signal dict for this hash+user, else None.

    P85: never raises — returns None on any error.
    """
    try:
        conn = get_db_conn(db_path or default_sqlite_path())
        conn.row_factory = _get_row_factory(conn)
        row = None
        # Search for the content_hash in metadata. The hash is 64 hex chars
        # (unique enough that false positives are impossible). We search without
        # surrounding quotes because save_signal_to_db() may double-encode the
        # metadata JSON, escaping the quotes.
        row = conn.execute(
            "SELECT * FROM signals WHERE user_email = ? "
            "AND metadata LIKE ? "
            "ORDER BY created_at ASC LIMIT 1",
            (user_email, f'%{content_hash}%'),
        ).fetchone()
        return dict(row) if row else None
    except Exception as exc:
        logger.error("duplicate check failed for user=%s: %s", user_email, exc)
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _get_row_factory(conn):
    """Get the appropriate row factory (sqlite3.Row for SQLite, DictCursor for Postgres)."""
    import sqlite3
    try:
        return sqlite3.Row
    except Exception:
        return None


def _parse_metadata(raw) -> dict:
    """Parse metadata from a DB column value, handling double-encoding.

    save_signal_to_db() may JSON-encode the metadata string, producing
    double-encoded values like '"{\\"source\\": \\"gmail\\"}"'. This
    function parses until it gets a dict.
    """
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        val = raw
        for _ in range(3):  # max 3 levels of double-encoding
            try:
                val = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                break
            if isinstance(val, dict):
                return val
        return {}
    return {}


def _touch_last_seen(signal_id: str, content_hash: str, db_path: str | None) -> None:
    """Update last_seen timestamp in the signal's metadata (P76).

    No new row is created — the existing signal's metadata is updated with
    last_seen and seen_count.
    """
    try:
        conn = get_db_conn(db_path or default_sqlite_path())
        import sqlite3 as _sqlite3
        try:
            conn.row_factory = _sqlite3.Row
        except Exception:
            pass  # PostgresConnection uses DictCursor already
        row = conn.execute(
            "SELECT metadata FROM signals WHERE signal_id = ?", (signal_id,)
        ).fetchone()
        if not row:
            return
        raw = row[0] if isinstance(row, (tuple, list)) else (row["metadata"] if hasattr(row, '__getitem__') and not isinstance(row, str) else row)
        metadata = _parse_metadata(raw)
        metadata["content_hash"] = content_hash
        metadata["last_seen"] = _now_iso()
        metadata["seen_count"] = int(metadata.get("seen_count", 1)) + 1
        conn.execute(
            "UPDATE signals SET metadata = ? WHERE signal_id = ?",
            (json.dumps(metadata), signal_id),
        )
        conn.commit()
    except Exception as exc:
        logger.error("touch_last_seen failed for signal=%s: %s", signal_id, exc)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _save_via_production_path(
    signal: dict, user_email: str, db_path: str | None
) -> str | None:
    """Save using the existing save_signal_to_db() (P22: production path).

    save_signal_to_db signature: (signal, db_path=None, user_email="bootstrap")
    """
    from maestro_personal_shell.api import save_signal_to_db

    try:
        result = save_signal_to_db(signal, db_path=db_path, user_email=user_email)
    except TypeError:
        # Older signature might not accept db_path as kwarg
        result = save_signal_to_db(signal, user_email=user_email)
    if isinstance(result, dict):
        sid = result.get("signal_id") or result.get("id")
        return str(sid) if sid is not None else None
    return str(result) if result is not None else None


def dedup_and_save(
    signal: dict, user_email: str, db_path: str | None = None
) -> dict:
    """Deduplicate and save a signal (P76). Never raises (P85).

    Existing hash → update last_seen in metadata, return existing (no new row).
    New hash → save via the production save_signal_to_db() path with the
    content_hash embedded in metadata. On any error, falls through to a
    plain save so the signal is still persisted without dedup protection.
    """
    source_id, text, entity = _extract_fields(signal)
    content_hash = compute_content_hash(source_id, text, entity)
    try:
        existing = check_duplicate(content_hash, user_email, db_path)
        if existing:
            existing_id = existing.get("signal_id") or existing.get("id")
            _touch_last_seen(str(existing_id), content_hash, db_path)
            return {
                "action": "updated_existing",
                "signal_id": str(existing_id),
                "content_hash": content_hash,
                "duplicate_of": str(existing_id),
            }
        # New signal — embed content_hash in metadata before saving
        raw_meta = signal.get("metadata")
        metadata: dict = {}
        if isinstance(raw_meta, str):
            try:
                metadata = json.loads(raw_meta)
            except (json.JSONDecodeError, TypeError):
                metadata = {}
        elif isinstance(raw_meta, dict):
            metadata = dict(raw_meta)
        metadata["content_hash"] = content_hash
        now = _now_iso()
        metadata.setdefault("first_seen", now)
        metadata["last_seen"] = now
        metadata.setdefault("seen_count", 1)
        to_save = dict(signal)
        to_save["metadata"] = (
            json.dumps(metadata) if isinstance(raw_meta, str) else metadata
        )
        signal_id = _save_via_production_path(to_save, user_email, db_path)
        return {
            "action": "created",
            "signal_id": signal_id,
            "content_hash": content_hash,
            "duplicate_of": None,
        }
    except Exception as exc:
        logger.error("dedup path failed, falling through to plain save: %s", exc)
        try:
            signal_id = _save_via_production_path(signal, user_email, db_path)
        except Exception as save_exc:
            logger.error("fallback save also failed for user=%s: %s", user_email, save_exc)
            signal_id = None
        return {
            "action": "created",
            "signal_id": signal_id,
            "content_hash": content_hash,
            "duplicate_of": None,
        }


def backfill_content_hashes(db_path: str | None = None) -> dict:
    """One-time migration: compute content_hash for existing signals (P76).

    Returns {processed: int, updated: int, errors: int}. Never raises.
    """
    stats = {"processed": 0, "updated": 0, "errors": 0}
    try:
        conn = get_db_conn(db_path or default_sqlite_path())
        conn.row_factory = _get_row_factory(conn)
        rows = conn.execute("SELECT * FROM signals").fetchall()
        for row in rows:
            stats["processed"] += 1
            try:
                sig = dict(row)
                raw = sig.get("metadata")
                metadata = _parse_metadata(raw)
                if metadata.get("content_hash"):
                    continue
                source_id, text, entity = _extract_fields(sig)
                metadata["content_hash"] = compute_content_hash(source_id, text, entity)
                signal_id = sig.get("signal_id") or sig.get("id")
                conn.execute(
                    "UPDATE signals SET metadata = ? WHERE signal_id = ?",
                    (json.dumps(metadata), signal_id),
                )
                stats["updated"] += 1
            except Exception as exc:
                stats["errors"] += 1
                logger.error("backfill failed for one signal: %s", exc)
        conn.commit()
    except Exception as exc:
        logger.error("backfill_content_hashes failed: %s", exc)
        stats["errors"] += 1
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return stats

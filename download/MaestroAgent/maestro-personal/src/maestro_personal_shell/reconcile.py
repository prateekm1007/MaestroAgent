"""P41 — Single source of truth for signal classification/ownership.

The 5-layer ownership trace exposed a class-level smell: the
classification/ownership truth was stored in FOUR parallel places:
  1. The signal's metadata (the canonical source)
  2. The commitment_ledger table's commitment_type column (a copy)
  3. The evidence dict assembled in the ask router (a copy)
  4. The pre-built answer lines (a copy)

Each copy drifted, and each drift was a layer the CTO had to chase
(dont→don't, signal_id→source_signal_id, ledger never synced, evidence
dict missing commitment_type, answer built before filter). The
denormalization IS the bug class.

PRINCIPLE P41: at read time, the answer and its evidence are DERIVED
from ONE reconciled record (the signal's metadata), never assembled
from parallel copies that must be re-synced after every migration.

This module exposes reconcile_signal(signal_id) — the single read path.
The commitment_ledger becomes a CACHED VIEW; its commitment_type column
is DERIVED from signal metadata at read time, never written independently.

ReconciledRecord shape:
  {
    "signal_id": str,
    "entity": str,
    "owner": str,             # "user" | "other" | "unknown"
    "commitment_type": str,   # explicit | tentative | third_party_report | ...
    "is_commitment": bool,
    "text": str,              # ORIGINAL display text (never normalized)
    "timestamp": str,
    "source": str,            # "manual" | "gmail" | "calendar" | ...
    "reconciled_at": str,     # ISO 8601 UTC
  }
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def reconcile_signal(signal_id: str, db_path: str | None = None, user_email: str = "") -> dict[str, Any] | None:
    """Return the canonical reconciled record for a signal.

    SINGLE SOURCE OF TRUTH (P41): reads the signal's metadata ONCE and
    derives the classification/ownership from it. The commitment_ledger
    table is NOT consulted — its commitment_type column is a stale copy.
    All future reads of a signal's classification MUST go through this
    function.

    Args:
        signal_id: the signal's UUID
        db_path: optional SQLite path (defaults to the personal.db)
        user_email: the user's email (for ownership derivation — signals
            where the user is the speaker have owner="user")

    Returns:
        ReconciledRecord dict, or None if the signal doesn't exist.
    """
    if not signal_id:
        return None
    from maestro_personal_shell.db_util import get_db_conn, default_sqlite_path
    _db = db_path or default_sqlite_path()
    try:
        conn = get_db_conn(_db)
    except Exception as e:
        logger.debug("reconcile_signal: DB connection failed: %s", e)
        return None
    try:
        row = conn.execute(
            "SELECT signal_id, entity, text, timestamp, metadata, signal_type, user_email "
            "FROM signals WHERE signal_id = ?",
            (signal_id,),
        ).fetchone()
        conn.close()
    except Exception as e:
        logger.debug("reconcile_signal: query failed: %s", e)
        try:
            conn.close()
        except Exception:
            pass
        return None
    if not row:
        return None

    sig_id, entity, text, timestamp, metadata_json, signal_type, sig_user_email = row

    # Parse metadata — this is the SINGLE SOURCE OF TRUTH for classification
    metadata: dict[str, Any] = {}
    if metadata_json:
        try:
            metadata = json.loads(metadata_json)
        except Exception:
            metadata = {}

    # Derive commitment_type from metadata (canonical) — fall back to
    # signal_type only if metadata has no classification (legacy signal)
    commitment_type = (
        metadata.get("commitment_type")
        or metadata.get("classification", {}).get("commitment_type")
        or ""
    )
    if not commitment_type:
        # Legacy signal — derive from signal_type
        st = (signal_type or "").lower()
        if "commitment" in st:
            commitment_type = "explicit"
        elif "report" in st or "statement" in st:
            commitment_type = "third_party_report"
        elif "follow_up" in st:
            commitment_type = "request"
        else:
            commitment_type = "not_a_commitment"

    # Derive is_commitment from metadata (canonical)
    is_commitment = metadata.get("is_commitment")
    if is_commitment is None:
        # Fall back to derived rule
        is_commitment = commitment_type in (
            "explicit", "implicit", "conditional", "completed",
            "cancelled", "superseded", "disputed", "broken",
        )

    # Derive owner from metadata (canonical) — "user" | "other" | "unknown"
    owner = metadata.get("owner", "unknown")
    if owner not in ("user", "other", "unknown"):
        owner = "unknown"

    # The text is the ORIGINAL — never normalized (P42 only normalizes
    # for structural matching, not display)
    return {
        "signal_id": str(sig_id or ""),
        "entity": str(entity or ""),
        "owner": owner,
        "commitment_type": commitment_type,
        "is_commitment": bool(is_commitment),
        "text": str(text or ""),
        "timestamp": str(timestamp or ""),
        "source": metadata.get("source", "manual"),
        "user_email": str(sig_user_email or user_email or ""),
        "reconciled_at": datetime.now(timezone.utc).isoformat(),
        # Provenance — verifiable: this record came from signal metadata
        "reconcile_source": "signal.metadata",
    }


def reconcile_signals_for_user(
    user_email: str,
    db_path: str | None = None,
    entity_filter: str = "",
    include_non_commitments: bool = False,
) -> list[dict[str, Any]]:
    """Return reconciled records for all of a user's signals.

    SINGLE SOURCE OF TRUTH (P41): one read path. The commitments surface,
    the ask router, and the prepare fallback MUST all call this function
    instead of querying the DB or ledger directly.

    Args:
        user_email: the user's email
        db_path: optional SQLite path
        entity_filter: if non-empty, only return signals for this entity
        include_non_commitments: if False (default), filter out signals
            where is_commitment=False (P37 — non-commitments MUST NOT
            surface in the commitment list)

    Returns:
        List of ReconciledRecord dicts, sorted by timestamp descending.
    """
    from maestro_personal_shell.db_util import get_db_conn, default_sqlite_path
    _db = db_path or default_sqlite_path()
    try:
        conn = get_db_conn(_db)
    except Exception as e:
        logger.debug("reconcile_signals_for_user: DB connection failed: %s", e)
        return []
    try:
        if entity_filter:
            rows = conn.execute(
                "SELECT signal_id FROM signals WHERE user_email = ? AND entity = ? "
                "ORDER BY timestamp DESC",
                (user_email, entity_filter),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT signal_id FROM signals WHERE user_email = ? "
                "ORDER BY timestamp DESC",
                (user_email,),
            ).fetchall()
        conn.close()
    except Exception as e:
        logger.debug("reconcile_signals_for_user: query failed: %s", e)
        try:
            conn.close()
        except Exception:
            pass
        return []

    results: list[dict[str, Any]] = []
    for (sig_id,) in rows:
        rec = reconcile_signal(sig_id, db_path=_db, user_email=user_email)
        if rec is None:
            continue
        # P37: filter non-commitments unless explicitly requested
        if not include_non_commitments and not rec["is_commitment"]:
            continue
        results.append(rec)
    return results


def filter_for_promise_query(
    records: list[dict[str, Any]],
    user_email: str,
    entity_filter: str = "",
) -> list[dict[str, Any]]:
    """P36 ownership filter for "What did I promise X?" queries.

    SINGLE SOURCE OF TRUTH (P41): operates on ReconciledRecords (already
    derived from signal metadata). Excludes:
      - third_party_report (someone else's promise)
      - non-commitment types (tentative, proposal, request, aspiration, negation)
      - signals where owner != "user"
      - signals for a different entity (if entity_filter is set)

    This is the structural end of the 5-layer wack-a-mole — ONE filter on
    the reconciled record, not 5 separate filters on parallel copies.
    """
    NON_USER_TYPES = {
        "third_party_report", "not_a_commitment",
        "tentative", "proposal", "request", "aspiration", "negation",
    }
    filtered = []
    for rec in records:
        if rec.get("commitment_type") in NON_USER_TYPES:
            continue
        if rec.get("owner") != "user":
            continue
        if entity_filter and rec.get("entity", "").lower() != entity_filter.lower():
            continue
        if not rec.get("is_commitment"):
            continue
        filtered.append(rec)
    return filtered

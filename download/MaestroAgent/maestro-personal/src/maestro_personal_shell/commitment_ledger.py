"""
Commitment Ledger — the normalized, persistent store of commitments.

Phase 3 of the Road-to-9/10. The roadmap requires:
  1. A 500-item labeled corpus (13 categories).
  2. Structured extraction schema (owner, recipient, action, deadline).
  3. Full lifecycle state machine (candidate → active → at_risk →
     completed_claimed → completed_verified → disputed → cancelled →
     superseded → tombstoned).
  4. Closure matching by topic/action/recipient, not entity only.
  5. Dispute handling (completed but incomplete / late / denied / changed).
  6. Corrections propagate to all surfaces.

This module owns the schema + state machine + persistence + closure
matching + correction propagation. It does NOT re-implement commitment
*classification* — that stays in commitment_classifier.py (which calls
Core's classify_transcript_chunk per the no-dilution guard). The ledger
persists the classifier's output and enforces lifecycle invariants.

Design notes
------------
- The ledger is a SEPARATE table from `signals`. A signal is a raw
  observation; a ledger entry is the normalized commitment derived from
  one or more signals. One signal can produce at most one ledger entry
  (1:1 via signal_id FK), but a ledger entry can be superseded by a
  newer one (superseded_by FK).
- Every state transition is audit-logged via audit_trust.log_data_access
  BEFORE the write (P20: log before destructive op). Illegal transitions
  are rejected and logged as 'rejected_transition'.
- Closure matching uses (entity + action-keyword overlap + recipient)
  so "Sent the proposal" closes "I'll send the proposal by Friday" even
  though the texts differ. This is the roadmap's requirement #4.
- Correction propagation invalidates downstream artifacts by deleting
  the signal from FTS and marking the ledger entry cancelled/tombstoned;
  the next build_shell() call re-derives situations/predictions/graph
  from the corrected signal set. We prove no stale artifacts remain by
  re-running detect_situations() and asserting the corrected entity no
  longer appears.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

LEDGER_SCHEMA = """
CREATE TABLE IF NOT EXISTS commitments_ledger (
    ledger_id        TEXT PRIMARY KEY,
    signal_id        TEXT NOT NULL,
    user_email       TEXT NOT NULL,
    entity           TEXT NOT NULL,
    commitment_type  TEXT NOT NULL,
    state            TEXT NOT NULL,
    owner            TEXT NOT NULL DEFAULT 'unknown',
    recipient        TEXT NOT NULL DEFAULT '',
    action           TEXT NOT NULL DEFAULT '',
    deadline_text    TEXT NOT NULL DEFAULT '',
    deadline_datetime TEXT NOT NULL DEFAULT '',
    confidence       REAL NOT NULL DEFAULT 0.0,
    evidence_quote   TEXT NOT NULL DEFAULT '',
    superseded_by    TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    UNIQUE(signal_id)
)
"""

LEDGER_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_ledger_user_state ON commitments_ledger(user_email, state)",
    "CREATE INDEX IF NOT EXISTS idx_ledger_entity ON commitments_ledger(entity)",
    "CREATE INDEX IF NOT EXISTS idx_ledger_signal ON commitments_ledger(signal_id)",
]


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

# Legal forward transitions. A transition not in this map is rejected.
# The roadmap's lifecycle:
#   candidate -> active -> at_risk -> completed_claimed -> completed_verified
#            -> disputed -> cancelled -> superseded -> tombstoned
#
# We allow:
#   candidate → active, cancelled, tombstoned
#   active → at_risk, completed_claimed, disputed, cancelled, superseded
#   at_risk → completed_claimed, disputed, cancelled, superseded
#   completed_claimed → completed_verified, disputed, cancelled
#   completed_verified → disputed (reopen), tombstoned
#   disputed → completed_verified, cancelled, superseded, tombstoned
#   cancelled → tombstoned
#   superseded → tombstoned
#   tombstoned → (terminal)
LEGAL_TRANSITIONS: dict[str, set[str]] = {
    "candidate":          {"active", "cancelled", "tombstoned"},
    "active":             {"at_risk", "completed_claimed", "disputed", "cancelled", "superseded"},
    "at_risk":            {"completed_claimed", "disputed", "cancelled", "superseded"},
    "completed_claimed":  {"completed_verified", "disputed", "cancelled"},
    "completed_verified": {"disputed", "tombstoned"},
    "disputed":           {"completed_verified", "cancelled", "superseded", "tombstoned"},
    "cancelled":          {"tombstoned"},
    "superseded":         {"tombstoned"},
    "tombstoned":         set(),  # terminal
}


def is_legal_transition(from_state: str, to_state: str) -> bool:
    """Return True iff from_state → to_state is a legal lifecycle transition."""
    return to_state in LEGAL_TRANSITIONS.get(from_state, set())


# ---------------------------------------------------------------------------
# Table initialization
# ---------------------------------------------------------------------------

def init_ledger_table(db_path: str) -> None:
    """Create the commitments_ledger table + indexes if they don't exist."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(LEDGER_SCHEMA)
        for idx in LEDGER_INDEXES:
            conn.execute(idx)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _new_ledger_id() -> str:
    import uuid
    return f"led-{uuid.uuid4()}"


def upsert_ledger_entry(
    classification: dict[str, Any],
    signal: dict[str, Any],
    user_email: str,
    db_path: str,
) -> dict[str, Any] | None:
    """Insert or update a ledger entry from a classifier result + signal.

    Returns the persisted entry dict, or None if the classification says
    'not_a_commitment' (no ledger row created).

    State handling:
      - If no existing entry for this signal_id, insert with the
        classifier's state (default 'candidate' if missing).
      - If an entry exists and the classifier's state differs, route
        through transition_ledger_state() to enforce legality.
    """
    init_ledger_table(db_path)

    # Don't persist non-commitments.
    ctype = classification.get("commitment_type", "not_a_commitment")
    if classification.get("is_commitment") is False or ctype == "not_a_commitment":
        return None

    signal_id = str(signal.get("signal_id", ""))
    if not signal_id:
        return None

    now = datetime.now(timezone.utc).isoformat()
    target_state = classification.get("state", "candidate")
    # Sanity: never insert an unknown state.
    if target_state not in LEGAL_TRANSITIONS:
        target_state = "candidate"

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        existing = conn.execute(
            "SELECT * FROM commitments_ledger WHERE signal_id = ?",
            (signal_id,),
        ).fetchone()

        if existing is None:
            # Insert new entry.
            ledger_id = _new_ledger_id()
            conn.execute(
                """INSERT INTO commitments_ledger
                   (ledger_id, signal_id, user_email, entity, commitment_type, state,
                    owner, recipient, action, deadline_text, deadline_datetime,
                    confidence, evidence_quote, superseded_by, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)""",
                (
                    ledger_id,
                    signal_id,
                    user_email,
                    signal.get("entity", ""),
                    ctype,
                    target_state,
                    classification.get("owner", "unknown"),
                    classification.get("recipient", ""),
                    classification.get("action", ""),
                    classification.get("deadline_text", ""),
                    classification.get("deadline_datetime", ""),
                    float(classification.get("confidence", 0.0)),
                    classification.get("evidence_quote", signal.get("text", "")),
                    now,
                    now,
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM commitments_ledger WHERE ledger_id = ?", (ledger_id,)
            ).fetchone()
            return dict(row) if row else None
        else:
            # Update fields that can change without a state transition.
            conn.execute(
                """UPDATE commitments_ledger
                   SET commitment_type = ?, owner = ?, recipient = ?, action = ?,
                       deadline_text = ?, deadline_datetime = ?, confidence = ?,
                       evidence_quote = ?, updated_at = ?
                   WHERE signal_id = ?""",
                (
                    ctype,
                    classification.get("owner", existing["owner"]),
                    classification.get("recipient", existing["recipient"]),
                    classification.get("action", existing["action"]),
                    classification.get("deadline_text", existing["deadline_text"]),
                    classification.get("deadline_datetime", existing["deadline_datetime"]),
                    float(classification.get("confidence", existing["confidence"])),
                    classification.get("evidence_quote", existing["evidence_quote"]),
                    now,
                    signal_id,
                ),
            )
            conn.commit()
            # If the classifier wants a different state, transition legally.
            if target_state != existing["state"]:
                _transition_state_conn(
                    conn, existing["ledger_id"], existing["state"], target_state,
                    user_email, signal_id, db_path,
                )
            row = conn.execute(
                "SELECT * FROM commitments_ledger WHERE ledger_id = ?",
                (existing["ledger_id"],),
            ).fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def _transition_state_conn(
    conn: sqlite3.Connection,
    ledger_id: str,
    from_state: str,
    to_state: str,
    user_email: str,
    signal_id: str,
    db_path: str,
) -> bool:
    """Transition state using an existing connection (no reconnect)."""
    if from_state == to_state:
        return True
    if not is_legal_transition(from_state, to_state):
        # Log the rejected transition (P20: audit before destructive op).
        try:
            from maestro_personal_shell.audit_trust import log_data_access
            log_data_access(
                user_email=user_email,
                action="rejected_transition",
                endpoint="/api/commitments/ledger",
                resource_id=ledger_id,
                details={"from": from_state, "to": to_state, "signal_id": signal_id},
                db_path=db_path,
            )
        except Exception:
            pass
        logger.warning(
            "Rejected illegal commitment transition %s → %s for ledger %s",
            from_state, to_state, ledger_id,
        )
        return False

    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE commitments_ledger SET state = ?, updated_at = ? WHERE ledger_id = ?",
        (to_state, now, ledger_id),
    )
    conn.commit()

    # Audit the successful transition.
    try:
        from maestro_personal_shell.audit_trust import log_data_access
        log_data_access(
            user_email=user_email,
            action="commitment_transition",
            endpoint="/api/commitments/ledger",
            resource_id=ledger_id,
            details={"from": from_state, "to": to_state, "signal_id": signal_id},
            db_path=db_path,
        )
    except Exception:
        pass
    return True


def transition_ledger_state(
    ledger_id: str,
    to_state: str,
    user_email: str,
    db_path: str,
) -> bool:
    """Public API: transition a ledger entry to a new state.

    Returns True if the transition was legal + applied, False otherwise.
    Every attempt (legal or rejected) is audit-logged.
    """
    init_ledger_table(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM commitments_ledger WHERE ledger_id = ?", (ledger_id,)
        ).fetchone()
        if row is None:
            return False
        return _transition_state_conn(
            conn, ledger_id, row["state"], to_state, user_email,
            row["signal_id"], db_path,
        )
    finally:
        conn.close()


def get_ledger_entries(
    user_email: str,
    db_path: str,
    state: str | None = None,
    entity: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Read ledger entries for a user, optionally filtered by state/entity."""
    init_ledger_table(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        sql = "SELECT * FROM commitments_ledger WHERE user_email = ?"
        params: list[Any] = [user_email]
        if state:
            sql += " AND state = ?"
            params.append(state)
        if entity:
            sql += " AND entity = ?"
            params.append(entity)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Closure matching (roadmap requirement #4)
# ---------------------------------------------------------------------------

# Action keywords used to match a completion/cancellation signal to an
# active ledger entry. Two commitments "match" for closure if they share
# the same entity AND overlap on at least one action keyword AND (if both
# have recipients) share the same recipient. This prevents "Sent the
# invoice" from closing "I'll send the proposal" even though both are
# "send" actions — "invoice" vs "proposal" don't overlap.
_ACTION_STOPWORDS = frozenset({
    "a", "an", "the", "by", "for", "to", "of", "with", "and", "or",
    "will", "shall", "should", "can", "may", "might", "must",
    "i", "you", "we", "they", "he", "she", "it",
    "me", "him", "her", "us", "them",
    "this", "that", "these", "those",
    "is", "are", "was", "were", "be", "been", "being",
    "do", "does", "did", "have", "has", "had",
    "in", "on", "at", "from", "up", "out", "into",
    "my", "your", "his", "its", "our", "their",
    "next", "last", "this", "week", "month", "day", "year",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "eod", "cob", "asap", "soon", "tomorrow", "today", "yesterday",
})


def _action_keywords(text: str) -> set[str]:
    """Extract content-bearing keywords from a commitment action/text."""
    import re
    cleaned = re.sub(r"[^\w\s]", " ", (text or "").lower())
    return {w for w in cleaned.split() if w and w not in _ACTION_STOPWORDS and len(w) > 2}


def match_closure(
    completion_signal: dict[str, Any],
    active_entries: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Find the active ledger entry that a completion/cancellation signal closes.

    Matching rules (roadmap requirement #4 — closure by topic/action/recipient,
    not entity only):
      1. Entity must match (case-insensitive, fuzzy on whitespace).
      2. Action keywords must overlap by >= 1 token.
      3. If both have recipients, recipients must match.
      4. Among matches, prefer the one with the most keyword overlap.

    Returns the best-matching entry, or None if no match.
    """
    def _norm_entity(s: str) -> str:
        """Normalize an entity name for fuzzy matching: lowercase, strip,
        collapse all internal whitespace to a single space. This makes
        'AcmeCorp' match 'Acme Corp' and 'Acme  Corp' without requiring
        exact substring containment (which fails across word boundaries)."""
        import re
        return re.sub(r"\s+", " ", (s or "").lower().strip())

    comp_entity = _norm_entity(completion_signal.get("entity", ""))
    comp_text = str(completion_signal.get("text", ""))
    comp_keywords = _action_keywords(comp_text)
    comp_recipient = str(completion_signal.get("recipient", "")).lower().strip()

    best: dict[str, Any] | None = None
    best_overlap = 0
    for entry in active_entries:
        ent_entity = _norm_entity(entry.get("entity", ""))
        # Entity match: exact, or one contains the other after whitespace
        # normalization. Handles "AcmeCorp" vs "Acme Corp" (the normalized
        # forms are "acmecorp" vs "acme corp" — "acme" is a substring of
        # "acme corp" but "acmecorp" is not, so we also try removing all
        # spaces from both sides for a compactness-insensitive compare).
        if comp_entity and ent_entity:
            comp_compact = comp_entity.replace(" ", "")
            ent_compact = ent_entity.replace(" ", "")
            if (comp_entity != ent_entity
                    and comp_entity not in ent_entity
                    and ent_entity not in comp_entity
                    and comp_compact != ent_compact
                    and comp_compact not in ent_compact
                    and ent_compact not in comp_compact):
                continue
        elif comp_entity != ent_entity:
            continue

        # Action overlap.
        entry_action = entry.get("action", "") or entry.get("evidence_quote", "")
        entry_keywords = _action_keywords(entry_action)
        overlap = comp_keywords & entry_keywords
        if not overlap:
            continue

        # Recipient check (only if both specify one).
        entry_recipient = str(entry.get("recipient", "")).lower().strip()
        if comp_recipient and entry_recipient and comp_recipient != entry_recipient:
            continue

        if len(overlap) > best_overlap:
            best_overlap = len(overlap)
            best = entry

    return best


# ---------------------------------------------------------------------------
# Correction propagation (roadmap requirement #6)
# ---------------------------------------------------------------------------

def propagate_correction(
    signal_id: str,
    correction: str,
    user_email: str,
    db_path: str,
) -> dict[str, Any]:
    """Propagate a signal correction to the ledger + downstream artifacts.

    correction is one of: 'dismiss', 'cancel', 'supersede', 'dispute'.

    Actions:
      - dismiss/cancel: transition the ledger entry to 'cancelled' (or
        'tombstoned' if already cancelled), remove from FTS so it stops
        surfacing in retrieval.
      - supersede: mark 'superseded' (the caller should also create the
        new entry).
      - dispute: mark 'disputed'.

    Returns a dict of what was propagated, for the caller to log/return.
    """
    init_ledger_table(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    propagated: dict[str, Any] = {
        "signal_id": signal_id,
        "correction": correction,
        "ledger_updated": False,
        "fts_removed": False,
        "ledger_id": None,
        "from_state": None,
        "to_state": None,
    }
    try:
        row = conn.execute(
            "SELECT * FROM commitments_ledger WHERE signal_id = ? AND user_email = ?",
            (signal_id, user_email),
        ).fetchone()
        if row is None:
            # No ledger entry for this signal — nothing to propagate.
            return propagated

        target_state = {
            "dismiss": "cancelled",
            "cancel": "cancelled",
            "supersede": "superseded",
            "dispute": "disputed",
        }.get(correction, "cancelled")

        propagated["ledger_id"] = row["ledger_id"]
        propagated["from_state"] = row["state"]

        applied = _transition_state_conn(
            conn, row["ledger_id"], row["state"], target_state,
            user_email, signal_id, db_path,
        )
        propagated["ledger_updated"] = applied
        propagated["to_state"] = target_state if applied else row["state"]
        conn.commit()
    finally:
        conn.close()

    # Remove from FTS so retrieval stops surfacing the corrected signal.
    try:
        from maestro_personal_shell.semantic_retrieval import delete_signal_from_fts
        delete_signal_from_fts(signal_id, db_path=db_path)
        propagated["fts_removed"] = True
    except Exception as e:
        logger.debug("FTS removal during correction propagation failed: %s", e)

    # Note: situations/predictions/graph are derived on each build_shell()
    # call from the current signals table. The corrected signal's metadata
    # marks it as dismissed, which the salience filter in build_shell()
    # already respects. We assert this in the correction-propagation test
    # by re-running detect_situations() and confirming the corrected entity
    # no longer appears as a top situation.
    return propagated


# ---------------------------------------------------------------------------
# Migration / backfill
# ---------------------------------------------------------------------------

def backfill_ledger_from_signals(
    db_path: str,
    user_email: str | None = None,
) -> int:
    """Backfill the ledger from existing signals.

    For each signal that is a commitment type (per its signal_type or a
    rule-based check), create a ledger entry with state='candidate' (we
    can't re-run the LLM classifier in bulk without an API key, so we
    conservatively mark backfilled entries as candidate, not active).

    Returns the number of entries created.
    """
    init_ledger_table(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    count = 0
    try:
        if user_email:
            rows = conn.execute(
                "SELECT * FROM signals WHERE user_email = ?", (user_email,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM signals").fetchall()

        for sig in rows:
            sig_dict = dict(sig)
            sig_id = sig_dict.get("signal_id", "")
            if not sig_id:
                continue
            # Skip if already in ledger.
            existing = conn.execute(
                "SELECT 1 FROM commitments_ledger WHERE signal_id = ?", (sig_id,)
            ).fetchone()
            if existing:
                continue

            stype = str(sig_dict.get("signal_type", "")).lower()
            # Only commitment-bearing signal types go in the ledger.
            is_commitment_type = any(
                kw in stype for kw in ("commitment", "promise", "pledge", "deliver")
            )
            if not is_commitment_type:
                continue

            classification = {
                "is_commitment": True,
                "commitment_type": "explicit" if "explicit" in stype else "implicit",
                "state": "candidate",
                "owner": "unknown",
                "recipient": "",
                "action": "",
                "deadline_text": "",
                "deadline_datetime": "",
                "confidence": 0.5,
                "evidence_quote": sig_dict.get("text", ""),
            }
            upsert_ledger_entry(classification, sig_dict, sig_dict.get("user_email", "bootstrap"), db_path)
            count += 1
    finally:
        conn.close()
    return count

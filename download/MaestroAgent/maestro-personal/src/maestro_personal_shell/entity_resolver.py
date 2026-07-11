"""
Entity Resolution Service — normalizes entity aliases to canonical names.

F3 fix: the same counterparty shows up as "Acme Corp" (manual entry),
"client" (Gmail header), "AcmeCorp" (no space), "acme" (lowercase) —
creating disjoint situations for one relationship.

This service normalizes entities using:
1. Exact match normalization (case, whitespace, punctuation)
2. Alias mapping (user-configurable: "client" → "AcmeCorp")
3. Fuzzy matching (Levenshtein distance for near-misses)
4. LLM-powered resolution (when available, for novel aliases)

The resolved canonical entity is stored in signal metadata so all
surfaces read from the same world model.
"""

from __future__ import annotations

import logging
import sqlite3
from maestro_personal_shell.db_util import get_db_conn
import os
import re
from typing import Any
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _get_db_path() -> str:
    return os.environ.get(
        "MAESTRO_PERSONAL_DB",
        str(Path(__file__).resolve().parent / "personal.db"),
    )


def init_entity_aliases(db_path: str | None = None) -> None:
    """Initialize the entity_aliases table."""
    path = db_path or _get_db_path()
    conn = get_db_conn(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entity_aliases (
            alias TEXT PRIMARY KEY,
            canonical_entity TEXT NOT NULL,
            user_email TEXT NOT NULL,
            created_at TEXT NOT NULL,
            confidence REAL DEFAULT 1.0
        )
    """)
    conn.commit()
    conn.close()


def _normalize(text: str) -> str:
    """Normalize text for comparison: lowercase, collapse whitespace, strip punctuation."""
    if not text:
        return ""
    text = text.lower().strip()
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    # Remove common suffixes/punctuation
    text = re.sub(r'[.,;:!?\-_]+', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    # Remove common corporate suffixes
    for suffix in [' corp', ' corporation', ' inc', ' llc', ' ltd', ' co']:
        if text.endswith(suffix):
            text = text[:-len(suffix)].strip()
    return text


def _levenshtein(a: str, b: str) -> int:
    """Compute Levenshtein distance between two strings."""
    if len(a) < len(b):
        return _levenshtein(b, a)
    if len(b) == 0:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        current = [i + 1]
        for j, cb in enumerate(b):
            insert = previous[j + 1] + 1
            delete = current[j] + 1
            substitute = previous[j] + (ca != cb)
            current.append(min(insert, delete, substitute))
        previous = current
    return previous[-1]


def _fuzzy_match(a: str, b: str, threshold: float = 0.85) -> bool:
    """Check if two strings are similar enough to be the same entity.

    P1-1 fix: the substring check was too aggressive. "Alex" was matching
    "Alexa" because "alex" is a substring of "alexa" — two DIFFERENT names
    that share a prefix were being collapsed into one entity. The fix:
    only treat a substring match as a match when the remainder (the part
    of the longer string after the shorter one ends) is a known corporate
    suffix (corp, inc, ltd, etc.) or empty. This allows "Acme" → "AcmeCorp"
    (remainder = "corp") while rejecting "Alex" → "Alexa" (remainder = "a").
    """
    if not a or not b:
        return False
    norm_a = _normalize(a)
    norm_b = _normalize(b)
    if norm_a == norm_b:
        return True
    # P1-1 fix: substring check with corporate-suffix guard.
    # Corporate suffixes that legitimately extend an entity name without
    # changing its identity. Only these remainders are treated as "same entity."
    _CORPORATE_SUFFIXES = {
        "corp", "corporation", "inc", "incorp", "llc", "ltd", "co",
        "group", "holdings", "partners", "solutions", "systems",
        "technologies", "tech", "labs", "industries", "global",
    }
    if norm_a in norm_b:
        remainder = norm_b[len(norm_a):].strip()
        if not remainder or remainder in _CORPORATE_SUFFIXES:
            return True
    if norm_b in norm_a:
        remainder = norm_a[len(norm_b):].strip()
        if not remainder or remainder in _CORPORATE_SUFFIXES:
            return True
    # Levenshtein-based similarity
    max_len = max(len(norm_a), len(norm_b))
    if max_len == 0:
        return False
    distance = _levenshtein(norm_a, norm_b)
    similarity = 1.0 - (distance / max_len)
    return similarity >= threshold


def add_alias(
    alias: str,
    canonical_entity: str,
    user_email: str = "bootstrap",
    confidence: float = 1.0,
    db_path: str | None = None,
) -> None:
    """Manually add an entity alias mapping."""
    path = db_path or _get_db_path()
    init_entity_aliases(path)
    conn = get_db_conn(path)
    conn.execute(
        "INSERT OR REPLACE INTO entity_aliases (alias, canonical_entity, user_email, created_at, confidence) VALUES (?, ?, ?, ?, ?)",
        (alias.lower().strip(), canonical_entity, user_email, datetime.now(timezone.utc).isoformat(), confidence),
    )
    conn.commit()
    conn.close()


def resolve_entity(
    entity: str,
    user_email: str = "bootstrap",
    known_entities: list[str] | None = None,
    db_path: str | None = None,
) -> str:
    """Resolve an entity name to its canonical form.

    F3 fix: normalizes "Acme Corp", "client", "AcmeCorp", "acme" to a
    single canonical entity so they don't create disjoint situations.

    Resolution order:
    1. Check user-configured alias table
    2. Exact normalized match against known entities
    3. Fuzzy match against known entities (Levenshtein)
    4. Return the normalized input as the canonical form

    Args:
        entity: The raw entity name to resolve
        user_email: User scope for alias lookup
        known_entities: List of canonical entities already in the system
        db_path: Database path

    Returns: The canonical entity name
    """
    if not entity or not entity.strip():
        return entity or ""

    entity = entity.strip()
    path = db_path or _get_db_path()

    # 1. Check user-configured alias table
    try:
        init_entity_aliases(path)
        conn = get_db_conn(path)
        row = conn.execute(
            "SELECT canonical_entity FROM entity_aliases WHERE alias = ? AND user_email = ?",
            (entity.lower().strip(), user_email),
        ).fetchone()
        conn.close()
        if row:
            return row[0]
    except Exception as e:
        logger.debug("Entity alias lookup failed: %s", e)

    # 2. Exact normalized match against known entities
    if known_entities:
        norm_input = _normalize(entity)
        for known in known_entities:
            if _normalize(known) == norm_input:
                return known  # Return the known canonical form (preserves original casing)

        # 3. Fuzzy match against known entities
        for known in known_entities:
            if _fuzzy_match(entity, known):
                return known

    # 4. Return normalized input as canonical (title case for consistency)
    return entity


def resolve_entity_with_signals(
    entity: str,
    signals: list[Any],
    user_email: str = "bootstrap",
    db_path: str | None = None,
) -> str:
    """Resolve entity using existing signals as the known-entity pool.

    This is the production entry point — it collects all known entities
    from the user's signals and resolves against them.
    """
    known = set()
    for sig in signals:
        sig_entity = getattr(sig, "entity", "") or (sig.get("entity", "") if isinstance(sig, dict) else "")
        if sig_entity:
            known.add(sig_entity)

    return resolve_entity(
        entity,
        user_email=user_email,
        known_entities=list(known),
        db_path=db_path,
    )


def get_entity_clusters(
    signals: list[Any],
    user_email: str = "bootstrap",
    db_path: str | None = None,
) -> dict[str, list[str]]:
    """Group all entity aliases into clusters by canonical entity.

    Returns a dict: {canonical_entity: [alias1, alias2, ...]}
    Useful for showing the user what aliases were merged.
    """
    clusters: dict[str, list[str]] = {}
    resolved_map: dict[str, str] = {}  # alias -> canonical

    # First pass: resolve all entities
    for sig in signals:
        entity = getattr(sig, "entity", "") or (sig.get("entity", "") if isinstance(sig, dict) else "")
        if not entity:
            continue
        if entity not in resolved_map:
            canonical = resolve_entity_with_signals(entity, signals, user_email, db_path)
            resolved_map[entity] = canonical

    # Second pass: build clusters
    for alias, canonical in resolved_map.items():
        if canonical not in clusters:
            clusters[canonical] = []
        if alias != canonical:
            clusters[canonical].append(alias)

    return {k: v for k, v in clusters.items() if v}  # Only return clusters with aliases

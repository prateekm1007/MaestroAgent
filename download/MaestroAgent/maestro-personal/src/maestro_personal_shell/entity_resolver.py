"""Entity Resolution Service — normalizes entity aliases to canonical names."""

from __future__ import annotations

import logging
import sqlite3
from maestro_personal_shell.db_util import get_db_conn, default_sqlite_path
import os
import re
from typing import Any
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _get_db_path() -> str:
    return default_sqlite_path()


def init_entity_aliases(db_path: str | None = None) -> None:
    """Initialize the entity_aliases table.

    K3-DATA-001 fix: PRIMARY KEY is now (alias, user_email) — composite, scoped
    per tenant. The old schema used `alias TEXT PRIMARY KEY` alone, which meant
    Bob's INSERT OR REPLACE would silently repoint Alice's "Maria" alias to a
    different canonical entity (cross-tenant data corruption). With the composite
    key, two users can independently own the same alias string.
    """
    path = db_path or _get_db_path()
    conn = get_db_conn(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entity_aliases (
            alias TEXT NOT NULL,
            canonical_entity TEXT NOT NULL,
            user_email TEXT NOT NULL,
            created_at TEXT NOT NULL,
            confidence REAL DEFAULT 1.0,
            PRIMARY KEY (alias, user_email)
        )
    """)
    # K3-DATA-001 migration: if the old schema (alias TEXT PRIMARY KEY) exists,
    # recreate with the composite key. This is a no-op on fresh databases.
    try:
        cols = conn.execute("PRAGMA table_info(entity_aliases)").fetchall()
        pk_cols = [c[1] for c in cols if c[5] > 0]  # c[5] is pk flag
        if pk_cols == ["alias"]:
            logger.info("K3-DATA-001 migration: rebuilding entity_aliases with composite PK (alias, user_email)")
            conn.execute("ALTER TABLE entity_aliases RENAME TO entity_aliases_old")
            conn.execute("""
                CREATE TABLE entity_aliases (
                    alias TEXT NOT NULL,
                    canonical_entity TEXT NOT NULL,
                    user_email TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    PRIMARY KEY (alias, user_email)
                )
            """)
            conn.execute("INSERT OR IGNORE INTO entity_aliases (alias, canonical_entity, user_email, created_at, confidence) SELECT alias, canonical_entity, user_email, created_at, confidence FROM entity_aliases_old")
            conn.execute("DROP TABLE entity_aliases_old")
    except Exception as e:
        logger.debug("K3-DATA-001 migration check skipped: %s", e)
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
    """Check if two strings are similar enough to be the same entity."""
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
        # Allow first-name match: "alex" matches "alex chen" if "alex"
        # is a complete word (followed by space) in "alex chen"
        if norm_b[len(norm_a):len(norm_a)+1] == " ":
            return True
    if norm_b in norm_a:
        remainder = norm_a[len(norm_b):].strip()
        if not remainder or remainder in _CORPORATE_SUFFIXES:
            return True
        # Allow first-name match in the other direction too
        if norm_a[len(norm_b):len(norm_b)+1] == " ":
            return True
    # Levenshtein-based similarity
    max_len = max(len(norm_a), len(norm_b))
    if max_len == 0:
        return False
    distance = _levenshtein(norm_a, norm_b)
    similarity = 1.0 - (distance / max_len)

    # Bug 5 fix (auditor v15): numeric-suffix entity collapse.
    # "Sarah Chen A" and "Sarah Chen B" have similarity 0.917 (above 0.85
    # threshold) so they get matched as the same entity — but they are
    # DISTINCT entities. Fix: if the only difference is a trailing
    # alphanumeric character (A/B/1/2/etc.), they are DIFFERENT entities.
    # This prevents the collapse that has been unfixed for 3 builds.
    if similarity >= threshold and distance == 1:
        # Find where they differ
        min_len = min(len(norm_a), len(norm_b))
        if len(norm_a) != len(norm_b):
            # Length difference of 1 — one has an extra trailing char
            # e.g. "sarah chen" vs "sarah chen a" — but this was already
            # caught by the substring check above. If we're here, the
            # shorter one is NOT a prefix of the longer one.
            pass
        else:
            # Same length, 1 char difference — find the position
            diff_pos = next((i for i in range(min_len) if norm_a[i] != norm_b[i]), -1)
            if diff_pos >= 0:
                # If the difference is at the LAST character, they are
                # distinct entities with a trailing identifier
                # (e.g. "sarah chen a" vs "sarah chen b")
                if diff_pos == min_len - 1:
                    return False
                # If the difference is a single char in the middle,
                # it could be a typo — allow the match
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
    allow_fuzzy: bool = False,
) -> str:
    """Resolve an entity name to its canonical form.

    Phase 1.1 fix (auditor v16): fuzzy matching is now DISABLED at write
    time (allow_fuzzy=False). The prior code fuzzy-matched at ingestion,
    causing "Fabian Ashworth 1785394619" to merge with "Nadia Ashworth
    1785393308" (similarity > 0.85 because they share "Ashworth 178539").
    This caused 1-in-8 misattribution across four consecutive audits.

    Fix: at write time, only exact alias table + exact normalized match.
    Fuzzy matching is query-time only (allow_fuzzy=True in Ask path).

    Args:
        allow_fuzzy: if True, allow fuzzy matching (query-time only).
                     Default False (write-time: exact match only).
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
            return row[0] if hasattr(row, "keys") else row[0]
    except Exception as e:
        logger.debug("Entity alias lookup failed: %s", e)

    # 2. Exact normalized match against known entities
    if known_entities:
        norm_input = _normalize(entity)
        for known in known_entities:
            if _normalize(known) == norm_input:
                return known  # Return the known canonical form (preserves original casing)

        # 3. Fuzzy match against known entities (QUERY-TIME ONLY)
        # Phase 1.1 fix: disabled at write time to prevent cross-run merges.
        if allow_fuzzy:
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
    allow_fuzzy: bool = False,
) -> str:
    """Resolve entity using existing signals as the known-entity pool.

    This is the production entry point — it collects all known entities
    from the user's signals and resolves against them.

    Phase 1.1 fix (auditor v16): allow_fuzzy defaults to False (write-time).
    The Ask path should pass allow_fuzzy=True for query-time fuzzy matching.
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
        allow_fuzzy=allow_fuzzy,
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


# ---------------------------------------------------------------------------
# Deterministic possessive entity resolution (Trust gap #4 / Alex's-thing fix)
# ---------------------------------------------------------------------------

# Matches possessive forms: "Alex's", "Maria's", "David's", "Jamie's"
# Also matches bare first names that appear before "thing" / "stuff":
# "Alex's thing", "Maria's stuff", "Jamie's situation"
_POSSESSIVE_RE = re.compile(r"\b([A-Z][a-z]+)'s\b")
_BARE_NAME_BEFORE_THING_RE = re.compile(
    r"\b([A-Z][a-z]+)\s+(?:thing|stuff|situation|matter|item)\b",
    re.IGNORECASE,
)


def extract_possessive_entity(query: str) -> str | None:
    """Extract the entity name from a possessive or implicit-reference query.

    Examples:
      "Alex's thing — what did I promise?"  → "Alex"
      "What did Maria promise?"              → None (no possessive; standard query)
      "Jamie's stuff"                        → "Jamie"
      "Sam's situation"                      → "Sam"

    Returns the extracted first name, or None if no possessive/implicit
    reference is present.
    """
    if not query:
        return None
    m = _POSSESSIVE_RE.search(query)
    if m:
        return m.group(1)
    m = _BARE_NAME_BEFORE_THING_RE.search(query)
    if m:
        return m.group(1)
    return None


def resolve_possessive_to_canonical(
    query: str,
    signals: list[Any],
    user_email: str = "bootstrap",
    db_path: str | None = None,
) -> str | None:
    """Deterministically resolve a possessive/implicit entity to its canonical form.

    This is the three-benefit fix:
      1. Retires Alex's-thing product leak (wrong entity returned)
      2. Retires CI LLM-flakiness (entity no longer depends on stochastic choice)
      3. Retires consistency-trust gap (same entity regardless of phrasing)

    Flow:
      1. Extract the first name from the possessive ("Alex's" → "Alex")
      2. Resolve it against the user's known entities via resolve_entity_with_signals
         (e.g., "Alex" → "Alex Chen")
      3. Return the canonical entity name, or None if no possessive/unresolvable

    The caller should FILTER evidence to only this entity before synthesis,
    so the LLM can't pick a different entity stochastically.
    """
    first_name = extract_possessive_entity(query)
    if not first_name:
        return None
    try:
        canonical = resolve_entity_with_signals(
            first_name, signals, user_email=user_email, db_path=db_path,
        )
        if canonical and canonical.lower() != first_name.lower():
            logger.debug(
                "Possessive resolution: %r → %r (from %d signals)",
                first_name, canonical, len(signals),
            )
        return canonical or first_name
    except Exception as e:
        logger.debug("Possessive entity resolution failed: %s", e)
        return first_name  # fall back to the bare first name


def filter_evidence_to_entity(
    evidence: list[dict[str, Any]],
    canonical_entity: str,
) -> list[dict[str, Any]]:
    """Filter evidence to only rows matching the canonical entity.

    Used after resolve_possessive_to_canonical to ensure the LLM only sees
    evidence for the queried entity. Matching is case-insensitive substring
    (canonical_entity "Alex Chen" matches evidence entity "alex chen" or
    "Alex Chen" or "Alex Chen (Acme)").
    """
    if not canonical_entity or not evidence:
        return evidence
    canon_lower = canonical_entity.lower()
    filtered = [
        ev for ev in evidence
        if canon_lower in str(ev.get("entity", "")).lower()
        or str(ev.get("entity", "")).lower() in canon_lower
    ]
    return filtered if filtered else evidence  # don't return empty; fall back


# ---------------------------------------------------------------------------
# Multi-entity possessive support (edge case #2 — union, not first-only)
# ---------------------------------------------------------------------------


def extract_all_possessive_entities(query: str) -> list[str]:
    """Extract ALL possessive/implicit entity names from a query.

    Handles multi-entity possessives like "Maria and Alex's things" —
    extracts both "Maria" (bare name before "and") and "Alex" (possessive).
    Also handles "Alex's and Maria's things" (both possessive).

    Returns a list of first names (may be empty if no possessives).
    """
    if not query:
        return []
    names: list[str] = []
    # Find all possessive forms ("Alex's", "Maria's")
    for m in _POSSESSIVE_RE.finditer(query):
        names.append(m.group(1))
    # Find bare-name-before-thing forms ("Alex thing")
    for m in _BARE_NAME_BEFORE_THING_RE.finditer(query):
        name = m.group(1)
        if name not in names:
            names.append(name)
    # Also handle "Maria and Alex's" — the "Maria" before "and" is a bare
    # name that's implicitly possessive in context. Look for the pattern:
    # "Name1 and Name2's" → both are possessive.
    conjunctive = re.compile(
        r"\b([A-Z][a-z]+)\s+(?:and|&|,)\s+([A-Z][a-z]+)'s\b"
    )
    for m in conjunctive.finditer(query):
        name1 = m.group(1)
        if name1 not in names:
            names.append(name1)
    return names


def resolve_possessives_to_canonical_set(
    query: str,
    signals: list[Any],
    user_email: str = "bootstrap",
    db_path: str | None = None,
) -> list[str]:
    """Resolve ALL possessive entities in a query to their canonical forms.

    Multi-entity version of resolve_possessive_to_canonical. Handles
    "Maria and Alex's things" → ["Maria Garcia", "Alex Chen"].

    Returns a list of canonical entity names (may be empty if no
    possessives or none resolve).
    """
    first_names = extract_all_possessive_entities(query)
    if not first_names:
        return []
    canonicals: list[str] = []
    for first_name in first_names:
        try:
            canonical = resolve_entity_with_signals(
                first_name, signals, user_email=user_email, db_path=db_path,
            )
            canonicals.append(canonical or first_name)
        except Exception as e:
            logger.debug("Possessive resolution for %r failed: %s", first_name, e)
            canonicals.append(first_name)
    return canonicals


def filter_evidence_to_entities(
    evidence: list[dict[str, Any]],
    canonical_entities: list[str],
) -> list[dict[str, Any]]:
    """Filter evidence to rows matching ANY of the canonical entities (union).

    Multi-entity version of filter_evidence_to_entity. For "Maria and Alex's
    things", keeps evidence for Maria OR Alex, drops everyone else.

    P36 (seventh audit retrieval contamination): if NO evidence matches the
    entity, return EMPTY — do NOT fall back to unfiltered evidence. The prior
    code returned all evidence when nothing matched, which is how a Maria
    query returned Railway build failures. Evidence that doesn't match the
    query entity is contamination, not a fallback.
    """
    if not canonical_entities or not evidence:
        return evidence
    canon_lowers = [c.lower() for c in canonical_entities if c]
    if not canon_lowers:
        return evidence
    filtered = []
    for ev in evidence:
        ev_entity_lower = str(ev.get("entity", "")).lower()
        if any(
            c in ev_entity_lower or ev_entity_lower in c
            for c in canon_lowers
        ):
            filtered.append(ev)
    # P36: return filtered only — do NOT fall back to unfiltered evidence.
    # An empty result triggers the P60 answer-evidence guard (clean abstention)
    # or the ledger-grounded fallback — both are better than contamination.
    return filtered

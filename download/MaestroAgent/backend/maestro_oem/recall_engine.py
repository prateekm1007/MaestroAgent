"""Phase 2: Hybrid RecallEngine — associative organizational memory.

Director directive (2026-07-03, EXT-AUDITOR-SYNTHESIS):

> Replace the keyword-only `whisper_recall.py` with a hybrid `RecallEngine`
> that returns Evidence objects.

Pipeline (per the directive):
    Query
      ↓
    1. Temporal interpretation (dateparser — "last month" → date range)
      ↓
    2. Entity resolution (synonym map + fuzzy match against known entities)
      ↓
    3. Semantic retrieval (all-MiniLM-L6-v2 embeddings, cosine similarity)
      ↓
    4. Graph expansion (find related entities via signal metadata)
      ↓
    5. Relationship traversal (find signals/decisions involving matched entities)
      ↓
    6. Relevance ranking (0.4 semantic + 0.3 recency + 0.3 entity match)
      ↓
    7. Build Evidence objects with source_artifacts/people_involved/timestamps
      ↓
    8. Compute what_changed_since from signal diff (signals AFTER last whisper shown)

This is the second of the 7-phase build order. Phase 1 (Evidence Spine)
is complete; this engine returns Evidence objects, not ad-hoc dicts.

DESIGN NOTES
------------

1. **Embedding model is lazy-loaded.** `SentenceTransformer('all-MiniLM-L6-v2')`
   is ~80MB. Loading it on import would slow down every API request.
   The model is loaded on first recall call and cached as a module-level
   singleton.

2. **Graceful degradation.** If sentence-transformers is unavailable
   (e.g., offline environment), the engine falls back to the existing
   `SemanticMatcher` (character n-gram TF-IDF). This is still more
   semantic than keyword matching. The fallback is LOGGED LOUDLY (P6).

3. **Store abstraction.** The engine accepts any object with
   `get_all_history(org_id)`. It does NOT require a real SQLite store —
   this is what makes it testable with MockWhisperHistoryStore (P3:
   don't mock the thing you're testing).

4. **Entity synonym map.** Vague queries use entity synonyms — "legal"
   expands to {compliance, contract, law, regulation}. The expansion is
   prepended to the query before embedding, so semantic similarity can
   bridge "legal" → "compliance review flagged".

5. **What-changed-since is signal-derived.** The old engine returned
   hardcoded template strings ("You ignored this. The issue may have
   evolved."). The new engine diffs signals: any signal with timestamp
   AFTER the whisper's last_shown, involving the same entity, becomes
   part of what_changed_since.
"""

from __future__ import annotations

import logging
import math
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any

logger = logging.getLogger(__name__)


# ─── Entity Synonym Map ────────────────────────────────────────────────────
# Used by the entity resolver to expand vague query terms. "legal" →
# {compliance, contract, law, regulation}. The expansion is prepended
# to the query before semantic embedding, so "legal" can match an
# insight that says "Compliance review flagged" even though the literal
# word "legal" is not in the insight.

ENTITY_SYNONYMS: dict[str, list[str]] = {
    "legal": ["legal", "compliance", "contract", "regulation", "law", "clause"],
    "security": ["security", "vulnerability", "cve", "auth", "oauth", "sso", "breach"],
    "pricing": ["pricing", "price", "cost", "budget", "discount", "invoice"],
    "engineering": ["engineering", "deploy", "deployment", "pr", "merge", "rollback", "release"],
    "customer": ["customer", "client", "account"],
    "timeline": ["timeline", "deadline", "delay", "late", "schedule", "due"],
    "hiring": ["hiring", "hire", "recruit", "staff", "headcount"],
    "commitment": ["commitment", "promise", "pledge", "deliverable", "due date"],
    "objection": ["objection", "concern", "pushback", "resistance", "hesitation"],
    "decision": ["decision", "decided", "outcome", "verdict", "ruling"],
    "churn": ["churn", "churned", "lost", "attrition", "departure"],
    "renewal": ["renewal", "renewed", "renew", "extend", "continue"],
}


# ─── Module-level model singleton (lazy-loaded) ────────────────────────────
# SentenceTransformer is ~80MB. Load it once per process, not per request.
# AUDITOR-FIX (HIGH-01): Added preload_model() for lifespan startup.
# Before this fix, the model was lazy-loaded on the first Ask request,
# causing a 9s blocking delay. Now the lifespan calls preload_model()
# at startup so the model is ready before any request arrives.

_MODEL_LOCK = threading.Lock()
_MODEL: Any = None  # Cached SentenceTransformer instance
_MODEL_LOAD_ATTEMPTED = False  # True after first load attempt (success or fail)


def preload_model() -> None:
    """Pre-load the embedding model at application startup.

    AUDITOR-FIX (HIGH-01): Call this from the FastAPI lifespan to load
    the SentenceTransformer model BEFORE any request arrives. This
    prevents the 9s blocking delay on the first Ask request.

    If sentence-transformers is unavailable, this is a no-op — the
    RecallEngine will fall back to character n-gram TF-IDF.
    """
    _get_embedding_model()


def _get_embedding_model() -> Any:
    """Get the cached SentenceTransformer, loading it on first call.

    Returns None if sentence-transformers is unavailable — the engine
    then falls back to character n-gram TF-IDF (logged loudly per P6).
    """
    global _MODEL, _MODEL_LOAD_ATTEMPTED
    if _MODEL is not None:
        return _MODEL
    with _MODEL_LOCK:
        if _MODEL_LOAD_ATTEMPTED:
            return _MODEL  # Already tried; either have it or gave up
        _MODEL_LOAD_ATTEMPTED = True
        try:
            from sentence_transformers import SentenceTransformer
            _MODEL = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("RecallEngine: loaded all-MiniLM-L6-v2 (384-dim embeddings)")
        except Exception as e:
            logger.warning(
                "RecallEngine: sentence-transformers unavailable (%s). "
                "Falling back to character n-gram TF-IDF. This is still more "
                "semantic than keyword matching but less powerful.",
                e,
            )
            _MODEL = None
    return _MODEL


def _embed(text: str) -> list[float] | None:
    """Embed a text using MiniLM. Returns None if model unavailable."""
    model = _get_embedding_model()
    if model is None or not text:
        return None
    try:
        vec = model.encode([text], normalize_embeddings=True)[0]
        return vec.tolist()
    except Exception as e:
        logger.warning("RecallEngine: embed failed (%s) — falling back", e)
        return None


def _cosine(v1: list[float], v2: list[float]) -> float:
    """Cosine similarity between two vectors (already L2-normalized by
    sentence-transformers when normalize_embeddings=True)."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    return max(0.0, min(1.0, sum(a * b for a, b in zip(v1, v2))))


def _decode_embedding_blob(blob: bytes) -> list[float] | None:
    """Decode an embedding BLOB stored in whisper_history.

    Stored as packed little-endian float32 (struct.pack(f"{N}f", *vec)).
    Returns None if the blob is invalid or empty.
    """
    if not blob:
        return None
    try:
        import struct
        # Each float32 is 4 bytes
        n = len(blob) // 4
        if n == 0:
            return None
        return list(struct.unpack(f"{n}f", blob))
    except Exception as e:
        logger.warning("RecallEngine: failed to decode embedding blob (%s)", e)
        return None


# ─── TF-IDF fallback (when sentence-transformers unavailable) ──────────────

_TFIDF_MATCHER = None
_TFIDF_LOCK = threading.Lock()


def _get_tfidf_fallback():
    """Get a cached SemanticMatcher for fallback embedding."""
    global _TFIDF_MATCHER
    if _TFIDF_MATCHER is not None:
        return _TFIDF_MATCHER
    with _TFIDF_LOCK:
        if _TFIDF_MATCHER is None:
            from maestro_oem.semantic_matcher import SemanticMatcher
            _TFIDF_MATCHER = SemanticMatcher(ngram_size=3, similarity_threshold=0.10)
        return _TFIDF_MATCHER


def _embed_fallback(text: str, corpus_texts: list[str]) -> list[float]:
    """Embed using TF-IDF character n-grams (fallback when MiniLM unavailable).

    The matcher is fitted on the corpus so the vocabulary matches.
    """
    matcher = _get_tfidf_fallback()
    if not hasattr(matcher, "_fitted_corpus") or matcher._fitted_corpus != corpus_texts:
        matcher.fit(corpus_texts + [text])
        matcher._fitted_corpus = list(corpus_texts)
    return matcher.embed(text)


# ─── Recall Query Builder ─────────────────────────────────────────────────

@dataclass
class ParsedQuery:
    """A parsed recall query — temporal + entity + semantic components."""

    raw: str
    # Temporal window (start, end). None if no temporal phrase detected.
    temporal_start: datetime | None = None
    temporal_end: datetime | None = None
    temporal_phrase: str | None = None  # The original phrase, e.g. "last month"
    # Resolved entities (canonical names) + their synonyms (for query expansion)
    entities: list[str] = field(default_factory=list)
    entity_synonyms: list[str] = field(default_factory=list)
    # The expanded query (original + entity synonyms) — used for embedding
    expanded_query: str = ""


class RecallQueryBuilder:
    """Parse a vague recall query into temporal + entity + semantic components.

    Step 1 of the RecallEngine pipeline. Uses `dateparser` for temporal
    interpretation and the ENTITY_SYNONYMS map for entity resolution.
    """

    # Phrases that signal a temporal filter is being requested
    TEMPORAL_PHRASES = [
        "last week", "last month", "last quarter", "last year",
        "yesterday", "this week", "this month", "this quarter",
        "a few days ago", "a week ago", "a month ago",
        "recently", "earlier", "before",
    ]

    def __init__(self, now: datetime | None = None) -> None:
        self._now = now or datetime.now(timezone.utc)

    def parse(self, query: str) -> ParsedQuery:
        """Parse a vague query into components."""
        query_lower = query.lower().strip()

        # ── Step 1: Temporal interpretation ────────────────────────────
        temporal_start, temporal_end, temporal_phrase = self._parse_temporal(query_lower)

        # ── Step 2: Entity resolution ──────────────────────────────────
        entities, synonyms = self._resolve_entities(query_lower)

        # ── Step 3: Query expansion (for semantic embedding) ───────────
        # Append synonyms so MiniLM can bridge "legal" → "compliance"
        expansion_parts = [query]
        if synonyms:
            expansion_parts.append(" ".join(synonyms))
        expanded_query = " ".join(expansion_parts)

        return ParsedQuery(
            raw=query,
            temporal_start=temporal_start,
            temporal_end=temporal_end,
            temporal_phrase=temporal_phrase,
            entities=entities,
            entity_synonyms=synonyms,
            expanded_query=expanded_query,
        )

    def _parse_temporal(self, query_lower: str) -> tuple[datetime | None, datetime | None, str | None]:
        """Extract a temporal window from the query using dateparser."""
        try:
            import dateparser
        except ImportError:
            logger.warning("RecallEngine: dateparser unavailable — no temporal filtering")
            return None, None, None

        # Find the first matching temporal phrase
        matched_phrase = None
        for phrase in self.TEMPORAL_PHRASES:
            if phrase in query_lower:
                matched_phrase = phrase
                break

        if not matched_phrase:
            return None, None, None

        # dateparser returns a single point in time. We convert to a window:
        #   "last week" → (now - 7d, now)
        #   "last month" → (now - 30d, now)
        #   "yesterday" → (now - 1d, now)
        try:
            parsed = dateparser.parse(
                matched_phrase,
                settings={"RELATIVE_BASE": self._now.replace(tzinfo=None)},
            )
        except Exception as e:
            logger.warning("RecallEngine: dateparser failed on %r: %s", matched_phrase, e)
            return None, None, None

        if parsed is None:
            return None, None, None

        # Convert to timezone-aware UTC
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        # Compute window based on phrase
        if "week" in matched_phrase:
            window = timedelta(days=7)
        elif "month" in matched_phrase:
            window = timedelta(days=30)
        elif "quarter" in matched_phrase:
            window = timedelta(days=90)
        elif "year" in matched_phrase:
            window = timedelta(days=365)
        elif "yesterday" in matched_phrase or "day" in matched_phrase:
            window = timedelta(days=1)
        else:
            # Fallback: 7-day window
            window = timedelta(days=7)

        return parsed, self._now, matched_phrase

    def _resolve_entities(self, query_lower: str) -> tuple[list[str], list[str]]:
        """Resolve entities mentioned in the query.

        Returns:
            (entities, synonyms) —
              entities: canonical entity names whose synonyms matched
              synonyms: ALL synonyms of matched entities (for query expansion)
        """
        entities: list[str] = []
        synonyms: list[str] = []
        for canonical, syns in ENTITY_SYNONYMS.items():
            for syn in syns:
                if syn in query_lower:
                    if canonical not in entities:
                        entities.append(canonical)
                    for s in syns:
                        if s not in synonyms:
                            synonyms.append(s)
                    break
        return entities, synonyms


# ─── Recall Engine ────────────────────────────────────────────────────────


@dataclass
class RecallItem:
    """A single recalled item — whisper, signal, or decision.

    The RecallEngine returns these. Each carries an Evidence object
    (Phase 1's universal evidence spine).
    """
    source_type: str  # "whisper" | "signal" | "decision"
    source_id: str
    text: str
    timestamp: datetime | None
    relevance_score: float
    evidence: Any  # Evidence object
    what_changed: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "source_id": self.source_id,
            "text": self.text,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "relevance_score": round(self.relevance_score, 4),
            "evidence_spine": self.evidence.to_dict() if hasattr(self.evidence, "to_dict") else self.evidence,
            "what_changed": self.what_changed,
        }


class RecallEngine:
    """Hybrid recall engine — semantic + temporal + entity + graph.

    Usage:
        engine = RecallEngine(whisper_history_store=store, signals=signals)
        result = engine.recall("that legal thing from last month")

    Result shape:
        {
            "query": str,
            "found": bool,
            "match_count": int,
            "whispers": [...],   # Backward-compatible with old WhisperRecall
            "items": [...],      # Cross-entity items (whisper + signal + decision)
            "message": str,      # Conversational recall message
            "parsed_query": {...},  # For debugging / auditor verification
        }
    """

    # Relevance weights (per directive: 0.4 semantic + 0.3 recency + 0.3 entity)
    W_SEMANTIC = 0.4
    W_RECENCY = 0.3
    W_ENTITY = 0.3

    # Minimum semantic similarity to consider a match (0-1)
    SEMANTIC_THRESHOLD = 0.20

    # For cross-entity recall, how many recent signals/decisions to surface
    MAX_CROSS_ENTITY_ITEMS = 5

    # Max whispers to return
    MAX_WHISPERS = 5

    def __init__(
        self,
        whisper_history_store: Any = None,
        signals: list | None = None,
        oem_state: Any = None,
        now: datetime | None = None,
    ) -> None:
        self.store = whisper_history_store
        self.signals = list(signals) if signals else []
        self.oem_state = oem_state
        self._now = now or datetime.now(timezone.utc)

    # ─── Public API ─────────────────────────────────────────────────────

    def recall(self, query: str, org_id: str = "default") -> dict[str, Any]:
        """Find whispers + signals + decisions matching a vague recollection.

        Pipeline:
          1. Parse query (temporal + entity)
          2. Fetch all whisper history
          3. For each whisper, compute semantic + recency + entity scores
          4. Filter by temporal window + semantic threshold
          5. Cross-entity expansion: find signals/decisions involving the
             same entities
          6. Build Evidence objects with rich field density
          7. Compute what_changed_since from signal diff
          8. Rank by combined score, return top items
        """
        if not query or not query.strip():
            return self._empty_result(query)

        # ── Step 1: Parse query ────────────────────────────────────────
        builder = RecallQueryBuilder(now=self._now)
        parsed = builder.parse(query)

        # ── Step 1b: L-01 fix — derive customer names from signal metadata ──
        # P13: Customer names are DERIVED from evidence (signal metadata),
        # not hardcoded in ENTITY_SYNONYMS. The synonym map only contains
        # generic topic terms ("customer", "client", "account"). Specific
        # customer names ("Globex", "AcmeCorp") are extracted from the
        # `metadata.customer` field of stored signals.
        #
        # This is the same pattern AskPipeline uses (Phase A, line 167).
        # Without this, "everything about Globex" would not resolve to
        # entity "Globex" — only to the generic "customer" topic.
        #
        # Names are lowercased because the entire entity-matching pipeline
        # (ENTITY_SYNONYMS, _entity_match_score, graph expansion) operates
        # case-insensitively. Storing mixed-case names would break matches.
        query_lower = query.lower()
        for sig in self.signals:
            try:
                customer = sig.metadata.get("customer", "") if hasattr(sig, "metadata") else ""
                if customer and customer.lower() in query_lower:
                    cust_lower = customer.lower()
                    if cust_lower not in parsed.entities:
                        parsed.entities.append(cust_lower)
                    if cust_lower not in parsed.entity_synonyms:
                        parsed.entity_synonyms.append(cust_lower)
            except Exception:
                continue

        # ── Step 2: Fetch all whisper history ──────────────────────────
        all_history: dict[str, dict[str, Any]] = {}
        if self.store:
            try:
                all_history = self.store.get_all_history(org_id=org_id)
            except Exception as e:
                logger.warning("RecallEngine: failed to get history: %s", e)

        # ── Step 3: Score whispers ─────────────────────────────────────
        query_vec = _embed(parsed.expanded_query)
        tfidf_fallback = query_vec is None
        if tfidf_fallback:
            # Fit fallback on the actual whisper insights we'll search against
            corpus = [h.get("insight", "") for h in all_history.values()]
            query_vec = _embed_fallback(parsed.expanded_query, corpus)

        scored_whispers: list[RecallItem] = []
        for wid, history in all_history.items():
            if not isinstance(history, dict):
                continue
            insight = history.get("insight", "")
            if not insight:
                continue

            # Semantic score
            # Phase 2 optimization: use cached embedding from store if present
            # (avoids re-embedding the same insight on every recall call)
            insight_vec = None
            cached_emb = history.get("embedding")
            if cached_emb and not tfidf_fallback:
                insight_vec = _decode_embedding_blob(cached_emb)
            if insight_vec is None:
                if tfidf_fallback:
                    insight_vec = _embed_fallback(insight, [h.get("insight", "") for h in all_history.values()])
                else:
                    insight_vec = _embed(insight)
            semantic_score = _cosine(query_vec, insight_vec) if query_vec and insight_vec else 0.0

            # Entity match score (does the whisper mention any resolved entity?)
            entity_score = self._entity_match_score(insight, history, parsed)

            # Recency score (1.0 = just shown, 0.0 = 1 year ago)
            recency_score = self._recency_score(history.get("last_shown"))

            # Combined score
            combined = (
                self.W_SEMANTIC * semantic_score
                + self.W_RECENCY * recency_score
                + self.W_ENTITY * entity_score
            )

            # Temporal filter — exclude if outside window
            in_temporal_window = True
            if parsed.temporal_start and parsed.temporal_end:
                last_shown = self._parse_timestamp(history.get("last_shown"))
                if last_shown:
                    if last_shown < parsed.temporal_start or last_shown > parsed.temporal_end:
                        in_temporal_window = False
                        continue  # Outside temporal window

            # Match threshold — must pass at least ONE of:
            #   - semantic similarity (the query content matches the insight)
            #   - strong entity match (cross-entity query like "everything about <customer>")
            #   - explicit temporal filter with whisper in window
            #     (the user said "last week" — they want time-bounded recall,
            #      not semantic match. The time window IS the filter.)
            passes_semantic = semantic_score >= self.SEMANTIC_THRESHOLD
            passes_entity = entity_score >= 0.5  # Strong entity match
            passes_temporal = (
                in_temporal_window
                and parsed.temporal_start is not None
            )
            if not (passes_semantic or passes_entity or passes_temporal):
                continue

            # ── Step 6: Build Evidence object ──────────────────────────
            evidence = self._build_evidence(
                insight=insight,
                history=history,
                entity=history.get("entity", ""),
                whisper_type=history.get("type", ""),
            )

            # ── Step 7: Compute what_changed_since ─────────────────────
            what_changed = self._compute_what_changed(
                whisper_last_shown=history.get("last_shown"),
                entity=history.get("entity", ""),
            )

            scored_whispers.append(RecallItem(
                source_type="whisper",
                source_id=wid,
                text=insight,
                timestamp=self._parse_timestamp(history.get("last_shown")),
                relevance_score=combined,
                evidence=evidence,
                what_changed=what_changed,
            ))

        # Sort by score
        scored_whispers.sort(key=lambda x: x.relevance_score, reverse=True)

        # ── Step 5: Cross-entity expansion (signals + decisions) ───────
        cross_items = self._cross_entity_recall(parsed, max_items=self.MAX_CROSS_ENTITY_ITEMS)

        # Combine all items
        all_items = scored_whispers[: self.MAX_WHISPERS] + cross_items

        # ── Step 8: Build result ───────────────────────────────────────
        # Backward-compatible "whispers" key (for old /ask/recall consumers)
        whispers_payload = [self._recall_item_to_whisper_dict(w) for w in scored_whispers[: self.MAX_WHISPERS]]

        found = len(all_items) > 0
        return {
            "query": query,
            "found": found,
            "match_count": len(all_items),
            "whispers": whispers_payload,
            "items": [item.to_dict() for item in all_items],
            "message": self._build_recall_message(scored_whispers[:1], query, found),
            "parsed_query": {
                "temporal_phrase": parsed.temporal_phrase,
                "temporal_start": parsed.temporal_start.isoformat() if parsed.temporal_start else None,
                "temporal_end": parsed.temporal_end.isoformat() if parsed.temporal_end else None,
                "entities": parsed.entities,
                "entity_synonyms": parsed.entity_synonyms,
                "expanded_query": parsed.expanded_query,
                "semantic_backend": "minilm" if not tfidf_fallback else "tfidf-fallback",
            },
        }

    # ─── Scoring helpers ────────────────────────────────────────────────

    def _entity_match_score(
        self,
        insight: str,
        history: dict,
        parsed: ParsedQuery,
    ) -> float:
        """Score how strongly the whisper matches the resolved entities.

        Returns 0.0-1.0:
          - 1.0 if the whisper's `entity` field exactly matches a resolved entity
          - 0.7 if the insight text contains a resolved entity synonym
          - 0.0 otherwise
        """
        if not parsed.entities:
            return 0.0  # No entities in query → no entity boost

        insight_lower = insight.lower()
        history_entity = (history.get("entity") or "").lower()

        # Direct entity field match (strongest)
        for ent in parsed.entities:
            if ent == history_entity:
                return 1.0
            # Also check synonyms against the entity field
            for syn in ENTITY_SYNONYMS.get(ent, []):
                if syn == history_entity:
                    return 1.0

        # Synonym appears in insight text
        for ent in parsed.entities:
            for syn in ENTITY_SYNONYMS.get(ent, []):
                if syn in insight_lower:
                    return 0.7

        return 0.0

    def _recency_score(self, last_shown_iso: str | None) -> float:
        """Score recency: 1.0 = just shown, 0.0 = 1 year ago.

        Uses exponential decay with a 30-day half-life.
        """
        if not last_shown_iso:
            return 0.0
        ts = self._parse_timestamp(last_shown_iso)
        if not ts:
            return 0.0
        days_ago = (self._now - ts).total_seconds() / 86400.0
        if days_ago < 0:
            return 1.0  # Future timestamp (clock skew) — treat as now
        # Exponential decay: 0.5 at 30 days, 0.25 at 60 days, ~0.0 at 1 year
        return max(0.0, math.exp(-days_ago / 30.0))

    def _parse_timestamp(self, ts: str | None) -> datetime | None:
        """Parse an ISO timestamp string into a datetime."""
        if not ts:
            return None
        try:
            # Handle 'Z' suffix
            if ts.endswith("Z"):
                ts = ts[:-1] + "+00:00"
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return None

    # ─── Cross-entity expansion ────────────────────────────────────────

    def _cross_entity_recall(
        self,
        parsed: ParsedQuery,
        max_items: int = 5,
    ) -> list[RecallItem]:
        """Find signals + decisions involving the resolved entities.

        This is the "graph expansion + relationship traversal" step.
        Returns RecallItems with source_type='signal' or 'decision'.

        If no entities were resolved, returns [] (no graph traversal
        without a starting node).
        """
        if not parsed.entities:
            return []

        items: list[RecallItem] = []
        for sig in self.signals:
            try:
                sig_metadata = sig.metadata if hasattr(sig, "metadata") else {}
                sig_actor = sig.actor or ""
                sig_artifact = sig.artifact or ""
                sig_text = f"{sig_artifact} {sig_metadata.get('commitment', '')} {sig_metadata.get('objection_type', '')} {sig_metadata.get('decision_outcome', '')}".strip()

                # Check if this signal involves any resolved entity
                matched_entity = None
                for ent in parsed.entities:
                    for syn in ENTITY_SYNONYMS.get(ent, []):
                        if syn.lower() in sig_text.lower() or syn.lower() == (sig_metadata.get("customer") or "").lower():
                            matched_entity = ent
                            break
                    if matched_entity:
                        break
                    # Direct customer field match
                    if sig_metadata.get("customer", "").lower() in parsed.entity_synonyms:
                        matched_entity = ent
                        break

                if not matched_entity:
                    continue

                # Determine source_type based on signal type
                sig_type_str = str(sig.type).lower() if hasattr(sig, "type") else ""
                if "decision" in sig_type_str:
                    source_type = "decision"
                else:
                    source_type = "signal"

                # Build evidence
                evidence = self._build_signal_evidence(sig, matched_entity)

                # Recency
                recency = self._recency_score(
                    sig.timestamp.isoformat() if hasattr(sig.timestamp, "isoformat") else None
                )

                items.append(RecallItem(
                    source_type=source_type,
                    source_id=getattr(sig, "signal_id", "") or f"sig-{id(sig)}",
                    text=sig_text[:200],
                    timestamp=sig.timestamp if hasattr(sig, "timestamp") else None,
                    relevance_score=0.5 + 0.5 * recency,  # Entity match + recency
                    evidence=evidence,
                ))
            except Exception as e:
                logger.debug("RecallEngine: skip signal in cross-entity: %s", e)
                continue

        # Sort by score, take top N
        items.sort(key=lambda x: x.relevance_score, reverse=True)
        return items[:max_items]

    # ─── Evidence builders ──────────────────────────────────────────────

    def _build_evidence(
        self,
        insight: str,
        history: dict,
        entity: str,
        whisper_type: str,
    ) -> Any:
        """Build a rich Evidence object for a recalled whisper.

        Per the directive's enrichment goal: source_artifacts,
        people_involved, timestamps must be populated — not just
        observed_facts.
        """
        from maestro_oem.evidence import Evidence

        # Use signal data to enrich the evidence
        signals_for_entity = self._signals_for_entity(entity)
        last_shown = history.get("last_shown", "")
        first_shown = history.get("first_shown", "")

        # Observed facts: from the whisper history + matching signals
        observed_facts: list[dict] = [{
            "source": "whisper_history",
            "date": (last_shown or "")[:10],
            "text": insight,
            "people": [],
        }]
        # Add up to 2 signal-derived facts
        for sig in signals_for_entity[:2]:
            try:
                sig_meta = sig.metadata if hasattr(sig, "metadata") else {}
                sig_text = (
                    sig_meta.get("commitment")
                    or sig_meta.get("objection_type")
                    or sig_meta.get("decision_outcome")
                    or sig.artifact
                    or ""
                )
                if sig_text:
                    observed_facts.append({
                        "source": (sig.provider.value if hasattr(sig.provider, "value") else "signal"),
                        "date": sig.timestamp.isoformat()[:10] if hasattr(sig.timestamp, "isoformat") else "",
                        "text": str(sig_text)[:120],
                        "people": [sig.actor] if sig.actor else [],
                    })
            except Exception:
                continue

        # Source artifacts — from the signal artifacts
        source_artifacts: list[dict] = []
        for sig in signals_for_entity[:1]:
            try:
                if sig.artifact:
                    source_artifacts.append({
                        "type": "signal_artifact",
                        "url": "",
                        "retrieved_at": sig.timestamp.isoformat()[:10] if hasattr(sig.timestamp, "isoformat") else "",
                        "artifact_id": sig.artifact,
                    })
            except Exception:
                continue
        # Whisper history itself is an artifact
        source_artifacts.insert(0, {
            "type": "whisper_history",
            "url": "",
            "retrieved_at": (last_shown or "")[:10],
            "artifact_id": history.get("whisper_id", ""),
        })

        # People involved — from signals
        people: list[dict] = []
        seen_people: set[str] = set()
        for sig in signals_for_entity:
            try:
                if sig.actor and sig.actor not in seen_people:
                    seen_people.add(sig.actor)
                    people.append({
                        "name": sig.actor,
                        "role": "actor",
                        "why_relevant": f"involved in {entity}" if entity else "involved",
                    })
            except Exception:
                continue

        # Timestamps
        timestamps: dict[str, str] = {
            "first_observed": (first_shown or "")[:10],
            "last_observed": (last_shown or "")[:10],
        }
        if signals_for_entity:
            try:
                latest_signal = max(
                    (s.timestamp for s in signals_for_entity if hasattr(s, "timestamp")),
                    default=None,
                )
                if latest_signal:
                    timestamps["latest_signal"] = latest_signal.isoformat()[:10]
            except Exception:
                pass

        # Build claim
        claim = insight if len(insight) <= 200 else insight[:197] + "..."

        return Evidence(
            claim=claim,
            observed_facts=observed_facts,
            source_artifacts=source_artifacts,
            people_involved=people,
            timestamps=timestamps,
            assumptions=["The whisper is still relevant to current operations"],
        )

    def _build_signal_evidence(self, sig: Any, entity: str) -> Any:
        """Build an Evidence object for a recalled signal (cross-entity)."""
        from maestro_oem.evidence import Evidence

        sig_meta = sig.metadata if hasattr(sig, "metadata") else {}
        sig_text = (
            sig_meta.get("commitment")
            or sig_meta.get("objection_type")
            or sig_meta.get("decision_outcome")
            or sig.artifact
            or "Signal recorded"
        )
        sig_date = sig.timestamp.isoformat()[:10] if hasattr(sig.timestamp, "isoformat") else ""
        sig_source = sig.provider.value if hasattr(sig.provider, "value") else "signal"

        return Evidence(
            claim=f"{entity}: {str(sig_text)[:100]}",
            observed_facts=[{
                "source": sig_source,
                "date": sig_date,
                "text": str(sig_text)[:150],
                "people": [sig.actor] if sig.actor else [],
            }],
            source_artifacts=[{
                "type": "signal",
                "url": "",
                "retrieved_at": sig_date,
                "artifact_id": sig.artifact or "",
            }],
            people_involved=[{
                "name": sig.actor,
                "role": "actor",
                "why_relevant": f"involved in {entity}",
            }] if sig.actor else [],
            timestamps={"event_date": sig_date, "last_observed": sig_date},
            assumptions=["The signal is still relevant"],
        )

    # ─── What-changed-since computation ────────────────────────────────

    def _compute_what_changed(
        self,
        whisper_last_shown: str | None,
        entity: str,
    ) -> str:
        """Compute what changed since the whisper was last shown.

        Diffs signals: any signal with timestamp AFTER whisper_last_shown,
        involving the same entity, becomes part of what_changed_since.

        Returns a NON-template string. If nothing changed, returns ""
        (caller treats empty as "no changes tracked").
        """
        if not whisper_last_shown or not entity:
            return ""

        whisper_ts = self._parse_timestamp(whisper_last_shown)
        if not whisper_ts:
            return ""

        # Find signals AFTER the whisper, involving the same entity
        new_signals: list[Any] = []
        for sig in self.signals:
            try:
                sig_ts = sig.timestamp if hasattr(sig, "timestamp") else None
                if sig_ts is None:
                    continue
                if sig_ts <= whisper_ts:
                    continue  # Not new
                # Entity match
                sig_meta = sig.metadata if hasattr(sig, "metadata") else {}
                sig_customer = (sig_meta.get("customer") or "").lower()
                if sig_customer != entity.lower():
                    continue
                new_signals.append(sig)
            except Exception:
                continue

        if not new_signals:
            return ""

        # Build a non-template description
        parts: list[str] = []
        for sig in new_signals[:3]:  # Cap at 3 to keep message readable
            try:
                sig_meta = sig.metadata if hasattr(sig, "metadata") else {}
                # Normalize signal type to a clean human-readable label
                # e.g. "SignalType.CUSTOMER_COMMITMENT_BROKEN" → "commitment broken"
                sig_type_raw = str(sig.type).lower()
                # Strip enum prefix variations: "signaltype." or "customertype." etc.
                if "." in sig_type_raw:
                    sig_type_raw = sig_type_raw.split(".")[-1]
                sig_type_str = sig_type_raw.replace("_", " ")
                # Strip leading "customer " if present (it's redundant — we already know it's the customer)
                if sig_type_str.startswith("customer "):
                    sig_type_str = sig_type_str[len("customer "):]
                sig_date = sig.timestamp.isoformat()[:10] if hasattr(sig.timestamp, "isoformat") else ""

                if "commitment broken" in sig_type_str:
                    parts.append(f"Commitment broken on {sig_date}")
                elif "commitment kept" in sig_type_str:
                    parts.append(f"Commitment kept on {sig_date}")
                elif "objection" in sig_type_str:
                    obj_type = sig_meta.get("objection_type", "")
                    parts.append(f"New objection raised on {sig_date}: {obj_type}" if obj_type else f"New objection on {sig_date}")
                elif "decision" in sig_type_str:
                    outcome = sig_meta.get("decision_outcome", "")
                    parts.append(f"Decision made on {sig_date}: {outcome}" if outcome else f"New decision on {sig_date}")
                elif "churn" in sig_type_str:
                    parts.append(f"Customer churned on {sig_date}")
                elif "champion quiet" in sig_type_str:
                    parts.append(f"Champion went quiet on {sig_date}")
                else:
                    parts.append(f"New {sig_type_str} on {sig_date}")
            except Exception:
                continue

        if not parts:
            return ""

        if len(parts) == 1:
            return parts[0] + "."
        return "; ".join(parts) + "."

    # ─── Helpers ────────────────────────────────────────────────────────

    def _signals_for_entity(self, entity: str) -> list[Any]:
        """Find all signals involving the given entity."""
        if not entity or not self.signals:
            return []
        entity_lower = entity.lower()
        matched: list[Any] = []
        for sig in self.signals:
            try:
                sig_meta = sig.metadata if hasattr(sig, "metadata") else {}
                sig_customer = (sig_meta.get("customer") or "").lower()
                if sig_customer == entity_lower:
                    matched.append(sig)
            except Exception:
                continue
        return matched

    def _recall_item_to_whisper_dict(self, item: RecallItem) -> dict[str, Any]:
        """Convert a RecallItem to the legacy 'whispers' array shape.

        Backward compatibility: the old WhisperRecall returned
        {whisper_id, original_insight, executive_action, shown_count,
         first_shown, last_shown, matched_keywords, what_changed}
        Consumers (frontend, /ask/conversation recall branch) expect this.
        """
        evidence_dict = item.evidence.to_dict() if hasattr(item.evidence, "to_dict") else {}
        return {
            "whisper_id": item.source_id,
            "original_insight": item.text,
            "executive_action": None,  # Not in store shape — would need DB schema change
            "shown_count": 0,  # Same as above
            "first_shown": item.timestamp.isoformat() if item.timestamp else None,
            "last_shown": item.timestamp.isoformat() if item.timestamp else None,
            "matched_keywords": [],  # Replaced by relevance_score
            "what_changed": item.what_changed,
            "relevance_score": item.relevance_score,
            "evidence_spine": evidence_dict,
        }

    def _build_recall_message(
        self,
        top_whispers: list[RecallItem],
        query: str,
        found: bool,
    ) -> str:
        """Build a conversational recall message."""
        if not found or not top_whispers:
            return (
                "I couldn't find anything matching that description. "
                "Try mentioning a person, customer, or topic."
            )
        w = top_whispers[0]
        parts = ["I think this is what you remember.", ""]
        parts.append(f"On a previous occasion, I surfaced: {w.text}")
        if w.what_changed:
            parts.append("")
            parts.append(f"What changed since: {w.what_changed}")
        return "\n".join(parts)

    def _empty_result(self, query: str) -> dict[str, Any]:
        return {
            "query": query,
            "found": False,
            "match_count": 0,
            "whispers": [],
            "items": [],
            "message": "Empty query — nothing to recall.",
            "parsed_query": {},
        }

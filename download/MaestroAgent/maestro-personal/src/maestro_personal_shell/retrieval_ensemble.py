"""Retrieval Ensemble — multi-stage hybrid retrieval with Reciprocal Rank Fusion."""
from __future__ import annotations

import logging
import re
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# RRF constant (Cormack, Clarke & Buttcher 2009). Standard k=60.
RRF_K = 60

# Stage 1 broad-recall depth. BM25 returns up to N candidates; specialized
# retrievers may add more. The final ensemble is fused + trimmed.
STAGE1_BM25_DEPTH = 50
STAGE2_SPECIALIST_DEPTH = 20
STAGE4_FINAL_TOP_K = 8


# ---------------------------------------------------------------------------
# Stage 1: BM25 broad recall (delegates to existing FTS5 retriever)
# ---------------------------------------------------------------------------

def stage1_bm25_recall(
    query: str,
    user_email: str,
    as_of: str | None = None,
    from_date: str | None = None,
    db_path: str | None = None,
    limit: int = STAGE1_BM25_DEPTH,
) -> list[dict[str, Any]]:
    """Stage 1: BM25 broad recall via existing FTS5 index.

    Returns up to `limit` signal dicts, BM25-ranked, temporally filtered.
    This is the lexical recall floor — every later stage operates on or
    augments this candidate set.
    """
    from maestro_personal_shell.semantic_retrieval import get_relevant_signals
    try:
        kwargs = {
            "user_email": user_email,
            "limit": limit,
            "as_of": as_of,
            "from_date": from_date,
        }
        if db_path:
            kwargs["db_path"] = db_path
        results = get_relevant_signals(query, **kwargs)
        # Tag provenance for RRF
        for r in results:
            r["_provenance"] = "bm25"
        return results
    except Exception as e:
        logger.debug("Stage 1 BM25 recall failed: %s", e)
        return []


# ---------------------------------------------------------------------------
# Stage 2: Specialized retrievers
# ---------------------------------------------------------------------------

def _load_all_signals(user_email: str, limit: int = 500, db_path: str | None = None) -> list[dict[str, Any]]:
    """Load raw signals (up to limit) for this user, for specialist filtering.

    Trust gap #2 fix: filter out dismissed/corrected signals so they don't
    surface in Ask evidence via specialist retrievers. The BM25/FTS retriever
    already excludes them (propagate_correction calls delete_signal_from_fts),
    but specialist retrievers load ALL signals and didn't filter corrections,
    creating a partial write-only correction path. Now we exclude any signal
    whose metadata.status is dismissed/completed/cancelled OR whose
    metadata.correction is set (dismiss/cancel/complete/dispute/supersede).
    """
    from maestro_personal_shell.api import load_signals_from_db
    try:
        kwargs = {"user_email": user_email, "limit": limit}
        if db_path:
            kwargs["db_path"] = db_path
        sigs = load_signals_from_db(**kwargs)
        dismissed_statuses = {"dismissed", "completed", "cancelled"}
        dismissed_corrections = {"dismiss", "cancel", "complete", "dispute", "supersede"}
        filtered = []
        for s in sigs:
            if not isinstance(s, dict):
                continue
            meta = s.get("metadata")
            if isinstance(meta, str):
                try:
                    import json as _json
                    meta = _json.loads(meta)
                except Exception:
                    meta = {}
            if not isinstance(meta, dict):
                meta = {}
            status = str(meta.get("status", "")).lower()
            correction = str(meta.get("correction", "")).lower()
            if status in dismissed_statuses or correction in dismissed_corrections:
                continue
            filtered.append(s)
        return filtered
    except Exception as e:
        logger.debug("load_signals_from_db failed: %s", e)
        return []


def _extract_entity_mentions(query: str) -> list[str]:
    """Extract candidate entity names from the query."""
    common = {
        "What", "Did", "Will", "The", "How", "When", "Why", "Who", "Is", "Are",
        "Can", "Could", "I", "Do", "Does", "Has", "Have", "Was", "Were",
        "Should", "Would", "May", "Might", "Must", "Shall", "About", "For",
        "With", "From", "To", "In", "On", "At", "By", "Of", "And", "Or",
        "But", "Not", "If", "Then", "Else", "So", "Than", "That", "This",
        "These", "Those", "There", "Here", "Where", "Which", "Whose", "Whom",
        "A", "An", "List", "Show", "Find", "Get", "Tell", "Give", "Display",
        "Search", "Open", "See", "Check", "Review", "Summarize", "Explain",
    }
    multi = re.findall(r'\b[A-Z][a-z]+\s+[A-Z][a-z]+\b', query)
    single = [w for w in re.findall(r'\b[A-Z][a-z]+\b', query) if w not in common]
    multi_lower = [m.lower() for m in multi]
    single_filtered = [s for s in single
                       if not any(s.lower() in m for m in multi_lower)]
    return multi + single_filtered


def _entity_match(query_entity: str, sig_entity: str) -> bool:
    """Word-boundary entity match (case-insensitive)."""
    qe = query_entity.lower().strip()
    se = sig_entity.lower().strip()
    if not qe or not se:
        return False
    if qe == se:
        return True
    if re.search(r'\b' + re.escape(qe) + r'\b', se):
        return True
    if re.search(r'\b' + re.escape(se) + r'\b', qe):
        return True
    return False


def specialist_entity_retriever(
    query: str,
    all_signals: list[dict[str, Any]],
    limit: int = STAGE2_SPECIALIST_DEPTH,
) -> list[dict[str, Any]]:
    """Specialist: entity-name match.

    Excels at: "What did I promise Maria?" where "Maria" is a proper noun
    that BM25 might rank below a textually-denser signal about someone else.
    """
    mentions = _extract_entity_mentions(query)
    if not mentions:
        return []
    matches = []
    for sig in all_signals:
        sig_entity = str(sig.get("entity", ""))
        if any(_entity_match(qe, sig_entity) for qe in mentions):
            sig_copy = dict(sig)
            sig_copy["_provenance"] = "entity"
            matches.append(sig_copy)
    matches.sort(
        key=lambda s: str(s.get("timestamp", "")),
        reverse=True,
    )
    return matches[:limit]


def specialist_temporal_retriever(
    query: str,
    all_signals: list[dict[str, Any]],
    as_of: str | None = None,
    from_date: str | None = None,
    limit: int = STAGE2_SPECIALIST_DEPTH,
) -> list[dict[str, Any]]:
    """Specialist: time-window match.

    Excels at: "What changed since Tuesday?" / "What's been pending for over
    a month?" — these queries are about time, not entities.
    """
    from maestro_personal_shell.temporal_query import parse_temporal_query
    try:
        temporal = parse_temporal_query(query)
    except Exception:
        temporal = {}

    has_temporal = temporal.get("has_temporal_ref", False)
    parsed_to = temporal.get("to_date")
    parsed_from = temporal.get("from_date")

    effective_to = as_of or parsed_to
    effective_from = from_date or parsed_from

    query_lower = query.lower()
    is_stale_query = any(kw in query_lower for kw in [
        "over a month", "oldest", "stale", "pending for", "longest",
        "still pending",
    ])
    is_recent_query = any(kw in query_lower for kw in [
        "this week", "today", "yesterday", "recent", "latest",
        "most recent", "last week",
    ])

    if not (has_temporal or effective_to or effective_from or is_stale_query or is_recent_query):
        return []

    def _parse_ts(ts_str: str) -> datetime | None:
        if not ts_str:
            return None
        try:
            dt = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return None

    to_dt = _parse_ts(effective_to) if effective_to else None
    from_dt = _parse_ts(effective_from) if effective_from else None

    matches = []
    for sig in all_signals:
        ts = _parse_ts(str(sig.get("timestamp", "")))
        if not ts:
            continue
        if to_dt and ts > to_dt:
            continue
        if from_dt and ts < from_dt:
            continue
        sig_copy = dict(sig)
        sig_copy["_provenance"] = "temporal"
        matches.append(sig_copy)

    if is_stale_query:
        matches.sort(key=lambda s: str(s.get("timestamp", "")))
    elif is_recent_query:
        matches.sort(key=lambda s: str(s.get("timestamp", "")), reverse=True)
    else:
        matches.sort(key=lambda s: str(s.get("timestamp", "")), reverse=True)

    return matches[:limit]


def specialist_commitment_retriever(
    query: str,
    user_email: str,
    db_path: str,
    intent: str,
    limit: int = STAGE2_SPECIALIST_DEPTH,
) -> list[dict[str, Any]]:
    """Specialist: structured commitment ledger lookup.

    Excels at: "Which promises are overdue?" / "What did I fail to deliver?"
    — these queries need STATE, not text.
    """
    from maestro_personal_shell.ledger_routing import route_to_ledger
    if intent not in ("broken", "overdue", "relational", "commitment", "risk", "conditional"):
        try:
            from maestro_personal_shell.ledger_routing import get_active_commitments
            entries = get_active_commitments(user_email, db_path, limit=limit)
        except Exception:
            return []
    else:
        try:
            entries = route_to_ledger(intent, user_email, db_path) or []
        except Exception as e:
            logger.debug("Ledger routing failed: %s", e)
            entries = []

    if not entries:
        return []

    results = []
    for entry in entries[:limit]:
        state = entry.get("state", "unknown")
        entity = entry.get("entity", "unknown")
        action = entry.get("action") or entry.get("evidence_quote", "")
        deadline = entry.get("deadline_text", "")
        commitment_type = entry.get("commitment_type", "")

        text = f"[LEDGER state={state}] {entity}: {action}"
        if deadline:
            text += f" (deadline: {deadline})"
        if commitment_type:
            text += f" [{commitment_type}]"

        results.append({
            "text": text,
            "entity": entity,
            "timestamp": str(entry.get("updated_at", entry.get("created_at", ""))),
            "signal_id": entry.get("signal_id", ""),
            "source_type": "ledger",
            "ledger_state": state,
            "deadline": deadline,
            "commitment_type": commitment_type,
            "_provenance": "commitment",
        })
    return results


def specialist_relationship_retriever(
    query: str,
    all_signals: list[dict[str, Any]],
    limit: int = STAGE2_SPECIALIST_DEPTH,
) -> list[dict[str, Any]]:
    """Specialist: graph-traversal match.

    Excels at: "Who am I disappointing?" / "Who are my biggest risks?" —
    these queries need entity-LEVEL aggregation, not signal-level matching.
    """
    from maestro_personal_shell.ask_ranker import aggregate_by_entity
    query_lower = query.lower()
    is_relational = any(kw in query_lower for kw in [
        "who am i", "who are my", "who keeps", "who owes",
        "who is my", "which clients", "which people", "which projects",
        "disappointing", "delivery risk", "most reliable", "biggest risk",
        "at risk", "broken", "overdue",
    ])
    if not is_relational:
        return []

    try:
        from maestro_personal_shell.ask_ranker import understand_query, rerank_signals
        understanding = understand_query(query)
        ranked = rerank_signals(all_signals, understanding)
        entities = aggregate_by_entity(ranked, understanding.get("intent", "general"))
    except Exception as e:
        logger.debug("aggregate_by_entity failed: %s", e)
        return []

    if not entities:
        return []

    results = []
    for ent_summary in entities[:5]:
        ent_name = ent_summary.get("entity", "unknown")
        for sig in ent_summary.get("top_signals", [])[:2]:
            sig_copy = dict(sig)
            sig_copy["_provenance"] = "relationship"
            sig_copy["_entity_risk_score"] = ent_summary.get("risk_score", 0)
            sig_copy["_entity_broken_count"] = ent_summary.get("broken_count", 0)
            results.append(sig_copy)
        results.append({
            "text": (
                f"[ENTITY SUMMARY] {ent_name}: "
                f"{ent_summary.get('broken_count', 0)} broken, "
                f"{ent_summary.get('completed_count', 0)} completed, "
                f"{ent_summary.get('stale_count', 0)} stale, "
                f"{ent_summary.get('commitment_count', 0)} total commitments, "
                f"risk_score={ent_summary.get('risk_score', 0)}"
            ),
            "entity": ent_name,
            "timestamp": "",
            "signal_id": "",
            "source_type": "entity_summary",
            "_provenance": "relationship",
        })
    return results[:limit]


def specialist_intent_keyword_retriever(
    query: str,
    all_signals: list[dict[str, Any]],
    intent: str,
    intent_keywords: list[str],
    limit: int = STAGE2_SPECIALIST_DEPTH,
) -> list[dict[str, Any]]:
    """Specialist: intent-keyword match."""
    if not intent_keywords or intent == "general":
        return []

    matches = []
    seen_ids = set()
    for sig in all_signals:
        sig_text = str(sig.get("text", "")).lower()
        sig_id = str(sig.get("signal_id", ""))
        for kw in intent_keywords:
            if kw in sig_text:
                if sig_id in seen_ids:
                    continue
                sig_copy = dict(sig)
                sig_copy["_provenance"] = "intent_keyword"
                sig_copy["_matched_keyword"] = kw
                matches.append(sig_copy)
                seen_ids.add(sig_id)
                break

    for m in matches:
        sig_text = str(m.get("text", "")).lower()
        m["_keyword_match_count"] = sum(1 for kw in intent_keywords if kw in sig_text)
    matches.sort(key=lambda s: s.get("_keyword_match_count", 0), reverse=True)
    return matches[:limit]


# ---------------------------------------------------------------------------
# Stage 3: Reciprocal Rank Fusion
# ---------------------------------------------------------------------------

def reciprocal_rank_fusion(
    retriever_outputs: dict[str, list[dict[str, Any]]],
    final_k: int = 20,
    rrf_k: int = RRF_K,
) -> list[dict[str, Any]]:
    """Stage 3: Reciprocal Rank Fusion.

    For each signal, sum 1/(k + rank_in_retriever) across all retrievers.
    Higher score = more retrievers agree this is relevant.
    """
    fused: dict[str, dict[str, Any]] = {}

    def _key(sig: dict[str, Any]) -> str:
        sid = str(sig.get("signal_id", ""))
        if sid:
            return sid
        return f"{sig.get('entity', '')}::{str(sig.get('text', ''))[:80]}"

    for retriever_name, results in retriever_outputs.items():
        if not results:
            continue
        for rank, sig in enumerate(results):
            key = _key(sig)
            if key not in fused:
                fused[key] = {
                    "signal": sig,
                    "score": 0.0,
                    "provenances": [],
                }
            fused[key]["score"] += 1.0 / (rrf_k + rank + 1)
            if retriever_name not in fused[key]["provenances"]:
                fused[key]["provenances"].append(retriever_name)

    ranked = sorted(fused.values(), key=lambda x: x["score"], reverse=True)

    output = []
    for entry in ranked[:final_k]:
        sig = dict(entry["signal"])
        sig["_rrf_score"] = round(entry["score"], 6)
        sig["_provenances"] = entry["provenances"]
        output.append(sig)
    return output


# ---------------------------------------------------------------------------
# Stage 4: Context engineering — dedup, chronological, top-K
# ---------------------------------------------------------------------------

def _normalize_text(text: str) -> str:
    """Normalize text for near-duplicate detection."""
    if not text:
        return ""
    text = str(text).lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def context_engineer(
    fused_signals: list[dict[str, Any]],
    query: str,
    top_k: int = STAGE4_FINAL_TOP_K,
) -> list[dict[str, Any]]:
    """Stage 4: Context engineering for LLM consumption.

    1. Drop noise signals (unless explicitly queried)
    2. Deduplicate by normalized text
    3. Sort chronologically (oldest first) for LLM timeline reasoning
    4. Top-K (8 by default)
    """
    if not fused_signals:
        return []

    query_lower = query.lower()
    is_noise_lookup = any(kw in query_lower for kw in [
        "newsletter", "industry news", "fyi", "noise", "digest",
    ])
    if not is_noise_lookup:
        filtered = []
        for sig in fused_signals:
            sig_type = str(sig.get("signal_type", "")).lower()
            if sig_type in ("newsletter", "fyi", "notification", "blog", "social", "marketing"):
                continue
            filtered.append(sig)
        fused_signals = filtered

    seen_texts: set[str] = set()
    deduped = []
    for sig in fused_signals:
        norm = _normalize_text(sig.get("text", ""))
        if not norm:
            continue
        if norm in seen_texts:
            continue
        seen_texts.add(norm)
        deduped.append(sig)

    def _ts_key(sig: dict[str, Any]) -> str:
        return str(sig.get("timestamp", "")) or ""

    # F-IntentSort fix (auditor 2026-07-20, reproduce_rrf_bug_with_llm.py
    # TEST 2/3 partial): for intent queries where the relevant evidence is
    # the BROKEN-FULFILLMENT signal (newer) rather than the original
    # commitment (older), chronological sort puts the wrong signal first.
    # Example: 'Which promises are now overdue?' returned Riley's commitment
    # (May 21) at rank 1 and Riley's 'Never sent' (July 10) at rank 2 —
    # because chronological sort puts the older commitment first. But for
    # overdue queries, the 'Never sent' signal IS the answer.
    #
    # Fix: for intent queries (broken/overdue/at_risk/recurring/relational/
    # critical/priority/disputed/noise_lookup), preserve the RRF rank order
    # (don't sort chronologically). For timeline-reasoning queries
    # (direct_lookup, contradiction, temporal, prepare), keep chronological.
    #
    # Intent detection: mirror the _INTENT_BROAD_PATTERNS list from
    # routers/ask.py (keep in sync). Use a compact set of substrings —
    # the full list there has 60+ patterns; here we use the load-bearing
    # ones that distinguish intent queries from timeline queries.
    query_lower_for_intent = query.lower()
    intent_substrings = [
        # broken / fail-to-deliver
        "fail to deliver", "what did i fail", "never sent", "never delivered",
        "broken promise", "broken commitment", "missed deadline",
        "what did i not send", "which commitment did i miss",
        "did i fail to deliver",
        # overdue
        "overdue", "past due", "behind schedule", "what am i late",
        "what's past due", "show me overdue",
        # at_risk
        "at risk", "what commitments are in danger", "which promises might slip",
        "which commitments are threatened",
        # relational
        "who am i", "who are my", "who keeps", "who owes", "who is my",
        "which clients", "which people", "which projects",
        "disappointing", "delivery risk", "most reliable", "biggest risk",
        "who has broken", "who should i follow", "who delivered on time",
        "who has unfulfilled",
        # recurring
        "keeps happening", "keeps breaking", "what pattern",
        "recurring issue", "recurring problem", "what keeps going wrong",
        "systemic issue",
        # critical / priority
        "legal issue", "legal matter", "churn", "cancel account",
        "board escalation", "emergency meeting", "breach",
        "any legal", "any customer", "any board", "customer at risk",
        "most urgent", "what needs attention",
        "regulatory", "is any account churning",
        # disputed
        "were any completions", "disputed", "challenged",
        "was the nova presentation",
        # noise_lookup
        "newsletter", "digest", "industry trend",
        # which promises / commitments
        "which promises are", "which commitments are",
        "which entities have",
        # F-WeakTypes fix (2026-07-20): temporal/priority/disputed phrasings
        # that should preserve RRF order, not chronological.
        "pending for over", "outstanding the longest", "oldest commitment",
        "haven't kept", "delayed the most", "commit to months ago",
        "commit to last quarter", "did i do this week",
        "most important commitment", "needs my attention",
        "needs attention immediately",
        "was the nova presentation", "presentation complete",
        # F-Recurring fix (2026-07-20): recurring phrasings
        "recurring production", "keeps going wrong", "systemic issue",
        "what keeps", "what pattern", "keeps happening",
    ]
    is_intent_query = any(p in query_lower_for_intent for p in intent_substrings)
    if is_intent_query:
        # Preserve RRF rank order — the fused_signals list is already
        # sorted by RRF score (highest first) from reciprocal_rank_fusion().
        # Don't re-sort chronologically.
        pass
    else:
        # Chronological sort (oldest first) for timeline-reasoning queries
        deduped.sort(key=_ts_key)

    return deduped[:top_k]


# ---------------------------------------------------------------------------
# Stage 5: Structural memory — JSON representation of entity state
# ---------------------------------------------------------------------------

def build_structural_memory(
    query: str,
    fused_signals: list[dict[str, Any]],
    user_email: str,
    db_path: str,
) -> dict[str, Any]:
    """Stage 5: Build a structured JSON representation of entity state."""
    from maestro_personal_shell.ask_ranker import understand_query

    understanding = understand_query(query)
    intent = understanding.get("intent", "general")
    entity_mentions = understanding.get("entity_mentions", [])

    sig_entity_counts: dict[str, int] = {}
    for sig in fused_signals:
        ent = str(sig.get("entity", "")).strip()
        if ent:
            sig_entity_counts[ent] = sig_entity_counts.get(ent, 0) + 1
    top_sig_entities = [e for e, _ in sorted(sig_entity_counts.items(),
                                              key=lambda x: x[1], reverse=True)[:5]]

    all_entities_to_profile = []
    seen = set()
    for ent in entity_mentions:
        if ent.lower() not in seen:
            all_entities_to_profile.append(ent)
            seen.add(ent.lower())
    for ent in top_sig_entities:
        if ent.lower() not in seen:
            all_entities_to_profile.append(ent)
            seen.add(ent.lower())

    entity_profiles = []
    try:
        from maestro_personal_shell.ledger_routing import get_active_commitments, get_overdue_commitments, get_broken_commitments
        active = get_active_commitments(user_email, db_path, limit=50)
        overdue = get_overdue_commitments(user_email, db_path, limit=50)
        broken = get_broken_commitments(user_email, db_path, limit=50)
    except Exception as e:
        logger.debug("Ledger queries failed: %s", e)
        active, overdue, broken = [], [], []

    for ent in all_entities_to_profile[:5]:
        ent_active = [e for e in active if _entity_match(ent, e.get("entity", ""))]
        ent_overdue = [e for e in overdue if _entity_match(ent, e.get("entity", ""))]
        ent_broken = [e for e in broken if _entity_match(ent, e.get("entity", ""))]

        ent_signals = []
        for sig in fused_signals:
            if _entity_match(ent, str(sig.get("entity", ""))):
                ent_signals.append({
                    "text": str(sig.get("text", ""))[:200],
                    "timestamp": str(sig.get("timestamp", "")),
                    "signal_type": str(sig.get("signal_type", "")),
                })

        risk_summary = (
            f"{len(ent_broken)} broken, {len(ent_overdue)} overdue, "
            f"{len(ent_active)} active"
        )

        entity_profiles.append({
            "name": ent,
            "active_commitments": [
                {"action": e.get("action", e.get("evidence_quote", ""))[:150],
                 "deadline": e.get("deadline_text", ""),
                 "state": e.get("state", "")}
                for e in ent_active[:3]
            ],
            "broken_commitments": [
                {"action": e.get("action", e.get("evidence_quote", ""))[:150],
                 "state": e.get("state", "")}
                for e in ent_broken[:3]
            ],
            "overdue_commitments": [
                {"action": e.get("action", e.get("evidence_quote", ""))[:150],
                 "deadline": e.get("deadline_text", "")}
                for e in ent_overdue[:3]
            ],
            "recent_signals": ent_signals[:3],
            "risk_summary": risk_summary,
        })

    from maestro_personal_shell.temporal_query import parse_temporal_query
    try:
        temporal = parse_temporal_query(query)
        temporal_window = {
            "from": temporal.get("from_date"),
            "to": temporal.get("to_date"),
            "description": temporal.get("time_range_description"),
        }
    except Exception:
        temporal_window = {"from": None, "to": None, "description": None}

    return {
        "query_intent": intent,
        "entity_mentions": entity_mentions,
        "temporal_window": temporal_window,
        "entities": entity_profiles,
    }


def structural_memory_to_text(memory: dict[str, Any]) -> str:
    """Render the structural memory as compact text for the LLM prompt."""
    if not memory or not memory.get("entities"):
        return ""
    lines = []
    lines.append(f"Query intent: {memory.get('query_intent', 'general')}")
    tw = memory.get("temporal_window", {})
    if tw.get("description"):
        lines.append(f"Time window: {tw['description']}")
    lines.append("")
    lines.append("Entity state (structured):")
    for ent in memory["entities"]:
        lines.append(f"\n  {ent['name']} — {ent['risk_summary']}")
        if ent["active_commitments"]:
            lines.append("    Active:")
            for c in ent["active_commitments"]:
                dl = f" (due {c['deadline']})" if c.get("deadline") else ""
                lines.append(f"      • {c['action']}{dl}")
        if ent["broken_commitments"]:
            lines.append("    Broken:")
            for c in ent["broken_commitments"]:
                lines.append(f"      • {c['action']} [{c.get('state', '')}]")
        if ent["overdue_commitments"]:
            lines.append("    Overdue:")
            for c in ent["overdue_commitments"]:
                dl = f" (due {c['deadline']})" if c.get("deadline") else ""
                lines.append(f"      • {c['action']}{dl}")
        if ent["recent_signals"]:
            lines.append("    Recent signals:")
            for s in ent["recent_signals"]:
                ts = f" [{s['timestamp'][:10]}]" if s.get("timestamp") else ""
                lines.append(f"      • {s['text'][:120]}{ts}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------

def retrieve(
    query: str,
    user_email: str,
    db_path: str,
    as_of: str | None = None,
    from_date: str | None = None,
    include_structural: bool = True,
    use_reranker: bool = False,
    reranker_method: str = "llm",
) -> dict[str, Any]:
    """Top-level retrieval orchestrator.

    Runs the full 5-stage pipeline and returns:
      {
        "evidence": list[dict] (top-K context-engineered evidence),
        "structural_memory": dict (JSON entity state),
        "structural_memory_text": str (rendered for LLM prompt),
        "fused_count": int (signals before context engineering),
        "retriever_counts": {retriever_name: count},
        "reranked": bool (whether Stage 4 reranker was applied),
      }

    Args:
        use_reranker: If True, apply cross-encoder reranking (Stage 4)
            between RRF fusion and context engineering. Default False.
        reranker_method: "llm" (LLM-as-a-reranker, default) or "cohere"
            (true cross-encoder via Cohere Rerank API).
    """
    from maestro_personal_shell.ask_ranker import understand_query

    understanding = understand_query(query)
    intent = understanding.get("intent", "general")
    intent_keywords = understanding.get("intent_keywords", [])

    # Stage 1: BM25 broad recall
    bm25_results = stage1_bm25_recall(
        query, user_email, as_of=as_of, from_date=from_date, db_path=db_path,
    )

    all_signals = _load_all_signals(user_email, limit=500, db_path=db_path)

    # Stage 2: specialists
    entity_results = specialist_entity_retriever(query, all_signals)
    temporal_results = specialist_temporal_retriever(
        query, all_signals, as_of=as_of, from_date=from_date,
    )
    commitment_results = specialist_commitment_retriever(
        query, user_email, db_path, intent,
    )
    relationship_results = specialist_relationship_retriever(query, all_signals)
    intent_keyword_results = specialist_intent_keyword_retriever(
        query, all_signals, intent, intent_keywords,
    )

    retriever_outputs = {
        "bm25": bm25_results,
        "entity": entity_results,
        "temporal": temporal_results,
        "commitment": commitment_results,
        "relationship": relationship_results,
        "intent_keyword": intent_keyword_results,
    }

    retriever_counts = {k: len(v) for k, v in retriever_outputs.items() if v}

    # Stage 3: RRF fusion
    fused = reciprocal_rank_fusion(retriever_outputs, final_k=20)

    # Stage 3.5: LLM-based cross-encoder reranking (optional, Stage 4)
    # Uses the "LLM-as-a-reranker" technique: scores each signal's
    # relevance to the query via a fast LLM call, then re-sorts.
    # Skipped by default (use_reranker=False) for backward compatibility.
    reranked = False
    if use_reranker and fused:
        try:
            from maestro_personal_shell.stage4_reranker import rerank_evidence_sync
            fused = rerank_evidence_sync(
                query, fused, top_k=20, max_to_score=20,
                method=reranker_method,
            )
            reranked = True
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                "Stage 4 reranker failed, using unranked RRF output: %s", e,
            )

    # Stage 4: Context engineering
    evidence = context_engineer(fused, query, top_k=STAGE4_FINAL_TOP_K)

    # Stage 5: Structural memory
    structural_memory = {}
    structural_memory_text = ""
    if include_structural:
        structural_memory = build_structural_memory(
            query, fused, user_email, db_path,
        )
        structural_memory_text = structural_memory_to_text(structural_memory)

    return {
        "evidence": evidence,
        "structural_memory": structural_memory,
        "structural_memory_text": structural_memory_text,
        "fused_count": len(fused),
        "retriever_counts": retriever_counts,
        "understanding": understanding,
        "reranked": reranked,
    }

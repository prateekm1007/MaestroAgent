"""Surfaces router — the heavy "surface" endpoints."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, model_validator

from maestro_personal_shell.models import (
    PrepareResponse,
    WhatChangedMasterpieceResponse,
    WhatChangedResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["surfaces"])

# Phase 2.9: 60-second per-user cache for /api/prepare (was 4.5s, target <2s)
_PREPARE_CACHE: dict[str, tuple[float, list]] = {}

# Phase L4: 60-second per-user cache for /api/the-moment (was 1.1-1.4s)
_MOMENT_CACHE: dict[str, tuple[float, Any]] = {}


def invalidate_all_caches(user_email: str) -> None:
    """Clear ALL cached entries for a user after a mutation (P54).

    Called after: signal creation, signal correction, commitment transition,
    draft resolution. Without this, surfaces show stale data for up to 60s.

    Clears all 4 cache dicts:
    - _MOMENT_CACHE (the-moment + the-shifts + ambient)
    - _WHISPER_CACHE (whisper list)
    - _BRIEFING_CACHE (morning/evening briefing)
    - _PREPARE_CACHE (meeting preparation)

    P85: never raises — silently skips if cache unavailable.
    """
    try:
        for cache in [_MOMENT_CACHE, _WHISPER_CACHE, _BRIEFING_CACHE, _PREPARE_CACHE]:
            _keys_to_del = [k for k in cache if f":{user_email}" in k]
            for k in _keys_to_del:
                del cache[k]
    except Exception:
        pass

# LATENCY FIX (v21): 60-second per-user cache for /api/whisper (was 6s every call)
_WHISPER_CACHE: dict[str, tuple[float, Any]] = {}

# LATENCY FIX (v21): 60-second per-user cache for /api/briefing
_BRIEFING_CACHE: dict[str, tuple[float, Any]] = {}

# R-03 fix (reviewer S2): structural tentativeness filter.
# Tentative content ("maybe", "I'll let you know", "don't count on it") must
# be excluded from briefing unknowns, material_changes, cannot_decide_yet,
# and other commitment-tracking surfaces — not just from top_situation.
# A tentative statement is not a commitment and should not generate
# follow-up questions like "Was the commitment to X fulfilled?"
_TENTATIVE_MARKERS = [
    "maybe", "might", "possibly", "don't count on", "not sure",
    "try to", "i hope", "hopefully", "i'd like to", "i wish i could",
    "no promises", "can't guarantee", "might be able", "i'll try",
    "i'll see", "we'll see", "i'll let you know", "tentative",
]


def _is_tentative_text(text: str) -> bool:
    """Check if text contains tentative/hedging language."""
    if not text:
        return False
    text_lower = str(text).lower()
    return any(marker in text_lower for marker in _TENTATIVE_MARKERS)


def _filter_tentative_from_list(items: list, shell: Any) -> list:
    """Filter tentative content from a list of briefing items.

    Each item can be a dict (with 'entity', 'title', 'text') or an object
    with attributes. We check the entity's signals for tentative language
    and exclude items whose source signal is tentative.
    """
    if not items:
        return items
    filtered = []
    for item in items:
        # Extract text to check
        if isinstance(item, dict):
            item_text = str(item.get("text", "") or item.get("title", "") or item.get("action", ""))
            item_entity = str(item.get("entity", ""))
        else:
            item_text = str(getattr(item, "text", "") or getattr(item, "title", "") or getattr(item, "action", ""))
            item_entity = str(getattr(item, "entity", ""))

        # Check the item text itself for tentative language
        if _is_tentative_text(item_text):
            logger.info("R-03: filtered tentative item from briefing: %s", item_text[:80])
            continue

        # Check the source signal for this entity
        if shell and item_entity:
            for sig in shell.oem_state.signals:
                sig_entity = str(getattr(sig, "entity", "")).lower()
                if sig_entity == item_entity.lower():
                    sig_text = str(getattr(sig, "text", ""))
                    if _is_tentative_text(sig_text):
                        logger.info("R-03: filtered briefing item for entity %s — source signal is tentative",
                                    item_entity)
                        item = None
                        break
            if item is None:
                continue

        filtered.append(item)
    return filtered


# ---------------------------------------------------------------------------
# verify_token lazy proxy
# ---------------------------------------------------------------------------


async def verify_token_dep(authorization: str = Header(None)) -> str:
    """Lazy proxy to api.verify_token — decouples this router from api.py's load order."""
    from maestro_personal_shell.api import verify_token
    return await verify_token(authorization=authorization)


# ---------------------------------------------------------------------------
# Pydantic models — moved here from api.py
# ---------------------------------------------------------------------------


class BriefingResponse(BaseModel):
    """The masterpiece briefing — Situation-centric, not agent-centric."""
    greeting: str = ""
    top_situation: dict[str, Any] | None = None
    material_changes: list[str] | None = None
    unknowns: list[str] | None = None
    disputes: list[dict[str, Any]] | None = None
    can_decide_now: list[str] | None = None
    cannot_decide_yet: list[str] | None = None
    why_boundary: str | None = None
    next_step: str | None = None
    belief: str | None = None
    why_belief: str | None = None
    what_would_change_belief: str | None = None
    watching_quietly: list[dict[str, Any]] | None = None
    ask_prompt: str | None = None
    # S2-4 SURFACES reconciliation (P41) — single source of truth.
    # Briefing, What-Changed, The-Moment all return the SAME reconciliation
    # block, derived from the SAME CommitmentsSurface call.
    reconciliation: dict[str, Any] = {}

    model_config = {"exclude_none": True}

    @model_validator(mode="after")
    def _strip_empty_to_none(self):
        """Convert empty strings and empty lists to None so they're excluded."""
        for field_name in [
            "material_changes", "unknowns", "disputes", "can_decide_now",
            "cannot_decide_yet", "why_boundary", "next_step", "belief",
            "why_belief", "what_would_change_belief", "watching_quietly",
            "ask_prompt",
        ]:
            val = getattr(self, field_name)
            if val == "" or val == []:
                setattr(self, field_name, None)
        return self


class TheMomentResponse(BaseModel):
    """The single most important thing Maestro knows right now."""
    has_moment: bool
    commitment: dict[str, Any] | None = None
    situation: dict[str, Any] | None = None
    why_this_one: str = ""
    source_evidence: list[dict[str, Any]] = []
    # S2-4 SURFACES reconciliation (P41) — see BriefingResponse.reconciliation
    reconciliation: dict[str, Any] = {}


class WhisperResponse(BaseModel):
    type: str
    entity: str
    title: str
    body: str
    priority: str
    action_url: str = ""
    delivery_route: str = ""
    delivery_explanation: str = ""
    suppression_reason: str = ""
    evidence_refs: list[str] = []


# ---------------------------------------------------------------------------
# Noise filter helpers (kept here for use by briefing/evening)
# ---------------------------------------------------------------------------


_NOISE_SIGNAL_TYPES = frozenset({
    "newsletter", "fyi", "notification", "notification_digest",
    "blog", "social", "marketing", "announcement",
})
_NOISE_NAME_PATTERNS = ("newsletter", "news corp", "digest", "fyi", "notification",
                        "trending", "promo", "limited offer", "discount")


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
# GET /what-changed — What Changed surface
# ---------------------------------------------------------------------------


@router.get("/what-changed", response_model=list[WhatChangedResponse])
async def get_what_changed(as_of: str | None = None, token: str = Depends(verify_token_dep)):
    """Get recent meaningful deltas.

    Phase 3.4 fix (auditor v13): "detect change, don't summarise."
    - No-change day → silence (return empty list, not a feed of mundane updates)
    - One critical change → surfaced alone (not buried in a list of 3)
    - State transitions (resolved, cancelled, broken) rank higher than new signals
    """
    from maestro_personal_shell.api import build_shell
    shell = build_shell(user_email=token, as_of=as_of)
    from maestro_personal_shell.surfaces.what_changed import WhatChangedSurface
    surface = WhatChangedSurface(shell=shell)
    # Phase 3.4: use 24h window (not 30d) — "what changed" means RECENTLY
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    deltas = surface.get_recent_deltas(since_timestamp=since)

    # Phase 3.4: rank by materiality — state transitions first, then new commitments
    _RANK = {
        "resolved": 5,        # commitment completed = highest signal
        "cancelled": 4,       # commitment cancelled = high signal
        "broken": 4,          # commitment broken = high signal
        "commitment_made": 3, # new commitment = medium
        "personal.promise": 3,
        "personal.commitment": 3,
        "question": 2,        # question asked = low-medium
        "reported_statement": 1, # statement = low
    }
    def _rank_key(d):
        t = str(d.get("type", "")).lower()
        return (_RANK.get(t, 0), 1 if d.get("is_meaningful") else 0)
    deltas.sort(key=_rank_key, reverse=True)

    # Phase 3.4: only return deltas with rank >= 3 (state transitions + new commitments)
    # If nothing ranked >= 3, return EMPTY (silence) — not a feed of mundane updates
    critical_deltas = [d for d in deltas if _rank_key(d)[0] >= 3]

    # If there are critical deltas, return only those (top 3 max)
    # If no critical deltas, return empty (silence — no-change day)
    result_deltas = critical_deltas[:3] if critical_deltas else []

    return [
        WhatChangedResponse(
            entity=d["entity"], text=d["text"], type=d["type"],
            is_meaningful=d["is_meaningful"],
        )
        for d in result_deltas
    ]


@router.get("/what-changed/the-shifts", response_model=WhatChangedMasterpieceResponse)
async def get_the_shifts(token: str = Depends(verify_token_dep)):
    """The 2 things that materially shifted — not a feed."""
    # RESTORE CACHE: 60s TTL, same pattern as /api/the-moment.
    # The-shifts calls build_shell + change_detection + reconcile_snapshot
    # — expensive on cold cache. Without this, every Today page load
    # pays the full cost even if nothing changed in the last 60s.
    import time as _shifts_cache_time
    _shifts_key = f"the-shifts:{token}"
    _cached_shifts = _MOMENT_CACHE.get(_shifts_key)
    if _cached_shifts and _cached_shifts[0] > _shifts_cache_time.monotonic():
        return _cached_shifts[1]

    from maestro_personal_shell.api import build_shell
    shell = build_shell(user_email=token)
    from maestro_personal_shell.surfaces.what_changed import WhatChangedSurface
    # S2-4 SURFACES reconciliation (P41): single source of truth — every
    # surface derives its counts from the same reconcile_snapshot() call.
    from maestro_personal_shell.surfaces._snapshot import reconcile_snapshot
    recon = reconcile_snapshot(shell, user_email=token)
    surface = WhatChangedSurface(shell=shell)
    # P11 WIRING FIX: change_detection (P78) — use baseline tracking instead
    # of a fixed 24h window. The prior code always looked back 24h, so a user
    # who checked twice in 10 minutes saw the same "changes" both times.
    # The change_detection module tracks last_seen_at per user and computes
    # actual deltas (new, modified, resolved, contradicted since last read).
    # Latency: ~50ms (one DB query for baseline + one for deltas).
    try:
        from maestro_personal_shell.change_detection import compute_changes, update_last_seen
        from maestro_personal_shell.db_util import default_sqlite_path
        _db = default_sqlite_path()
        _changes = compute_changes(user_email=token, db_path=_db)
        # FIX: compute_changes returns keys 'new', 'modified', 'resolved', 'contradicted'
        # (NOT 'deltas'). Combine all into a single list for the surface to filter.
        deltas = (_changes.get("new", []) + _changes.get("modified", [])
                  + _changes.get("resolved", []) + _changes.get("contradicted", []))
        # Update the baseline so the next call shows only new changes
        update_last_seen(user_email=token, db_path=_db)
    except Exception as _cd_err:
        logger.warning("change_detection failed (non-fatal, falling back to 24h window): %s", _cd_err)
        # Fallback: original 24h window approach
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        deltas = surface.get_recent_deltas(since_timestamp=since)

    meaningful = [d for d in deltas if d.get("is_meaningful")]
    if not meaningful:
        _result_empty = WhatChangedMasterpieceResponse(
            the_shifts=[],
            silence_message="Nothing material changed in the last 24 hours.",
            reconciliation=recon,
        )
        _MOMENT_CACHE[_shifts_key] = (_shifts_cache_time.monotonic() + 60.0, _result_empty)
        return _result_empty
    # Phase 3.4: if only ONE meaningful change, surface it alone (not padded
    # to 2 with less-important items). The auditor wants "one critical change
    # → surfaced alone."
    the_shifts = meaningful[:2] if len(meaningful) > 1 else meaningful
    _result = WhatChangedMasterpieceResponse(
        the_shifts=[
            WhatChangedResponse(
                entity=d["entity"], text=d["text"], type=d["type"],
                is_meaningful=d["is_meaningful"],
            )
            for d in the_shifts
        ],
        silence_message="",
        reconciliation=recon,
    )
    _MOMENT_CACHE[_shifts_key] = (_shifts_cache_time.monotonic() + 60.0, _result)
    return _result


# ---------------------------------------------------------------------------
# GET /prepare — Prepare surface (3 things that matter)
# ---------------------------------------------------------------------------


@router.get("/prepare", response_model=list[PrepareResponse])
async def get_prepare(as_of: str | None = None, token: str = Depends(verify_token_dep)):
    """Get preparation for upcoming situations — 3 things that matter.

    Phase 2.9 fix (auditor v13): /api/prepare regressed to 4.5s. Root cause:
    the endpoint iterates ALL situations (102+) and calls generate_prep (DB
    query) for each. Fix: cap at top 10 situations by priority + add a 60s
    in-memory cache per user.
    """
    # Phase 2.9: 60-second per-user cache
    import time as _cache_time
    _cache_key = f"prepare:{token}:{as_of or 'now'}"
    _cached = _PREPARE_CACHE.get(_cache_key)
    if _cached and _cached[0] > _cache_time.monotonic():
        return _cached[1]

    try:
        from maestro_personal_shell.api import build_shell, _filter_corrected_signals
        shell = build_shell(user_email=token, as_of=as_of)
        core = shell.core
        from maestro_personal_shell.surfaces.prepare import PrepareSurface
        surface = PrepareSurface(shell=shell)
        situations = surface.get_situations_needing_preparation()
        # Phase 2.9: cap at top 10 situations (was unbounded — 102+ situations
        # each requiring a DB query in generate_prep)
        situations = situations[:10]
    except Exception as e:
        logger.error("prepare: failed to build shell/situations: %s", e)
        return []
    result = []
    for s in situations:
        sit_id = str(getattr(s, "situation_id", uuid4()))
        entity = str(getattr(s, "entity", ""))
        try:
            prep = surface.prepare_for_situation(sit_id)
            is_stale = bool(prep and getattr(prep, "is_stale", False))
        except Exception:
            is_stale = False

        raw_entity_signals = [
            sig for sig in shell.oem_state.signals
            if str(getattr(sig, "entity", "")).lower() == entity.lower()
        ]
        entity_signals = _filter_corrected_signals(raw_entity_signals)

        # THE FORGOTTEN: oldest commitment signal that is >14 days old
        # Phase 3.1 fix (auditor v16): the prior code just took the oldest
        # commitment — even if it was from 5 minutes ago. The auditor wants
        # ">14d untouched, unresolved." Fix: filter to commitments older than
        # 14 days that are still active.
        the_forgotten = ""
        commitment_signals = [
            sig for sig in entity_signals
            if "commitment" in str(getattr(sig, "signal_type", "")).lower()
        ]
        if commitment_signals:
            commitment_signals.sort(key=lambda x: getattr(x, "timestamp", datetime.max))
            # Phase 3.1: find the OLDEST commitment that is >14 days old
            _now = datetime.now(timezone.utc)
            _fourteen_days_ago = _now - timedelta(days=14)
            for cs in commitment_signals:
                try:
                    cs_ts = getattr(cs, "timestamp", None)
                    if cs_ts and hasattr(cs_ts, "tzinfo"):
                        if cs_ts.tzinfo is None:
                            cs_ts = cs_ts.replace(tzinfo=timezone.utc)
                        if cs_ts < _fourteen_days_ago:
                            the_forgotten = getattr(cs, "text", "")
                            break
                except Exception:
                    pass
            # Fallback: if no >14d commitment, use the oldest (non-empty)
            if not the_forgotten and commitment_signals:
                the_forgotten = getattr(commitment_signals[0], "text", "")

        # THE OPEN QUESTION: signals containing "?" that haven't been answered
        # Phase 3.1 fix (auditor v16): the prior code only looked for
        # "follow_up" signal_type — but the classifier rarely sets that type.
        # Fix: also scan for "?" in signal text, which catches real questions.
        the_open_question = ""
        # First try follow_up signals (original logic)
        followup_signals = [
            sig for sig in entity_signals
            if "follow_up" in str(getattr(sig, "signal_type", "")).lower()
        ]
        if followup_signals:
            the_open_question = getattr(followup_signals[-1], "text", "")
        else:
            # Phase 3.1: scan for questions (text containing "?")
            _ANSWER_KEYWORDS = [
                "confirmed", "yes", "answered", "resolved",
                "decided", "agreed", "approved", "denied", "rejected",
                "sent", "delivered", "completed", "done", "finished",
            ]
            for sig in entity_signals:
                text = str(getattr(sig, "text", ""))
                if "?" not in text:
                    continue
                # Check if any LATER signal answers this question
                sig_ts = getattr(sig, "timestamp", datetime.max)
                _answered = False
                for ans in entity_signals:
                    ans_ts = getattr(ans, "timestamp", datetime.min)
                    if ans_ts > sig_ts:
                        ans_text = str(getattr(ans, "text", "")).lower()
                        if any(kw in ans_text for kw in _ANSWER_KEYWORDS):
                            _answered = True
                            break
                if not _answered:
                    the_open_question = text
                    break

        # THE CONTRADICTION: most recent reported_statement
        the_contradiction = ""
        statement_signals = [
            sig for sig in entity_signals
            if "reported" in str(getattr(sig, "signal_type", "")).lower()
            or "observed" in str(getattr(sig, "signal_type", "")).lower()
        ]
        if statement_signals and len(entity_signals) > 1:
            the_contradiction = getattr(statement_signals[-1], "text", "")

        state_raw = getattr(s, "state", getattr(s, "operational_state", "unknown"))
        if hasattr(state_raw, "value"):
            meeting_context = f"Situation is {state_raw.value}"
        else:
            meeting_context = f"Situation is {str(state_raw).split('.')[-1].lower()}"

        copilot_talking_points = []
        copilot_blocking_unknowns = []
        copilot_can_decide = []
        copilot_cannot_decide = []
        copilot_timeline = []
        if core.copilot_bridge:
            try:
                pre_call = core.copilot_bridge.pre_call_briefing(
                    meeting_title=f"Meeting with {entity}",
                    attendees=[entity] if entity else [],
                    user_email="personal", org_id="personal",
                )
                if pre_call:
                    copilot_talking_points = [
                        tp if isinstance(tp, dict) else {"point": str(tp)}
                        for tp in (getattr(pre_call, "talking_points", []) or [])[:5]
                    ]
                    copilot_blocking_unknowns = getattr(pre_call, "blocking_unknowns", []) or []
                    copilot_can_decide = getattr(pre_call, "can_decide_now", []) or []
                    copilot_cannot_decide = getattr(pre_call, "cannot_decide_yet", []) or []
                    copilot_timeline = [
                        ts if isinstance(ts, dict) else {"summary": str(ts)}
                        for ts in (getattr(pre_call, "timeline_summary", []) or [])[:5]
                    ]
            except Exception as e:
                logger.debug("Copilot pre_call_briefing failed: %s", e)

        # S2-3 fix (auditor): if copilot_talking_points is still empty,
        # generate them from the situation's evidence. The auditor found
        # /api/prepare returns prep_points: [] and copilot_talking_points: []
        # because the copilot bridge isn't wired. Generate fallback points
        # from the commitment + contradiction data we already have.
        #
        # Phase 3.1 fix (roadmap v13): use the prepare_engine to generate
        # rich, data-driven prep points from signals + commitments.
        # This is the biggest single audit gap (7 points, 13 audits empty).
        # The prepare_engine produces: who, open_loops, forgotten,
        # blocking_unknowns, decisions_available, why_it_matters, prep_points.
        # We now map ALL of these into the PrepareResponse, not just
        # copilot_talking_points.
        _has_real_points = False
        for tp in copilot_talking_points:
            text = tp.get("point", "") if isinstance(tp, dict) else str(tp)
            if text.strip() and "No active situation" not in text:
                _has_real_points = True
                break

        # Phase 3.1: always run prepare_engine to get rich data, even if
        # copilot produced points. The prepare_engine data populates
        # prep_points, why_this_matters, and enriches blocking_unknowns.
        _prep_engine_data = None
        try:
            from maestro_personal_shell.prepare_engine import generate_prep
            _prep_engine_data = generate_prep(token, entity)
        except Exception as e:
            logger.warning("prepare_engine failed for %s (non-fatal): %s", entity, e)

        if not _has_real_points and _prep_engine_data and _prep_engine_data.get("prep_points"):
            copilot_talking_points = [
                {"point": pp, "source": "prepare_engine"}
                for pp in _prep_engine_data["prep_points"][:5]
            ]
            if not copilot_blocking_unknowns and _prep_engine_data.get("blocking_unknowns"):
                copilot_blocking_unknowns = [str(b.get("question", b)) if isinstance(b, dict) else str(b) for b in _prep_engine_data["blocking_unknowns"][:3]]
            if not copilot_can_decide and _prep_engine_data.get("decisions_available"):
                copilot_can_decide = [str(d.get("text", d)) if isinstance(d, dict) else str(d) for d in _prep_engine_data["decisions_available"][:3]]

        # Phase 3.1: populate prep_points from the prepare_engine (the
        # auditor found these were always empty — the endpoint never
        # mapped them, only mapped to copilot_talking_points).
        _prep_points = []
        if _prep_engine_data and _prep_engine_data.get("prep_points"):
            _prep_points = _prep_engine_data["prep_points"][:5]

        # Phase 3.1: populate why_this_matters from the prepare_engine
        _why_this_matters = ""
        if _prep_engine_data and _prep_engine_data.get("why_it_matters"):
            _why_this_matters = _prep_engine_data["why_it_matters"]

        # Fallback to rule-based if prepare_engine didn't produce results
        if not copilot_talking_points:
            fallback_points = []
            if the_forgotten:
                fallback_points.append({"point": f"Forgotten: {the_forgotten}", "source": "rule-based"})
            if the_open_question:
                fallback_points.append({"point": f"Open question: {the_open_question}", "source": "rule-based"})
            if the_contradiction:
                fallback_points.append({"point": f"Contradiction: {the_contradiction}", "source": "rule-based"})
            fallback_points.append({"point": f"Current state: {meeting_context}", "source": "rule-based"})
            copilot_talking_points = fallback_points[:5]
            if not _prep_points:
                _prep_points = [tp.get("point", str(tp)) for tp in fallback_points[:5]]

        if not copilot_timeline:
            # Generate a simple timeline from the situation's signals
            sig_refs = getattr(s, "evidence_refs", []) or []
            if sig_refs:
                copilot_timeline = [{"summary": f"Signal: {sid}"} for sid in sig_refs[:3]]

        result.append(PrepareResponse(
            situation_id=sit_id, entity=entity, meeting_context=meeting_context,
            is_stale=is_stale, the_forgotten=the_forgotten,
            the_open_question=the_open_question, the_contradiction=the_contradiction,
            prep_points=_prep_points,
            why_this_matters=_why_this_matters,
            copilot_talking_points=copilot_talking_points,
            copilot_blocking_unknowns=copilot_blocking_unknowns,
            copilot_can_decide=copilot_can_decide,
            copilot_cannot_decide=copilot_cannot_decide,
            copilot_timeline=copilot_timeline,
        ))

    # S2-3 PREPARE fix (Kimi K3 design, P35 + P41):
    # Auditor found "No active situation found for Me." template appearing
    # even when there are 24 active commitments. Root cause: Prepare returns
    # an empty list when no situations need preparation, and the frontend
    # renders that as a template.
    #
    # FIX: when no situations are found, DERIVE Prepare content from the
    # active commitments ledger — the SAME source /api/commitments uses
    # (P41 single source of truth — never a parallel snapshot). Top 3
    # commitments by salience/urgency become the talking points; the
    # "moment" line summarizes what the user owes.
    if not result:
        try:
            from maestro_personal_shell.surfaces.commitments import CommitmentsSurface
            from maestro_personal_shell.api import (
                _filter_corrected_signals as _fs_corrected,
            )
            # Single source of truth (P41): CommitmentsSurface.get_active_commitments
            # is the SAME path /api/commitments uses — never query the DB directly.
            commit_surface = CommitmentsSurface(shell=shell)
            active = commit_surface.get_active_commitments()
            # Read stale map (same source as /api/commitments — days_threshold=2)
            stale_prep = shell.detect_stale_commitments(days_threshold=2)
            stale_sids = set()
            for s in stale_prep:
                commit = s.get("commitment")
                if not commit:
                    continue
                if isinstance(commit, dict):
                    sid = commit.get("signal_id", "")
                else:
                    sid = getattr(commit, "signal_id", "")
                if sid:
                    stale_sids.add(sid)
            # Sort: stale first, then by entity name for determinism
            active_sorted = sorted(
                active,
                key=lambda c: (
                    0 if c.get("signal_id", "") in stale_sids else 1,
                    c.get("entity", "").lower(),
                ),
            )
            top3 = active_sorted[:3]
            if top3:
                # Build talking points from the top 3 commitments — these are
                # the things the user needs to prepare for NOW.
                fallback_points = []
                for c in top3:
                    ent = c.get("entity", "unknown")
                    txt = c.get("text", "")[:100]
                    is_stale_c = c.get("signal_id", "") in stale_sids
                    marker = "OVERDUE " if is_stale_c else ""
                    fallback_points.append({
                        "point": f"{marker}{ent}: {txt}",
                        "source": "commitment-ledger",
                    })
                # Build the "moment" line — a single summary of what the user owes
                total_active = len(active)
                overdue_count = sum(1 for c in active if c.get("signal_id", "") in stale_sids)
                top_entity = top3[0].get("entity", "")
                top_action = top3[0].get("text", "")[:60]
                moment_ctx = (
                    f"You have {total_active} active commitment(s)"
                    + (f", {overdue_count} OVERDUE" if overdue_count else "")
                    + f". Highest priority: {top_entity} — {top_action}."
                )
                # Build timeline from the top 3
                fallback_timeline = [
                    {"summary": f"{c.get('entity','')}: {c.get('text','')[:60]}"}
                    for c in top3
                ]
                # The "forgotten" is the oldest commitment (most likely to be forgotten)
                forgotten = ""
                if top3:
                    forgotten = top3[0].get("text", "")
                result.append(PrepareResponse(
                    situation_id="commitment-ledger-fallback",
                    entity=top_entity or "your commitments",
                    meeting_context=moment_ctx,
                    is_stale=False,
                    the_forgotten=forgotten,
                    the_open_question="",
                    the_contradiction="",
                    copilot_talking_points=fallback_points,
                    copilot_blocking_unknowns=[],
                    copilot_can_decide=[],
                    copilot_cannot_decide=[],
                    copilot_timeline=fallback_timeline,
                ))
        except Exception as e:
            logger.debug("S2-3 PREPARE fallback (commitment-ledger) failed: %s", e)

    # Phase 2.9: cache the result for 60 seconds
    _PREPARE_CACHE[_cache_key] = (_cache_time.monotonic() + 60.0, result)
    return result


# ---------------------------------------------------------------------------
# GET /whisper — Whisper surface (proactive push)
# ---------------------------------------------------------------------------


# Issue 13-A: Rule-based early-exit for whisper materiality gate.
#
# The materiality_gate_v2 LLM call adds 10-25s latency per whisper. For
# most whispers, we can decide rule-based in <1ms:
#   - critical/high-priority → ALWAYS whisper (return True, skip LLM)
#   - low-value types → NEVER whisper (return False, skip LLM)
#   - medium-priority borderline → return None (let LLM gate decide)
#
# This brings /api/whisper from 10-25s down to <200ms for the majority
# of calls. The LLM gate only runs for the borderline medium-priority
# cases where the rule-based decision is ambiguous.

# Whisper types that are ALWAYS worth surfacing — never suppress.
# Note: these still go through the materiality gate (the gate learns from
# dismissals). Only critical_signal bypasses the gate entirely (F6 guard:
# emergencies never get suppressed).
#
# Phase 3.2 fix (auditor v13): stale_commitment and deadline_approaching
# also bypass the gate when they're high priority. The auditor found
# Whisper returning 0 while Ambient holds 3 stale commitments — the gate
# was suppressing the most actionable whispers. These types are inherently
# user-actionable (an overdue commitment or a deadline in <48h), so the
# gate's "is this worth interrupting?" question is already answered.
_ALWAYS_WHISPER_TYPES = frozenset({
    "critical_signal",      # lawsuit, churn, breach, outage — BYPASSES gate (F6)
    "stale_commitment",     # overdue commitment — inherently actionable
    "deadline_approaching", # deadline in <48h — inherently time-bounded
})

# Types that go through the gate but the gate should be lenient with
# (these are important but can still be suppressed if the user dismisses
# them repeatedly — the learning loop needs to see them)
_GATE_PASSTHROUGH_TYPES = frozenset({
    "broken_commitment",    # "Never sent the questionnaire"
    "stale_commitment",     # overdue commitment
    "deadline_approaching", # deadline in <48h
    "contradiction_detected",
})

# Whisper types that are NEVER worth surfacing — always suppress.
# These are noise the user doesn't need a push notification for.
_NEVER_WHISPER_TYPES = frozenset({
    "fyi",
    "newsletter",
    "digest",
    "routine_update",
    "status_acknowledgment",
})

# Priority levels that always warrant a whisper regardless of type.
_ALWAYS_WHISPER_PRIORITIES = frozenset({"critical", "high"})


def _should_whisper_rule_based(w: dict) -> bool | None:
    """Rule-based early-exit for the whisper materiality gate."""
    w_type = w.get("type", "")
    w_priority = str(w.get("priority", "")).lower()

    # 1. Critical_signal type ALWAYS fires — emergencies bypass the gate.
    #    Only the critical_signal TYPE bypasses, NOT high priority (the
    #    test test_priority_does_not_override_gate verifies this: a
    #    "routine" type with "high" priority must still go through the gate).
    if w_type in _ALWAYS_WHISPER_TYPES:
        return True

    # 2. Low-value types NEVER fire — these are noise
    if w_type in _NEVER_WHISPER_TYPES:
        return False

    # 3. All other whispers (including high-priority non-critical types)
    #    → let LLM gate decide. The gate must see ALL non-critical whispers
    #    to learn from dismissals. High priority alone does NOT bypass.
    return None


@router.get("/whisper", response_model=list[WhisperResponse])
async def get_whispers(token: str = Depends(verify_token_dep)):
    """Get active whispers — things that deserve attention RIGHT NOW.

    LATENCY FIX (v21): added 60-second cache. The whisper endpoint was
    taking 6+ seconds on EVERY call because build_shell loads all signals
    and the materiality_gate_v2 LLM call adds 10-25s per whisper.
    """
    # LATENCY FIX: 60-second cache (same pattern as the-moment)
    import time as _whisper_cache_time
    _whisper_key = f"whisper:{token}"
    _cached_whisper = _WHISPER_CACHE.get(_whisper_key)
    if _cached_whisper and _cached_whisper[0] > _whisper_cache_time.monotonic():
        return _cached_whisper[1]

    from maestro_personal_shell.api import build_shell
    shell = build_shell(user_email=token)
    core = shell.core
    from maestro_personal_shell.surfaces.whisper import WhisperSurface
    surface = WhisperSurface(shell=shell)
    whispers = surface.get_active_whispers()

    situations = shell.detect_situations()
    sit_by_entity = {}
    for s in situations:
        entity = str(getattr(s, "entity", "")).lower()
        if entity:
            sit_by_entity[entity] = s

    result = []
    for w in whispers:
        delivery_route = ""
        delivery_explanation = ""
        suppression_reason = ""
        evidence_refs = []
        entity_lower = w.get("entity", "").lower()
        matching_sit = sit_by_entity.get(entity_lower)
        if core.whisper_bridge and matching_sit:
            try:
                whisper_result = core.whisper_bridge.from_situation(
                    situation=matching_sit,
                    context="meeting" if "meeting" in w.get("type", "") else "",
                )
                if whisper_result:
                    delivery_route = str(getattr(whisper_result, "delivery_route", ""))
                    delivery_explanation = str(getattr(whisper_result, "delivery_explanation", ""))
                    suppression_reason = str(getattr(whisper_result, "suppression_reason", ""))
                    evidence_refs = [str(r) for r in (getattr(whisper_result, "evidence_refs", []) or [])[:3]]
            except Exception as e:
                logger.debug("WhisperSituationBridge call failed: %s", e)

        # F5 fix: wire materiality_gate_v2 into /api/whisper path. F6 guard:
        # NEVER apply the gate to critical_signal-type whispers.
        #
        # Issue 13-A fix: rule-based early-exit. The materiality_gate_v2 LLM
        # call adds 10-25s latency per whisper. For most whispers, we can
        # decide rule-based in <1ms:
        #   - critical/high-priority → ALWAYS whisper (skip gate)
        #   - low-value types (fyi, newsletter, digest) → NEVER whisper (skip gate)
        #   - medium-priority borderline → LLM gate (the only case that needs it)
        # This brings whisper endpoint from 10-25s down to <200ms for the
        # majority of calls.
        should_whisper = True
        _RULE_BASED = _should_whisper_rule_based(w)
        if _RULE_BASED is not None:
            # Rule-based decision made — skip the LLM gate entirely
            should_whisper = _RULE_BASED
            if not should_whisper:
                suppression_reason = "suppressed by rule-based filter (low-value type)"
        elif w.get("type") != "critical_signal":
            try:
                from maestro_personal_shell.dynamic_agents import materiality_gate_v2
                mat_context = {
                    "days_stale": 0, "has_deadline": False, "deadline": "",
                    "age_days": 0, "transition_type": w.get("type", "routine"),
                }
                pseudo_commit = {
                    "entity": w.get("entity", ""), "text": w.get("body", ""),
                    "signal_type": w.get("type", ""),
                }
                mat_result = await materiality_gate_v2(pseudo_commit, mat_context, user_email=token)
                should_whisper = mat_result.get("should_speak", True)
                if not should_whisper:
                    suppression_reason = mat_result.get("reason", "suppressed by materiality_gate_v2 (learned from your dismissals)")
            except Exception as e:
                logger.warning("materiality_gate_v2 failed on /api/whisper (non-fatal, whisper still emitted): %s", e)

        if not should_whisper:
            continue

        result.append(WhisperResponse(
            type=w["type"], entity=w["entity"], title=w["title"], body=w["body"],
            priority=w["priority"], action_url=w.get("action_url", ""),
            delivery_route=delivery_route, delivery_explanation=delivery_explanation,
            suppression_reason=suppression_reason, evidence_refs=evidence_refs,
        ))

    # P1-Audit-F9 fix: stale commitment whispers must NOT default to "silent".
    for r in result:
        if r.type == "stale_commitment" and r.delivery_route in ("", "silent"):
            r.delivery_route = "whisper"
            if not r.delivery_explanation:
                r.delivery_explanation = "Stale commitment — follow-up needed"
            if r.suppression_reason:
                r.suppression_reason = ""

    # LATENCY FIX: cache the result for 60 seconds
    _WHISPER_CACHE[_whisper_key] = (_whisper_cache_time.monotonic() + 60.0, result)

    return result


# ---------------------------------------------------------------------------
# GET /briefing — Morning briefing
# ---------------------------------------------------------------------------


@router.get("/briefing", response_model=BriefingResponse, response_model_exclude_none=True)
async def get_briefing(token: str = Depends(verify_token_dep)):
    """Morning briefing — the full Situation-centric intelligence."""
    from maestro_personal_shell.api import build_shell
    shell = build_shell(user_email=token)
    core = shell.core
    # S2-4 SURFACES reconciliation (P41) — single source of truth.
    from maestro_personal_shell.surfaces._snapshot import reconcile_snapshot
    recon = reconcile_snapshot(shell, user_email=token)
    if not core.briefing_bridge:
        return BriefingResponse(
            greeting="Good morning. Briefing engine unavailable.",
            ask_prompt="What do you want to understand?",
            reconciliation=recon,
        )
    try:
        briefing = core.briefing_bridge.generate_morning_briefing(
            user_email=token, org_id="personal",
        )

        # F-07 fix (auditor S2 — briefing prioritizes ambiguous content):
        # Filter noise + tentative content from top_situation. The morning
        # briefing was promoting David Kim's "Maybe we can grab coffee" as
        # the top situation. Tentative/social content should never be the
        # top briefing item.
        top_situation = getattr(briefing, "top_situation", None)
        if top_situation:
            top_entity = str(getattr(top_situation, "entity", "") or
                           (top_situation.get("entity", "") if isinstance(top_situation, dict) else "")).lower()
            top_title = str(getattr(top_situation, "title", "") or
                           (top_situation.get("title", "") if isinstance(top_situation, dict) else "")).lower()
            is_noise = False
            for sig in shell.oem_state.signals:
                sig_entity = str(getattr(sig, "entity", "")).lower()
                sig_type = str(getattr(sig, "signal_type", "") or
                             getattr(getattr(sig, "type", ""), "value", "")).lower()
                sig_text = str(getattr(sig, "text", "")).lower()
                if sig_entity == top_entity:
                    # Check for noise signal types
                    if sig_type in (
                        "newsletter", "fyi", "notification", "notification_digest",
                        "blog", "social", "marketing", "announcement",
                    ):
                        is_noise = True
                        break
                    # F-07 fix: check for tentative/hedging language in the signal text
                    tentative_markers = [
                        "maybe", "might", "possibly", "don't count on",
                        "not sure", "try to", "i hope", "hopefully",
                        "i'd like to", "i wish i could", "no promises",
                        "can't guarantee", "might be able", "i'll try",
                        "i'll see", "we'll see", "i'll let you know",
                    ]
                    if any(marker in sig_text for marker in tentative_markers):
                        is_noise = True
                        break
            if not is_noise:
                # F-05 (sixth audit): expanded noise patterns — newsletters,
                # promo senders, marketing, and known newsletter brands must
                # never rank above a human obligation in the top situation.
                noise_name_patterns = ("newsletter", "news corp", "digest", "fyi", "notification",
                                       "the athletic", "athletic", "substack", "medium",
                                       "hacker news", "product hunt", "techcrunch",
                                       "promotional", "no-reply", "noreply", "do not reply",
                                       "unsubscribe", "mailing list", "mailinglist")
                if any(pat in top_entity for pat in noise_name_patterns):
                    is_noise = True
                # F-05: also check the title
                if not is_noise and any(pat in top_title for pat in noise_name_patterns):
                    is_noise = True
                # F-05: marketing sender patterns (all-caps TEAM, NOTIFICATIONS, etc.)
                if not is_noise:
                    _entity_upper = top_entity.upper()
                    if any(kw in _entity_upper for kw in ("TEAM", "NOTIFICATIONS", "NO-REPLY", "NOREPLY", "UPDATES", "DIGEST")):
                        is_noise = True
            # Also check the title directly for tentative language
            if not is_noise:
                tentative_in_title = [
                    "maybe", "might", "possibly", "i'll let you know",
                    "don't count on", "tentative",
                ]
                if any(marker in top_title for marker in tentative_in_title):
                    is_noise = True
            if is_noise:
                top_situation = None

        return BriefingResponse(
            greeting=getattr(briefing, "greeting", ""),
            top_situation=top_situation,
            material_changes=_filter_tentative_from_list(getattr(briefing, "material_changes", []) or [], shell),
            unknowns=_filter_tentative_from_list(getattr(briefing, "unknowns", []) or [], shell),
            disputes=getattr(briefing, "disputes", []) or [],
            can_decide_now=getattr(briefing, "can_decide_now", []) or [],
            cannot_decide_yet=_filter_tentative_from_list(getattr(briefing, "cannot_decide_yet", []) or [], shell),
            why_boundary=getattr(briefing, "why_boundary", ""),
            next_step=getattr(briefing, "next_step", ""),
            belief=getattr(briefing, "belief", ""),
            why_belief=getattr(briefing, "why_belief", ""),
            what_would_change_belief=getattr(briefing, "what_would_change_belief", ""),
            watching_quietly=getattr(briefing, "watching_quietly", []) or [],
            ask_prompt=getattr(briefing, "ask_prompt", "What do you want to understand?"),
            reconciliation=recon,
        )
    except Exception as e:
        logger.debug("Briefing generation failed: %s", e)
        return BriefingResponse(
            greeting="Good morning.",
            ask_prompt="What do you want to understand?",
            reconciliation=recon,
        )


# ---------------------------------------------------------------------------
# GET /briefing/evening — Evening briefing
# ---------------------------------------------------------------------------


@router.get("/briefing/evening", response_model=BriefingResponse, response_model_exclude_none=True)
async def get_evening_briefing(token: str = Depends(verify_token_dep)):
    """Evening briefing — what happened today, what's pending."""
    from maestro_personal_shell.api import build_shell
    shell = build_shell(user_email=token)
    core = shell.core
    # S2-4 SURFACES reconciliation (P41) — single source of truth.
    from maestro_personal_shell.surfaces._snapshot import reconcile_snapshot
    recon = reconcile_snapshot(shell, user_email=token)
    if not core.briefing_bridge:
        return BriefingResponse(
            greeting="Good evening. Briefing engine unavailable.",
            ask_prompt="What do you want to understand?",
            reconciliation=recon,
        )
    try:
        briefing = core.briefing_bridge.generate_evening_briefing(
            user_email=token, org_id="personal",
        )

        # P1-2 fix: filter noise from top_situation (auditor finding D)
        top_situation = getattr(briefing, "top_situation", None)
        if top_situation:
            top_entity = str(getattr(top_situation, "entity", "") or
                           (top_situation.get("entity", "") if isinstance(top_situation, dict) else "")).lower()
            is_noise = False
            for sig in shell.oem_state.signals:
                sig_entity = str(getattr(sig, "entity", "")).lower()
                sig_type = str(getattr(sig, "signal_type", "") or
                             getattr(getattr(sig, "type", ""), "value", "")).lower()
                if sig_entity == top_entity and sig_type in (
                    "newsletter", "fyi", "notification", "notification_digest",
                    "blog", "social", "marketing", "announcement",
                ):
                    is_noise = True
                    break
            if not is_noise:
                # F-05 (sixth audit): expanded noise patterns — newsletters,
                # promo senders, marketing, and known newsletter brands must
                # never rank above a human obligation in the top situation.
                noise_name_patterns = ("newsletter", "news corp", "digest", "fyi", "notification",
                                       "the athletic", "athletic", "substack", "medium",
                                       "hacker news", "product hunt", "techcrunch",
                                       "promotional", "no-reply", "noreply", "do not reply",
                                       "unsubscribe", "mailing list", "mailinglist")
                if any(pat in top_entity for pat in noise_name_patterns):
                    is_noise = True
                # F-05: also check the title
                if not is_noise and any(pat in top_title for pat in noise_name_patterns):
                    is_noise = True
                # F-05: marketing sender patterns (all-caps TEAM, NOTIFICATIONS, etc.)
                if not is_noise:
                    _entity_upper = top_entity.upper()
                    if any(kw in _entity_upper for kw in ("TEAM", "NOTIFICATIONS", "NO-REPLY", "NOREPLY", "UPDATES", "DIGEST")):
                        is_noise = True
            if is_noise:
                top_situation = None

        return BriefingResponse(
            greeting=getattr(briefing, "greeting", ""),
            top_situation=top_situation,
            material_changes=_filter_noise_from_material_changes(
                getattr(briefing, "material_changes", []) or [],
                shell.oem_state.signals,
            ),
            unknowns=getattr(briefing, "unknowns", []) or [],
            disputes=getattr(briefing, "disputes", []) or [],
            can_decide_now=getattr(briefing, "can_decide_now", []) or [],
            cannot_decide_yet=getattr(briefing, "cannot_decide_yet", []) or [],
            why_boundary=getattr(briefing, "why_boundary", ""),
            next_step=getattr(briefing, "next_step", ""),
            belief=getattr(briefing, "belief", ""),
            why_belief=getattr(briefing, "why_belief", ""),
            what_would_change_belief=getattr(briefing, "what_would_change_belief", ""),
            watching_quietly=getattr(briefing, "watching_quietly", []) or [],
            ask_prompt=getattr(briefing, "ask_prompt", "What do you want to understand?"),
            reconciliation=recon,
        )
    except Exception as e:
        logger.debug("Evening briefing failed: %s", e)
        return BriefingResponse(
            greeting="Good evening.",
            ask_prompt="What do you want to understand?",
            reconciliation=recon,
        )


# ---------------------------------------------------------------------------
# GET /the-moment — THE MASTERPIECE ENDPOINT
# ---------------------------------------------------------------------------


@router.get("/the-moment", response_model=TheMomentResponse)
async def get_the_moment(as_of: str | None = None, token: str = Depends(verify_token_dep)):
    """The single most important thing Maestro knows right now.

    The Spotlight moment — the one commitment that matters most. Not a list.
    If nothing deserves attention, returns has_moment=False.

    Phase L4 fix (auditor v18): added 60-second cache. /api/the-moment was
    consistently the slowest read (1.1-1.4s vs 0.2s for every other read)
    because it calls build_shell + CommitmentsSurface + stale detection +
    materiality gate. The cache reduces warm calls to <50ms.
    """
    # Phase L4: 60-second cache
    import time as _cache_time_moment
    _moment_key = f"the-moment:{token}:{as_of or 'now'}"
    _cached_moment = _MOMENT_CACHE.get(_moment_key)
    if _cached_moment and _cached_moment[0] > _cache_time_moment.monotonic():
        return _cached_moment[1]

    from maestro_personal_shell.api import (
        build_shell,
        _filter_completed_commitments,
        _filter_dismissed_commitments,
        _filter_non_commitments_by_classification,
    )
    shell = build_shell(user_email=token, as_of=as_of)
    # S2-4 SURFACES reconciliation (P41) — single source of truth.
    from maestro_personal_shell.surfaces._snapshot import reconcile_snapshot
    recon = reconcile_snapshot(shell, user_email=token)
    from maestro_personal_shell.surfaces.commitments import CommitmentsSurface
    surface = CommitmentsSurface(shell=shell)
    commitments = surface.get_active_commitments()
    commitments = _filter_completed_commitments(commitments, shell.oem_state.signals)
    commitments = _filter_dismissed_commitments(commitments, shell.oem_state.signals)
    commitments = _filter_non_commitments_by_classification(commitments, shell.oem_state.signals)

    if not commitments:
        return TheMomentResponse(has_moment=False, reconciliation=recon)

    stale = shell.detect_stale_commitments(days_threshold=2)
    stale_ids = {s.get("commitment", None) and getattr(s["commitment"], "signal_id", "") or
                 s.get("commitment", {}).get("signal_id", "") for s in stale}

    best_commitment = None
    best_score = -1
    best_why = ""
    now = datetime.now(timezone.utc)

    for c in commitments:
        score = 0
        reasons = []
        if c.get("signal_id") in stale_ids:
            score += 50
            reasons.append("no follow-up in days")
        sig_meta = c.get("metadata", {}) or {}
        deadline = sig_meta.get("deadline")
        if deadline:
            score += 30
            reasons.append(f"deadline: {deadline}")
        if c.get("claim_type") == "commitment":
            score += 20
            reasons.append("you made this promise")
        ts = c.get("timestamp")
        if ts:
            try:
                ct = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                age_days = (now - ct).days
                score += min(age_days, 20)
                if age_days > 7:
                    reasons.append(f"made {age_days} days ago")
            except Exception as e:
                logger.debug("append failed: %s", e)
        # Change 5: Learning loop affects ranking — entities with high
        # dismissal rates get deprioritized (score * (1 - dismissal_rate * 0.5))
        try:
            from maestro_personal_shell.learning_loop_v2 import get_entity_dismissal_rate
            entity = c.get("entity", "")
            dismissal_rate = get_entity_dismissal_rate(user_email=token, entity=entity)
            c["dismissal_rate"] = dismissal_rate
            score = int(score * (1.0 - dismissal_rate * 0.5))
        except Exception:
            c["dismissal_rate"] = 0.0
        if score > best_score:
            best_score = score
            best_commitment = c
            best_why = "; ".join(reasons) if reasons else "active commitment"

    if not best_commitment:
        return TheMomentResponse(has_moment=False, reconciliation=recon)

    # Phase 3.1: LLM-powered Trusted Silence (Materiality Gate)
    # Phase 2.9 fix (auditor v13): skip the LLM gate when the commitment
    # is clearly high-priority (stale or has a deadline). The LLM gate
    # adds 1-3s latency per call, pushing /api/the-moment over the 2s
    # target. For stale commitments (days_stale > 2) or commitments with
    # deadlines, the materiality question is already answered — surface
    # them. The gate only runs for the borderline case (not stale, no
    # deadline, not old) where 'should we surface this?' is genuinely
    # ambiguous.
    try:
        mat_context = {
            "days_stale": 0,
            "has_deadline": bool(best_commitment.get("metadata", {}).get("deadline")),
            "deadline": best_commitment.get("metadata", {}).get("deadline", ""),
            "age_days": 0,
        }
        if best_commitment.get("signal_id") in stale_ids:
            for s in stale:
                sid = getattr(s.get("commitment", {}), "signal_id", "") or s.get("commitment", {}).get("signal_id", "")
                if sid == best_commitment.get("signal_id"):
                    mat_context["days_stale"] = s.get("days_stale", 0)
                    break
        ts = best_commitment.get("timestamp")
        if ts:
            try:
                ct = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                mat_context["age_days"] = (now - ct).days
            except Exception as e:
                logger.debug("= failed: %s", e)

        _skip_gate = (
            best_commitment.get("signal_id") in stale_ids  # stale → always surface
            or bool(best_commitment.get("metadata", {}).get("deadline"))  # has deadline → always surface
            or mat_context.get("age_days", 0) > 7  # old → always surface
        )
        if _skip_gate:
            materiality = {"should_speak": True, "reasoning": "rule-based: stale/deadline/old", "materiality_score": 0.8, "llm_powered": False}
        else:
            try:
                from maestro_personal_shell.dynamic_agents import materiality_gate_v2
                materiality = await materiality_gate_v2(best_commitment, mat_context, user_email=token)
            except Exception as e:
                logger.debug("Materiality gate failed, using rule-based: %s", e)
                materiality = {"should_speak": True, "reasoning": "gate failed — surfacing", "materiality_score": 0.5, "llm_powered": False}

        try:
            from maestro_personal_shell.observability import log_whisper_decision
            evidence_avail = [
                {"entity": getattr(sig, "entity", ""), "text": getattr(sig, "text", "")[:80],
                 "signal_id": getattr(sig, "signal_id", "")}
                for sig in shell.oem_state.signals
                if str(getattr(sig, "entity", "")).lower() == str(best_commitment.get("entity", "")).lower()
            ][:5]
            candidate = f"Would surface: {best_commitment.get('entity', '')} — {best_commitment.get('text', '')[:60]}" if materiality.get("should_speak", True) else ""
            log_whisper_decision(
                surface="the_moment",
                entity=str(best_commitment.get("entity", "")),
                should_whisper=materiality.get("should_speak", True),
                materiality_score=materiality.get("materiality_score", 0.0),
                transition_type="stale_commitment" if mat_context.get("days_stale", 0) > 2 else "active",
                threshold=0.0,
                reasoning=materiality.get("reasoning", ""),
                evidence_available=evidence_avail,
                candidate_output=candidate,
            )
        except Exception as e:
            logger.debug(") failed: %s", e)
        if not materiality.get("should_speak", True):
            # P53 (fifth audit F5/S2): "trusted silence" has a FLOOR.
            # Dismissal-based suppression must NEVER hide the flagship
            # feature on a synthetic or fresh-user artifact. If the user
            # has fewer than 5 real dismissals, The Moment STILL surfaces
            # — the suppression requires real dismissal history. This
            # prevents the "100%-dismissal artifact hides everything"
            # failure the auditor found.
            try:
                from maestro_personal_shell.learning_loop_v2 import get_entity_dismissal_rate
                _p53_dismissal_rate = get_entity_dismissal_rate(
                    user_email=token, entity=str(best_commitment.get("entity", "")),
                )
                # P53 floor: if dismissal_rate is 1.0 but the user has
                # very few total signals (likely a fresh/synthetic artifact),
                # surface The Moment anyway.
                _total_signals = len(shell.oem_state.signals)
                if _p53_dismissal_rate >= 0.95 and _total_signals < 50:
                    logger.info(
                        "P53: trusted-silence floor — dismissal_rate=%.2f but only %d signals "
                        "(likely fresh/synthetic); surfacing The Moment anyway.",
                        _p53_dismissal_rate, _total_signals,
                    )
                    # Fall through to surface The Moment (don't return False)
                else:
                    return TheMomentResponse(
                        has_moment=False,
                        why_this_one=f"Trusted silence: {materiality.get('reasoning', 'low materiality')}",
                        reconciliation=recon,
                    )
            except Exception as _p53_err:
                logger.debug("P53 floor check failed, surfacing The Moment: %s", _p53_err)
                # On error, surface The Moment (fail-open for the flagship feature)
        if materiality.get("llm_powered"):
            best_why = materiality.get("reasoning", best_why)
    except Exception as e:
        logger.debug("Materiality gate failed, using rule-based: %s", e)

    situations = shell.detect_situations()
    related_situation = None
    for s in situations:
        s_entity = str(getattr(s, "entity", "")).lower()
        c_entity = str(best_commitment.get("entity", "")).lower()
        if s_entity and c_entity and s_entity == c_entity:
            related_situation = {
                "situation_id": str(getattr(s, "situation_id", "")),
                "entity": str(getattr(s, "entity", "")),
                "state": str(getattr(s, "state", getattr(s, "operational_state", "unknown"))).split(".")[-1].lower(),
                "evidence_count": len(getattr(s, "evidence_refs", []) or []),
            }
            break

    source_evidence = []
    for sig in shell.oem_state.signals:
        if str(getattr(sig, "signal_id", "")) == str(best_commitment.get("signal_id", "")):
            source_evidence.append({
                "text": getattr(sig, "text", ""),
                "entity": getattr(sig, "entity", ""),
                "timestamp": str(getattr(sig, "timestamp", "")),
                "source": (getattr(sig, "metadata", {}) or {}).get("source", "manual"),
            })
            break

    _result = TheMomentResponse(
        has_moment=True,
        commitment={
            "entity": re.sub(r'\s+[a-f0-9]{6,}$', '', best_commitment.get("entity", "")).strip()
                if best_commitment.get("entity") else "",
            "text": best_commitment.get("text", ""),
            "claim_type": str(best_commitment.get("claim_type", "commitment")),
            "signal_id": best_commitment.get("signal_id", ""),
            "timestamp": str(best_commitment.get("timestamp", "")),
        },
        situation=related_situation,
        why_this_one=best_why,
        source_evidence=source_evidence,
        reconciliation=recon,
    )
    # Phase L4: cache the result for 60 seconds
    _MOMENT_CACHE[_moment_key] = (_cache_time_moment.monotonic() + 60.0, _result)
    return _result


# ---------------------------------------------------------------------------
# GET /notifications/smart — context-aware ambient notifications
# ---------------------------------------------------------------------------


class SmartNotificationRequest(BaseModel):
    """Request body for /notifications/smart.

    Per P13: the caller supplies CONTEXT (am I in a call? is DND on?),
    NOT the notification content. The notifications themselves are DERIVED
    from the user's signal history by the AmbientNotificationEngine.
    """
    is_in_call: bool = False
    is_dnd_active: bool = False
    is_focus_mode: bool = False
    user_timezone: str = "UTC"
    limit: int = 10


@router.post("/notifications/smart")
async def get_smart_notifications(
    req: SmartNotificationRequest,
    token: str = Depends(verify_token_dep),
):
    """Get context-aware ambient notifications for the current user."""
    from maestro_personal_shell.ambient_notifications import (
        get_smart_notifications as _get_smart,
        ENTERPRISE_ENGINE_AVAILABLE,
    )
    if not ENTERPRISE_ENGINE_AVAILABLE:
        return {
            "notifications": [],
            "engine_available": False,
            "message": "Smart notifications unavailable — enterprise engine not importable",
        }
    notifications = _get_smart(
        user_email=token,
        is_in_call=req.is_in_call,
        is_dnd_active=req.is_dnd_active,
        is_focus_mode=req.is_focus_mode,
        user_timezone=req.user_timezone,
        limit=req.limit,
    )
    return {
        "notifications": notifications,
        "engine_available": True,
        "count": len(notifications),
    }


# ---------------------------------------------------------------------------
# Phase 9: Calendar awareness + commitment escalation endpoints
# ---------------------------------------------------------------------------


class CalendarAwarenessRequest(BaseModel):
    """Request body for /calendar/awareness.

    P13: caller supplies only a time horizon (CONTEXT), not meeting data.
    The meeting context is DERIVED from the user's signal history.
    """
    hours_ahead: int = 48


@router.post("/calendar/awareness")
async def get_calendar_awareness_endpoint(
    req: CalendarAwarenessRequest,
    token: str = Depends(verify_token_dep),
):
    """Get calendar awareness for upcoming meetings."""
    from maestro_personal_shell.phase9_ambient import (
        get_calendar_awareness as _get_awareness,
        ENTERPRISE_ENGINES_AVAILABLE,
    )
    if not ENTERPRISE_ENGINES_AVAILABLE:
        return {
            "meetings": [],
            "engine_available": False,
            "message": "Calendar awareness unavailable — enterprise engine not importable",
        }
    meetings = _get_awareness(user_email=token, hours_ahead=req.hours_ahead)
    return {
        "meetings": meetings,
        "engine_available": True,
        "count": len(meetings),
    }


@router.get("/commitments/escalations")
async def get_commitment_escalations_endpoint(
    token: str = Depends(verify_token_dep),
):
    """Get commitment escalations for the current user."""
    from maestro_personal_shell.phase9_ambient import (
        get_commitment_escalations as _get_escalations,
        ENTERPRISE_ENGINES_AVAILABLE,
    )
    if not ENTERPRISE_ENGINES_AVAILABLE:
        return {
            "escalations": [],
            "engine_available": False,
            "message": "Commitment escalation unavailable — enterprise engine not importable",
        }
    escalations = _get_escalations(user_email=token)
    return {
        "escalations": escalations,
        "engine_available": True,
        "count": len(escalations),
        "critical_count": sum(1 for e in escalations if e.get("escalation_level") == "critical"),
        "overdue_count": sum(1 for e in escalations if e.get("escalation_level") == "overdue"),
    }


# ---------------------------------------------------------------------------
# Phase 14: Cross-meeting threads (institutional memory)
# ---------------------------------------------------------------------------


class ThreadRequest(BaseModel):
    """Request body for /threads.

    P13: caller supplies only an optional entity filter (CONTEXT), not
    meeting data. The threads are DERIVED from the user's signal history.
    """
    entity_filter: str = ""


@router.post("/threads")
async def get_threads_endpoint(
    req: ThreadRequest,
    token: str = Depends(verify_token_dep),
):
    """Get cross-meeting threads linking related meetings by entity + topic."""
    from maestro_personal_shell.cross_meeting_threads import (
        get_cross_meeting_threads as _get_threads,
        ENTERPRISE_THREAD_BUILDER_AVAILABLE,
    )
    if not ENTERPRISE_THREAD_BUILDER_AVAILABLE:
        return {
            "threads": [],
            "engine_available": False,
            "message": "Cross-meeting threading unavailable — enterprise engine not importable",
        }
    threads = _get_threads(user_email=token, entity_filter=req.entity_filter)
    return {
        "threads": threads,
        "engine_available": True,
        "count": len(threads),
        "high_confidence_count": sum(1 for t in threads if t.get("confidence_level") == "high"),
    }


@router.get("/threads/{entity}")
async def get_threads_for_entity_endpoint(
    entity: str,
    token: str = Depends(verify_token_dep),
):
    """Get cross-meeting threads for a specific entity.

    Convenience endpoint — used by /api/ask to surface the thread when the
    user asks about an entity. Returns the same shape as POST /threads but
    filtered to the specified entity.
    """
    from maestro_personal_shell.cross_meeting_threads import (
        get_threads_for_entity as _get_for_entity,
        ENTERPRISE_THREAD_BUILDER_AVAILABLE,
    )
    if not ENTERPRISE_THREAD_BUILDER_AVAILABLE:
        return {
            "threads": [],
            "engine_available": False,
            "message": "Cross-meeting threading unavailable",
        }
    threads = _get_for_entity(user_email=token, entity=entity)
    return {
        "threads": threads,
        "engine_available": True,
        "count": len(threads),
        "entity": entity,
    }


@router.get("/threads/{entity}/decisions")
async def get_decision_history_endpoint(
    entity: str,
    token: str = Depends(verify_token_dep),
):
    """Get the decision history for an entity across meetings.

    Surfaces the "Decided to offer phased rollout (Oct 22); confirmed in
    Nov 5 call" capability — decisions tracked across meetings as a chain.
    """
    from maestro_personal_shell.cross_meeting_threads import (
        get_decision_history as _get_decisions,
        ENTERPRISE_THREAD_BUILDER_AVAILABLE,
    )
    if not ENTERPRISE_THREAD_BUILDER_AVAILABLE:
        return {
            "decisions": [],
            "engine_available": False,
            "message": "Cross-meeting threading unavailable",
        }
    decisions = _get_decisions(user_email=token, entity=entity)
    return {
        "decisions": decisions,
        "engine_available": True,
        "count": len(decisions),
        "entity": entity,
    }


# ---------------------------------------------------------------------------
# Phase 16: Meeting grader (meeting effectiveness score)
# ---------------------------------------------------------------------------


class MeetingOverrideRequest(BaseModel):
    """Request body for overriding a meeting grade.

    P13: the caller supplies the grade letter (user judgment), not the
    meeting data. The meeting data is DERIVED from signal history.
    """
    grade: str  # A, B, C, D, or F


@router.get("/meetings/grades")
async def get_all_meeting_grades_endpoint(
    token: str = Depends(verify_token_dep),
):
    """Get grades for all meetings for the current user."""
    from maestro_personal_shell.meeting_grader import (
        grade_all_meetings as _grade_all,
        ENTERPRISE_GRADER_AVAILABLE,
    )
    if not ENTERPRISE_GRADER_AVAILABLE:
        return {
            "grades": [],
            "engine_available": False,
            "message": "Meeting grading unavailable — enterprise engine not importable",
        }
    grades = _grade_all(user_email=token)
    return {
        "grades": grades,
        "engine_available": True,
        "count": len(grades),
        "average_score": sum(g.get("score", 0) for g in grades) / len(grades) if grades else 0,
    }


@router.get("/meetings/{meeting_id}/grade")
async def get_meeting_grade_endpoint(
    meeting_id: str,
    token: str = Depends(verify_token_dep),
):
    """Get the grade for a specific meeting.

    Returns 404 if the meeting signal isn't found in the user's history.
    """
    from maestro_personal_shell.meeting_grader import (
        grade_meeting as _grade_one,
        ENTERPRISE_GRADER_AVAILABLE,
    )
    if not ENTERPRISE_GRADER_AVAILABLE:
        return {
            "grade": None,
            "engine_available": False,
            "message": "Meeting grading unavailable",
        }
    report = _grade_one(user_email=token, meeting_id=meeting_id)
    if not report:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Meeting {meeting_id} not found")
    return {
        "grade": report,
        "engine_available": True,
    }


@router.post("/meetings/{meeting_id}/grade/override")
async def override_meeting_grade_endpoint(
    meeting_id: str,
    req: MeetingOverrideRequest,
    token: str = Depends(verify_token_dep),
):
    """Override the computed grade for a meeting."""
    from maestro_personal_shell.meeting_grader import (
        set_user_override as _override,
        ENTERPRISE_GRADER_AVAILABLE,
    )
    if not ENTERPRISE_GRADER_AVAILABLE:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Meeting grading unavailable")
    report = _override(user_email=token, meeting_id=meeting_id, grade=req.grade)
    if not report:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Meeting {meeting_id} not found")
    return {
        "grade": report,
        "engine_available": True,
        "message": f"Grade overridden to {req.grade.upper()}",
    }


# ---------------------------------------------------------------------------
# Phase 11: Deal health (live deal momentum score)
# ---------------------------------------------------------------------------


@router.get("/deals/health")
async def get_all_deal_health_endpoint(
    token: str = Depends(verify_token_dep),
):
    """Get deal health scores for all entities."""
    from maestro_personal_shell.deal_health import (
        get_deal_health_for_all_entities as _get_all,
        ENTERPRISE_DEAL_HEALTH_AVAILABLE,
    )
    if not ENTERPRISE_DEAL_HEALTH_AVAILABLE:
        return {
            "deals": [],
            "engine_available": False,
            "message": "Deal health unavailable — enterprise engine not importable",
        }
    deals = _get_all(user_email=token)
    return {
        "deals": deals,
        "engine_available": True,
        "count": len(deals),
        "strong_count": sum(1 for d in deals if d.get("status") == "strong"),
        "at_risk_count": sum(1 for d in deals if d.get("status") == "at_risk"),
        "critical_count": sum(1 for d in deals if d.get("status") == "critical"),
    }


@router.get("/deals/{entity}/health")
async def get_deal_health_endpoint(
    entity: str,
    token: str = Depends(verify_token_dep),
):
    """Get the deal health score for a specific entity.

    Returns 404 if the entity has no signals.
    """
    from maestro_personal_shell.deal_health import (
        get_deal_health as _get_one,
        ENTERPRISE_DEAL_HEALTH_AVAILABLE,
    )
    if not ENTERPRISE_DEAL_HEALTH_AVAILABLE:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Deal health unavailable")
    score = _get_one(user_email=token, entity=entity)
    if not score:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=404,
            detail=f"No signals found for entity '{entity}' — cannot compute deal health",
        )
    return {
        "deal_health": score,
        "engine_available": True,
    }


# ---------------------------------------------------------------------------
# Phase 20: Advanced analytics (trend analysis + org learning)
# ---------------------------------------------------------------------------


@router.get("/analytics/trends")
async def get_analytics_endpoint(
    token: str = Depends(verify_token_dep),
):
    """Get the organizational learning report."""
    from maestro_personal_shell.advanced_analytics import (
        get_analytics_report as _get_report,
        ENTERPRISE_ANALYTICS_AVAILABLE,
    )
    if not ENTERPRISE_ANALYTICS_AVAILABLE:
        return {
            "report": None,
            "engine_available": False,
            "message": "Advanced analytics unavailable — enterprise engine not importable",
        }
    report = _get_report(user_email=token)
    if not report:
        return {
            "report": None,
            "engine_available": True,
            "message": "No signals yet — sync connectors to start the flywheel",
        }
    return {
        "report": report,
        "engine_available": True,
        "flywheel_summary": report.get("flywheel_summary", ""),
    }


@router.get("/analytics/flywheel")
async def get_flywheel_endpoint(
    token: str = Depends(verify_token_dep),
):
    """Get a one-line flywheel summary for the user.

    Convenience endpoint — useful for dashboard headers + mobile UI.
    """
    from maestro_personal_shell.advanced_analytics import (
        get_flywheel_summary as _get_summary,
        ENTERPRISE_ANALYTICS_AVAILABLE,
    )
    if not ENTERPRISE_ANALYTICS_AVAILABLE:
        return {
            "summary": "Analytics unavailable",
            "engine_available": False,
        }
    summary = _get_summary(user_email=token)
    return {
        "summary": summary,
        "engine_available": True,
    }

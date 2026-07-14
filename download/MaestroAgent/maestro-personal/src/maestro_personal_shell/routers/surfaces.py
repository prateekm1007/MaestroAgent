"""Surfaces router — the heavy "surface" endpoints.

Extracted from api.py during the Phase 8 router split. These endpoints
(briefing, the-moment, what-changed, prepare, whisper) are listed in the
task spec as belonging to the account grouping, but their combined size
(~630 lines) would push account.py over the 800-line limit. They live
here in surfaces.py and mount at the same /api prefix.

No behavior changes — same paths, same response schemas, same filters.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel

from maestro_personal_shell.models import (
    PrepareResponse,
    WhatChangedMasterpieceResponse,
    WhatChangedResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["surfaces"])


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
    material_changes: list[str] = []
    unknowns: list[str] = []
    disputes: list[dict[str, Any]] = []
    can_decide_now: list[str] = []
    cannot_decide_yet: list[str] = []
    why_boundary: str = ""
    next_step: str = ""
    belief: str = ""
    why_belief: str = ""
    what_would_change_belief: str = ""
    watching_quietly: list[dict[str, Any]] = []
    ask_prompt: str = ""


class TheMomentResponse(BaseModel):
    """The single most important thing Maestro knows right now."""
    has_moment: bool
    commitment: dict[str, Any] | None = None
    situation: dict[str, Any] | None = None
    why_this_one: str = ""
    source_evidence: list[dict[str, Any]] = []


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
    """Get recent meaningful deltas."""
    from maestro_personal_shell.api import build_shell
    shell = build_shell(user_email=token, as_of=as_of)
    from maestro_personal_shell.surfaces.what_changed import WhatChangedSurface
    surface = WhatChangedSurface(shell=shell)
    since = datetime.now(timezone.utc) - timedelta(days=30)
    deltas = surface.get_recent_deltas(since_timestamp=since)
    return [
        WhatChangedResponse(
            entity=d["entity"], text=d["text"], type=d["type"],
            is_meaningful=d["is_meaningful"],
        )
        for d in deltas
    ]


@router.get("/what-changed/the-shifts", response_model=WhatChangedMasterpieceResponse)
async def get_the_shifts(token: str = Depends(verify_token_dep)):
    """The 2 things that materially shifted — not a feed."""
    from maestro_personal_shell.api import build_shell
    shell = build_shell(user_email=token)
    from maestro_personal_shell.surfaces.what_changed import WhatChangedSurface
    surface = WhatChangedSurface(shell=shell)
    since = datetime.now(timezone.utc) - timedelta(days=30)
    deltas = surface.get_recent_deltas(since_timestamp=since)
    meaningful = [d for d in deltas if d.get("is_meaningful")]
    if not meaningful:
        return WhatChangedMasterpieceResponse(
            the_shifts=[],
            silence_message="Nothing material changed since you last looked."
        )
    the_shifts = meaningful[:2]
    return WhatChangedMasterpieceResponse(
        the_shifts=[
            WhatChangedResponse(
                entity=d["entity"], text=d["text"], type=d["type"],
                is_meaningful=d["is_meaningful"],
            )
            for d in the_shifts
        ],
        silence_message="",
    )


# ---------------------------------------------------------------------------
# GET /prepare — Prepare surface (3 things that matter)
# ---------------------------------------------------------------------------


@router.get("/prepare", response_model=list[PrepareResponse])
async def get_prepare(as_of: str | None = None, token: str = Depends(verify_token_dep)):
    """Get preparation for upcoming situations — 3 things that matter."""
    from maestro_personal_shell.api import build_shell, _filter_corrected_signals
    shell = build_shell(user_email=token, as_of=as_of)
    core = shell.core
    from maestro_personal_shell.surfaces.prepare import PrepareSurface
    surface = PrepareSurface(shell=shell)
    situations = surface.get_situations_needing_preparation()
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

        # THE FORGOTTEN: oldest commitment_made signal
        the_forgotten = ""
        commitment_signals = [
            sig for sig in entity_signals
            if "commitment" in str(getattr(sig, "signal_type", "")).lower()
        ]
        if commitment_signals:
            commitment_signals.sort(key=lambda x: getattr(x, "timestamp", datetime.max))
            the_forgotten = getattr(commitment_signals[0], "text", "")

        # THE OPEN QUESTION: follow_up.required signal
        the_open_question = ""
        followup_signals = [
            sig for sig in entity_signals
            if "follow_up" in str(getattr(sig, "signal_type", "")).lower()
        ]
        if followup_signals:
            the_open_question = getattr(followup_signals[-1], "text", "")

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

        result.append(PrepareResponse(
            situation_id=sit_id, entity=entity, meeting_context=meeting_context,
            is_stale=is_stale, the_forgotten=the_forgotten,
            the_open_question=the_open_question, the_contradiction=the_contradiction,
            copilot_talking_points=copilot_talking_points,
            copilot_blocking_unknowns=copilot_blocking_unknowns,
            copilot_can_decide=copilot_can_decide,
            copilot_cannot_decide=copilot_cannot_decide,
            copilot_timeline=copilot_timeline,
        ))
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
_ALWAYS_WHISPER_TYPES = frozenset({
    "critical_signal",      # lawsuit, churn, breach, outage — BYPASSES gate (F6)
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
    """Rule-based early-exit for the whisper materiality gate.

    Returns:
        True  — always whisper (skip LLM gate)
        False — never whisper (skip LLM gate)
        None  — borderline, let LLM gate decide

    F6 guard: critical_signal whispers ALWAYS fire (emergencies never
    suppressed). All other types go through the gate so the learning
    loop can learn from dismissals.
    """
    w_type = w.get("type", "")
    w_priority = str(w.get("priority", "")).lower()

    # 1. Critical/high-priority whispers ALWAYS fire — emergencies don't
    #    need a materiality gate to decide if they're worth surfacing.
    #    F6 guard: critical_signal type bypasses the gate entirely.
    if w_type in _ALWAYS_WHISPER_TYPES:
        return True

    # 2. Low-value types NEVER fire — these are noise
    if w_type in _NEVER_WHISPER_TYPES:
        return False

    # 3. All other types (including stale_commitment, broken_commitment,
    #    deadline_approaching, contradiction_detected) go through the gate.
    #    The gate learns from dismissals — if we skip it here, the learning
    #    loop can't learn to suppress these. (F5 regression fix.)
    return None


@router.get("/whisper", response_model=list[WhisperResponse])
async def get_whispers(token: str = Depends(verify_token_dep)):
    """Get active whispers — things that deserve attention RIGHT NOW.

    DEPTH: calls Core's WhisperSituationBridge.from_situation() for each
    situation. Empty list = trusted silence.
    """
    from maestro_personal_shell.api import build_shell
    shell = build_shell(user_email=token, signal_limit=500)
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

    return result


# ---------------------------------------------------------------------------
# GET /briefing — Morning briefing
# ---------------------------------------------------------------------------


@router.get("/briefing", response_model=BriefingResponse)
async def get_briefing(token: str = Depends(verify_token_dep)):
    """Morning briefing — the full Situation-centric intelligence."""
    from maestro_personal_shell.api import build_shell
    shell = build_shell(user_email=token)
    core = shell.core
    if not core.briefing_bridge:
        return BriefingResponse(
            greeting="Good morning. Briefing engine unavailable.",
            ask_prompt="What do you want to understand?",
        )
    try:
        briefing = core.briefing_bridge.generate_morning_briefing(
            user_email="personal", org_id="personal",
        )
        return BriefingResponse(
            greeting=getattr(briefing, "greeting", ""),
            top_situation=getattr(briefing, "top_situation", None),
            material_changes=getattr(briefing, "material_changes", []) or [],
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
        )
    except Exception as e:
        logger.debug("Briefing generation failed: %s", e)
        return BriefingResponse(greeting="Good morning.", ask_prompt="What do you want to understand?")


# ---------------------------------------------------------------------------
# GET /briefing/evening — Evening briefing
# ---------------------------------------------------------------------------


@router.get("/briefing/evening", response_model=BriefingResponse)
async def get_evening_briefing(token: str = Depends(verify_token_dep)):
    """Evening briefing — what happened today, what's pending."""
    from maestro_personal_shell.api import build_shell
    shell = build_shell(user_email=token)
    core = shell.core
    if not core.briefing_bridge:
        return BriefingResponse(
            greeting="Good evening. Briefing engine unavailable.",
            ask_prompt="What do you want to understand?",
        )
    try:
        briefing = core.briefing_bridge.generate_evening_briefing(
            user_email="personal", org_id="personal",
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
                noise_name_patterns = ("newsletter", "news corp", "digest", "fyi", "notification")
                if any(pat in top_entity for pat in noise_name_patterns):
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
        )
    except Exception as e:
        logger.debug("Evening briefing failed: %s", e)
        return BriefingResponse(greeting="Good evening.", ask_prompt="What do you want to understand?")


# ---------------------------------------------------------------------------
# GET /the-moment — THE MASTERPIECE ENDPOINT
# ---------------------------------------------------------------------------


@router.get("/the-moment", response_model=TheMomentResponse)
async def get_the_moment(as_of: str | None = None, token: str = Depends(verify_token_dep)):
    """The single most important thing Maestro knows right now.

    The Spotlight moment — the one commitment that matters most. Not a list.
    If nothing deserves attention, returns has_moment=False.
    """
    from maestro_personal_shell.api import (
        build_shell,
        _filter_completed_commitments,
        _filter_dismissed_commitments,
        _filter_non_commitments_by_classification,
    )
    shell = build_shell(user_email=token, as_of=as_of)
    from maestro_personal_shell.surfaces.commitments import CommitmentsSurface
    surface = CommitmentsSurface(shell=shell)
    commitments = surface.get_active_commitments()
    commitments = _filter_completed_commitments(commitments, shell.oem_state.signals)
    commitments = _filter_dismissed_commitments(commitments, shell.oem_state.signals)
    commitments = _filter_non_commitments_by_classification(commitments, shell.oem_state.signals)

    if not commitments:
        return TheMomentResponse(has_moment=False)

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
            except Exception:
                pass
        if score > best_score:
            best_score = score
            best_commitment = c
            best_why = "; ".join(reasons) if reasons else "active commitment"

    if not best_commitment:
        return TheMomentResponse(has_moment=False)

    # Phase 3.1: LLM-powered Trusted Silence (Materiality Gate)
    try:
        from maestro_personal_shell.dynamic_agents import materiality_gate_v2
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
            except Exception:
                pass

        materiality = await materiality_gate_v2(best_commitment, mat_context, user_email=token)

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
        except Exception:
            pass

        if not materiality.get("should_speak", True):
            return TheMomentResponse(
                has_moment=False,
                why_this_one=f"Trusted silence: {materiality.get('reasoning', 'low materiality')}",
            )
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

    return TheMomentResponse(
        has_moment=True,
        commitment={
            "entity": best_commitment.get("entity", ""),
            "text": best_commitment.get("text", ""),
            "claim_type": str(best_commitment.get("claim_type", "commitment")),
            "signal_id": best_commitment.get("signal_id", ""),
            "timestamp": str(best_commitment.get("timestamp", "")),
        },
        situation=related_situation,
        why_this_one=best_why,
        source_evidence=source_evidence,
    )

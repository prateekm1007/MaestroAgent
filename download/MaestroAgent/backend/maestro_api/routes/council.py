"""
Maestro Cognitive Council — Production API Routes.

These routes wire the Cognitive Council bridges into the actual API,
making the Situation Engine the substrate for Ask, Briefing, Prepare,
Whisper, and Copilot.

Per the external audit (C-A): "the maestro_cognitive_council package is
imported by zero production modules." This file fixes that — it imports
and calls every bridge from real API routes.

The old OEM routes (oem.py /api/oem/ask, /api/oem/whisper, etc.) remain
for backward compatibility. The new /api/council/* routes use the
Situation-aware bridges.

All routes require USER auth (Depends(require_user)) + @auth_policy.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from maestro_api.security.policy import auth_policy, AuthPolicy, set_router_policy

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/council", tags=["cognitive-council"])
set_router_policy(router, AuthPolicy.USER)

# Persistent Situation Store — survives across requests (fixes audit finding:
# "No persistent Situation store — rebuilds per request")
_situation_store = None

def _get_situation_store():
    global _situation_store
    if _situation_store is None:
        from maestro_cognitive_council import SituationStore
        db_path = os.environ.get("MAESTRO_SITUATION_DB", "situations.db")
        _situation_store = SituationStore(db_path=db_path)
        logger.info("SituationStore initialized (db=%s)", db_path)
    return _situation_store


def _require_user_if_auth_enabled(request: Request) -> dict[str, Any]:
    """Auth dependency that's bypassed in local dev mode."""
    from maestro_auth.permissions import is_auth_enabled, current_user
    if not is_auth_enabled():
        return {"user": {"email": "dev@local", "id": "dev"}, "org_id": "default"}
    result = current_user(request)
    if not result:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return result


def _safe_json(obj: Any) -> Any:
    """Recursively stringify UUIDs in a response payload.

    Audit C-A fix: real OEM signal_ids are UUID-typed, and even though
    situation_engine.py now stringifies them at the source, defense-in-depth
    at the API boundary guarantees no UUID ever reaches FastAPI's JSON
    encoder. This is the third line of defense (after engine source fix
    and SituationStore._stringify_uuids).

    Calling this on every to_dict() return value is cheap (it's a no-op
    for already-string data) and prevents the entire class of "Object of
    type UUID is not JSON serializable" 500 errors.
    """
    try:
        from maestro_cognitive_council.situation_store import _stringify_uuids
        return _stringify_uuids(obj)
    except ImportError:
        return obj


# ════════════════════════════════════════════════════════════════════════════
# Ask → Situation Engine
# ════════════════════════════════════════════════════════════════════════════

class AskRequest(BaseModel):
    query: str
    org_id: str = "default"


@router.post("/ask")
@auth_policy(AuthPolicy.USER)
async def council_ask(
    req: AskRequest,
    user: dict = Depends(_require_user_if_auth_enabled),
) -> dict[str, Any]:
    """Situation-aware Ask — retrieves the correct Situation, not just OEM signals.

    This route IMPORTS and CALLS SituationAwareAskBridge from the Cognitive
    Council. The old /api/oem/ask route remains for backward compatibility.

    The bridge:
      1. Detects the entity from the query
      2. Finds the relevant LivingSituation
      3. Reconstructs chronology
      4. Distinguishes fact from report (epistemic states)
      5. Surfaces unknowns
      6. Preserves disagreements
      7. Cites evidence by reference
    """
    try:
        from maestro_cognitive_council import SituationAwareAskBridge, SituationEngine
        from maestro_api.oem_state import oem_state

        org_id = req.org_id or user.get("org_id", "default")
        store = _get_situation_store()
        engine = SituationEngine(oem_state=oem_state, situation_store=store)
        engine.detect_situations(org_id)
        bridge = SituationAwareAskBridge(oem_state=oem_state)
        result = bridge.ask(req.query, org_id=org_id)
        return _safe_json(result.to_dict())
    except Exception as e:
        logger.error(f"Council ask failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Council ask failed: {e}")


# ════════════════════════════════════════════════════════════════════════════
# Briefing → Situation Judgment
# ════════════════════════════════════════════════════════════════════════════

class BriefingRequest(BaseModel):
    user_email: str = ""
    org_id: str = "default"
    briefing_type: str = "morning"  # "morning" | "evening"


@router.post("/briefing")
@auth_policy(AuthPolicy.USER)
async def council_briefing(
    req: BriefingRequest,
    user: dict = Depends(_require_user_if_auth_enabled),
) -> dict[str, Any]:
    """Situation-centric briefing — "What materially changed?"

    NOT "How many insights did each agent produce?" (the old Nerve briefing).
    This route uses SituationBriefingEngine which:
      1. Finds the top situation needing judgment
      2. Includes material changes, unknowns, disputes
      3. Produces the decision boundary
      4. States what Maestro believes + why + what would change that
      5. Lists situations being watched quietly
    """
    try:
        from maestro_cognitive_council import SituationBriefingEngine
        from maestro_api.oem_state import oem_state

        org_id = req.org_id or user.get("org_id", "default")
        user_email = req.user_email or user.get("email", "")
        engine = SituationBriefingEngine(oem_state=oem_state)

        if req.briefing_type == "evening":
            briefing = engine.generate_evening_briefing(user_email=user_email, org_id=org_id)
        else:
            briefing = engine.generate_morning_briefing(user_email=user_email, org_id=org_id)

        return _safe_json(briefing.to_dict())
    except Exception as e:
        logger.error(f"Council briefing failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Council briefing failed: {e}")


# ════════════════════════════════════════════════════════════════════════════
# Prepare → LivingSituation
# ════════════════════════════════════════════════════════════════════════════

class PrepareRequest(BaseModel):
    situation_id: str = ""
    org_id: str = "default"


@router.post("/prepare")
@auth_policy(AuthPolicy.USER)
async def council_prepare(
    req: PrepareRequest,
    user: dict = Depends(_require_user_if_auth_enabled),
) -> dict[str, Any]:
    """Situation-aware preparation — prepare FOR a specific Situation.

    Surfaces:
      - Unknowns that must be resolved before the event
      - Decision boundary (what can/cannot be decided)
      - Learned insights from the Behavioral Learning Engine
      - Stale detection (has reality changed since preparation?)
      - Questions to ask in the meeting
    """
    try:
        from maestro_cognitive_council import SituationPreparationBridge, SituationEngine
        from maestro_api.oem_state import oem_state

        org_id = req.org_id or user.get("org_id", "default")
        engine = SituationEngine(oem_state=oem_state, situation_store=_get_situation_store())
        engine.detect_situations(org_id)
        bridge = SituationPreparationBridge(oem_state=oem_state, situation_engine=engine)

        if req.situation_id:
            prep = bridge.prepare_for_situation(req.situation_id, org_id=org_id)
        else:
            # Prepare for all upcoming situations
            preps = bridge.prepare_for_upcoming_meetings(org_id=org_id)
            return {
                "preparations": [_safe_json(p.to_dict()) for p in preps],
                "count": len(preps),
            }

        return _safe_json(prep.to_dict())
    except Exception as e:
        logger.error(f"Council prepare failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Council prepare failed: {e}")


# ════════════════════════════════════════════════════════════════════════════
# Whisper → Delivery Governor
# ════════════════════════════════════════════════════════════════════════════

class WhisperRequest(BaseModel):
    entity: str = ""
    context: str = ""  # "meeting" | "review" | "decision"
    org_id: str = "default"
    is_in_meeting: bool = False
    is_in_focus_mode: bool = False
    is_doing_morning_review: bool = False
    fatigue_level: float = 0.0


@router.post("/whisper")
@auth_policy(AuthPolicy.USER)
async def council_whisper(
    req: WhisperRequest,
    user: dict = Depends(_require_user_if_auth_enabled),
) -> dict[str, Any]:
    """Situation-aware Whisper — routed through the Delivery Governor.

    Uses the opportunity cost model (intervention value vs interruption cost).
    Explains WHY it's silent. References evidence by reference (not copies).
    Applies fatigue caps on batch routing.
    """
    try:
        from maestro_cognitive_council import (
            WhisperSituationBridge, SituationEngine, UserContext,
        )
        from maestro_api.oem_state import oem_state

        org_id = req.org_id or user.get("org_id", "default")
        engine = SituationEngine(oem_state=oem_state, situation_store=_get_situation_store())
        situations = engine.detect_situations(org_id)

        # Find situation for the requested entity
        situation = None
        if req.entity:
            for s in situations:
                if s.entity.lower() == req.entity.lower():
                    situation = s
                    break

        if not situation and situations:
            situation = situations[0]  # default to first

        if not situation:
            return {
                "delivery_route": "silent",
                "suppression_reason": "No active situations detected.",
                "whispers": [],
            }

        bridge = WhisperSituationBridge()
        user_context = UserContext(
            is_in_meeting=req.is_in_meeting,
            is_in_focus_mode=req.is_in_focus_mode,
            is_doing_morning_review=req.is_doing_morning_review,
            fatigue_level=req.fatigue_level,
        )

        result = bridge.from_situation(situation, context=req.context, user_context=user_context)
        return _safe_json(result.to_dict())
    except Exception as e:
        logger.error(f"Council whisper failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Council whisper failed: {e}")


# ════════════════════════════════════════════════════════════════════════════
# Copilot → Situation Engine
# ════════════════════════════════════════════════════════════════════════════

class CopilotPreCallRequest(BaseModel):
    meeting_title: str = ""
    attendees: list[str] = []
    user_email: str = ""
    org_id: str = "default"


@router.post("/copilot/pre-call")
@auth_policy(AuthPolicy.USER)
async def council_copilot_pre_call(
    req: CopilotPreCallRequest,
    user: dict = Depends(_require_user_if_auth_enabled),
) -> dict[str, Any]:
    """Situation-aware pre-call briefing from the Copilot bridge.

    Finds the relevant Situation, surfaces its unknowns, decision boundary,
    and talking points — referencing evidence_refs (not copies).
    """
    try:
        from maestro_cognitive_council import CopilotSituationBridge
        from maestro_api.oem_state import oem_state

        org_id = req.org_id or user.get("org_id", "default")
        user_email = req.user_email or user.get("email", "")
        bridge = CopilotSituationBridge(oem_state=oem_state)
        briefing = bridge.pre_call_briefing(
            meeting_title=req.meeting_title,
            attendees=req.attendees,
            user_email=user_email,
            org_id=org_id,
        )
        return _safe_json(briefing.to_dict())
    except Exception as e:
        logger.error(f"Council copilot pre-call failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Council copilot pre-call failed: {e}")


class CopilotPostCallRequest(BaseModel):
    situation_id: str = ""
    transcript_chunks: list[dict] = []
    commitments: list[dict] = []
    entity: str = ""
    org_id: str = "default"


@router.post("/copilot/post-call")
@auth_policy(AuthPolicy.USER)
async def council_copilot_post_call(
    req: CopilotPostCallRequest,
    user: dict = Depends(_require_user_if_auth_enabled),
) -> dict[str, Any]:
    """Situation-aware post-call summary from the Copilot bridge.

    Transitions operational state (ACTION_IN_PROGRESS → AWAITING_OUTCOME),
    ingests commitments as refs, triggers the Behavioral Learning Engine,
    and generates a draft follow-up citing evidence_refs.
    """
    try:
        from maestro_cognitive_council import CopilotSituationBridge, SituationEngine
        from maestro_api.oem_state import oem_state

        org_id = req.org_id or user.get("org_id", "default")
        engine = SituationEngine(oem_state=oem_state, situation_store=_get_situation_store())
        engine.detect_situations(org_id)
        bridge = CopilotSituationBridge(oem_state=oem_state, situation_engine=engine)

        summary = bridge.post_call_summary(
            situation_id=req.situation_id,
            transcript_chunks=req.transcript_chunks,
            commitments=req.commitments,
            entity=req.entity,
        )
        return _safe_json(summary.to_dict())
    except Exception as e:
        logger.error(f"Council copilot post-call failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Council copilot post-call failed: {e}")


# ════════════════════════════════════════════════════════════════════════════
# Situations — list/get active situations
# ════════════════════════════════════════════════════════════════════════════

@router.get("/situations")
@auth_policy(AuthPolicy.USER)
async def council_situations(
    user: dict = Depends(_require_user_if_auth_enabled),
    org_id: str = Query("default", description="Tenant scope"),
) -> dict[str, Any]:
    """List all active situations for the org."""
    try:
        from maestro_cognitive_council import SituationEngine
        from maestro_api.oem_state import oem_state

        org = org_id or user.get("org_id", "default")
        engine = SituationEngine(oem_state=oem_state, situation_store=_get_situation_store())
        situations = engine.detect_situations(org)
        return {
            "situations": [_safe_json(s.to_dict()) for s in situations],
            "count": len(situations),
        }
    except Exception as e:
        logger.error(f"Council situations failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Council situations failed: {e}")


@router.get("/situations/{situation_id}")
@auth_policy(AuthPolicy.USER)
async def council_get_situation(
    situation_id: str,
    user: dict = Depends(_require_user_if_auth_enabled),
    org_id: str = Query("default"),
) -> dict[str, Any]:
    """Get a specific situation by ID."""
    try:
        from maestro_cognitive_council import SituationEngine
        from maestro_api.oem_state import oem_state

        org = org_id or user.get("org_id", "default")
        engine = SituationEngine(oem_state=oem_state, situation_store=_get_situation_store())
        engine.detect_situations(org)
        situation = engine.get_situation(situation_id)
        if not situation:
            raise HTTPException(status_code=404, detail=f"Situation {situation_id} not found")
        return _safe_json(situation.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Council get situation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Council get situation failed: {e}")


# ════════════════════════════════════════════════════════════════════════════
# N2: Governance operator surface
# ════════════════════════════════════════════════════════════════════════════

_governance_surface = None

def _get_governance_surface():
    global _governance_surface
    if _governance_surface is None:
        from maestro_cognitive_council import GovernanceOperatorSurface
        _governance_surface = GovernanceOperatorSurface()
    return _governance_surface


class GovernanceActionRequest(BaseModel):
    pattern_id: str
    action: str  # promote | suspend | falsify | narrow_scope | expand_scope | override
    reason: str = ""
    operator: str = ""
    scope: dict = {}
    current_scope: str = ""
    requested_scope: str = ""
    evidence_in_new_scope: list[dict] = []
    decision: str = ""


@router.post("/governance/action")
@auth_policy(AuthPolicy.ADMIN)
async def council_governance_action(
    req: GovernanceActionRequest,
    user: dict = Depends(_require_user_if_auth_enabled),
) -> dict[str, Any]:
    """N2: Take a governance action on a pattern.

    N1 FIX (delta audit): Changed from AuthPolicy.USER to AuthPolicy.ADMIN.
    Per audit: "Any authenticated user can falsify/suspend/promote patterns.
    Change to AuthPolicy.ADMIN before pilot."
    Only admins can take governance actions (promote/suspend/falsify/etc).
    Every action is auditable.
    """
    try:
        from maestro_cognitive_council import (
            GovernanceOperatorSurface, ScopeExpansionRequest, can_expand_scope,
        )
        surface = _get_governance_surface()
        operator = req.operator or user.get("email", "unknown")

        if req.action == "suspend":
            action = surface.suspend_pattern(req.pattern_id, operator, req.reason)
        elif req.action == "falsify":
            action = surface.falsify_pattern(req.pattern_id, operator, req.reason)
        elif req.action == "promote":
            action = surface.promote_pattern(req.pattern_id, operator, req.reason)
        elif req.action == "narrow_scope":
            action = surface.narrow_scope(req.pattern_id, req.scope, operator, req.reason)
        elif req.action == "expand_scope":
            scope_req = ScopeExpansionRequest(
                pattern_id=req.pattern_id,
                current_scope=req.current_scope,
                requested_scope=req.requested_scope,
                evidence_in_new_scope=req.evidence_in_new_scope,
            )
            action = surface.expand_scope(scope_req, operator)
        elif req.action == "override":
            action = surface.override(req.pattern_id, req.decision, operator, req.reason)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {req.action}")

        return _safe_json(action.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Governance action failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Governance action failed: {e}")


@router.get("/governance/audit-log")
@auth_policy(AuthPolicy.USER)
async def council_governance_audit_log(
    user: dict = Depends(_require_user_if_auth_enabled),
) -> dict[str, Any]:
    """N2: Get the full audit log of all governance actions."""
    try:
        surface = _get_governance_surface()
        return {
            "actions": surface.get_audit_log(),
            "count": len(surface.get_audit_log()),
        }
    except Exception as e:
        logger.error(f"Governance audit log failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Governance audit log failed: {e}")


@router.get("/governance/patterns")
@auth_policy(AuthPolicy.USER)
async def council_governance_patterns(
    user: dict = Depends(_require_user_if_auth_enabled),
) -> dict[str, Any]:
    """N2: List all patterns for operator review."""
    try:
        from maestro_cognitive_council import GovernanceOperatorSurface
        surface = _get_governance_surface()
        # Get candidate store from app state
        try:
            from maestro_api.oem_state import oem_state
            candidate_store = getattr(oem_state, "_candidate_pattern_store", None)
        except ImportError:
            candidate_store = None

        patterns = surface.review_patterns(candidate_store) if candidate_store else []
        return {"patterns": patterns, "count": len(patterns)}
    except Exception as e:
        logger.error(f"Governance patterns failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Governance patterns failed: {e}")

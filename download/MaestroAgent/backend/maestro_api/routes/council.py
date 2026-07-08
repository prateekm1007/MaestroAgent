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
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from maestro_api.security.policy import auth_policy, AuthPolicy, set_router_policy

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/council", tags=["cognitive-council"])
set_router_policy(router, AuthPolicy.USER)


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
        from maestro_cognitive_council import SituationAwareAskBridge
        from maestro_api.oem_state import oem_state

        org_id = req.org_id or user.get("org_id", "default")
        bridge = SituationAwareAskBridge(oem_state=oem_state)
        result = bridge.ask(req.query, org_id=org_id)
        return result.to_dict()
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

        return briefing.to_dict()
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
        engine = SituationEngine(oem_state=oem_state)
        engine.detect_situations(org_id)
        bridge = SituationPreparationBridge(oem_state=oem_state, situation_engine=engine)

        if req.situation_id:
            prep = bridge.prepare_for_situation(req.situation_id, org_id=org_id)
        else:
            # Prepare for all upcoming situations
            preps = bridge.prepare_for_upcoming_meetings(org_id=org_id)
            return {
                "preparations": [p.to_dict() for p in preps],
                "count": len(preps),
            }

        return prep.to_dict()
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
        engine = SituationEngine(oem_state=oem_state)
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
        return result.to_dict()
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
        return briefing.to_dict()
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
        engine = SituationEngine(oem_state=oem_state)
        engine.detect_situations(org_id)
        bridge = CopilotSituationBridge(oem_state=oem_state, situation_engine=engine)

        summary = bridge.post_call_summary(
            situation_id=req.situation_id,
            transcript_chunks=req.transcript_chunks,
            commitments=req.commitments,
            entity=req.entity,
        )
        return summary.to_dict()
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
        engine = SituationEngine(oem_state=oem_state)
        situations = engine.detect_situations(org)
        return {
            "situations": [s.to_dict() for s in situations],
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
        engine = SituationEngine(oem_state=oem_state)
        engine.detect_situations(org)
        situation = engine.get_situation(situation_id)
        if not situation:
            raise HTTPException(status_code=404, detail=f"Situation {situation_id} not found")
        return situation.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Council get situation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Council get situation failed: {e}")

"""Copilot router — live-call intelligence, playbooks, shadow mode.

Extracted from api.py during the Phase 8 router split. No behavior
changes — same paths, same request/response schemas, same auth.

The WebSocket handler (/ws/copilot) stays in api.py because it uses
internal state and `app.add_api_websocket_route` directly (not a
router decorator). The REST endpoints here all use the same
verify_token dependency as the inline versions did.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/copilot", tags=["copilot"])


# ---------------------------------------------------------------------------
# verify_token lazy proxy (see routers/auth.py for rationale)
# ---------------------------------------------------------------------------


async def verify_token_dep(authorization: str = Header(None)) -> str:
    """Lazy proxy to api.verify_token — decouples this router from api.py's load order."""
    from maestro_personal_shell.api import verify_token
    return await verify_token(authorization=authorization)


# ---------------------------------------------------------------------------
# Pydantic models — moved here from api.py (router-specific)
# ---------------------------------------------------------------------------


class TranscriptChunkRequest(BaseModel):
    # P1-Audit-F10 fix: situation_id is now optional. When omitted, the
    # endpoint auto-binds a situation from the entity field.
    situation_id: str = ""
    text: str
    speaker: str = ""
    entity: str = ""


class PostCallSummaryRequest(BaseModel):
    situation_id: str = ""  # P1-Audit-F10: optional — auto-bound from entity
    transcript_chunks: list[dict[str, Any]] = []
    commitments: list[dict[str, Any]] = []
    entity: str = ""


class FollowUpEmailRequest(BaseModel):
    meeting_title: str = ""
    participants: list[str] = []
    commitments: list[dict[str, Any]] = []
    objections: list[dict[str, Any]] = []
    entity: str = ""
    transcript_chunks: list[dict[str, Any]] = []
    tone: str = ""  # professional | warm | direct (auto-inferred if empty)


class PreCallIntelRequest(BaseModel):
    entity: str = ""
    meeting_title: str = ""


class PostCallSummaryUIRequest(BaseModel):
    meeting_title: str = ""
    duration_seconds: int = 0
    participants: list[str] = []
    transcript_chunks: list[dict[str, Any]] = []
    suggestion_cards: list[dict[str, Any]] = []
    entity: str = ""
    talk_ratio_pct: float = 0.0


class PlaybookUpsertRequest(BaseModel):
    id: str = ""
    name: str = ""
    triggers: list[str] = []
    talk_tracks: list[dict[str, Any]] = []
    objection_responses: dict[str, str] = {}


class PlaybookMatchRequest(BaseModel):
    transcript_text: str = ""


class PlaybookOutcomeRequest(BaseModel):
    playbook_id: str
    talk_track_idx: int
    outcome: str  # positive | negative | neutral
    context: str = ""


class ShadowStartRequest(BaseModel):
    rep_email: str
    meeting_title: str = ""
    entity: str = ""


class ShadowNoteRequest(BaseModel):
    note_text: str
    transcript_chunk: str = ""
    note_type: str = "coaching"  # coaching | praise | warning


class ShadowFeedbackRequest(BaseModel):
    overall_rating: int  # 1-5
    strengths: str = ""
    improvements: str = ""
    next_steps: str = ""


class TalkRatioRequest(BaseModel):
    segments: list[dict[str, Any]]


class NegotiationRequest(BaseModel):
    text: str
    speaker: str = ""
    batna: float | None = None


# ---------------------------------------------------------------------------
# POST /transcript — process a live transcript chunk
# ---------------------------------------------------------------------------


@router.post("/transcript")
async def process_transcript(req: TranscriptChunkRequest, token: str = Depends(verify_token_dep)):
    """Process a transcript chunk during a live call.

    Phase 4: Cluely-class real-time intelligence. Calls Core's
    CopilotSituationBridge.on_transcript_chunk(). Updates the Situation's
    operational state in real-time, detects new commitments, resolves unknowns.

    Phase 8 fix: call detect_situations() before passing situation_id to
    the copilot bridge. Without this, the situation engine is empty and
    get_situation() returns None.

    P1-Audit-F10 fix: auto-bind situation_id from entity when not provided.
    """
    from maestro_personal_shell.copilot_live import process_transcript_chunk
    from maestro_personal_shell.api import build_shell
    shell = build_shell(user_email=token)
    situations = shell.detect_situations()

    # P1-Audit-F10: auto-bind situation_id from entity
    situation_id = req.situation_id
    if not situation_id:
        if req.entity:
            entity_lower = req.entity.lower()
            for s in situations:
                if str(getattr(s, "entity", "")).lower() == entity_lower:
                    situation_id = str(getattr(s, "situation_id", ""))
                    break
        if not situation_id and situations:
            situation_id = str(getattr(situations[0], "situation_id", ""))
        if not situation_id:
            situation_id = "unknown"

    result = process_transcript_chunk(
        shell=shell,
        situation_id=situation_id,
        text=req.text,
        speaker=req.speaker,
        entity=req.entity,
    )

    # P0 fix: wire CopilotContextFuser into the REST path so REST also
    # generates evidence-backed whispers (not just WS).
    try:
        from maestro_personal_shell.copilot_context_fuser import CopilotContextFuser
        fuser = CopilotContextFuser(shell=shell, user_email=token)
        fused = await fuser.fuse(
            transcript_chunks=[{"speaker": req.speaker, "text": req.text}],
            meeting_entity=req.entity,
        )
        if fused.get("should_whisper"):
            evidence_refs = []
            for sig in fused.get("relevant_signals", [])[:3]:
                evidence_refs.append({
                    "text": sig.get("text", "")[:100],
                    "entity": sig.get("entity", ""),
                    "timestamp": sig.get("timestamp", ""),
                })
            for c in fused.get("active_commitments", [])[:2]:
                evidence_refs.append({
                    "text": c.get("text", "")[:100],
                    "entity": c.get("entity", ""),
                    "type": "commitment",
                })

            conf = 0.5
            if evidence_refs:
                conf = min(0.9, 0.4 + len(evidence_refs) * 0.1)
            if any(c.get("severity") == "high" for c in fused.get("contradictions", [])):
                conf = min(0.95, conf + 0.15)

            has_high = any(c.get("severity") == "high" for c in fused.get("contradictions", []))
            has_stale = any(s.get("days_stale", 0) > 5 for s in fused.get("stale_commitments", []))
            priority = "high" if (has_high or has_stale) else "medium"

            result["whisper"] = {
                "type": "whisper",
                "entity": req.entity or (evidence_refs[0]["entity"] if evidence_refs else "Maestro"),
                "text": fused.get("whisper_reason", ""),
                "priority": priority,
                "confidence": round(conf, 2),
                "evidence_refs": evidence_refs,
                "suggestions": fused.get("suggestions", []),
                "contradictions": fused.get("contradictions", []),
                "stale_commitments": fused.get("stale_commitments", []),
                "negotiation_anchors": fused.get("negotiation_anchors", []),
            }
    except Exception as e:
        logger.debug("REST copilot fuser failed (non-fatal): %s", e)

    return result


# ---------------------------------------------------------------------------
# POST /transcribe — audio file upload → text via STT provider
# ---------------------------------------------------------------------------


@router.post("/transcribe")
async def transcribe_audio_endpoint(
    file: UploadFile = File(...),
    token: str = Depends(verify_token_dep),
):
    """Transcribe an audio file using the configured STT provider.

    Accepts multipart/form-data with an audio file (m4a, wav, mp3).
    Returns the transcribed text, which the client then sends through
    /api/copilot/transcript for real-time intelligence.

    Providers (configured via env vars):
    - MAESTRO_WHISPER_MODEL: local Whisper (pip install openai-whisper)
    - MAESTRO_OPENAI_API_KEY: OpenAI Whisper API (cloud)
    - MAESTRO_GOOGLE_STT_KEY: Google Speech-to-Text

    If no provider is configured, returns 200 with configured=False
    and a clear error message.
    """
    from maestro_personal_shell.audio_transcription import transcribe_audio

    audio_data = await file.read()
    if not audio_data:
        raise HTTPException(status_code=400, detail="Empty audio file")

    result = transcribe_audio(audio_data, file.filename or "audio.m4a")
    return result


# ---------------------------------------------------------------------------
# POST /post-call — generate post-call summary after meeting ends
# ---------------------------------------------------------------------------


@router.post("/post-call")
async def post_call_summary(req: PostCallSummaryRequest, token: str = Depends(verify_token_dep)):
    """Generate a post-call summary after the meeting ends.

    Phase 4: calls Core's CopilotSituationBridge.post_call_summary().
    """
    from maestro_personal_shell.copilot_live import generate_post_call_summary
    from maestro_personal_shell.api import build_shell
    shell = build_shell(user_email=token)
    return generate_post_call_summary(
        shell=shell,
        situation_id=req.situation_id,
        transcript_chunks=req.transcript_chunks,
        commitments=req.commitments,
        entity=req.entity,
    )


# ---------------------------------------------------------------------------
# Phase 5 P2 — Follow-up Email Generator
# ---------------------------------------------------------------------------


@router.post("/follow-up-email")
async def generate_follow_up_email(req: FollowUpEmailRequest, token: str = Depends(verify_token_dep)):
    """Generate a commitment-aware follow-up email draft.

    Phase 5 P2: cites specific commitments + org laws. Adapts tone to
    the conversation.
    """
    from maestro_personal_shell.copilot_postcall_features import FollowUpEmailGenerator
    from maestro_personal_shell.api import build_shell
    shell = build_shell(user_email=token)
    gen = FollowUpEmailGenerator(shell)
    return gen.generate(
        meeting_title=req.meeting_title,
        participants=req.participants,
        commitments=req.commitments,
        objections=req.objections,
        entity=req.entity,
        transcript_chunks=req.transcript_chunks,
        tone=req.tone,
    )


# ---------------------------------------------------------------------------
# Phase 5 P2 — Pre-call Intelligence Panel
# ---------------------------------------------------------------------------


@router.post("/pre-call-intel")
async def get_pre_call_intel(req: PreCallIntelRequest, token: str = Depends(verify_token_dep)):
    """Get pre-call intelligence panel: 3 things that matter for THIS meeting."""
    from maestro_personal_shell.copilot_postcall_features import PreCallIntelPanel
    from maestro_personal_shell.api import build_shell
    shell = build_shell(user_email=token)
    panel = PreCallIntelPanel(shell)
    return panel.build(entity=req.entity, meeting_title=req.meeting_title)


# ---------------------------------------------------------------------------
# Phase 5 P2 — Post-call Summary UI payload
# ---------------------------------------------------------------------------


@router.post("/post-call-ui")
async def get_post_call_ui(req: PostCallSummaryUIRequest, token: str = Depends(verify_token_dep)):
    """Build the full post-call summary UI payload."""
    from maestro_personal_shell.copilot_postcall_features import PostCallSummaryUI
    from maestro_personal_shell.api import build_shell
    shell = build_shell(user_email=token)
    builder = PostCallSummaryUI(shell)
    return builder.build(
        meeting_title=req.meeting_title,
        duration_seconds=req.duration_seconds,
        participants=req.participants,
        transcript_chunks=req.transcript_chunks,
        suggestion_cards=req.suggestion_cards,
        entity=req.entity,
        talk_ratio_pct=req.talk_ratio_pct,
    )


# ---------------------------------------------------------------------------
# Playbook Engine — CRUD + match + outcome
# ---------------------------------------------------------------------------


@router.get("/playbooks")
async def list_playbooks(token: str = Depends(verify_token_dep)):
    """List all playbooks (summary form)."""
    from maestro_personal_shell.copilot_enterprise import PlaybookEngine
    engine = PlaybookEngine()
    return {"playbooks": engine.list_playbooks()}


@router.get("/playbooks/{playbook_id}")
async def get_playbook(playbook_id: str, token: str = Depends(verify_token_dep)):
    """Get a specific playbook by ID."""
    from maestro_personal_shell.copilot_enterprise import PlaybookEngine
    engine = PlaybookEngine()
    pb = engine.get_playbook(playbook_id)
    if not pb:
        raise HTTPException(status_code=404, detail=f"Playbook {playbook_id} not found")
    return pb


@router.post("/playbooks")
async def upsert_playbook(req: PlaybookUpsertRequest, token: str = Depends(verify_token_dep)):
    """Create or update a playbook."""
    from maestro_personal_shell.copilot_enterprise import PlaybookEngine
    engine = PlaybookEngine()
    return engine.upsert(req.model_dump())


@router.delete("/playbooks/{playbook_id}")
async def delete_playbook(playbook_id: str, token: str = Depends(verify_token_dep)):
    """Delete a playbook by ID."""
    from maestro_personal_shell.copilot_enterprise import PlaybookEngine
    engine = PlaybookEngine()
    deleted = engine.delete(playbook_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Playbook {playbook_id} not found")
    return {"deleted": True, "playbook_id": playbook_id}


@router.post("/playbooks/match")
async def match_playbook(req: PlaybookMatchRequest, token: str = Depends(verify_token_dep)):
    """Find the active playbook for the current transcript text."""
    from maestro_personal_shell.copilot_enterprise import PlaybookEngine
    engine = PlaybookEngine()
    match = engine.match_transcript(req.transcript_text)
    return {"match": match}


@router.post("/playbooks/outcome")
async def record_playbook_outcome(req: PlaybookOutcomeRequest, token: str = Depends(verify_token_dep)):
    """Record the outcome of using a talk track (feeds the learning loop)."""
    from maestro_personal_shell.copilot_enterprise import PlaybookEngine
    engine = PlaybookEngine()
    return engine.record_outcome(
        playbook_id=req.playbook_id,
        talk_track_idx=req.talk_track_idx,
        outcome=req.outcome,
        context=req.context,
    )


# ---------------------------------------------------------------------------
# Shadow Mode — manager observes a rep's live call
# ---------------------------------------------------------------------------


@router.post("/shadow/start")
async def start_shadow_session(req: ShadowStartRequest, token: str = Depends(verify_token_dep)):
    """Start a shadow session — manager observes a rep's live call."""
    from maestro_personal_shell.copilot_enterprise import ShadowMode
    shadow = ShadowMode()
    return shadow.start_session(
        manager_email=token,  # the manager is the authenticated user
        rep_email=req.rep_email,
        meeting_title=req.meeting_title,
        entity=req.entity,
    )


@router.post("/shadow/{session_id}/end")
async def end_shadow_session(session_id: str, token: str = Depends(verify_token_dep)):
    """End a shadow session."""
    from maestro_personal_shell.copilot_enterprise import ShadowMode
    shadow = ShadowMode()
    return shadow.end_session(session_id)


@router.post("/shadow/{session_id}/notes")
async def add_shadow_note(
    session_id: str,
    req: ShadowNoteRequest,
    token: str = Depends(verify_token_dep),
):
    """Add a coaching note to a shadow session."""
    from maestro_personal_shell.copilot_enterprise import ShadowMode
    shadow = ShadowMode()
    return shadow.add_note(
        session_id=session_id,
        note_text=req.note_text,
        transcript_chunk=req.transcript_chunk,
        note_type=req.note_type,
    )


@router.get("/shadow/{session_id}/notes")
async def list_shadow_notes(session_id: str, token: str = Depends(verify_token_dep)):
    """List all coaching notes for a shadow session."""
    from maestro_personal_shell.copilot_enterprise import ShadowMode
    shadow = ShadowMode()
    return {"notes": shadow.list_notes(session_id)}


@router.post("/shadow/{session_id}/feedback")
async def leave_shadow_feedback(
    session_id: str,
    req: ShadowFeedbackRequest,
    token: str = Depends(verify_token_dep),
):
    """Leave structured post-call feedback for a shadow session."""
    from maestro_personal_shell.copilot_enterprise import ShadowMode
    shadow = ShadowMode()
    return shadow.leave_feedback(
        session_id=session_id,
        overall_rating=req.overall_rating,
        strengths=req.strengths,
        improvements=req.improvements,
        next_steps=req.next_steps,
    )


@router.get("/shadow/{session_id}")
async def get_shadow_session(session_id: str, token: str = Depends(verify_token_dep)):
    """Get a shadow session by ID (includes notes + feedback)."""
    from maestro_personal_shell.copilot_enterprise import ShadowMode
    shadow = ShadowMode()
    session = shadow.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Shadow session {session_id} not found")
    session["notes"] = shadow.list_notes(session_id)
    session["feedback"] = shadow.get_feedback(session_id)
    return session


@router.get("/shadow")
async def list_shadow_sessions(
    token: str = Depends(verify_token_dep),
    rep_email: str = "",
    status: str = "",
):
    """List shadow sessions (filtered by manager = current user)."""
    from maestro_personal_shell.copilot_enterprise import ShadowMode
    shadow = ShadowMode()
    sessions = shadow.list_sessions(
        manager_email=token,
        rep_email=rep_email,
        status=status,
    )
    return {"sessions": sessions, "count": len(sessions)}


# ---------------------------------------------------------------------------
# Talk Ratio Coaching
# ---------------------------------------------------------------------------


@router.post("/talk-ratio")
async def get_talk_ratio(req: TalkRatioRequest, token: str = Depends(verify_token_dep)):
    """Get talk ratio coaching from Core's TalkRatioCoach."""
    from maestro_personal_shell.copilot_live import get_talk_ratio_coaching
    from maestro_personal_shell.api import build_shell
    shell = build_shell(user_email=token)
    return get_talk_ratio_coaching(shell=shell, segments=req.segments)


# ---------------------------------------------------------------------------
# Negotiation Coaching
# ---------------------------------------------------------------------------


@router.post("/negotiation")
async def get_negotiation(req: NegotiationRequest, token: str = Depends(verify_token_dep)):
    """Get negotiation coaching from Core's NegotiationStrategyEngine."""
    from maestro_personal_shell.copilot_live import get_negotiation_coaching
    from maestro_personal_shell.api import build_shell
    shell = build_shell(user_email=token)
    return get_negotiation_coaching(
        shell=shell,
        text=req.text,
        speaker=req.speaker,
        batna=req.batna,
    )

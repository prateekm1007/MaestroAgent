"""Pydantic models for the Maestro Personal API."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    # P-2026-07-18 fix (auditor S3 finding): accept both `user_email` (the
    # canonical field) and `email` (the intuitive field most API clients try
    # first). Previously, sending `email` was silently ignored and the login
    # defaulted to "default@personal.local" — confusing first-touch UX.
    user_email: str = ""
    email: str = ""  # alias — merged into user_email in the login handler
    password: str = ""


class LoginResponse(BaseModel):
    token: str
    user_email: str
    message: str


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------


class SignalCreate(BaseModel):
    # MEDIUM-2 fix (independent audit): cap input sizes to prevent DoS.
    # 200 chars is generous for an entity name; 10K chars is generous for
    # signal text (~1500 words). The previous code had no length cap, so a
    # 1MB signal was accepted, stored, FTS-indexed, and materialized by
    # build_shell — OOM risk on the 3.9GB server.
    entity: str = Field(..., max_length=200)
    text: str = Field(..., max_length=10_000)
    signal_type: str = "reported_statement"
    timestamp: str | None = None  # P0-3 fix: accept client timestamp to preserve history


class SignalResponse(BaseModel):
    signal_id: str
    entity: str
    text: str
    signal_type: str
    timestamp: str
    # P1-Audit-F4: surface audit-log write failures to the caller
    audit_log_error: str | None = None
    # P3 auditor fix (2026-07-24): return classification metadata so the
    # user and auditor can see WHY a signal was classified as a commitment.
    # Inspectable memory is the thesis; hidden classification contradicts it.
    commitment_type: str | None = None
    is_commitment: bool | None = None
    commitment_state: str | None = None
    commitment_confidence: float | None = None
    classification_reasoning: str | None = None
    llm_powered: bool | None = None


# ---------------------------------------------------------------------------
# Ask
# ---------------------------------------------------------------------------


class AskRequest(BaseModel):
    # Phase 3 fix: empty query should be rejected at the model level (422),
    # not crash the pipeline (500). min_length=1 prevents empty strings.
    query: str = Field(..., min_length=1, max_length=10_000)
    session_id: str = ""  # P0-3: optional session ID for multi-turn conversations


class AskResponse(BaseModel):
    """The masterpiece Ask response — the truth, sourced, with full depth."""
    answer: str
    query: str
    source_sentence: str = ""
    source_entity: str = ""
    source_timestamp: str = ""
    situation_state: str = ""
    evidence_refs: list[dict[str, Any]] = []
    # Phase 5: roadmap answer schema fields
    confidence: float = 0.0            # calibrated confidence in the answer (0.0-1.0)
    counterevidence: list[dict[str, Any]] = []  # evidence that contradicts the answer
    unknowns: list[str] = []           # what we don't know / can't verify
    as_of: str = ""                    # the temporal cutoff used for this answer
    # DEPTH FIELDS (wired from Core)
    decision_boundary: str = ""        # from JudgmentSynthesizer — "decide now / wait / what would change this"
    perspectives: list[dict[str, Any]] = []  # from Perspective — specialist views
    reasoning_chain: list[str] = []   # from ReasoningTrace — how Maestro arrived at this
    calibration_note: str = ""         # from CalibrationPrimitives — "insufficient history" if applicable
    consequence_paths: list[str] = []  # from ConsequencePathRouter — what happens if you decide X
    # TRANSPARENCY — the user knows whether they're getting AI or rules
    llm_active: bool = False           # True if LLM powered this response
    llm_provider: str = "none"         # "zai-glm", "openai", "anthropic", or "none"
    # P1-Audit-F2 fix: top-level intelligence source label so the user
    # knows whether the answer came from LLM, rules, or ranker-only.
    # Propagates /api/llm-status honesty to every response.
    intelligence_source: str = "rules"  # "llm" | "rules" | "ranker"


# ---------------------------------------------------------------------------
# Commitments
# ---------------------------------------------------------------------------


class CommitmentResponse(BaseModel):
    entity: str
    text: str
    claim_type: str
    signal_id: str
    is_commitment: bool
    is_at_risk: bool = False
    days_stale: int = 0
    deadline: str = ""
    # DEPTH FIELDS (wired from Core)
    calibration_note: str = ""        # from CalibrationPrimitives — "insufficient history" or Brier score
    outcome_history: str = ""         # from BehavioralLearningEngine — "kept 3/5 like this"
    confidence: float = 0.0           # calibrated confidence in this commitment being kept


class CommitmentsMasterpieceResponse(BaseModel):
    """The masterpiece Commitments response — one at risk, rest secondary.

    Not a list of 47. One primary (the at-risk commitment), the rest
    available but secondary. The inevitability: you know what you owe
    without scrolling.
    """
    primary: CommitmentResponse | None = None
    why_primary: str = ""
    secondary: list[CommitmentResponse] = []
    # DEPTH: overall calibration across all commitments
    overall_calibration: str = ""     # from CalibrationPrimitives — aggregate Brier or "insufficient history"


class CommitmentSimulationRequest(BaseModel):
    commitment_text: str
    entity: str
    deadline: str | None = None


# ---------------------------------------------------------------------------
# Situations / What-changed / Prepare
# ---------------------------------------------------------------------------


class SituationResponse(BaseModel):
    situation_id: str
    entity: str
    state: str
    evidence_count: int


class WhatChangedResponse(BaseModel):
    entity: str
    text: str
    type: str
    is_meaningful: bool


class WhatChangedMasterpieceResponse(BaseModel):
    """The masterpiece What Changed response — 2 material shifts, not a feed.

    Not a chronological inbox dump. Two cards. The things that materially
    changed since you last looked. The inevitability: you're already
    caught up.
    """
    the_shifts: list[WhatChangedResponse] = []
    silence_message: str = ""
    # S2-4 SURFACES reconciliation (P41) — see BriefingResponse.reconciliation
    reconciliation: dict[str, Any] = {}


class PrepareResponse(BaseModel):
    """The masterpiece Prepare response — 3 things that matter for THIS meeting.

    Not 5 prep points. Three. The forgotten commitment, the open question,
    the contradiction. The right three. PLUS: Cluely-class depth from
    CopilotSituationBridge.pre_call_briefing().
    """
    situation_id: str
    entity: str = ""
    meeting_context: str = ""
    is_stale: bool = False
    the_forgotten: str = ""
    the_open_question: str = ""
    the_contradiction: str = ""
    prep_points: list[str] = []  # kept for backward compat, but the 3 above are the point
    # DEPTH FIELDS (wired from Core's CopilotSituationBridge)
    copilot_talking_points: list[dict[str, Any]] = []  # from pre_call_briefing — each cites evidence_refs
    copilot_blocking_unknowns: list[str] = []           # what you DON'T know going into this meeting
    copilot_can_decide: list[str] = []                  # what you can decide in this meeting
    copilot_cannot_decide: list[str] = []               # what you should NOT decide yet
    copilot_timeline: list[dict[str, Any]] = []         # the situation's timeline summary


# ---------------------------------------------------------------------------
# Whisper
# ---------------------------------------------------------------------------


class WhisperResponse(BaseModel):
    type: str
    entity: str
    title: str
    body: str
    priority: str
    action_url: str = ""
    # DEPTH FIELDS (wired from Core)
    delivery_route: str = ""          # from Core's DeliveryGovernor via WhisperSituationBridge
    delivery_explanation: str = ""    # WHY this route was chosen
    suppression_reason: str = ""      # if SILENT, why
    evidence_refs: list[str] = []     # provenance — which signals led to this whisper


class PushDeliverResponse(BaseModel):
    whispers_pushed: int
    whispers_suppressed: int
    log: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Sync / Ingest
# ---------------------------------------------------------------------------


class GmailSyncRequest(BaseModel):
    messages: list[dict[str, Any]]
    user_email: str = "me"


class GmailSyncResponse(BaseModel):
    signals_created: int
    message: str


class CalendarSyncRequest(BaseModel):
    events: list[dict[str, Any]]
    user_email: str = "me"


class CalendarSyncResponse(BaseModel):
    signals_created: int
    message: str


class SlackIngestRequest(BaseModel):
    messages: list[dict[str, Any]]


class TranscriptIngestRequest(BaseModel):
    transcript: list[dict[str, str]]
    meeting_entity: str = ""


# ---------------------------------------------------------------------------
# Devices
# ---------------------------------------------------------------------------


class DeviceRegisterRequest(BaseModel):
    push_token: str
    platform: str = "ios"
    user_timezone: str = "UTC"


class DeviceRegisterResponse(BaseModel):
    device_id: str
    message: str


# ---------------------------------------------------------------------------
# Copilot
# ---------------------------------------------------------------------------


class TranscriptChunkRequest(BaseModel):
    # P1-Audit-F10 fix: situation_id is now optional. When omitted, the
    # endpoint auto-binds a situation from the entity field. The auditor
    # found POST /api/copilot/transcript without situation_id → 422.
    situation_id: str = ""
    text: str
    speaker: str = ""
    entity: str = ""


class PostCallSummaryRequest(BaseModel):
    situation_id: str = ""  # P1-Audit-F10: optional — auto-bound from entity
    transcript_chunks: list[dict[str, Any]] = []
    commitments: list[dict[str, Any]] = []
    entity: str = ""


class PostCallSummaryUIRequest(BaseModel):
    meeting_title: str = ""
    duration_seconds: int = 0
    participants: list[str] = []
    transcript_chunks: list[dict[str, Any]] = []
    suggestion_cards: list[dict[str, Any]] = []
    entity: str = ""
    talk_ratio_pct: float = 0.0


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
# Connectors / Drafts
# ---------------------------------------------------------------------------


class ConnectorConnectRequest(BaseModel):
    provider: str  # gmail | slack | github | calendar | whatsapp | facebook | instagram | twitter
    oauth_token: str = ""  # empty in demo mode


class ConnectorDraftRequest(BaseModel):
    provider: str
    recipient: str
    commitment_text: str = ""
    entity: str = ""
    evidence_refs: list[dict[str, Any]] = []


class ConnectorAutoDraftRequest(BaseModel):
    """P13 fix: only provider + recipient — commitment + evidence are DERIVED."""
    provider: str
    recipient: str


class DraftResolutionRequest(BaseModel):
    resolution: str  # approve | deny | use_draft


# ---------------------------------------------------------------------------
# Learning loop / Outcomes
# ---------------------------------------------------------------------------


class PredictionRequest(BaseModel):
    predicted_confidence: float
    expected_outcome: str = "hit"
    prediction_type: str = "recommendation"
    entity_id: str = ""


class OutcomeRequest(BaseModel):
    prediction_id: str
    actual_outcome: str  # "hit" or "miss"


# ---------------------------------------------------------------------------
# Briefing / The Moment
# ---------------------------------------------------------------------------


class BriefingResponse(BaseModel):
    """The masterpiece briefing — Situation-centric, not agent-centric.

    Structure (from Core's SituationCentricBriefing):
      - Greeting
      - The one thing that needs your judgment
      - What changed since last briefing
      - What is unknown / disputed
      - What can/cannot be decided
      - What Maestro believes, why, what would change that
      - Situations being watched quietly
    """
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
    # S2-4 SURFACES reconciliation (P41 — single source of truth):
    # All three surfaces (Briefing, What-Changed, The-Moment) MUST return
    # the SAME reconciliation block, derived from the SAME
    # CommitmentsSurface.get_active_commitments() call. The auditor found
    # Briefing saying "no changes" while What-Changed said "three changes"
    # and The-Moment said "nothing" — with 24 active commitments. The
    # reconciliation block ensures cross-surface consistency is verifiable.
    reconciliation: dict[str, Any] = {}


class TheMomentResponse(BaseModel):
    """The single most important thing Maestro knows right now.

    This is not a list. This is one commitment, one situation, one moment.
    The salience gate fires on the commitment whose deadline is closest
    AND whose last signal is oldest — the one you're most likely to miss.

    If nothing deserves attention, this returns null. Trusted silence.
    """
    has_moment: bool
    commitment: dict[str, Any] | None = None
    situation: dict[str, Any] | None = None
    why_this_one: str = ""
    source_evidence: list[dict[str, Any]] = []
    # S2-4 SURFACES reconciliation (P41) — see BriefingResponse.reconciliation
    reconciliation: dict[str, Any] = {}

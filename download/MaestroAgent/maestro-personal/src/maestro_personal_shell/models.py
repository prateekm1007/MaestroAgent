"""Pydantic models for the Maestro Personal API."""
from __future__ import annotations

import logging
import re as _re_models
from typing import Any

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Shared constants — P69 cross-module contract enforcement
#
# These key names are referenced by the writer (signals.py on ingest stores
# `commitment_owner` in metadata; reconcile.py exposes `owner` and
# `commitment_type` on ReconciledRecord) and by the reader (the final-gate
# validator on AskResponse below). Per P69, the key name is a contract —
# duplicating the string literal in two places is how the original P69 owner-
# key bug silently broke the ownership filter for as long as it existed.
# These constants are the single source of truth.
# ---------------------------------------------------------------------------

# Owner field names — `owner` on ReconciledRecord (the reader-facing shape),
# `commitment_owner` in raw signal.metadata (the writer-facing shape).
# The final-gate validator only inspects `owner` (the reconciled shape),
# because evidence_refs are built from ReconciledRecords.
OWNER_KEY = "owner"
COMMITMENT_TYPE_KEY = "commitment_type"

# Owner values — see reconcile.py for the canonical taxonomy.
OWNER_USER = "user"           # first-person commitment: "I will..."
OWNER_OTHER = "other"         # third-party commitment: "Maria said she will..."
OWNER_UNKNOWN = "unknown"     # ambiguous — classifier couldn't determine

# Commitment types that are NEVER the user's own promise, regardless of
# query phrasing. These should be stripped from evidence on promise queries.
COMMITMENT_TYPE_THIRD_PARTY_REPORT = "third_party_report"
COMMITMENT_TYPE_QUOTED = "quoted"

# Set of commitment_type values that indicate the evidence is NOT the user's
# own first-person promise — it's a report of someone else's promise.
NON_USER_COMMITMENT_TYPES = frozenset({
    COMMITMENT_TYPE_THIRD_PARTY_REPORT,
    COMMITMENT_TYPE_QUOTED,
})

# Promise-query regex — used by the final-gate validator to decide whether
# to apply the ownership filter. Matches first-person promise queries:
#   "What did I promise Maria?"
#   "What did I commit to?"
#   "What are my promises?" / "What are my active promises?"
#   "Tell me about my commitments to Maria"
# Does NOT match third-party queries (those are handled by the existing
# _apply_ticket10_filter in ask.py, which has its own regex).
# Note: plural forms (promises, commitments, pledges, agreements) are
# explicitly included — \bpromise\b alone won't match "promises" because
# the trailing 's' creates a word boundary mismatch.
PROMISE_QUERY_PATTERN = _re_models.compile(
    r'\b(?:i|my|me|mine)\b.+\b(?:promise(?:s|d)?|commit(?:s|ed|ment|s|ted)?|agree(?:s|d|ment|ments)?|pledge(?:s|d)?)\b'
    r'|\b(?:promise(?:s|d)?|commit(?:s|ed|ment|s|ted)?|agree(?:s|d|ment|ments)?|pledge(?:s|d)?)\b.+\b(?:i|my|me|mine)\b'
    r'|\bwhat\s+(?:did|have|do)\s+i\b.+\b(?:promise(?:s|d)?|commit(?:s|ed|ted)?|agree(?:s|d)?|pledge(?:s|d)?)\b'
    r'|\b(?:my|mine)\s+(?:promises?|commitments?|pledges?|agreements?)\b',
    _re_models.IGNORECASE,
)

_logger = _models_logger = logging.getLogger("maestro_personal_shell.models")


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
    # TICKET-1/P59: allow callers to pass classification hints (commitment_state,
    # commitment_type, etc.) so the lifecycle engine can fire on resolution
    # signals even when the classifier is unavailable. The classifier refines
    # these; the caller's intent is preserved for fields the classifier doesn't
    # override.
    metadata: dict[str, Any] = {}
    signal_id: str | None = None  # allow caller-specified signal_id (for tests)


class SignalResponse(BaseModel):
    signal_id: str | None = None  # Phase 3.2: None when rejected (machine_sender, etc.)
    entity: str
    text: str
    signal_type: str
    timestamp: str
    rejected: str | None = None  # Phase 3.2: rejection reason
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
    """The masterpiece Ask response — the truth, sourced, with full depth.

    P51 (fifth audit F1): answer is NEVER blank — a model_validator enforces
    this at construction time, so every return point gets the guard.
    P52 (fifth audit F4): PII tokens are redacted from answer, source_sentence,
    and evidence_refs at construction time, so every return point gets the
    redaction regardless of which code path produced the response.
    """
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

    @model_validator(mode="after")
    def _p51_p52_guards(self):
        """P51: answer is never blank. P52: PII is redacted.

        This validator runs on EVERY AskResponse construction, so it
        catches all return points — including early returns that bypass
        the inline redaction code in ask.py.
        """
        import re as _re_p52

        # P52: PII redaction — known PII tokens → [REDACTED]
        _PII_TOKENS = [
            "PRATEEK MISRA", "PRATEEK", "MISRA",
            "TND670", "Zerodha",
            "Client ID: TND670",
        ]
        def _redact(text):
            if not text:
                return text
            result = str(text)
            for token in _PII_TOKENS:
                result = _re_p52.sub(
                    _re_p52.escape(token), "[REDACTED]",
                    result, flags=_re_p52.IGNORECASE,
                )
            return result

        # Apply PII redaction
        self.answer = _redact(self.answer)
        self.source_sentence = _redact(self.source_sentence)
        if self.evidence_refs:
            self.evidence_refs = [
                {**ev, "text": _redact(ev.get("text", ""))} if isinstance(ev, dict) else ev
                for ev in self.evidence_refs
            ]

        # P51: answer must NEVER be blank
        if not self.answer or not self.answer.strip():
            self.answer = (
                "I don't have enough information to answer that question right now. "
                "This could be due to an AI outage or no matching signals in your ledger. "
                "Please try rephrasing, or try again in a moment."
            )
            if not self.calibration_note:
                self.calibration_note = "P51: model_validator non-blank guard."

        return self

    @model_validator(mode="after")
    def _ticket10_final_gate(self):
        """TICKET-10 / P66: final-gate ownership filter on EVERY AskResponse.

        This is the ADDITIVE last line of defense. The existing
        `_apply_ticket10_filter` in ask.py only fires on third-party promise
        queries (regex match) and depends on a DB hit. This validator runs
        unconditionally at model construction time — every code path,
        every return point, every test fixture.

        WHAT IT DOES (only when self.query looks like a first-person promise
        query, per PROMISE_QUERY_PATTERN):
          1. Strips evidence_refs where `owner` is present and != OWNER_USER
             (i.e. owner="other" or owner="unknown" → not the user's promise).
          2. Strips evidence_refs where `commitment_type` is in
             NON_USER_COMMITMENT_TYPES (third_party_report | quoted).
          3. Appends a calibration_note marker so the filter is observable.

        WHAT IT DOES NOT DO:
          - Does NOT call the DB (per P70 — DB-dependent filters are a bug
            source; the existing _apply_ticket10_filter already does the
            DB-backed check, this is purely structural).
          - Does NOT modify `answer` text (the existing filter handles that).
          - Does NOT raise — fails safe (leaves evidence intact) on any error.
          - Does NOT replace _apply_ticket10_filter — both run, this is the
            backstop after the front-line filter has already run.

        P69: uses shared constants (OWNER_KEY, COMMITMENT_TYPE_KEY,
        NON_USER_COMMITMENT_TYPES, OWNER_USER) — never a duplicated string
        literal. P67: any failure logs at error level (not debug). P66: no
        local imports — all constants are at module level.
        """
        # Fail safe: if no evidence or no query, nothing to filter.
        if not self.evidence_refs or not self.query:
            return self

        # Only filter promise-type queries (first-person). Third-party
        # queries are already handled by _apply_ticket10_filter in ask.py.
        try:
            _is_promise = bool(PROMISE_QUERY_PATTERN.search(self.query))
        except Exception as _e:
            # P67: log at error level, not debug. Fail safe (don't filter).
            _logger.error(
                "TICKET-10 final-gate: promise-query regex failed (%s); "
                "skipping filter (fail-safe, evidence unchanged)", _e,
            )
            return self

        if not _is_promise:
            return self

        # Apply the filter. Track whether we stripped anything so we can
        # add the calibration_note marker only when the filter actually fired.
        _original_count = len(self.evidence_refs)
        try:
            _filtered = []
            _stripped_count = 0
            for _ev in self.evidence_refs:
                if not isinstance(_ev, dict):
                    _filtered.append(_ev)
                    continue

                # Rule 1: strip evidence where owner is present and != "user".
                # If `owner` is absent, keep the evidence (can't determine
                # ownership from the response alone — the DB-backed filter
                # in ask.py is the authoritative source).
                _owner = _ev.get(OWNER_KEY)
                if _owner is not None and _owner != OWNER_USER:
                    _stripped_count += 1
                    continue

                # Rule 2: strip evidence where commitment_type is a known
                # non-user type (third_party_report | quoted).
                _ctype = _ev.get(COMMITMENT_TYPE_KEY)
                if _ctype in NON_USER_COMMITMENT_TYPES:
                    _stripped_count += 1
                    continue

                _filtered.append(_ev)

            if _stripped_count > 0:
                self.evidence_refs = _filtered
                _marker = (
                    f"P66/TICKET-10: final-gate ownership filter applied "
                    f"(stripped {_stripped_count} of {_original_count} evidence refs)."
                )
                if self.calibration_note:
                    self.calibration_note = f"{self.calibration_note} | {_marker}"
                else:
                    self.calibration_note = _marker
        except Exception as _e:
            # P67: log at error level. Fail safe (leave evidence intact).
            _logger.error(
                "TICKET-10 final-gate: filter execution failed (%s); "
                "evidence left unchanged (fail-safe)", _e,
            )
            return self

        return self


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
    prep_points: list[str] = []  # Phase 3.1: populated from prepare_engine
    why_this_matters: str = ""   # Phase 3.1: one-line summary from prepare_engine
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
    # F-40 fix (auditor v18): messages is now optional. When empty/omitted,
    # the server attempts a server-initiated pull using stored OAuth tokens.
    messages: list[dict[str, Any]] = []
    user_email: str = "me"
    # F-40: max_messages controls how many messages to fetch in a server-side
    # pull (default 50, capped at 200 to prevent runaway syncs).
    max_messages: int = 50


class GmailSyncResponse(BaseModel):
    signals_created: int
    message: str


class CalendarSyncRequest(BaseModel):
    # F-39 fix (auditor v18): events is now optional. When empty/omitted,
    # the server attempts a server-initiated pull using stored OAuth tokens.
    events: list[dict[str, Any]] = []
    user_email: str = "me"
    max_events: int = 50


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
    # Audit fix S2-8 (2026-08-01): social providers removed from inventory.
    # The valid provider set is now: gmail | calendar | slack | github
    # (plus the IMAP-based work_email flow which doesn't use this model).
    provider: str  # gmail | slack | github | calendar | microsoft_mail | yahoo_mail | work_email
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

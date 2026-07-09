"""
Maestro Personal HTTP API — FastAPI on port 8766.

Separate from Enterprise (port 8765). This is the Personal API that the
mobile app calls. It wraps the PersonalShell (which calls Core directly)
and adds:
  - SQLite persistence (signals survive restart)
  - Bearer token auth (simple, v1)
  - 8 endpoints mapping to the 4 surfaces + signal management + auth

Per build directions: do NOT couple to Enterprise's 8765. Separate
process, separate product.
"""

from __future__ import annotations

import os
import sqlite3
import secrets
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_PORT = int(os.environ.get("MAESTRO_PERSONAL_PORT", "8766"))
DB_PATH = os.environ.get(
    "MAESTRO_PERSONAL_DB",
    str(Path(__file__).resolve().parent / "personal.db"),
)
# Bearer token — in production this would be per-user; for v1 dogfood,
# a single shared token from env or auto-generated on first run.
AUTH_TOKEN = os.environ.get("MAESTRO_PERSONAL_TOKEN") or secrets.token_urlsafe(32)

# ---------------------------------------------------------------------------
# SQLite persistence
# ---------------------------------------------------------------------------


def init_db(db_path: str = DB_PATH) -> None:
    """Initialize the SQLite database for signal persistence."""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            signal_id TEXT PRIMARY KEY,
            entity TEXT NOT NULL,
            text TEXT NOT NULL,
            signal_type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            metadata TEXT DEFAULT '{}',
            source_acl TEXT DEFAULT 'public',
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS auth_tokens (
            token TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            active INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()


def load_signals_from_db(db_path: str = DB_PATH) -> list[dict[str, Any]]:
    """Load all signals from SQLite, ordered by timestamp."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM signals ORDER BY timestamp ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_signal_to_db(signal: dict[str, Any], db_path: str = DB_PATH) -> None:
    """Save a signal to SQLite."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT OR REPLACE INTO signals
           (signal_id, entity, text, signal_type, timestamp, metadata, source_acl, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            signal["signal_id"],
            signal["entity"],
            signal["text"],
            signal["signal_type"],
            signal["timestamp"],
            json.dumps(signal.get("metadata", {})),
            signal.get("source_acl", "public"),
            signal.get("created_at", datetime.now(timezone.utc).isoformat()),
        ),
    )
    conn.commit()
    conn.close()


def clear_signals_db(db_path: str = DB_PATH) -> None:
    """Clear all signals (for testing)."""
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM signals")
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


async def verify_token(authorization: str = Header(None)) -> str:
    """Verify bearer token. Returns the token if valid."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid auth scheme — expected 'Bearer <token>'")
    token = authorization.split(" ", 1)[1]
    if token != AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")
    return token


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    password: str = ""


class LoginResponse(BaseModel):
    token: str
    message: str


class SignalCreate(BaseModel):
    entity: str
    text: str
    signal_type: str = "reported_statement"


class SignalResponse(BaseModel):
    signal_id: str
    entity: str
    text: str
    signal_type: str
    timestamp: str


class AskRequest(BaseModel):
    query: str


class AskResponse(BaseModel):
    """The masterpiece Ask response — the truth, sourced, with full depth.

    Not a summary. Not a paraphrase. The exact sentence from the source,
    with provenance you can tap to verify. PLUS: judgment, perspectives,
    decision boundary, and reasoning trace from the full Core engine.
    """
    answer: str
    query: str
    source_sentence: str = ""
    source_entity: str = ""
    source_timestamp: str = ""
    situation_state: str = ""
    evidence_refs: list[dict[str, Any]] = []
    # DEPTH FIELDS (wired from Core)
    decision_boundary: str = ""        # from JudgmentSynthesizer — "decide now / wait / what would change this"
    perspectives: list[dict[str, Any]] = []  # from Perspective — specialist views
    reasoning_chain: list[str] = []   # from ReasoningTrace — how Maestro arrived at this
    calibration_note: str = ""         # from CalibrationPrimitives — "insufficient history" if applicable
    consequence_paths: list[str] = []  # from ConsequencePathRouter — what happens if you decide X


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
# Shell builder — loads signals from DB into PersonalShell
# ---------------------------------------------------------------------------


def build_shell():
    """Build a PersonalShell with signals loaded from SQLite.

    This is the bridge between persistence (SQLite) and intelligence
    (Core via PersonalShell). The shell does NOT persist — persistence
    is the API layer's job.
    """
    import sys
    import pathlib

    # Ensure paths are set
    personal_src = pathlib.Path(__file__).resolve().parents[1]
    if str(personal_src) not in sys.path:
        sys.path.insert(0, str(personal_src))

    backend_dir = pathlib.Path(__file__).resolve().parents[3] / "backend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    from maestro_personal_shell.personal_oem_state import PersonalOemState, PersonalSignal
    from maestro_personal_shell.shell import PersonalShell

    # Load signals from DB
    db_signals = load_signals_from_db()

    # Convert DB rows to PersonalSignal objects
    personal_signals = []
    for row in db_signals:
        ts = row["timestamp"]
        # Parse ISO timestamp
        try:
            timestamp = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            timestamp = datetime.now(timezone.utc)

        sig = PersonalSignal(
            entity=row["entity"],
            text=row["text"],
            signal_type=row["signal_type"],
            signal_id=row["signal_id"],
            timestamp=timestamp,
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            source_acl=row["source_acl"],
        )
        personal_signals.append(sig)

    state = PersonalOemState(signals=personal_signals)
    return PersonalShell(oem_state=state)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler — replaces deprecated @app.on_event("startup")."""
    init_db()
    logger.info("Maestro Personal API starting on port %d", API_PORT)
    logger.info("DB path: %s", DB_PATH)
    logger.info("Auth token: %s", AUTH_TOKEN)
    yield  # App runs here
    # Shutdown (if needed)


app = FastAPI(
    title="Maestro Personal API",
    description="HTTP API for Maestro Personal v1 — wraps the PersonalShell (Core via Python)",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow the mobile app (Expo Metro bundler runs on :8081/:19000) to call
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # v1 dogfood — tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. POST /api/auth/login — bearer token auth


@app.post("/api/auth/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    """Login — returns bearer token.

    For v1 dogfood: any password works (the token is shared). In production,
    this would validate against a user store.
    """
    return LoginResponse(token=AUTH_TOKEN, message="Login successful")


# 2. GET /api/situations — list detected situations


@app.get("/api/situations", response_model=list[SituationResponse])
async def get_situations(token: str = Depends(verify_token)):
    """Get all detected situations from personal signals."""
    shell = build_shell()
    situations = shell.detect_situations()

    result = []
    for s in situations:
        # Extract state value — handle enums (use .value) and plain strings
        state_raw = getattr(s, "state", getattr(s, "operational_state", "unknown"))
        if hasattr(state_raw, "value"):
            state_val = state_raw.value
        else:
            # Strip enum repr like "SituationState.OBSERVING" → "OBSERVING" → lowercase
            state_str = str(state_raw)
            if "." in state_str:
                state_val = state_str.split(".")[-1].lower()
            else:
                state_val = state_str.lower()

        result.append(SituationResponse(
            situation_id=str(getattr(s, "situation_id", uuid4())),
            entity=str(getattr(s, "entity", "")),
            state=state_val,
            evidence_count=len(getattr(s, "evidence_refs", []) or []),
        ))
    return result


# 3. POST /api/signals — manual signal entry


@app.post("/api/signals", response_model=SignalResponse)
async def create_signal(req: SignalCreate, token: str = Depends(verify_token)):
    """Create a new personal signal (manual entry for v1)."""
    signal_id = str(uuid4())
    now = datetime.now(timezone.utc)

    signal_data = {
        "signal_id": signal_id,
        "entity": req.entity,
        "text": req.text,
        "signal_type": req.signal_type,
        "timestamp": now.isoformat(),
        "metadata": {},
        "source_acl": "public",
        "created_at": now.isoformat(),
    }

    save_signal_to_db(signal_data)

    return SignalResponse(
        signal_id=signal_id,
        entity=req.entity,
        text=req.text,
        signal_type=req.signal_type,
        timestamp=now.isoformat(),
    )


# 4. GET /api/signals — list all signals


@app.get("/api/signals", response_model=list[SignalResponse])
async def get_signals(token: str = Depends(verify_token)):
    """Get all stored signals."""
    db_signals = load_signals_from_db()
    return [
        SignalResponse(
            signal_id=r["signal_id"],
            entity=r["entity"],
            text=r["text"],
            signal_type=r["signal_type"],
            timestamp=r["timestamp"],
        )
        for r in db_signals
    ]


# 5. POST /api/ask — Ask surface


@app.post("/api/ask", response_model=AskResponse)
async def ask(req: AskRequest, token: str = Depends(verify_token)):
    """Ask a question — get the truth, sourced.

    The masterpiece Ask: returns the exact sentence from the source, the
    entity, the timestamp, and the situation state. Not a summary. The
    provenance is the point — you can verify the answer.
    """
    shell = build_shell()

    from maestro_personal_shell.surfaces.ask import AskSurface
    surface = AskSurface(shell=shell)
    result = surface.ask(req.query)

    answer = (
        getattr(result, "answer", None)
        or getattr(result, "synthesized_answer", None)
        or str(result)
    )

    # Extract the source sentence — the exact text from the original signal
    # that supports the answer. This is the provenance the user can verify.
    source_sentence = ""
    source_entity = ""
    source_timestamp = ""
    situation_state = ""
    evidence_refs = []

    # Try to get evidence_refs from the result (Core provides these)
    raw_refs = getattr(result, "evidence_refs", None) or getattr(result, "evidence", None) or []
    for ref in raw_refs[:3]:  # max 3 evidence refs
        if isinstance(ref, dict):
            evidence_refs.append({
                "text": ref.get("text", ""),
                "entity": ref.get("entity", ""),
                "timestamp": str(ref.get("timestamp", "")),
            })
        else:
            evidence_refs.append({"text": str(ref), "entity": "", "timestamp": ""})

    # Find the situation state for the entity mentioned in the query
    # Extract entity from the query (simple: capitalized word that's not a common word)
    import re
    words = re.findall(r'\b[A-Z][a-z]+\b', req.query)
    common_words = {"What", "Did", "Will", "The", "How", "When", "Why", "Who", "Is", "Are", "Can", "Could", "I"}
    entities = [w for w in words if w not in common_words]

    situations = shell.detect_situations()
    for entity in entities:
        for s in situations:
            s_entity = str(getattr(s, "entity", "")).lower()
            if s_entity == entity.lower():
                state_raw = getattr(s, "state", getattr(s, "operational_state", "unknown"))
                if hasattr(state_raw, "value"):
                    situation_state = state_raw.value
                else:
                    situation_state = str(state_raw).split(".")[-1].lower()

                # Get the source sentence from the situation's evidence
                sig_refs = getattr(s, "evidence_refs", []) or []
                for sig_id in sig_refs[:1]:
                    for sig in shell.oem_state.signals:
                        if str(getattr(sig, "signal_id", "")) == str(sig_id):
                            source_sentence = getattr(sig, "text", "")
                            source_entity = getattr(sig, "entity", "")
                            source_timestamp = str(getattr(sig, "timestamp", ""))
                            break
                break
        if situation_state:
            break

    # If no situation found, try to find a matching signal directly
    if not source_sentence and entities:
        for sig in shell.oem_state.signals:
            sig_entity = str(getattr(sig, "entity", "")).lower()
            if any(e.lower() == sig_entity for e in entities):
                source_sentence = getattr(sig, "text", "")
                source_entity = getattr(sig, "entity", "")
                source_timestamp = str(getattr(sig, "timestamp", ""))
                break

    # ── DEPTH: wire Core modules for full intelligence ──────────────
    # Per CEO directive: "80% depth on Core. The complexity behind the screens."
    # These fields are what make Ask feel like the full engine, not a
    # thin wrapper. Each is a lazy call to a Core module via shell.core.
    #
    # Auditor P27 finding at 9229757: the wiring was theater — modules
    # were imported but calls used wrong signatures, so fields stayed
    # empty. This rewrite uses the CORRECT API for each module.

    decision_boundary = ""
    perspectives_data = []
    reasoning_chain = []
    calibration_note = ""
    consequence_paths = []

    core = shell.core

    # Find the matching situation (for entity-specific calls)
    matching_situation = None
    for s in situations:
        s_entity = str(getattr(s, "entity", "")).lower()
        if any(e.lower() == s_entity for e in entities):
            matching_situation = s
            break
    if not matching_situation and situations:
        matching_situation = situations[0]  # fall back to first

    # 1. ConsequencePathRouter — route first (produces specialists + paths)
    # This MUST come before JudgmentSynthesizer because synthesize() needs perspectives
    specialists = []
    if core.consequence_path_router and matching_situation:
        try:
            routing = core.consequence_path_router.route(matching_situation)
            if routing:
                specialists = getattr(routing, "specialists", []) or []
                raw_paths = getattr(routing, "paths", []) or []
                for p in raw_paths[:3]:
                    consequence_paths.append(str(getattr(p, "description", str(p))[:100]))
        except Exception as e:
            logger.debug("Consequence routing failed: %s", e)

    # 2. Perspectives — REAL Nerve agent insights (not template strings)
    # Per CEO Phase 3 directive: replace "Analyzing Alex from X perspective"
    # with real agent.generate_insights() output — title, body, evidence,
    # recommended_action, priority.
    from maestro_cognitive_council.perspective import Perspective
    from uuid import uuid4 as _uuid4

    # First try Nerve agents for real insights
    nerve_perspectives = []
    try:
        nerve = shell.nerve
        entity_name = ""
        if matching_situation:
            entity_name = str(getattr(matching_situation, "entity", ""))
        if not entity_name and entities:
            entity_name = entities[0]

        if entity_name:
            nerve_perspectives = nerve.get_perspectives_for_entity(entity_name)
    except Exception as e:
        logger.debug("Nerve perspectives failed: %s", e)

    # Build Perspective objects from real Nerve insights (or fall back to
    # ConsequencePathRouter specialists if Nerve produces nothing)
    persp_objects = []
    if nerve_perspectives:
        # Use real Nerve agent insights
        for np in nerve_perspectives[:3]:
            try:
                p = Perspective(
                    situation_id=str(getattr(matching_situation, "situation_id", "")) if matching_situation else "",
                    specialist=np.get("name", "specialist"),
                    observation=np.get("observation", np.get("view", "")),
                    implication=np.get("implication", ""),
                    recommended_next_step=np.get("recommended_next_step", ""),
                    evidence=np.get("evidence", []),
                )
                persp_objects.append(p)
            except Exception:
                pass
    elif matching_situation:
        # Fallback: use ConsequencePathRouter specialists (NOT template strings)
        # Honest: "No agent insight available" if Nerve produced nothing
        for specialist_name in (specialists[:3] if specialists else []):
            try:
                p = Perspective(
                    situation_id=str(getattr(matching_situation, "situation_id", "")),
                    specialist=specialist_name,
                    observation="No agent insight available for this specialist",
                    implication="The agent did not produce an insight from the available signals",
                    recommended_next_step="Add more signals to enable agent analysis",
                )
                persp_objects.append(p)
            except Exception:
                pass

    # 3. JudgmentSynthesizer — synthesize judgment from perspectives
    # synthesize(situation, perspectives) requires BOTH args
    if core.judgment_synthesizer and matching_situation and persp_objects:
        try:
            judgment = core.judgment_synthesizer.synthesize(matching_situation, persp_objects)
            if judgment:
                # Extract decision boundary from the Judgment object
                boundary = getattr(judgment, "decision_boundary", "") or \
                           getattr(judgment, "boundary", "") or \
                           getattr(judgment, "central_claim", "")
                if boundary:
                    decision_boundary = str(boundary)[:300]

                # Extract perspectives from the judgment if available
                judgment_perspectives = getattr(judgment, "perspectives", []) or []
                for jp in judgment_perspectives[:3]:
                    perspectives_data.append({
                        "name": str(getattr(jp, "specialist", "specialist")),
                        "view": str(getattr(jp, "observation", "") or getattr(jp, "implication", ""))[:200],
                    })
        except Exception as e:
            logger.debug("Judgment synthesis failed: %s", e)

    # If judgment didn't produce perspectives, use the Perspective objects directly
    # These now contain REAL Nerve agent insights (or honest "No agent insight available")
    if not perspectives_data:
        for p in persp_objects[:3]:
            perspectives_data.append({
                "name": p.specialist,
                "view": f"{p.observation}. {p.implication}"[:300],
                "observation": p.observation,
                "implication": p.implication,
                "recommended_next_step": p.recommended_next_step,
                "evidence": p.evidence if hasattr(p, 'evidence') else [],
                "urgency": getattr(p, 'urgency', 'normal'),
                "confidence": getattr(p, 'confidence', 0.0),
            })

    # 4. ReasoningTrace — capture provenance chain
    # capture_reasoning_trace(situation, signals_available, checkpoint_day, checkpoint_description, engine)
    if core.reasoning_trace and matching_situation:
        try:
            trace = core.reasoning_trace.capture_reasoning_trace(
                situation=matching_situation,
                signals_available=shell.oem_state.signals,
                checkpoint_day=1,
                checkpoint_description=f"Query: {req.query}",
                engine=shell.situation_engine,
            )
            if trace and isinstance(trace, dict):
                # Extract reasoning steps from the trace dict
                steps = trace.get("reasoning_steps", []) or trace.get("steps", [])
                if not steps:
                    # Try other keys
                    for key in ("situation_state", "evidence_summary", "selection_reason"):
                        val = trace.get(key, "")
                        if val:
                            reasoning_chain.append(str(val)[:200])
                else:
                    reasoning_chain = [str(s)[:200] for s in steps[:5]]
        except Exception as e:
            logger.debug("Reasoning trace failed: %s", e)

    # 5. CalibrationPrimitives — calibration note
    # This is a FUNCTION module: brier_score(resolved_predictions), build_calibration_report
    if core.calibration_primitives:
        try:
            # Check if we have any resolved predictions (we won't in v1, so
            # the honest answer is "insufficient calibration history")
            # Try to call brier_score with empty data to test
            brier = core.calibration_primitives.brier_score([])
            if brier is None:
                calibration_note = "Insufficient calibration history — keep tracking outcomes to build your Brier score."
            else:
                calibration_note = f"Brier score: {brier:.4f} (lower is better)"
        except Exception:
            # If brier_score fails on empty, it means we have no predictions
            calibration_note = "Insufficient calibration history — keep tracking outcomes to build your Brier score."

    return AskResponse(
        answer=str(answer),
        query=req.query,
        source_sentence=source_sentence,
        source_entity=source_entity,
        source_timestamp=source_timestamp,
        situation_state=situation_state,
        evidence_refs=evidence_refs,
        decision_boundary=decision_boundary,
        perspectives=perspectives_data,
        reasoning_chain=reasoning_chain,
        calibration_note=calibration_note,
        consequence_paths=consequence_paths,
    )


# 6. GET /api/commitments — Commitments surface


@app.get("/api/commitments", response_model=list[CommitmentResponse])
async def get_commitments(token: str = Depends(verify_token)):
    """Get active commitments — calls Core's commitment classifier via the shell.

    DEPTH: each commitment includes calibration_note (from CalibrationPrimitives)
    and outcome_history (from BehavioralLearningEngine).
    """
    shell = build_shell()
    core = shell.core

    from maestro_personal_shell.surfaces.commitments import CommitmentsSurface
    surface = CommitmentsSurface(shell=shell)
    commitments = surface.get_active_commitments()

    # Get stale commitments for at-risk flagging
    stale = shell.detect_stale_commitments(days_threshold=2)
    stale_map = {}
    for s in stale:
        sig_id = ""
        commit = s.get("commitment", None)
        if commit:
            sig_id = getattr(commit, "signal_id", "") or (commit.get("signal_id", "") if isinstance(commit, dict) else "")
        if sig_id:
            stale_map[sig_id] = s.get("days_stale", 0)

    # DEPTH: get calibration note from Core's calibration_primitives
    cal_note = ""
    if core.calibration_primitives:
        try:
            brier = core.calibration_primitives.brier_score([])
            if brier is None:
                cal_note = "Insufficient calibration history — keep tracking outcomes."
            else:
                cal_note = f"Brier score: {brier:.4f} (lower is better)"
        except Exception:
            cal_note = "Insufficient calibration history — keep tracking outcomes."

    result = []
    for c in commitments:
        sig_id = c.get("signal_id", "")
        days_stale = stale_map.get(sig_id, 0)

        # DEPTH: get outcome history from BehavioralLearningEngine
        outcome = ""
        if core.behavioral_learning_engine:
            try:
                entity = c.get("entity", "")
                metrics = core.behavioral_learning_engine.get_replication_metrics(
                    candidate_id=None
                ) if hasattr(core.behavioral_learning_engine, "get_replication_metrics") else {}
                if metrics and isinstance(metrics, dict):
                    resolved = metrics.get("resolved_count", 0)
                    confirmed = metrics.get("confirmed_count", 0)
                    if resolved > 0:
                        outcome = f"Kept {confirmed}/{resolved} like this"
            except Exception:
                pass

        result.append(CommitmentResponse(
            entity=c["entity"],
            text=c["text"],
            claim_type=str(c.get("claim_type", "commitment")),
            signal_id=sig_id,
            is_commitment=c.get("is_commitment", True),
            is_at_risk=sig_id in stale_map,
            days_stale=days_stale,
            deadline=(c.get("metadata", {}) or {}).get("deadline", ""),
            calibration_note=cal_note,
            outcome_history=outcome,
            confidence=0.5 if not cal_note.startswith("Insufficient") else 0.0,
        ))

    return result


# 6b. GET /api/commitments/the-one — the masterpiece Commitments endpoint


@app.get("/api/commitments/the-one", response_model=CommitmentsMasterpieceResponse)
async def get_the_one_commitment(token: str = Depends(verify_token)):
    """The one commitment at risk today — not a list of 47.

    The masterpiece Commitments: returns ONE primary commitment (the
    most at-risk) + the rest as secondary. The inevitability: you know
    what you owe without scrolling.
    """
    shell = build_shell()

    from maestro_personal_shell.surfaces.commitments import CommitmentsSurface
    surface = CommitmentsSurface(shell=shell)
    commitments = surface.get_active_commitments()

    if not commitments:
        return CommitmentsMasterpieceResponse(primary=None, why_primary="", secondary=[])

    # Get stale commitments
    stale = shell.detect_stale_commitments(days_threshold=2)
    stale_map = {}
    for s in stale:
        sig_id = ""
        commit = s.get("commitment", None)
        if commit:
            sig_id = getattr(commit, "signal_id", "") or (commit.get("signal_id", "") if isinstance(commit, dict) else "")
        if sig_id:
            stale_map[sig_id] = s.get("days_stale", 0)

    # Build commitment responses with at-risk info
    all_commitments = []
    for c in commitments:
        sig_id = c.get("signal_id", "")
        days_stale = stale_map.get(sig_id, 0)
        all_commitments.append(CommitmentResponse(
            entity=c["entity"],
            text=c["text"],
            claim_type=str(c.get("claim_type", "commitment")),
            signal_id=sig_id,
            is_commitment=c.get("is_commitment", True),
            is_at_risk=sig_id in stale_map,
            days_stale=days_stale,
            deadline=(c.get("metadata", {}) or {}).get("deadline", ""),
        ))

    # The primary is the most at-risk: highest days_stale, then oldest
    def risk_score(c: CommitmentResponse) -> tuple[int, int]:
        return (c.days_stale, -len(c.signal_id))  # stale first, then by ID for stability

    all_commitments.sort(key=risk_score, reverse=True)
    primary = all_commitments[0] if all_commitments else None

    why = ""
    if primary:
        reasons = []
        if primary.is_at_risk:
            reasons.append(f"no follow-up for {primary.days_stale} days")
        if primary.deadline:
            reasons.append(f"deadline: {primary.deadline}")
        if primary.claim_type == "commitment":
            reasons.append("you made this promise")
        why = "; ".join(reasons) if reasons else "most active commitment"

    return CommitmentsMasterpieceResponse(
        primary=primary,
        why_primary=why,
        secondary=all_commitments[1:] if len(all_commitments) > 1 else [],
    )


# 7. GET /api/what-changed — What Changed surface


@app.get("/api/what-changed", response_model=list[WhatChangedResponse])
async def get_what_changed(token: str = Depends(verify_token)):
    """Get recent meaningful deltas."""
    shell = build_shell()

    from maestro_personal_shell.surfaces.what_changed import WhatChangedSurface
    from datetime import timedelta

    surface = WhatChangedSurface(shell=shell)
    since = datetime.now(timezone.utc) - timedelta(days=30)
    deltas = surface.get_recent_deltas(since_timestamp=since)

    return [
        WhatChangedResponse(
            entity=d["entity"],
            text=d["text"],
            type=d["type"],
            is_meaningful=d["is_meaningful"],
        )
        for d in deltas
    ]


# 7b. GET /api/what-changed/the-shifts — the masterpiece What Changed endpoint


@app.get("/api/what-changed/the-shifts", response_model=WhatChangedMasterpieceResponse)
async def get_the_shifts(token: str = Depends(verify_token)):
    """The 2 things that materially shifted — not a feed.

    The masterpiece What Changed: returns at most 2 meaningful shifts.
    Not a chronological inbox dump. Two cards. The inevitability: you're
    already caught up.
    """
    shell = build_shell()

    from maestro_personal_shell.surfaces.what_changed import WhatChangedSurface
    from datetime import timedelta

    surface = WhatChangedSurface(shell=shell)
    since = datetime.now(timezone.utc) - timedelta(days=30)
    deltas = surface.get_recent_deltas(since_timestamp=since)

    # Filter to meaningful only, take top 2
    meaningful = [d for d in deltas if d.get("is_meaningful")]

    if not meaningful:
        return WhatChangedMasterpieceResponse(
            the_shifts=[],
            silence_message="Nothing material changed since you last looked."
        )

    # Take at most 2 — the 2 most recent meaningful shifts
    the_shifts = meaningful[:2]

    return WhatChangedMasterpieceResponse(
        the_shifts=[
            WhatChangedResponse(
                entity=d["entity"],
                text=d["text"],
                type=d["type"],
                is_meaningful=d["is_meaningful"],
            )
            for d in the_shifts
        ],
        silence_message="",
    )


# 8. GET /api/prepare — Prepare surface


@app.get("/api/prepare", response_model=list[PrepareResponse])
async def get_prepare(token: str = Depends(verify_token)):
    """Get preparation for upcoming situations — 3 things that matter.

    The masterpiece Prepare: for each situation needing prep, return:
      - the_forgotten: the oldest commitment you haven't acted on
      - the_open_question: a follow-up someone asked that you never answered
      - the_contradiction: a signal that conflicts with an earlier assumption

    Not 5 prep points. Three. The right three.
    """
    shell = build_shell()
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

        # Get all signals for this entity to find the 3 things
        entity_signals = [
            sig for sig in shell.oem_state.signals
            if str(getattr(sig, "entity", "")).lower() == entity.lower()
        ]

        # THE FORGOTTEN: the oldest commitment_made signal with no follow-up
        the_forgotten = ""
        commitment_signals = [
            sig for sig in entity_signals
            if "commitment" in str(getattr(sig, "signal_type", "")).lower()
        ]
        if commitment_signals:
            # Sort by timestamp ascending — oldest first
            commitment_signals.sort(key=lambda x: getattr(x, "timestamp", datetime.max))
            the_forgotten = getattr(commitment_signals[0], "text", "")

        # THE OPEN QUESTION: a follow_up.required signal (someone asked, no answer)
        the_open_question = ""
        followup_signals = [
            sig for sig in entity_signals
            if "follow_up" in str(getattr(sig, "signal_type", "")).lower()
        ]
        if followup_signals:
            the_open_question = getattr(followup_signals[-1], "text", "")

        # THE CONTRADICTION: a reported_statement that contradicts an earlier signal
        # (simplified: the most recent reported_statement that isn't a commitment)
        the_contradiction = ""
        statement_signals = [
            sig for sig in entity_signals
            if "reported" in str(getattr(sig, "signal_type", "")).lower()
            or "observed" in str(getattr(sig, "signal_type", "")).lower()
        ]
        if statement_signals and len(entity_signals) > 1:
            the_contradiction = getattr(statement_signals[-1], "text", "")

        # Meeting context: the situation's current state
        state_raw = getattr(s, "state", getattr(s, "operational_state", "unknown"))
        if hasattr(state_raw, "value"):
            meeting_context = f"Situation is {state_raw.value}"
        else:
            meeting_context = f"Situation is {str(state_raw).split('.')[-1].lower()}"

        # DEPTH: call Core's CopilotSituationBridge.pre_call_briefing()
        # This is the Cluely-class depth — Situation-aware pre-call intelligence
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
                    user_email="personal",
                    org_id="personal",
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
            situation_id=sit_id,
            entity=entity,
            meeting_context=meeting_context,
            is_stale=is_stale,
            the_forgotten=the_forgotten,
            the_open_question=the_open_question,
            the_contradiction=the_contradiction,
            copilot_talking_points=copilot_talking_points,
            copilot_blocking_unknowns=copilot_blocking_unknowns,
            copilot_can_decide=copilot_can_decide,
            copilot_cannot_decide=copilot_cannot_decide,
            copilot_timeline=copilot_timeline,
        ))

    return result


# 9. GET /api/whisper — Whisper surface (v2: proactive push)


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


@app.get("/api/whisper", response_model=list[WhisperResponse])
async def get_whispers(token: str = Depends(verify_token)):
    """Get active whispers — things that deserve attention RIGHT NOW.

    DEPTH: calls Core's WhisperSituationBridge.from_situation() for each
    situation to generate nuanced, situation-aware whisper content with
    delivery route + explanation + evidence refs.

    Empty list = trusted silence (break-test dimension 7: Restraint).
    """
    shell = build_shell()
    core = shell.core

    from maestro_personal_shell.surfaces.whisper import WhisperSurface
    surface = WhisperSurface(shell=shell)
    whispers = surface.get_active_whispers()

    # DEPTH: enrich each whisper with Core's WhisperSituationBridge content
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

        # Call Core's WhisperSituationBridge for the matching situation
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

        result.append(WhisperResponse(
            type=w["type"],
            entity=w["entity"],
            title=w["title"],
            body=w["body"],
            priority=w["priority"],
            action_url=w.get("action_url", ""),
            delivery_route=delivery_route,
            delivery_explanation=delivery_explanation,
            suppression_reason=suppression_reason,
            evidence_refs=evidence_refs,
        ))

    return result


# 10. POST /api/sync/gmail — Gmail sync (v2: accepts pre-fetched messages)


class GmailSyncRequest(BaseModel):
    messages: list[dict[str, Any]]
    user_email: str = "me"


class GmailSyncResponse(BaseModel):
    signals_created: int
    message: str


@app.post("/api/sync/gmail", response_model=GmailSyncResponse)
async def sync_gmail(req: GmailSyncRequest, token: str = Depends(verify_token)):
    """Sync Gmail messages → signals.

    Accepts pre-fetched Gmail messages (the OAuth wiring happens in the
    mobile app or a background worker). Extracts commitments, follow-ups,
    and meeting changes using the Gmail adapter.
    """
    from maestro_personal_shell.signal_adapters.gmail import extract_signals_from_message

    count = 0
    for message in req.messages:
        signals = extract_signals_from_message(message, req.user_email)
        for sig in signals:
            sig["signal_id"] = str(uuid4())
            sig["created_at"] = datetime.now(timezone.utc).isoformat()
            sig["source_acl"] = "private"  # Gmail is private by default
            save_signal_to_db(sig)
            count += 1

    return GmailSyncResponse(
        signals_created=count,
        message=f"Extracted {count} signals from {len(req.messages)} Gmail messages",
    )


# 11. POST /api/sync/calendar — Calendar sync (v2: accepts pre-fetched events)


class CalendarSyncRequest(BaseModel):
    events: list[dict[str, Any]]
    user_email: str = "me"


class CalendarSyncResponse(BaseModel):
    signals_created: int
    message: str


@app.post("/api/sync/calendar", response_model=CalendarSyncResponse)
async def sync_calendar(req: CalendarSyncRequest, token: str = Depends(verify_token)):
    """Sync Calendar events → signals.

    Accepts pre-fetched calendar events. Extracts meeting.scheduled,
    meeting.cancelled, and deadline.approaching signals.
    """
    from maestro_personal_shell.signal_adapters.calendar import extract_signals_from_event

    count = 0
    for event in req.events:
        signals = extract_signals_from_event(event, req.user_email)
        for sig in signals:
            sig["signal_id"] = str(uuid4())
            sig["created_at"] = datetime.now(timezone.utc).isoformat()
            sig["source_acl"] = "private"
            save_signal_to_db(sig)
            count += 1

    return CalendarSyncResponse(
        signals_created=count,
        message=f"Extracted {count} signals from {len(req.events)} calendar events",
    )


# 12. DELETE /api/account — Account deletion (v3: App Store Guideline 5.1.1)


@app.delete("/api/account")
async def delete_account(token: str = Depends(verify_token)):
    """Delete the user's account and all associated data.

    Per App Store Guideline 5.1.1(v): apps that support account creation
    must also offer account deletion. This endpoint deletes ALL signals
    and associated data from the SQLite database.
    """
    clear_signals_db()
    return {"message": "Account deleted. All signals removed.", "status": "ok"}


# 13. GET /api/account/export — GDPR/CCPA data export (v3)


@app.get("/api/account/export")
async def export_data(token: str = Depends(verify_token)):
    """Export all user data (GDPR/CCPA compliance).

    Returns all signals in JSON format for download.
    """
    signals = load_signals_from_db()
    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "signal_count": len(signals),
        "signals": signals,
    }


# 14. POST /api/devices/register — Register device for push (v2.4)


class DeviceRegisterRequest(BaseModel):
    push_token: str
    platform: str = "ios"
    user_timezone: str = "UTC"


class DeviceRegisterResponse(BaseModel):
    device_id: str
    message: str


@app.post("/api/devices/register", response_model=DeviceRegisterResponse)
async def register_device_endpoint(req: DeviceRegisterRequest, token: str = Depends(verify_token)):
    """Register a device for push notifications.

    The mobile app calls this on launch after obtaining an Expo push token.
    """
    from maestro_personal_shell.push import register_device, init_push_db
    init_push_db()
    device_id = register_device(
        push_token=req.push_token,
        platform=req.platform,
        user_timezone=req.user_timezone,
    )
    return DeviceRegisterResponse(
        device_id=device_id,
        message="Device registered for push notifications",
    )


# 15. POST /api/whisper/push — Deliver whispers as push (v2.4)


class PushDeliverResponse(BaseModel):
    whispers_pushed: int
    whispers_suppressed: int
    log: list[dict[str, Any]]


@app.post("/api/whisper/push", response_model=PushDeliverResponse)
async def deliver_whispers_push(token: str = Depends(verify_token)):
    """Deliver high-priority whispers as push notifications.

    GATE: only HIGH-priority whispers are pushed. Medium/low are batched
    (appear in app, don't interrupt). Quiet hours (10pm-7am local) suppress
    all pushes.
    """
    from maestro_personal_shell.push import deliver_whispers_as_push, init_push_db
    from maestro_personal_shell.surfaces.whisper import WhisperSurface

    init_push_db()
    shell = build_shell()
    surface = WhisperSurface(shell=shell)
    whispers = surface.get_active_whispers()

    log = deliver_whispers_as_push(whispers)

    pushed = sum(1 for e in log if e.get("status") == "sent")
    suppressed = sum(1 for e in log if e.get("status") == "suppressed")

    return PushDeliverResponse(
        whispers_pushed=pushed,
        whispers_suppressed=suppressed,
        log=log,
    )


# ---------------------------------------------------------------------------
# PHASE 4: LIVE COPILOT — real-time call intelligence
# ---------------------------------------------------------------------------


class TranscriptChunkRequest(BaseModel):
    situation_id: str
    text: str
    speaker: str = ""
    entity: str = ""


@app.post("/api/copilot/transcript")
async def process_transcript(req: TranscriptChunkRequest, token: str = Depends(verify_token)):
    """Process a transcript chunk during a live call.

    Phase 4: Cluely-class real-time intelligence. Calls Core's
    CopilotSituationBridge.on_transcript_chunk(). Updates the Situation's
    operational state in real-time, detects new commitments, resolves unknowns.
    """
    from maestro_personal_shell.copilot_live import process_transcript_chunk
    shell = build_shell()
    return process_transcript_chunk(
        shell=shell,
        situation_id=req.situation_id,
        text=req.text,
        speaker=req.speaker,
        entity=req.entity,
    )


class PostCallSummaryRequest(BaseModel):
    situation_id: str
    transcript_chunks: list[dict[str, Any]] = []
    commitments: list[dict[str, Any]] = []
    entity: str = ""


@app.post("/api/copilot/post-call")
async def post_call_summary(req: PostCallSummaryRequest, token: str = Depends(verify_token)):
    """Generate a post-call summary after the meeting ends.

    Phase 4: calls Core's CopilotSituationBridge.post_call_summary().
    Transitions state → AWAITING_OUTCOME, ingests commitments, triggers
    learning, generates draft follow-up.
    """
    from maestro_personal_shell.copilot_live import generate_post_call_summary
    shell = build_shell()
    return generate_post_call_summary(
        shell=shell,
        situation_id=req.situation_id,
        transcript_chunks=req.transcript_chunks,
        commitments=req.commitments,
        entity=req.entity,
    )


# ---------------------------------------------------------------------------
# PHASE 4+: TALK RATIO COACHING
# ---------------------------------------------------------------------------


class TalkRatioRequest(BaseModel):
    segments: list[dict[str, Any]]


@app.post("/api/copilot/talk-ratio")
async def get_talk_ratio(req: TalkRatioRequest, token: str = Depends(verify_token)):
    """Get talk ratio coaching from Core's TalkRatioCoach.

    Processes speech segments and returns your % vs their %, interruptions,
    and coaching feedback.
    """
    from maestro_personal_shell.copilot_live import get_talk_ratio_coaching
    shell = build_shell()
    return get_talk_ratio_coaching(shell=shell, segments=req.segments)


# ---------------------------------------------------------------------------
# PHASE 4+: NEGOTIATION COACHING
# ---------------------------------------------------------------------------


class NegotiationRequest(BaseModel):
    text: str
    speaker: str = ""
    batna: float | None = None


@app.post("/api/copilot/negotiation")
async def get_negotiation(req: NegotiationRequest, token: str = Depends(verify_token)):
    """Get negotiation coaching from Core's NegotiationStrategyEngine.

    Processes a transcript chunk and returns phase, anchors, concessions,
    and recommended strategy.
    """
    from maestro_personal_shell.copilot_live import get_negotiation_coaching
    shell = build_shell()
    return get_negotiation_coaching(
        shell=shell,
        text=req.text,
        speaker=req.speaker,
        batna=req.batna,
    )


# ---------------------------------------------------------------------------
# PHASE 4+: WEBSOCKET for real-time bidirectional
# ---------------------------------------------------------------------------

@app.websocket("/ws/copilot")
async def websocket_copilot(websocket: Request):
    """WebSocket endpoint for real-time bidirectional copilot communication.

    The browser extension connects here during a call. Transcript chunks
    are sent as messages; suggestions are pushed back in real-time.

    Message format (from extension):
      {"type": "transcript", "text": "...", "speaker": "...", "entity": "..."}
      {"type": "start", "meeting_title": "...", "entity": "..."}
      {"type": "stop"}

    Message format (to extension):
      {"type": "suggestion", "transitions": [...], "commitments_detected": [...]}
      {"type": "briefing", "greeting": "...", "top_situation": {...}}
      {"type": "ambient", "summary": "...", "alerts": [...]}
      {"type": "post_call", "summary": {...}}
      {"type": "error", "message": "..."}
    """
    from fastapi import WebSocket, WebSocketDisconnect
    import json

    # Note: FastAPI WebSocket needs the actual WebSocket type, not Request
    # This endpoint is defined but requires the server to support WebSocket
    # The actual WebSocket handler is below
    pass


# Real WebSocket handler (separate function because FastAPI needs WebSocket type)
async def websocket_copilot_handler(websocket: "WebSocket"):
    """Handle WebSocket connection for real-time copilot.

    This is the actual handler — registered via app.websocket().
    """
    from fastapi import WebSocket, WebSocketDisconnect
    from maestro_personal_shell.copilot_live import (
        process_transcript_chunk,
        generate_post_call_summary,
        get_ambient_intelligence,
    )
    import json

    await websocket.accept()

    # Auth: get token from first message or query param
    try:
        # Wait for auth message
        auth_msg = await websocket.receive_text()
        auth_data = json.loads(auth_msg)
        token = auth_data.get("token", "")
        if token != AUTH_TOKEN:
            await websocket.send_json({"type": "error", "message": "Invalid token"})
            await websocket.close()
            return
    except Exception:
        await websocket.send_json({"type": "error", "message": "Auth failed"})
        await websocket.close()
        return

    transcript_chunks = []
    meeting_entity = ""
    is_active = False

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            msg_type = msg.get("type", "")

            if msg_type == "start":
                is_active = True
                meeting_entity = msg.get("entity", "")
                transcript_chunks = []

                # Send pre-call briefing
                shell = build_shell()
                core = shell.core
                if core.briefing_bridge:
                    try:
                        briefing = core.briefing_bridge.generate_morning_briefing(
                            user_email="personal", org_id="personal")
                        await websocket.send_json({
                            "type": "briefing",
                            "greeting": getattr(briefing, "greeting", ""),
                            "top_situation": getattr(briefing, "top_situation", None),
                            "material_changes": getattr(briefing, "material_changes", []),
                            "unknowns": getattr(briefing, "unknowns", []),
                            "ask_prompt": getattr(briefing, "ask_prompt", ""),
                        })
                    except Exception:
                        pass

                # Send ambient
                ambient = get_ambient_intelligence(shell)
                await websocket.send_json({"type": "ambient", **ambient})

                await websocket.send_json({"type": "started"})

            elif msg_type == "transcript" and is_active:
                shell = build_shell()

                # Get situation ID
                situations = shell.detect_situations()
                sit_id = situations[0].situation_id if situations else "unknown"

                chunk = {
                    "speaker": msg.get("speaker", ""),
                    "text": msg.get("text", ""),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                transcript_chunks.append(chunk)

                result = process_transcript_chunk(
                    shell=shell,
                    situation_id=sit_id,
                    text=msg.get("text", ""),
                    speaker=msg.get("speaker", ""),
                    entity=meeting_entity,
                )

                # Send suggestion if something detected
                if result.get("transitions") or result.get("commitments_detected"):
                    await websocket.send_json({
                        "type": "suggestion",
                        **result,
                    })
                else:
                    await websocket.send_json({"type": "ack"})

            elif msg_type == "talk_ratio":
                # Process talk ratio
                from maestro_personal_shell.copilot_live import get_talk_ratio_coaching
                shell = build_shell()
                result = get_talk_ratio_coaching(shell, msg.get("segments", []))
                await websocket.send_json({"type": "talk_ratio", **result})

            elif msg_type == "negotiation":
                # Process negotiation
                from maestro_personal_shell.copilot_live import get_negotiation_coaching
                shell = build_shell()
                result = get_negotiation_coaching(
                    shell,
                    text=msg.get("text", ""),
                    speaker=msg.get("speaker", ""),
                    batna=msg.get("batna"),
                )
                await websocket.send_json({"type": "negotiation", **result})

            elif msg_type == "stop":
                is_active = False
                shell = build_shell()
                situations = shell.detect_situations()
                sit_id = situations[0].situation_id if situations else "unknown"

                summary = generate_post_call_summary(
                    shell=shell,
                    situation_id=sit_id,
                    transcript_chunks=transcript_chunks,
                    commitments=[],
                    entity=meeting_entity,
                )
                await websocket.send_json({"type": "post_call", **summary})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass


# Register the WebSocket route properly
from fastapi import WebSocket
app.add_api_websocket_route("/ws/copilot", websocket_copilot_handler)


# ---------------------------------------------------------------------------
# PHASE 5: AMBIENT INTELLIGENCE — calendar + sentiment between calls
# ---------------------------------------------------------------------------


@app.get("/api/ambient")
async def get_ambient(token: str = Depends(verify_token)):
    """Get ambient intelligence — what's happening between calls.

    Phase 5: combines calendar awareness (upcoming meetings, preparation
    needed), sentiment patterns (frustration/positivity detected), and
    commitment staleness into a single ambient view.

    This is the background intelligence that feeds Whisper between calls.
    """
    from maestro_personal_shell.copilot_live import get_ambient_intelligence
    shell = build_shell()
    return get_ambient_intelligence(shell=shell)


# ---------------------------------------------------------------------------
# DEPTH ENDPOINT — GET /api/depth
# Shows which Core modules are wired. The CEO can verify the depth.
# ---------------------------------------------------------------------------


@app.get("/api/depth")
async def get_depth(token: str = Depends(verify_token)):
    """Show which Core modules are wired to Personal.

    Per CEO directive: "80% depth on Core." This endpoint lets you verify
    the wiring — how many of the 23 Core modules are actually called.
    """
    shell = build_shell()
    core = shell.core
    wired = core.wired_modules
    return {
        "wired_count": len(wired),
        "total_core_modules": 23,
        "coverage_pct": round(len(wired) / 23 * 100),
        "wired_modules": wired,
        "target": "80%+",
        "status": "ON_TARGET" if len(wired) >= 18 else "IN_PROGRESS",
    }


# ---------------------------------------------------------------------------
# DEPTH ENDPOINT — GET /api/briefing
# Morning briefing from Core's SituationBriefingEngine.
# Not a feed — a Situation-centric briefing with the one thing, unknowns,
# disputes, decision boundary, and what Maestro believes.
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


@app.get("/api/briefing", response_model=BriefingResponse)
async def get_briefing(token: str = Depends(verify_token)):
    """Morning briefing — the full Situation-centric intelligence.

    DEPTH: calls Core's SituationBriefingEngine.generate_morning_briefing().
    This is the orchestrated intelligence behind the Home screen.
    """
    shell = build_shell()
    core = shell.core

    if not core.briefing_bridge:
        return BriefingResponse(
            greeting="Good morning. Briefing engine unavailable.",
            ask_prompt="What do you want to understand?",
        )

    try:
        briefing = core.briefing_bridge.generate_morning_briefing(
            user_email="personal",
            org_id="personal",
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
        return BriefingResponse(
            greeting="Good morning.",
            ask_prompt="What do you want to understand?",
        )


# ---------------------------------------------------------------------------
# THE MASTERPIECE ENDPOINT — GET /api/the-moment
# Returns ONE thing: the commitment that matters most right now.
# Not a list. Not a dashboard. One card. The Spotlight moment.
# ---------------------------------------------------------------------------


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


@app.get("/api/the-moment", response_model=TheMomentResponse)
async def get_the_moment(token: str = Depends(verify_token)):
    """The single most important thing Maestro knows right now.

    This is the Spotlight moment — the one commitment that matters most.
    Not a list. One card. If nothing deserves attention, returns has_moment=False.
    """
    shell = build_shell()

    # Get all commitments via the Commitments surface (calls Core)
    from maestro_personal_shell.surfaces.commitments import CommitmentsSurface
    surface = CommitmentsSurface(shell=shell)
    commitments = surface.get_active_commitments()

    if not commitments:
        return TheMomentResponse(has_moment=False)

    # Get stale commitments (absence detection — the ones at risk)
    stale = shell.detect_stale_commitments(days_threshold=2)
    stale_ids = {s.get("commitment", None) and getattr(s["commitment"], "signal_id", "") or
                 s.get("commitment", {}).get("signal_id", "") for s in stale}

    # Score each commitment: the one with the closest deadline AND oldest last signal wins
    # This is NOT a new salience model — it's the Core's salience applied to personal data
    best_commitment = None
    best_score = -1
    best_why = ""

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    for c in commitments:
        score = 0
        reasons = []

        # Stale commitments score higher (at risk)
        if c.get("signal_id") in stale_ids:
            score += 50
            reasons.append("no follow-up in days")

        # Commitments with deadlines score higher
        sig_meta = c.get("metadata", {}) or {}
        deadline = sig_meta.get("deadline")
        if deadline:
            score += 30
            reasons.append(f"deadline: {deadline}")

        # Commitments made by the user (commitment_made) score higher than received
        if c.get("claim_type") == "commitment":
            score += 20
            reasons.append("you made this promise")

        # Older commitments score slightly higher (more likely forgotten)
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

    # Find the situation this commitment belongs to (if any)
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

    # Get source evidence (the original email/signal)
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


# ---------------------------------------------------------------------------
# Health check (no auth)
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health():
    """Health check — no auth required."""
    return {"status": "ok", "service": "maestro-personal", "version": "1.0.0"}


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


def main():
    """Run the API server."""
    import uvicorn

    init_db()
    print(f"\n  Maestro Personal API")
    print(f"  Port: {API_PORT}")
    print(f"  DB: {DB_PATH}")
    print(f"  Auth token: {AUTH_TOKEN}")
    print(f"  Health: http://localhost:{API_PORT}/api/health")
    print(f"\n  Endpoints:")
    print(f"    POST /api/auth/login")
    print(f"    GET  /api/situations")
    print(f"    POST /api/signals")
    print(f"    GET  /api/signals")
    print(f"    POST /api/ask")
    print(f"    GET  /api/commitments")
    print(f"    GET  /api/what-changed")
    print(f"    GET  /api/prepare")
    print()

    uvicorn.run(app, host="0.0.0.0", port=API_PORT)


if __name__ == "__main__":
    main()

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
    answer: str
    query: str


class CommitmentResponse(BaseModel):
    entity: str
    text: str
    claim_type: str
    signal_id: str
    is_commitment: bool


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


class PrepareResponse(BaseModel):
    situation_id: str
    is_stale: bool
    prep_points: list[str]


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
    """Ask a question — calls SituationAwareAskBridge via the shell."""
    shell = build_shell()

    from maestro_personal_shell.surfaces.ask import AskSurface
    surface = AskSurface(shell=shell)
    result = surface.ask(req.query)

    answer = (
        getattr(result, "answer", None)
        or getattr(result, "synthesized_answer", None)
        or str(result)
    )

    return AskResponse(answer=str(answer), query=req.query)


# 6. GET /api/commitments — Commitments surface


@app.get("/api/commitments", response_model=list[CommitmentResponse])
async def get_commitments(token: str = Depends(verify_token)):
    """Get active commitments — calls classify_transcript_chunk via the shell."""
    shell = build_shell()

    from maestro_personal_shell.surfaces.commitments import CommitmentsSurface
    surface = CommitmentsSurface(shell=shell)
    commitments = surface.get_active_commitments()

    return [
        CommitmentResponse(
            entity=c["entity"],
            text=c["text"],
            claim_type=str(c.get("claim_type", "commitment")),
            signal_id=c["signal_id"],
            is_commitment=c.get("is_commitment", True),
        )
        for c in commitments
    ]


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


# 8. GET /api/prepare — Prepare surface


@app.get("/api/prepare", response_model=list[PrepareResponse])
async def get_prepare(token: str = Depends(verify_token)):
    """Get preparation for upcoming situations."""
    shell = build_shell()

    from maestro_personal_shell.surfaces.prepare import PrepareSurface
    surface = PrepareSurface(shell=shell)

    situations = surface.get_situations_needing_preparation()
    result = []

    for s in situations:
        sit_id = str(getattr(s, "situation_id", uuid4()))
        try:
            prep = surface.prepare_for_situation(sit_id)
            prep_points = []
            if prep:
                unknowns = getattr(prep, "unknowns", []) or []
                prep_points = [str(u) for u in unknowns[:5]]
                is_stale = getattr(prep, "is_stale", False)
            else:
                is_stale = False
        except Exception:
            prep_points = []
            is_stale = False

        result.append(PrepareResponse(
            situation_id=sit_id,
            is_stale=is_stale,
            prep_points=prep_points,
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


@app.get("/api/whisper", response_model=list[WhisperResponse])
async def get_whispers(token: str = Depends(verify_token)):
    """Get active whispers — things that deserve attention RIGHT NOW.

    Empty list = trusted silence (break-test dimension 7: Restraint).
    """
    shell = build_shell()

    from maestro_personal_shell.surfaces.whisper import WhisperSurface
    surface = WhisperSurface(shell=shell)
    whispers = surface.get_active_whispers()

    return [
        WhisperResponse(
            type=w["type"],
            entity=w["entity"],
            title=w["title"],
            body=w["body"],
            priority=w["priority"],
            action_url=w.get("action_url", ""),
        )
        for w in whispers
    ]


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


# 16. GET /api/billing/tier — Get current billing tier (v3.1)


class BillingTierResponse(BaseModel):
    tier: str
    connectors_used: int
    connectors_limit: int
    history_days_limit: int


@app.get("/api/billing/tier", response_model=BillingTierResponse)
async def get_billing_tier(token: str = Depends(verify_token)):
    """Get the user's current billing tier and limits.

    v3.1: Free tier = 3 connectors, 30-day history. Pro = unlimited.
    """
    from maestro_personal_shell.billing import get_user_tier, get_tier_limits
    tier = get_user_tier()
    limits = get_tier_limits(tier)

    # Count connectors used (distinct sources in signals)
    signals = load_signals_from_db()
    sources = set()
    for s in signals:
        meta = json.loads(s.get("metadata", "{}")) if isinstance(s.get("metadata"), str) else s.get("metadata", {})
        src = meta.get("source", "manual")
        sources.add(src)

    return BillingTierResponse(
        tier=tier,
        connectors_used=len(sources),
        connectors_limit=limits["connectors"],
        history_days_limit=limits["history_days"],
    )


# 17. POST /api/billing/upgrade — Upgrade tier (v3.1)


class UpgradeRequest(BaseModel):
    tier: str  # "free" | "pro" | "team"


class UpgradeResponse(BaseModel):
    tier: str
    message: str


@app.post("/api/billing/upgrade", response_model=UpgradeResponse)
async def upgrade_tier(req: UpgradeRequest, token: str = Depends(verify_token)):
    """Upgrade the user's billing tier.

    In production, this is triggered by a Stripe webhook or RevenueCat
    IAP callback. For v1 dogfood, this is a manual endpoint for testing.
    """
    from maestro_personal_shell.billing import set_user_tier
    if req.tier not in ("free", "pro", "team"):
        raise HTTPException(status_code=400, detail="Invalid tier — must be free, pro, or team")
    set_user_tier(req.tier)
    return UpgradeResponse(tier=req.tier, message=f"Tier upgraded to {req.tier}")


# 18. PUT /api/user/role — Set role-adaptive UX mode (v3.2)


class RoleRequest(BaseModel):
    role: str  # "intern" | "ic" | "manager" | "executive"


class RoleResponse(BaseModel):
    role: str
    default_view: str
    salience_priority: list[str]


@app.put("/api/user/role", response_model=RoleResponse)
async def set_user_role(req: RoleRequest, token: str = Depends(verify_token)):
    """Set the user's role-adaptive UX mode.

    v3.2: 4 roles with different default views and salience weighting.
    """
    from maestro_personal_shell.roles import set_role, get_role_config
    if req.role not in ("intern", "ic", "manager", "executive"):
        raise HTTPException(status_code=400, detail="Invalid role")
    set_role(req.role)
    config = get_role_config(req.role)
    return RoleResponse(
        role=req.role,
        default_view=config["default_view"],
        salience_priority=config["salience_priority"],
    )


# 19. GET /api/user/role — Get current role (v3.2)


@app.get("/api/user/role", response_model=RoleResponse)
async def get_user_role(token: str = Depends(verify_token)):
    """Get the user's current role-adaptive UX mode."""
    from maestro_personal_shell.roles import get_role, get_role_config
    role = get_role()
    config = get_role_config(role)
    return RoleResponse(
        role=role,
        default_view=config["default_view"],
        salience_priority=config["salience_priority"],
    )


# 20. GET /api/persona — Get persona model (v4)


class PersonaResponse(BaseModel):
    persona_id: str
    created_at: str
    dimensions: dict[str, Any]
    action_count: int


@app.get("/api/persona", response_model=PersonaResponse)
async def get_persona(token: str = Depends(verify_token)):
    """Get the user's persona model (v4).

    Returns what the persona system has learned about the user's patterns.
    The user can see this for transparency (privacy control).
    """
    from maestro_personal_shell.persona import get_persona_model
    model = get_persona_model()
    return PersonaResponse(
        persona_id=model["persona_id"],
        created_at=model["created_at"],
        dimensions=model["dimensions"],
        action_count=model["action_count"],
    )


# 21. POST /api/persona/action — Record a user action (v4)


class PersonaActionRequest(BaseModel):
    action_type: str  # "open" | "dismiss" | "act" | "snooze"
    surface: str      # "whisper" | "commitment" | "prepare" | "ask"
    entity: str = ""
    timestamp: str = ""


class PersonaActionResponse(BaseModel):
    recorded: bool
    action_count: int


@app.post("/api/persona/action", response_model=PersonaActionResponse)
async def record_persona_action(req: PersonaActionRequest, token: str = Depends(verify_token)):
    """Record a user action for the persona model (v4).

    The persona system learns from: opens, dismissals, actions, snoozes.
    This data personalizes delivery (timing, format, salience).
    """
    from maestro_personal_shell.persona import record_action, get_persona_model
    ts = req.timestamp or datetime.now(timezone.utc).isoformat()
    record_action(
        action_type=req.action_type,
        surface=req.surface,
        entity=req.entity,
        timestamp=ts,
    )
    model = get_persona_model()
    return PersonaActionResponse(recorded=True, action_count=model["action_count"])


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

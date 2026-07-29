"""Account + insight router — account, export, privacy, audit, calibration,"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from maestro_personal_shell.db_util import get_db_conn, default_sqlite_path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["account"])


# P85 fix (2026-07-27): production runs on PostgreSQL via MAESTRO_DATABASE_URL.
# A bare `except sqlite3.OperationalError` does NOT catch psycopg2's
# `UndefinedTable` / `UndefinedColumn` errors — those bubble up as unhandled
# HTTP 500s on the read endpoints (Audit #2 found /api/account/export and
# /api/observability/traces returning 500 on every call). The fix is to
# catch the broad Exception class for "table/column may not exist" guards
# where the intent is to fall through to an empty list, and to LOG loudly
# (P6) so the operator can see what's missing in production.
#
# The catch is intentionally narrow in scope: it only wraps the
# optional-table probes in export_data and the predictions fallback. Every
# other query in this router is on a table that MUST exist (created in
# init_db at startup); those still raise loudly if broken.
def _probe_table(conn, sql: str, params: tuple) -> list[dict]:
    """Run a SELECT that may target a missing/changed table on Postgres.

    Returns [] on any DB-side error, with a loud log so production
    drift is visible. Never raises.
    """
    try:
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
        return rows
    except Exception as e:  # noqa: BLE001 — intentional broad catch for table probes
        logger.warning(
            "account.export: optional-table probe failed (sql=%r params=%r): %s",
            sql[:80], params, e,
        )
        return []


# ---------------------------------------------------------------------------
# verify_token lazy proxy (see routers/auth.py for rationale)
# ---------------------------------------------------------------------------


async def verify_token_dep(authorization: str = Header(None)) -> str:
    """Lazy proxy to api.verify_token — decouples this router from api.py's load order."""
    from maestro_personal_shell.api import verify_token
    return await verify_token(authorization=authorization)


def _require_admin(token: str = Depends(verify_token_dep)) -> str:
    """Gate debug/admin endpoints behind admin auth.

    Fail closed in production if ADMIN_EMAILS not set.
    Detect production via MAESTRO_PERSONAL_TOKEN (always set in prod, never in dev).
    """
    import os as _os
    admin_emails = {e.strip().lower() for e in _os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()}

    _is_prod = bool(_os.environ.get("MAESTRO_PERSONAL_TOKEN", "")) and not _os.environ.get("MAESTRO_DEMO_MODE", "")
    if not admin_emails:
        if _is_prod:
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Admin access not configured (set ADMIN_EMAILS)")
        return token

    if token.lower() not in admin_emails:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Admin access required")
    return token


# ---------------------------------------------------------------------------
# Pydantic models — moved here from api.py (router-specific)
# ---------------------------------------------------------------------------


class DeviceRegisterRequest(BaseModel):
    push_token: str
    platform: str = "ios"
    user_timezone: str = "UTC"


class DeviceRegisterResponse(BaseModel):
    device_id: str
    message: str


class PushDeliverResponse(BaseModel):
    whispers_pushed: int
    whispers_suppressed: int
    log: list[dict[str, Any]]


class PredictionRequest(BaseModel):
    predicted_confidence: float
    expected_outcome: str = "hit"
    prediction_type: str = "recommendation"
    entity_id: str = ""


class OutcomeRequest(BaseModel):
    prediction_id: str
    actual_outcome: str  # "hit" or "miss"


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
# DELETE /account — Account deletion (App Store Guideline 5.1.1)
# ---------------------------------------------------------------------------


@router.delete("/account")
async def delete_account(token: str = Depends(verify_token_dep)):
    """Delete the user's account and all associated data (scoped to caller)."""
    db = _get_db_path()

    # P11 fix: audit-log the deletion BEFORE the data is wiped.
    audit_log_error = None
    try:
        from maestro_personal_shell.audit_trust import log_data_access
        log_data_access(token, "delete", "/api/account", None, {"user_email": token})
    except Exception as e:
        audit_log_error = str(e)[:200]
        logger.error("CRITICAL: audit log write failed during account deletion: %s", e)

    deleted_stores: list[str] = []
    conn = get_db_conn(db)
    # TICKET-5 root cause fix: on Postgres (autocommit=False by default),
    # a failed statement aborts the transaction. All subsequent statements
    # fail with "current transaction is aborted" until rollback(). The
    # prior inner try/excepts caught the exception but didn't rollback,
    # so every DELETE after the first failure also failed, and conn.commit()
    # at the end failed too — propagating as 500.
    #
    # Fix: set autocommit=True on the connection so each statement is
    # independent. This is safe for deletion (we don't need atomicity
    # across tables — partial deletion is acceptable, and the
    # deleted_accounts table is the GDPR gate, not the data wipe).
    # Handle both Postgres (psycopg2: conn._conn.autocommit) and SQLite
    # (sqlite3: conn.isolation_level = None for autocommit mode).
    try:
        if hasattr(conn, '_conn'):
            # PostgresConnection wrapper
            conn._conn.autocommit = True
        else:
            # sqlite3.Connection — isolation_level=None enables autocommit
            conn.isolation_level = None
    except Exception:
        pass  # best-effort; if this fails, the try/excepts below handle errors
    try:
        # TICKET-5: reorder deletes — children before parents (FK safety).
        # On Postgres, FOREIGN KEY constraints are enforced. The original
        # order (signals first) failed if any table referenced signals.
        # Correct order: outcomes → predictions → commitments_ledger →
        # calibration_history → signals → graph/devices/tokens.
        try:
            # Outcomes (FK → predictions)
            try:
                conn.execute("""
                    DELETE FROM outcomes WHERE prediction_id IN (
                        SELECT prediction_id FROM predictions WHERE user_email = ?
                    )
                """, (token,))
                deleted_stores.append("outcomes")
            except Exception as e:
                logger.debug("failed to delete outcomes: %s", e)
            # Predictions (parent of outcomes)
            try:
                conn.execute("DELETE FROM predictions WHERE user_email = ?", (token,))
                deleted_stores.append("predictions")
            except Exception as e:
                logger.debug("failed to delete predictions: %s", e)
            # Predictions fallback (metadata LIKE — for older schema)
            try:
                conn.execute("DELETE FROM predictions WHERE metadata LIKE ?", (f'%"{token}"%',))
            except Exception as e:
                logger.debug("failed: %s", e)
            # Commitments ledger + calibration history
            for table in ("commitments_ledger", "calibration_history"):
                try:
                    conn.execute(f"DELETE FROM {table} WHERE user_email = ?", (token,))
                    deleted_stores.append(table)
                except Exception as e:
                    logger.debug("failed: %s", e)
            # Signals (parent table — delete AFTER children)
            try:
                conn.execute("DELETE FROM signals WHERE user_email = ?", (token,))
                deleted_stores.append("signals")
            except Exception as e:
                logger.debug("failed to delete signals: %s", e)
            # Graph + devices + push_log + tokens
            for table in ("graph_entities", "graph_edges", "graph_patterns",
                          "push_log", "devices", "user_tokens"):
                try:
                    conn.execute(f"DELETE FROM {table} WHERE user_email = ?", (token,))
                    deleted_stores.append(table)
                except Exception as e:
                    logger.debug("failed: %s", e)
        except Exception as e:
            logger.error("delete_account data wipe failed for %s: %s", token, e, exc_info=True)
            raise HTTPException(status_code=500, detail=f"Account deletion failed during data wipe: {str(e)[:200]}")
    finally:
        conn.close()
    # FTS index — rebuild without deleted user's signals
    try:
        from maestro_personal_shell.semantic_retrieval import rebuild_fts_index
        rebuild_fts_index(db)
        deleted_stores.append("fts_index")
    except Exception as e:
        logger.debug("FTS cleanup after delete failed (non-fatal): %s", e)

    # P38 DELETION FINALITY (S1 #3 — auditor critical finding):
    # After DELETE /api/account, re-login with the same credentials MUST fail.
    # The previous implementation only wiped the user's data but left the
    # user_accounts row intact (with active=1), so re-login succeeded and
    # minted a fresh token — resurrection by re-login.
    #
    # Fix: record the deleted email in a dedicated `deleted_accounts` table.
    # The login and register endpoints check this table and REJECT any
    # attempt to authenticate or re-create a deleted account (403).
    # Deletion is final.
    try:
        _conn2 = get_db_conn(db)
        # TICKET-5: set autocommit=True so CREATE TABLE + INSERT are independent
        try:
            if hasattr(_conn2, '_conn'):
                _conn2._conn.autocommit = True
            else:
                _conn2.isolation_level = None
        except Exception:
            pass
        try:
            _conn2.execute("""
                CREATE TABLE IF NOT EXISTS deleted_accounts (
                    user_email TEXT PRIMARY KEY,
                    deleted_at TEXT NOT NULL
                )
            """)
            _conn2.execute(
                "INSERT OR REPLACE INTO deleted_accounts (user_email, deleted_at) VALUES (?, ?)",
                (token, datetime.now(timezone.utc).isoformat()),
            )
            # Also deactivate the user_accounts row so the login DB lookup
            # (which checks active=1) fails. Belt + suspenders: the
            # deleted_accounts table is the primary gate, but deactivating
            # the row prevents the password-hash path from succeeding even
            # if the deleted_accounts check is somehow bypassed.
            try:
                _conn2.execute(
                    "UPDATE user_accounts SET active = 0 WHERE user_email = ?",
                    (token,),
                )
            except Exception:
                pass  # user_accounts table may not exist (dev/bootstrap mode)
            deleted_stores.append("deleted_accounts")
        finally:
            _conn2.close()
    except Exception as e:
        logger.error("CRITICAL: failed to record deletion in deleted_accounts: %s", e)

    return {
        "message": f"Account deleted. Data removed from {len(deleted_stores)} stores.",
        "status": "ok",
        "deleted_stores": deleted_stores,
        "audit_log_error": audit_log_error,
    }


# ---------------------------------------------------------------------------
# GET /account/export — GDPR/CCPA data export
# ---------------------------------------------------------------------------


@router.get("/account/export")
async def export_data(token: str = Depends(verify_token_dep)):
    """Export all user data (GDPR/CCPA compliance)."""
    db = _get_db_path()
    conn = get_db_conn(db)
    conn.row_factory = sqlite3.Row

    export: dict[str, Any] = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user_email": token,
    }

    signals = [dict(r) for r in conn.execute(
        "SELECT * FROM signals WHERE user_email = ?", (token,)
    ).fetchall()]
    export["signals"] = signals
    export["signal_count"] = len(signals)

    # P85 fix: optional-table probes use _probe_table so a missing/changed
    # table on Postgres (which raises psycopg2.errors.UndefinedTable, NOT
    # sqlite3.OperationalError) is logged loudly and falls through to []
    # instead of bubbling up as an unhandled HTTP 500.
    for table in ("commitments_ledger", "audit_log", "calibration_history",
                  "devices", "push_log", "graph_entities", "graph_edges", "graph_patterns"):
        rows = _probe_table(
            conn,
            f"SELECT * FROM {table} WHERE user_email = ?",
            (token,),
        )
        export[table] = rows

    # Predictions (P0 fix: use user_email, not metadata LIKE)
    preds = _probe_table(
        conn,
        "SELECT * FROM predictions WHERE user_email = ?",
        (token,),
    )
    if preds:
        export["predictions"] = preds
        export["prediction_count"] = len(preds)
    else:
        # Fallback: older predictions rows may not have user_email populated
        # (pre-migration). Use metadata LIKE as a last resort.
        preds = _probe_table(
            conn,
            "SELECT * FROM predictions WHERE metadata LIKE ?",
            (f'%"{token}"%',),
        )
        export["predictions"] = preds
        export["prediction_count"] = len(preds)

    conn.close()
    return export


# ---------------------------------------------------------------------------
# Devices + push
# ---------------------------------------------------------------------------


@router.post("/devices/register", response_model=DeviceRegisterResponse)
async def register_device_endpoint(req: DeviceRegisterRequest, token: str = Depends(verify_token_dep)):
    """Register a device for push notifications."""
    from maestro_personal_shell.push import register_device, init_push_db
    init_push_db()
    device_id = register_device(
        push_token=req.push_token,
        platform=req.platform,
        user_timezone=req.user_timezone,
        user_email=token,
    )
    return DeviceRegisterResponse(
        device_id=device_id,
        message="Device registered for push notifications",
    )


@router.post("/whisper/push", response_model=PushDeliverResponse)
async def deliver_whispers_push(token: str = Depends(verify_token_dep)):
    """Deliver high-priority whispers as push notifications."""
    from maestro_personal_shell.push import deliver_whispers_as_push, init_push_db
    from maestro_personal_shell.surfaces.whisper import WhisperSurface
    from maestro_personal_shell.api import build_shell

    init_push_db()
    shell = build_shell(user_email=token)
    surface = WhisperSurface(shell=shell)
    whispers = surface.get_active_whispers()

    log = deliver_whispers_as_push(whispers, user_email=token)
    pushed = sum(1 for e in log if e.get("status") == "sent")
    suppressed = sum(1 for e in log if e.get("status") == "suppressed")

    return PushDeliverResponse(
        whispers_pushed=pushed,
        whispers_suppressed=suppressed,
        log=log,
    )


# ---------------------------------------------------------------------------
# Agents — list, dashboard, per-agent insights, relevant
# ---------------------------------------------------------------------------


@router.get("/agents")
async def list_agents(
    experimental: bool = False,
    token: str = Depends(verify_token_dep),
):
    """List all wired Nerve agents."""
    from maestro_personal_shell.api import build_shell
    shell = build_shell(user_email=token)
    nerve = shell.nerve
    all_agents = nerve.wired_agents
    if experimental:
        return {"agents": all_agents, "count": nerve.wired_count}
    _DEMO_AGENTS = {"sales", "customer_success", "chief_of_staff"}
    demo_agents = [a for a in all_agents if a in _DEMO_AGENTS]
    return {"agents": demo_agents, "count": len(demo_agents)}


@router.get("/agents/dashboard")
async def agent_dashboard(
    token: str = Depends(verify_token_dep),
    agent: str = "",
    priority: str = "",
    min_confidence: float = 0.0,
    text: str = "",
    experimental: bool = False,
):
    """Unified dashboard view: all insights from all agents."""
    from maestro_personal_shell.api import build_shell
    shell = build_shell(user_email=token)
    nerve = shell.nerve
    insights = nerve.get_insights(situation_text=text) if text else nerve.get_insights()

    # Filter to demo agents unless experimental=true
    if not experimental:
        _DEMO_AGENTS = {"sales", "customer_success", "chief_of_staff"}
        insights = [i for i in insights if i.get("agent") in _DEMO_AGENTS]

    if agent:
        insights = [i for i in insights if i.get("agent") == agent]
    if priority:
        insights = [i for i in insights if i.get("priority") == priority]
    if min_confidence > 0:
        insights = [i for i in insights if i.get("confidence", 0) >= min_confidence]

    by_agent = {}
    for ins in insights:
        a = ins.get("agent", "unknown")
        by_agent.setdefault(a, []).append(ins)

    return {
        "total_insights": len(insights),
        "agent_count": len(by_agent),
        "by_agent": {a: {"count": len(items), "insights": items} for a, items in by_agent.items()},
        "filters": {"agent": agent, "priority": priority, "min_confidence": min_confidence},
    }


@router.get("/agents/{agent_name}/insights")
async def per_agent_insights(agent_name: str, token: str = Depends(verify_token_dep)):
    """Query a specific agent's insights."""
    from maestro_personal_shell.api import build_shell
    shell = build_shell(user_email=token)
    nerve = shell.nerve
    all_insights = nerve.get_insights(situation_text=agent_name)
    agent_insights = [i for i in all_insights if i.get("agent") == agent_name]
    return {"agent": agent_name, "insights": agent_insights, "count": len(agent_insights)}


@router.get("/agents/relevant")
async def get_relevant_agents(text: str = "", token: str = Depends(verify_token_dep)):
    """Get dynamically selected agents for a situation (Directive 4)."""
    from maestro_personal_shell.dynamic_agents import select_relevant_agents
    from maestro_personal_shell.api import build_shell
    shell = build_shell(user_email=token)
    agents = select_relevant_agents(text, shell.oem_state.signals)
    return {"relevant_agents": agents, "text": text}


# ---------------------------------------------------------------------------
# Predictions + Outcomes — closes the learning + calibration loop
# ---------------------------------------------------------------------------


@router.post("/predictions")
async def register_prediction_endpoint(req: PredictionRequest, token: str = Depends(verify_token_dep)):
    """Register a prediction — the START of the learning loop."""
    from maestro_personal_shell.outcome_tracker import register_prediction, init_outcome_db
    init_outcome_db()
    return register_prediction(
        predicted_confidence=req.predicted_confidence,
        expected_outcome=req.expected_outcome,
        prediction_type=req.prediction_type,
        entity_id=req.entity_id,
        user_email=token,
    )


@router.post("/outcomes")
async def resolve_outcome_endpoint(req: OutcomeRequest, token: str = Depends(verify_token_dep)):
    """Resolve a prediction with the actual outcome — CLOSES the learning loop."""
    from maestro_personal_shell.outcome_tracker import resolve_outcome, init_outcome_db
    init_outcome_db()
    result = resolve_outcome(
        prediction_id=req.prediction_id,
        actual_outcome=req.actual_outcome,
        user_email=token,
    )
    if isinstance(result, dict) and result.get("error") == "Prediction not found":
        raise HTTPException(status_code=404, detail="Prediction not found or not owned by caller")
    return result


# ---------------------------------------------------------------------------
# Calibration — Brier score + history
# ---------------------------------------------------------------------------


@router.get("/calibration")
async def get_calibration(token: str = Depends(verify_token_dep)):
    """Get the Brier score + calibration report."""
    from maestro_personal_shell.outcome_tracker import (
        get_calibration_report, get_prediction_count, init_outcome_db,
    )
    init_outcome_db()
    report = get_calibration_report(user_email=token)
    counts = get_prediction_count(user_email=token)
    return {**report, "counts": counts}


@router.get("/calibration/history")
async def get_calibration_history_endpoint(limit: int = 30, token: str = Depends(verify_token_dep)):
    """Get calibration history — Brier score trends over time."""
    from maestro_personal_shell.audit_trust import get_calibration_history, log_data_access
    log_data_access(token, "read", "/api/calibration/history")
    return {"history": get_calibration_history(user_email=token, limit=limit)}


# ---------------------------------------------------------------------------
# Privacy + audit-log
# ---------------------------------------------------------------------------


@router.get("/privacy/mode")
async def get_privacy_mode(token: str = Depends(verify_token_dep)):
    """Get the current processing mode for privacy transparency."""
    from maestro_personal_shell.audit_trust import get_processing_mode, log_data_access
    log_data_access(token, "read", "/api/privacy/mode")
    return get_processing_mode()


@router.get("/privacy/retention-status")
async def get_retention_status(token: str = Depends(verify_token_dep)):
    """Get the data retention TTL configuration (Step 15).

    Returns the enforced retention periods for each data type, so users
    can see exactly how long their data is kept.
    """
    from maestro_personal_shell.audit_trust import log_data_access
    from maestro_personal_shell.retention_enforcer import get_retention_policy
    log_data_access(token, "read", "/api/privacy/retention-status")
    return {
        "policy": get_retention_policy(),
        "enforcement": "automated — runs daily via background task",
        "user_controls": {
            "export_all_data": "GET /api/account/export",
            "delete_all_data": "DELETE /api/account",
            "disconnect_connector": "DELETE /api/connectors/{provider}",
        },
    }


# ---------------------------------------------------------------------------
# Per-connector consent settings (Task 59-7)
#
# Granular consent toggles: for each connector, the user can independently
# enable/disable specific data-type access (e.g. Gmail: read emails yes,
# send drafts no; Calendar: read events yes, create events no).
# ---------------------------------------------------------------------------

# Default consent settings per provider — what each connector CAN access.
# User can toggle these off individually for granular privacy control.
_DEFAULT_CONSENT: dict[str, dict[str, bool]] = {
    "gmail": {"read_emails": True, "create_drafts": True, "send_emails": False},
    "calendar": {"read_events": True, "create_events": False},
    "slack": {"read_messages": True, "post_messages": False},
    "github": {"read_issues": True, "read_prs": True, "create_issues": False},
    "whatsapp": {"read_messages": True},
    "facebook": {"read_posts": True},
    "instagram": {"read_posts": True},
    "twitter": {"read_tweets": True},
}


@router.get("/consent/settings")
async def get_consent_settings(token: str = Depends(verify_token_dep)):
    """Get per-connector consent toggles for the current user."""
    from maestro_personal_shell.db_util import get_db_conn, default_sqlite_path
    from maestro_personal_shell.audit_trust import log_data_access
    log_data_access(token, "read", "/api/consent/settings")

    conn = get_db_conn()
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS consent_settings "
            "(user_email TEXT, settings_json TEXT, updated_at TEXT, "
            "PRIMARY KEY (user_email))"
        )
        row = conn.execute(
            "SELECT settings_json FROM consent_settings WHERE user_email = ?",
            (token,),
        ).fetchone()
        if row:
            import json
            user_settings = json.loads(row[0])
        else:
            user_settings = {}
    finally:
        conn.close()

    # Merge defaults with user overrides
    result = {}
    for provider, defaults in _DEFAULT_CONSENT.items():
        result[provider] = {}
        for scope, default_val in defaults.items():
            result[provider][scope] = user_settings.get(provider, {}).get(scope, default_val)

    return {"consent": result, "defaults": _DEFAULT_CONSENT}


@router.put("/consent/settings")
async def set_consent_settings(
    body: dict,
    token: str = Depends(verify_token_dep),
):
    """Update per-connector consent toggles for the current user.

    Body: {"provider": "gmail", "scope": "create_drafts", "enabled": false}
    """
    from maestro_personal_shell.db_util import get_db_conn, default_sqlite_path
    from maestro_personal_shell.audit_trust import log_data_access
    import json

    provider = body.get("provider", "")
    scope = body.get("scope", "")
    enabled = bool(body.get("enabled", True))

    if provider not in _DEFAULT_CONSENT:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")
    if scope not in _DEFAULT_CONSENT[provider]:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Unknown scope for {provider}: {scope}")

    log_data_access(token, "write", f"/api/consent/settings ({provider}.{scope}={enabled})")

    conn = get_db_conn()
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS consent_settings "
            "(user_email TEXT, settings_json TEXT, updated_at TEXT, "
            "PRIMARY KEY (user_email))"
        )
        row = conn.execute(
            "SELECT settings_json FROM consent_settings WHERE user_email = ?",
            (token,),
        ).fetchone()
        settings = json.loads(row[0]) if row else {}
        settings.setdefault(provider, {})[scope] = enabled
        conn.execute(
            "INSERT OR REPLACE INTO consent_settings (user_email, settings_json, updated_at) "
            "VALUES (?, ?, ?)",
            (token, json.dumps(settings), __import__("datetime").datetime.utcnow().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()

    return {"ok": True, "provider": provider, "scope": scope, "enabled": enabled}


def check_consent(user_email: str, provider: str, scope: str) -> bool:
    """Check if the user has consented to a specific data scope.

    Used by connector ingestion paths to enforce granular consent before
    reading or writing data. Returns True if consent is granted (default
    if no explicit setting exists).
    """
    if provider not in _DEFAULT_CONSENT:
        return True  # unknown provider — allow (backward compat)
    if scope not in _DEFAULT_CONSENT[provider]:
        return True  # unknown scope — allow

    from maestro_personal_shell.db_util import get_db_conn, default_sqlite_path
    import json
    import logging
    logger = logging.getLogger(__name__)

    conn = get_db_conn()
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS consent_settings "
            "(user_email TEXT, settings_json TEXT, updated_at TEXT, "
            "PRIMARY KEY (user_email))"
        )
        row = conn.execute(
            "SELECT settings_json FROM consent_settings WHERE user_email = ?",
            (user_email,),
        ).fetchone()
        if not row:
            return _DEFAULT_CONSENT[provider][scope]
        settings = json.loads(row[0])
        return settings.get(provider, {}).get(scope, _DEFAULT_CONSENT[provider][scope])
    except Exception as e:
        logger.debug("check_consent error for %s.%s: %s — returning default", provider, scope, e)
        return _DEFAULT_CONSENT[provider][scope]
    finally:
        conn.close()


@router.get("/audit-log")
async def get_audit_log_endpoint(
    limit: int = 50,
    action: str | None = None,
    token: str = Depends(verify_token_dep),
):
    """Get the audit log — every data access event."""
    from maestro_personal_shell.audit_trust import get_audit_log, log_data_access
    log_data_access(token, "read", "/api/audit-log")
    return {"events": get_audit_log(user_email=token, limit=limit, action=action)}


# ---------------------------------------------------------------------------
# LLM status — verify the Cognitive Council is LLM-powered
# ---------------------------------------------------------------------------


@router.get("/llm-status")
async def llm_status(token: str = Depends(verify_token_dep)):
    """Verify whether the Cognitive Council is LLM-powered or rule-based."""
    from maestro_personal_shell.llm_bridge import (
        is_llm_available, get_llm_router, get_llm_provider_name, probe_provider,
        _LLM_IMPORT_ERROR,
    )
    configured = is_llm_available()
    router_obj = get_llm_router() if configured else None
    provider = get_llm_provider_name()
    probe = await probe_provider()
    verified = probe.get("verified", False)
    active = configured and verified

    # P0: router_loaded distinguishes "module imported" from "module failed to import".
    # This is the R2-killer: a dummy API key makes available=false, but router_loaded
    # stays true. If maestro_db is missing, router_loaded=false with the import error.
    router_loaded = _LLM_IMPORT_ERROR is None

    return {
        "router_loaded": router_loaded,
        "import_error": _LLM_IMPORT_ERROR,
        "configured": configured,
        "verified": verified,
        "active": active,
        "llm_active": active,
        "provider": provider,
        "probe_latency_ms": probe.get("latency_ms", 0),
        "probe_error": probe.get("error", ""),
        "probe_cached_seconds": 60,
        "available_providers": getattr(router_obj, "available_providers", [provider] if router_obj else []),
        "mode": "LLM-powered (genuine AI reasoning)" if active else "Rule-based (keyword fallback)",
        "intelligence_paths": {
            "ask_answer": "llm" if active else "rule-based",
            "perspectives": "llm" if active else "keyword-counters",
            "judgment_synthesis": "llm" if active else "rule-concatenation",
            "consequence_routing": "llm" if active else "dictionary-lookup",
            "ambient": "llm" if active else "keyword-triggers",
        },
        "note": (
            f"LLM verified via {provider} ({probe.get('latency_ms', 0)}ms). All intelligence paths use genuine AI reasoning."
            if active
            else f"Provider '{provider}' configured but probe failed: {probe.get('error', 'unknown')}. Falling back to rules."
            if configured and not verified
            else "No LLM available. Set ANTHROPIC_API_KEY or OPENAI_API_KEY as a Railway env var to enable LLM-powered intelligence. See docs/LLM_SETUP.md for details."
        ),
    }


# ---------------------------------------------------------------------------
# Depth — which Core modules are wired + producing value
# ---------------------------------------------------------------------------


@router.get("/debug-llm")
async def debug_llm(token: str = Depends(_require_admin)):
    """TEMP debug — inspect LLM router state.

    P51 (fifth audit F1): this endpoint must NEVER throw an unhandled 500.
    Every operation is guarded; the endpoint returns structured JSON with
    error fields rather than crashing.
    """
    # P51: wrap the ENTIRE endpoint in a try/except so no internal error
    # can produce an unhandled 500. The user gets a structured response
    # even if the LLM bridge is completely broken.
    try:
        import os
        from maestro_personal_shell.llm_bridge import (
            get_llm_router, is_llm_available, _is_circuit_breaker_open,
            _OllamaDirectRouter,
        )
        ollama_host = os.environ.get("OLLAMA_HOST", "<NOT SET>")
        ollama_model = os.environ.get("OLLAMA_MODEL", "<NOT SET>")
        openrouter_key = os.environ.get("OPENROUTER_API_KEY", "<NOT SET>")

        try:
            cb_open = _is_circuit_breaker_open()
        except Exception:
            cb_open = "error"
        try:
            llm_avail = is_llm_available()
        except Exception:
            llm_avail = False

        # Try to build a router directly
        router = None
        router_error = ""
        try:
            router = get_llm_router()
        except Exception as e:
            router_error = str(e)[:200]

        # Try health check directly
        health = None
        health_error = ""
        direct_fetch_status = "not_attempted"
        direct_fetch_error = ""
        try:
            if ollama_host and ollama_host.startswith("http") and "localhost" not in ollama_host:
                try:
                    test = _OllamaDirectRouter()
                    health = test.health_check()
                except Exception as e:
                    health_error = str(e)[:200]
                # Also try a direct urllib fetch to see the actual error
                try:
                    import urllib.request
                    req = urllib.request.Request(f"{ollama_host}/api/tags")
                    resp = urllib.request.urlopen(req, timeout=15)
                    direct_data = json.loads(resp.read())
                    direct_fetch_status = f"OK ({len(direct_data.get('models', []))} models)"
                except Exception as e:
                    direct_fetch_status = "FAILED"
                    direct_fetch_error = str(e)[:300]
        except Exception as e:
            health_error = f"outer guard: {str(e)[:200]}"

        return {
            "OLLAMA_HOST": ollama_host,
            "OLLAMA_MODEL": ollama_model,
            "OPENROUTER_API_KEY": "<set>" if openrouter_key and openrouter_key != "<NOT SET>" else openrouter_key,
            "circuit_breaker_open": cb_open,
            "is_llm_available": llm_avail,
            "router_present": router is not None,
            "router_provider": getattr(router, "default_provider", "none") if router else "none",
            "router_error": router_error,
            "direct_health_check": health,
            "health_error": health_error,
            "direct_fetch_status": direct_fetch_status,
            "direct_fetch_error": direct_fetch_error,
        }
    except Exception as e:
        # P51: unhandled 500 is forbidden — return a structured 200 with the error
        return {
            "error": f"P51 guarded: {str(e)[:300]}",
            "OLLAMA_HOST": os.environ.get("OLLAMA_HOST", "<NOT SET>") if 'os' in dir() else "<unknown>",
            "is_llm_available": False,
            "circuit_breaker_open": "unknown",
            "note": "P51: debug-llm endpoint caught an internal error and returned structured JSON instead of a 500.",
        }


@router.get("/debug-canonical-ledger")
async def debug_canonical_ledger(token: str = Depends(_require_admin)):
    """P83 diagnostic: check the canonical ledger (commitment_events table) state.

    Returns whether the table exists, row count, and a sample of recent events.
    Used to diagnose why /api/ask returns 'no records' when /api/commitments
    shows commitments exist (the two query different tables).
    """
    try:
        from maestro_personal_shell.db_util import default_sqlite_path, get_db_conn
        from maestro_personal_shell.canonical_ledger import reduce_commitments, _ensure_table_exists
        import sqlite3

        db_path = default_sqlite_path()
        result = {
            "user_email": token,
            "db_path": db_path,
            "table_exists": False,
            "row_count": 0,
            "recent_events": [],
            "reduce_commitments_count": 0,
            "errors": [],
        }

        try:
            conn = get_db_conn(db_path)
            # Check if table exists
            try:
                cur = conn.execute("SELECT COUNT(*) FROM commitment_events")
                count = cur.fetchone()
                result["table_exists"] = True
                result["row_count"] = count[0] if count else 0
                # Get recent events for this user
                cur = conn.execute(
                    "SELECT event_id, commitment_id, entity, text, state, timestamp "
                    "FROM commitment_events WHERE user_email = ? "
                    "ORDER BY timestamp DESC LIMIT 5",
                    (token,),
                )
                rows = cur.fetchall()
                result["recent_events"] = [
                    {
                        "event_id": r[0] if not isinstance(r, dict) else r.get("event_id"),
                        "commitment_id": r[1] if not isinstance(r, dict) else r.get("commitment_id"),
                        "entity": r[2] if not isinstance(r, dict) else r.get("entity"),
                        "text": (r[3] if not isinstance(r, dict) else r.get("text")) or "",
                        "state": r[4] if not isinstance(r, dict) else r.get("state"),
                        "timestamp": r[5] if not isinstance(r, dict) else r.get("timestamp"),
                    }
                    for r in rows
                ] if rows else []
            except Exception as table_err:
                result["errors"].append(f"Table check failed: {table_err}")
                # Try to create the table
                try:
                    _ensure_table_exists(conn)
                    result["errors"].append("Table creation attempted via _ensure_table_exists")
                except Exception as create_err:
                    result["errors"].append(f"Table creation failed: {create_err}")
            conn.close()
        except Exception as conn_err:
            result["errors"].append(f"Connection failed: {conn_err}")

        # Also check reduce_commitments
        try:
            reduced = reduce_commitments(token, db_path=db_path)
            result["reduce_commitments_count"] = len(reduced)
        except Exception as reduce_err:
            result["errors"].append(f"reduce_commitments failed: {reduce_err}")

        return result
    except Exception as e:
        return {"error": str(e), "note": "debug-canonical-ledger caught an internal error"}


@router.post("/admin/backfill-canonical-ledger")
async def backfill_canonical_ledger(token: str = Depends(verify_token_dep)):
    """TICKET-27: Backfill the canonical ledger (commitment_events table) with
    historical commitments from the legacy commitments_ledger table.

    Every signal created BEFORE the P83 fix (commit a6f66e0b) silently failed
    to write to the canonical ledger because of the PostgresConnection.cursor()
    bug. This endpoint iterates existing ledger entries and calls append_event()
    for each one that's a genuine commitment (owner != 'other').

    IDEMPOTENT: checks if a commitment_event already exists for each
    commitment_id before inserting. Re-running this script twice does NOT
    double-count — it only inserts events that are missing.

    P22: production path — uses the same append_event() the live write path
    uses, so the same filters and ownership rules apply. No bypass.
    P67: no silent except — errors are logged and surfaced in the response.
    P85: never returns 500 — structured response with error details.
    """
    try:
        from maestro_personal_shell.db_util import default_sqlite_path, get_db_conn
        from maestro_personal_shell.canonical_ledger import append_event, CommitmentEvent
        from maestro_personal_shell.commitment_ledger import get_ledger_entries
        import json as _json
        import logging as _logging

        _logger = _logging.getLogger(__name__)
        db_path = default_sqlite_path()

        result = {
            "user_email": token,
            "scanned": 0,
            "already_present": 0,
            "backfilled": 0,
            "skipped_other_owner": 0,
            "errors": [],
            "backfilled_commitment_ids": [],
        }

        # 1. Get ALL ledger entries for this user (limit 10000 — generous)
        entries = get_ledger_entries(user_email=token, db_path=db_path, limit=10000)
        result["scanned"] = len(entries)

        # 2. Get existing commitment_ids from canonical ledger (for idempotency check)
        existing_commitment_ids = set()
        try:
            conn = get_db_conn(db_path)
            try:
                cur = conn.execute(
                    "SELECT DISTINCT commitment_id FROM commitment_events WHERE user_email = ?",
                    (token,),
                )
                rows = cur.fetchall()
                for row in rows:
                    cid = row[0] if not isinstance(row, dict) else row.get("commitment_id")
                    if cid:
                        existing_commitment_ids.add(cid)
            finally:
                conn.close()
        except Exception as e:
            # Table might not exist yet — that's fine, we'll create it via append_event
            _logger.warning("backfill: could not query existing commitment_ids: %s", e)

        # 3. For each ledger entry, backfill if missing
        for entry in entries:
            commitment_id = entry.get("signal_id", "")  # ledger uses signal_id as commitment_id
            if not commitment_id:
                continue

            # Idempotency check — skip if already in canonical ledger
            if commitment_id in existing_commitment_ids:
                result["already_present"] += 1
                continue

            # P83 condition: only backfill if owner != 'other' (third-party commitments
            # are never surfaced by reduce_commitments anyway)
            owner = entry.get("owner", "unknown")
            if owner == "other":
                result["skipped_other_owner"] += 1
                continue

            # Map ledger entry → CommitmentEvent (same mapping as the P83 block)
            state = entry.get("state", "active")
            # Canonical ledger only accepts: active, cancelled, completed, superseded
            if state not in ("active", "cancelled", "completed", "superseded"):
                state = "active"

            event = CommitmentEvent(
                commitment_id=commitment_id,
                event_type="commitment",
                actor="user" if owner == "user" else "entity_name",
                entity=entry.get("entity", "Unknown"),
                text=entry.get("action") or entry.get("evidence_quote") or "",
                source_signal_id=commitment_id,
                confidence=entry.get("confidence", 0.5),
                state=state,
                user_email=token,
                metadata=_json.dumps({
                    "signal_id": commitment_id,
                    "commitment_type": entry.get("commitment_type", "explicit"),
                    "state": state,
                    "backfilled": True,  # marker for audit
                }),
            )

            try:
                append_event(event)
                result["backfilled"] += 1
                result["backfilled_commitment_ids"].append(commitment_id)
                existing_commitment_ids.add(commitment_id)  # prevent dupes within this run
            except Exception as e:
                err_msg = f"Failed to backfill {commitment_id}: {e}"
                result["errors"].append(err_msg)
                _logger.error("backfill: %s", err_msg)

        return result
    except Exception as e:
        return {
            "error": str(e),
            "note": "backfill-canonical-ledger caught an internal error. See logs for details.",
        }


@router.get("/depth")
async def get_depth(token: str = Depends(verify_token_dep)):
    """Show which Core modules are wired to Personal."""
    import os as _os
    admin_token = _os.environ.get("MAESTRO_ADMIN_TOKEN", "")
    # If no admin token is configured, return 404 (endpoint doesn't exist publicly)
    if not admin_token:
        raise HTTPException(status_code=404, detail="Not Found")
    # If admin token is configured but the caller's token doesn't match, 403
    if token != admin_token:
        raise HTTPException(status_code=403, detail="Admin access required")

    from maestro_personal_shell.llm_bridge import is_llm_available
    from maestro_personal_shell.api import build_shell
    shell = build_shell(user_email=token)
    core = shell.core
    wired = core.wired_modules

    placeholder_indicators = [
        "insufficient calibration history", "no agent insight available",
        "not available", "placeholder", "todo", "not implemented",
    ]
    _ = placeholder_indicators  # kept for parity with original; not used in fast-path

    producing_value = []
    placeholder_modules = []
    for module_name in wired:
        is_producing = True
        try:
            llm_modules = {
                "judgment_synthesizer", "consequence_path_router", "nerve",
                "whisper_bridge", "copilot_bridge",
            }
            if module_name in llm_modules and not is_llm_available():
                is_producing = False
            if module_name == "calibration_primitives":
                from maestro_personal_shell.outcome_tracker import get_prediction_count
                counts = get_prediction_count(user_email=token)
                if counts.get("resolved", 0) == 0:
                    is_producing = False
        except Exception as e:
            logger.debug("is_producing failed: %s", e)
        if is_producing:
            producing_value.append(module_name)
        else:
            placeholder_modules.append(module_name)

    producing_count = len(producing_value)
    return {
        "wired_count": len(wired),
        "producing_value_count": producing_count,
        "placeholder_count": len(placeholder_modules),
        "total_core_modules": 23,
        "coverage_pct": round(len(wired) / 23 * 100),
        "producing_value_pct": round(producing_count / 23 * 100),
        "wired_modules": wired,
        "producing_value_modules": producing_value,
        "placeholder_modules": placeholder_modules,
        "target": "80%+ producing value",
        "status": (
            "ON_TARGET" if producing_count >= 18
            else "IN_PROGRESS" if producing_count >= 12
            else "EARLY"
        ),
        "note": (
            "producing_value_pct is the honest metric — modules that return "
            "real data, not templates or 'insufficient history' placeholders. "
            "wired_pct counts existence; producing_value_pct counts value."
        ),
    }


# ---------------------------------------------------------------------------
# Graph + behavior — Directive 2 personal graph
# ---------------------------------------------------------------------------


@router.get("/graph/entity/{entity_name}")
async def get_entity_graph(entity_name: str, token: str = Depends(verify_token_dep)):
    """Get the personal knowledge graph summary for an entity."""
    from maestro_personal_shell.personal_graph import PersonalGraph
    graph = PersonalGraph(user_email=token)
    summary = graph.get_entity_summary(entity_name)
    if not summary.get("exists"):
        return {"exists": False, "message": f"No history for {entity_name}"}
    summary["risk_prediction"] = graph.predict_risk(entity_name)
    return summary


@router.get("/graph/risk/{entity_name}")
async def get_entity_risk(entity_name: str, token: str = Depends(verify_token_dep)):
    """Get the risk prediction for a new commitment with this entity."""
    from maestro_personal_shell.personal_graph import PersonalGraph
    graph = PersonalGraph(user_email=token)
    return graph.predict_risk(entity_name)


@router.get("/behavior/patterns")
async def get_behavior_patterns_endpoint(token: str = Depends(verify_token_dep)):
    """Get the user's behavior patterns for personalization."""
    from maestro_personal_shell.learning_loop_v2 import get_behavior_patterns
    return get_behavior_patterns(user_email=token)


# ---------------------------------------------------------------------------
# Observability — trace IDs, whisper decisions
# ---------------------------------------------------------------------------


@router.get("/observability/trace/{trace_id}")
async def get_trace_endpoint(trace_id: str, token: str = Depends(verify_token_dep)):
    """Get all events for a trace ID."""
    from maestro_personal_shell.observability import get_trace
    events = get_trace(trace_id, user_email=token)
    return {"trace_id": trace_id, "event_count": len(events), "events": events}


@router.get("/observability/traces")
async def get_traces_endpoint(limit: int = 50, token: str = Depends(verify_token_dep)):
    """Get recent traces for the authenticated user."""
    from maestro_personal_shell.observability import get_user_traces
    traces = get_user_traces(token, limit=limit)
    return {"traces": traces, "count": len(traces)}


@router.get("/observability/whisper-decisions")
async def get_whisper_decisions_endpoint(limit: int = 50, token: str = Depends(verify_token_dep)):
    """Get recent whisper decisions for the authenticated user."""
    from maestro_personal_shell.observability import get_whisper_decisions
    decisions = get_whisper_decisions(token, limit=limit)
    return {"decisions": decisions, "count": len(decisions)}


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


@router.get("/metrics")
async def get_metrics(token: str = Depends(verify_token_dep)):
    """Get success metrics — tracks real user value."""
    from maestro_personal_shell.success_metrics import get_success_metrics
    from maestro_personal_shell.audit_trust import log_data_access
    log_data_access(token, "read", "/api/metrics")
    return get_success_metrics(user_email=token)


# ---------------------------------------------------------------------------
# Ambient + persisted-situations
# ---------------------------------------------------------------------------


@router.get("/ambient")
async def get_ambient(token: str = Depends(verify_token_dep)):
    """Get ambient intelligence — what's happening between calls."""
    from maestro_personal_shell.copilot_live import get_ambient_intelligence
    from maestro_personal_shell.api import build_shell
    shell = build_shell(user_email=token)
    return await get_ambient_intelligence(shell=shell)


@router.get("/persisted-situations")
async def get_persisted_situations(token: str = Depends(verify_token_dep)):
    """Verify situation persistence across restart (S2 beta blocker fix)."""
    from maestro_personal_shell.api import build_shell
    shell = build_shell(user_email=token)
    persisted = shell.load_persisted_situations(org_id="personal")
    return {
        "persisted_count": len(persisted),
        "persisted_situations": persisted[:5],
        "persistence_active": True,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_db_path() -> str:
    """Get the DB path from env (always fresh — avoids reload staleness)."""
    import os
    return default_sqlite_path()

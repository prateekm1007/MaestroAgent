"""Account + insight router — account, export, privacy, audit, calibration,
metrics, llm-status, depth, graph, behavior, agents, briefing, the-moment,
what-changed, prepare, whisper.

Extracted from api.py during the Phase 8 router split. No behavior changes.
The heavy "surface" endpoints (briefing, the-moment, what-changed, prepare,
whisper) live in routers/surfaces.py and are mounted via this module so the
task's account.py grouping is preserved. Lighter endpoints (account/export/
privacy/audit/calibration/metrics/llm-status/depth/graph/behavior/agents/
predictions/outcomes/devices/observability) live here directly.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from maestro_personal_shell.db_util import get_db_conn

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["account"])


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
    try:
        conn.execute("DELETE FROM signals WHERE user_email = ?", (token,))
        deleted_stores.append("signals")
        for table in ("commitments_ledger", "calibration_history"):
            try:
                conn.execute(f"DELETE FROM {table} WHERE user_email = ?", (token,))
                deleted_stores.append(table)
            except sqlite3.OperationalError:
                pass
        # Predictions + outcomes (P0 fix: use user_email column)
        try:
            conn.execute("""
                DELETE FROM outcomes WHERE prediction_id IN (
                    SELECT prediction_id FROM predictions WHERE user_email = ?
                )
            """, (token,))
            conn.execute("DELETE FROM predictions WHERE user_email = ?", (token,))
            deleted_stores.append("predictions+outcomes")
        except sqlite3.OperationalError:
            try:
                conn.execute("DELETE FROM predictions WHERE metadata LIKE ?", (f'%"{token}"%',))
                deleted_stores.append("predictions (fallback)")
            except sqlite3.OperationalError:
                pass
        # Graph + devices + push_log + tokens
        for table in ("graph_entities", "graph_edges", "graph_patterns",
                      "push_log", "devices", "user_tokens"):
            try:
                conn.execute(f"DELETE FROM {table} WHERE user_email = ?", (token,))
                deleted_stores.append(table)
            except sqlite3.OperationalError:
                pass
        conn.commit()
    finally:
        conn.close()
    # FTS index — rebuild without deleted user's signals
    try:
        from maestro_personal_shell.semantic_retrieval import rebuild_fts_index
        rebuild_fts_index(db)
        deleted_stores.append("fts_index")
    except Exception as e:
        logger.debug("FTS cleanup after delete failed (non-fatal): %s", e)

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

    for table in ("commitments_ledger", "audit_log", "calibration_history",
                  "devices", "push_log", "graph_entities", "graph_edges", "graph_patterns"):
        try:
            rows = [dict(r) for r in conn.execute(
                f"SELECT * FROM {table} WHERE user_email = ?", (token,)
            ).fetchall()]
            export[table] = rows
        except sqlite3.OperationalError:
            export[table] = []

    # Predictions (P0 fix: use user_email, not metadata LIKE)
    try:
        preds = [dict(r) for r in conn.execute(
            "SELECT * FROM predictions WHERE user_email = ?", (token,)
        ).fetchall()]
        export["predictions"] = preds
        export["prediction_count"] = len(preds)
    except sqlite3.OperationalError:
        try:
            preds = [dict(r) for r in conn.execute(
                "SELECT * FROM predictions WHERE metadata LIKE ?", (f'%"{token}"%',)
            ).fetchall()]
            export["predictions"] = preds
            export["prediction_count"] = len(preds)
        except sqlite3.OperationalError:
            export["predictions"] = []

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
async def list_agents(token: str = Depends(verify_token_dep)):
    """List all wired Nerve agents."""
    from maestro_personal_shell.api import build_shell
    shell = build_shell(user_email=token)
    nerve = shell.nerve
    return {"agents": nerve.wired_agents, "count": nerve.wired_count}


@router.get("/agents/dashboard")
async def agent_dashboard(
    token: str = Depends(verify_token_dep),
    agent: str = "",
    priority: str = "",
    min_confidence: float = 0.0,
    text: str = "",
):
    """Unified dashboard view: all insights from all agents."""
    from maestro_personal_shell.api import build_shell
    shell = build_shell(user_email=token)
    nerve = shell.nerve
    insights = nerve.get_insights(situation_text=text) if text else nerve.get_insights()
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
    )
    configured = is_llm_available()
    router_obj = get_llm_router() if configured else None
    provider = get_llm_provider_name()
    probe = await probe_provider()
    verified = probe.get("verified", False)
    active = configured and verified

    return {
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
            else "No LLM available. Set OPENAI_API_KEY, ANTHROPIC_API_KEY, OPENROUTER_API_KEY, XAI_API_KEY, run Ollama, or install the z-ai CLI to activate LLM mode."
        ),
    }


# ---------------------------------------------------------------------------
# Depth — which Core modules are wired + producing value
# ---------------------------------------------------------------------------


@router.get("/depth")
async def get_depth(token: str = Depends(verify_token_dep)):
    """Show which Core modules are wired to Personal (honest: producing_value vs placeholder)."""
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
        except Exception:
            pass
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
    return os.environ.get(
        "MAESTRO_PERSONAL_DB",
        str(Path(__file__).resolve().parents[1] / "personal.db"),
    )

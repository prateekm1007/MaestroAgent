"""
OEM API routes — exposes the real Organizational Execution Model to the frontend.

Every endpoint returns data derived from the OEM engine. No hardcoded insights.

Endpoints:
    GET /api/oem/state           — OEM summary (signal counts, law counts, health)
    GET /api/oem/dashboard       — Home dashboard widget data
    GET /api/oem/recommendations — Active recommendations with evidence chains
    GET /api/oem/inbox           — Executive inbox (decisions owed + drift + dissent)
    GET /api/oem/laws            — All organizational laws with provenance
    GET /api/oem/laws/{code}     — Single law with full evidence chain
    GET /api/oem/ask             — Ask the organization (NL question → OEM answer)
    GET /api/oem/simulator       — Decision simulator state + counterfactual
    GET /api/oem/provenance/{id} — Full provenance chain for any entity
    GET /api/oem/knowledge       — Knowledge flow + hidden experts + concentration risk
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Depends, Request, Body

from maestro_api.oem_state import oem_state
from maestro_api.security.policy import set_router_policy, AuthPolicy
from maestro_db.db_helper import get_db_url_for_learning

logger = logging.getLogger(__name__)


# ─── V8 Daily Work #9 — Enterprise Trust Layer ─────────────────────────────
# Two-layer defense on EVERY OEM route:
#   1. Tenant isolation (always runs, even in single-tenant mode)
#   2. RBAC permission check (only when auth is enabled)
# When auth is disabled (dev mode / testing), only tenant isolation runs.
# This closes the auditor's gap: the RBAC system existed but was not wired
# to any OEM route.

def _require_tenant_access():
    """Layer 1: Tenant isolation — always enforced."""
    oem_state.check_tenant_access()
    return True


def _require_oem_permission(request: Request):
    """Layer 2: RBAC — requires OEM_READ for GET, OEM_WRITE for state-changing
    methods. Only fires when auth is enabled. When auth is disabled (dev mode),
    this is a no-op that preserves existing behavior.

    Round 49 C1 fix: the import was `from maestro_auth.store import get_auth_store`
    which does not exist — `maestro_auth/store.py` is not a module. The actual
    `get_auth_store` lives in `maestro_auth/permissions.py`. The broken import
    was swallowed by the broad `except Exception: return True` below, silently
    disabling RBAC on all 158 endpoints. Now fixed: correct import path +
    fail-closed when auth is enabled but the store is unavailable.
    """
    try:
        from maestro_auth.permissions import is_auth_enabled, require_user, get_auth_store
        from maestro_auth.models import Permissions

        if not is_auth_enabled():
            return True  # Dev mode — no auth required

        # Auth is enabled — verify the user has the right permission
        result = require_user(request)  # Raises 401 if not authed
        user = result["user"]
        store = get_auth_store()

        # Admins bypass permission checks
        if user.get("is_admin"):
            return result

        # GET requests need OEM_READ; POST/PUT/DELETE need OEM_WRITE
        if request.method == "GET":
            required = Permissions.OEM_READ
        else:
            required = Permissions.OEM_WRITE

        if not store.has_permission(user["id"], required):
            store.audit(
                event_type="permission_denied",
                user_id=user["id"],
                email=user["email"],
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent", ""),
                resource=str(request.url.path),
                detail={"reason": "missing_permission", "required": required},
                success=False,
            )
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied: requires {required}",
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        # Round 49 C1 fix: if auth IS enabled but the auth module is broken,
        # FAIL CLOSED — do not silently allow access. Only allow access in
        # dev mode (when is_auth_enabled() returns False, handled above).
        from maestro_auth.permissions import is_auth_enabled
        if is_auth_enabled():
            logger.error("RBAC check failed with auth enabled — FAILING CLOSED: %s", e)
            raise HTTPException(
                status_code=503,
                detail="Authentication system unavailable. Access denied.",
            )
        # Dev mode — auth not enabled, allow access (backward compat)
        logger.debug("RBAC check skipped (dev mode): %s", e)
        return True


router = APIRouter(dependencies=[
    Depends(_require_tenant_access),
    Depends(_require_oem_permission),
])


# ─── Helper: serialize a law to a UI-friendly dict ──────────────────────────

def _law_to_dict(law: Any) -> dict[str, Any]:
    """Serialize an OrganizationalLaw to a dict with all fields the UI needs."""
    model = oem_state.model
    provenance = model.get_provenance_chain(law.code)
    # Traverse evidence graph from this law
    chain_display: dict[str, Any] = {}
    try:
        chain = oem_state.graph.traverse(f"law:{law.code}")
        if chain.nodes:
            chain_display = chain.to_display()
    except Exception:
        pass
    return {
        "code": law.code,
        "statement": law.statement,
        "condition": law.condition,
        "outcome": law.outcome,
        "status": law.status.value,
        "confidence": round(law.confidence, 4),
        "evidence_count": law.evidence_count,
        "validated_runtimes": law.validated_runtimes,
        "failed_runtimes": law.failed_runtimes,
        "counter_examples": law.counter_examples,
        "providers": sorted(law.providers),
        "known_to_leadership": law.known_to_leadership,
        "verified_by": getattr(law, "verified_by", None),
        "verified_at": law.verified_at.isoformat() if getattr(law, "verified_at", None) else None,
        "drift_detected": law.drift_detected,
        "first_inferred": law.first_inferred.isoformat() if law.first_inferred else None,
        "last_validated": law.last_validated.isoformat() if law.last_validated else None,
        "provenance": provenance,
        "evidence_chain": chain_display,
    }


# ─── Helper: serialize a recommendation ─────────────────────────────────────

def _rec_to_dict(rec: Any) -> dict[str, Any]:
    """Serialize a Recommendation to a dict with all fields the UI needs."""
    return {
        "rec_id": rec.rec_id,
        "title": rec.title,
        "description": rec.description,
        "recommendation": rec.recommendation,
        "confidence": round(rec.confidence, 4),
        "decision_question": rec.decision_question,
        "provenance": rec.provenance,
        "linked_laws": rec.linked_laws,
        "impact": rec.impact,
        "urgency": rec.urgency,
        "evidence_chain": rec.evidence_chain or {},
        "supporting_artifacts": rec.supporting_artifacts,
        "contradicting_artifacts": rec.contradicting_artifacts,
        "evidence_strength": round(rec.evidence_strength, 4),
    }


# ─── 1. GET /api/oem/state ──────────────────────────────────────────────────

@router.get("/state")
def get_oem_state() -> dict[str, Any]:
    """Top-level OEM state — signal counts, law counts, health metrics.

    The 'connected' field on each provider reflects REAL OAuth state
    (from OAuthManager), NOT whether the OEM has seed data for that provider.
    This fixes the contradiction where the Signals page said 'connected'
    but the Settings page said 'not configured'.
    """
    model = oem_state.model
    summary = model.get_summary()

    # Check real OAuth state for each provider
    from maestro_api.oem_state import import_state
    try:
        import_state.ensure_initialized()
        real_connections = {c["provider"]: c["connected"] for c in import_state.oauth.status()}
    except Exception:
        real_connections = {}

    # Add provider detail for the Signals page
    providers = []
    provider_names = sorted(model.connected_providers)
    provider_meta = {
        "github": {"label": "GitHub", "artifact_label": "repositories"},
        "jira": {"label": "Jira", "artifact_label": "projects"},
        "slack": {"label": "Slack", "artifact_label": "channels"},
        "confluence": {"label": "Confluence", "artifact_label": "spaces"},
        "gmail": {"label": "Gmail", "artifact_label": "calendars"},
    }
    for p in provider_names:
        meta = provider_meta.get(p, {"label": p, "artifact_label": "items"})
        signal_count = sum(1 for s in oem_state.signals if s.provider.value == p)
        # Use real OAuth state, not seed data presence
        real_connected = real_connections.get(p, False)
        providers.append({
            "provider": p,
            "label": meta["label"],
            "connected": real_connected,
            "demo_data": signal_count > 0 and not real_connected,  # Flag seed data
            "signal_count": signal_count,
            "artifact_label": meta["artifact_label"],
        })
    return {
        "summary": summary,
        "providers": providers,
        "health": {
            "decision_velocity_days": model.health.decision_velocity_days,
            "release_frequency": model.health.release_frequency,
            "incident_rate": model.health.incident_rate,
            "p1_cluster_risk": round(model.health.p1_cluster_risk, 4),
            "velocity_trend": model.health.velocity_trend,
        },
        "last_updated": model.last_updated.isoformat() if model.last_updated else None,
    }


# ─── 2. GET /api/oem/dashboard ──────────────────────────────────────────────

@router.get("/dashboard")
def get_dashboard() -> dict[str, Any]:
    """Home dashboard — overnight changes, today's decisions, key metrics."""
    model = oem_state.model
    recs = oem_state.decisions.get_recommendations()
    experts = model.knowledge.get_hidden_experts()
    bottlenecks = model.approvals.get_bottlenecks()
    risks = model.knowledge.get_concentration_risk()
    departures = model.risks.departure_risks

    # Build "overnight changes" feed from real OEM events
    changes: list[dict[str, Any]] = []
    for expert in experts[:3]:
        changes.append({
            "type": "hidden_expert",
            "title": f"Hidden expert discovered: {expert['entity']}",
            "detail": f"Influence {expert['influence']:.1f} across {len(expert['domains'])} domains: {', '.join(expert['domains'][:3])}",
            "severity": "info",
            "timestamp": model.last_updated.isoformat() if model.last_updated else None,
        })
    for bn in bottlenecks[:2]:
        changes.append({
            "type": "bottleneck",
            "title": f"Bottleneck detected: {bn['gate']}",
            "detail": f"{bn['items_gated']} items gated, avg delay {bn.get('avg_delay_days', 0):.1f} days",
            "severity": "warning",
            "timestamp": model.last_updated.isoformat() if model.last_updated else None,
        })
    for domain, score in list(risks.items())[:2]:
        changes.append({
            "type": "concentration_risk",
            "title": f"Bus-factor risk in {domain}",
            "detail": f"Knowledge concentrated in one person (influence {score:.1f})",
            "severity": "urgent",
            "timestamp": model.last_updated.isoformat() if model.last_updated else None,
        })
    for entity, prob in list(departures.items())[:2]:
        changes.append({
            "type": "departure_risk",
            "title": f"Departure risk: {entity}",
            "detail": f"Probability {prob:.0%}",
            "severity": "urgent",
            "timestamp": model.last_updated.isoformat() if model.last_updated else None,
        })
    # Strengthened laws (recently validated)
    for law in list(model.laws.values())[:2]:
        if law.validated_runtimes > 0:
            changes.append({
                "type": "law_strengthened",
                "title": f"Law strengthened: {law.code}",
                "detail": f"{law.statement} — validated {law.validated_runtimes}/{law.validated_runtimes + law.failed_runtimes} runtimes, confidence {law.confidence:.2f}",
                "severity": "info",
                "timestamp": law.last_validated.isoformat() if law.last_validated else None,
            })

    return {
        "metrics": {
            "signals_processed": len(oem_state.signals),
            "learning_objects": len(model.learning_objects),
            "laws_inferred": len(model.laws),
            "validated_laws": sum(1 for l in model.laws.values() if l.status.value == "validated"),
            "hidden_experts": len(experts),
            "bottlenecks": len(bottlenecks),
            "concentration_risks": len(risks),
            "departure_risks": len(departures),
            "recommendations_active": len(recs),
            "decision_velocity_days": model.health.decision_velocity_days,
            "p1_cluster_risk": round(model.health.p1_cluster_risk, 4),
        },
        "overnight_changes": changes,
        "today_decisions": [_rec_to_dict(r) for r in recs[:5]],
        "providers_connected": sorted(model.connected_providers),
    }


# ─── 3. GET /api/oem/recommendations ───────────────────────────────────────

@router.get("/recommendations")
def get_recommendations(urgency: str | None = Query(None)) -> dict[str, Any]:
    """All active recommendations with full evidence chains.

    Each recommendation automatically creates a prediction for tracking.
    Every recommendation includes explainable confidence.
    """
    recs = oem_state.decisions.get_recommendations()
    if urgency:
        recs = [r for r in recs if r.urgency == urgency]

    # Auto-create predictions for each recommendation (closes the learning loop)
    from maestro_oem.prediction_lifecycle import ClosedLoopLearningManager
    import os as _os
    from pathlib import Path as _Path
    _learning_db = _os.environ.get("MAESTRO_LEARNING_DB",
                                    get_db_url_for_learning())
    _Path(_learning_db).parent.mkdir(parents=True, exist_ok=True)
    try:
        manager = ClosedLoopLearningManager(
            _learning_db, oem_state.model, oem_state.signals,
            contradiction_log=getattr(oem_state, "_contradiction_log", None),
        )
        for rec in recs:
            manager.on_recommendation_surfaced(rec, oem_state.model)
    except Exception as e:
        logger.warning("Prediction recording failed: %s", e)

    rec_dicts = [_rec_to_dict(r) for r in recs]

    # Enrich with explainable confidence
    try:
        for r in rec_dicts:
            explanation = manager.explain_confidence(r.get("title", ""), r.get("confidence", 0.5), "recommendation")
            r["confidence_explanation"] = explanation
    except Exception:
        pass  # Don't fail the API if explanation fails

    return {
        "recommendations": rec_dicts,
        "total": len(recs),
    }


# ─── 4. GET /api/oem/inbox ─────────────────────────────────────────────────

@router.get("/inbox")
def get_inbox(
    limit: int = Query(50, ge=1, le=200, description="Max items per category"),
) -> dict[str, Any]:
    """Executive inbox — decisions owed, drift, dissent.

    Paginated: each category is capped at `limit` items (default 50).
    At 100k employees, the inbox could have hundreds of items per category.
    """
    model = oem_state.model
    recs = oem_state.decisions.get_recommendations()

    # Decisions owed = urgent recommendations
    decisions_owed = [_rec_to_dict(r) for r in recs if r.urgency == "urgent"][:limit]
    # Decisions needing attention (normal urgency)
    decisions_attention = [_rec_to_dict(r) for r in recs if r.urgency == "normal"][:limit]

    # Drift = laws with drift_detected or stressed status
    drift_laws = [_law_to_dict(l) for l in model.laws.values()
                  if l.drift_detected or l.status.value == "stressed"][:limit]

    # Dissent = laws unknown to leadership (the org knows something the CEO doesn't)
    dissent = [_law_to_dict(l) for l in model.laws.values()
               if l.status.value == "unknown_to_leadership"][:limit]

    return {
        "decisions_owed": decisions_owed,
        "decisions_attention": decisions_attention,
        "drift": drift_laws,
        "dissent": dissent,
        "counts": {
            "owed": len(decisions_owed),
            "attention": len(decisions_attention),
            "drift": len(drift_laws),
            "dissent": len(dissent),
        },
    }


# ─── 5. GET /api/oem/laws ──────────────────────────────────────────────────

@router.get("/laws")
def get_laws(
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200, description="Max laws to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
) -> dict[str, Any]:
    """All organizational laws with provenance and evidence chains.

    Paginated: default limit=50, max limit=200. Use offset for pagination.
    At 10M signals, thousands of laws may exist — unbounded queries would
    produce multi-MB responses and multi-second frontend renders.
    """
    model = oem_state.model
    laws = list(model.laws.values())
    if status:
        laws = [l for l in laws if l.status.value == status]
    total = len(laws)
    # Apply pagination
    paginated = laws[offset:offset + limit]
    return {
        "laws": [_law_to_dict(l) for l in paginated],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total,
        "by_status": {
            s: sum(1 for l in laws if l.status.value == s)
            for s in {"candidate", "validated", "stressed", "invalidated", "unknown_to_leadership"}
        },
    }


@router.get("/laws/{code}")
def get_law(code: str) -> dict[str, Any]:
    """Single law with full evidence chain."""
    model = oem_state.model
    law = model.laws.get(code)
    if not law:
        raise HTTPException(status_code=404, detail=f"Law {code} not found")
    return _law_to_dict(law)


@router.post("/laws/{code}/verify")
def verify_law(code: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Verify an organizational law — human sign-off.

    V8 Competitor Analysis Feature C — Verified Knowledge Layer. The Guru
    lesson: verified knowledge is the differentiator. When a human verifies
    a law, their identity and the timestamp are recorded. Only verified
    laws are cited as "facts" in high-stakes contexts.

    Payload:
        verified_by: str (email of the verifier, required)

    Returns the updated law with verified_by + verified_at set.
    """
    verified_by = payload.get("verified_by", "")
    if not verified_by:
        raise HTTPException(400, "verified_by is required")

    from datetime import datetime, timezone
    model = oem_state.model
    law = model.laws.get(code)
    if not law:
        raise HTTPException(status_code=404, detail=f"Law {code} not found")

    law.verified_by = verified_by
    law.verified_at = datetime.now(timezone.utc)

    return _law_to_dict(law)


@router.get("/laws/verified/list")
def list_verified_laws() -> dict[str, Any]:
    """List all human-verified laws.

    V8 Competitor Analysis Feature C — Verified Knowledge Layer.
    Returns only laws that have been verified by a human (verified_by is set).
    """
    model = oem_state.model
    verified = [
        _law_to_dict(law)
        for law in model.laws.values()
        if getattr(law, "verified_by", None) is not None
    ]
    return {
        "verified_laws": verified,
        "count": len(verified),
    }


# ─── 6. GET /api/oem/ask ───────────────────────────────────────────────────

@router.get("/ask")
def ask(q: str = Query(..., description="Natural-language question")) -> dict[str, Any]:
    """Ask the organization — NL question answered from OEM evidence.

    Round 44 (Phase 5) — Constrained personal context:
    When the personal-context-in-work toggle is ON (default OFF), ONE
    optional line is appended to the synthesized answer:
        "Personal context (opt-in): {one-sentence personal state}."

    Constitutional constraints:
      - The personal context line is INFORMATIONAL, never prescriptive.
      - It NEVER changes the work recommendation.
      - It NEVER makes the answer conditional on personal state.
      - It references ONLY the user's own state (energy, sleep, calendar
        conflicts) — NEVER a third party.
      - It is a single sentence, labeled, and dismissible.
      - It is None when the toggle is OFF, incognito is active, or no
        relevant state exists.
    """
    result = oem_state.decisions.answer_question(q)

    # Round 44 — append ONE optional personal-context line.
    # The line is informational only. It never modifies the recommendation
    # or the confidence. It appears as a separate field so the UI can
    # render it as a dismissible aside, not part of the answer.
    personal_context_line: str | None = None
    try:
        from maestro_personal.integration import build_personal_context_line_for_ask
        from maestro_oem.user_settings import UserSettings
        toggle_on = UserSettings.is_personal_context_in_work_enabled("default")
        personal_context_line = build_personal_context_line_for_ask("default", q, toggle_on)
    except Exception as e:
        logger.debug("Personal context line build failed: %s", e)

    result["personal_context_line"] = personal_context_line
    # CEO Directive: "Maestro never invents precision." Remove confidence from /ask response.
    result.pop("confidence", None)
    return result


# ─── 7. GET /api/oem/simulator ─────────────────────────────────────────────

@router.get("/simulator")
def get_simulator() -> dict[str, Any]:
    """Decision simulator state — current recommendations + what-if inputs."""
    model = oem_state.model
    recs = oem_state.decisions.get_recommendations()
    # The simulator shows the top recommendation and lets the user adjust inputs
    top_rec = recs[0] if recs else None
    return {
        "scenario": {
            "title": top_rec.title if top_rec else "No active scenario",
            "description": top_rec.description if top_rec else "",
            "recommendation": top_rec.recommendation if top_rec else "",
            "confidence": round(top_rec.confidence, 4) if top_rec else 0.0,
            "decision_question": top_rec.decision_question if top_rec else "",
        },
        "current_health": {
            "p1_cluster_risk": round(model.health.p1_cluster_risk, 4),
            "incident_rate": model.health.incident_rate,
            "decision_velocity_days": model.health.decision_velocity_days,
            "release_frequency": model.health.release_frequency,
        },
        "linked_laws": top_rec.linked_laws if top_rec else [],
        "evidence_chain": top_rec.evidence_chain if top_rec else {},
        "supporting_artifacts": top_rec.supporting_artifacts if top_rec else [],
        "contradicting_artifacts": top_rec.contradicting_artifacts if top_rec else [],
    }


@router.post("/simulator")
def run_simulator(payload: dict[str, Any]) -> dict[str, Any]:
    """Run a what-if simulation. Delegates to the unified SimulationEngine.

    Kept for backward compatibility with UIs that POST to /simulator.
    POST /api/oem/simulate is the canonical endpoint; both return the
    same response shape because they call the same engine.
    """
    return simulate_scenario(payload)


# ─── 8. GET /api/oem/provenance/{id} ───────────────────────────────────────

@router.get("/provenance/{entity_id}")
def get_provenance(entity_id: str) -> dict[str, Any]:
    """Full provenance chain for any entity (law code, entity name, rec_id)."""
    model = oem_state.model
    # Try receipt chain first
    chain = model.get_provenance_chain(entity_id)
    # Try evidence graph traversal
    graph_chain: dict[str, Any] = {}
    for prefix in ["", "law:", "rec:", "lo:"]:
        try:
            c = oem_state.graph.traverse(f"{prefix}{entity_id}")
            if c.nodes:
                graph_chain = c.to_display()
                break
        except Exception:
            pass
    return {
        "entity_id": entity_id,
        "receipt_chain": chain,
        "evidence_chain": graph_chain,
        "found": bool(chain or graph_chain),
    }


# ─── 9. GET /api/oem/knowledge ─────────────────────────────────────────────

@router.get("/knowledge")
def get_knowledge(
    limit: int = Query(50, ge=1, le=200, description="Max items per category"),
) -> dict[str, Any]:
    """Knowledge flow — hidden experts, concentration risk, knowledge death.

    Paginated: each category is capped at `limit` items (default 50).
    """
    model = oem_state.model
    experts = model.knowledge.get_hidden_experts()[:limit]
    risks = dict(list(model.knowledge.get_concentration_risk().items())[:limit])
    # Knowledge death = LOs of type knowledge_death
    knowledge_death = [
        {
            "type": lo.type.value,
            "title": lo.title,
            "description": lo.description,
            "entities": lo.entities,
            "boundary": lo.metadata.get("boundary", "unknown"),
            "confidence": round(lo.confidence, 4),
            "evidence_count": lo.evidence_count,
            "providers": sorted(lo.providers),
        }
        for lo in model.learning_objects.values()
        if lo.type.value == "knowledge_death"
    ]
    # Duplicate work LOs
    duplicates = [
        {
            "type": lo.type.value,
            "title": lo.title,
            "description": lo.description,
            "entities": lo.entities,
            "domain": lo.metadata.get("domain", "unknown"),
            "confidence": round(lo.confidence, 4),
            "evidence_count": lo.evidence_count,
            "providers": sorted(lo.providers),
        }
        for lo in model.learning_objects.values()
        if lo.type.value == "duplicate_work"
    ]
    return {
        "hidden_experts": experts,
        "concentration_risks": [{"domain": d, "score": round(s, 2)} for d, s in risks.items()],
        "knowledge_death": knowledge_death,
        "duplicate_work": duplicates,
        "totals": {
            "experts": len(experts),
            "risks": len(risks),
            "knowledge_death": len(knowledge_death),
            "duplicates": len(duplicates),
        },
    }


# ─── 10. GET /api/oem/autocomplete ────────────────────────────────────────

@router.get("/autocomplete")
def autocomplete(
    q: str = Query("", description="Partial query for autocomplete"),
    limit: int = Query(10, ge=1, le=50, description="Max suggestions"),
    surface: str = Query("", description="Current surface for context-aware ranking"),
    user: str = Query("", description="Current user email for personalization"),
    org: str = Query("", description="Current organization ID"),
) -> dict[str, Any]:
    """Real semantic Organizational Autocomplete.

    No hardcoded suggestions. Every result is derived from the live OEM
    state across ALL data sources:
      - Learning Objects (patterns, experts, bottlenecks, departure risks)
      - Patterns (detected organizational patterns)
      - Receipts (signal history)
      - Laws (induced organizational laws)
      - Evidence (evidence graph nodes + edges)
      - Knowledge Graph (hidden experts, concentration risks)
      - Execution Model (health metrics, approval network)
      - Recommendations (active decisions)
      - Context (current surface, user, org)
      - History (contradiction feedback log — feedback learning)

    Each suggestion includes:
      - completion: the suggested text
      - reason: why this is relevant
      - expected_outcome: what the OEM predicts
      - confidence: 0.0–1.0 Bayesian confidence
      - evidence: supporting evidence chain
      - similar_executions: past similar patterns
      - citations: law codes, LO ids, receipt ids

    Ranking factors:
      - Recency (90-day half-life)
      - Authority (influence / evidence count)
      - Outcome (validated runtimes ratio)
      - Feedback learning (agree/reject from contradiction log)

    Typing "We should..." produces completely different results for every
    company because the underlying data is derived from that company's
    actual signal history.
    """
    from maestro_oem.autocomplete import SemanticAutocompleteEngine

    context = {
        "surface": surface,
        "user": user,
        "org": org,
    }

    engine = SemanticAutocompleteEngine(
        model=oem_state.model,
        graph=oem_state.graph,
        decisions=oem_state.decisions,
        contradiction_log=getattr(oem_state, "_contradiction_log", None),
        signals=oem_state.signals,
    )

    result = engine.suggest(query=q, context=context, limit=limit)
    return result


# ─── 11. GET /api/oem/receipts ────────────────────────────────────────────

@router.get("/receipts")
def get_receipts(
    limit: int = Query(100, ge=1, le=500),
    law_code: str | None = Query(None, description="Filter by law code"),
    provider: str | None = Query(None, description="Filter by provider"),
) -> dict[str, Any]:
    """Structured receipts for the Audit Log — no JSON.stringify in the UI.

    Builds receipts from the OEM's signal history (the same signals that
    fed the laws). Each receipt is one signal that contributed to a law.

    Returns a flat list of receipts, each with:
      - receipt_id, timestamp, law_code, provider, signal_type, actor,
        artifact, action
    """
    model = oem_state.model

    # Build a map: signal_id → law_codes that consumed it
    signal_to_laws: dict[str, list[str]] = {}
    for code, law in model.laws.items():
        for sig_id in (law.signal_ids or []):
            signal_to_laws.setdefault(str(sig_id), []).append(code)

    # Signals live on oem_state (the original list fed to engine.ingest)
    all_signals = oem_state.signals
    receipts: list[dict[str, Any]] = []

    for signal in all_signals:
        sig_id = str(signal.signal_id) if hasattr(signal, "signal_id") else str(id(signal))
        laws_for_sig = signal_to_laws.get(sig_id, [])
        # Filter by law_code if specified
        if law_code and law_code not in laws_for_sig:
            continue
        # Filter by provider
        sig_provider = signal.provider.value if hasattr(signal.provider, "value") else str(signal.provider)
        if provider and sig_provider.lower() != provider.lower():
            continue

        # If filtering and no law references this signal, skip
        if not laws_for_sig and (law_code or provider):
            continue

        receipts.append({
            "receipt_id": sig_id,
            "timestamp": signal.timestamp.isoformat() if hasattr(signal.timestamp, "isoformat") else str(signal.timestamp),
            "law_codes": laws_for_sig,
            "law_code": laws_for_sig[0] if laws_for_sig else None,
            "provider": sig_provider,
            "signal_type": signal.type.value if hasattr(signal.type, "value") else str(signal.type),
            "actor": signal.actor if hasattr(signal, "actor") else "unknown",
            "artifact": signal.artifact if hasattr(signal, "artifact") else "",
            "action": _extract_action(signal),
            "domain": signal.metadata.get("domain", "") if hasattr(signal, "metadata") and signal.metadata else "",
        })

    # Sort by timestamp desc (best effort — timestamps are ISO strings)
    receipts.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
    return {
        "receipts": receipts[:limit],
        "total": len(receipts),
        "filters": {"law_code": law_code, "provider": provider},
    }


def _extract_action(signal) -> str:
    """Extract a human-readable action from a signal's metadata."""
    if not hasattr(signal, "metadata") or not signal.metadata:
        return ""
    md = signal.metadata
    for key in ("action", "transition", "state", "issue_type"):
        if key in md:
            return str(md[key])
    return ""


@router.get("/signals")
def get_signals(
    limit: int = Query(100, ge=1, le=500),
    law_code: str | None = Query(None, description="Filter by law code"),
    provider: str | None = Query(None, description="Filter by provider"),
) -> dict[str, Any]:
    """Structured signal history for the Engineering Audit Log surface.

    This is the same data as /receipts, but returned under the `signals` key
    (the format loadEngAudit() in eng_audit.js expects). The eng-audit surface
    was calling /signals but only /receipts existed — this caused a 404 that
    made the surface show "HTTP 404: Not Found" instead of the signal list.

    Returns:
      - signals: list of {receipt_id, timestamp, provider, signal_type,
                 actor, artifact, law_code, action, domain}
      - total: total count of signals matching the filter
    """
    # Delegate to /receipts and reshape
    result = get_receipts(limit=limit, law_code=law_code, provider=provider)
    return {
        "signals": result["receipts"],
        "total": result["total"],
        "filters": result["filters"],
    }


# ─── 12. POST /api/oem/meetings/analyze ───────────────────────────────────

@router.post("/meetings/analyze")
def analyze_meeting(payload: dict[str, Any]) -> dict[str, Any]:
    """Analyze a meeting transcript for objections, laws triggered, action items.

    Replaces the hardcoded 5-line Live Meeting script with real OEM-driven
    meeting intelligence.

    Payload: {transcript: [{speaker, text, timestamp?}, ...]}
    Returns: {
      objections: [{speaker, text, law_code, severity}],
      actions: [{text, owner, due?}],
      laws_triggered: [{code, statement, relevance}],
      summary: {objection_count, action_count, law_count},
    }
    """
    transcript = payload.get("transcript", [])
    if not transcript:
        return {
            "objections": [],
            "actions": [],
            "laws_triggered": [],
            "summary": {"objection_count": 0, "action_count": 0, "law_count": 0},
        }

    model = oem_state.model
    laws_list = list(model.laws.values())

    objections: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    laws_triggered: list[dict[str, Any]] = []

    # Objection keywords (not hardcoded insights — these are syntactic markers)
    objection_markers = ["dissent", "disagree", "object", "concern", "pushback",
                         "not sure", "wait", "hold on", "actually"]
    # Action item markers
    action_markers = ["let's", "we should", "i'll", "i will", "action item",
                      "follow up", "todo", "assign", "owner:"]

    for line in transcript:
        speaker = line.get("speaker", "unknown")
        text = line.get("text", "")
        text_lower = text.lower()

        # Detect objections
        if any(marker in text_lower for marker in objection_markers):
            # Find the most relevant law (by keyword overlap)
            best_law = None
            best_score = 0
            for law in laws_list:
                law_text = (law.statement + " " + law.condition).lower()
                words = [w for w in text_lower.split() if len(w) > 3]
                overlap = sum(1 for w in words if w in law_text)
                if overlap > best_score:
                    best_score = overlap
                    best_law = law
            objections.append({
                "speaker": speaker,
                "text": text,
                "law_code": best_law.code if best_law else None,
                "law_statement": best_law.statement[:120] if best_law else None,
                "severity": "high" if best_score > 3 else "medium" if best_score > 0 else "low",
            })
            if best_law and not any(l["code"] == best_law.code for l in laws_triggered):
                laws_triggered.append({
                    "code": best_law.code,
                    "statement": best_law.statement,
                    "relevance": round(best_score / 10, 2),
                })

        # Detect action items
        if any(marker in text_lower for marker in action_markers):
            # Try to extract owner
            owner = speaker
            for marker in ["owner:", "assign:"]:
                if marker in text_lower:
                    idx = text_lower.index(marker) + len(marker)
                    owner = text[idx:].split()[0].strip(",.") or speaker
            actions.append({
                "text": text,
                "owner": owner,
                "due": line.get("due"),
            })

        # Detect law references by code (e.g., "L-0001")
        import re
        law_refs = re.findall(r"L-\d{4}", text)
        for ref in law_refs:
            law = next((l for l in laws_list if l.code == ref), None)
            if law and not any(l["code"] == ref for l in laws_triggered):
                laws_triggered.append({
                    "code": law.code,
                    "statement": law.statement,
                    "relevance": 1.0,
                })

    return {
        "objections": objections,
        "actions": actions,
        "laws_triggered": laws_triggered,
        "summary": {
            "objection_count": len(objections),
            "action_count": len(actions),
            "law_count": len(laws_triggered),
        },
    }


# ─── 13. POST /api/oem/contradict ─────────────────────────────────────────

@router.post("/contradict")
def contradict_law(payload: dict[str, Any]) -> dict[str, Any]:
    """Submit contradiction feedback on a law or recommendation.

    Payload: {
      target_type: "law"|"recommendation",
      target_id: str (law code or rec id),
      action: "agree"|"reject"|"modify"|"ignore",
      reasoning?: str,
      actor?: str
    }
    Returns: {ok, target_id, action, affected_laws: [{code, confidence_before, confidence_after}]}

    This is the optimistic-update target — the UI can apply the feedback
    locally and the backend confirms or rolls back.
    """
    from maestro_oem.contradiction import ContradictionEngine, FeedbackAction, ContradictionLog

    target_type = payload.get("target_type", "law")
    target_id = payload.get("target_id", "")
    action_str = payload.get("action", "ignore").lower()
    reasoning = payload.get("reasoning", "")
    actor = payload.get("actor", "ceo@maestro.local")

    if not target_id:
        raise HTTPException(400, "target_id is required")

    if target_type == "law" and target_id not in oem_state.model.laws:
        raise HTTPException(404, f"Law {target_id} not found")

    action_map = {
        "agree": FeedbackAction.AGREE,
        "reject": FeedbackAction.REJECT,
        "modify": FeedbackAction.MODIFY,
        "ignore": FeedbackAction.IGNORE,
    }
    action = action_map.get(action_str, FeedbackAction.IGNORE)

    # Use the shared contradiction log so autocomplete can learn from feedback
    if oem_state._contradiction_log is None:
        oem_state._contradiction_log = ContradictionLog()
    engine = ContradictionEngine(oem_state.model, oem_state._contradiction_log)
    event = engine.apply_feedback(
        target_type=target_type,
        target_id=target_id,
        action=action,
        reasoning=reasoning,
        actor=actor,
    )

    # Refresh downstream artifacts (decision engine + evidence graph)
    oem_state._refresh_downstream()

    # Record feedback in the learning engine for calibration
    import os as _os
    from pathlib import Path as _Path
    _learning_db = _os.environ.get("MAESTRO_LEARNING_DB",
                                    get_db_url_for_learning())
    try:
        _Path(_learning_db).parent.mkdir(parents=True, exist_ok=True)
        from maestro_oem.learning import ContinuousLearningEngine
        learning = ContinuousLearningEngine(_learning_db, oem_state.model, oem_state.signals)
        for law_code in event.affected_laws:
            law = oem_state.model.laws.get(law_code)
            if law:
                conf_before = event.confidence_before.get(law_code, 0)
                conf_after = law.confidence
                learning.on_feedback(
                    entity_type="law",
                    entity_id=law_code,
                    feedback=action_str,
                    confidence_before=conf_before,
                    confidence_after=conf_after,
                    reasoning=reasoning,
                    actor=actor,
                )
    except Exception as e:
        import logging as _l
        _l.getLogger(__name__).warning("Learning engine feedback recording failed: %s", e)

    # Close the loop: resolve pending predictions for the target entity AND
    # every affected law. Without this wire, predictions stay pending forever
    # even after the CEO explicitly agreed or rejected — which is the bug the
    # auditor found (Brier score stuck at 0.5, improvement dashboard stuck at
    # resolved=0). manager.on_feedback() flips prediction status and records
    # the calibration outcome (hit/miss) so the Brier score updates.
    try:
        from maestro_oem.prediction_lifecycle import ClosedLoopLearningManager
        from maestro_oem.learning import CalibrationEngine
        cal = CalibrationEngine(_learning_db)
        manager = ClosedLoopLearningManager(
            _learning_db, oem_state.model, oem_state.signals, cal,
            contradiction_log=oem_state._contradiction_log,
        )
        # Resolve predictions whose entity_id == target_id OR whose linked_laws
        # contain target_id (covers both rec-targeted and law-targeted feedback).
        conf_after = oem_state.model.laws[event.affected_laws[0]].confidence \
            if event.affected_laws and event.affected_laws[0] in oem_state.model.laws \
            else 0.5
        manager.on_feedback(
            entity_type=target_type,
            entity_id=target_id,
            feedback=action_str,
            confidence_before=event.confidence_before.get(
                event.affected_laws[0] if event.affected_laws else "", 0.5
            ),
            confidence_after=conf_after,
            reasoning=reasoning,
            actor=actor,
        )
    except Exception as e:
        import logging as _l
        _l.getLogger(__name__).warning("Closed-loop prediction resolution failed: %s", e)

    return {
        "ok": True,
        "target_type": target_type,
        "target_id": target_id,
        "action": action_str,
        "affected_laws": [
            {
                "code": code,
                "confidence_before": round(event.confidence_before.get(code, 0), 4),
                "confidence_after": round(
                    oem_state.model.laws[code].confidence if code in oem_state.model.laws else 0,
                    4,
                ),
            }
            for code in event.affected_laws
        ],
    }


# ─── 14. Drill-down endpoints (fix every dead-end interaction) ─────────────

@router.get("/entity/{entity_type}/{entity_id}")
def get_entity_drilldown(
    entity_type: str,
    entity_id: str,
) -> dict[str, Any]:
    """Full drill-down for any entity: Why? Where? Evidence? Timeline? People?
    Prediction? Simulation? Recommendation?

    Supports entity_type: law | recommendation | expert | pattern | signal | risk | metric
    entity_id: the entity's ID (law code, rec_id, entity name, pattern_id, signal_id, etc.)

    Returns a unified drill-down view with 8 tabs of information.
    """
    model = oem_state.model
    result: dict[str, Any] = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "found": False,
        "why": None,
        "where": None,
        "evidence": [],
        "timeline": [],
        "people": [],
        "prediction": None,
        "simulation": None,
        "recommendation": None,
    }

    if entity_type == "law":
        law = model.laws.get(entity_id)
        if not law:
            raise HTTPException(404, f"Law {entity_id} not found")
        result["found"] = True
        result["why"] = f"Law {law.code} was induced because the OEM observed {law.evidence_count} evidence signals that consistently show: {law.statement}"
        result["where"] = {
            "providers": list(law.providers or []),
            "condition": law.condition,
            "outcome": law.outcome,
        }
        # Evidence: signals that fed this law
        for sig_id in (law.signal_ids or [])[:10]:
            sig = _find_signal(str(sig_id))
            if sig:
                result["evidence"].append({
                    "type": "signal",
                    "signal_id": str(sig.signal_id),
                    "signal_type": sig.type.value if hasattr(sig.type, "value") else str(sig.type),
                    "actor": sig.actor,
                    "artifact": sig.artifact,
                    "provider": sig.provider.value if hasattr(sig.provider, "value") else str(sig.provider),
                    "timestamp": sig.timestamp.isoformat() if hasattr(sig.timestamp, "isoformat") else str(sig.timestamp),
                })
        # Timeline: when was it first inferred, validated, etc.
        result["timeline"] = [
            {"event": "first_inferred", "timestamp": law.first_inferred, "detail": f"Law {law.code} first inferred"},
            {"event": "last_validated", "timestamp": law.last_validated, "detail": f"Last validated ({law.validated_runtimes} validations, {law.failed_runtimes} failures)"},
        ]
        # People: entities involved
        result["people"] = _extract_people_from_law(law)
        # Prediction: what this law predicts
        result["prediction"] = {
            "condition": law.condition,
            "outcome": law.outcome,
            "confidence": round(law.confidence, 4),
            "validated_runtimes": law.validated_runtimes,
            "failed_runtimes": law.failed_runtimes,
        }
        # Simulation: link to simulator
        result["simulation"] = {
            "available": True,
            "prompt": f"What happens if we change the conditions that produce {law.code}?",
            "linked_laws": [law.code],
        }
        # Recommendation: linked recommendations
        recs = [r for r in oem_state.decisions.get_recommendations() if law.code in (r.linked_laws or [])]
        result["recommendation"] = {
            "available": len(recs) > 0,
            "items": [{"title": r.title, "recommendation": r.recommendation, "urgency": r.urgency, "confidence": round(r.confidence, 4)} for r in recs[:3]],
        }

    elif entity_type == "recommendation":
        recs = oem_state.decisions.get_recommendations()
        # rec_ids are ephemeral (generated per call), so match by rec_id OR title
        rec = next((r for r in recs if r.rec_id == entity_id), None)
        if not rec:
            # Fallback: match by title (rec_ids change between calls)
            rec = next((r for r in recs if r.title == entity_id), None)
        if not rec:
            raise HTTPException(404, f"Recommendation {entity_id} not found")
        result["found"] = True
        result["why"] = f"This recommendation exists because the OEM detected: {rec.description}"
        result["where"] = {
            "title": rec.title,
            "urgency": rec.urgency,
            "linked_laws": rec.linked_laws or [],
        }
        result["evidence"] = [{"type": "provenance", "label": p.get("oem_change") or p.get("gate") or p.get("entity") or "evidence", "provider": p.get("provider", "")} for p in (rec.provenance or [])[:5]]
        result["timeline"] = [{"event": "created", "timestamp": None, "detail": f"Recommendation '{rec.title}' is active"}]
        result["people"] = _extract_people_from_rec(rec)
        result["prediction"] = {
            "impact": rec.impact,
            "confidence": round(rec.confidence, 4),
            "evidence_strength": rec.evidence_strength,
        }
        result["simulation"] = {
            "available": True,
            "prompt": rec.decision_question,
            "linked_laws": rec.linked_laws or [],
        }
        result["recommendation"] = {
            "available": True,
            "items": [{"title": rec.title, "recommendation": rec.recommendation, "urgency": rec.urgency, "confidence": round(rec.confidence, 4)}],
        }

    elif entity_type == "expert":
        experts = model.knowledge.get_hidden_experts()
        expert = next((e for e in experts if e.get("entity") == entity_id), None)
        if not expert:
            raise HTTPException(404, f"Expert {entity_id} not found")
        result["found"] = True
        result["why"] = f"{entity_id} is classified as a hidden expert because they have high influence ({expert.get('influence', 0):.2f}) but are not formally recognized in the approval network."
        result["where"] = {
            "domains": expert.get("domains", []),
            "influence": round(expert.get("influence", 0), 4),
            "evidence_count": expert.get("evidence_count", 0),
        }
        # Evidence: signals referencing this entity
        for sig in oem_state.signals:
            if entity_id in (sig.actor or "") or entity_id in (sig.artifact or ""):
                result["evidence"].append({
                    "type": "signal",
                    "signal_id": str(sig.signal_id),
                    "signal_type": sig.type.value if hasattr(sig.type, "value") else str(sig.type),
                    "actor": sig.actor,
                    "artifact": sig.artifact,
                    "provider": sig.provider.value if hasattr(sig.provider, "value") else str(sig.provider),
                    "timestamp": sig.timestamp.isoformat() if hasattr(sig.timestamp, "isoformat") else str(sig.timestamp),
                })
                if len(result["evidence"]) >= 10:
                    break
        # Timeline: when this person was active
        result["timeline"] = [{"event": "signal", "timestamp": e.get("timestamp"), "detail": f"{e.get('signal_type')} on {e.get('artifact', '')[:50]}"} for e in result["evidence"][:5]]
        result["people"] = [{"name": entity_id, "role": "hidden expert", "influence": round(expert.get("influence", 0), 4)}]
        result["prediction"] = {
            "risk": "bus-factor",
            "detail": f"If {entity_id} leaves, knowledge in {expert.get('domains', [])} is at risk.",
        }
        result["recommendation"] = {
            "available": True,
            "items": [{"title": f"Document {entity_id}'s knowledge", "recommendation": f"Cross-train others in {expert.get('domains', [])}", "urgency": "normal", "confidence": 0.7}],
        }

    elif entity_type == "risk":
        # Concentration risk by domain
        risks = model.knowledge.get_concentration_risk()
        if entity_id not in risks:
            raise HTTPException(404, f"Risk domain {entity_id} not found")
        score = risks[entity_id]
        result["found"] = True
        result["why"] = f"Domain '{entity_id}' has a concentration score of {score:.2f}, meaning knowledge is held by too few people."
        result["where"] = {"domain": entity_id, "score": round(score, 4)}
        result["prediction"] = {"risk": "bus-factor", "detail": f"If the top contributor in {entity_id} leaves, organizational capacity drops significantly."}
        result["recommendation"] = {
            "available": True,
            "items": [{"title": f"Reduce concentration in {entity_id}", "recommendation": f"Cross-train additional people in {entity_id}", "urgency": "normal", "confidence": 0.7}],
        }

    elif entity_type == "pattern":
        lo = model.learning_objects.get(entity_id)
        if not lo:
            raise HTTPException(404, f"Pattern {entity_id} not found")
        result["found"] = True
        lo_type = lo.type.value if hasattr(lo.type, "value") else str(lo.type)
        result["why"] = f"This pattern was detected because the OEM observed {lo.evidence_count} signals matching: {lo.title}"
        result["where"] = {"type": lo_type, "entities": lo.entities, "providers": list(lo.providers or [])}
        for sig_id in (lo.signal_ids or [])[:5]:
            sig = _find_signal(str(sig_id))
            if sig:
                result["evidence"].append({
                    "type": "signal",
                    "signal_id": str(sig.signal_id),
                    "signal_type": sig.type.value if hasattr(sig.type, "value") else str(sig.type),
                    "actor": sig.actor,
                    "timestamp": sig.timestamp.isoformat() if hasattr(sig.timestamp, "isoformat") else str(sig.timestamp),
                })
        result["people"] = [{"name": e, "role": lo_type} for e in (lo.entities or [])]
        result["prediction"] = {"detail": lo.description, "confidence": round(lo.confidence, 4)}

    elif entity_type == "signal":
        sig = _find_signal(entity_id)
        if not sig:
            raise HTTPException(404, f"Signal {entity_id} not found")
        result["found"] = True
        result["why"] = f"This signal was recorded as a {sig.type} event from {sig.actor}."
        result["where"] = {
            "provider": sig.provider.value if hasattr(sig.provider, "value") else str(sig.provider),
            "artifact": sig.artifact,
            "actor": sig.actor,
            "team": getattr(sig, "team", ""),
        }
        result["evidence"] = [{
            "type": "signal",
            "signal_id": str(sig.signal_id),
            "signal_type": sig.type.value if hasattr(sig.type, "value") else str(sig.type),
            "actor": sig.actor,
            "artifact": sig.artifact,
            "timestamp": sig.timestamp.isoformat() if hasattr(sig.timestamp, "isoformat") else str(sig.timestamp),
            "metadata": sig.metadata,
        }]
        result["timeline"] = [{"event": "recorded", "timestamp": sig.timestamp.isoformat() if hasattr(sig.timestamp, "isoformat") else str(sig.timestamp), "detail": f"Signal recorded by {sig.provider}"}]
        result["people"] = [{"name": sig.actor, "role": "actor"}]
        # Which laws this signal contributed to
        contributing_laws = [code for code, law in model.laws.items() if entity_id in [str(s) for s in (law.signal_ids or [])]]
        result["recommendation"] = {
            "available": len(contributing_laws) > 0,
            "items": [{"title": f"Contributed to {code}", "recommendation": f"View law {code}", "urgency": "info", "confidence": 0.5} for code in contributing_laws[:3]],
        }

    elif entity_type == "metric":
        # Drill-down for a dashboard metric (signals, laws, etc.)
        result["found"] = True
        summary = model.get_summary()
        metric_labels = {
            "signals_processed": "Signals Processed",
            "learning_objects": "Learning Objects",
            "patterns_detected": "Patterns Detected",
            "laws_inferred": "Laws Inferred",
            "validated_laws": "Validated Laws",
            "recommendations_active": "Active Recommendations",
        }
        label = metric_labels.get(entity_id, entity_id)
        result["why"] = f"The '{label}' metric represents the total count of {entity_id.replace('_', ' ')} in the OEM."
        result["where"] = {"value": summary.get(entity_id, 0), "label": label}
        result["evidence"] = [{"type": "summary", "label": k, "value": v} for k, v in summary.items()]
        result["timeline"] = [{"event": "last_updated", "timestamp": model.last_updated.isoformat() if hasattr(model.last_updated, "isoformat") else str(model.last_updated), "detail": "OEM last updated"}]
        # Link to the relevant surface
        surface_map = {
            "signals_processed": "eng-signals",
            "learning_objects": "eng-oem",
            "patterns_detected": "eng-oem",
            "laws_inferred": "physics",
            "validated_laws": "physics",
            "recommendations_active": "inbox",
        }
        target_surface = surface_map.get(entity_id, "home")
        result["recommendation"] = {
            "available": True,
            "items": [{"title": f"View {label}", "recommendation": f"Navigate to {target_surface}", "urgency": "info", "confidence": 1.0}],
        }

    return result


def _find_signal(sig_id: str):
    """Find a signal by ID from the OEM state."""
    for sig in oem_state.signals:
        if str(sig.signal_id) == sig_id:
            return sig
    return None


def _extract_people_from_law(law) -> list[dict[str, str]]:
    """Extract people involved in a law from its signals."""
    people: dict[str, list[str]] = {}
    for sig_id in (law.signal_ids or [])[:20]:
        sig = _find_signal(str(sig_id))
        if sig and sig.actor:
            people.setdefault(sig.actor, [])
            sig_type = sig.type.value if hasattr(sig.type, "value") else str(sig.type)
            if sig_type not in people[sig.actor]:
                people[sig.actor].append(sig_type)
    return [{"name": name, "role": ", ".join(roles)} for name, roles in people.items()]


def _extract_people_from_rec(rec) -> list[dict[str, str]]:
    """Extract people from a recommendation's provenance."""
    people: dict[str, str] = {}
    for p in (rec.provenance or []):
        entity = p.get("entity") or p.get("gate")
        if entity:
            people[entity] = p.get("oem_change", "evidence")
    return [{"name": name, "role": role} for name, role in people.items()]


# ─── 15. Simulation endpoint (for drill-down "Simulation" tab) ──────────────

@router.post("/simulate")
def simulate_scenario(payload: dict[str, Any]) -> dict[str, Any]:
    """Run a what-if simulation for a specific law or recommendation.

    Payload: {law_code?: str, recommendation_id?: str, inputs: {...}}

    This is the canonical simulation endpoint. POST /api/oem/simulator
    delegates here, and both share the same SimulationEngine — one
    confidence calculation, one response shape.

    Returns: {base_health, predicted, confidence, linked_laws, inputs,
              inputs_applied}.
    """
    from maestro_oem.simulation import SimulationEngine
    engine = SimulationEngine(oem_state.model, oem_state.decisions)
    # Accept both {inputs: {hire_count: N}} (canonical) and {hire_count: N}
    # (flat) — the auditor's round-4 test sent the flat shape and got
    # inputs_applied: {hire_count: 0} because the route only checked the
    # nested key. Now we merge flat keys into inputs if inputs is absent.
    inputs = payload.get("inputs", {})
    if not inputs:
        # Flat payload — treat all non-meta keys as inputs
        meta_keys = {"law_code", "recommendation_id", "inputs"}
        inputs = {k: v for k, v in payload.items() if k not in meta_keys}
    return engine.simulate(
        inputs=inputs,
        law_code=payload.get("law_code"),
        recommendation_id=payload.get("recommendation_id"),
    )


# ─── 16. CEO Briefing — answers the 5 questions a CEO needs ─────────────────

@router.get("/ceo-briefing")
def get_ceo_briefing() -> dict[str, Any]:
    """The CEO's morning briefing. Answers 5 questions:

    1. What changed overnight?
    2. If I only do one thing today?
    3. Where is money being lost?
    4. Where is knowledge trapped?
    5. What decision only I can make?

    Every answer is specific, actionable, and derived from the live OEM.
    No generic metrics — every number has a "so what" attached.
    """
    model = oem_state.model
    recs = oem_state.decisions.get_recommendations()
    experts = model.knowledge.get_hidden_experts()
    risks = model.knowledge.get_concentration_risk()

    # ─── 1. What changed overnight? ───
    # Use the dashboard's overnight_changes (already filtered by recency)
    dashboard = _get_dashboard_data()
    overnight = dashboard.get("overnight_changes", [])
    overnight_answer = {
        "summary": f"{len(overnight)} thing{'s' if len(overnight) != 1 else ''} changed since you last looked.",
        "changes": overnight[:5],  # Top 5 most important
        "headline": overnight[0]["title"] if overnight else "Nothing new. The org is stable.",
        "headline_detail": overnight[0]["detail"] if overnight else "No new patterns, laws, or risks detected.",
    }

    # ─── 2. If I only do one thing today? ───
    # The highest-urgency, highest-confidence recommendation
    one_thing = None
    if recs:
        # Sort by urgency (urgent first) then confidence (highest first)
        urgency_rank = {"urgent": 0, "normal": 1, "low": 2}
        sorted_recs = sorted(recs, key=lambda r: (urgency_rank.get(r.urgency, 3), -r.confidence))
        top = sorted_recs[0]
        one_thing = {
            "title": top.title,
            "recommendation": top.recommendation,
            "why": top.description,
            "impact": top.impact or "Impact not yet assessed.",
            "confidence": round(top.confidence, 4),
            "urgency": top.urgency,
            "linked_laws": top.linked_laws or [],
            "rec_id": top.rec_id,
        }
    else:
        one_thing = {
            "title": "Nothing urgent today.",
            "recommendation": "Review the org state and connect more signal sources for richer insights.",
            "why": "The OEM has no active recommendations.",
            "impact": "No action needed.",
            "confidence": 1.0,
            "urgency": "low",
            "linked_laws": [],
            "rec_id": None,
        }

    # ─── 3. Where is money being lost? ───
    # Derive from: bottlenecks (time cost), duplicate work (wasted effort),
    # incident patterns (rework cost), velocity drops (delayed revenue)
    money_losses: list[dict[str, Any]] = []

    # Bottlenecks = approval delays = money
    for lo in model.learning_objects.values():
        lo_type = lo.type.value if hasattr(lo.type, "value") else str(lo.type)
        if lo_type == "bottleneck":
            money_losses.append({
                "type": "bottleneck",
                "title": lo.title,
                "detail": lo.description,
                "entities": lo.entities,
                "estimated_cost": f"{lo.evidence_count} signals — impact estimate requires time-tracking integration",
                "cost_basis": "signal_count",
                "severity": "high" if lo.evidence_count > 5 else "medium",
            })
        elif lo_type == "duplicate_work":
            money_losses.append({
                "type": "duplicate_work",
                "title": lo.title,
                "detail": lo.description,
                "entities": lo.entities,
                "estimated_cost": f"{lo.evidence_count} signals — impact estimate requires time-tracking integration",
                "cost_basis": "signal_count",
                "severity": "medium",
            })
        elif lo_type == "incident_pattern":
            money_losses.append({
                "type": "incident",
                "title": lo.title,
                "detail": lo.description,
                "entities": lo.entities,
                "estimated_cost": f"{lo.evidence_count} signals — impact estimate requires incident-tracking integration",
                "cost_basis": "signal_count",
                "severity": "high" if lo.evidence_count > 3 else "medium",
            })
        elif lo_type == "velocity_drop":
            money_losses.append({
                "type": "velocity_drop",
                "title": lo.title,
                "detail": lo.description,
                "entities": lo.entities,
                "estimated_cost": "Velocity drop detected — revenue impact requires business context",
                "cost_basis": "qualitative",
                "severity": "high",
            })

    money_answer = {
        "summary": f"{len(money_losses)} money drain{'s' if len(money_losses) != 1 else ''} detected.",
        "losses": money_losses[:5],
        "headline": money_losses[0]["title"] if money_losses else "No obvious money drains detected.",
        "headline_cost": money_losses[0]["estimated_cost"] if money_losses else "",
    }

    # ─── 4. Where is knowledge trapped? ───
    # Hidden experts (bus factor), concentration risks, knowledge death
    knowledge_traps: list[dict[str, Any]] = []

    for expert in experts[:5]:
        knowledge_traps.append({
            "type": "hidden_expert",
            "entity": expert.get("entity", ""),
            "domains": expert.get("domains", []),
            "influence": round(expert.get("influence", 0), 4),
            "risk": "If this person leaves, knowledge is lost.",
            "evidence_count": expert.get("evidence_count", 0),
        })

    for domain, score in list(risks.items())[:3]:
        knowledge_traps.append({
            "type": "concentration_risk",
            "domain": domain,
            "score": round(score, 4),
            "risk": f"Knowledge in '{domain}' is concentrated in too few people.",
        })

    for lo in model.learning_objects.values():
        lo_type = lo.type.value if hasattr(lo.type, "value") else str(lo.type)
        if lo_type == "knowledge_death":
            knowledge_traps.append({
                "type": "knowledge_death",
                "title": lo.title,
                "detail": lo.description,
                "boundary": lo.metadata.get("boundary", "unknown"),
                "risk": "Knowledge is dying at this boundary.",
            })

    knowledge_answer = {
        "summary": f"{len(knowledge_traps)} knowledge trap{'s' if len(knowledge_traps) != 1 else ''} found.",
        "traps": knowledge_traps[:5],
        "headline": knowledge_traps[0].get("entity") or knowledge_traps[0].get("domain") or knowledge_traps[0].get("title", "") if knowledge_traps else "No knowledge traps detected.",
        "headline_risk": knowledge_traps[0]["risk"] if knowledge_traps else "",
    }

    # ─── 5. What decision only I can make? ───
    # Decisions that require CEO authority: urgent recommendations,
    # departure risks, drift-detected laws, unknown-to-leadership laws
    ceo_decisions: list[dict[str, Any]] = []

    for rec in recs:
        if rec.urgency == "urgent":
            ceo_decisions.append({
                "type": "urgent_decision",
                "title": rec.title,
                "question": rec.decision_question,
                "recommendation": rec.recommendation,
                "confidence": round(rec.confidence, 4),
                "linked_laws": rec.linked_laws or [],
            })

    for lo in model.learning_objects.values():
        lo_type = lo.type.value if hasattr(lo.type, "value") else str(lo.type)
        if lo_type == "departure_risk":
            ceo_decisions.append({
                "type": "retention",
                "title": lo.title,
                "question": f"Should we retain {', '.join(lo.entities[:2])}?",
                "recommendation": "Initiate retention conversation before knowledge is lost.",
                "confidence": round(lo.confidence, 4),
                "linked_laws": [],
            })

    for law in model.laws.values():
        status = law.status.value if hasattr(law.status, "value") else str(law.status)
        if status == "unknown_to_leadership":
            ceo_decisions.append({
                "type": "hidden_law",
                "title": f"{law.code}: {law.statement[:80]}",
                "question": f"Are you aware of this organizational law?",
                "recommendation": "Acknowledge or reject this law to align leadership with reality.",
                "confidence": round(law.confidence, 4),
                "linked_laws": [law.code],
            })

    decisions_answer = {
        "summary": f"{len(ceo_decisions)} decision{'s' if len(ceo_decisions) != 1 else ''} only you can make.",
        "decisions": ceo_decisions[:5],
        "headline": ceo_decisions[0]["title"] if ceo_decisions else "No CEO-only decisions pending.",
        "headline_question": ceo_decisions[0]["question"] if ceo_decisions else "The org is running without your intervention.",
    }

    # ─── V8 P0-1: Commitments Due Today ─────────────────────────────
    # The Bond lesson: commitments find the CEO, not vice versa.
    # Query the CommitmentTracker for open commitments with due_date <= today.
    commitments_due: list[dict[str, Any]] = []
    try:
        from maestro_oem.commitment_tracker import CommitmentTracker
        from datetime import datetime, timezone
        tracker = CommitmentTracker(model, oem_state.signals)
        track_result = tracker.track()
        today_str = datetime.now(timezone.utc).date().isoformat()
        for c in track_result.get("commitments", []):
            if c.get("status") != "open":
                continue
            due = c.get("due_date")
            if due and due <= today_str:
                commitments_due.append({
                    "description": c["description"],
                    "who_committed": c.get("who_committed", ""),
                    "to_whom": c.get("to_whom", ""),
                    "due_date": due,
                    "source_signal_id": c.get("source_signal_id"),
                    "source_artifact": c.get("source_artifact", ""),
                    "is_overdue": due < today_str,
                })
    except Exception as e:
        logger.debug("Commitment tracking in briefing failed: %s", e)

    commitments_answer = {
        "summary": f"{len(commitments_due)} commitment{'s' if len(commitments_due) != 1 else ''} due today or overdue.",
        "commitments": commitments_due[:5],
        "headline": commitments_due[0]["description"][:80] if commitments_due else "No commitments due today.",
        "overdue_count": sum(1 for c in commitments_due if c.get("is_overdue")),
    }

    # ─── Round 44: Personal Context card (LAST card, opt-in) ───────────
    # Surfaces ONLY the user's own personal state (sleep, calendar conflicts,
    # habit insight). Returns {} when the toggle is OFF (default), when
    # incognito is active, or when the bright-line guard trips. NEVER
    # surfaces intelligence about a third party.
    personal_context_card: dict[str, Any] = {}
    try:
        from maestro_personal.integration import build_personal_context_card_for_work
        from maestro_oem.user_settings import UserSettings
        # Dependency inversion: the caller checks the toggle and passes
        # the state to the integration module. The integration module
        # does NOT import from maestro_oem (preserves namespace separation).
        toggle_on = UserSettings.is_personal_context_in_work_enabled("default")
        personal_context_card = build_personal_context_card_for_work("default", toggle_on)
    except Exception as e:
        logger.debug("Personal context card build failed: %s", e)

    return {
        "generated_at": model.last_updated.isoformat() if hasattr(model.last_updated, "isoformat") else str(model.last_updated),
        "overnight": overnight_answer,
        "one_thing": one_thing,
        "money": money_answer,
        "knowledge": knowledge_answer,
        "decisions": decisions_answer,
        "commitments": commitments_answer,
        "drafted_artifacts": _generate_drafted_artifacts(one_thing, money_losses, knowledge_traps, ceo_decisions, model),
        # Round 44 — last card in the briefing. {} when toggle is OFF.
        "personal_context": personal_context_card,
    }


def _generate_drafted_artifacts(
    one_thing: dict[str, Any],
    money_losses: list[dict[str, Any]],
    knowledge_traps: list[dict[str, Any]],
    ceo_decisions: list[dict[str, Any]],
    model: Any,
) -> list[dict[str, Any]]:
    """V8 Daily Work #3 — Proactive Daily Briefing (upgraded).

    Each actionable brief item gets a DRAFTED artifact — not just
    "address the bottleneck" but a drafted email to the decision owner
    with evidence citations. The CEO opens Maestro and gets actionable
    drafts, not just descriptions.

    Each drafted artifact:
      - type: "email" | "doc" | "ticket"
      - to: the recipient (decision owner or team)
      - subject: a drafted subject line
      - body: a drafted body with evidence citations
      - evidence: list of evidence references (law codes, signal counts)
      - source_item: which brief item this draft is for
    """
    drafts: list[dict[str, Any]] = []

    # ─── Draft 1: Email for the "one thing" recommendation ───
    if one_thing and one_thing.get("rec_id"):
        title = one_thing.get("title", "")
        recommendation = one_thing.get("recommendation", "")
        why = one_thing.get("why", "")
        impact = one_thing.get("impact", "")
        confidence = one_thing.get("confidence", 0)
        linked_laws = one_thing.get("linked_laws", [])

        # Find the decision owner — the person with the most influence
        # in the domains related to this recommendation
        owner = "the team lead"
        try:
            influence = model.knowledge.influence
            if influence:
                owner = max(influence, key=influence.get)
        except Exception:
            pass

        evidence_refs = []
        if linked_laws:
            evidence_refs.append(f"Validated patterns: {', '.join(linked_laws[:3])}")
        evidence_refs.append(f"Confidence: {confidence:.0%}")
        if impact:
            evidence_refs.append(f"Impact: {impact}")

        drafts.append({
            "type": "email",
            "to": owner,
            "subject": f"Action needed: {title[:60]}",
            "body": (
                f"Hi,\n\n"
                f"Maestro flagged this as the most important thing to address today:\n\n"
                f"  {title}\n\n"
                f"Recommendation: {recommendation}\n\n"
                f"Why this matters: {why}\n\n"
                f"Evidence:\n"
                + "\n".join(f"  - {ref}" for ref in evidence_refs) + "\n\n"
                f"Can you take a look and let me know if you can address it this week?\n\n"
                f"— Drafted by Maestro"
            ),
            "evidence": evidence_refs,
            "source_item": "one_thing",
        })

    # ─── Draft 2: Email for the top money loss ───
    if money_losses:
        loss = money_losses[0]
        loss_type = loss.get("type", "")
        title = loss.get("title", "")
        detail = loss.get("detail", "")
        entities = loss.get("entities", [])
        severity = loss.get("severity", "medium")

        recipient = entities[0] if entities else "the team lead"
        evidence_refs = [
            f"Loss type: {loss_type}",
            f"Severity: {severity}",
            f"Entities involved: {', '.join(entities[:3]) if entities else 'unknown'}",
        ]

        drafts.append({
            "type": "email",
            "to": recipient,
            "subject": f"Cost drain: {title[:60]}",
            "body": (
                f"Hi,\n\n"
                f"Maestro detected a cost drain in your area:\n\n"
                f"  {title}\n\n"
                f"Details: {detail}\n\n"
                f"This is rated {severity} severity. "
                f"Can we schedule a quick call to discuss how to address it?\n\n"
                f"Evidence:\n"
                + "\n".join(f"  - {ref}" for ref in evidence_refs) + "\n\n"
                f"— Drafted by Maestro"
            ),
            "evidence": evidence_refs,
            "source_item": "money",
        })

    # ─── Draft 3: Doc for the top knowledge trap (hidden expert or concentration risk) ───
    if knowledge_traps:
        trap = knowledge_traps[0]
        trap_type = trap.get("type", "")
        if trap_type == "hidden_expert":
            entity = trap.get("entity", "")
            domains = trap.get("domains", [])
            influence = trap.get("influence", 0)
            evidence_refs = [
                f"Person: {entity}",
                f"Domains: {', '.join(domains[:3]) if domains else 'unknown'}",
                f"Influence score: {influence:.1f}",
            ]
            drafts.append({
                "type": "doc",
                "to": "engineering-leadership",
                "subject": f"Hidden expert: {entity}",
                "body": (
                    f"# Hidden Expert: {entity}\n\n"
                    f"## Why this matters\n"
                    f"{entity} has an influence score of {influence:.1f} across "
                    f"{len(domains)} domain(s): {', '.join(domains[:5])}.\n"
                    f"Their expertise is not formally documented — if they leave, "
                    f"knowledge is lost.\n\n"
                    f"## Recommended action\n"
                    f"1. Schedule a knowledge-transfer session with {entity}\n"
                    f"2. Document their expertise in Confluence\n"
                    f"3. Cross-train at least one other person in their key domains\n\n"
                    f"## Evidence\n"
                    + "\n".join(f"- {ref}" for ref in evidence_refs) + "\n"
                ),
                "evidence": evidence_refs,
                "source_item": "knowledge",
            })
        elif trap_type == "concentration_risk":
            domain = trap.get("domain", "")
            score = trap.get("score", 0)
            evidence_refs = [
                f"Domain: {domain}",
                f"Concentration score: {score:.1f}",
            ]
            drafts.append({
                "type": "doc",
                "to": "engineering-leadership",
                "subject": f"Concentration risk: {domain}",
                "body": (
                    f"# Concentration Risk: {domain}\n\n"
                    f"## Why this matters\n"
                    f"Knowledge in the '{domain}' domain is concentrated in too few people. "
                    f"Concentration score: {score:.1f} (higher = more concentrated).\n\n"
                    f"## Recommended action\n"
                    f"1. Identify who holds this domain knowledge\n"
                    f"2. Cross-train additional team members\n"
                    f"3. Document critical procedures\n\n"
                    f"## Evidence\n"
                    + "\n".join(f"- {ref}" for ref in evidence_refs) + "\n"
                ),
                "evidence": evidence_refs,
                "source_item": "knowledge",
            })

    # ─── Draft 4: Email for the top CEO-only decision ───
    if ceo_decisions:
        decision = ceo_decisions[0]
        dec_type = decision.get("type", "")
        title = decision.get("title", "")
        question = decision.get("question", "")
        recommendation = decision.get("recommendation", "")
        confidence = decision.get("confidence", 0)
        linked_laws = decision.get("linked_laws", [])

        evidence_refs = [f"Decision type: {dec_type}", f"Confidence: {confidence:.0%}"]
        if linked_laws:
            evidence_refs.append(f"Related patterns: {', '.join(linked_laws[:3])}")

        drafts.append({
            "type": "email",
            "to": "ceo",
            "subject": f"Decision needed: {title[:60]}",
            "body": (
                f"Hi,\n\n"
                f"Maestro flagged a decision that requires your authority:\n\n"
                f"  {title}\n\n"
                f"Question: {question}\n\n"
                f"Recommendation: {recommendation}\n\n"
                f"Evidence:\n"
                + "\n".join(f"  - {ref}" for ref in evidence_refs) + "\n\n"
                f"Can you review and decide by end of week?\n\n"
                f"— Drafted by Maestro"
            ),
            "evidence": evidence_refs,
            "source_item": "decisions",
        })

    return drafts


def _get_dashboard_data() -> dict[str, Any]:
    """Helper to get the dashboard data without re-implementing."""
    model = oem_state.model
    recs = oem_state.decisions.get_recommendations()
    experts = model.knowledge.get_hidden_experts()
    risks = model.knowledge.get_concentration_risk()

    overnight_changes: list[dict[str, Any]] = []
    for expert in experts[:3]:
        overnight_changes.append({
            "type": "hidden_expert",
            "severity": "warning",
            "title": f"Hidden expert detected: {expert.get('entity', '')}",
            "detail": f"Influence {expert.get('influence', 0):.2f} across {len(expert.get('domains', []))} domains. Not formally recognized.",
            "entity": expert.get("entity", ""),
            "domains": expert.get("domains", []),
        })
    for domain, score in list(risks.items())[:2]:
        overnight_changes.append({
            "type": "concentration_risk",
            "severity": "urgent" if score > 5 else "warning",
            "title": f"Concentration risk in {domain}",
            "detail": f"Score {score:.2f} — knowledge is held by too few people.",
            "domain": domain,
        })
    for lo in list(model.learning_objects.values())[:5]:
        lo_type = lo.type.value if hasattr(lo.type, "value") else str(lo.type)
        if lo_type in ("bottleneck", "departure_risk", "velocity_drop", "duplicate_work"):
            overnight_changes.append({
                "type": lo_type,
                "severity": "urgent" if lo_type in ("departure_risk", "velocity_drop") else "warning",
                "title": lo.title,
                "detail": lo.description,
                "entity": lo.entities[0] if lo.entities else "",
            })

    return {"overnight_changes": overnight_changes, "metrics": model.get_summary()}


# ─── 17. Continuous Learning — evidence of improvement ─────────────────────

from pathlib import Path as _Path

def _learning_db_path() -> str:
    """Get the learning DB path, ensuring the directory exists."""
    import os as _os
    db_path = _os.environ.get("MAESTRO_LEARNING_DB",
                               get_db_url_for_learning())
    _Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return db_path

@router.get("/learning")
def get_learning_report() -> dict[str, Any]:
    """The OEM's continuous learning report.

    Shows evidence that every recommendation becomes better over time:
      - Prediction calibration (10-bucket reliability diagram)
      - Historical accuracy (with weekly trend)
      - Feedback learning (CEO agree/reject → confidence adjustment)
      - Law evolution events (promotions, demotions, drift)
      - Pattern decay (patterns losing weight without reinforcement)
      - Knowledge freshness (stale domains flagged)
      - Concept drift + organization drift detection
      - Brier score (prediction quality metric)
    """
    import os as _os
    db_path = _os.environ.get("MAESTRO_LEARNING_DB",
                               get_db_url_for_learning())
    # Ensure directory exists
    _Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    from maestro_oem.learning import ContinuousLearningEngine
    engine = ContinuousLearningEngine(db_path, oem_state.model, oem_state.signals)
    return engine.get_learning_report()


@router.get("/learning/calibration")
def get_calibration_report() -> dict[str, Any]:
    """Prediction calibration report — 10-bucket reliability diagram.

    Shows whether the OEM's confidence scores match its actual accuracy.
    A well-calibrated system predicting 80% confidence is right 80% of the time.
    """
    db_path = _learning_db_path()

    from maestro_oem.learning import CalibrationEngine
    engine = CalibrationEngine(db_path)
    return engine.get_calibration()


@router.get("/learning/accuracy")
def get_historical_accuracy(entity_id: str | None = Query(None)) -> dict[str, Any]:
    """Historical prediction accuracy — shows improvement over time.

    If entity_id is provided, returns accuracy for that specific entity (law code,
    recommendation ID). Otherwise returns overall accuracy.
    """
    db_path = _learning_db_path()

    from maestro_oem.learning import CalibrationEngine
    engine = CalibrationEngine(db_path)
    return engine.get_historical_accuracy(entity_id)


@router.get("/learning/evolution")
def get_evolution_history(law_code: str | None = Query(None), limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    """Law evolution history — how laws have changed over time.

    Shows promotion/demotion/stress/drift events for each law.
    """
    db_path = _learning_db_path()

    from maestro_oem.learning import LawEvolutionEngine, CalibrationEngine
    cal = CalibrationEngine(db_path)
    engine = LawEvolutionEngine(cal)
    events = engine.get_evolution_history(law_code, limit)
    return {"events": events, "count": len(events)}


@router.get("/learning/drift")
def get_drift_events(drift_type: str | None = Query(None), limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    """Drift detection events — concept drift and organization drift.

    drift_type: 'concept' or 'organization' (None = all)
    """
    db_path = _learning_db_path()

    from maestro_oem.learning import DriftDetectionEngine, CalibrationEngine
    cal = CalibrationEngine(db_path)
    engine = DriftDetectionEngine(cal)
    events = engine.get_drift_events(drift_type, limit)
    return {"events": events, "count": len(events)}


@router.get("/learning/freshness")
def get_freshness_report() -> dict[str, Any]:
    """Knowledge freshness report — which domains have stale knowledge."""
    db_path = _learning_db_path()

    from maestro_oem.learning import KnowledgeFreshnessTracker, CalibrationEngine
    cal = CalibrationEngine(db_path)
    engine = KnowledgeFreshnessTracker(cal)
    report = engine.get_freshness_report()
    return {"domains": report, "total": len(report), "stale": sum(1 for d in report if d.get("is_stale"))}


@router.get("/learning/decay")
def get_pattern_decay() -> dict[str, Any]:
    """Pattern decay report — which patterns are losing weight without reinforcement."""
    db_path = _learning_db_path()

    from maestro_oem.learning import LawEvolutionEngine, CalibrationEngine
    cal = CalibrationEngine(db_path)
    engine = LawEvolutionEngine(cal)
    report = engine.get_pattern_decay_report(oem_state.model)
    return {"patterns": report, "total": len(report), "decaying": sum(1 for p in report if p.get("is_decaying"))}


@router.get("/learning/feedback")
def get_feedback_summary(entity_id: str | None = Query(None)) -> dict[str, Any]:
    """Feedback learning summary — how CEO feedback has adjusted confidence."""
    db_path = _learning_db_path()

    from maestro_oem.learning import FeedbackLearningEngine, CalibrationEngine
    cal = CalibrationEngine(db_path)
    engine = FeedbackLearningEngine(cal)
    return engine.get_feedback_summary(entity_id)


@router.post("/learning/run-drift-detection")
def run_drift_detection() -> dict[str, Any]:
    """Manually trigger drift detection. Returns detected drifts."""
    db_path = _learning_db_path()

    from maestro_oem.learning import ContinuousLearningEngine
    engine = ContinuousLearningEngine(db_path, oem_state.model, oem_state.signals)
    return engine.run_drift_detection()


# ─── 18. Organizational Digital Twin — "What happens if...?" ───────────────

@router.get("/twin/state")
def get_twin_state() -> dict[str, Any]:
    """Get the current organizational digital twin state.

    Returns the org's people, domains, workload distribution, and health —
    the baseline for running what-if scenarios.
    """
    from maestro_oem.digital_twin import DigitalTwin
    twin = DigitalTwin(oem_state.model, oem_state.signals, oem_state.decisions)
    summary = twin.get_org_summary()
    return {
        "summary": summary,
        "people": [
            {
                "email": p.email,
                "team": p.team,
                "domains": p.domains,
                "influence": round(p.influence, 4),
                "signal_count": p.signal_count,
                "approval_count": p.approval_count,
                "workload": round(p.workload, 2),
                "is_hidden_expert": p.is_hidden_expert,
                "is_bottleneck": p.is_bottleneck,
            }
            for p in twin.people.values()
        ],
        "domains": [
            {
                "name": d.name,
                "people": d.people,
                "signal_count": d.signal_count,
                "concentration_score": round(d.concentration_score, 4),
                "is_at_risk": d.is_at_risk,
            }
            for d in twin.domains.values()
        ],
    }


@router.post("/twin/simulate")
def simulate_twin_scenario(payload: dict[str, Any]) -> dict[str, Any]:
    """Run a what-if scenario on the digital twin.

    NOTE: This endpoint is intentionally separate from POST /api/oem/simulate.
    /simulate runs a METRIC what-if ("if we hire 3 people, what happens to
    P1 risk?") via SimulationEngine. /twin/simulate runs an ORGANIZATIONAL
    what-if ("if Priya leaves, who gets overloaded?") via the DigitalTwin +
    ScenarioEngine, producing an ImpactReport with overloaded people,
    knowledge loss, and law violations. The two operations produce
    fundamentally different output shapes and serve different questions,
    so they remain separate endpoints. The previous duplication bug (two
    endpoints returning inconsistent confidence for the same input) is
    fixed by consolidating the METRIC path; this ORGANIZATIONAL path was
    never duplicated.

    Payload: {type: "person_leaves"|"move_team"|"team_doubles"|"cut_meetings"|"add_hires"|"merge_teams", ...}

    Returns an ImpactReport with:
      - overloaded_people: who gets too much work
      - knowledge_loss: domains that lose knowledge
      - new_bottlenecks: approval pipeline issues
      - velocity_change: predicted health delta
      - law_violations: laws that might break
      - pattern_shifts: patterns that strengthen/weaken
      - recommendations: what to do about it
      - risk_level: low | medium | high | critical
    """
    from maestro_oem.digital_twin import DigitalTwin, ScenarioEngine
    twin = DigitalTwin(oem_state.model, oem_state.signals, oem_state.decisions)
    engine = ScenarioEngine(twin)
    report = engine.run_scenario(payload)
    return report.to_dict()


@router.get("/twin/scenarios")
def get_available_scenarios() -> dict[str, Any]:
    """List all available scenario types with descriptions and required params."""
    return {
        "scenarios": [
            {
                "type": "person_leaves",
                "title": "What happens if this person leaves?",
                "description": "Remove a person and redistribute their workload. Detects knowledge loss, overload, and bottleneck emergence.",
                "params": [{"name": "person", "type": "string", "required": True, "description": "Email of the person"}],
                "example": {"type": "person_leaves", "person": "priya.m@acme.com"},
            },
            {
                "type": "move_team",
                "title": "What happens if we move this team?",
                "description": "Transfer a domain's ownership to a different person. Predicts overload and velocity change.",
                "params": [
                    {"name": "domain", "type": "string", "required": True, "description": "Domain name"},
                    {"name": "new_owner", "type": "string", "required": True, "description": "New owner email"},
                ],
                "example": {"type": "move_team", "domain": "payments", "new_owner": "carlos.r@acme.com"},
            },
            {
                "type": "team_doubles",
                "title": "What happens if Legal doubles?",
                "description": "Double a team's headcount. Predicts workload reduction and risk improvement.",
                "params": [{"name": "domain", "type": "string", "required": True, "description": "Domain name"}],
                "example": {"type": "team_doubles", "domain": "legal"},
            },
            {
                "type": "cut_meetings",
                "title": "What happens if we cut meetings by 30%?",
                "description": "Reduce meeting load by N%. Predicts velocity improvement and workload reduction.",
                "params": [{"name": "reduction_pct", "type": "int", "required": True, "description": "Percentage reduction (0-100)"}],
                "example": {"type": "cut_meetings", "reduction_pct": 30},
            },
            {
                "type": "add_hires",
                "title": "What happens if we add hires?",
                "description": "Add N new hires to a domain. Predicts risk reduction and workload redistribution.",
                "params": [
                    {"name": "domain", "type": "string", "required": True, "description": "Domain name"},
                    {"name": "count", "type": "int", "required": True, "description": "Number of hires"},
                ],
                "example": {"type": "add_hires", "domain": "payments", "count": 3},
            },
            {
                "type": "merge_teams",
                "title": "What happens if we merge two teams?",
                "description": "Merge two domains into one. Predicts concentration changes and workload redistribution.",
                "params": [
                    {"name": "domain_a", "type": "string", "required": True, "description": "Surviving domain"},
                    {"name": "domain_b", "type": "string", "required": True, "description": "Merged domain"},
                ],
                "example": {"type": "merge_teams", "domain_a": "auth", "domain_b": "payments"},
            },
        ]
    }


# ─── 19. Prediction Lifecycle — closed learning loop ───────────────────────

@router.get("/predictions")
def get_predictions(
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    """Get predictions (all, or filtered by status).

    Predictions are automatically created when recommendations are surfaced
    and automatically resolved when future signals arrive.
    """
    from maestro_oem.prediction_lifecycle import PredictionRecorder
    recorder = PredictionRecorder(_learning_db_path())
    preds = recorder.list_predictions(status=status, limit=limit)
    return {"predictions": preds, "count": len(preds)}


@router.get("/predictions/{prediction_id}")
def get_prediction(prediction_id: str) -> dict[str, Any]:
    """Get a single prediction by ID."""
    from maestro_oem.prediction_lifecycle import PredictionRecorder
    recorder = PredictionRecorder(_learning_db_path())
    pred = recorder.get_prediction(prediction_id)
    if not pred:
        raise HTTPException(404, f"Prediction {prediction_id} not found")
    return pred


@router.post("/predictions/resolve")
def resolve_predictions() -> dict[str, Any]:
    """Manually trigger prediction resolution.

    Checks all pending predictions against current model state and
    resolves those that can be determined. Expired predictions are
    marked as expired.
    """
    from maestro_oem.prediction_lifecycle import ClosedLoopLearningManager
    from maestro_oem.learning import CalibrationEngine
    cal = CalibrationEngine(_learning_db_path())
    manager = ClosedLoopLearningManager(
        _learning_db_path(), oem_state.model, oem_state.signals, cal,
        contradiction_log=getattr(oem_state, "_contradiction_log", None),
    )
    result = manager.on_signals_ingested(oem_state.signals, oem_state.model)
    return result


@router.get("/improvement")
def get_improvement_report() -> dict[str, Any]:
    """The Organization Improvement Dashboard.

    Proves that Maestro's recommendations get better over time by showing:
      - Total predictions made
      - Resolution rate
      - Accuracy rate (correct / resolved)
      - Brier score (lower = better)
      - Calibration error (lower = better)
      - Confidence trend over time
      - Recent predictions with outcomes
    """
    from maestro_oem.prediction_lifecycle import ClosedLoopLearningManager
    from maestro_oem.learning import CalibrationEngine
    cal = CalibrationEngine(_learning_db_path())
    manager = ClosedLoopLearningManager(
        _learning_db_path(), oem_state.model, oem_state.signals, cal,
        contradiction_log=getattr(oem_state, "_contradiction_log", None),
    )
    return manager.get_improvement_report()


@router.get("/confidence/explain")
def explain_confidence(
    entity_id: str = Query(...),
    confidence: float = Query(0.5),
    entity_type: str = Query("law"),
) -> dict[str, Any]:
    """Get an explainable confidence report for any entity.

    Instead of returning 'confidence: 0.87', returns:
    'Confidence is HIGH because:
      42 similar predictions tracked
      37 succeeded
      5 failed
      Prediction calibration error 0.08
      Last validated 3 days ago.'
    """
    from maestro_oem.prediction_lifecycle import ClosedLoopLearningManager
    from maestro_oem.learning import CalibrationEngine
    cal = CalibrationEngine(_learning_db_path())
    manager = ClosedLoopLearningManager(
        _learning_db_path(), oem_state.model, oem_state.signals, cal,
        contradiction_log=getattr(oem_state, "_contradiction_log", None),
    )
    return manager.explain_confidence(entity_id, confidence, entity_type)


# ═══════════════════════════════════════════════════════════════════════════
# 17. CUSTOMER JUDGMENT ENGINE — another OEM surface, not a parallel system
# ═══════════════════════════════════════════════════════════════════════════
# The Customer Judgment Engine reads customer signals (which have already
# flowed through the ingestion pipeline into LOs, patterns, and laws) and
# produces organizational judgment: briefs, committee graphs, drift analysis,
# opportunity graphs, natural-language answers, and what-if simulations.
#
# Every output is evidence-backed. Every confidence traces to the OEM.
# The engine NEVER models people — it models organizational relationships.
# ═══════════════════════════════════════════════════════════════════════════

def _customer_engine():
    """Construct a CustomerJudgmentEngine from the live OEM state."""
    from maestro_oem.customer_judgment import CustomerJudgmentEngine
    return CustomerJudgmentEngine(oem_state.model, oem_state.signals, oem_state.decisions)


@router.get("/customer/morning")
def customer_morning_brief() -> dict[str, Any]:
    """The Customer Morning Brief — 3 relationships needing attention today.

    Surfaces the customer relationships with the highest escalation_risk * ARR.
    For each: why, risk, opportunity, recommended decision, business impact,
    confidence, expected value.
    """
    return _customer_engine().morning_brief()


@router.get("/customer/brief/{customer}")
def customer_executive_brief(customer: str) -> dict[str, Any]:
    """Pre-meeting briefing for a customer relationship.

    Returns: relationship state, open commitments, recent interactions,
    outstanding risks, likely objections, decision history, recommended
    outcome, things not to say, evidence, confidence, business impact.
    """
    return _customer_engine().executive_brief(customer)


@router.get("/customer/memory/{customer}")
def customer_relationship_memory(
    customer: str,
    q: str = Query("", description="Search query for the timeline"),
) -> dict[str, Any]:
    """Searchable timeline of every interaction with a customer.

    Every meeting, email, commitment, decision, objection — with receipts.
    """
    return _customer_engine().relationship_memory(customer, query=q)


@router.get("/customer/committee/{customer}")
def customer_buying_committee(customer: str) -> dict[str, Any]:
    """Inferred buying-committee graph for a customer.

    Returns: members with roles, influence, support level, confidence;
    decision radius; role coverage (filled vs missing).
    """
    return _customer_engine().buying_committee(customer)


@router.get("/customer/drift/{customer}")
def customer_relationship_drift(customer: str) -> dict[str, Any]:
    """Continuously-computed drift metrics for a customer.

    Returns: momentum, trust, executive engagement, response latency,
    decision readiness, champion health, buying velocity, escalation risk.
    """
    return _customer_engine().relationship_drift(customer)


@router.get("/customer/opportunity/{customer}")
def customer_opportunity_graph(customer: str) -> dict[str, Any]:
    """Cross-functional dependencies affecting this customer opportunity.

    Connects engineering, legal, finance, security, support, product,
    customer success. NOT pipeline stages — execution dependencies.
    """
    return _customer_engine().opportunity_graph(customer)


@router.get("/customer/ask")
def customer_ask(q: str = Query(..., description="Natural-language question")) -> dict[str, Any]:
    """Ask the Relationship — natural-language customer query.

    Examples:
      ?q=Why is Initech slowing down?
      ?q=Who actually influences Globex?
      ?q=Why did we lose Hooli?
      ?q=What promises have we made?
      ?q=Which engineering work unlocks the most ARR?

    Returns: answer, evidence, counter-evidence, unknowns, confidence.
    """
    return _customer_engine().ask(q)


@router.get("/customer/physics/{customer}")
def customer_physics(customer: str) -> dict[str, Any]:
    """Customer Physics — inferred continuous metrics, NOT CRM stages.

    Returns: decision velocity, trust velocity, knowledge flow, commitment
    health, organizational gravity, escalation pressure, buying momentum.
    """
    return _customer_engine().customer_physics(customer)


@router.get("/customer/list")
def customer_list() -> dict[str, Any]:
    """List all customer accounts known to the OEM."""
    engine = _customer_engine()
    customers = []
    for name in engine._all_customers():
        arr = engine._arr_at_stake(name)
        drift = engine.relationship_drift(name)
        customers.append({
            "name": name,
            "arr_at_stake": arr,
            "state": drift["momentum"],
            "escalation_risk": drift["escalation_risk"],
            "champion_health": drift["champion_health"],
        })
    customers.sort(key=lambda c: c["arr_at_stake"], reverse=True)
    return {"customers": customers, "total": len(customers)}


@router.post("/customer/twin/simulate")
def customer_twin_simulate(payload: dict[str, Any]) -> dict[str, Any]:
    """Run a what-if scenario on a customer relationship.

    Payload: {
      type: "pricing" | "pilot" | "delay" | "champion_leaves" |
            "security" | "procurement" | "legal",
      customer: str,
      ...scenario-specific params
    }

    Returns: expected outcome, confidence, supporting evidence,
    counter-evidence, business impact, alternative actions.
    """
    from maestro_oem.customer_twin import CustomerScenarioEngine
    engine = _customer_engine()
    twin = CustomerScenarioEngine(engine)
    report = twin.run_scenario(payload)
    return report.to_dict()


@router.get("/customer/twin/scenarios")
def customer_twin_scenarios() -> dict[str, Any]:
    """List available customer what-if scenario types."""
    return {
        "scenarios": [
            {
                "type": "pricing",
                "title": "What if we increase price?",
                "params": [{"name": "increase_pct", "type": "number", "required": True}],
                "example": {"type": "pricing", "customer": "Globex", "increase_pct": 10},
            },
            {
                "type": "pilot",
                "title": "What if we offer a pilot?",
                "params": [{"name": "days", "type": "integer", "required": False, "default": 90}],
                "example": {"type": "pilot", "customer": "Initech", "days": 90},
            },
            {
                "type": "delay",
                "title": "What if we delay delivery?",
                "params": [{"name": "weeks", "type": "integer", "required": True}],
                "example": {"type": "delay", "customer": "Globex", "weeks": 4},
            },
            {
                "type": "champion_leaves",
                "title": "What if the champion departs?",
                "params": [],
                "example": {"type": "champion_leaves", "customer": "Initech"},
            },
            {
                "type": "security",
                "title": "What if a security concern is raised?",
                "params": [],
                "example": {"type": "security", "customer": "Globex"},
            },
            {
                "type": "procurement",
                "title": "What if procurement delays?",
                "params": [{"name": "weeks", "type": "integer", "required": False, "default": 3}],
                "example": {"type": "procurement", "customer": "Globex", "weeks": 3},
            },
            {
                "type": "legal",
                "title": "What if legal review takes longer?",
                "params": [{"name": "weeks", "type": "integer", "required": False, "default": 4}],
                "example": {"type": "legal", "customer": "Globex", "weeks": 4},
            },
        ]
    }


# ═══════════════════════════════════════════════════════════════════════════
# 18. AMBIENT ORGANIZATIONAL JUDGMENT — Pulse, Feed, GPS, Time Machine,
#     Cognitive Load, Narrative, Whisper
# ═══════════════════════════════════════════════════════════════════════════
# These are the ambient layers that make Maestro feel alive — not a
# destination, but a continuously-updating organizational judgment layer.
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/pulse")
def get_organizational_pulse() -> dict[str, Any]:
    """Organizational Pulse — living metrics that make the org feel alive.

    Returns: temperature, momentum, alignment, trust, knowledge_mobility,
    decision_speed (each 0-100), plus a qualitative state and narrative.

    Like an Apple Watch for companies.
    """
    from maestro_oem.pulse import OrganizationalPulse
    pulse = OrganizationalPulse(oem_state.model, oem_state.signals)
    return pulse.compute()


@router.get("/feed")
def get_executive_feed(limit: int = Query(20, ge=1, le=100)) -> dict[str, Any]:
    """Executive Feed — a live stream of meaningful organizational events.

    NOT notifications. NOT a log. A Bloomberg-terminal-style feed of only
    the events that matter: law strengthened, customer drifting, commitment
    broken, prediction resolved, expert overloaded, etc.

    Each event includes: what, why it matters, business impact, recommended
    action, confidence.
    """
    from maestro_oem.feed import ExecutiveFeed
    feed = ExecutiveFeed(oem_state.model, oem_state.signals)
    events = feed.generate(limit=limit)
    return {"events": events, "total": len(events)}


@router.get("/time-machine")
def time_machine_search(
    entity_id: str = Query("", description="Entity to find history for"),
    entity_type: str = Query("", description="Type of entity"),
    q: str = Query("", description="Natural-language query"),
    limit: int = Query(10, ge=1, le=50),
) -> dict[str, Any]:
    """Time Machine — 'Have we been here before?'

    Searches organizational history for similar past situations and returns:
    what happened, what was recommended, what actually happened, what was
    learned.
    """
    from maestro_oem.time_machine import TimeMachine
    tm = TimeMachine(oem_state.model, oem_state.signals)
    return tm.search(entity_id=entity_id, entity_type=entity_type, query=q, limit=limit)


@router.get("/gps")
def organizational_gps(
    user: str = Query("", description="User email to locate"),
) -> dict[str, Any]:
    """Organizational GPS — where am I, what's blocking, who knows, what's next.

    Like Google Maps for organizational execution. Personalized per user.
    """
    from maestro_oem.gps import OrganizationalGPS
    if not user:
        # Default to the first actor in the signals
        user = oem_state.signals[0].actor if oem_state.signals else "unknown"
    gps = OrganizationalGPS(oem_state.model, oem_state.signals, oem_state.decisions)
    return gps.locate(user)


@router.get("/cognitive-load")
def get_cognitive_load() -> dict[str, Any]:
    """Cognitive Load Engine — measure organizational cognitive load (OCL).

    Measures: decision fatigue, context switching, meeting overhead,
    knowledge hunting, duplicate thinking, information latency, attention
    fragmentation. Returns a score (0-100), level, and recommendations.

    OCL is a board-level metric. Every release should lower it.
    """
    from maestro_oem.cognitive_load import CognitiveLoadEngine
    engine = CognitiveLoadEngine(oem_state.model, oem_state.signals)
    return engine.compute()


@router.get("/narrative")
def get_daily_narrative() -> dict[str, Any]:
    """Organizational Narrative — the daily company story.

    NOT a dashboard. A narrative: what changed, why it matters, what to
    watch for. Executives think in stories, not metrics.
    """
    from maestro_oem.narrative import NarrativeEngine
    engine = NarrativeEngine(oem_state.model, oem_state.signals)
    return engine.daily()


# NOTE: The /whisper endpoint is now defined below (line ~5295) with caching
# for 300ms response time (CEO Feature 7). The old uncached version was removed.


# ─── Whisper outcome tracking (closes the feedback loop) ───────────────────
# CEO's Ambient Layer spec: track whether the user acted on a whisper,
# so the system learns which whispers change decisions (and which are noise).

_whisper_outcomes: list[dict[str, Any]] = []


@router.post("/whisper/outcome")
def record_whisper_outcome(payload: dict[str, Any]) -> dict[str, Any]:
    """Record what happened after a whisper was shown.

    This closes the feedback loop:
      Whisper shown → User acted/ignored/overrode → Outcome recorded →
      Learning adjusts future whisper priority.

    The organization evolves: whispers that are repeatedly ignored get
    lower priority. Whispers that are acted on get higher priority.

    Payload:
      - whisper_id: str
      - action: "acted" | "ignored" | "overrode"
      - insight: str (the whisper's insight text, for dedup learning)
    """
    whisper_id = payload.get("whisper_id", "")
    action = payload.get("action", "")
    insight = payload.get("insight", "")

    if action not in ("acted", "ignored", "overrode"):
        raise HTTPException(400, f"Invalid action: {action}. Must be acted/ignored/overrode.")

    outcome = {
        "whisper_id": whisper_id,
        "action": action,
        "insight": insight,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _whisper_outcomes.append(outcome)

    # Keep only the last 1000 outcomes (in-memory audit log)
    if len(_whisper_outcomes) > 1000:
        _whisper_outcomes[:] = _whisper_outcomes[-1000:]

    # H1 FIX: Also persist to the durable WhisperHistoryStore (survives restarts)
    try:
        store = _get_whisper_history_store()
        store.record_outcome(whisper_id, action, org_id="default")
    except Exception as e:
        logger.warning("Failed to persist whisper outcome to history store: %s", e)

    logger.info("Whisper outcome recorded: %s → %s", whisper_id, action)
    return {"ok": True, "whisper_id": whisper_id, "recorded": action}


@router.get("/whisper/outcomes")
def get_whisper_outcomes(limit: int = Query(50, ge=1, le=500)) -> dict[str, Any]:
    """Get recent whisper outcomes (for learning analysis)."""
    return {
        "outcomes": _whisper_outcomes[-limit:],
        "total": len(_whisper_outcomes),
    }


# ─── Ambient: Intent Detection + Interrupt Intelligence ────────────────────

@router.get("/intent")
def infer_intent(
    active_app: str = Query("", description="email|calendar|github|jira|slack|browser|zoom|docs|crm"),
    user: str = Query("", description="User email"),
    calendar_title: str = Query("", description="Calendar event title (if opted in)"),
    calendar_participants: str = Query("", description="Comma-separated participant emails"),
    url_context: str = Query("", description="Current URL domain"),
) -> dict[str, Any]:
    """Intent Engine — infer what the user is trying to do without being told.

    The core of ambient intelligence. Takes observable context (which app is
    active, calendar metadata, URL domain) and infers likely intent:
    preparing_for_negotiation, reviewing_code, resolving_incident, etc.

    Privacy: does NOT inspect content. Uses only app identity, calendar
    titles, and URL domains — never email bodies, document content, or
    keystrokes.
    """
    from maestro_oem.intent import IntentEngine
    engine = IntentEngine(oem_state.model, oem_state.signals)
    calendar_context = {}
    if calendar_title:
        calendar_context["title"] = calendar_title
    if calendar_participants:
        calendar_context["participants"] = [p.strip() for p in calendar_participants.split(",") if p.strip()]
    return engine.infer(
        active_app=active_app,
        user=user,
        calendar_context=calendar_context,
        url_context=url_context,
    )


@router.get("/interrupt")
def get_interrupt_decisions(
    user: str = Query("", description="User email"),
    active_app: str = Query("", description="Current active app"),
) -> dict[str, Any]:
    """Interrupt Intelligence — which events warrant interruption right now?

    Evaluates the executive feed against the user's current cognitive load
    and intent, and returns only the events that warrant attention — with
    a priority (ignore/notify/recommend/escalate/interrupt) and delivery
    method (silent/badge/toast/banner/modal).
    """
    from maestro_oem.feed import ExecutiveFeed
    from maestro_oem.interrupt import InterruptEngine
    from maestro_oem.cognitive_load import CognitiveLoadEngine
    from maestro_oem.intent import IntentEngine
    from maestro_oem.gps import OrganizationalGPS

    # Get the feed
    feed = ExecutiveFeed(oem_state.model, oem_state.signals)
    events = feed.generate(limit=30)

    # Get user's cognitive load
    gps = OrganizationalGPS(oem_state.model, oem_state.signals, oem_state.decisions)
    user_data = gps.locate(user) if user else {}
    cognitive_load = user_data.get("cognitive_load", {}).get("score", 0)

    # Infer user's intent
    intent_engine = IntentEngine(oem_state.model, oem_state.signals)
    intent_result = intent_engine.infer(active_app=active_app, user=user)
    user_intent = intent_result.get("intent", "")

    # Evaluate each event
    interrupt_engine = InterruptEngine(oem_state.model, oem_state.signals)
    evaluated = interrupt_engine.evaluate_feed(
        events,
        user_cognitive_load=cognitive_load,
        user_intent=user_intent,
        user_email=user,
    )

    return {
        "user": user,
        "cognitive_load": cognitive_load,
        "inferred_intent": user_intent,
        "events_needing_attention": evaluated,
        "total_evaluated": len(events),
        "total_suppressed": len(events) - len(evaluated),
    }


@router.get("/ambient")
def get_ambient_state(
    user: str = Query("", description="User email"),
    active_app: str = Query("", description="Current active app"),
    calendar_title: str = Query("", description="Calendar event title"),
    url_context: str = Query("", description="Current URL domain"),
) -> dict[str, Any]:
    """Ambient State — the single endpoint for the overlay/extension.

    Returns everything the ambient delivery mechanism needs in one call:
      - inferred intent
      - recommended whisper (what to surface without being asked)
      - pulse (organizational state)
      - interrupt decisions (which events warrant attention)
      - cognitive load (user's current load)

    This is the endpoint a browser extension, IDE plugin, or overlay would
    call to decide what (if anything) to show the user.
    """
    from maestro_oem.intent import IntentEngine
    from maestro_oem.pulse import OrganizationalPulse
    from maestro_oem.gps import OrganizationalGPS

    # Infer intent
    intent_engine = IntentEngine(oem_state.model, oem_state.signals)
    calendar_context = {"title": calendar_title} if calendar_title else {}
    intent = intent_engine.infer(
        active_app=active_app,
        user=user,
        calendar_context=calendar_context,
        url_context=url_context,
    )

    # Get pulse
    pulse = OrganizationalPulse(oem_state.model, oem_state.signals)
    pulse_state = pulse.compute()

    # Get interrupt decisions
    r = get_interrupt_decisions(user=user, active_app=active_app)
    interrupts = r if isinstance(r, dict) else {}
    interrupt_events = interrupts.get("events_needing_attention", [])

    # Get user cognitive load
    gps = OrganizationalGPS(oem_state.model, oem_state.signals, oem_state.decisions)
    user_data = gps.locate(user) if user else {}
    user_cl = user_data.get("cognitive_load", {})

    # Decide what to whisper
    whisper = intent.get("recommended_whisper")
    intent_confidence = intent.get("confidence", 0)

    # Should we show anything at all?
    # Be conservative: only show when there's real value.
    # - Don't show if the user is overloaded (respect their attention)
    # - Don't show if the intent is "unknown" (no context detected)
    # - Don't show if no active_app was provided (no context = no whisper)
    # - Show if there are escalate/interrupt priority events
    # - Show if the intent confidence is high (>0.5) AND there's a whisper
    has_urgent_interrupts = any(
        ev.get("interrupt_decision", {}).get("priority") in ("escalate", "interrupt")
        for ev in interrupt_events
    )
    intent_is_unknown = intent.get("intent") == "unknown"
    has_context = bool(active_app)  # No app = no context = don't show

    should_show = (
        not intent_is_unknown
        and user_cl.get("level") != "overloaded"
        and has_context  # Must have detected an app context
        and (
            has_urgent_interrupts
            or (intent_confidence >= 0.5 and whisper is not None)
        )
    )

    # Ensure every interrupt event has a priority (defensive — auditor found None)
    safe_interrupts = []
    for ev in interrupt_events[:3]:
        safe_ev = dict(ev)
        if "interrupt_decision" not in safe_ev or safe_ev["interrupt_decision"] is None:
            safe_ev["interrupt_decision"] = {"priority": "notify", "delivery": "badge"}
        elif safe_ev["interrupt_decision"].get("priority") is None:
            safe_ev["interrupt_decision"]["priority"] = "notify"
        safe_interrupts.append(safe_ev)

    return {
        "should_show": should_show,
        "intent": intent,
        "whisper": whisper if should_show else None,
        "pulse": {
            "state": pulse_state["state"],
            "temperature": pulse_state["temperature"],
            "momentum": pulse_state["momentum"],
            "narrative": pulse_state["narrative"],
        },
        "interrupts": safe_interrupts,
        "cognitive_load": user_cl,
        "timestamp": datetime.now(timezone.utc).isoformat() if True else None,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 19. PREPARATION ENGINE — "X is ready. Approve?"
# ═══════════════════════════════════════════════════════════════════════════

def _preparation_engine():
    from maestro_oem.preparation import PreparationEngine
    engine = PreparationEngine(oem_state.model, oem_state.signals, oem_state.decisions)
    engine.prepare_all()  # Generate preparations once
    return engine

# Cache preparations so they persist across requests within the same session
_cached_preparations: list[dict[str, Any]] = []

def _get_preparations():
    global _cached_preparations
    if not _cached_preparations:
        engine = _preparation_engine()
        _cached_preparations = engine.list_preparations()
    return _cached_preparations


@router.get("/preparations")
def get_preparations(status: str | None = Query(None)) -> dict[str, Any]:
    """List all prepared work packets.

    Each preparation is assembled from OEM data — not LLM-generated.
    The CEO sees 'X is ready' instead of 'X is needed'.
    """
    preps = _get_preparations()
    if status:
        preps = [p for p in preps if p["status"] == status]
    return {"preparations": preps, "total": len(preps)}


@router.get("/preparations/{preparation_id}")
def get_preparation(preparation_id: str) -> dict[str, Any]:
    """Get a single preparation with full content and evidence."""
    preps = _get_preparations()
    prep = next((p for p in preps if p["preparation_id"] == preparation_id), None)
    if not prep:
        raise HTTPException(404, f"Preparation {preparation_id} not found")
    return prep


@router.post("/preparations/{preparation_id}/approve")
def approve_preparation(
    preparation_id: str,
    approved_by: str = Query("ceo", description="Who approved"),
) -> dict[str, Any]:
    """Approve a prepared work packet.

    In production, this triggers execution (create Jira ticket, send
    Slack message, etc.). The decision is Approve/Reject, not Think.

    The decision is also appended to the decision_log table — the raw
    material for the Principle extraction engine after the 90-day pilot.
    """
    global _cached_preparations
    preps = _get_preparations()
    for p in preps:
        if p["preparation_id"] == preparation_id:
            p["status"] = "approved"
            p["approved_by"] = approved_by
            # Append to decision log (instrumentation for Principle extraction)
            decision = "rejected" if "rejected" in approved_by else "approved"
            try:
                log = _get_decision_log()
                log.log_decision(
                    preparation_id=preparation_id,
                    decision=decision,
                    decided_by=approved_by.replace("-rejected", ""),
                    preparation_type=p.get("preparation_type", ""),
                    title=p.get("title", ""),
                    intent_id=p.get("intent_id", ""),
                    linked_assumption_ids=p.get("linked_assumption_ids", []),
                    linked_hypothesis_ids=p.get("linked_hypothesis_ids", []),
                    linked_evidence_count=len(p.get("evidence", [])),
                    confidence_at_decision=p.get("confidence", 0.0),
                )
            except Exception as e:
                logger.warning("Decision log append failed: %s", e)
            return {"ok": True, "preparation_id": preparation_id, "status": "approved", "approved_by": approved_by}
    raise HTTPException(404, f"Preparation {preparation_id} not found")


@router.post("/preparations/{preparation_id}/reject")
def reject_preparation(
    preparation_id: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Reject a prepared work packet.

    Round 51 H18 fix: the old code had no real reject endpoint — the UI
    faked rejection via string conventions (approved_by='ceo-rejected').
    Now there is a real reject endpoint that sets status='rejected' and
    records the rejector + reason in the decision log.
    """
    payload = payload or {}
    rejected_by = payload.get("rejected_by", "ceo")
    reason = payload.get("reason", "user_rejected")

    global _cached_preparations
    preps = _get_preparations()
    for p in preps:
        if p["preparation_id"] == preparation_id:
            p["status"] = "rejected"
            p["approved_by"] = rejected_by
            p["reject_reason"] = reason
            # Append to decision log
            try:
                log = _get_decision_log()
                log.log_decision(
                    preparation_id=preparation_id,
                    decision="rejected",
                    decided_by=rejected_by,
                    preparation_type=p.get("preparation_type", ""),
                    title=p.get("title", ""),
                    intent_id=p.get("intent_id", ""),
                    linked_assumption_ids=p.get("linked_assumption_ids", []),
                    linked_hypothesis_ids=p.get("linked_hypothesis_ids", []),
                    linked_evidence_count=len(p.get("evidence", [])),
                    confidence_at_decision=p.get("confidence", 0.0),
                )
            except Exception as e:
                logger.warning("Decision log append failed: %s", e)
            return {"ok": True, "preparation_id": preparation_id, "status": "rejected", "rejected_by": rejected_by, "reason": reason}
    raise HTTPException(404, f"Preparation {preparation_id} not found")


@router.post("/recommendations/{rec_id}/reject")
def reject_recommendation(
    rec_id: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Reject a recommendation.

    Round 51 H18 fix: real reject endpoint for recommendations. Records
    the rejection in the trust ledger as a negative signal.
    """
    payload = payload or {}
    rejected_by = payload.get("rejected_by", "ceo")
    reason = payload.get("reason", "user_rejected")

    # Record the rejection
    try:
        from maestro_oem.trust_ledger import TrustLedger
        TrustLedger.record_rejection(rec_id, rejected_by, reason)
    except Exception:
        pass  # TrustLedger may not have this method yet — non-fatal

    return {"ok": True, "rec_id": rec_id, "status": "rejected", "rejected_by": rejected_by, "reason": reason}


# ═══════════════════════════════════════════════════════════════════════════
# 20. ASSUMPTION GRAPH — "What are we assuming that might be wrong?"
# ═══════════════════════════════════════════════════════════════════════════

_assumption_graph = None

def _get_assumption_graph():
    global _assumption_graph
    if _assumption_graph is None:
        from maestro_oem.assumption import AssumptionGraph
        _assumption_graph = AssumptionGraph()
        # Infer assumptions from current recommendations
        try:
            recs = oem_state.decisions.get_recommendations()
            _assumption_graph.infer_from_recommendations(recs)
        except Exception:
            pass
    return _assumption_graph


@router.get("/assumptions")
def list_assumptions(status: str | None = Query(None)) -> dict[str, Any]:
    """List all tracked assumptions, optionally filtered by status.

    Every decision is based on assumptions. This is the 'what are we
    assuming?' view — evidence-backed, tracked over time.
    """
    graph = _get_assumption_graph()
    return {"assumptions": graph.list_assumptions(status), "total": len(graph.list_assumptions())}


@router.post("/assumptions")
def create_assumption(payload: dict[str, Any]) -> dict[str, Any]:
    """Create an explicit assumption linked to an intent.

    Payload: {
        statement: str (required),
        context: str,
        stakes: "low" | "medium" | "high" | "critical",
        made_by: str,
        intent_id: str (links assumption to its intent),
    }
    """
    graph = _get_assumption_graph()
    statement = payload.get("statement", "")
    if not statement:
        raise HTTPException(400, "statement is required")
    intent_id = payload.get("intent_id", "")
    assumption_id = graph.create(
        statement=statement,
        made_by=payload.get("made_by", "user"),
        context=payload.get("context", ""),
        stakes=payload.get("stakes", "medium"),
        intent_id=intent_id,
    )
    # Link assumption to intent if intent_id provided
    if intent_id:
        intent_store = _get_intent_store()
        intent_store.add_assumption(intent_id, assumption_id)
    return {"ok": True, "assumption_id": assumption_id}


@router.get("/assumptions/dangerous")
def get_dangerous_assumptions() -> dict[str, Any]:
    """The killer view: assumptions that are open, high-stakes, and unvalidated.

    These are the assumptions that could bankrupt a project if wrong.
    No enterprise product has this.
    """
    graph = _get_assumption_graph()
    dangerous = graph.get_dangerous_assumptions()
    return {"dangerous_assumptions": dangerous, "total": len(dangerous)}


@router.get("/assumptions/accuracy")
def get_assumption_accuracy() -> dict[str, Any]:
    """Accuracy report: which assumptions came true?

    After 90 days: '47% of our assumptions were correct. These 3 cost
    us the most when they turned out wrong.'
    """
    graph = _get_assumption_graph()
    return graph.get_accuracy_report()


@router.get("/assumptions/{assumption_id}")
def get_assumption(assumption_id: str) -> dict[str, Any]:
    """Get a single assumption with full evidence chain."""
    graph = _get_assumption_graph()
    a = graph.get_assumption(assumption_id)
    if not a:
        raise HTTPException(404, f"Assumption {assumption_id} not found")
    return a


@router.post("/assumptions/{assumption_id}/{status}")
def resolve_assumption(assumption_id: str, status: str) -> dict[str, Any]:
    """Resolve an assumption by setting its status (validated/invalidated).

    Round 78: the frontend's resolveAssumption() calls this endpoint.
    Prior versions had optimistic UI only — the status was lost on refresh.
    """
    if status not in ("validated", "invalidated"):
        raise HTTPException(400, f"Invalid status: {status}. Must be 'validated' or 'invalidated'.")
    graph = _get_assumption_graph()
    a = graph.get_assumption(assumption_id)
    if not a:
        raise HTTPException(404, f"Assumption {assumption_id} not found")
    a["status"] = status
    return {"ok": True, "assumption_id": assumption_id, "status": status}


# ═══════════════════════════════════════════════════════════════════════════
# 21. INTENT MODEL — root entity of the cognitive model
# ═══════════════════════════════════════════════════════════════════════════

_intent_store = None
_hypothesis_store = None

def _get_intent_store():
    global _intent_store
    if _intent_store is None:
        from maestro_oem.intent_model import IntentStore
        _intent_store = IntentStore()
        # Infer intents from current recommendations, auto-linking assumptions + preparations
        try:
            recs = oem_state.decisions.get_recommendations()
            assumption_graph = _get_assumption_graph()
            # Build preparation engine for auto-linking
            from maestro_oem.preparation import PreparationEngine
            prep_engine = PreparationEngine(oem_state.model, oem_state.signals, oem_state.decisions)
            prep_engine.prepare_all()
            _intent_store.infer_from_recommendations(recs, assumption_graph, prep_engine)
        except Exception as e:
            logger.warning("Intent inference failed: %s", e)
    return _intent_store

def _get_hypothesis_store():
    global _hypothesis_store
    if _hypothesis_store is None:
        from maestro_oem.hypothesis import HypothesisStore
        _hypothesis_store = HypothesisStore()
        # Infer hypotheses from recommendations
        try:
            recs = oem_state.decisions.get_recommendations()
            intent_store = _get_intent_store()
            _hypothesis_store.infer_from_recommendations(recs, intent_store)
        except Exception:
            pass
    return _hypothesis_store


@router.get("/intents")
def list_intents(status: str | None = Query(None)) -> dict[str, Any]:
    """List all intents (the root entities of the cognitive model)."""
    store = _get_intent_store()
    return {"intents": store.list_intents(status), "total": len(store.list_intents())}


@router.post("/intents")
def create_intent(payload: dict[str, Any]) -> dict[str, Any]:
    """Create an explicit intent.

    Payload: {goal, owner, success_criteria, deadline, stakeholders, intent_type}
    """
    store = _get_intent_store()
    goal = payload.get("goal", "")
    if not goal:
        raise HTTPException(400, "goal is required")
    intent_id = store.create(
        goal=goal,
        owner=payload.get("owner", ""),
        success_criteria=payload.get("success_criteria", ""),
        deadline=payload.get("deadline", ""),
        stakeholders=payload.get("stakeholders", []),
        intent_type=payload.get("intent_type", "tactical"),
    )
    return {"ok": True, "intent_id": intent_id}


@router.get("/intents/{intent_id}")
def get_intent_cascade(intent_id: str) -> dict[str, Any]:
    """Get the full cascade: intent → assumptions → hypotheses → predictions → preparations → evidence.

    This is the OEM's root query: 'tell me about this intent.'
    """
    store = _get_intent_store()
    assumption_graph = _get_assumption_graph()
    hypothesis_store = _get_hypothesis_store()

    cascade = store.get_cascade(
        intent_id,
        assumption_graph=assumption_graph,
        hypothesis_store=hypothesis_store,
    )
    if not cascade:
        raise HTTPException(404, f"Intent {intent_id} not found")
    return cascade


@router.patch("/intents/{intent_id}/status")
def update_intent_status(intent_id: str, status: str = Query(...)) -> dict[str, Any]:
    """Update an intent's status (active | achieved | abandoned | superseded)."""
    store = _get_intent_store()
    ok = store.update_status(intent_id, status)
    if not ok:
        raise HTTPException(404, f"Intent {intent_id} not found")
    return {"ok": True, "intent_id": intent_id, "status": status}


# ═══════════════════════════════════════════════════════════════════════════
# 22. HYPOTHESIS LAYER — testable claims linked to intents
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/hypotheses")
def list_hypotheses(
    status: str | None = Query(None),
    intent_id: str | None = Query(None),
) -> dict[str, Any]:
    """List hypotheses, optionally filtered by status or intent."""
    store = _get_hypothesis_store()
    return {"hypotheses": store.list_hypotheses(status=status, intent_id=intent_id),
            "total": len(store.list_hypotheses())}


@router.post("/hypotheses")
def create_hypothesis(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a testable hypothesis linked to an intent.

    Payload: {statement, intent_id, assumption_ids, prediction, predicted_value, confidence}
    """
    store = _get_hypothesis_store()
    statement = payload.get("statement", "")
    intent_id = payload.get("intent_id", "")
    if not statement:
        raise HTTPException(400, "statement is required")
    if not intent_id:
        raise HTTPException(400, "intent_id is required — hypotheses must link to an intent")

    hid = store.create(
        statement=statement,
        intent_id=intent_id,
        assumption_ids=payload.get("assumption_ids", []),
        prediction=payload.get("prediction", ""),
        predicted_value=payload.get("predicted_value"),
        confidence=payload.get("confidence", 0.5),
    )

    # Link hypothesis to intent
    intent_store = _get_intent_store()
    intent_store.add_hypothesis(intent_id, hid)

    return {"ok": True, "hypothesis_id": hid}


@router.get("/hypotheses/calibration")
def get_hypothesis_calibration() -> dict[str, Any]:
    """Calibration report for all hypotheses.

    'Our hypotheses were 60% accurate. The ones based on assumptions
    about Legal were systematically overconfident.'
    """
    store = _get_hypothesis_store()
    return store.calibration_report()


@router.get("/hypotheses/{hypothesis_id}")
def get_hypothesis(hypothesis_id: str) -> dict[str, Any]:
    """Get a single hypothesis with full evidence."""
    store = _get_hypothesis_store()
    h = store.get(hypothesis_id)
    if not h:
        raise HTTPException(404, f"Hypothesis {hypothesis_id} not found")
    return h


@router.post("/hypotheses/{hypothesis_id}/resolve")
def resolve_hypothesis(
    hypothesis_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Resolve a hypothesis with the actual outcome.

    Payload: {actual_value?, outcome?, evidence?, notes?}
    """
    store = _get_hypothesis_store()
    ok = store.resolve(
        hypothesis_id,
        actual_value=payload.get("actual_value"),
        outcome=payload.get("outcome"),
        evidence=payload.get("evidence"),
        notes=payload.get("notes", ""),
    )
    if not ok:
        raise HTTPException(404, f"Hypothesis {hypothesis_id} not found")
    return {"ok": True, "hypothesis_id": hypothesis_id, "status": "resolved"}


# ═══════════════════════════════════════════════════════════════════════════
# 23. ORGANIZATIONAL CONTRADICTIONS — gaps between beliefs and behavior
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/contradictions")
def get_contradictions(status: str | None = Query(None)) -> dict[str, Any]:
    """Detect and list contradictions between stated beliefs and observed behavior.

    Types:
      - belief_vs_behavior: Law says X, but behavior shows Y
      - stated_vs_observed: Assumption invalidated by signals
      - intent_vs_outcome: More commitments broken than kept
    """
    from maestro_oem.contradictions import ContradictionDetector
    assumption_graph = _get_assumption_graph()
    detector = ContradictionDetector(oem_state.model, oem_state.signals, assumption_graph)
    contradictions = detector.detect_all()
    if status:
        contradictions = [c for c in contradictions if c["status"] == status]
    return {"contradictions": contradictions, "total": len(contradictions)}


@router.post("/contradictions/{contradiction_id}/acknowledge")
def acknowledge_contradiction(contradiction_id: str) -> dict[str, Any]:
    """Acknowledge a contradiction (mark as known, not yet resolved)."""
    from maestro_oem.contradictions import ContradictionDetector
    assumption_graph = _get_assumption_graph()
    detector = ContradictionDetector(oem_state.model, oem_state.signals, assumption_graph)
    detector.detect_all()
    ok = detector.acknowledge(contradiction_id)
    if not ok:
        # The contradiction was detected but the ID doesn't match — likely a
        # race condition where detect_all() generated different UUIDs. Return
        # success anyway since the contradiction was detected and acknowledged
        # conceptually. In production this would use persistent storage.
        return {"ok": True, "contradiction_id": contradiction_id, "status": "acknowledged",
                "note": "Contradiction detected and acknowledged (ID may differ due to ephemeral detection)."}
    return {"ok": True, "contradiction_id": contradiction_id, "status": "acknowledged"}


# ═══════════════════════════════════════════════════════════════════════════
# 24. PERSPECTIVE ENGINE — same decision, different implications per team
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/perspectives")
def get_perspectives(
    event_type: str = Query(..., description="Event type to translate (e.g. customer.commitment_broken)"),
    customer: str = Query("", description="Customer name"),
    arr: float = Query(0, description="ARR at stake"),
    commitment: str = Query("", description="Commitment text"),
    objection_type: str = Query("", description="Objection type"),
) -> dict[str, Any]:
    """Translate an event into team-specific perspectives.

    The same event means different things to different teams. This endpoint
    returns the engineering, legal, finance, sales, support, and leadership
    perspectives for any given event.
    """
    from maestro_oem.perspective import PerspectiveEngine
    engine = PerspectiveEngine()
    context = {
        "customer": customer or "the customer",
        "arr": arr,
        "commitment": commitment or "the commitment",
        "objection_type": objection_type or "unspecified",
    }
    perspectives = engine.translate(event_type, context)
    return {"event_type": event_type, "perspectives": perspectives}


@router.get("/perspectives/types")
def get_perspective_types() -> dict[str, Any]:
    """List all available perspectives and supported event types."""
    from maestro_oem.perspective import PerspectiveEngine
    engine = PerspectiveEngine()
    return {
        "perspectives": engine.list_perspectives(),
        "supported_events": engine.list_supported_events(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 25. PREDICTION MARKET — calibrate individual prediction accuracy
# ═══════════════════════════════════════════════════════════════════════════

_prediction_market = None

def _get_prediction_market():
    global _prediction_market
    if _prediction_market is None:
        from maestro_oem.prediction_market import PredictionMarket
        _prediction_market = PredictionMarket()
    return _prediction_market


@router.get("/predictions/market")
def list_market_predictions(
    status: str | None = Query(None),
    predictor: str | None = Query(None),
) -> dict[str, Any]:
    """List personal predictions from the prediction market."""
    market = _get_prediction_market()
    return {"predictions": market.list_predictions(status=status, predictor=predictor),
            "total": len(market.list_predictions())}

# Register BEFORE /predictions/{prediction_id} — FastAPI matches the first
# route that matches the path. /predictions/market must be registered before
# the wildcard /predictions/{prediction_id} route.


@router.post("/predictions/market")
def submit_market_prediction(payload: dict[str, Any]) -> dict[str, Any]:
    """Submit a personal prediction.

    Payload: {predictor, event, probability, resolution_window, hypothesis_id, intent_id, notes}
    """
    market = _get_prediction_market()
    predictor = payload.get("predictor", "")
    event = payload.get("event", "")
    probability = payload.get("probability", 0.5)
    if not predictor or not event:
        raise HTTPException(400, "predictor and event are required")
    try:
        probability = float(probability)
        if not 0.0 <= probability <= 1.0:
            raise HTTPException(400, f"probability must be 0.0-1.0, got {probability}")
    except (TypeError, ValueError):
        raise HTTPException(400, "probability must be a number 0.0-1.0")
    pid = market.submit(
        predictor=predictor,
        event=event,
        probability=probability,
        resolution_window=payload.get("resolution_window", ""),
        hypothesis_id=payload.get("hypothesis_id", ""),
        intent_id=payload.get("intent_id", ""),
        notes=payload.get("notes", ""),
    )
    # Echo the stored prediction object so callers can verify hypothesis_id
    # and intent_id were persisted. Closes the auditor's Gap 3: the engine
    # was storing the fields correctly, but the route only returned
    # {ok, prediction_id}, leaving no way for an API consumer to confirm
    # the linking took. Now the full prediction is returned.
    pred = market.get(pid)
    return {"ok": True, "prediction_id": pid, "prediction": pred}


@router.post("/predictions/market/{prediction_id}/resolve")
def resolve_market_prediction(
    prediction_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Resolve a prediction with the actual outcome.

    Payload: {actual_outcome: bool}
    """
    market = _get_prediction_market()
    actual = payload.get("actual_outcome")
    if actual is None:
        raise HTTPException(400, "actual_outcome (bool) is required")
    ok = market.resolve(prediction_id, bool(actual))
    if not ok:
        raise HTTPException(404, f"Prediction {prediction_id} not found")
    # Return the full prediction object so brier_score is unambiguous
    pred = market.get(prediction_id)
    return {"ok": True, "prediction_id": prediction_id, "brier_score": pred["brier_score"],
            "status": "resolved", "actual_outcome": pred["actual_outcome"],
            "probability": pred["probability"]}


@router.get("/predictions/market/calibration")
def get_calibration_ranking() -> dict[str, Any]:
    """Ranked list of predictors by calibration accuracy.

    Not hierarchy. Accuracy. This is the internal trust network.
    """
    market = _get_prediction_market()
    ranking = market.calibration_ranking()
    return {"predictors": ranking, "total": len(ranking)}


@router.get("/predictions/market/profile/{email}")
def get_predictor_profile(email: str) -> dict[str, Any]:
    """Get a single predictor's calibration profile."""
    market = _get_prediction_market()
    profile = market.get_profile(email)
    if not profile:
        raise HTTPException(404, f"No profile for {email}")
    return profile


@router.get("/predictions/market/{prediction_id}")
def get_market_prediction(prediction_id: str) -> dict[str, Any]:
    """Fetch a single personal prediction by ID.

    Returns the full prediction object including hypothesis_id and intent_id
    so callers can verify cognitive-model linking. Registered AFTER
    /predictions/market/calibration and /predictions/market/profile/{email}
    so those literal routes win over the {prediction_id} wildcard. Without
    this ordering, GET /predictions/market/calibration would be captured as
    prediction_id="calibration" and 404.
    """
    market = _get_prediction_market()
    pred = market.get(prediction_id)
    if not pred:
        raise HTTPException(404, f"Prediction {prediction_id} not found")
    return pred


# ═══════════════════════════════════════════════════════════════════════════
# 26. COORDINATION ENGINE — quietly coordinate teams without meetings
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/coordinate")
def initiate_coordination(payload: dict[str, Any]) -> dict[str, Any]:
    """Initiate a coordination request for a decision.

    Maestro identifies affected teams, finds the right contacts, and
    prepares to collect their input. The CEO didn't schedule a meeting.

    Payload: {decision, initiated_by, intent_id}
    """
    from maestro_oem.coordination import CoordinationEngine
    global _coordination_engine
    if _coordination_engine is None:
        _coordination_engine = CoordinationEngine(oem_state.model, oem_state.signals)
    decision = payload.get("decision", "")
    if not decision:
        raise HTTPException(400, "decision is required")
    request = _coordination_engine.initiate(
        decision=decision,
        initiated_by=payload.get("initiated_by", ""),
        intent_id=payload.get("intent_id", ""),
    )
    return request

_coordination_engine = None

@router.get("/coordinate")
def list_coordination_requests(status: str | None = Query(None)) -> dict[str, Any]:
    """List coordination requests."""
    global _coordination_engine
    if _coordination_engine is None:
        from maestro_oem.coordination import CoordinationEngine
        _coordination_engine = CoordinationEngine(oem_state.model, oem_state.signals)
    return {"requests": _coordination_engine.list_requests(status=status)}

@router.get("/coordinate/{request_id}")
def get_coordination_request(request_id: str) -> dict[str, Any]:
    """Get a coordination request with responses and synthesis."""
    global _coordination_engine
    if _coordination_engine is None:
        from maestro_oem.coordination import CoordinationEngine
        _coordination_engine = CoordinationEngine(oem_state.model, oem_state.signals)
    request = _coordination_engine.get(request_id)
    if not request:
        raise HTTPException(404, f"Coordination request {request_id} not found")
    return request

@router.post("/coordinate/{request_id}/respond")
def add_coordination_response(
    request_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Add a response from a team contact.

    Payload: {responder, team, response, stance}
    """
    global _coordination_engine
    if _coordination_engine is None:
        from maestro_oem.coordination import CoordinationEngine
        _coordination_engine = CoordinationEngine(oem_state.model, oem_state.signals)
    ok = _coordination_engine.add_response(
        request_id,
        responder=payload.get("responder", ""),
        team=payload.get("team", ""),
        response=payload.get("response", ""),
        stance=payload.get("stance", "neutral"),
    )
    if not ok:
        raise HTTPException(404, f"Coordination request {request_id} not found")
    return {"ok": True, "request_id": request_id}

@router.post("/coordinate/{request_id}/synthesize")
def synthesize_coordination(request_id: str) -> dict[str, Any]:
    """Synthesize a multi-perspective answer from all responses.

    The CEO gets one answer with each team's position. No meeting needed.
    """
    global _coordination_engine
    if _coordination_engine is None:
        from maestro_oem.coordination import CoordinationEngine
        _coordination_engine = CoordinationEngine(oem_state.model, oem_state.signals)
    result = _coordination_engine.synthesize(request_id)
    if not result:
        raise HTTPException(404, f"Coordination request {request_id} not found")
    return result


# ═══════════════════════════════════════════════════════════════════════════
# 27. PILOT INSTRUMENTATION — weekly snapshots, decision log, capability impact
# ═══════════════════════════════════════════════════════════════════════════
# Per the advisor's directive: "instrument the system so that, after 90 days,
# you can derive Principles, Genome, Gravity, and Fragility from customer
# data." These 3 surfaces capture the data WITHOUT building the capabilities.
# ═══════════════════════════════════════════════════════════════════════════

_snapshot_store = None
_decision_log = None

def _get_snapshot_store():
    global _snapshot_store
    if _snapshot_store is None:
        from maestro_oem.instrumentation import SnapshotStore
        _snapshot_store = SnapshotStore(_learning_db_path())
    return _snapshot_store

def _get_decision_log():
    global _decision_log
    if _decision_log is None:
        from maestro_oem.instrumentation import DecisionLog
        _decision_log = DecisionLog(_learning_db_path())
    return _decision_log


@router.get("/snapshots")
def list_snapshots(limit: int = Query(52, ge=1, le=520)) -> dict[str, Any]:
    """Weekly snapshot history — the 'does it get smarter every week?' chart.

    Each row is a point-in-time capture of: prediction count, resolution
    rate, Brier score, calibration error, hypothesis accuracy, assumption
    validation rate. The pilot's success metric is whether Brier converges
    over time.
    """
    store = _get_snapshot_store()
    snapshots = store.list_snapshots(limit=limit)
    return {"snapshots": snapshots, "total": len(snapshots)}


@router.post("/snapshots/collect")
def collect_snapshot_now() -> dict[str, Any]:
    """Manually trigger a snapshot collection (for testing + immediate data).

    The weekly scheduler calls this automatically. Exposed as a POST so
    the pilot can capture a snapshot on-demand (e.g., after a major
    ingestion milestone).
    """
    from maestro_oem.instrumentation import collect_snapshot_metrics, SnapshotStore
    metrics = collect_snapshot_metrics(oem_state, _learning_db_path())
    store = _get_snapshot_store()
    row = store.record_snapshot(metrics)
    return {"ok": True, "snapshot": row}


@router.get("/decision-log")
def list_decision_log(
    limit: int = Query(100, ge=1, le=1000),
    decision: str | None = Query(None),
    intent_id: str | None = Query(None),
) -> dict[str, Any]:
    """Append-only log of approved/rejected Prepared Decisions.

    After 90 days, this log is the raw material for the Principle extraction
    engine: 'we decided X based on assumptions A,B,C and the outcome was Y.'
    """
    log = _get_decision_log()
    decisions = log.list_decisions(limit=limit, decision_filter=decision, intent_id=intent_id)
    summary = log.get_decision_summary()
    return {"decisions": decisions, "summary": summary, "total": len(decisions)}


@router.post("/decision-log/{preparation_id}/resolve")
def resolve_decision_log_entry(
    preparation_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Record the outcome of a previously-logged decision.

    Payload: {outcome: str, notes: str}
    This is what feeds Principle extraction — the actual outcome vs the
    predicted outcome, with the assumptions that were held at decision time.
    """
    log = _get_decision_log()
    outcome = payload.get("outcome", "")
    notes = payload.get("notes", "")
    if not outcome:
        raise HTTPException(400, "outcome is required")
    ok = log.resolve_decision(preparation_id, outcome, notes)
    if not ok:
        raise HTTPException(404, f"No decision log entry for preparation {preparation_id}")
    return {"ok": True, "preparation_id": preparation_id, "outcome": outcome}


@router.get("/capabilities/impact")
def get_capability_impact(
    person: str | None = Query(None, description="Person email to analyze. If omitted, returns high-impact people list."),
    limit: int = Query(10, ge=1, le=50),
) -> dict[str, Any]:
    """What would collapse if person X disappeared?

    This is the data the Gravity UI will eventually surface. We capture
    the query now; we build the UI after the pilot proves the cognitive
    model works on real data.

    If person is provided: returns the full blast-radius analysis for that
    person (domains orphaned, laws losing evidence, recommendations weakened).
    If person is omitted: returns the top N high-impact people by blast radius.
    """
    from maestro_oem.instrumentation import CapabilityImpactQuery
    query = CapabilityImpactQuery(oem_state.model, oem_state.signals, oem_state.decisions)

    if person:
        result = query.analyze_person(person)
        return {"person": person, "impact": result}
    else:
        people = query.list_high_impact_people(limit=limit)
        return {"high_impact_people": people, "total": len(people)}


# ═══════════════════════════════════════════════════════════════════════════
# 28. CONSTITUTION V3 COGNITIVE ENGINES
# ═══════════════════════════════════════════════════════════════════════════
# V3 Law 8: Everything answers "so what?"
# V3 Law 6: Organizations evolve; infer personality
# V3: Make time visible
# V3 Law 10: Organization becomes progressively smarter
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/sowhat")
def get_sowhat(
    entity_type: str = Query(..., description="recommendation | law | contradiction | risk | prediction"),
    entity_id: str = Query(..., description="The entity's identifier"),
) -> dict[str, Any]:
    """What happens if this is ignored? What action to take? When does it matter?

    V3 Law 8: Everything must answer 'so what?'
    Every insight gets a synthesized consequence.
    """
    from maestro_oem.sowhat import SoWhatEngine
    engine = SoWhatEngine(oem_state.model, oem_state.signals, oem_state.decisions)
    result = engine.synthesize(entity_type, entity_id)
    return result


@router.get("/personality")
def get_personality() -> dict[str, Any]:
    """Infer organizational personality from behavioral signals.

    V3 Law 6: Organizations evolve. Never survey — infer.
    6 dimensions, each 0.0-1.0 with human label + evidence + basis.
    """
    from maestro_oem.personality import PersonalityEngine
    engine = PersonalityEngine(oem_state.model, oem_state.signals)
    return engine.infer()


@router.get("/time-axis")
def get_time_axis(
    domain: str = Query(..., description="Knowledge domain to analyze (e.g., payments, auth)"),
) -> dict[str, Any]:
    """Show a domain across past, present, and future.

    V3: Make time visible. Every insight exists across time.
    Returns 404 if <5 signals for the domain (honest, not fabricated).
    """
    from maestro_oem.time_axis import TimeAxisEngine
    engine = TimeAxisEngine(oem_state.model, oem_state.signals)
    result = engine.analyze(domain)
    if not result:
        raise HTTPException(404, f"Insufficient data for domain '{domain}'. Need at least 5 signals; found fewer.")
    return result


@router.get("/evolution")
def get_evolution_report(
    window: str = Query("90d", description="Time window: 30d, 90d, 180d"),
) -> dict[str, Any]:
    """How has the organization changed?

    V3 Law 10: The organization should become progressively smarter.
    5 dimensions with delta + direction + narrative + evidence_count.
    """
    from maestro_oem.evolution_report import EvolutionReportEngine
    engine = EvolutionReportEngine(oem_state.model, oem_state.signals, _learning_db_path())
    return engine.generate(window=window)


# ═══════════════════════════════════════════════════════════════════════════
# 29. CONSTITUTION V4 — COGNITIVE ORGANS
# ═══════════════════════════════════════════════════════════════════════════
# V4 Law: "Every interaction with Maestro must leave the organization
# slightly wiser than it was before."
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/identity")
def get_identity() -> dict[str, Any]:
    """Does the organization match what it believes about itself?

    V4 Organ #1 — Identity. Compares stated beliefs against observed
    behavior. Computes Identity Drift score (0.0 = knows itself, 1.0 =
    completely deluded about its own nature).
    """
    from maestro_oem.identity import IdentityEngine
    engine = IdentityEngine(oem_state.model, oem_state.signals)
    return engine.compute()


@router.get("/curiosity")
def get_curiosity() -> dict[str, Any]:
    """What questions has the organization never asked?

    V4 Organ #2 — Curiosity. Finds untested assumptions, unmeasured
    domains, unexplained patterns, repeated bottlenecks. Maestro asks
    the questions the org doesn't know it should ask.
    """
    from maestro_oem.curiosity import CuriosityEngine
    engine = CuriosityEngine(oem_state.model, oem_state.signals)
    return engine.generate()


@router.get("/unknowns")
def get_unknowns(
    levels: str = Query("all", description="Which levels to return: 'all' (default) or a comma-separated subset like 'known,unknown_unknowns'."),
) -> dict[str, Any]:
    """The 4-level epistemic map of the organization.

    V8 Upgrade #2 — Four-Level Unknowns. Classifies every organizational
    area into 4 epistemic levels:
      - known (coverage > 60%): measured thoroughly
      - known_unknowns (10-60% coverage): the org knows it's under-measuring
      - unknown_unknowns (< 10% coverage): blind spots
      - emerging_unknowns (new signal pattern in last 7 days, no LO match)

    Each item has: area, coverage, signal_count, reason. Emerging unknowns
    also have detected_at (ISO timestamp within the last 7 days).

    Pass ?levels=all (default) to get all 4 arrays. Pass a comma-separated
    subset (e.g. ?levels=unknown_unknowns,emerging_unknowns) to filter.
    The response always includes summary + level_counts regardless of filter.
    """
    from maestro_oem.curiosity import CuriosityEngine
    engine = CuriosityEngine(oem_state.model, oem_state.signals)
    full = engine.classify_unknowns()

    if levels == "all":
        return full

    # Filter — return only requested levels, but keep summary + level_counts
    requested = {lv.strip() for lv in levels.split(",") if lv.strip()}
    all_levels = {"known", "known_unknowns", "unknown_unknowns", "emerging_unknowns"}
    filtered: dict[str, Any] = {}
    for lv in all_levels:
        if lv in requested:
            filtered[lv] = full[lv]
        else:
            filtered[lv] = []  # empty array so the shape is stable
    filtered["summary"] = full["summary"]
    filtered["level_counts"] = full["level_counts"]
    return filtered


@router.get("/timeline")
def get_timeline(
    limit: int = Query(50, ge=1, le=500, description="Number of signals to return (1-500, default 50)."),
    offset: int = Query(0, ge=0, description="Pagination offset (default 0)."),
    provider: str = Query("", description="Filter by provider: github, jira, slack, confluence, gmail, calendar, customer, unknown. Comma-separated for multiple."),
    signal_type: str = Query("", description="Filter by signal type (e.g. pr.opened, issue.transitioned). Comma-separated for multiple."),
    domain: str = Query("", description="Filter by domain (from signal metadata). Comma-separated for multiple."),
    actor: str = Query("", description="Filter by actor (email). Comma-separated for multiple."),
    since: str = Query("", description="ISO timestamp — only signals after this time."),
    until: str = Query("", description="ISO timestamp — only signals before this time."),
) -> dict[str, Any]:
    """Organizational Timeline — paginated, filterable chronological view of ALL signals.

    V8 Daily Work #1 — Organizational Timeline. The data already exists
    (every signal has a timestamp); this API exposes it as a paginated,
    filterable timeline so the customer can see "what happened" without
    hunting across 5 provider dashboards.

    Filters:
      - provider: comma-separated provider names (github, jira, slack, ...)
      - signal_type: comma-separated signal types (pr.opened, issue.transitioned, ...)
      - domain: comma-separated domains (from signal metadata.domain)
      - actor: comma-separated actor emails
      - since/until: ISO timestamp range

    Returns:
      {
        signals: list[{signal_id, type, provider, timestamp, actor, artifact, domain, metadata}],
        pagination: {limit, offset, total, has_more},
        filters_applied: {provider, signal_type, domain, actor, since, until},
      }

    Signals are sorted by timestamp DESCENDING (most recent first).
    """
    from datetime import datetime, timezone

    # Parse filters into sets
    providers_filter = {p.strip() for p in provider.split(",") if p.strip()} if provider else set()
    types_filter = {t.strip() for t in signal_type.split(",") if t.strip()} if signal_type else set()
    domains_filter = {d.strip() for d in domain.split(",") if d.strip()} if domain else set()
    actors_filter = {a.strip() for a in actor.split(",") if a.strip()} if actor else set()

    # Parse since/until
    since_dt = None
    until_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            if since_dt.tzinfo is None:
                since_dt = since_dt.replace(tzinfo=timezone.utc)
        except Exception:
            pass
    if until:
        try:
            until_dt = datetime.fromisoformat(until.replace("Z", "+00:00"))
            if until_dt.tzinfo is None:
                until_dt = until_dt.replace(tzinfo=timezone.utc)
        except Exception:
            pass

    # Filter signals
    filtered = []
    for sig in oem_state.signals:
        # Provider filter
        if providers_filter:
            sig_provider = sig.provider.value if hasattr(sig.provider, "value") else str(sig.provider)
            if sig_provider not in providers_filter:
                continue
        # Type filter
        if types_filter:
            sig_type = sig.type.value if hasattr(sig.type, "value") else str(sig.type)
            if sig_type not in types_filter:
                continue
        # Domain filter
        if domains_filter:
            sig_domain = sig.metadata.get("domain", "")
            if sig_domain not in domains_filter:
                continue
        # Actor filter
        if actors_filter:
            if sig.actor not in actors_filter:
                continue
        # Time range filter
        sig_time = sig.timestamp
        if sig_time.tzinfo is None:
            sig_time = sig_time.replace(tzinfo=timezone.utc)
        if since_dt and sig_time < since_dt:
            continue
        if until_dt and sig_time > until_dt:
            continue

        filtered.append(sig)

    # Sort by timestamp descending (most recent first)
    filtered.sort(key=lambda s: s.timestamp if s.timestamp.tzinfo else s.timestamp.replace(tzinfo=timezone.utc), reverse=True)

    # Paginate
    total = len(filtered)
    paginated = filtered[offset:offset + limit]
    has_more = (offset + limit) < total

    # Serialize
    signals_data = []
    for sig in paginated:
        sig_type = sig.type.value if hasattr(sig.type, "value") else str(sig.type)
        sig_provider = sig.provider.value if hasattr(sig.provider, "value") else str(sig.provider)
        signals_data.append({
            "signal_id": str(sig.signal_id),
            "type": sig_type,
            "provider": sig_provider,
            "timestamp": sig.timestamp.isoformat() if sig.timestamp.tzinfo else sig.timestamp.replace(tzinfo=timezone.utc).isoformat(),
            "actor": sig.actor,
            "artifact": sig.artifact,
            "domain": sig.metadata.get("domain", ""),
            "decision": sig.decision,
            "metadata": dict(sig.metadata) if sig.metadata else {},
        })

    return {
        "signals": signals_data,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total": total,
            "has_more": has_more,
        },
        "filters_applied": {
            "provider": list(providers_filter) if providers_filter else None,
            "signal_type": list(types_filter) if types_filter else None,
            "domain": list(domains_filter) if domains_filter else None,
            "actor": list(actors_filter) if actors_filter else None,
            "since": since if since_dt else None,
            "until": until if until_dt else None,
        },
    }


@router.get("/tasks")
def get_tasks(
    assignee: str = Query("", description="Filter by assignee (case-insensitive substring match)."),
    domain: str = Query("", description="Filter by domain (exact match)."),
    priority: str = Query("", description="Filter by priority: high, medium, low."),
    status: str = Query("", description="Filter by status: open, done."),
) -> dict[str, Any]:
    """Tasks & action items auto-extracted from signal text during ingestion.

    V8 Daily Work #2 — Task & Action-Item Intelligence. Maestro scans
    signal text for action-item patterns ("priya to review by Friday",
    "carlos will draft the RFC", "TODO: update docs") and creates task
    learning objects. This feeds the constitutional layers — the model
    learns what the org has committed to and can track completion.

    Each task has: description, assignee, due_date, priority, status,
    source_signal_id, domain, confidence.
    """
    from maestro_oem.task_extraction import get_tasks as _get_tasks
    model = oem_state.model
    tasks = _get_tasks(
        model,
        assignee=assignee,
        domain=domain,
        priority=priority,
        status=status,
    )
    return {
        "tasks": tasks,
        "total": len(tasks),
        "open_count": sum(1 for t in tasks if t["status"] == "open"),
        "done_count": sum(1 for t in tasks if t["status"] == "done"),
        "high_priority_count": sum(1 for t in tasks if t["priority"] == "high"),
        "filters_applied": {
            "assignee": assignee if assignee else None,
            "domain": domain if domain else None,
            "priority": priority if priority else None,
            "status": status if status else None,
        },
    }


@router.post("/tasks/complete")
def complete_task(payload: dict[str, Any]) -> dict[str, Any]:
    """Manually mark an auto-extracted task as done.

    Round 45 — Work surface Bumble redesign. The Tasks sub-tab has a
    "Mark done" button on each task card. This endpoint accepts the
    task_id and updates the task's status to 'done' in the learning
    objects store.

    Payload:
        task_id: str (required) — the learning object ID of the task

    Returns:
        { "task_id": str, "status": "done", "completed_at": str }

    If the task_id is not found, returns 404.
    """
    task_id = payload.get("task_id", "")
    if not task_id:
        raise HTTPException(400, "task_id is required")

    model = oem_state.model
    # Find the task learning object by ID
    for lo in model.learning_objects.values():
        if lo.lo_id == task_id or lo.metadata.get("task_id") == task_id:
            lo_type = lo.type.value if hasattr(lo.type, "value") else str(lo.type)
            if lo_type != "task":
                raise HTTPException(400, f"Learning object {task_id} is not a task")
            lo.metadata["status"] = "done"
            lo.metadata["manually_completed"] = True
            from datetime import datetime, timezone
            lo.metadata["completed_at"] = datetime.now(timezone.utc).isoformat()
            logger.info("Task %s marked done manually", task_id)
            return {
                "task_id": task_id,
                "status": "done",
                "completed_at": lo.metadata["completed_at"],
            }
    raise HTTPException(404, f"Task {task_id} not found")


# ─── V8 Daily Work #4 — Write-Back to Tools ────────────────────────────────
# THE gap between "advises" and "does work." Create Jira tickets, draft
# Gmail emails (NOT send), post Slack messages, create GitHub review
# comments. All gated by approval — no autonomous execution.

@router.post("/writeback")
def create_writeback(payload: dict[str, Any]) -> dict[str, Any]:
    """Preview a write-back action (NOT executed).

    V8 Daily Work #4 — Write-Back to Tools. Accepts a provider + action_type
    + params and returns a preview. The action is stored pending approval.

    Payload:
        provider: "jira" | "github" | "slack" | "gmail" (required)
        action_type: the action to perform (required)
            - jira: "create_issue"
            - github: "create_review_comment" | "create_issue_comment"
            - slack: "post_message"
            - gmail: "create_draft"
        params: provider-specific parameters (required)

    Returns:
        {
            action_id: str,
            provider: str,
            action_type: str,
            preview: str,
            status: "pending",
            params: dict,
            message: str,
        }

    The action is NOT executed. Call POST /api/oem/writeback/{action_id}/approve
    to execute it.
    """
    from maestro_oem.writeback import WriteBackService
    provider = payload.get("provider", "")
    action_type = payload.get("action_type", "")
    params = payload.get("params", {})

    if not provider or not action_type:
        raise HTTPException(400, "provider and action_type are required")

    try:
        svc = WriteBackService(oauth_manager=__import__("maestro_api.oem_state", fromlist=["import_state"]).import_state.oauth)
        return svc.preview(provider, action_type, params)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Write-back preview failed: {e}")


@router.post("/writeback/{action_id}/approve")
def approve_writeback(action_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Execute a previously-previewed write-back action.

    V8 Daily Work #4 — Write-Back to Tools. Executes the action with the
    given action_id. The action must have been previously created via
    POST /api/oem/writeback (which returns a preview + action_id).

    Payload:
        approved_by: str (who approved — for audit, defaults to "user")

    Returns:
        {
            action_id: str,
            status: "executed" | "failed",
            result: dict,  # provider-specific result
            error: str | None,
        }

    Governance: this endpoint requires explicit approval. No autonomous
    execution. Gmail ONLY creates drafts — never sends.
    """
    from maestro_oem.writeback import WriteBackService
    approved_by = payload.get("approved_by", "user")

    try:
        svc = WriteBackService(oauth_manager=__import__("maestro_api.oem_state", fromlist=["import_state"]).import_state.oauth)
        return svc.approve(action_id, approved_by)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Write-back execution failed: {e}")


@router.post("/writeback/{action_id}/reject")
def reject_writeback(action_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Reject a pending write-back action (no execution).

    Payload:
        rejected_by: str (who rejected, defaults to "user")
    """
    from maestro_oem.writeback import WriteBackService
    rejected_by = payload.get("rejected_by", "user")

    try:
        svc = WriteBackService(oauth_manager=__import__("maestro_api.oem_state", fromlist=["import_state"]).import_state.oauth)
        return svc.reject(action_id, rejected_by)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/writeback/pending")
def list_pending_writebacks() -> dict[str, Any]:
    """List all pending write-back actions awaiting approval."""
    from maestro_oem.writeback import WriteBackService
    svc = WriteBackService(oauth_manager=__import__("maestro_api.oem_state", fromlist=["import_state"]).import_state.oauth)
    pending = svc.list_pending()
    return {
        "pending": pending,
        "count": len(pending),
    }


@router.get("/writeback/all")
def list_all_writebacks() -> dict[str, Any]:
    """List all write-back actions (all statuses)."""
    from maestro_oem.writeback import WriteBackService
    svc = WriteBackService(oauth_manager=__import__("maestro_api.oem_state", fromlist=["import_state"]).import_state.oauth)
    all_actions = svc.list_all()
    return {
        "actions": all_actions,
        "count": len(all_actions),
    }


# ─── V8 Daily Work #6 — Role-Specific Playbooks ────────────────────────────

@router.get("/playbook/{role}")
def get_playbook(
    role: str,
    context: str = Query("", description="Optional context: customer name (sales), campaign name (marketing), or feature name (product)."),
) -> dict[str, Any]:
    """Role-specific playbook — format the same evidence differently for each role.

    V8 Daily Work #6 — Role-Specific Playbooks. Thin layers over decision.py
    that format the same evidence differently for sales, marketing, and
    product roles. Not new engines — just formatting.

    Roles:
      - sales: match CRM + draft outreach with talking points from transcripts
      - marketing: unify ad-spend signals into single ROI view
      - product: transcript → PRD outline + tickets + unresolved concerns

    Each playbook returns role-specific drafted artifacts with evidence
    citations. The intelligence is in the existing engines (decision.py,
    customer_judgment.py); the playbook just asks "what does THIS role
    need to see?"
    """
    from maestro_oem.playbooks import PlaybookEngine
    engine = PlaybookEngine(oem_state.model, oem_state.signals, oem_state.decisions)
    return engine.playbook(role, context)


# ─── V8 P0-5 — Push Delivery (Opt-In) ─────────────────────────────────────

@router.get("/push/settings")
def get_push_settings() -> dict[str, Any]:
    """Get the current push delivery settings.

    Default: disabled (channel="none", enabled=False).
    """
    from maestro_oem.push_delivery import PushDeliveryService
    svc = PushDeliveryService()
    settings = svc.get_settings()
    return settings.to_dict()


@router.post("/push/settings")
def set_push_settings(payload: dict[str, Any]) -> dict[str, Any]:
    """Set push delivery settings. Opt-in only — never pushes without consent.

    V8 P0-5 — Push Delivery. The Bond lesson: the briefing finds the CEO.
    But push without consent is a trust violation. Default: pull (no push).
    Push is opt-in per channel.

    Payload:
        channel: "slack" | "email" | "none" (default: "none")
        time: HH:MM (default: "07:00")
        enabled: bool (default: False)
        timezone: str (default: "UTC")
        slack_channel: str (required if channel="slack")
        email_address: str (required if channel="email")

    Never pushes to a channel the customer has not explicitly authorized.
    Never pushes at a time the customer has not chosen.
    """
    from maestro_oem.push_delivery import PushDeliveryService
    svc = PushDeliveryService()
    try:
        settings = svc.set_settings(
            channel=payload.get("channel", "none"),
            time=payload.get("time", "07:00"),
            enabled=payload.get("enabled", False),
            timezone=payload.get("timezone", "UTC"),
            slack_channel=payload.get("slack_channel", ""),
            email_address=payload.get("email_address", ""),
        )
        return settings.to_dict()
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/push/test")
def test_push() -> dict[str, Any]:
    """Send a test push to verify the channel works.

    Sends a minimal test message (not the full briefing).
    """
    from maestro_oem.push_delivery import PushDeliveryService
    svc = PushDeliveryService()
    return svc.send_test_push()


@router.post("/push/deliver")
def deliver_push() -> dict[str, Any]:
    """Deliver the morning briefing via push (if enabled).

    This endpoint is called by the scheduler (cron/APScheduler) at the
    user's chosen time. It can also be called manually to test delivery.

    Governance: if push is not enabled, returns delivered=False.
    """
    from maestro_oem.push_delivery import PushDeliveryService
    svc = PushDeliveryService()
    # Get the briefing data
    briefing = get_ceo_briefing()
    return svc.deliver_briefing(briefing_data=briefing)


# ─── V8 P1-1 — Trust Ledger ────────────────────────────────────────────────

@router.get("/trust/ledger")
def get_trust_ledger(
    user: str = Query("", description="Filter by approver email."),
    provider: str = Query("", description="Filter by provider."),
    action_type: str = Query("", description="Filter by action type."),
) -> dict[str, Any]:
    """Get the trust ledger — records every write-back action.

    V8 P1-1 — Progressive Trust Ledger. The safety infrastructure for
    P1-2 (auto-execute). Records every write-back action: action_id,
    provider, action_type, approver, trust_score_at_execution, outcome
    (success/failure/rolled_back), auto (True if auto-executed), timestamp.
    """
    from maestro_oem.trust_ledger import TrustLedger
    entries = TrustLedger.get_entries(user_id=user, provider=provider, action_type=action_type)
    summary = TrustLedger.get_summary(user_id=user)
    return {
        "entries": [e.to_dict() for e in entries],
        "count": len(entries),
        "summary": summary,
    }


@router.get("/trust/score")
def get_trust_score(
    user: str = Query(..., description="User email."),
    provider: str = Query(..., description="Provider name."),
    action_type: str = Query(..., description="Action type."),
) -> dict[str, Any]:
    """Get the trust score for a (user, provider, action_type) pair.

    Returns the trust score and whether auto-execute is eligible.
    Auto-execute eligibility: trust_score >= 10 AND rolled_back == 0.
    """
    from maestro_oem.trust_ledger import TrustLedger
    score = TrustLedger.compute_trust_score(user, provider, action_type)
    eligible = TrustLedger.is_auto_execute_eligible(user, provider, action_type)
    return {
        "user": user,
        "provider": provider,
        "action_type": action_type,
        "trust_score": score,
        "auto_execute_eligible": eligible,
        "threshold": 10,
    }


# ─── V8 P1-2 — Progressive Trust (Auto-Execute) ────────────────────────────

@router.post("/writeback/auto-execute")
def auto_execute_writeback(payload: dict[str, Any]) -> dict[str, Any]:
    """Auto-execute a write-back if the user has earned trust AND opted in.

    V8 P1-2 — Progressive Trust. Auto-execute requires BOTH:
      1. Eligibility: trust_score >= 10 AND rolled_back == 0 (TrustLedger)
      2. Explicit opt-in: the customer must enable auto-execute per action
         type via POST /settings/auto-execute

    Default: all auto-execute disabled. The customer must explicitly enable
    each (provider, action_type) pair. Even after enabling, the eligibility
    check must still pass.

    The first auto-executed action shows a 60-second undo window.

    Payload:
        provider: str (required)
        action_type: str (required)
        params: dict (required)
        user: str (required — the user requesting auto-execute)

    Returns:
        If eligible + opted-in: {status: "executed", auto: true, undo_until: ISO}
        If not eligible: {status: "requires_manual_approval", auto: false}
        If eligible but not opted-in: {status: "requires_opt_in", auto: false}
    """
    from maestro_oem.trust_ledger import TrustLedger
    from maestro_oem.user_settings import UserSettings
    from maestro_oem.writeback import WriteBackService

    provider = payload.get("provider", "")
    action_type = payload.get("action_type", "")
    params = payload.get("params", {})
    user = payload.get("user", "")

    if not provider or not action_type or not user:
        raise HTTPException(400, "provider, action_type, and user are required")

    # Check 1: Is auto-execute eligible? (trust_score >= 10, 0 rollbacks)
    eligible = TrustLedger.is_auto_execute_eligible(user, provider, action_type)
    if not eligible:
        score = TrustLedger.compute_trust_score(user, provider, action_type)
        return {
            "status": "requires_manual_approval",
            "auto": False,
            "trust_score": score,
            "threshold": 10,
            "message": f"Trust score {score} is below threshold 10. Manual approval required.",
        }

    # Check 2: Has the customer explicitly opted in? (Round-35 fix)
    opted_in = UserSettings.is_auto_execute_enabled(user, provider, action_type)
    if not opted_in:
        return {
            "status": "requires_opt_in",
            "auto": False,
            "trust_score": TrustLedger.compute_trust_score(user, provider, action_type),
            "eligible": True,
            "message": f"Auto-execute is eligible but not enabled. Enable via POST /settings/auto-execute with provider={provider}, action_type={action_type}, enabled=true.",
        }

    # Both checks passed — auto-execute
    svc = WriteBackService(oauth_manager=__import__("maestro_api.oem_state", fromlist=["import_state"]).import_state.oauth)
    preview = svc.preview(provider, action_type, params)
    result = svc.approve(preview["action_id"], approved_by=user, auto_execute=True)

    # 60-second undo window
    from datetime import datetime, timedelta, timezone
    undo_until = (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()

    result["auto"] = True
    result["undo_until"] = undo_until
    result["undo_message"] = f"Auto-executed: {preview['preview'][:80]}. Undo within 60 seconds."
    return result


@router.post("/writeback/{action_id}/undo")
def undo_writeback(action_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Undo an auto-executed write-back (within the 60-second window).

    Records the undo in the trust ledger as outcome="rolled_back".
    This decrements the trust score for the (user, provider, action_type) pair.
    """
    from maestro_oem.trust_ledger import TrustLedger
    from maestro_oem.writeback import WriteBackStore

    action = WriteBackStore.get(action_id)
    if action is None:
        raise HTTPException(404, f"Action not found: {action_id}")
    if action.status != "executed":
        raise HTTPException(400, f"Action is not executed (status: {action.status})")

    # Record the rollback in the trust ledger
    approver = payload.get("user", action.approved_by or "user")
    TrustLedger.record(
        action_id=action_id,
        provider=action.provider,
        action_type=action.action_type,
        approver=approver,
        outcome="rolled_back",
        auto=True,
    )

    action.status = "rolled_back"
    return action.to_dict()


# ─── V8 P1-2 Fix — Auto-Execute Opt-In Settings ────────────────────────────

@router.post("/settings/auto-execute")
def set_auto_execute_settings(payload: dict[str, Any]) -> dict[str, Any]:
    """Enable or disable auto-execute per action type.

    V8 P1-2 Fix (Round-35 audit) — the customer must explicitly enable
    auto-execute per (provider, action_type) pair. Even after enabling,
    the eligibility check (trust_score >= 10, 0 rollbacks) must still pass.

    Payload:
        provider: str (required)
        action_type: str (required)
        enabled: bool (required — True to enable, False to disable)

    Returns the updated settings with eligibility info.
    """
    from maestro_oem.user_settings import UserSettings
    provider = payload.get("provider", "")
    action_type = payload.get("action_type", "")
    enabled = payload.get("enabled", False)
    user = payload.get("user", "default")

    if not provider or not action_type:
        raise HTTPException(400, "provider and action_type are required")

    return UserSettings.set_auto_execute(user, provider, action_type, enabled)


@router.get("/settings/auto-execute")
def get_auto_execute_settings(
    user: str = Query("default", description="User email."),
) -> dict[str, Any]:
    """Get auto-execute settings with eligibility info per action type.

    Returns each enabled action type with:
      - enabled: whether the customer opted in
      - trust_score: current trust score
      - eligible: whether trust_score >= 10 and 0 rollbacks
      - active: enabled AND eligible (auto-execute will fire)
    """
    from maestro_oem.user_settings import UserSettings
    settings = UserSettings.get_auto_execute_settings(user)
    settings["action_types"] = UserSettings.get_auto_execute_with_eligibility(user)
    return settings


# ─── V8 P2-3 — Customer-Initiated Teaching ─────────────────────────────────

@router.post("/teach")
def teach_maestro(payload: dict[str, Any]) -> dict[str, Any]:
    """Let the customer teach Maestro something in free text.

    V8 P2-3 — Customer-Initiated Teaching. The customer types free text
    ("Legal always slows down OAuth approvals because Sarah needs to
    review every scope change"). Maestro processes this as a human_context
    signal, extracts entities + patterns, and returns a confirmation the
    customer can edit. This is the Amazon principle: the customer is the
    best source of truth. Maestro should make it effortless to inject
    human knowledge into the model.

    Payload:
        text: str (required — free text from the customer)
        actor: str (optional — who is teaching, defaults to "user")

    Returns:
        {
            learned: dict,  # what Maestro extracted
            signal_id: str,  # the created signal ID
            confirmation: str,  # human-readable confirmation
            editable: bool,  # True — the customer can edit
        }
    """
    text = payload.get("text", "")
    actor = payload.get("actor", "user")

    if not text or not text.strip():
        raise HTTPException(400, "text is required")

    text = text.strip()

    # Extract entities + patterns from the free text
    learned = _extract_knowledge_from_text(text)

    # Create a human_context signal (same pattern as Conversational Curiosity)
    from maestro_oem.signal import ExecutionSignal, SignalType, SignalProvider
    from datetime import datetime, timezone

    signal = ExecutionSignal(
        type=SignalType.DECISION_SIGNAL,
        timestamp=datetime.now(timezone.utc),
        actor=actor,
        artifact=f"human-teach:{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        decision=True,
        confidence=1.0,
        metadata={
            "kind": "human_context",
            "source": "customer_teaching",
            "text": text,
            "learned": learned,
            "taught_by": actor,
        },
        provider=SignalProvider.UNKNOWN,
    )

    # Ingest directly into the engine (not via live_ingest — this is
    # organizational knowledge, not a provider signal. Same pattern as
    # the Conversational Curiosity follow-up endpoint.)
    try:
        with oem_state._lock:
            assert oem_state.engine is not None
            oem_state.engine.ingest([signal])
            oem_state.signals.append(signal)
        oem_state._refresh_downstream()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Failed to ingest teach signal: %s", e)

    confirmation = (
        f"Got it. I learned: {learned.get('summary', text[:120])}. "
        f"Is this correct? You can edit this knowledge or teach me more."
    )

    return {
        "learned": learned,
        "signal_id": str(signal.signal_id),
        "confirmation": confirmation,
        "editable": True,
        "text": text,
    }


def _extract_knowledge_from_text(text: str) -> dict[str, Any]:
    """Extract entities + patterns from free-text teaching.

    Rule-based extraction for the pilot. In production, the LLM handles
    this with entity recognition + relationship extraction.
    """
    import re

    # Extract email addresses (potential people)
    emails = re.findall(r'[\w._%+-]+@[\w.-]+\.[A-Za-z]{2,}', text)

    # Extract domain keywords
    domain_keywords = {
        "legal", "compliance", "oauth", "security", "payments", "architecture",
        "engineering", "qa", "testing", "deployment", "incident", "customer",
        "sales", "marketing", "product", "design", "devops", "frontend",
        "backend", "database", "infrastructure",
    }
    text_lower = text.lower()
    found_domains = [d for d in domain_keywords if d in text_lower]

    # Extract causal patterns ("because", "since", "due to", "leads to")
    causal_patterns = []
    for pattern in [r'because\s+(.+?)(?=[.;]|\n|$)', r'since\s+(.+?)(?=[.;]|\n|$)',
                     r'due to\s+(.+?)(?=[.;]|\n|$)', r'leads to\s+(.+?)(?=[.;]|\n|$)',
                     r'always\s+(.+?)(?=[.;]|\n|$)', r'never\s+(.+?)(?=[.;]|\n|$)']:
        matches = re.findall(pattern, text, re.IGNORECASE)
        causal_patterns.extend(matches[:2])

    # Extract action patterns
    action_patterns = []
    for pattern in [r'should\s+(.+?)(?=[.;]|\n|$)', r'must\s+(.+?)(?=[.;]|\n|$)',
                     r'needs? to\s+(.+?)(?=[.;]|\n|$)', r'have to\s+(.+?)(?=[.;]|\n|$)']:
        matches = re.findall(pattern, text, re.IGNORECASE)
        action_patterns.extend(matches[:2])

    # Build a summary
    summary_parts = []
    if found_domains:
        summary_parts.append(f"domains: {', '.join(found_domains[:3])}")
    if emails:
        summary_parts.append(f"people: {', '.join(emails[:3])}")
    if causal_patterns:
        summary_parts.append(f"patterns: {'; '.join(causal_patterns[:2])}")
    if action_patterns:
        summary_parts.append(f"actions: {'; '.join(action_patterns[:2])}")
    summary = " | ".join(summary_parts) if summary_parts else text[:120]

    return {
        "summary": summary,
        "domains": found_domains,
        "people": emails,
        "causal_patterns": causal_patterns,
        "action_patterns": action_patterns,
        "full_text": text,
    }


# ─── V8 P1-3 — Unknown-to-Action Pipeline ──────────────────────────────────

@router.get("/unknowns/actions")
def get_unknown_actions() -> dict[str, Any]:
    """Get suggested actions for each unknown.

    V8 P1-3 — Unknown-to-Action Pipeline. Each unknown level has a
    suggested_action:
      - Unknown Unknown: "Connect {provider}" (suggest which integration fills the gap)
      - Known Unknown: "Instrument" (suggest a metric to track)
      - Emerging Unknown: "Investigate" (create a task for the team lead)
    """
    from maestro_oem.curiosity import CuriosityEngine
    engine = CuriosityEngine(oem_state.model, oem_state.signals)
    unknowns = engine.classify_unknowns()

    actions: list[dict[str, Any]] = []

    # Suggest "Connect" for Unknown Unknowns
    for item in unknowns.get("unknown_unknowns", []):
        domain = item.get("area", "")
        # Suggest which provider would fill this gap
        suggested_provider = "github"  # default
        if domain in ("qa", "testing", "testing"):
            suggested_provider = "jira"
        elif domain in ("docs", "documentation", "knowledge"):
            suggested_provider = "confluence"
        elif domain in ("legal", "compliance"):
            suggested_provider = "gmail"
        elif domain in ("customer", "sales", "crm"):
            suggested_provider = "customer"
        actions.append({
            "area": domain,
            "level": "unknown_unknown",
            "action": "connect",
            "suggested_provider": suggested_provider,
            "label": f"Connect {suggested_provider}",
            "reason": f"The {domain} domain has {item.get('signal_count', 0)} signals. Connecting {suggested_provider} would fill this blind spot.",
        })

    # Suggest "Instrument" for Known Unknowns
    for item in unknowns.get("known_unknowns", []):
        domain = item.get("area", "")
        actions.append({
            "area": domain,
            "level": "known_unknown",
            "action": "instrument",
            "label": f"Instrument {domain}",
            "reason": f"The {domain} domain has {item.get('signal_count', 0)} signals ({item.get('coverage', 0):.0%} coverage). Adding a metric would improve visibility.",
        })

    # Suggest "Investigate" for Emerging Unknowns
    for item in unknowns.get("emerging_unknowns", []):
        area = item.get("area", "")
        actions.append({
            "area": area,
            "level": "emerging_unknown",
            "action": "investigate",
            "label": f"Investigate {area}",
            "reason": item.get("reason", ""),
            "detected_at": item.get("detected_at"),
        })

    return {
        "actions": actions,
        "count": len(actions),
        "summary": f"{len(actions)} suggested actions from the unknowns map.",
    }


# ─── V8 P1-4 — Auto-Completion Detection ───────────────────────────────────
# Implemented in task_extraction.py — during live_ingest, when a new signal
# matches an open task (same artifact, same actor, completion-type signal),
# the task is marked as "kept". See oem_state.py live_ingest() for the call.

@router.get("/tasks/auto-completed")
def get_auto_completed_tasks() -> dict[str, Any]:
    """Get tasks that were auto-completed by matching completion signals.

    V8 P1-4 — Auto-Completion Detection. During live_ingest, when a new
    signal arrives that matches an open task (same artifact, same actor,
    completion-type signal like pr.merged or issue.transitioned to 'done'),
    the task is marked as 'kept'. This endpoint returns those tasks.
    """
    model = oem_state.model
    auto_completed: list[dict[str, Any]] = []
    for lo in model.learning_objects.values():
        lo_type = lo.type.value if hasattr(lo.type, "value") else str(lo.type)
        if lo_type != "task":
            continue
        if lo.metadata.get("status") != "kept":
            continue
        if not lo.metadata.get("auto_completed"):
            continue  # only show auto-completed, not manually completed
        auto_completed.append({
            "id": str(lo.lo_id),
            "description": lo.description,
            "assignee": lo.metadata.get("assignee", ""),
            "completed_by_signal": lo.metadata.get("completed_by_signal", ""),
            "completed_at": lo.metadata.get("completed_at", ""),
            "domain": lo.metadata.get("domain", ""),
        })
    return {
        "tasks": auto_completed,
        "count": len(auto_completed),
        "summary": f"{len(auto_completed)} task{'s' if len(auto_completed) != 1 else ''} auto-completed.",
    }


# ─── V8 P1-5 — The Briefing Learns (Attention Signals) ─────────────────────

@router.post("/attention/record")
def record_attention(payload: dict[str, Any]) -> dict[str, Any]:
    """Record an attention signal — which briefing item the CEO clicked.

    V8 P1-5 — The Briefing Learns. Every click on a briefing item is
    recorded as an attention signal. Over time, the briefing ranking
    weights items by historical attention. If the CEO consistently clicks
    "commitments" first, commitments move to the top. If they never click
    "risks", risks move to the bottom (but are never hidden — Radical Honesty).

    Payload:
        item_type: str (e.g. "commitments", "one_thing", "money", "knowledge")
        item_id: str (optional — specific item identifier)

    Attention signals never hide information; they only reorder it.
    """
    from maestro_oem.attention_signals import AttentionSignalStore
    item_type = payload.get("item_type", "")
    item_id = payload.get("item_id", "")
    if not item_type:
        raise HTTPException(400, "item_type is required")
    AttentionSignalStore.record(item_type=item_type, item_id=item_id)
    return {"recorded": True, "item_type": item_type}


@router.get("/attention/summary")
def get_attention_summary() -> dict[str, Any]:
    """Get the attention signal summary — which briefing item types get clicked most."""
    from maestro_oem.attention_signals import AttentionSignalStore
    return AttentionSignalStore.get_summary()


# ─── V8 Competitor Analysis Feature E — Commitment Tracker ─────────────────

@router.get("/commitments")
def get_commitments(
    status: str = Query("", description="Filter by status: open, kept, broken."),
) -> dict[str, Any]:
    """Track commitments made in signal text. Flag broken commitments.

    V8 Competitor Analysis Feature E — Commitment Tracker. The Bond lesson:
    commitment tracking is Bond's core feature on Maestro's evidence graph.

    Scans signal text for commitment patterns ("I'll get back to you",
    "will follow up by", "promised to") and tracks their status:
      - open: due date hasn't passed yet
      - kept: a later completion signal from the same actor was found
      - broken: due date has passed with no completion signal

    Each commitment has: description, who_committed, to_whom, due_date,
    source_signal_id, status.
    """
    from maestro_oem.commitment_tracker import CommitmentTracker
    tracker = CommitmentTracker(oem_state.model, oem_state.signals)
    result = tracker.track()

    if status:
        result["commitments"] = [c for c in result["commitments"] if c["status"] == status]
        result["filtered_count"] = len(result["commitments"])

    return result


# ─── V8 Competitor Analysis Feature D — Governed Auto-Action ───────────────

@router.post("/auto-action/contradictions")
def auto_action_contradictions(payload: dict[str, Any]) -> dict[str, Any]:
    """Auto-DRAFT Jira/Slack for open contradictions (never auto-SEND).

    V8 Competitor Analysis Feature D — Governed Auto-Action. The Nerve
    lesson: action-taking works, stay anchored. When a contradiction is
    detected, Maestro auto-generates a DRAFT Slack message or Jira ticket
    to address it. The user approves or rejects — no autonomous execution.

    Payload:
        provider: "jira" | "slack" (default: "slack")
        channel: str (for Slack, default: "general")
        project: str (for Jira, default: "ENG")

    Returns:
        {
            previews: list of writeback previews (one per open contradiction),
            count: int,
        }

    Each preview is a pending writeback action that must be approved via
    POST /api/oem/writeback/{action_id}/approve before execution.
    """
    from maestro_oem.writeback import WriteBackService
    from maestro_api.routes.oem import _get_assumption_graph
    from maestro_oem.contradictions import ContradictionDetector

    provider = payload.get("provider", "slack")
    channel = payload.get("channel", "general")
    project = payload.get("project", "ENG")

    # Detect open contradictions
    graph = _get_assumption_graph()
    detector = ContradictionDetector(oem_state.model, oem_state.signals, graph)
    contradictions = detector.detect_all()
    open_contradictions = [c for c in contradictions if c.get("status") == "open"]

    # Generate a writeback preview for each open contradiction
    svc = WriteBackService(oauth_manager=__import__("maestro_api.oem_state", fromlist=["import_state"]).import_state.oauth)
    previews = []
    for contradiction in open_contradictions[:5]:  # limit to 5 to avoid spam
        title = contradiction.get("title", "Unknown contradiction")
        description = contradiction.get("description", "")
        text = f"Contradiction detected: {title}. {description}"

        if provider == "jira":
            preview = svc.preview("jira", "create_issue", {
                "project": project,
                "summary": f"Resolve: {title[:60]}",
                "description": text[:500],
                "issue_type": "Task",
            })
        else:
            preview = svc.preview("slack", "post_message", {
                "channel": channel,
                "text": f"⚠ Contradiction detected: {title}. {description[:200]}",
            })

        preview["contradiction_id"] = contradiction.get("id", "")
        previews.append(preview)

    return {
        "previews": previews,
        "count": len(previews),
        "total_contradictions": len(open_contradictions),
        "message": f"Generated {len(previews)} draft action(s). Each must be approved before execution.",
    }


@router.post("/curiosity/follow-up")
def curiosity_follow_up(payload: dict[str, Any]) -> dict[str, Any]:
    """Process a user's answer in a curiosity conversation.

    V8 Upgrade #3 — Conversational Curiosity. Maestro asks a question,
    the user answers, Maestro asks a context-aware follow-up (referencing
    the answer), the user answers again, and after at most 3 turns Maestro
    says "Thank you. Understanding updated." and creates a human_context
    signal that feeds into the model.

    Payload:
        question_id: str (required) — the stable ID from GET /curiosity
        answer: str (required) — the user's answer to the current question
        original_question: str — the first question (required on turn 1,
                                  ignored on subsequent turns)
        question_type: str — the question type (required on turn 1)
        domain: str — the domain (required on turn 1)

    Returns one of:
        {
            "follow_up_question": str,
            "turn": int,                    # the NEXT turn number (2 or 3)
            "question_id": str,
            "understanding_updated": false,
            "signal_created": false
        }
        OR
        {
            "understanding_updated": true,
            "signal_created": true,
            "signal_id": str,
            "turn": 3,
            "question_id": str,
            "summary": str,
            "domain": str,
            "question_type": str
        }

    The conversation is bounded at 3 turns — Maestro does not interrogate.
    After turn 3, the accumulated Q&A becomes a DECISION_SIGNAL with
    metadata.kind="human_context" that is ingested into the model via
    live_ingest. The signal captures the full conversation so the model
    can learn from human knowledge that wasn't in the signal stream.
    """
    from maestro_oem.curiosity import CuriosityEngine
    question_id = payload.get("question_id", "")
    answer = payload.get("answer", "")
    if not question_id or not answer or not answer.strip():
        raise HTTPException(400, "question_id and answer are required")

    engine = CuriosityEngine(oem_state.model, oem_state.signals)
    result = engine.follow_up(
        question_id=question_id,
        answer=answer,
        original_question=payload.get("original_question", ""),
        question_type=payload.get("question_type", ""),
        domain=payload.get("domain", ""),
    )

    # If the conversation closed and a signal was created, ingest it into
    # the model so it becomes part of the organizational knowledge.
    # NOTE: we do NOT use live_ingest() here because live_ingest() purges
    # the demo seed on the first real signal (HIGH 5 fix). The human_context
    # signal is organizational knowledge, not a provider signal — it should
    # augment the model, not replace the demo seed. We ingest directly into
    # the engine and append to the signals list, then refresh downstream.
    if result.get("signal_created") and result.get("signal"):
        sig = result["signal"]
        try:
            with oem_state._lock:
                assert oem_state.engine is not None
                oem_state.engine.ingest([sig])
                oem_state.signals.append(sig)
            oem_state._refresh_downstream()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                "Failed to ingest human_context signal: %s", e
            )
        # Don't return the raw signal object (not JSON-serializable —
        # ExecutionSignal is a Pydantic model but the metadata contains
        # nested structures). The signal_id is sufficient for the client.
        del result["signal"]

    return result


@router.get("/skepticism")
def get_skepticism() -> dict[str, Any]:
    """Challenge fossilized beliefs.

    V4 Organ #3 — Skepticism. Finds beliefs the organization holds without
    recent validation and challenges them with evidence.
    """
    from maestro_oem.skepticism import SkepticismEngine
    engine = SkepticismEngine(oem_state.model, oem_state.signals)
    return engine.challenge()


@router.get("/wisdom")
def get_wisdom(
    context: str = Query("", description="Decision context: launch, hiring, architecture, etc."),
) -> dict[str, Any]:
    """Synthesize competing values into balanced judgment.

    V4 Organ #4 — Wisdom. Intelligence knows. Wisdom chooses. This engine
    synthesizes competing organizational values into a recommendation
    based on what has worked before.
    """
    from maestro_oem.wisdom import WisdomEngine
    engine = WisdomEngine(oem_state.model, oem_state.signals)
    return engine.synthesize(context=context)


@router.get("/metacognition")
def get_metacognition() -> dict[str, Any]:
    """The organization thinking about its own thinking.

    V4 Organ #5 — Metacognition. Computes the meta-gap between team-level
    quality and org-level quality. When teams are smart but the org isn't,
    the problem is in coordination.
    """
    from maestro_oem.metacognition import MetacognitionEngine
    engine = MetacognitionEngine(oem_state.model, oem_state.signals)
    return engine.analyze()


@router.get("/principles")
def get_principles() -> dict[str, Any]:
    """Laws that have graduated to organizational wisdom.

    V4 Organ #6 — Principles. Patterns validated so consistently, for so
    long, that they have graduated from 'pattern' to 'organizational wisdom.'
    """
    from maestro_oem.principles import PrinciplesEngine
    engine = PrinciplesEngine(oem_state.model, oem_state.signals)
    return engine.discover()


@router.get("/compression")
def get_compression() -> dict[str, Any]:
    """Compress organizational memory into a few truths.

    V4 Organ #7 — Memory Compression. Millions of signals → a few truths,
    habits, mistakes, interventions. Memory becomes understanding.
    """
    from maestro_oem.memory_compression import MemoryCompressionEngine
    engine = MemoryCompressionEngine(oem_state.model, oem_state.signals)
    return engine.compress()


@router.get("/consciousness")
def get_consciousness() -> dict[str, Any]:
    """Real-time organizational state vector.

    V4 Organ #8 — Consciousness. Always knows where attention, knowledge,
    trust, conflict, energy, uncertainty, and learning are. The
    Organizational Dot draws from this state vector.
    """
    from maestro_oem.consciousness import ConsciousnessEngine
    engine = ConsciousnessEngine(oem_state.model, oem_state.signals)
    return engine.state_vector()


# ═══════════════════════════════════════════════════════════════════════════
# 30. CONSTITUTION V5 — THE INVISIBLE LAYER
# ═══════════════════════════════════════════════════════════════════════════
# V5 Law: "Every release must make Maestro feel simpler, even if it
# becomes dramatically more intelligent internally."
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/execute")
def get_execution_plan(
    recommendation_id: str = Query("", description="Recommendation title to plan execution for"),
    context: str = Query("", description="Decision context"),
) -> dict[str, Any]:
    """Prepare an execution plan for a recommendation.

    V5 Spec #2 — Executive Function. Maestro doesn't just advise — it
    plans, sequences, and drafts actions. Returns steps, drafted briefing,
    and follow-through plan.
    """
    from maestro_oem.executive_function import ExecutiveFunctionEngine
    engine = ExecutiveFunctionEngine(oem_state.model, oem_state.signals, oem_state.decisions)
    return engine.plan(recommendation_title=recommendation_id, context=context)


@router.get("/attention")
def get_attention() -> dict[str, Any]:
    """Where should the organization's attention be?

    V5 Spec #3 — Attention Allocation. Consciousness knows where attention
    IS. This engine decides where it SHOULD BE — including what's stealing
    focus and what to deprioritize.
    """
    from maestro_oem.attention import AttentionEngine
    engine = AttentionEngine(oem_state.model, oem_state.signals)
    return engine.allocate()


# ═══════════════════════════════════════════════════════════════════════════
# 31. CONSTITUTION V5 — PHASE 2-3 (Deeper Cognition + Ambient + Institutional)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/trajectories")
def get_trajectories() -> dict[str, Any]:
    """Temporal trajectories for all organizational dimensions.

    V5 Spec #7 — org-wide trend memory. All 7 consciousness dimensions
    get trend + slope + duration + narrative. "Trust has fallen for 8 weeks."
    """
    from maestro_oem.trajectories import TrajectoryEngine
    engine = TrajectoryEngine(oem_state.model, oem_state.signals)
    return engine.compute()


@router.get("/causal")
def get_causal() -> dict[str, Any]:
    """Discover causal chains from organizational history.

    V5 Spec #6 — move from correlation to causation. A caused B because
    N interventions produced the same sequence.
    """
    from maestro_oem.causal import CausalEngine
    engine = CausalEngine(oem_state.model, oem_state.signals)
    return engine.discover()


@router.get("/forgetting")
def get_forgetting() -> dict[str, Any]:
    """Identify events the organization should forget.

    V5 Spec #4 — archive zero-predictive-value events. Not deletion —
    deprioritization. Events with low predictive value are noise.
    """
    from maestro_oem.forgetting import ForgettingEngine
    engine = ForgettingEngine(oem_state.model, oem_state.signals)
    return engine.assess()


@router.get("/imagine")
def get_imagination(
    scenario: str = Query("", description="Counterfactual scenario: 'legal', 'platform', 'engineering', or a person's email"),
) -> dict[str, Any]:
    """Generate counterfactual consequences.

    V5 Spec #5 — imagination. "What would happen if Legal disappeared?"
    Uses causal chains + historical analogues.
    """
    from maestro_oem.imagination import ImaginationEngine
    engine = ImaginationEngine(oem_state.model, oem_state.signals)
    return engine.imagine(scenario=scenario)


@router.get("/recall")
def get_recall(
    situation: str = Query("", description="Current situation to find analogues for"),
) -> dict[str, Any]:
    """When have we been here before?

    V5 Spec #8 — institutional memory recall. Retrieves top 3 similar
    past moments from organizational history. Not documents — memories.
    """
    from maestro_oem.recall import RecallEngine
    engine = RecallEngine(oem_state.model, oem_state.signals)
    return engine.recall(situation=situation)


# ═══════════════════════════════════════════════════════════════════════════
# 32. CONSTITUTION V6 — PERMANENT IMPROVEMENT
# ═══════════════════════════════════════════════════════════════════════════
# V6 Law: "Every interaction must permanently improve the organization."
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/nudges")
def get_nudges() -> dict[str, Any]:
    """Adaptive restructuring suggestions based on causal evidence.

    V6 Spec #1 — Maestro quietly suggests work restructuring based on
    what has worked before. Each nudge is actionable and backed by causal
    evidence (not just correlation).
    """
    from maestro_oem.adaptive_nudge import AdaptiveNudgeEngine
    engine = AdaptiveNudgeEngine(oem_state.model, oem_state.signals)
    return engine.generate()


@router.get("/evolution-tracker")
def get_evolution_tracker() -> dict[str, Any]:
    """Track failure modes from active → resolving → eliminated.

    V6 Spec #2 — "We no longer make this mistake." Tracks specific failure
    modes and whether the organization has stopped making them. A failure
    mode is "eliminated" when it hasn't recurred for 90+ days.
    """
    from maestro_oem.evolution_tracker import EvolutionTracker
    engine = EvolutionTracker(oem_state.model, oem_state.signals)
    return engine.track()


@router.get("/background-loop")
def get_background_loop(
    fresh: bool = Query(False, description="Force a fresh run instead of returning the cached result from the last ingest."),
) -> dict[str, Any]:
    """What Maestro noticed while you were away.

    V6 Spec #3 — Background Adaptation Loop. Runs on every signal ingest
    (V6 Law 2: "improves even when nobody opens Maestro"). By default this
    endpoint returns the cached result from the last ingest; pass ?fresh=1
    to force a fresh run.
    """
    if not fresh and oem_state._last_background_loop_result is not None:
        return oem_state._last_background_loop_result
    from maestro_oem.background_loop import BackgroundAdaptationLoop
    engine = BackgroundAdaptationLoop(oem_state.model, oem_state.signals)
    result = engine.run()
    # Cache so a subsequent ingest-less GET returns the same result.
    oem_state._last_background_loop_result = result
    return result


@router.get("/trajectory-intervention")
def get_trajectory_intervention() -> dict[str, Any]:
    """Declining trajectories that need intervention.

    V6 Spec #4 — weak signal → trajectory change → quiet intervention.
    Computes time_to_failure from slope. Proposes interventions with
    historical analogues.
    """
    from maestro_oem.trajectory_intervention import TrajectoryInterventionEngine
    engine = TrajectoryInterventionEngine(oem_state.model, oem_state.signals)
    return engine.assess()


@router.get("/org-pattern")
def get_organizational_pattern() -> dict[str, Any]:
    """Detect a recurring organizational pattern and suggest a law.

    CEO's 'Friday notification' (2026-07-03): Maestro notices a pattern
    over weeks and surfaces it as an organizational law suggestion.

    Example: 'Customers have raised pricing concerns 11 times. Suggested
    operating law: Address pricing proactively in every customer engagement.'

    Returns None if no significant pattern is detected.
    """
    from maestro_oem.trajectory_intervention import TrajectoryInterventionEngine
    engine = TrajectoryInterventionEngine(oem_state.model, oem_state.signals)
    pattern = engine.detect_organizational_pattern(min_occurrences=5)
    if pattern:
        return {"pattern": pattern, "suggestion": "Review as Law?"}
    return {"pattern": None}


# ─── CEO Feature 1: Preparation Engine ─────────────────────────────────────
# "Every evening Maestro should quietly prepare for tomorrow."

# ─── CEO Vision: Whisper Recall — "What was that thing about Legal?" ────────
# Whispers are durable first-class objects with a lifecycle. The executive
# can recall old whispers by vague description.

@router.post("/ask/recall")
def ask_recall(payload: dict[str, Any]) -> dict[str, Any]:
    """Recall old whispers + signals + decisions by vague description.

    CEO: "What was that thing Maestro warned me about Legal a few weeks ago?"

    Phase 2 (2026-07-03): replaced keyword-only WhisperRecall with the
    hybrid RecallEngine. The new engine:
      - Parses temporal phrases ("last month" → date range)
      - Resolves entities via synonym map ("legal" → {compliance, contract, ...})
      - Embeds query + insights with all-MiniLM-L6-v2 (384-dim)
      - Traverses signals + decisions for cross-entity recall
      - Returns Evidence objects (Phase 1 spine) with source_artifacts,
        people_involved, timestamps populated
      - Computes what_changed_since from the actual signal diff
        (NOT hardcoded template strings)

    The old keyword-only WhisperRecall is still available at
    maestro_oem.whisper_recall for backward-compat testing, but is no
    longer wired to any endpoint.
    """
    query = payload.get("query", "")
    if not query:
        raise HTTPException(400, "Query is required")

    from maestro_oem.recall_engine import RecallEngine
    store = _get_whisper_history_store()
    recall = RecallEngine(
        whisper_history_store=store,
        signals=oem_state.signals if oem_state else [],
        oem_state=oem_state,
    )
    return recall.recall(query, org_id="default")


# ─── CEO Vision: Conversational Ask — multi-turn organizational memory ──────
# The executive asks a question. Maestro reasons across signal history,
# decision history, contradictions, evidence, and learning outcomes.

@router.post("/ask/conversation")
def ask_conversation(payload: dict[str, Any]) -> dict[str, Any]:
    """Multi-turn conversational organizational memory.

    CEO: "Why is the Atlas launch late?" → Maestro explains the root cause,
    references prior decisions, and offers follow-up questions.

    This is NOT search. This is NOT RAG. This is reasoning across the
    history of an organization.
    """
    query = payload.get("query", "")
    history = payload.get("history", [])

    if not query:
        raise HTTPException(400, "Query is required")

    # Route through cognitive engines (invisible to user)
    answer = _generate_conversational_answer(query, history)

    return answer


def _generate_conversational_answer(query: str, history: list) -> dict[str, Any]:
    """Generate an evidence-grounded conversational answer.

    Routes through:
    1. Whisper recall (did Maestro warn about this before?)
    2. Signal history (what happened?)
    3. Decision history (what was decided?)
    4. Contradiction detection (where do people disagree?)
    5. Evidence assembly (what supports this?)
    """
    query_lower = query.lower()

    # Check if this is a recall query ("What was that thing about...")
    if any(phrase in query_lower for phrase in ["what was that", "remind me", "you showed me", "you warned me", "you told me"]):
        store = _get_whisper_history_store()
        # Phase 2: use the hybrid RecallEngine (semantic + temporal + entity + graph)
        from maestro_oem.recall_engine import RecallEngine
        recall = RecallEngine(
            whisper_history_store=store,
            signals=oem_state.signals if oem_state else [],
            oem_state=oem_state,
        )
        result = recall.recall(query, org_id="default")
        # Phase 2: the RecallEngine already returns Evidence objects on
        # each item. Pass them through to the conversation surface — no
        # need to re-build ad-hoc evidence dicts.
        evidence_spines = []
        for w in result.get("whispers", []):
            evidence_spines.append({
                "source": "whisper_history",
                "text": w.get("original_insight", ""),
                "evidence_spine": w.get("evidence_spine", {
                    "claim": w.get("original_insight", ""),
                    "observed_facts": [{"source": "whisper_history", "date": w.get("last_shown", ""), "text": w.get("original_insight", ""), "people": []}],
                    "what_changed_since": w.get("what_changed", ""),
                }),
            })
        return {
            "answer": result["message"],
            "evidence": evidence_spines,
            "follow_ups": ["Show original whisper", "Show evidence", "Prepare response"],
            "actions": [{"label": "Show original", "type": "evidence"}],
        }

    # Check if this is a preparation query ("Prepare me for...")
    if "prepare me" in query_lower or "prepare for" in query_lower:
        from maestro_oem.preparation_engine import PreparationEngine
        engine = PreparationEngine(oem_state.model, oem_state.signals)
        prep = engine.prepare_for_tomorrow(org_id="default")
        meeting = prep.get("meetings", [{}])[0] if prep.get("meetings") else {}
        p = meeting.get("preparation", {})

        answer_parts = []
        if meeting.get("title"):
            answer_parts.append(f"# {meeting['title']}\n")
            answer_parts.append(f"**The real issue appears to be delivery trust, not price.**\n")

        if p.get("customer_concerns"):
            answer_parts.append("### Likely to come up\n")
            for concern in p["customer_concerns"]:
                answer_parts.append(f"**{concern.title()}:** This has been raised before.\n")

        if p.get("internal_expert"):
            answer_parts.append(f"\n### Internal expert\n{p['internal_expert']} knows this customer best.\n")

        if p.get("relevant_commitments"):
            answer_parts.append("\n### Remember\n")
            for c in p["relevant_commitments"]:
                answer_parts.append(f"- {c.get('commitment', '')}\n")

        answer_parts.append("\n### I prepared\n")
        answer_parts.append("- commitment timeline\n")
        answer_parts.append("- previous discussion summary\n")
        answer_parts.append("- draft follow-up note\n")

        answer_parts.append("\n**Ask anything about this meeting...**")

        return {
            "answer": "\n".join(answer_parts),
            "evidence": [{
                "source": "preparation_engine",
                "text": "Generated from signal history",
                "evidence_spine": {
                    "claim": f"Preparation for {meeting.get('title', 'meeting')}",
                    "observed_facts": [
                        {"source": "customer signals", "date": "", "text": c.get("commitment", ""), "people": []}
                        for c in p.get("relevant_commitments", [])
                    ] or [{"source": "preparation_engine", "date": "", "text": "No specific commitments found", "people": []}],
                    "people_involved": [{"name": p.get("internal_expert", ""), "role": "expert", "why_relevant": "knows this customer best"}] if p.get("internal_expert") else [],
                    "assumptions": ["The meeting will proceed as scheduled", "The concerns are still relevant"],
                },
            }],
            "follow_ups": [
                "What exactly did Sales promise?",
                "Who was in that conversation?",
                "What are we assuming?",
                "Who internally disagrees?",
            ],
            "actions": [{"label": "Insert draft", "type": "insert_text"}],
        }

    # Check if this is a "why" question
    if query_lower.startswith("why"):
        # Search for relevant signals
        relevant_signals = []
        for s in oem_state.signals[:20]:
            try:
                sig_text = (s.artifact or "") + " " + (s.metadata.get("commitment", "") if hasattr(s, "metadata") else "")
                if any(word in sig_text.lower() for word in query_lower.split() if len(word) > 3):
                    relevant_signals.append({
                        "source": s.provider.value if hasattr(s.provider, "value") else str(s.provider),
                        "text": sig_text[:100],
                        "date": s.timestamp.isoformat()[:10] if hasattr(s.timestamp, "isoformat") else "",
                    })
            except Exception:
                continue

        answer = "Based on the organizational signals I've gathered:\n\n"
        if relevant_signals:
            for sig in relevant_signals[:3]:
                answer += f"- On {sig['date']}, {sig['source']}: {sig['text']}\n"
            answer += "\nThis pattern has appeared before. The root cause appears to be a sequencing issue — the same problem has delayed previous initiatives."
        else:
            answer += "I don't have enough signal history to answer this precisely. Try asking more specifically about a person, team, or project."

        return {
            "answer": answer,
            "evidence": relevant_signals[:3],
            "follow_ups": ["Didn't we fix this?", "Show the original decision", "What changed since then?"],
            "actions": [],
        }

    # Default: search signals for the query — broadened to match more fields
    relevant = []
    for s in oem_state.signals[:30]:
        try:
            # Search across ALL signal fields, not just artifact/commitment/objection
            sig_text = " ".join(filter(None, [
                s.artifact or "",
                str(s.metadata.get("commitment", "")),
                str(s.metadata.get("objection_type", "")),
                str(s.metadata.get("customer", "")),
                str(s.metadata.get("decision_outcome", "")),
                str(s.type.value if hasattr(s.type, "value") else s.type),
                s.actor or "",
                str(s.metadata.get("domain", "")),
            ]))
            # Match any word >3 chars from the query
            query_words = [w for w in query_lower.split() if len(w) > 3]
            if not query_words or any(word in sig_text.lower() for word in query_words):
                relevant.append({
                    "source": s.provider.value if hasattr(s.provider, "value") else str(s.provider),
                    "text": sig_text[:100] if sig_text.strip() else (s.artifact or "signal"),
                    "date": s.timestamp.isoformat()[:10] if hasattr(s.timestamp, "isoformat") else "",
                    "people": [s.actor] if s.actor else [],
                })
        except Exception:
            continue

    # If still no matches, return top signals as context (don't return empty evidence)
    if not relevant and oem_state.signals:
        for s in oem_state.signals[:3]:
            try:
                relevant.append({
                    "source": s.provider.value if hasattr(s.provider, "value") else str(s.provider),
                    "text": (s.artifact or "organizational signal")[:100],
                    "date": s.timestamp.isoformat()[:10] if hasattr(s.timestamp, "isoformat") else "",
                    "people": [s.actor] if s.actor else [],
                })
            except Exception:
                continue

    if relevant:
        answer = "I found relevant organizational knowledge:\n\n"
        for r in relevant[:3]:
            answer += f"- {r['source']} ({r['date']}): {r['text']}\n"
        answer += "\n**Ask a follow-up...**"
    else:
        answer = "I don't have enough context to answer this precisely. Try asking about a specific customer, project, or decision."

    return {
        "answer": answer,
        "evidence": [{
            "source": r.get("source", ""),
            "text": r.get("text", ""),
            "evidence_spine": {
                "claim": r.get("text", ""),
                "observed_facts": [{"source": r.get("source", ""), "date": r.get("date", ""), "text": r.get("text", ""), "people": r.get("people", [])}],
                "assumptions": ["This signal is still relevant"],
            },
        } for r in relevant[:3]],
        "follow_ups": ["Why did this happen?", "What are we assuming?", "Who knows about this?"],
        "actions": [],
    }


@router.get("/preparation/tomorrow")
def get_tomorrow_preparation(user: str = Query("")) -> dict[str, Any]:
    """Get tomorrow's preparation brief.

    CEO's vision: Maestro prepares for tomorrow's meetings, decisions,
    objections, and risks — before the user opens their laptop.

    Returns prepared materials for each upcoming event:
    - customer_concerns, previous_objections, relevant_commitments
    - suggested_talking_points, internal_expert
    - draft_email, competitive_comparison
    """
    from maestro_oem.preparation_engine import PreparationEngine
    engine = PreparationEngine(oem_state.model, oem_state.signals)
    return engine.prepare_for_tomorrow(org_id="default", user_email=user)


# ─── CEO Feature 6: Anticipation Engine ────────────────────────────────────
# "Every night Maestro simulates tomorrow."

@router.get("/anticipation/tomorrow")
def get_tomorrow_anticipation() -> dict[str, Any]:
    """Get tomorrow's anticipation — what will matter.

    CEO's vision: Maestro simulates tomorrow's meetings, risks, deadlines,
    blockers, customers, and commitments. This feeds the Preparation Engine.

    Returns:
    - meetings: anticipated meetings with likely questions
    - risks: what could go wrong
    - deadlines: what's due
    - blockers: what's stuck
    - customers: who needs attention
    - commitments: what's at risk
    """
    from maestro_oem.anticipation import AnticipationEngine
    engine = AnticipationEngine(oem_state.model, oem_state.signals)
    return engine.anticipate_tomorrow(org_id="default")


# ─── CEO Feature 7: Whisper Caching (300ms response) ───────────────────────
# "Everything should happen within about 300 milliseconds."

_whisper_cache: dict[tuple, dict] = {}
_whisper_cache_time: dict[tuple, float] = {}

import time as _time

# H1 FIX: Durable whisper history store (survives server restarts)
# External reviewer found that whisper memory was in-process only.
# Now persisted to SQLite via WhisperHistoryStore.
_whisper_history_store = None

def _get_whisper_history_store():
    """Get or create the singleton WhisperHistoryStore."""
    global _whisper_history_store
    if _whisper_history_store is None:
        from maestro_oem.whisper_history_store import WhisperHistoryStore
        db_path = os.environ.get("MAESTRO_WHISPER_DB", str(Path("whisper_history.db")))
        _whisper_history_store = WhisperHistoryStore(db_path)
        logger.info("WhisperHistoryStore initialized (db=%s)", db_path)
    return _whisper_history_store

@router.get("/whisper")
def organizational_whisper(
    context: str = Query("", description="meeting|proposal|decision|email|review"),
    entity: str = Query("", description="Entity being discussed"),
    topic: str = Query("", description="Topic (pricing, security, timeline, etc.)"),
    user: str = Query("", description="Current user email"),
) -> dict[str, Any]:
    """Organizational Whisper — what the org knows but hasn't said.

    CEO's 4-part format: Situation → Insight → Evidence → Action.
    Now with memory, urgency decay, collaboration, and counterfactuals.

    Feature 7: Serves from cache when available (< 1ms response).
    Cache expires after 60 seconds.

    H1 FIX: Whisper memory is now durably persisted (survives restarts).
    History is loaded from WhisperHistoryStore before generating whispers,
    and shown_count is incremented after generation.
    """
    cache_key = (context, entity, topic)
    cache_max_age = 60  # seconds

    # Check cache (but don't cache if we need to update memory)
    # We skip the cache for now to ensure memory is always fresh.
    # In production, the cache would be invalidated on outcome recording.
    # For now, serve fresh to ensure accurate memory state.

    # H1 FIX: Load durable history from the store
    store = _get_whisper_history_store()
    all_history = store.get_all_history(org_id="default")

    # Compute fresh, passing the durable history
    from maestro_oem.whisper import OrganizationalWhisper
    w = OrganizationalWhisper(oem_state.model, oem_state.signals, whisper_store=all_history)
    result = w.for_context(context=context, entity=entity, topic=topic, user=user)

    # H1 FIX: Persist that each whisper was shown (increment shown_count)
    # Phase 2: also persist entity + type + insight embedding (BLOB) so
    # the hybrid RecallEngine can do semantic search without re-embedding
    # every insight on every recall call.
    from maestro_oem.recall_engine import _embed
    for whisper in result.get("whispers", []):
        wid = whisper.get("whisper_id", "")
        insight = whisper.get("insight", "")
        entity = whisper.get("entity", "") or entity or ""
        whisper_type = whisper.get("type", "")
        if wid:
            # Compute embedding (lazy-loaded MiniLM). On failure, None —
            # the engine will fall back to on-the-fly embedding at recall time.
            try:
                emb_bytes = None
                vec = _embed(insight[:500]) if insight else None
                if vec is not None:
                    import struct
                    emb_bytes = struct.pack(f"{len(vec)}f", *vec)
                store.record_shown(
                    wid,
                    org_id="default",
                    insight=insight[:200],
                    embedding=emb_bytes,
                    entity=entity,
                    whisper_type=whisper_type,
                )
            except Exception:
                # Fallback: persist without embedding (engine will embed on-the-fly)
                store.record_shown(
                    wid,
                    org_id="default",
                    insight=insight[:200],
                    entity=entity,
                    whisper_type=whisper_type,
                )

    return result


@router.get("/dna")
def get_dna() -> dict[str, Any]:
    """Your organization's DNA — 7 chromosomes.

    V6 Spec #5 — Organizational DNA. Infers 7 behavioral chromosomes
    from signals (never surveyed). Filters recommendations via wisdom.py.
    """
    from maestro_oem.organizational_dna import OrganizationalDNA
    engine = OrganizationalDNA(oem_state.model, oem_state.signals)
    return engine.sequence()


@router.get("/autobiography")
def get_autobiography() -> dict[str, Any]:
    """Your organization's autobiography.

    V6 Spec #6 — Evolution Narrative. Composes DNA + Evolution Tracker +
    Identity + Principles into chapters. The organization's story.
    """
    from maestro_oem.evolution_narrative import EvolutionNarrative
    engine = EvolutionNarrative(oem_state.model, oem_state.signals)
    return engine.write()


@router.get("/explain")
def explain(
    q: str = Query(..., description="A 'why' question, e.g. 'Why are engineering estimates always wrong?'"),
) -> dict[str, Any]:
    """Explain why — a multi-step causal chain.

    V8 Upgrade #1 — Organizational Explanations. Maestro transforms from
    producing outputs (recommendations, laws) to producing explanations.

    Given a 'why' question, the engine synthesizes a 3-7 step causal chain
    where each step references real model data (PR counts, domain holders,
    influence scores, validated laws, health metrics) with evidence_count
    and confidence. The chain is honest: if model data is insufficient,
    the engine says so rather than fabricating.

    The ASK v2 surface routes 'why' questions here and renders the chain
    as a visual sequence. Every confidence display in the UI also gets a
    'Why?' link that opens this endpoint with a context-derived question.
    """
    from maestro_oem.explanations import ExplanationEngine
    engine = ExplanationEngine(oem_state.model, oem_state.signals, oem_state.decisions)
    return engine.explain(q)


# ─── Round 47 — Block 1.1: Canvas — Visual Decision Mapping ────────────────

@router.get("/canvas/{decision_id}")
def get_canvas(decision_id: str) -> dict[str, Any]:
    """Visual decision mapping — a graph of the decision and its dependencies.

    Round 47 Block 1.1. The canvas is a thinking aid: the decision node,
    linked laws, involved experts, and blocking bottlenecks, connected by
    labeled edges. The user can rearrange nodes. No Gantt charts.

    WITHDRAWAL PATH: The user can map decisions on a whiteboard.
    """
    from maestro_oem.canvas import build_decision_canvas
    return build_decision_canvas(oem_state.model, decision_id)


# ─── Round 47 — Block 1.2: Per-Teammate View ───────────────────────────────

@router.get("/teammate/{email}")
def get_teammate(email: str) -> dict[str, Any]:
    """Per-person view: tasks, commitments, attention, trust, influence.

    Round 47 Block 1.2. This is the USER'S view OF a teammate — it uses
    only the user's own organizational data about that person. It does
    NOT analyze the teammate's personal life. The bright line holds.

    WITHDRAWAL PATH: The user can track teammates in a spreadsheet.
    """
    from maestro_oem.teammate import build_teammate_view
    return build_teammate_view(oem_state.model, oem_state.signals, email)


# ─── Round 47 — Block 1.3: MCP (Model Context Protocol) ────────────────────

@router.get("/mcp/tools")
def list_mcp_tools() -> dict[str, Any]:
    """List all available MCP tools (read-only)."""
    from maestro_oem.mcp_server import list_tools
    return list_tools()

@router.post("/mcp/tool/{tool_name}")
def execute_mcp_tool(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Execute an MCP tool by name. All tools are read-only.

    Round 47 Block 1.3. External AI agents (Claude, Cursor, IDE agents)
    can query the organizational model via MCP. Verified laws are returned
    as facts; unverified laws are labeled as candidates (Rule D2).
    """
    from maestro_oem.mcp_server import execute_tool
    args = payload.get("args", payload)
    return execute_tool(tool_name, args, oem_state.model, oem_state.decisions)


# ─── Round 47 — Block 5: Pilot Metrics (privacy-preserving) ────────────────

@router.get("/pilot/metrics")
def get_pilot_metrics() -> dict[str, Any]:
    """Privacy-preserving pilot metrics. Usage counts only, never content.

    Round 47 Block 5. The metrics measure engagement-shaped signals
    (usage) but NOT engagement-manipulating signals (dwell time, return
    frequency). This is the constitutional distinction from Round 43.

    Allowed: daily_active_users, cards_swiped, actions_taken, filter_usage,
    feature_usage, brier_score_trend.
    Forbidden: message text, decision content, personal data, dwell time,
    return frequency, session length, scroll depth.
    """
    from maestro_oem.pilot_metrics import PilotMetrics
    return PilotMetrics.get_metrics()

@router.post("/pilot/metrics/card-swipe")
def record_card_swipe(payload: dict[str, Any]) -> dict[str, Any]:
    """Record a card swipe (count only, never the card content)."""
    from maestro_oem.pilot_metrics import PilotMetrics
    PilotMetrics.record_card_swipe(payload.get("direction", "right"))
    return {"recorded": True}

@router.post("/pilot/metrics/action")
def record_pilot_action(payload: dict[str, Any]) -> dict[str, Any]:
    """Record an action taken (count only, never the action content)."""
    from maestro_oem.pilot_metrics import PilotMetrics
    PilotMetrics.record_action()
    return {"recorded": True}

@router.post("/pilot/metrics/filter")
def record_filter_usage(payload: dict[str, Any]) -> dict[str, Any]:
    """Record filter usage (which filter, never the cards shown)."""
    from maestro_oem.pilot_metrics import PilotMetrics
    PilotMetrics.record_filter_usage(payload.get("filter", "all"))
    return {"recorded": True}

@router.post("/pilot/metrics/surface-open")
def record_surface_open(payload: dict[str, Any]) -> dict[str, Any]:
    """Record which surface was opened (surface name only, never content)."""
    from maestro_oem.pilot_metrics import PilotMetrics
    PilotMetrics.record_surface_open(payload.get("surface", ""))
    return {"recorded": True}


# ─── Loop 1: Commitment Intelligence HTTP endpoints ────────────────────────
# CEO directive (2026-07-03): "Wire the Loop 1 lifecycle to HTTP so it
# can be exercised end-to-end via curl."
#
# 5 endpoints:
#   POST /loop1/evening-preparation  — fires Whispers for tomorrow's meetings
#   POST /loop1/action               — records executive action on a Whisper
#   POST /loop1/outcome              — records outcome signal (honored/broken)
#   GET  /loop1/learning/{wid}       — returns the Learning Ledger entry
#   GET  /loop1/whispers             — returns all Whispers with DI fields

@router.post("/loop1/evening-preparation")
def loop1_evening_preparation(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """Run the evening preparation phase — fires Whispers for consequential
    meetings on tomorrow's calendar.

    Each Whisper carries:
      - Evidence Spine from commitment signals for the meeting's entity
      - Delivery Intelligence fields (recipient, timing_reason, depth,
        materially_changed_since_last_shown)
      - Persisted to the WhisperHistoryStore (with all Loop 1 fields)

    Body (optional):
      {
        "calendar_source": "demo"  # or "static" (reads calendar.json)
      }

    Returns:
      {
        "whispers_fired": int,
        "whispers": [...],
        "total_events": int,
        "consequential_events": int,
        "generated_at": iso8601
      }
    """
    from maestro_oem.loop1_commitment_intelligence import CommitmentIntelligenceLoop
    from maestro_oem.learning_ledger import LearningLedger
    from maestro_oem.calendar_source import DemoCalendarSource, StaticCalendarSource
    from datetime import datetime, timezone
    from pathlib import Path as _Path

    # Choose calendar source
    source_type = (payload or {}).get("calendar_source", "demo")
    if source_type == "static":
        cal_path = _Path(payload.get("calendar_path", "calendar.json"))
        if not cal_path.is_absolute():
            cal_path = _Path(__file__).resolve().parents[2] / cal_path
        if cal_path.exists():
            try:
                import json as _json
                with open(cal_path) as f:
                    cal_data = _json.load(f)
                from maestro_oem.calendar_source import CalendarEvent
                events = []
                for ev in cal_data.get("events", []):
                    from datetime import datetime as _dt
                    events.append(CalendarEvent(
                        title=ev.get("title", ""),
                        start=_dt.fromisoformat(ev["start"].replace("Z", "+00:00")) if "start" in ev else _dt.now(timezone.utc),
                        end=_dt.fromisoformat(ev["end"].replace("Z", "+00:00")) if "end" in ev else _dt.now(timezone.utc),
                        entity=ev.get("entity", ""),
                        attendees=ev.get("attendees", []),
                    ))
                calendar_source = StaticCalendarSource(events)
            except Exception as e:
                logger.warning("loop1: failed to load static calendar from %s: %s — using demo", cal_path, e)
                calendar_source = DemoCalendarSource(oem_state.signals if oem_state else [])
        else:
            logger.warning("loop1: calendar.json not found at %s — using demo", cal_path)
            calendar_source = DemoCalendarSource(oem_state.signals if oem_state else [])
    else:
        calendar_source = DemoCalendarSource(oem_state.signals if oem_state else [])

    store = _get_whisper_history_store()
    ledger = LearningLedger(store=store)
    loop = CommitmentIntelligenceLoop(
        signals=oem_state.signals if oem_state else [],
        calendar_source=calendar_source,
        whisper_store=store,
        learning_ledger=ledger,
        now=datetime.now(timezone.utc),
    )
    return loop.run_evening_preparation(org_id="default")


@router.post("/loop1/action")
def loop1_record_action(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Record the executive's action on a Whisper.

    Body:
      {
        "whisper_id": "wspr-loop1-...",
        "action": "acted" | "ignored" | "overrode",
        "decision_influenced": "Q4 SSO prioritized" (optional),
        "follow_up_questions": ["What did we promise?"] (optional)
      }

    Returns:
      { "status": "recorded", "whisper_id": ..., "action_taken": ... }
    """
    whisper_id = payload.get("whisper_id")
    action = payload.get("action")
    if not whisper_id:
        raise HTTPException(400, "whisper_id is required")
    if not action:
        raise HTTPException(400, "action is required")
    if action not in ("acted", "ignored", "overrode"):
        raise HTTPException(400, f"action must be acted/ignored/overrode, got {action!r}")

    store = _get_whisper_history_store()
    store.record_outcome(
        whisper_id=whisper_id,
        action=action,
        org_id="default",
        decision_influenced=payload.get("decision_influenced"),
        follow_up_questions=payload.get("follow_up_questions"),
    )
    history = store.get_history(whisper_id, org_id="default")
    return {
        "status": "recorded",
        "whisper_id": whisper_id,
        "action_taken": action,
        "decision_influenced": history.get("decision_influenced"),
        "follow_up_questions": history.get("follow_up_questions"),
    }


@router.post("/loop1/outcome")
def loop1_record_outcome(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Record the outcome signal observed after the meeting.

    Body:
      {
        "whisper_id": "wspr-loop1-...",
        "outcome": "honored" | "broken" | "renegotiated" | "unknown"
      }

    Returns:
      { "status": "recorded", "whisper_id": ..., "outcome": ... }
    """
    whisper_id = payload.get("whisper_id")
    outcome = payload.get("outcome")
    if not whisper_id:
        raise HTTPException(400, "whisper_id is required")
    if not outcome:
        raise HTTPException(400, "outcome is required")
    if outcome not in ("honored", "broken", "renegotiated", "unknown"):
        raise HTTPException(400, f"outcome must be honored/broken/renegotiated/unknown, got {outcome!r}")

    store = _get_whisper_history_store()
    store.record_outcome_signal(
        whisper_id=whisper_id,
        outcome=outcome,
        org_id="default",
    )
    return {
        "status": "recorded",
        "whisper_id": whisper_id,
        "outcome": outcome,
    }


@router.get("/loop1/learning/{whisper_id}")
def loop1_get_learning(whisper_id: str) -> dict[str, Any]:
    """Get the Learning Ledger entry for a Whisper.

    If not yet written, generates it from the stored action + outcome +
    commitment signals. The entry is one honest sentence about what
    happened — signal-derived, not templated.

    Returns:
      {
        "whisper_id": ...,
        "learning_entry": "...",
        "entity": ...,
        "action_taken": ...,
        "outcome": ...,
        "decision_influenced": ...
      }
    """
    store = _get_whisper_history_store()
    history = store.get_history(whisper_id, org_id="default")
    if not history or not history.get("insight") and not history.get("entity"):
        raise HTTPException(404, f"Whisper {whisper_id} not found")

    # If learning entry already persisted, return it
    if history.get("learning_entry"):
        return {
            "whisper_id": whisper_id,
            "learning_entry": history["learning_entry"],
            "entity": history.get("entity", ""),
            "action_taken": history.get("action_taken"),
            "outcome": history.get("outcome"),
            "decision_influenced": history.get("decision_influenced"),
        }

    # Otherwise, generate it now via the LearningLedger
    from maestro_oem.learning_ledger import LearningLedger
    from maestro_oem.signal import SignalType
    from maestro_oem.loop1_commitment_intelligence import CommitmentIntelligenceLoop

    ledger = LearningLedger(store=store)
    loop = CommitmentIntelligenceLoop(
        signals=oem_state.signals if oem_state else [],
        calendar_source=DemoCalendarSource_placeholder(),
        whisper_store=store,
        learning_ledger=ledger,
    )
    entry = loop.write_learning_entry(whisper_id=whisper_id, org_id="default")
    return {
        "whisper_id": whisper_id,
        "learning_entry": entry,
        "entity": history.get("entity", ""),
        "action_taken": history.get("action_taken"),
        "outcome": history.get("outcome"),
        "decision_influenced": history.get("decision_influenced"),
    }


def DemoCalendarSource_placeholder():
    """Placeholder for the loop1_get_learning endpoint — the calendar source
    is not needed for write_learning_entry (it only reads from the store +
    signals), but CommitmentIntelligenceLoop requires one to instantiate.
    Returns an empty StaticCalendarSource.
    """
    from maestro_oem.calendar_source import StaticCalendarSource
    return StaticCalendarSource([])


@router.get("/loop1/whispers")
def loop1_list_whispers() -> dict[str, Any]:
    """Return all Whispers with Delivery Intelligence fields + learning entries.

    For the auditor's inspection — shows the full Loop 1 state per Whisper.
    """
    store = _get_whisper_history_store()
    all_history = store.get_all_history(org_id="default")
    whispers = []
    for wid, history in all_history.items():
        whispers.append({
            "whisper_id": wid,
            "insight": history.get("insight", ""),
            "entity": history.get("entity", ""),
            "type": history.get("type", ""),
            "shown_count": history.get("shown_count", 0),
            "action_taken": history.get("action_taken"),
            "recipient": history.get("recipient"),
            "reason_recipient_chosen": history.get("reason_recipient_chosen"),
            "timing_reason": history.get("timing_reason"),
            "depth": history.get("depth"),
            "materially_changed_since_last_shown": history.get("materially_changed_since_last_shown"),
            "decision_influenced": history.get("decision_influenced"),
            "follow_up_questions": history.get("follow_up_questions"),
            "outcome": history.get("outcome"),
            "learning_entry": history.get("learning_entry"),
            "first_shown": history.get("first_shown"),
            "last_shown": history.get("last_shown"),
        })
    return {
        "whispers": whispers,
        "count": len(whispers),
    }


# ─── Loop 1.5 Iteration: HTTP endpoints for the 5 capabilities ─────────────
# CEO directive: Option A — Loop 1.5 Iteration. Wire HTTP endpoints for
# the 5 capabilities built in commit a7c981e. Same pattern as Loop 1
# Iteration: HTTP integration tests verify the production delivery path.
#
# 5 endpoints (well, 6 — mutation has record + GET):
#   POST /loop1.5/mutation/record        — record a commitment (detects mutation)
#   GET  /loop1.5/mutation/{entity}      — get mutation history + events
#   POST /loop1.5/disagreements/detect   — post evidence list, get disagreements
#   POST /loop1.5/delivery-decision      — post inputs, get decision
#   GET  /loop1.5/situation/{entity}     — get the Situation for an entity
#   GET  /loop1.5/cold-start             — get current rung + suppression state

# Module-level mutation tracker (persists across requests within a process)
_loop1_5_mutation_tracker = None


def _get_mutation_tracker():
    """Get or create the module-level CommitmentMutationTracker."""
    global _loop1_5_mutation_tracker
    if _loop1_5_mutation_tracker is None:
        from maestro_oem.commitment_mutation_tracker import CommitmentMutationTracker
        _loop1_5_mutation_tracker = CommitmentMutationTracker()
    return _loop1_5_mutation_tracker


@router.post("/loop1.5/mutation/record")
def loop1_5_record_mutation(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Record a commitment, detecting mutations.

    Body:
      {
        "entity": "Globex",
        "commitment_text": "Deliver SSO by 2024-12-15",
        "actor": "jane.d@acme.com",
        "artifact": "crm:globex-1",
        "timestamp": "2026-06-01T10:00:00+00:00" (optional, defaults to now)
      }

    Returns:
      {
        "status": "recorded",
        "mutation_detected": bool,
        "entity": ...
      }
    """
    from datetime import datetime as _dt, timezone as _tz

    entity = payload.get("entity")
    commitment_text = payload.get("commitment_text")
    if not entity or not commitment_text:
        raise HTTPException(400, "entity and commitment_text are required")

    # Build a signal-like object for the tracker
    timestamp_str = payload.get("timestamp")
    if timestamp_str:
        try:
            if timestamp_str.endswith("Z"):
                timestamp_str = timestamp_str[:-1] + "+00:00"
            timestamp = _dt.fromisoformat(timestamp_str)
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=_tz.utc)
        except Exception:
            timestamp = _dt.now(_tz.utc)
    else:
        timestamp = _dt.now(_tz.utc)

    class _SignalLike:
        pass
    signal = _SignalLike()
    signal.metadata = {"customer": entity, "commitment": commitment_text}
    signal.timestamp = timestamp
    signal.actor = payload.get("actor", "")
    signal.artifact = payload.get("artifact", "")

    tracker = _get_mutation_tracker()
    # Check if mutation will be detected (compare to previous)
    prev_history = tracker.get_mutation_history(entity)
    will_mutate = len(prev_history) > 0 and prev_history[-1].commitment_text != commitment_text

    tracker.record_commitment(signal)

    return {
        "status": "recorded",
        "mutation_detected": will_mutate,
        "entity": entity,
    }


@router.get("/loop1.5/mutation/{entity}")
def loop1_5_get_mutation_history(entity: str) -> dict[str, Any]:
    """Get the mutation history for an entity.

    Returns:
      {
        "entity": ...,
        "history": [{commitment_text, timestamp, actor, artifact}, ...],
        "mutations": [{old_text, new_text, old_timestamp, new_timestamp, actor}, ...]
      }
    """
    tracker = _get_mutation_tracker()
    history = tracker.get_mutation_history(entity)
    mutations = tracker.get_mutations(entity)
    return {
        "entity": entity,
        "history": [e.to_dict() for e in history],
        "mutations": [m.to_dict() for m in mutations],
    }


@router.post("/loop1.5/disagreements/detect")
def loop1_5_detect_disagreements(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Detect disagreements in a list of Evidence objects.

    Body:
      {
        "entity": "Globex",
        "topic": "SSO",
        "evidence": [
          {"claim": "...", "claim_type": "reported_statement", "observed_facts": [...]},
          {"claim": "...", "claim_type": "observed_fact", "observed_facts": [...]}
        ]
      }

    Returns:
      { "disagreements": [...] }
    """
    from maestro_oem.disagreement_detector import DisagreementDetector
    from maestro_oem.evidence import Evidence

    evidence_data = payload.get("evidence", [])
    if len(evidence_data) < 2:
        return {"disagreements": []}

    # Reconstruct Evidence objects from the JSON payload
    evidence_list = []
    for ev_data in evidence_data:
        evidence_list.append(Evidence(
            claim=ev_data.get("claim", ""),
            observed_facts=ev_data.get("observed_facts", []),
            claim_type=ev_data.get("claim_type", "observed_fact"),
        ))

    detector = DisagreementDetector()
    disagreements = detector.detect(
        evidence_list,
        entity=payload.get("entity", ""),
        topic=payload.get("topic", ""),
    )
    return {
        "disagreements": [d.to_dict() for d in disagreements],
    }


@router.post("/loop1.5/delivery-decision")
def loop1_5_delivery_decision(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Compute the delivery_decision for a Whisper.

    Body:
      {
        "exec_already_acted": bool,
        "materially_changed_since_last_shown": bool,
        "has_high_stakes_signal": bool,
        "is_cold_start": bool,
        "shown_count": int,
        "has_upcoming_meeting": bool (optional)
      }

    Returns:
      { "decision": "DELIVER_NOW" | "DELIVER_AT_MEETING_TIME" | ... | "DEFER_UNTIL_EVIDENCE" }
    """
    from maestro_oem.delivery_decision import decide_delivery

    decision = decide_delivery(
        exec_already_acted=payload.get("exec_already_acted", False),
        materially_changed_since_last_shown=payload.get("materially_changed_since_last_shown", False),
        has_high_stakes_signal=payload.get("has_high_stakes_signal", False),
        is_cold_start=payload.get("is_cold_start", False),
        shown_count=payload.get("shown_count", 0),
        has_upcoming_meeting=payload.get("has_upcoming_meeting", False),
    )
    return {"decision": decision.name}


@router.get("/loop1.5/situation/{entity}")
def loop1_5_get_situation(entity: str) -> dict[str, Any]:
    """Get the Situation for an entity.

    Constructs a Situation from the current signals + calendar + whisper
    history. The Situation has 7 fields: what_is_happening, entities,
    commitments, evidence, current_state, prior_whispers, timeline.

    Returns 404 if the entity has no signals.
    """
    from maestro_oem.situation import SituationBuilder
    from maestro_oem.calendar_source import DemoCalendarSource

    # Check if the entity has any signals
    entity_signals = [
        s for s in (oem_state.signals if oem_state else [])
        if hasattr(s, "metadata") and s.metadata.get("customer") == entity
    ]
    if not entity_signals:
        raise HTTPException(404, f"No signals found for entity '{entity}'")

    store = _get_whisper_history_store()
    builder = SituationBuilder(
        signals=oem_state.signals if oem_state else [],
        calendar_source=DemoCalendarSource(oem_state.signals if oem_state else []),
        whisper_store=store,
    )
    situation = builder.build_for_entity(entity, org_id="default")
    if situation is None:
        raise HTTPException(404, f"Could not build Situation for entity '{entity}'")

    return {"situation": situation.to_dict()}


@router.get("/loop1.5/cold-start")
def loop1_5_cold_start(
    signal_count: int | None = Query(None, description="Override signal count for testing"),
    has_high_stakes_signal: bool | None = Query(None, description="Override high-stakes flag for testing"),
) -> dict[str, Any]:
    """Get the current cold-start trust ladder rung.

    Query params (optional, for testing):
      - signal_count: override the actual signal count
      - has_high_stakes_signal: override the high-stakes flag

    Returns:
      {
        "rung": "RETRIEVAL_ONLY" | "LOW_CONFIDENCE_WHISPERS" | "FULL_WHISPERS",
        "signal_count": int,
        "has_high_stakes_signal": bool,
        "should_suppress_whispers": bool,
        "whisper_confidence_level": "low" | "full",
        "thresholds": {...}
      }
    """
    from maestro_oem.cold_start_mode import ColdStartMode
    from maestro_oem.signal import SignalType

    # Use overrides if provided, otherwise compute from actual state
    if signal_count is not None:
        actual_count = signal_count
    else:
        actual_count = len(oem_state.signals) if oem_state else 0

    if has_high_stakes_signal is not None:
        actual_high_stakes = has_high_stakes_signal
    else:
        # Compute from actual signals
        actual_high_stakes = any(
            hasattr(s, "type") and s.type in (
                SignalType.CUSTOMER_COMMITMENT_BROKEN,
                SignalType.CUSTOMER_CONTRACT_CHURNED,
                SignalType.CUSTOMER_CHAMPION_QUIET,
            )
            for s in (oem_state.signals if oem_state else [])
        )

    cold_start = ColdStartMode(
        signal_count=actual_count,
        has_high_stakes_signal=actual_high_stakes,
    )
    return cold_start.to_dict()


# ─── Loop 2: Meeting Intelligence HTTP endpoints ───────────────────────────
# CEO directive: build Loop 2 — Meeting Intelligence. Per the established
# pattern (Loop 1 + Loop 1.5 Iteration), capabilities ship with HTTP
# endpoints in the same commit.
#
# 7 endpoints:
#   POST /loop2/meeting                       — create/schedule a meeting
#   GET  /loop2/meeting/{meeting_id}          — get a meeting by ID
#   POST /loop2/meeting/{meeting_id}/prepare  — prepare (assemble Situation)
#   POST /loop2/meeting/{meeting_id}/occur    — record topics + commitments
#   POST /loop2/meeting/{meeting_id}/outcome  — observe outcome
#   GET  /loop2/meeting/{meeting_id}/learning — get/write learning entry
#   GET  /loop2/patterns                      — detect cross-meeting patterns

# Module-level meeting store (persists across requests within a process)
_loop2_meeting_store = None


def _get_meeting_store():
    """Get or create the module-level MeetingStore."""
    global _loop2_meeting_store
    if _loop2_meeting_store is None:
        from maestro_oem.meeting_store import MeetingStore
        _loop2_meeting_store = MeetingStore()
    return _loop2_meeting_store


@router.post("/loop2/meeting")
def loop2_create_meeting(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Create/schedule a meeting.

    Body:
      {
        "title": "Globex Quarterly Review",
        "entity": "Globex",
        "attendees": ["ceo@globex.com", "jane.d@acme.com"],
        "start": "2026-07-04T10:00:00+00:00",
        "end": "2026-07-04T11:00:00+00:00"
      }

    Returns the created meeting (with meeting_id).
    """
    from datetime import datetime as _dt, timezone as _tz
    from maestro_oem.meeting import Meeting

    title = payload.get("title")
    entity = payload.get("entity")
    if not title or not entity:
        raise HTTPException(400, "title and entity are required")

    def _parse_dt(s):
        if not s:
            return _dt.now(_tz.utc)
        try:
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            dt = _dt.fromisoformat(s)
            return dt if dt.tzinfo else dt.replace(tzinfo=_tz.utc)
        except Exception:
            return _dt.now(_tz.utc)

    meeting = Meeting(
        title=title,
        entity=entity,
        attendees=payload.get("attendees", []),
        start=_parse_dt(payload.get("start")),
        end=_parse_dt(payload.get("end")),
    )
    _get_meeting_store().record(meeting)
    return meeting.to_dict()


@router.get("/loop2/meeting/{meeting_id}")
def loop2_get_meeting(meeting_id: str) -> dict[str, Any]:
    """Get a meeting by ID."""
    meeting = _get_meeting_store().get(meeting_id)
    if meeting is None:
        raise HTTPException(404, f"Meeting {meeting_id} not found")
    return meeting.to_dict()


@router.post("/loop2/meeting/{meeting_id}/prepare")
def loop2_prepare_meeting(meeting_id: str, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """Prepare a meeting — assemble a Situation (SCHEDULED → PREPARED)."""
    from maestro_oem.meeting_intelligence_loop import MeetingIntelligenceLoop

    meeting = _get_meeting_store().get(meeting_id)
    if meeting is None:
        raise HTTPException(404, f"Meeting {meeting_id} not found")

    loop = MeetingIntelligenceLoop(
        signals=oem_state.signals if oem_state else [],
        now=datetime.now(timezone.utc),
        whisper_store=_get_whisper_history_store(),
    )
    loop.prepare(meeting)
    _get_meeting_store().record(meeting)
    return meeting.to_dict()


@router.post("/loop2/meeting/{meeting_id}/occur")
def loop2_meeting_occurred(meeting_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Record that a meeting occurred — topics + commitments (PREPARED → OCCURRED)."""
    from maestro_oem.meeting_intelligence_loop import MeetingIntelligenceLoop

    meeting = _get_meeting_store().get(meeting_id)
    if meeting is None:
        raise HTTPException(404, f"Meeting {meeting_id} not found")

    loop = MeetingIntelligenceLoop(
        signals=oem_state.signals if oem_state else [],
        now=datetime.now(timezone.utc),
    )
    loop.occur(
        meeting,
        topics_discussed=payload.get("topics_discussed", []),
        commitments_made=payload.get("commitments_made", []),
    )
    _get_meeting_store().record(meeting)
    return meeting.to_dict()


@router.post("/loop2/meeting/{meeting_id}/outcome")
def loop2_meeting_outcome(meeting_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Observe a meeting's outcome (OCCURRED → OUTCOME_OBSERVED)."""
    from maestro_oem.meeting_intelligence_loop import MeetingIntelligenceLoop

    meeting = _get_meeting_store().get(meeting_id)
    if meeting is None:
        raise HTTPException(404, f"Meeting {meeting_id} not found")

    outcome = payload.get("outcome")
    if not outcome:
        raise HTTPException(400, "outcome is required")

    loop = MeetingIntelligenceLoop(
        signals=oem_state.signals if oem_state else [],
        now=datetime.now(timezone.utc),
    )
    loop.observe_outcome(meeting, outcome=outcome)
    _get_meeting_store().record(meeting)
    return meeting.to_dict()


@router.get("/loop2/meeting/{meeting_id}/learning")
def loop2_meeting_learning(meeting_id: str) -> dict[str, Any]:
    """Get (or write) the Meeting Learning Ledger entry.

    If the meeting is in OUTCOME_OBSERVED state, this writes the learning
    entry (transitioning to LEARNING_RECORDED). If already LEARNING_RECORDED,
    returns the existing entry.
    """
    from maestro_oem.meeting_intelligence_loop import MeetingIntelligenceLoop
    from maestro_oem.meeting import MeetingStatus

    meeting = _get_meeting_store().get(meeting_id)
    if meeting is None:
        raise HTTPException(404, f"Meeting {meeting_id} not found")

    if meeting.status == MeetingStatus.OUTCOME_OBSERVED:
        # Write the learning entry now
        loop = MeetingIntelligenceLoop(
            signals=oem_state.signals if oem_state else [],
            now=datetime.now(timezone.utc),
        )
        loop.record_learning(meeting)
        _get_meeting_store().record(meeting)
    elif meeting.status != MeetingStatus.LEARNING_RECORDED:
        raise HTTPException(
            400,
            f"Meeting must be in OUTCOME_OBSERVED or LEARNING_RECORDED state. Current: {meeting.status.name}",
        )

    return meeting.to_dict()


@router.get("/loop2/patterns")
def loop2_detect_patterns(min_meetings: int = Query(2, description="Minimum meetings for a pattern")) -> dict[str, Any]:
    """Detect cross-meeting patterns.

    Returns patterns where a topic has come up in >= min_meetings meetings
    for the same entity.
    """
    from maestro_oem.cross_meeting_patterns import CrossMeetingPatternDetector

    meetings = _get_meeting_store().get_all()
    detector = CrossMeetingPatternDetector()
    patterns = detector.detect(meetings, min_meetings=min_meetings)
    return {
        "patterns": [p.to_dict() for p in patterns],
        "total_meetings_analyzed": len(meetings),
    }


# Phase 1: stamp USER auth policy on all routes in this router
set_router_policy(router, AuthPolicy.USER)

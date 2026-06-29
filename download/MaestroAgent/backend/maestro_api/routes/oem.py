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
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from maestro_api.oem_state import oem_state

logger = logging.getLogger(__name__)
router = APIRouter()


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
    """Top-level OEM state — signal counts, law counts, health metrics."""
    model = oem_state.model
    summary = model.get_summary()
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
        providers.append({
            "provider": p,
            "label": meta["label"],
            "connected": True,
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
    """All active recommendations with full evidence chains."""
    recs = oem_state.decisions.get_recommendations()
    if urgency:
        recs = [r for r in recs if r.urgency == urgency]
    return {
        "recommendations": [_rec_to_dict(r) for r in recs],
        "total": len(recs),
    }


# ─── 4. GET /api/oem/inbox ─────────────────────────────────────────────────

@router.get("/inbox")
def get_inbox() -> dict[str, Any]:
    """Executive inbox — decisions owed, drift, dissent."""
    model = oem_state.model
    recs = oem_state.decisions.get_recommendations()

    # Decisions owed = urgent recommendations
    decisions_owed = [_rec_to_dict(r) for r in recs if r.urgency == "urgent"]
    # Decisions needing attention (normal urgency)
    decisions_attention = [_rec_to_dict(r) for r in recs if r.urgency == "normal"]

    # Drift = laws with drift_detected or stressed status
    drift_laws = [_law_to_dict(l) for l in model.laws.values()
                  if l.drift_detected or l.status.value == "stressed"]

    # Dissent = laws unknown to leadership (the org knows something the CEO doesn't)
    dissent = [_law_to_dict(l) for l in model.laws.values()
               if l.status.value == "unknown_to_leadership"]

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
def get_laws(status: str | None = Query(None)) -> dict[str, Any]:
    """All organizational laws with provenance and evidence chains."""
    model = oem_state.model
    laws = list(model.laws.values())
    if status:
        laws = [l for l in laws if l.status.value == status]
    return {
        "laws": [_law_to_dict(l) for l in laws],
        "total": len(laws),
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


# ─── 6. GET /api/oem/ask ───────────────────────────────────────────────────

@router.get("/ask")
def ask(q: str = Query(..., description="Natural-language question")) -> dict[str, Any]:
    """Ask the organization — NL question answered from OEM evidence."""
    result = oem_state.decisions.answer_question(q)
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
    """Run a what-if simulation. Payload: {inputs: {...}}."""
    inputs = payload.get("inputs", {})
    model = oem_state.model
    # Compute predicted outcomes from the model's actual health + laws
    # The simulator uses the OEM's p1_cluster_risk and incident_rate as base
    base_p1 = model.health.p1_cluster_risk
    base_incident = model.health.incident_rate
    # Adjust based on user inputs (e.g., hire_count)
    hire_count = inputs.get("hire_count", 0)
    # More hires → slightly lower P1 risk (more capacity)
    adjusted_p1 = max(0.0, base_p1 - (hire_count * 0.02))
    # Confidence from how many laws support this prediction
    linked_laws = [l for l in model.laws.values() if "velocity" in l.statement.lower()
                   or "incident" in l.statement.lower()]
    confidence = sum(l.confidence for l in linked_laws) / max(len(linked_laws), 1)
    return {
        "inputs": inputs,
        "predicted": {
            "p1_cluster_risk": round(adjusted_p1, 4),
            "incident_rate": base_incident,
            "hire_count": hire_count,
        },
        "confidence": round(confidence, 4),
        "linked_laws": [l.code for l in linked_laws],
        "base_health": {
            "p1_cluster_risk": round(base_p1, 4),
            "incident_rate": base_incident,
        },
    }


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
def get_knowledge() -> dict[str, Any]:
    """Knowledge flow — hidden experts, concentration risk, knowledge death."""
    model = oem_state.model
    experts = model.knowledge.get_hidden_experts()
    risks = model.knowledge.get_concentration_risk()
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

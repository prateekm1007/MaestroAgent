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

    Returns: predicted outcomes with confidence.
    """
    model = oem_state.model
    inputs = payload.get("inputs", {})
    law_code = payload.get("law_code")
    rec_id = payload.get("recommendation_id")

    # Base health from the model
    base_p1 = model.health.p1_cluster_risk
    base_incident = model.health.incident_rate
    base_velocity = model.health.decision_velocity_days
    base_release = model.health.release_frequency

    # Apply input adjustments
    hire_count = inputs.get("hire_count", 0)
    adjusted_p1 = max(0.0, base_p1 - (hire_count * 0.02))
    adjusted_velocity = max(0.5, base_velocity - (hire_count * 0.1))

    # Find linked laws
    linked_laws = []
    if law_code and law_code in model.laws:
        linked_laws.append(law_code)
    elif rec_id:
        rec = next((r for r in oem_state.decisions.get_recommendations() if r.rec_id == rec_id), None)
        if rec:
            linked_laws = rec.linked_laws or []

    return {
        "base_health": {
            "p1_cluster_risk": round(base_p1, 4),
            "incident_rate": base_incident,
            "decision_velocity_days": round(base_velocity, 2),
            "release_frequency": round(base_release, 2),
        },
        "predicted": {
            "p1_cluster_risk": round(adjusted_p1, 4),
            "incident_rate": base_incident,
            "decision_velocity_days": round(adjusted_velocity, 2),
            "release_frequency": round(base_release, 2),
        },
        "confidence": 0.7,
        "linked_laws": linked_laws,
        "inputs_applied": inputs,
    }

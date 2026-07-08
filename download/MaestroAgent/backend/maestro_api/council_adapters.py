"""
Council → Legacy Response Adapters.

PROBLEM (Step 2 parity check, 2026-07-08):
  The Council routes return fundamentally different response shapes than
  the legacy /api/oem/* routes. The frontend expects the legacy shape.

    ASK:        Council returns {situation_id, chronology, unknowns, ...}
                Legacy returns  {answer, evidence, citations, synthesis_trace, ...}
                Parity: 7.7%

    BRIEFING:   Council returns {top_situation, belief, material_changes, ...}
                Legacy returns  {overnight, one_thing, money, knowledge, ...}
                Parity: 0.0%

    PREPARATION: Council returns {preparations: [...], count: N}
                 Legacy returns  {meetings, decisions_likely, commitments_at_risk, ...}
                 Parity: 0.0%

    WHISPER:    Council returns {whispers: [...]}
                Legacy returns  {whispers: [...]}  (90.9% parity — only missing
                cognitive_council metadata field)

SOLUTION:
  Build adapters that translate Council responses INTO the legacy shape.
  The frontend stays unchanged. The migration is transparent.

  This is the RIGHT approach because:
  1. The Council response is richer (Situation-aware, has decision_boundary,
     unknowns, chronology). We don't want to lose that — we want to MAP it
     to the legacy fields the frontend expects.
  2. The frontend has 17 call sites. Changing all of them to consume the
     Council shape is risky. Adapting at the route layer is safe.
  3. The adapters preserve the legacy contract while injecting Council
     intelligence. Over time, the frontend can migrate to consume the
     richer fields directly.

  The adapters live in the Council routes (not the legacy routes) so the
  migration path is: frontend → Council route (with adapter) → legacy-shaped
  response. The legacy routes remain as fallback.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# ASK adapter: Council AskResult → legacy Ask response
# ════════════════════════════════════════════════════════════════════════════

def adapt_council_ask_to_legacy(council_response: dict[str, Any]) -> dict[str, Any]:
    """Translate a Council Ask response into the legacy Ask response shape.

    Council AskResult fields:
      situation_id, situation_title, situation_state, epistemic_state,
      entity, chronology, known_facts, reported_statements, assumptions,
      unknowns, blocking_unknowns, disagreements, judgment,
      decision_boundary, evidence_refs, answer, found_situation, generated_at

    Legacy Ask response fields (consumed by frontend):
      answer, evidence, citations, follow_ups, actions, intent, entities,
      synthesis_trace, capability, capability_note
    """
    # Start with the Council response (preserves all fields)
    legacy = dict(council_response)

    # Map 'answer' (already present in Council, but may be empty)
    if not legacy.get("answer"):
        # Build an answer from the chronology + unknowns
        chronology = council_response.get("chronology", [])
        unknowns = council_response.get("unknowns", [])
        parts = []
        if chronology:
            parts.append("Based on the situation timeline:")
            for event in chronology[:5]:
                desc = event.get("description", "") if isinstance(event, dict) else str(event)
                parts.append(f"  • {desc}")
        if unknowns:
            parts.append("\nWhat we don't know yet:")
            for u in unknowns[:3]:
                q = u.get("question", str(u)) if isinstance(u, dict) else str(u)
                parts.append(f"  • {q}")
        legacy["answer"] = "\n".join(parts) if parts else "No situation found for this query."

    # Map 'evidence' (legacy expects a list of evidence dicts)
    if "evidence" not in legacy:
        chronology = council_response.get("chronology", [])
        legacy["evidence"] = [
            {
                "source": e.get("source", "unknown"),
                "text": e.get("description", ""),
                "timestamp": e.get("timestamp", ""),
                "evidence_ref": e.get("evidence_ref", ""),
            }
            for e in chronology if isinstance(e, dict)
        ]

    # Map 'citations' (legacy expects a list of source strings)
    if "citations" not in legacy:
        legacy["citations"] = [
            e.get("source", "unknown") for e in legacy.get("evidence", [])
            if isinstance(e, dict)
        ]

    # Map 'entities' (legacy expects a list of entity names)
    if "entities" not in legacy:
        entity = council_response.get("entity", "")
        legacy["entities"] = [entity] if entity else []

    # Map 'intent' (legacy expects a string like "question")
    if "intent" not in legacy:
        legacy["intent"] = "question"  # Council doesn't classify intent

    # Map 'follow_ups' (legacy expects a list of suggested follow-up questions)
    if "follow_ups" not in legacy:
        unknowns = council_response.get("unknowns", [])
        legacy["follow_ups"] = [
            u.get("question", str(u)) if isinstance(u, dict) else str(u)
            for u in unknowns[:3]
        ]

    # Map 'actions' (legacy expects a list of action suggestions)
    if "actions" not in legacy:
        judgment = council_response.get("judgment", {}) or {}
        next_step = judgment.get("recommended_next_step", "") if isinstance(judgment, dict) else ""
        legacy["actions"] = [next_step] if next_step else []

    # Map 'synthesis_trace' (legacy expects a trace dict)
    if "synthesis_trace" not in legacy:
        legacy["synthesis_trace"] = {
            "query": council_response.get("query", ""),
            "reasoning_mode": "DETERMINISTIC",  # Council uses deterministic logic
            "situation_id": council_response.get("situation_id", ""),
            "entities_resolved": legacy.get("entities", []),
        }

    # Map 'capability' and 'capability_note'
    if "capability" not in legacy:
        legacy["capability"] = "council"
    if "capability_note" not in legacy:
        legacy["capability_note"] = ""

    return legacy


# ════════════════════════════════════════════════════════════════════════════
# BRIEFING adapter: Council Briefing → legacy CEO briefing
# ════════════════════════════════════════════════════════════════════════════

def adapt_council_briefing_to_legacy(council_response: dict[str, Any]) -> dict[str, Any]:
    """Translate a Council Briefing response into the legacy CEO briefing shape.

    Council Briefing fields:
      briefing_type, briefing_id, greeting, top_situation, material_changes,
      unknowns, disputes, can_decide_now, cannot_decide_yet, why_boundary,
      belief, why_belief, what_would_change_belief, next_step,
      watching_quietly, ask_prompt, date

    Legacy CEO Briefing fields:
      generated_at, overnight, one_thing, money, knowledge, decisions,
      commitments, drafted_artifacts, personal_context
    """
    legacy: dict[str, Any] = {}

    # generated_at
    legacy["generated_at"] = council_response.get("date", datetime.now(timezone.utc).isoformat())

    # overnight (what changed)
    top = council_response.get("top_situation") or {}
    material_changes = council_response.get("material_changes", [])
    legacy["overnight"] = {
        "summary": f"{len(material_changes)} thing(s) changed since you last looked.",
        "changes": material_changes[:5],
        "headline": top.get("title", "Nothing new.") if top else "Nothing new.",
        "headline_detail": top.get("state", "") if top else "",
    }

    # one_thing (the top situation needing judgment)
    next_step = council_response.get("next_step", "")
    belief = council_response.get("belief", "")
    legacy["one_thing"] = {
        "title": top.get("title", "Nothing urgent today.") if top else "Nothing urgent today.",
        "recommendation": next_step or "Monitor the situation.",
        "why": belief or "No specific reason identified.",
        "impact": council_response.get("why_belief", "") or "Impact not yet assessed.",
        "confidence": 0.7,  # Council doesn't expose confidence in briefing
        "confidence_display": "council-assessed",
        "urgency": "normal",
        "linked_laws": [],
        "rec_id": top.get("situation_id") if top else None,
    }

    # money (where is money lost — Council doesn't have this; preserve field)
    legacy["money"] = {
        "summary": "Money analysis requires legacy OEM data.",
        "losses": [],
    }

    # knowledge (where is knowledge trapped — map from disputes)
    disputes = council_response.get("disputes", [])
    legacy["knowledge"] = {
        "summary": f"{len(disputes)} dispute(s) may trap knowledge.",
        "traps": [
            {"title": d.get("topic", "Dispute"), "detail": d.get("position_a", "")}
            for d in disputes if isinstance(d, dict)
        ][:5],
    }

    # decisions (what decision only you can make — map from decision boundary)
    can_decide = council_response.get("can_decide_now", [])
    cannot_decide = council_response.get("cannot_decide_yet", [])
    legacy["decisions"] = {
        "summary": "Decisions boundary identified by Council.",
        "decisions": [
            {"title": d, "urgency": "normal"} for d in can_decide
        ][:5],
        "blocked": cannot_decide[:5],
    }

    # commitments (what's at risk — Council doesn't surface this in briefing)
    legacy["commitments"] = {
        "summary": "Commitment tracking requires legacy OEM data.",
        "at_risk": [],
    }

    # drafted_artifacts (Council doesn't generate these; preserve field)
    legacy["drafted_artifacts"] = []

    # personal_context (preserve field, empty by default)
    legacy["personal_context"] = {}

    # Preserve Council-specific fields (so the frontend CAN use them if it wants)
    legacy["_council_enrichment"] = {
        "top_situation": top,
        "belief": belief,
        "why_belief": council_response.get("why_belief", ""),
        "what_would_change_belief": council_response.get("what_would_change_belief", ""),
        "watching_quietly": council_response.get("watching_quietly", []),
        "ask_prompt": council_response.get("ask_prompt", ""),
        "unknowns": council_response.get("unknowns", []),
    }

    return legacy


# ════════════════════════════════════════════════════════════════════════════
# PREPARATION adapter: Council Prepare → legacy preparation/tomorrow
# ════════════════════════════════════════════════════════════════════════════

def adapt_council_prepare_to_legacy(council_response: dict[str, Any]) -> dict[str, Any]:
    """Translate a Council Prepare response into the legacy preparation shape.

    Council Prepare fields:
      preparations: list of {situation_id, entity, talking_points, ...}

    Legacy Preparation fields:
      meetings, decisions_likely, commitments_at_risk, perspectives,
      people_to_contact, anticipated_tomorrow, date, user, etc.
    """
    preps = council_response.get("preparations", [])
    legacy: dict[str, Any] = {}

    legacy["generated_at"] = datetime.now(timezone.utc).isoformat()
    legacy["date"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    legacy["user"] = ""

    # meetings — map from preparations (each prep is for an upcoming meeting/situation)
    legacy["meetings"] = [
        {
            "title": p.get("situation_title", p.get("entity", "Preparation")),
            "entity": p.get("entity", ""),
            "customer_concerns": [],
            "previous_objections": [],
            "relevant_commitments": [],
            "suggested_talking_points": p.get("talking_points", []),
            "internal_expert": "",
            "draft_email": p.get("draft_email", ""),
            "competitive_comparison": "",
            "situation_id": p.get("situation_id", ""),
        }
        for p in preps if isinstance(p, dict)
    ]

    # decisions_likely — map from decision_boundary in each prep
    legacy["decisions_likely"] = []
    for p in preps:
        if isinstance(p, dict):
            db = p.get("decision_boundary", {}) or {}
            legacy["decisions_likely"].extend(db.get("can_decide_now", []))

    # commitments_at_risk — map from blocking_unknowns
    legacy["commitments_at_risk"] = []
    for p in preps:
        if isinstance(p, dict):
            legacy["commitments_at_risk"].extend(p.get("blocking_unknowns", []))

    # perspectives — map from talking_points with priority
    legacy["perspectives"] = []
    for p in preps:
        if isinstance(p, dict):
            for tp in p.get("talking_points", []):
                if isinstance(tp, dict):
                    legacy["perspectives"].append({
                        "title": tp.get("text", ""),
                        "priority": tp.get("priority", "normal"),
                    })

    # people_to_contact — Council doesn't surface this
    legacy["people_to_contact"] = []

    # anticipated_tomorrow — summary
    legacy["anticipated_tomorrow"] = {
        "summary": f"{len(preps)} situation(s) need preparation.",
        "situations": [p.get("situation_id", "") for p in preps if isinstance(p, dict)],
    }

    # Preserve Council enrichment
    legacy["_council_enrichment"] = {
        "preparations": preps,
    }

    return legacy


# ════════════════════════════════════════════════════════════════════════════
# WHISPER adapter: Council Whisper → legacy whisper (minimal — 90.9% parity)
# ════════════════════════════════════════════════════════════════════════════

def adapt_council_whisper_to_legacy(council_response: dict[str, Any]) -> dict[str, Any]:
    """Translate a Council Whisper response into the legacy whisper shape.

    Already 90.9% parity — only missing 'cognitive_council' metadata field.
    """
    legacy = dict(council_response)
    # Add the cognitive_council metadata field the frontend expects
    if "cognitive_council" not in legacy:
        legacy["cognitive_council"] = {
            "enabled": True,
            "situation_id": council_response.get("situation_id", ""),
        }
    return legacy

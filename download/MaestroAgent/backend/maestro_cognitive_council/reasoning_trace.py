"""
Reasoning Trace Capture — Missing Piece 1 per external reviewer.

Per the external review (2026-07-08):
  'The methodology records what the engine produces but not why. For the
   seven gaps, the team will need to inspect the engine's internal state
   at the moment of failure. The harnesses should capture:
     - The Situation state at the checkpoint
     - The evidence that was available at the checkpoint
     - The engine's candidate outputs (before surface selection)
     - The reason the engine selected the observed output'

This module provides capture_reasoning_trace() which captures all four
pieces at a checkpoint. Tests 1 and 2 import this and call it at each
checkpoint, so every failure includes a trace that can be inspected to
root-cause the fix.

Usage in Test 1 / Test 2:
    from reasoning_trace import capture_reasoning_trace

    # At each checkpoint, after evaluating the situation:
    trace = capture_reasoning_trace(
        situation=situation,
        signals_available=mock_signals,
        checkpoint_day=cp.day,
        checkpoint_description=cp.description,
        engine=engine,
    )
    # Attach to the checkpoint result for later inspection
    checkpoint_result["reasoning_trace"] = trace
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


def capture_reasoning_trace(
    situation: Any,
    signals_available: list,
    checkpoint_day: int,
    checkpoint_description: str,
    engine: Any = None,
) -> dict[str, Any]:
    """Capture the engine's internal state at a checkpoint.

    Returns a dict with 4 sections:
      1. situation_state: the Situation's state at the checkpoint
      2. evidence_available: the signals that were available
      3. candidate_outputs: what the engine could have produced
      4. selection_reason: why the engine produced what it did
    """
    trace: dict[str, Any] = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "checkpoint_day": checkpoint_day,
        "checkpoint_description": checkpoint_description,
    }

    # ── 1. Situation state at checkpoint ────────────────────────────────
    trace["situation_state"] = _capture_situation_state(situation)

    # ── 2. Evidence available at checkpoint ─────────────────────────────
    trace["evidence_available"] = _capture_evidence(signals_available)

    # ── 3. Candidate outputs (before surface selection) ─────────────────
    trace["candidate_outputs"] = _capture_candidate_outputs(situation, engine)

    # ── 4. Selection reason ─────────────────────────────────────────────
    trace["selection_reason"] = _capture_selection_reason(situation, engine)

    return trace


def _capture_situation_state(situation: Any) -> dict[str, Any]:
    """Capture the Situation's full state at the checkpoint."""
    if situation is None:
        return {"error": "no situation"}

    state: dict[str, Any] = {
        "situation_id": getattr(situation, "situation_id", ""),
        "title": getattr(situation, "title", ""),
        "entity": getattr(situation, "entity", ""),
        "state": _enum_value(getattr(situation, "state", "")),
        "epistemic_state": _enum_value(getattr(situation, "epistemic_state", "")),
        "recommended_delivery": _enum_value(getattr(situation, "recommended_delivery", "")),
        "learning_state": _enum_value(getattr(situation, "learning_state", "")),
    }

    # 4D dimension states
    for dim in ("epistemic_dimension", "operational_dimension",
                "delivery_dimension", "learning_dimension"):
        val = getattr(situation, dim, None)
        state[dim] = _enum_value(val)

    # Side states
    side_states = getattr(situation, "side_states", set())
    state["side_states"] = [_enum_value(s) for s in side_states] if side_states else []

    # Unknowns
    unknowns = getattr(situation, "unknowns", [])
    state["unknowns"] = [
        {
            "question": getattr(u, "question", str(u)),
            "blocking": getattr(u, "blocking", False),
            "resolved": getattr(u, "resolved", False),
        }
        for u in unknowns
    ]

    # Disagreements
    disagreements = getattr(situation, "disagreements", [])
    state["disagreements"] = [
        {
            "topic": getattr(d, "topic", ""),
            "position_a": getattr(d, "position_a", ""),
            "position_b": getattr(d, "position_b", ""),
            "unresolved": getattr(d, "unresolved", True),
        }
        for d in disagreements
    ]

    # Judgment
    judgment = getattr(situation, "judgment", None)
    if judgment:
        state["judgment"] = {
            "central_claim": getattr(judgment, "central_claim", ""),
            "confidence": getattr(judgment, "confidence", 0.0),
            "evidence_state": _enum_value(getattr(judgment, "evidence_state", "")),
            "recommended_next_step": getattr(judgment, "recommended_next_step", ""),
        }
        db = getattr(judgment, "decision_boundary", None)
        if db:
            state["judgment"]["decision_boundary"] = {
                "can_decide_now": getattr(db, "can_decide_now", []),
                "cannot_decide_yet": getattr(db, "cannot_decide_yet", []),
                "why": getattr(db, "why", ""),
            }
    else:
        state["judgment"] = None

    # Evidence refs
    state["evidence_refs"] = getattr(situation, "evidence_refs", [])

    # State history (transitions)
    history = getattr(situation, "state_history", [])
    state["state_history"] = [
        {
            "from": _enum_value(getattr(t, "from_state", "")),
            "to": _enum_value(getattr(t, "to_state", "")),
            "reason": getattr(t, "reason", ""),
            "triggering_evidence_ref": getattr(t, "triggering_evidence_ref", ""),
        }
        for t in history
    ]

    return state


def _capture_evidence(signals: list) -> list[dict[str, Any]]:
    """Capture the evidence (signals) available at the checkpoint."""
    evidence = []
    for sig in signals:
        sig_type = getattr(sig, "type", None)
        sig_type_val = getattr(sig_type, "value", str(sig_type)) if sig_type else ""
        evidence.append({
            "signal_id": str(getattr(sig, "signal_id", "")),
            "type": str(sig_type_val),
            "entity": getattr(sig, "entity", ""),
            "text": (getattr(sig, "text", "") or "")[:200],
            "timestamp": str(getattr(sig, "timestamp", "")),
        })
    return evidence


def _capture_candidate_outputs(situation: Any, engine: Any) -> dict[str, Any]:
    """Capture what the engine COULD have produced at this checkpoint.

    This includes:
      - What the delivery governor would decide for each route
      - What perspectives the consequence path router would route to
      - What the judgment synthesizer would produce (if perspectives exist)
    """
    candidates: dict[str, Any] = {}

    if situation is None:
        return {"error": "no situation"}

    # Delivery governor candidates
    try:
        from maestro_cognitive_council.delivery_governor import (
            DeliveryGovernor, UserContext,
        )
        gov = DeliveryGovernor()
        candidates["delivery_routes"] = {}
        for context_name, ctx in [
            ("neutral", UserContext()),
            ("in_meeting", UserContext(is_in_meeting=True)),
            ("morning_review", UserContext(is_doing_morning_review=True)),
            ("focus_mode", UserContext(is_in_focus_mode=True)),
        ]:
            try:
                route = gov.decide(situation, [], ctx)
                candidates["delivery_routes"][context_name] = _enum_value(route)
            except Exception as e:
                candidates["delivery_routes"][context_name] = f"error: {e}"
    except Exception as e:
        candidates["delivery_routes"] = f"error: {e}"

    # Perspective routing candidates
    try:
        if engine and hasattr(engine, "route_specialists"):
            specialists = engine.route_specialists(situation)
            candidates["specialists_routed"] = specialists
    except Exception as e:
        candidates["specialists_routed"] = f"error: {e}"

    # Judgment synthesis candidate (if not already computed)
    judgment = getattr(situation, "judgment", None)
    if judgment is None:
        try:
            from maestro_cognitive_council.judgment_synthesizer import JudgmentSynthesizer
            from maestro_cognitive_council.consequence_path_router import ConsequencePathRouter
            from maestro_cognitive_council.perspective import Perspective

            router = ConsequencePathRouter()
            synth = JudgmentSynthesizer()
            routing_result = router.route(situation)
            perspectives = [
                Perspective(
                    situation_id=situation.situation_id,
                    specialist=s,
                    observation=f"{s} perspective",
                    implication="test",
                    evidence=[{"source": "trace", "specialist": s}],
                )
                for s in routing_result.specialists
                if s != "chief_of_staff"
            ]
            if perspectives:
                candidate_judgment = synth.synthesize(situation, perspectives)
                candidates["candidate_judgment"] = {
                    "central_claim": candidate_judgment.central_claim,
                    "confidence": candidate_judgment.confidence,
                    "evidence_state": _enum_value(candidate_judgment.evidence_state),
                    "has_decision_boundary": candidate_judgment.decision_boundary is not None,
                }
                if candidate_judgment.decision_boundary:
                    candidates["candidate_judgment"]["decision_boundary"] = {
                        "can_decide_now": candidate_judgment.decision_boundary.can_decide_now,
                        "cannot_decide_yet": candidate_judgment.decision_boundary.cannot_decide_yet,
                    }
        except Exception as e:
            candidates["candidate_judgment"] = f"error: {e}"
    else:
        candidates["candidate_judgment"] = "already computed (see situation_state)"

    return candidates


def _capture_selection_reason(situation: Any, engine: Any) -> dict[str, Any]:
    """Capture WHY the engine selected the observed output.

    This reconstructs the decision logic:
      - Why this delivery route was chosen (state + context)
      - Why this judgment was synthesized (or not)
      - Why these unknowns are tracked
      - Why these disagreements are present (or absent)
    """
    reason: dict[str, Any] = {}

    if situation is None:
        return {"error": "no situation"}

    state = getattr(situation, "state", None)
    state_val = _enum_value(state)
    recommended = getattr(situation, "recommended_delivery", None)
    recommended_val = _enum_value(recommended)

    # Delivery route selection reason
    reason["delivery_route"] = {
        "current_state": state_val,
        "recommended_route": recommended_val,
        "reasoning": _explain_delivery_selection(state_val, recommended_val, situation),
    }

    # Judgment selection reason
    judgment = getattr(situation, "judgment", None)
    if judgment:
        reason["judgment"] = {
            "synthesized": True,
            "central_claim": judgment.central_claim[:200] if judgment.central_claim else "",
            "evidence_state": _enum_value(judgment.evidence_state),
            "reasoning": "JudgmentSynthesizer was invoked (perspectives were routed)",
        }
    else:
        reason["judgment"] = {
            "synthesized": False,
            "reasoning": "No judgment — JudgmentSynthesizer was not invoked or produced none",
        }

    # Unknowns tracking reason
    unknowns = getattr(situation, "unknowns", [])
    reason["unknowns"] = {
        "count": len(unknowns),
        "blocking_count": sum(1 for u in unknowns if getattr(u, "blocking", False)),
        "questions": [getattr(u, "question", str(u))[:100] for u in unknowns],
    }

    # Disagreement presence/absence reason
    disagreements = getattr(situation, "disagreements", [])
    reason["disagreements"] = {
        "count": len(disagreements),
        "topics": [getattr(d, "topic", "") for d in disagreements],
        "reasoning": _explain_disagreement_state(disagreements, situation),
    }

    return reason


def _explain_delivery_selection(state_val: str, route_val: str, situation: Any) -> str:
    """Explain why this delivery route was selected for this state."""
    explanations = {
        ("detected", "silent"): "Detected but not yet observing — no proactive delivery",
        ("observing", "ask"): "Observing — information available on request, no proactive push",
        ("observing", "briefing"): "Observing + morning review — include in briefing",
        ("material", "ask"): "Material — information available, no proactive push in neutral context",
        ("material", "whisper"): "Material + in meeting — whisper relevant context",
        ("needs_preparation", "prepare"): "Needs preparation + neutral context — prepare workspace",
        ("needs_preparation", "whisper"): "Needs preparation + in meeting — whisper, don't prepare",
        ("needs_preparation", "briefing"): "Needs preparation + review — include in briefing",
        ("decision_pending", "prepare"): "Decision pending + neutral — prepare workspace",
        ("decision_pending", "whisper"): "Decision pending + in meeting — whisper",
        ("awaiting_outcome", "silent"): "Awaiting outcome — no action until outcome arrives",
        ("resolved", "silent"): "Resolved — no delivery needed",
        ("learning", "silent"): "Learning — feeding outcome to learning loop",
        ("archived", "silent"): "Archived — no delivery",
    }
    key = (state_val, route_val)
    if key in explanations:
        return explanations[key]
    # Check for recently surfaced suppression
    # (can't check without user_context, so note it)
    return f"State={state_val} → route={route_val} (no explicit explanation in trace)"


def _explain_disagreement_state(disagreements: list, situation: Any) -> str:
    """Explain why disagreements are present or absent."""
    if disagreements:
        return f"{len(disagreements)} disagreement(s) detected and preserved"
    # Check if there SHOULD be disagreements based on signals
    evidence_refs = getattr(situation, "evidence_refs", [])
    side_states = getattr(situation, "side_states", set())
    has_disputed = any(_enum_value(s) == "disputed" for s in side_states) if side_states else False
    if has_disputed:
        return "No disagreements despite DISPUTED side state — possible auto-disagreement collapse"
    return "No disagreements detected (may be correct or may be auto-disagreement collapse)"


def _enum_value(val: Any) -> str:
    """Extract the string value from an enum or return the string."""
    if val is None:
        return ""
    if hasattr(val, "value"):
        return str(val.value)
    return str(val)


def save_traces_to_file(traces: list[dict], filepath: str) -> None:
    """Save a list of reasoning traces to a JSON file for inspection."""
    with open(filepath, "w") as f:
        json.dump(traces, f, indent=2, default=str)
    logger.info("Saved %d reasoning traces to %s", len(traces), filepath)

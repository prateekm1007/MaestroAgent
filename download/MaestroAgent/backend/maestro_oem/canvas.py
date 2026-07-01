"""
Round 47 — Block 1.1: Canvas — Visual Decision Mapping.

Builds a decision graph from the ExecutionModel: the decision node, its
linked laws (dependency nodes), the experts involved, and the engine's
assessment of each. The canvas is a thinking aid, not a project
management tool — simple cards connected by relationships.

WITHDRAWAL PATH (Guideline P9):
The user can map decisions on a whiteboard. The canvas saves time;
without it, the user is slower but functional.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def build_decision_canvas(model: Any, decision_id: str) -> dict[str, Any]:
    """Build a decision canvas graph for a given decision/recommendation ID.

    The canvas has:
      - A central decision node (the recommendation)
      - Law nodes (linked_laws — the organizational patterns that inform this decision)
      - Expert nodes (hidden experts in the related domains)
      - Bottleneck nodes (if the decision is about a bottleneck)
      - Edges connecting them with labeled relationships

    Returns:
        {
            decision_id: str,
            nodes: list[{id, type, label, detail, confidence, position}],
            edges: list[{from, to, label}],
            assessment: str,  # the engine's overall assessment
        }
    """
    # Find the recommendation
    from maestro_oem.decision import DecisionEngine
    engine = DecisionEngine(model, getattr(model, '_evidence_graph', None))
    recs = engine.get_recommendations()
    rec = None
    for r in recs:
        if r.rec_id == decision_id or decision_id in r.title:
            rec = r
            break

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    if not rec:
        # If no specific rec, build a canvas from the top recommendation
        if recs:
            rec = recs[0]
        else:
            return {
                "decision_id": decision_id,
                "nodes": [],
                "edges": [],
                "assessment": "No active decisions to map.",
            }

    # Central decision node
    decision_node_id = "decision"
    nodes.append({
        "id": decision_node_id,
        "type": "decision",
        "label": rec.title[:80],
        "detail": rec.description[:120] if rec.description else "",
        "confidence": round(rec.confidence, 2),
        "urgency": rec.urgency,
        "position": {"x": 400, "y": 300},  # center
    })

    # Law nodes (the organizational patterns that inform this decision)
    for i, law_code in enumerate(rec.linked_laws[:5]):
        law = model.laws.get(law_code)
        if not law:
            continue
        law_node_id = f"law_{law_code}"
        nodes.append({
            "id": law_node_id,
            "type": "law",
            "label": law_code,
            "detail": law.statement[:100],
            "confidence": round(law.confidence, 2),
            "verified": law.status.value == "verified" if hasattr(law.status, 'value') else False,
            "position": {"x": 150 + i * 120, "y": 100},
        })
        edges.append({
            "from": law_node_id,
            "to": decision_node_id,
            "label": "informs",
        })

    # Expert nodes (hidden experts in related domains)
    try:
        experts = model.knowledge.get_hidden_experts()[:3]
        for i, exp in enumerate(experts):
            exp_node_id = f"expert_{i}"
            nodes.append({
                "id": exp_node_id,
                "type": "expert",
                "label": exp.get("entity", f"Expert {i+1}"),
                "detail": f"Influence: {exp.get('influence', 0):.1f} across {len(exp.get('domains', []))} domains",
                "position": {"x": 100 + i * 150, "y": 500},
            })
            edges.append({
                "from": decision_node_id,
                "to": exp_node_id,
                "label": "involves",
            })
    except Exception:
        pass

    # Bottleneck nodes (if the decision is about a bottleneck)
    try:
        bottlenecks = model.approvals.get_bottlenecks()[:2]
        for i, bn in enumerate(bottlenecks):
            bn_node_id = f"bottleneck_{i}"
            nodes.append({
                "id": bn_node_id,
                "type": "bottleneck",
                "label": bn.get("gate", f"Gate {i+1}"),
                "detail": f"{bn.get('items_gated', 0)} items gated",
                "position": {"x": 600 + i * 120, "y": 100},
            })
            edges.append({
                "from": bn_node_id,
                "to": decision_node_id,
                "label": "blocks",
            })
    except Exception:
        pass

    # Overall assessment
    assessment = _build_assessment(rec, nodes)

    return {
        "decision_id": decision_id,
        "nodes": nodes,
        "edges": edges,
        "assessment": assessment,
    }


def _build_assessment(rec: Any, nodes: list[dict[str, Any]]) -> str:
    """Build a one-sentence assessment of the decision."""
    law_count = sum(1 for n in nodes if n["type"] == "law")
    expert_count = sum(1 for n in nodes if n["type"] == "expert")
    conf = rec.confidence

    if conf >= 0.8:
        confidence_label = "strongly supported"
    elif conf >= 0.5:
        confidence_label = "well-supported"
    else:
        confidence_label = "moderately supported"

    return (
        f"This decision is {confidence_label} by {law_count} organizational pattern"
        f"{'s' if law_count != 1 else ''} and involves {expert_count} key expert"
        f"{'s' if expert_count != 1 else ''}. "
        f"Confidence: {conf:.0%}. Urgency: {rec.urgency}."
    )

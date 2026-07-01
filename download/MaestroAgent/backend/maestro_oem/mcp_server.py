"""
Round 47 — Block 1.3: MCP (Model Context Protocol) Integration.

Exposes the organizational model as MCP tools that external AI agents
(Claude, Cursor, IDE agents) can query. MCP is READ-ONLY — external
agents can query the model but cannot modify it.

The verified-knowledge layer applies: external agents cite verified
laws as facts, unverified as candidates (Rule D2).

WITHDRAWAL PATH (Guideline P9):
External agents can query Maestro's REST API directly. MCP standardizes
the interface; without it, integration is harder but functional.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# MCP Tool registry — each tool is a read-only query function.
# External agents call POST /api/oem/mcp/tool/{tool_name} with a JSON
# payload of arguments. The tool returns a structured response.

MCP_TOOLS: dict[str, dict[str, Any]] = {
    "get_laws": {
        "description": "Get the organizational execution laws. Returns verified laws as facts and unverified as candidates.",
        "parameters": {"domain": "string (optional, filter by domain)"},
        "read_only": True,
    },
    "get_law": {
        "description": "Get a single law by code. Returns the law statement, confidence, and provenance.",
        "parameters": {"code": "string (required, the law code like LAW-001)"},
        "read_only": True,
    },
    "get_experts": {
        "description": "Get hidden experts in the organization (people with high influence but no documented expertise).",
        "parameters": {"min_influence": "float (optional, default 5.0)"},
        "read_only": True,
    },
    "get_bottlenecks": {
        "description": "Get approval bottlenecks (gates that are blocking too many items).",
        "parameters": {"min_count": "int (optional, default 3)"},
        "read_only": True,
    },
    "get_contradictions": {
        "description": "Get organizational contradictions (patterns where the org says one thing but does another).",
        "parameters": {},
        "read_only": True,
    },
    "ask_organization": {
        "description": "Ask a natural-language question about the organization. Returns a synthesized answer with evidence.",
        "parameters": {"question": "string (required)"},
        "read_only": True,
    },
    "get_recommendations": {
        "description": "Get active decision recommendations from the organizational model.",
        "parameters": {},
        "read_only": True,
    },
}


def list_tools() -> dict[str, Any]:
    """List all available MCP tools."""
    return {
        "tools": [
            {
                "name": name,
                "description": spec["description"],
                "parameters": spec["parameters"],
                "read_only": spec["read_only"],
            }
            for name, spec in MCP_TOOLS.items()
        ],
        "read_only_note": (
            "All MCP tools are read-only. External agents can query the "
            "organizational model but cannot modify it. Verified laws are "
            "returned as facts; unverified laws are labeled as candidates."
        ),
    }


def execute_tool(tool_name: str, args: dict[str, Any], model: Any, decisions: Any) -> dict[str, Any]:
    """Execute an MCP tool by name.

    All tools are read-only. The response always includes:
      - tool: the tool name
      - args: the arguments passed
      - result: the tool output
      - read_only: True (always)
      - verified_layer_applied: True (verified laws are facts, unverified are candidates)
    """
    if tool_name not in MCP_TOOLS:
        return {
            "tool": tool_name,
            "error": f"Unknown tool: {tool_name}",
            "available_tools": list(MCP_TOOLS.keys()),
        }

    spec = MCP_TOOLS[tool_name]
    if not spec["read_only"]:
        return {"tool": tool_name, "error": "Tool is not read-only (should not happen)"}

    try:
        if tool_name == "get_laws":
            result = _tool_get_laws(model, args)
        elif tool_name == "get_law":
            result = _tool_get_law(model, args)
        elif tool_name == "get_experts":
            result = _tool_get_experts(model, args)
        elif tool_name == "get_bottlenecks":
            result = _tool_get_bottlenecks(model, args)
        elif tool_name == "get_contradictions":
            result = _tool_get_contradictions(model)
        elif tool_name == "ask_organization":
            result = _tool_ask_organization(decisions, args)
        elif tool_name == "get_recommendations":
            result = _tool_get_recommendations(decisions)
        else:
            return {"tool": tool_name, "error": f"Tool not implemented: {tool_name}"}

        return {
            "tool": tool_name,
            "args": args,
            "result": result,
            "read_only": True,
            "verified_layer_applied": True,
        }
    except Exception as e:
        logger.error("MCP tool %s failed: %s", tool_name, e)
        return {"tool": tool_name, "error": str(e), "read_only": True}


def _tool_get_laws(model: Any, args: dict[str, Any]) -> dict[str, Any]:
    """Get organizational laws. Verified = facts, unverified = candidates."""
    domain = args.get("domain", "")
    laws: list[dict[str, Any]] = []
    for law in model.laws.values():
        if domain and domain.lower() not in (law.statement + law.condition).lower():
            continue
        status = law.status.value if hasattr(law.status, "value") else str(law.status)
        laws.append({
            "code": law.code,
            "statement": law.statement,
            "confidence": round(law.confidence, 2),
            "status": status,
            "evidence_count": law.evidence_count,
            "verified_by": getattr(law, "verified_by", None),
            "layer": "fact" if status == "verified" else "candidate",
        })
    return {
        "laws": laws[:20],
        "total": len(laws),
        "note": "Verified laws are facts. Unverified laws are candidates.",
    }


def _tool_get_law(model: Any, args: dict[str, Any]) -> dict[str, Any]:
    """Get a single law by code."""
    code = args.get("code", "")
    if not code:
        return {"error": "code parameter is required"}
    law = model.laws.get(code)
    if not law:
        return {"error": f"Law {code} not found"}
    status = law.status.value if hasattr(law.status, "value") else str(law.status)
    return {
        "code": law.code,
        "statement": law.statement,
        "condition": law.condition,
        "outcome": law.outcome,
        "confidence": round(law.confidence, 2),
        "status": status,
        "evidence_count": law.evidence_count,
        "verified_by": getattr(law, "verified_by", None),
        "layer": "fact" if status == "verified" else "candidate",
    }


def _tool_get_experts(model: Any, args: dict[str, Any]) -> dict[str, Any]:
    """Get hidden experts."""
    min_influence = args.get("min_influence", 5.0)
    try:
        experts = model.knowledge.get_hidden_experts()
        filtered = [e for e in experts if e.get("influence", 0) >= min_influence]
        return {"experts": filtered[:10], "total": len(filtered)}
    except Exception as e:
        return {"error": str(e), "experts": []}


def _tool_get_bottlenecks(model: Any, args: dict[str, Any]) -> dict[str, Any]:
    """Get approval bottlenecks."""
    min_count = args.get("min_count", 3)
    try:
        bottlenecks = model.approvals.get_bottlenecks(min_count=min_count)
        return {"bottlenecks": bottlenecks, "total": len(bottlenecks)}
    except Exception as e:
        return {"error": str(e), "bottlenecks": []}


def _tool_get_contradictions(model: Any) -> dict[str, Any]:
    """Get organizational contradictions."""
    try:
        from maestro_oem.contradictions import ContradictionDetector
        detector = ContradictionDetector(model)
        result = detector.detect()
        return {"contradictions": result.get("contradictions", [])[:10]}
    except Exception as e:
        return {"error": str(e), "contradictions": []}


def _tool_ask_organization(decisions: Any, args: dict[str, Any]) -> dict[str, Any]:
    """Ask a natural-language question."""
    question = args.get("question", "")
    if not question:
        return {"error": "question parameter is required"}
    try:
        answer = decisions.answer_question(question)
        # Apply the verified-knowledge layer
        for law in answer.get("laws", []):
            law["layer"] = "fact" if law.get("status") == "verified" else "candidate"
        return {
            "answer": answer.get("answer", ""),
            "confidence": answer.get("confidence", 0),
            "laws": answer.get("laws", []),
            "evidence_path": answer.get("evidence_path", []),
            "note": "Verified laws are facts. Unverified laws are candidates.",
        }
    except Exception as e:
        return {"error": str(e)}


def _tool_get_recommendations(decisions: Any) -> dict[str, Any]:
    """Get active recommendations."""
    try:
        recs = decisions.get_recommendations()
        return {
            "recommendations": [
                {
                    "title": r.title,
                    "recommendation": r.recommendation,
                    "confidence": round(r.confidence, 2),
                    "urgency": r.urgency,
                    "decision_question": r.decision_question,
                    "linked_laws": r.linked_laws,
                }
                for r in recs[:10]
            ],
            "total": len(recs),
        }
    except Exception as e:
        return {"error": str(e), "recommendations": []}

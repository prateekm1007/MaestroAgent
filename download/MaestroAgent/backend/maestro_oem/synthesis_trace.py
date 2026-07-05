"""SynthesisTrace — the audit record for every Ask Maestro answer.

AUDITOR-DIRECTIVE (2026-07-05, "Reasoning Plane"):
> every Maestro answer should reveal internally which cognitive path
> produced it. Not to the executive as technical clutter, but in the
> audit record.

The SynthesisTrace is the Fortune-100-grade explainability record. It is
returned in the API response under the `synthesis_trace` key.

Design principles:
  1. NEVER SILENT. Every answer carries a trace. reasoning_mode =
     MODEL | DETERMINISTIC_FALLBACK | TEMPLATE_ONLY. No third state.
  2. COMPLETE. Every field is populated, even if "none" or "unknown".
  3. SERIALIZABLE. Pydantic model — serializes to JSON.
  4. IMMUTABLE. Once recorded, not modified.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ReasoningMode(str, Enum):
    """Which cognitive path produced the answer."""
    MODEL = "model"
    DETERMINISTIC_FALLBACK = "deterministic_fallback"
    TEMPLATE_ONLY = "template_only"


class CitationValidationResult(str, Enum):
    """Result of post-reasoning citation validation."""
    NOT_RUN = "not_run"
    ALL_VALID = "all_valid"
    HALLUCINATIONS_STRIPPED = "hallucinations_stripped"
    UNSUPPORTED_CLAIMS_REMOVED = "unsupported_claims_removed"


class SynthesisTrace(BaseModel):
    """The audit record for a single Ask Maestro answer."""

    # Identity
    query_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Retrieval
    query: str = ""
    retrieval_strategy: str = ""
    intent: str = ""
    entities_resolved: list[str] = Field(default_factory=list)
    time_range: str = ""
    evidence_items_considered: int = 0
    evidence_items_selected: int = 0
    permission_filters_applied: list[str] = Field(default_factory=list)

    # Reasoning
    reasoning_mode: ReasoningMode = ReasoningMode.TEMPLATE_ONLY
    model_used: str = ""
    fallback_triggered: bool = False
    fallback_reason: str = ""
    contradictions_found: int = 0

    # Verification
    citation_validation_result: CitationValidationResult = CitationValidationResult.NOT_RUN

    # Delivery
    latency_ms: int = 0
    policy_version: str = "v1"

    # Workspace
    workspace_type: str = ""
    workspace_dimensions: list[str] = Field(default_factory=list)
    workspace_missingness: dict[str, list[str]] = Field(default_factory=dict)

    # Free-form metadata
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_audit_dict(self) -> dict[str, Any]:
        return {
            "query_id": str(self.query_id),
            "timestamp": self.timestamp.isoformat(),
            "query": self.query,
            "retrieval_strategy": self.retrieval_strategy,
            "intent": self.intent,
            "entities_resolved": self.entities_resolved,
            "time_range": self.time_range,
            "evidence_items_considered": self.evidence_items_considered,
            "evidence_items_selected": self.evidence_items_selected,
            "permission_filters_applied": self.permission_filters_applied,
            "reasoning_mode": self.reasoning_mode.value,
            "model_used": self.model_used,
            "fallback_triggered": self.fallback_triggered,
            "fallback_reason": self.fallback_reason,
            "contradictions_found": self.contradictions_found,
            "citation_validation_result": self.citation_validation_result.value,
            "latency_ms": self.latency_ms,
            "policy_version": self.policy_version,
            "workspace_type": self.workspace_type,
            "workspace_dimensions": self.workspace_dimensions,
            "workspace_missingness": self.workspace_missingness,
            "metadata": self.metadata,
        }

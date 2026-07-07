"""
Maestro + Nerve Integration: Base Agent Framework (Phase 1, Feature 1).

Every Nerve-style specialized agent inherits from BaseAgent and gets
unified access to the OEM Engine (Organizational Execution Model) —
organizational memory that Nerve's siloed agents never had.

The OEM Engine exposes:
  - SituationSnapshot (27-field canonical context per entity)
  - CommitmentTracker (open/overdue commitments across meetings + email + Slack)
  - SentimentPatternEngine (5 patterns, RAVDESS-validated)
  - DealHealthEngine (4-component weighted score: 0-100)
  - CrossMeetingThreadBuilder (conversation continuity, 70-80% accuracy)
  - CalendarAwarenessEngine (upcoming meetings + prep gaps)
  - AdvancedAnalyticsEngine (trends, team performance, Brier scores)
  - CommitmentEscalationEngine (failure prediction)
  - OrganizationalDNA (decision/risk/learning/communication style)
  - LearningLedger (validated patterns -> organizational laws)
  - CRMConnector (Salesforce/HubSpot one-way sync)
  - OutcomeLedger (durable, tenant-scoped execution history)

Design principles (from GOVERNANCE_LOOP):
  - P4 (honest disclosure): every insight cites its evidence chain
  - P13 (derived not asserted): every claim is derived from signals,
    not caller-supplied
  - P23 (commit-cites-output): every agent method that returns an
    insight includes a `confidence` and `evidence_chain` field
  - P25 (confidence gates): insights below CONFIDENCE_THRESHOLD are
    suppressed or marked "low confidence"
  - P34 (loop closure): agents read OEM, write insights back to OEM
    via the OutcomeLedger

Reference: docs/MAESTRO_NERVE_INTEGRATION_ROADMAP.md
"""

from __future__ import annotations

from .base_agent import (
    BaseAgent,
    AgentContext,
    AgentInsight,
    AgentCapability,
    CONFIDENCE_THRESHOLD,
    HIGH_CONFIDENCE_THRESHOLD,
    confidence_label,
    register_agent,
    get_agent,
    list_agents,
    get_all_agents,
)

__all__ = [
    "BaseAgent",
    "AgentContext",
    "AgentInsight",
    "AgentCapability",
    "CONFIDENCE_THRESHOLD",
    "HIGH_CONFIDENCE_THRESHOLD",
    "confidence_label",
    "register_agent",
    "get_agent",
    "list_agents",
    "get_all_agents",
]

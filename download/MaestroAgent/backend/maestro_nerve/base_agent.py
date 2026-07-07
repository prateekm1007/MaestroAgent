"""
Maestro + Nerve Integration: Base Agent Framework (Phase 1, Feature 1).

Every Nerve-style specialized agent inherits from BaseAgent and gets
unified access to the OEM Engine (Organizational Execution Model) —
organizational memory that Nerve's siloed agents never had.

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

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


# ── Confidence threshold (P25) ──────────────────────────────────────────────
# Insights below this threshold are suppressed or marked "low confidence".
CONFIDENCE_THRESHOLD = 0.60   # 60% — same as LiveIntelligenceEngine (Phase 4)
HIGH_CONFIDENCE_THRESHOLD = 0.80   # 80% — "high confidence" label


def confidence_label(score: float) -> str:
    """P25: convert a confidence score to a human-readable label."""
    if score >= HIGH_CONFIDENCE_THRESHOLD:
        return "high"
    if score >= CONFIDENCE_THRESHOLD:
        return "moderate"
    return "low"


# ── Data classes ────────────────────────────────────────────────────────────

@dataclass
class AgentContext:
    """Per-request context passed to every agent.

    Encapsulates the authenticated user, tenant, and request parameters
    so agents don't have to plumb these through every method.
    """
    user_email: str = ""
    org_id: str = "default"
    tenant_id: str = "default"
    request: dict[str, Any] = field(default_factory=dict)
    # The agent framework stamps this on each call for tracing.
    call_id: str = field(default_factory=lambda: f"agent-{uuid4().hex[:8]}")
    # When True, agents should suppress low-confidence insights (P25).
    strict_confidence: bool = True


@dataclass
class AgentInsight:
    """A single insight produced by an agent.

    Every insight MUST include:
      - id: stable identifier (for evidence-chain linking)
      - agent: which agent produced it
      - title: short headline
      - body: 1-3 sentence explanation
      - confidence: 0.0-1.0 (P25)
      - evidence_chain: list of OEM sources that back the insight (P4, P23)
      - recommended_action: concrete next step (or None)
      - priority: "high" | "medium" | "low"
      - organizational_law: optional reference to a validated law (L-YYYY-NNN)
    """
    id: str
    agent: str
    title: str
    body: str
    confidence: float
    evidence_chain: list[dict[str, Any]] = field(default_factory=list)
    recommended_action: Optional[str] = None
    priority: str = "medium"
    organizational_law: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "agent": self.agent,
            "title": self.title,
            "body": self.body,
            "confidence": round(self.confidence, 3),
            "confidence_label": confidence_label(self.confidence),
            "evidence_chain": self.evidence_chain,
            "recommended_action": self.recommended_action,
            "priority": self.priority,
            "organizational_law": self.organizational_law,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    def passes_confidence_gate(self, strict: bool = True) -> bool:
        """P25: returns True if this insight should be shown to the user."""
        if not strict:
            return True
        return self.confidence >= CONFIDENCE_THRESHOLD


@dataclass
class AgentCapability:
    """Declares what an agent can do (for the dashboard + handoffs)."""
    name: str
    description: str
    input_schema: dict[str, str]
    output_schema: dict[str, str]


# ── BaseAgent ───────────────────────────────────────────────────────────────

class BaseAgent(ABC):
    """Base class for all 17 Nerve-style agents.

    Every agent gets unified access to the OEM Engine. Subclasses
    implement `generate_insights()` and `capabilities()`.

    Design:
      - OEM access is lazy (imported on first use) to avoid circular imports.
      - All agents share the same OEM singleton (maestro_api.oem_state.oem_state).
      - Agents are stateless per-request: they read OEM, generate insights,
        and don't mutate OEM directly (the API routes do that via OutcomeLedger).
    """

    AGENT_NAME: str = "base"
    AGENT_DESCRIPTION: str = "Base agent — override in subclass"

    def __init__(self, oem_state: Any = None):
        """
        Args:
            oem_state: the OEM singleton (maestro_api.oem_state.oem_state).
                If None, the agent will lazily import it on first use.
        """
        self._oem_state = oem_state

    # ── OEM access ──────────────────────────────────────────────────────────

    @property
    def oem_state(self) -> Any:
        """Lazily resolve the OEM singleton."""
        if self._oem_state is None:
            try:
                from maestro_api.oem_state import oem_state
                self._oem_state = oem_state
            except ImportError:
                logger.warning(
                    f"{self.AGENT_NAME}: OEM state unavailable — running in standalone mode"
                )
                self._oem_state = _NullOemState()
        return self._oem_state

    def _get_signals(self, org_id: str = "default") -> list:
        """Get all OEM signals for a tenant."""
        signals = getattr(self.oem_state, "signals", None)
        if signals is None:
            return []
        # Some signals may be tenant-scoped; filter by org_id if available.
        result = []
        for s in signals:
            s_org = getattr(s, "org_id", None) or getattr(s, "tenant_id", None)
            if s_org is None or s_org == org_id:
                result.append(s)
        return result

    # ── OEM engine factories (lazy) ─────────────────────────────────────────

    def _situation_builder(self, user_email: str = ""):
        from maestro_oem.situation import SituationBuilder
        return SituationBuilder(
            signals=self._get_signals(),
            calendar_source=None,
            whisper_store=None,
            user_email=user_email,
        )

    def _deal_health_engine(self):
        from maestro_oem.deal_health import DealHealthEngine
        return DealHealthEngine(oem_state=self.oem_state)

    def _sentiment_engine(self):
        from maestro_oem.sentiment_patterns import SentimentPatternEngine
        return SentimentPatternEngine()

    def _commitment_tracker(self):
        from maestro_oem.commitment_tracker import CommitmentTracker
        return CommitmentTracker(model=None, signals=self._get_signals())

    def _commitment_escalation_engine(self):
        from maestro_oem.commitment_escalation import CommitmentEscalationEngine
        return CommitmentEscalationEngine(oem_state=self.oem_state)

    def _cross_meeting_thread_builder(self):
        from maestro_oem.cross_meeting_threads import CrossMeetingThreadBuilder
        return CrossMeetingThreadBuilder()

    def _calendar_awareness_engine(self):
        from maestro_oem.calendar_awareness import CalendarAwarenessEngine
        return CalendarAwarenessEngine(oem_state=self.oem_state)

    def _advanced_analytics_engine(self):
        from maestro_oem.advanced_analytics import AdvancedAnalyticsEngine
        return AdvancedAnalyticsEngine()

    def _organizational_dna(self):
        from maestro_oem.organizational_dna import OrganizationalDNA
        return OrganizationalDNA(model=None, signals=self._get_signals())

    def _crm_connector(self):
        from maestro_oem.crm_connector import CRMConnector, CRMConfig
        config = CRMConfig(provider="salesforce")
        return CRMConnector(config)

    def _outcome_ledger(self):
        from maestro_oem.governed_adaptation import get_default_outcome_ledger
        return get_default_outcome_ledger()

    def _meeting_grader(self):
        from maestro_oem.meeting_grader import MeetingGrader
        return MeetingGrader()

    def _negotiation_pattern_detector(self):
        try:
            from maestro_oem.negotiation_strategy import NegotiationPatternDetector
            return NegotiationPatternDetector()
        except ImportError:
            return None

    def _talk_ratio_coach(self):
        from maestro_oem.talk_ratio_coach import TalkRatioCoach
        return TalkRatioCoach()

    def _workplace_signal_fusion(self):
        from maestro_oem.workplace_signal_fusion import WorkplaceSignalFusion
        return WorkplaceSignalFusion()

    def _learning_ledger(self):
        from maestro_oem.learning_ledger import LearningLedger
        return LearningLedger()

    # ── Abstract methods ────────────────────────────────────────────────────

    @abstractmethod
    def generate_insights(self, ctx: AgentContext) -> list[AgentInsight]:
        """Generate insights for this user/tenant.

        Subclasses MUST:
          - Read from OEM (don't accept caller-supplied data — P13)
          - Cite evidence_chain on every insight (P4, P23)
          - Apply confidence gates (P25)
          - Be deterministic for the same OEM state (no random)
        """
        raise NotImplementedError

    def capabilities(self) -> list[AgentCapability]:
        """Declare what this agent can do (for dashboard + handoffs)."""
        return [
            AgentCapability(
                name="generate_insights",
                description=self.AGENT_DESCRIPTION,
                input_schema={"user_email": "str", "org_id": "str"},
                output_schema={"insights": "list[AgentInsight]"},
            ),
        ]

    # ── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def evidence(source: str, **kwargs) -> dict[str, Any]:
        """Build an evidence-chain entry (P4, P23)."""
        return {"source": source, **kwargs}

    @staticmethod
    def apply_confidence_gate(
        insights: list[AgentInsight],
        strict: bool = True,
    ) -> list[AgentInsight]:
        """Filter insights by the confidence threshold (P25)."""
        return [i for i in insights if i.passes_confidence_gate(strict)]

    @staticmethod
    def sort_by_priority(insights: list[AgentInsight]) -> list[AgentInsight]:
        """Sort insights by priority (high -> medium -> low), then by confidence."""
        priority_order = {"high": 0, "medium": 1, "low": 2}
        return sorted(
            insights,
            key=lambda i: (priority_order.get(i.priority, 1), -i.confidence),
        )

    def on_insight_generated(self, insight: AgentInsight, ctx: AgentContext) -> None:
        """Hook called after each insight is generated.

        Subclasses can override to write the insight to the OutcomeLedger
        (P34 — loop closure) or trigger downstream agents.
        """
        try:
            ledger = self._outcome_ledger()
            ledger.append({
                "whisper_id": f"{self.AGENT_NAME}-{insight.id}",
                "exec_action": "agent_insight",
                "outcome": insight.title,
                "entity": insight.metadata.get("entity", ""),
                "hypothesis": insight.body,
                "confounders": [],
                "context_signals": [e.get("source", "") for e in insight.evidence_chain],
                "org_id": ctx.org_id,
                "user_email": ctx.user_email,
                "agent": self.AGENT_NAME,
                "confidence": insight.confidence,
            }, org_id=ctx.org_id)
        except Exception as e:
            logger.debug(f"{self.AGENT_NAME}: could not write insight to ledger: {e}")


class _NullOemState:
    """Fallback when OEM state is unavailable (e.g., standalone tests)."""

    signals: list = []

    def __getattr__(self, name: str) -> Any:
        return None


# ── Agent registry ──────────────────────────────────────────────────────────

_AGENT_REGISTRY: dict[str, type[BaseAgent]] = {}


def register_agent(agent_class: type[BaseAgent]) -> type[BaseAgent]:
    """Decorator to register an agent class in the global registry."""
    _AGENT_REGISTRY[agent_class.AGENT_NAME] = agent_class
    return agent_class


def get_agent(name: str, oem_state: Any = None) -> Optional[BaseAgent]:
    """Get an agent instance by name."""
    cls = _AGENT_REGISTRY.get(name)
    if cls is None:
        return None
    return cls(oem_state=oem_state)


def list_agents() -> list[str]:
    """List all registered agent names."""
    return sorted(_AGENT_REGISTRY.keys())


def get_all_agents(oem_state: Any = None) -> dict[str, BaseAgent]:
    """Get instances of all registered agents."""
    return {name: cls(oem_state=oem_state) for name, cls in _AGENT_REGISTRY.items()}

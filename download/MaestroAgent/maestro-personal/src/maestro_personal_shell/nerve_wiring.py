"""
Nerve wiring — exposes all Nerve agents to the Personal shell.

Per CEO Phase 3 directive: replace template perspectives with real
Nerve agent insights. Each agent reads .signals from PersonalOemState
(duck-typed, same pattern as Core) and generates AgentInsight objects
with title, body, confidence, evidence_chain, recommended_action.

14 of 17 agents are personal-applicable (3 excluded: Security,
Support, Partnerships — enterprise-only).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class NerveWiring:
    """Lazy-accessor for all Nerve agents, wired to personal OEM state.

    Usage:
        nerve = NerveWiring(shell)
        insights = nerve.get_insights_for_entity("Alex")

    Each agent lazy-initializes on first access, cached for reuse.
    """

    # The 14 personal-applicable agents (3 excluded: security, support, partnerships)
    PERSONAL_AGENTS = [
        "chief_of_staff",
        "engineering",
        "product",
        "customer_success",
        "strategy",
        "operations",
        "growth",
        "sales",
        "finance",
        "marketing",
        "data",
        "communications",
        "hr",
        "legal",
    ]

    def __init__(self, shell: Any) -> None:
        self._shell = shell
        self._agents: dict[str, Any] = {}
        self._initialized = False

    def _init_agents(self) -> None:
        """Initialize all 14 personal-applicable agents."""
        if self._initialized:
            return

        oem_state = self._shell.oem_state

        agent_classes = []
        try:
            from maestro_nerve.agents_revenue import GrowthAgent, SalesAgent, CustomerSuccessAgent, FinanceAgent
            agent_classes.extend([
                ("growth", GrowthAgent),
                ("sales", SalesAgent),
                ("customer_success", CustomerSuccessAgent),
                ("finance", FinanceAgent),
            ])
        except ImportError as e:
            logger.debug("agents_revenue import failed: %s", e)

        try:
            from maestro_nerve.agents_product import ProductAgent, EngineeringAgent, MarketingAgent
            agent_classes.extend([
                ("product", ProductAgent),
                ("engineering", EngineeringAgent),
                ("marketing", MarketingAgent),
            ])
        except ImportError as e:
            logger.debug("agents_product import failed: %s", e)

        try:
            from maestro_nerve.agents_strategy import StrategyAgent, CommunicationsAgent, ChiefOfStaffAgent
            agent_classes.extend([
                ("strategy", StrategyAgent),
                ("communications", CommunicationsAgent),
                ("chief_of_staff", ChiefOfStaffAgent),
            ])
        except ImportError as e:
            logger.debug("agents_strategy import failed: %s", e)

        try:
            from maestro_nerve.agents_internal import HRAgent, LegalAgent, OperationsAgent, DataAgent
            agent_classes.extend([
                ("hr", HRAgent),
                ("legal", LegalAgent),
                ("operations", OperationsAgent),
                ("data", DataAgent),
            ])
        except ImportError as e:
            logger.debug("agents_internal import failed: %s", e)

        for name, cls in agent_classes:
            if name not in self.PERSONAL_AGENTS:
                continue
            try:
                self._agents[name] = cls(oem_state=oem_state)
            except Exception as e:
                logger.debug("Agent %s init failed: %s", name, e)

        self._initialized = True

    @property
    def agents(self) -> dict[str, Any]:
        """All initialized agents."""
        self._init_agents()
        return self._agents

    @property
    def wired_count(self) -> int:
        """How many agents are successfully wired."""
        self._init_agents()
        return len(self._agents)

    @property
    def wired_agents(self) -> list[str]:
        """Names of successfully wired agents."""
        self._init_agents()
        return list(self._agents.keys())

    def get_insights(self, org_id: str = "personal") -> list[dict[str, Any]]:
        """Generate insights from all wired agents.

        Per Phase 3+ directive: adapt agents with personal-mode adapters
        before calling generate_insights. The adapters patch the agents'
        enterprise engine factories to use personal-mode equivalents.

        Returns a list of insight dicts with:
          - agent: which agent produced it
          - title: short headline
          - body: 1-3 sentence explanation
          - confidence: 0.0-1.0
          - evidence_chain: list of evidence dicts
          - recommended_action: concrete next step
          - priority: high/medium/low
        """
        self._init_agents()
        from maestro_nerve.base_agent import AgentContext

        # ADAPT: patch agents' enterprise engines with personal adapters
        try:
            from maestro_personal_shell.agent_adapters import PersonalAgentAdapter
            adapter = PersonalAgentAdapter(shell=self._shell)
            adapter.adapt_all(self._agents)
        except Exception as e:
            logger.debug("Agent adaptation failed: %s", e)

        ctx = AgentContext(
            user_email="personal",
            org_id=org_id,
            tenant_id=org_id,
        )

        all_insights = []
        for name, agent in self._agents.items():
            if name == "chief_of_staff":
                continue  # ChiefOfStaff aggregates others — skip to avoid recursion
            try:
                insights = agent.generate_insights(ctx)
                for ins in insights[:3]:  # max 3 per agent
                    all_insights.append({
                        "agent": str(getattr(ins, "agent", name)),
                        "title": str(getattr(ins, "title", "")),
                        "body": str(getattr(ins, "body", ""))[:300],
                        "confidence": float(getattr(ins, "confidence", 0.0)),
                        "evidence_chain": [
                            ev if isinstance(ev, dict) else {"text": str(ev)}
                            for ev in (getattr(ins, "evidence_chain", []) or [])[:3]
                        ],
                        "recommended_action": str(getattr(ins, "recommended_action", "") or ""),
                        "priority": str(getattr(ins, "priority", "low")),
                    })
            except Exception as e:
                logger.debug("Agent %s generate_insights failed: %s", name, e)

        # Sort by priority: high > medium > low
        priority_order = {"high": 0, "medium": 1, "low": 2}
        all_insights.sort(key=lambda x: priority_order.get(x.get("priority", "low"), 2))

        return all_insights

    def get_insights_for_entity(self, entity: str, org_id: str = "personal") -> list[dict[str, Any]]:
        """Get insights filtered to a specific entity.

        Filters insights where the agent name, title, or body mentions
        the entity name.
        """
        all_insights = self.get_insights(org_id)
        entity_lower = entity.lower()

        filtered = []
        for ins in all_insights:
            # Check if the insight mentions this entity
            searchable = f"{ins.get('agent', '')} {ins.get('title', '')} {ins.get('body', '')}".lower()
            if entity_lower in searchable:
                filtered.append(ins)

        return filtered[:5]  # max 5 insights per entity

    def get_perspectives_for_entity(self, entity: str, org_id: str = "personal") -> list[dict[str, Any]]:
        """Get perspectives formatted for the Ask endpoint.

        Returns a list of dicts with 'name' and 'view' keys — but now
        with REAL agent insights instead of template strings.
        """
        insights = self.get_insights_for_entity(entity, org_id)

        if not insights:
            # Honest: no agent produced an insight for this entity
            return []

        perspectives = []
        for ins in insights[:3]:  # max 3 perspectives
            perspectives.append({
                "name": ins.get("agent", "specialist"),
                "view": ins.get("title", "") + ". " + ins.get("body", "")[:150],
                "observation": ins.get("title", ""),
                "implication": ins.get("body", ""),
                "evidence": ins.get("evidence_chain", []),
                "recommended_next_step": ins.get("recommended_action", ""),
                "urgency": ins.get("priority", "normal"),
                "confidence": ins.get("confidence", 0.0),
            })

        return perspectives

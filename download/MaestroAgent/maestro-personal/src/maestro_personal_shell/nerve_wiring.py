"""Nerve wiring — exposes all Nerve agents to the Personal shell."""

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

    # F4: Personal-applicable agents — pruned from 14 to 8.
    #
    # The auditor noted: "an individual doesn't obviously need an 'HR agent'
    # perspective on their own life." The original 14-agent list was the
    # Enterprise org-chart reused wholesale — dilutive for personal use.
    #
    # Removed (enterprise org functions, not personal):
    #   - hr: you are not your own HR department
    #   - legal: individuals rarely need legal framing on daily commitments
    #   - operations: operational efficiency is an org concept
    #   - data: data pipeline analysis is enterprise
    #   - growth: growth hacking is a business function
    #   - marketing: marketing strategy is enterprise
    #
    # Kept (personally meaningful):
    #   - chief_of_staff: broad prioritization (useful for anyone)
    #   - customer_success: relationship management (your clients/contacts)
    #   - sales: deal/negotiation tracking (your professional commitments)
    #   - finance: financial commitments (invoices, payments, budget)
    #   - engineering: technical commitments (code, infra, deliverables)
    #   - product: project/product thinking (useful for builders)
    #   - strategy: strategic thinking (career, priorities)
    #   - communications: communication follow-ups (emails, calls)
    #
    # This is the "less is more" principle — 8 focused perspectives beat
    # 14 dilutive ones. The LLM holistic analysis still can recommend any
    # specialist from the full list; this just controls which agents
    # generate standalone insights.
    PERSONAL_AGENTS = [
        "chief_of_staff",
        "customer_success",
        "sales",
        "finance",
        "engineering",
        "product",
        "strategy",
        "communications",
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

    def get_insights(self, org_id: str = "personal", situation_text: str = "") -> list[dict[str, Any]]:
        """Generate insights from dynamically selected agents."""
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

        # P11 fix: dynamically select relevant agents when situation_text is provided
        agents_to_run = self._agents
        if situation_text:
            try:
                from maestro_personal_shell.dynamic_agents import select_relevant_agents
                relevant_names = select_relevant_agents(
                    situation_text, self._shell.oem_state.signals,
                )
                agents_to_run = {
                    name: agent for name, agent in self._agents.items()
                    if name in relevant_names
                }
                if not agents_to_run:
                    agents_to_run = self._agents  # fallback to all if none selected
                logger.debug("Dynamic agent selection: %s → %s",
                             list(self._agents.keys()), list(agents_to_run.keys()))
            except Exception as e:
                logger.debug("Dynamic agent selection failed, running all: %s", e)
                agents_to_run = self._agents

        all_insights = []
        for name, agent in agents_to_run.items():
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
        """Get insights filtered to a specific entity."""
        all_insights = self.get_insights(org_id, situation_text=entity)
        entity_lower = entity.lower()

        filtered = []
        for ins in all_insights:
            # Check if the insight mentions this entity
            searchable = f"{ins.get('agent', '')} {ins.get('title', '')} {ins.get('body', '')}".lower()
            if entity_lower in searchable:
                filtered.append(ins)

        return filtered[:5]  # max 5 insights per entity

    async def get_perspectives_for_entity(self, entity: str, org_id: str = "personal") -> list[dict[str, Any]]:
        """Get perspectives formatted for the Ask endpoint.

        When an LLM is available, perspectives are generated by the LLM
        (genuine specialist analysis from the situation + signals).
        When no LLM is available, falls back to the keyword-based
        Nerve agent insights.

        Returns a list of dicts with 'name' and 'view' keys.
        """
        # --- LLM-powered path (primary) ---
        # When the LLM bridge is active, generate genuine specialist
        # perspectives instead of keyword-counter templates.
        try:
            from maestro_personal_shell.llm_bridge import is_llm_available
            if is_llm_available():
                llm_perspectives = await self._llm_perspectives_for_entity(entity, org_id)
                if llm_perspectives:
                    return llm_perspectives
                # If LLM produced nothing (e.g. no situation found),
                # fall through to keyword-based below.
        except Exception as e:
            logger.debug("LLM perspectives failed, falling back: %s", e)

        # --- Keyword-based fallback (secondary) ---
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
                "llm_powered": False,
            })

        return perspectives

    async def _llm_perspectives_for_entity(
        self, entity: str, org_id: str = "personal"
    ) -> list[dict[str, Any]]:
        """Generate LLM-powered specialist perspectives for an entity.

        Selects the most relevant specialists based on available signals,
        then asks the LLM to analyze the situation from each specialist's
        viewpoint. This is genuine AI reasoning, not keyword matching.
        """
        from maestro_personal_shell.llm_bridge import llm_generate_perspective

        # Find the situation for this entity (or build a lightweight one)
        situations = self._shell.detect_situations()
        matching = None
        for s in situations:
            if str(getattr(s, "entity", "")).lower() == entity.lower():
                matching = s
                break
        if not matching and situations:
            matching = situations[0]

        if not matching:
            return []

        # Gather signals related to this entity
        entity_signals = []
        for sig in self._shell.oem_state.signals:
            sig_entity = str(getattr(sig, "entity", "")).lower()
            sig_text = str(getattr(sig, "text", "")).lower()
            if entity.lower() in sig_entity or entity.lower() in sig_text:
                entity_signals.append(sig)

        if not entity_signals:
            # No evidence to analyze — honest silence
            return []

        # Select relevant specialists based on signal types
        specialists = self._select_specialists(entity_signals)

        # P1-Audit-parallelize: generate all perspectives in PARALLEL
        # instead of sequentially. This reduces latency from N×LLM_delay
        # to 1×LLM_delay (3 calls × 2s = 6s → 2s).
        import asyncio as _asyncio

        async def _safe_perspective(specialist):
            try:
                return await llm_generate_perspective(specialist, matching, entity_signals)
            except Exception:
                return None

        tasks = [_safe_perspective(s) for s in specialists[:3]]
        results = await _asyncio.gather(*tasks, return_exceptions=True)

        perspectives = []
        for i, result in enumerate(results):
            if isinstance(result, Exception) or not result or not isinstance(result, dict):
                continue
            specialist = specialists[i]
            perspectives.append({
                "name": specialist,
                "view": f"{result.get('observation', '')}. {result.get('implication', '')}"[:300],
                "observation": result.get("observation", ""),
                "implication": result.get("implication", ""),
                "evidence": [
                    {"text": str(getattr(s, "text", ""))[:200]}
                    for s in entity_signals[:3]
                ],
                "recommended_next_step": result.get("recommended_next_step", ""),
                "urgency": result.get("urgency", "normal"),
                "confidence": float(result.get("confidence", 0.5)),
                "llm_powered": True,
            })

        return perspectives

    def _select_specialists(self, signals: list[Any]) -> list[str]:
        """Select the most relevant specialists for the given signals.

        Uses signal types and keywords to determine which specialists
        would have the most relevant perspective. This is a routing
        decision, not the intelligence itself — the LLM does the analysis.
        """
        # Count signal types to determine relevance
        type_counts: dict[str, int] = {}
        text_blob = ""
        for sig in signals:
            sig_type = str(getattr(sig, "signal_type", getattr(sig, "type", "")))
            type_counts[sig_type] = type_counts.get(sig_type, 0) + 1
            text_blob += " " + str(getattr(sig, "text", "")).lower()

        specialists: list[str] = []

        # Revenue-related signals
        if any(t in type_counts for t in ("commitment_made", "deal_update", "pricing")) \
                or any(kw in text_blob for kw in ("contract", "pricing", "renewal", "deal")):
            specialists.extend(["sales", "customer_success", "finance"])

        # Product/engineering signals
        if any(t in type_counts for t in ("bug", "feature_request", "technical")) \
                or any(kw in text_blob for kw in ("bug", "api", "integration", "deploy")):
            specialists.extend(["engineering", "product"])

        # Relationship/communication signals
        if any(t in type_counts for t in ("email", "meeting", "call")) \
                or any(kw in text_blob for kw in ("meeting", "email", "call", "frustrat")):
            specialists.extend(["customer_success", "communications"])

        # Default: chief of staff perspective (broad)
        if not specialists:
            specialists = ["chief_of_staff", "customer_success", "strategy"]

        # Deduplicate, preserve order
        seen: set[str] = set()
        unique: list[str] = []
        for s in specialists:
            if s not in seen:
                seen.add(s)
                unique.append(s)

        return unique[:5]

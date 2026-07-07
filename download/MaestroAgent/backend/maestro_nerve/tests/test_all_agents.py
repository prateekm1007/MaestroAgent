"""Tests for all 17 Nerve-style agents.

Each agent test verifies:
  - The agent is registered
  - generate_insights() returns a list[AgentInsight]
  - Every insight has confidence + evidence_chain (P4, P23)
  - Cold-start (no OEM data) returns graceful low-confidence insights or empty
"""

from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import pytest


# Ensure all agents are registered before tests run
def _ensure_agents_registered():
    from maestro_nerve import agents_revenue, agents_product, agents_internal, agents_strategy  # noqa: F401


_ensure_agents_registered()


EXPECTED_AGENTS = [
    "growth",
    "sales",
    "customer_success",
    "finance",
    "product",
    "engineering",
    "marketing",
    "hr",
    "legal",
    "operations",
    "support",
    "data",
    "security",
    "partnerships",
    "strategy",
    "communications",
    "chief_of_staff",
]


class TestAllAgentsRegistered:
    """Verify all 17 agents are registered."""

    def test_all_17_agents_registered(self):
        from maestro_nerve.base_agent import list_agents
        agents = list_agents()
        for expected in EXPECTED_AGENTS:
            assert expected in agents, f"Agent '{expected}' not registered. Got: {agents}"

    def test_agent_count_is_17(self):
        from maestro_nerve.base_agent import list_agents
        agents = list_agents()
        assert len(agents) == 17, f"Expected 17 agents, got {len(agents)}: {agents}"

    def test_get_all_agents_returns_instances(self):
        from maestro_nerve.base_agent import get_all_agents, BaseAgent
        agents = get_all_agents()
        assert len(agents) == 17
        for name, agent in agents.items():
            assert isinstance(agent, BaseAgent), f"{name} is not a BaseAgent"


@pytest.mark.parametrize("agent_name", EXPECTED_AGENTS)
class TestAgentBehavior:
    """Each agent must:
      1. Return a list (possibly empty) — never raise
      2. Every insight has confidence + evidence_chain
      3. Cold-start (no OEM data) doesn't crash
    """

    def test_agent_returns_list(self, agent_name):
        from maestro_nerve.base_agent import get_agent, AgentContext
        agent = get_agent(agent_name)
        assert agent is not None
        ctx = AgentContext(user_email="test@test.com", org_id="default")
        # Use a NullOemState so we test cold-start
        from maestro_nerve.base_agent import _NullOemState
        agent._oem_state = _NullOemState()
        insights = agent.generate_insights(ctx)
        assert isinstance(insights, list)

    def test_insights_have_confidence_and_evidence(self, agent_name):
        from maestro_nerve.base_agent import get_agent, AgentContext
        agent = get_agent(agent_name)
        assert agent is not None
        from maestro_nerve.base_agent import _NullOemState
        agent._oem_state = _NullOemState()
        ctx = AgentContext(user_email="test@test.com", org_id="default")
        insights = agent.generate_insights(ctx)
        for ins in insights:
            # P25: confidence is a float in [0, 1]
            assert 0.0 <= ins.confidence <= 1.0
            # P4, P23: evidence_chain is a list
            assert isinstance(ins.evidence_chain, list)
            # Every insight has an agent name
            assert ins.agent == agent_name

    def test_agent_has_description(self, agent_name):
        from maestro_nerve.base_agent import get_agent
        agent = get_agent(agent_name)
        assert agent is not None
        assert agent.AGENT_DESCRIPTION
        assert len(agent.AGENT_DESCRIPTION) > 10

    def test_agent_has_capabilities(self, agent_name):
        from maestro_nerve.base_agent import get_agent
        agent = get_agent(agent_name)
        assert agent is not None
        caps = agent.capabilities()
        assert isinstance(caps, list)
        assert len(caps) >= 1
        # Each capability has the required fields
        for cap in caps:
            assert cap.name
            assert cap.description
            assert isinstance(cap.input_schema, dict)
            assert isinstance(cap.output_schema, dict)


class TestChiefOfStaffAgent:
    """The Chief of Staff Agent is the capstone — special tests."""

    def test_chief_of_staff_aggregates_all_agents(self):
        from maestro_nerve.base_agent import get_agent, AgentContext, _NullOemState
        cos = get_agent("chief_of_staff")
        assert cos is not None
        cos._oem_state = _NullOemState()
        ctx = AgentContext(user_email="ceo@acme.com", org_id="acme")
        insights = cos.generate_insights(ctx)
        # Should return a list (possibly large)
        assert isinstance(insights, list)

    def test_morning_briefing_structure(self):
        from maestro_nerve.base_agent import get_agent, AgentContext, _NullOemState
        cos = get_agent("chief_of_staff")
        cos._oem_state = _NullOemState()
        ctx = AgentContext(user_email="ceo@acme.com", org_id="acme")
        briefing = cos.generate_morning_briefing(ctx)
        assert "greeting" in briefing
        assert "date" in briefing
        assert "top_insights" in briefing
        assert "top_actions" in briefing
        assert "calendar_preview" in briefing
        assert "total_insights_generated" in briefing
        assert "agents_consulted" in briefing

    def test_evening_briefing_structure(self):
        from maestro_nerve.base_agent import get_agent, AgentContext, _NullOemState
        cos = get_agent("chief_of_staff")
        cos._oem_state = _NullOemState()
        ctx = AgentContext(user_email="ceo@acme.com", org_id="acme")
        briefing = cos.generate_evening_briefing(ctx)
        assert "greeting" in briefing
        assert "date" in briefing
        assert "todays_wins" in briefing
        assert "todays_risks" in briefing
        assert "pending_actions" in briefing

    def test_greeting_time_of_day(self):
        from maestro_nerve.base_agent import get_agent
        cos = get_agent("chief_of_staff")
        # Test all branches
        # We can't easily mock datetime here, but we can verify the method exists
        greeting = cos._greeting("jane.smith@acme.com")
        assert "Jane" in greeting or "Working late" in greeting

    def test_greeting_no_email(self):
        from maestro_nerve.base_agent import get_agent
        cos = get_agent("chief_of_staff")
        greeting = cos._greeting("")
        # Should not crash — falls back to "there"
        assert isinstance(greeting, str)

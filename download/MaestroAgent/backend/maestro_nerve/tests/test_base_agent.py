"""Tests for the Maestro + Nerve integration: BaseAgent framework.

Tests cover:
  - AgentInsight data class (to_dict, passes_confidence_gate)
  - AgentContext
  - confidence_label thresholds (P25)
  - BaseAgent abstract method enforcement
  - Agent registry (register_agent, get_agent, list_agents, get_all_agents)
  - _NullOemState fallback (standalone mode)
"""

from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import pytest
from datetime import datetime, timezone


class TestAgentInsight:
    """AgentInsight data class."""

    def _make_insight(self, confidence=0.85, priority="high"):
        from maestro_nerve.base_agent import AgentInsight
        return AgentInsight(
            id="test-1",
            agent="growth",
            title="Test insight",
            body="This is a test insight.",
            confidence=confidence,
            priority=priority,
            evidence_chain=[{"source": "test_source", "count": 5}],
            recommended_action="Do the thing",
        )

    def test_to_dict_has_required_fields(self):
        """P23: every insight dict has confidence + evidence_chain."""
        ins = self._make_insight()
        d = ins.to_dict()
        assert "id" in d
        assert "agent" in d
        assert "title" in d
        assert "body" in d
        assert "confidence" in d
        assert "evidence_chain" in d
        assert "recommended_action" in d
        assert "priority" in d
        assert "created_at" in d

    def test_to_dict_includes_confidence_label(self):
        """P25: every insight dict has a confidence_label."""
        ins = self._make_insight()
        d = ins.to_dict()
        assert "confidence_label" in d
        assert d["confidence_label"] in ("high", "moderate", "low")

    def test_passes_confidence_gate_strict(self):
        """P25: insights below 0.60 fail the strict gate."""
        from maestro_nerve.base_agent import CONFIDENCE_THRESHOLD
        high = self._make_insight(confidence=0.90)
        low = self._make_insight(confidence=0.30)
        assert high.passes_confidence_gate(strict=True)
        assert not low.passes_confidence_gate(strict=True)

    def test_passes_confidence_gate_non_strict(self):
        """P25: non-strict mode lets all insights through."""
        low = self._make_insight(confidence=0.10)
        assert low.passes_confidence_gate(strict=False)


class TestConfidenceLabel:
    """P25 confidence label thresholds."""

    def test_high_threshold(self):
        from maestro_nerve.base_agent import confidence_label, HIGH_CONFIDENCE_THRESHOLD
        assert confidence_label(HIGH_CONFIDENCE_THRESHOLD) == "high"
        assert confidence_label(0.95) == "high"

    def test_moderate_threshold(self):
        from maestro_nerve.base_agent import confidence_label, CONFIDENCE_THRESHOLD
        assert confidence_label(CONFIDENCE_THRESHOLD) == "moderate"
        assert confidence_label(0.65) == "moderate"

    def test_low_threshold(self):
        from maestro_nerve.base_agent import confidence_label
        assert confidence_label(0.30) == "low"
        assert confidence_label(0.59) == "low"

    def test_threshold_values(self):
        """Verify the threshold constants."""
        from maestro_nerve.base_agent import (
            CONFIDENCE_THRESHOLD,
            HIGH_CONFIDENCE_THRESHOLD,
        )
        assert CONFIDENCE_THRESHOLD == 0.60
        assert HIGH_CONFIDENCE_THRESHOLD == 0.80


class TestAgentContext:
    """AgentContext data class."""

    def test_default_context(self):
        from maestro_nerve.base_agent import AgentContext
        ctx = AgentContext()
        assert ctx.user_email == ""
        assert ctx.org_id == "default"
        assert ctx.tenant_id == "default"
        assert ctx.strict_confidence is True
        assert ctx.call_id.startswith("agent-")

    def test_context_with_user(self):
        from maestro_nerve.base_agent import AgentContext
        ctx = AgentContext(user_email="jane@acme.com", org_id="acme")
        assert ctx.user_email == "jane@acme.com"
        assert ctx.org_id == "acme"


class TestBaseAgent:
    """BaseAgent abstract class behavior."""

    def test_cannot_instantiate_abstract(self):
        """BaseAgent is abstract — cannot be instantiated directly."""
        from maestro_nerve.base_agent import BaseAgent
        with pytest.raises(TypeError):
            BaseAgent()

    def test_subclass_must_implement_generate_insights(self):
        """Subclass without generate_insights cannot be instantiated."""
        from maestro_nerve.base_agent import BaseAgent
        class BadAgent(BaseAgent):
            AGENT_NAME = "bad"
            AGENT_DESCRIPTION = "doesn't implement generate_insights"
        with pytest.raises(TypeError):
            BadAgent()

    def test_subclass_with_generate_insights_works(self):
        from maestro_nerve.base_agent import BaseAgent, AgentInsight, AgentContext
        class GoodAgent(BaseAgent):
            AGENT_NAME = "good"
            AGENT_DESCRIPTION = "implements generate_insights"
            def generate_insights(self, ctx):
                return [AgentInsight(
                    id="g1", agent=self.AGENT_NAME, title="t", body="b",
                    confidence=0.85,
                )]
        agent = GoodAgent()
        ctx = AgentContext()
        insights = agent.generate_insights(ctx)
        assert len(insights) == 1
        assert insights[0].agent == "good"

    def test_evidence_helper(self):
        """BaseAgent.evidence() builds evidence-chain entries."""
        from maestro_nerve.base_agent import BaseAgent
        ev = BaseAgent.evidence("deal_health_engine", entity="acme", score=42.5)
        assert ev["source"] == "deal_health_engine"
        assert ev["entity"] == "acme"
        assert ev["score"] == 42.5

    def test_apply_confidence_gate_filters_low_confidence(self):
        """P25: apply_confidence_gate removes sub-threshold insights."""
        from maestro_nerve.base_agent import BaseAgent, AgentInsight
        insights = [
            AgentInsight(id="1", agent="x", title="t1", body="b", confidence=0.90),
            AgentInsight(id="2", agent="x", title="t2", body="b", confidence=0.30),
            AgentInsight(id="3", agent="x", title="t3", body="b", confidence=0.65),
        ]
        filtered = BaseAgent.apply_confidence_gate(insights, strict=True)
        assert len(filtered) == 2  # 0.90 and 0.65 pass, 0.30 fails
        assert all(i.confidence >= 0.60 for i in filtered)

    def test_sort_by_priority(self):
        """sort_by_priority orders high -> medium -> low."""
        from maestro_nerve.base_agent import BaseAgent, AgentInsight
        insights = [
            AgentInsight(id="1", agent="x", title="t1", body="b",
                         confidence=0.90, priority="low"),
            AgentInsight(id="2", agent="x", title="t2", body="b",
                         confidence=0.70, priority="high"),
            AgentInsight(id="3", agent="x", title="t3", body="b",
                         confidence=0.85, priority="medium"),
        ]
        sorted_insights = BaseAgent.sort_by_priority(insights)
        assert sorted_insights[0].priority == "high"
        assert sorted_insights[1].priority == "medium"
        assert sorted_insights[2].priority == "low"

    def test_sort_by_priority_secondary_by_confidence(self):
        """When priority is equal, higher confidence comes first."""
        from maestro_nerve.base_agent import BaseAgent, AgentInsight
        insights = [
            AgentInsight(id="1", agent="x", title="t1", body="b",
                         confidence=0.70, priority="high"),
            AgentInsight(id="2", agent="x", title="t2", body="b",
                         confidence=0.90, priority="high"),
        ]
        sorted_insights = BaseAgent.sort_by_priority(insights)
        assert sorted_insights[0].confidence == 0.90
        assert sorted_insights[1].confidence == 0.70


class TestAgentRegistry:
    """Agent registry functions."""

    def test_list_agents_returns_list(self):
        from maestro_nerve.base_agent import list_agents
        agents = list_agents()
        assert isinstance(agents, list)
        # After importing the agent modules, should have 17+
        # (But we don't import here — that's tested in TestAllAgents.)

    def test_get_agent_returns_none_for_unknown(self):
        from maestro_nerve.base_agent import get_agent
        assert get_agent("nonexistent_agent_xyz") is None

    def test_register_and_get_agent(self):
        from maestro_nerve.base_agent import (
            BaseAgent, AgentInsight, AgentContext,
            register_agent, get_agent, _AGENT_REGISTRY,
        )

        @register_agent
        class TestAgent(BaseAgent):
            AGENT_NAME = "_test_temp_agent"
            AGENT_DESCRIPTION = "test"
            def generate_insights(self, ctx):
                return []

        try:
            agent = get_agent("_test_temp_agent")
            assert agent is not None
            assert agent.AGENT_NAME == "_test_temp_agent"
        finally:
            # Clean up the registry so this test agent doesn't contaminate
            # other tests that assert exact agent counts.
            _AGENT_REGISTRY.pop("_test_temp_agent", None)


class TestNullOemState:
    """_NullOemState fallback for standalone mode."""

    def test_signals_is_empty_list(self):
        from maestro_nerve.base_agent import _NullOemState
        state = _NullOemState()
        assert state.signals == []

    def test_unknown_attr_returns_none(self):
        from maestro_nerve.base_agent import _NullOemState
        state = _NullOemState()
        assert state.anything_else is None

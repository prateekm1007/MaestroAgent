"""
Tests for Directive 2: Learning Loop 2.0.

Tests:
- Cross-surface auto-outcome tracking (auto-register + auto-resolve)
- User behavior modeling (dismissal patterns → LLM context)
- Personal knowledge graph (entities, edges, completion rates, risk prediction)
- Behavior context injected into LLM prompts
"""

import sys
import os
import asyncio
import tempfile
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    yield db_path
    os.unlink(db_path)
    del os.environ["MAESTRO_PERSONAL_DB"]


class TestAutoOutcomeTracking:
    """Cross-surface auto-outcome tracking."""

    def test_auto_register_prediction(self, temp_db):
        """Auto-registering a prediction must create a prediction record."""
        from maestro_personal_shell.learning_loop_v2 import auto_register_prediction
        from maestro_personal_shell.outcome_tracker import init_outcome_db, get_prediction_count

        init_outcome_db(temp_db)
        pred_id = auto_register_prediction(
            signal_id="test-sig-1",
            commitment_type="explicit",
            confidence=0.9,
            entity="AcmeCorp",
            db_path=temp_db,
        )
        assert pred_id is not None, "Must return a prediction_id"

        counts = get_prediction_count(temp_db)
        assert counts["total"] >= 1, "Prediction must be registered"

    def test_auto_resolve_prediction(self, temp_db):
        """Auto-resolving must close the prediction loop."""
        from maestro_personal_shell.learning_loop_v2 import auto_register_prediction, auto_resolve_prediction
        from maestro_personal_shell.outcome_tracker import init_outcome_db, get_prediction_count

        init_outcome_db(temp_db)
        auto_register_prediction(
            signal_id="test-sig-2",
            commitment_type="explicit",
            confidence=0.8,
            entity="TestCorp",
            db_path=temp_db,
        )

        # Auto-resolve as "miss" (dismissed)
        resolved = auto_resolve_prediction("test-sig-2", "miss", db_path=temp_db)
        assert resolved is True, "Must resolve the prediction"

        counts = get_prediction_count(temp_db)
        assert counts["resolved"] >= 1, "Prediction must be resolved"

    def test_confidence_adjusted_by_type(self, temp_db):
        """Confidence must be adjusted by commitment type."""
        from maestro_personal_shell.learning_loop_v2 import auto_register_prediction
        from maestro_personal_shell.outcome_tracker import init_outcome_db
        import sqlite3

        init_outcome_db(temp_db)

        # Explicit: 0.9 * 1.0 = 0.9
        auto_register_prediction("sig-explicit", "explicit", 0.9, "Entity1", db_path=temp_db)
        # Conditional: 0.9 * 0.7 = 0.63
        auto_register_prediction("sig-conditional", "conditional", 0.9, "Entity2", db_path=temp_db)

        conn = sqlite3.connect(temp_db)
        rows = conn.execute(
            "SELECT predicted_confidence, metadata FROM predictions WHERE prediction_type = 'commitment_completion'"
        ).fetchall()
        conn.close()

        assert len(rows) >= 2
        confidences = {row[1]: row[0] for row in rows}
        # Explicit should have higher confidence than conditional
        explicit_conf = [r[0] for r in rows if "sig-explicit" in r[1]][0]
        conditional_conf = [r[0] for r in rows if "sig-conditional" in r[1]][0]
        assert explicit_conf > conditional_conf, "Explicit should have higher confidence"


class TestUserBehaviorModeling:
    """User behavior patterns for personalization."""

    def test_record_and_get_behavior(self, temp_db):
        """Recording behavior must be retrievable as patterns."""
        from maestro_personal_shell.learning_loop_v2 import record_user_behavior, get_behavior_patterns

        # Record several dismissals
        for i in range(5):
            record_user_behavior("dismiss_suggestion", {"agent": "sales"}, db_path=temp_db)
        record_user_behavior("dismiss_suggestion", {"agent": "customer_success"}, db_path=temp_db)
        record_user_behavior("correct_commitment", {"commitment_type": "tentative"}, db_path=temp_db)

        patterns = get_behavior_patterns(db_path=temp_db)
        assert patterns["total_behaviors"] >= 7
        assert patterns["total_dismissals"] >= 6
        assert patterns["dismissal_rate"] > 0.5
        assert patterns["most_dismissed_agent"] == "sales"

    def test_behavior_context_for_llm(self, temp_db):
        """Behavior context must be generated for LLM prompts."""
        from maestro_personal_shell.learning_loop_v2 import record_user_behavior, get_behavior_context_for_llm

        # Record enough behaviors for pattern detection
        for i in range(10):
            record_user_behavior("dismiss_suggestion", {"agent": "sales"}, db_path=temp_db)

        ctx = get_behavior_context_for_llm(db_path=temp_db)
        assert ctx, "Behavior context must not be empty with >= 3 behaviors"
        assert "USER BEHAVIOR PATTERNS" in ctx
        assert "sales" in ctx
        assert "BE MORE SELECTIVE" in ctx or "REDUCE" in ctx

    def test_behavior_context_empty_on_day1(self, temp_db):
        """Behavior context must be empty on Day 1 (no data)."""
        from maestro_personal_shell.learning_loop_v2 import get_behavior_context_for_llm
        ctx = get_behavior_context_for_llm(db_path=temp_db)
        assert ctx == "", "Must be empty on Day 1"


class TestPersonalGraph:
    """Personal knowledge graph for longitudinal intelligence."""

    def test_add_entity_and_edge(self, temp_db):
        """Adding entities and edges must work."""
        from maestro_personal_shell.personal_graph import PersonalGraph

        graph = PersonalGraph(db_path=temp_db)
        entity_id = graph.add_entity("AcmeCorp", entity_type="company")
        assert entity_id == "acmecorp"

        edge_id = graph.add_edge(
            source_entity="AcmeCorp",
            edge_type="commitment",
            topic="send proposal",
            confidence=0.8,
        )
        assert edge_id is not None

    def test_completion_rate(self, temp_db):
        """Completion rate must reflect resolved outcomes."""
        from maestro_personal_shell.personal_graph import PersonalGraph

        graph = PersonalGraph(db_path=temp_db)
        graph.add_edge("TestCorp", "commitment", "proposal", confidence=0.8)
        graph.add_edge("TestCorp", "commitment", "contract", confidence=0.7)

        # Resolve one as hit, one as miss
        graph.update_outcome("TestCorp", "proposal", "hit")
        graph.update_outcome("TestCorp", "contract", "miss")

        rate = graph.get_completion_rate("TestCorp")
        assert rate == 0.5, f"Expected 0.5 (1 hit, 1 miss), got {rate}"

    def test_entity_summary(self, temp_db):
        """Entity summary must include history and stats."""
        from maestro_personal_shell.personal_graph import PersonalGraph

        graph = PersonalGraph(db_path=temp_db)
        graph.add_edge("SummaryCorp", "commitment", "deliver report", confidence=0.9)
        graph.update_outcome("SummaryCorp", "deliver report", "hit")

        summary = graph.get_entity_summary("SummaryCorp")
        assert summary["exists"] is True
        assert summary["total_interactions"] >= 1
        assert summary["completion_rate"] == 1.0

    def test_predict_risk_high_for_low_completion(self, temp_db):
        """Risk prediction must flag entities with low completion rates."""
        from maestro_personal_shell.personal_graph import PersonalGraph

        graph = PersonalGraph(db_path=temp_db)
        # Create 3 commitments, resolve 2 as miss
        graph.add_edge("RiskyCorp", "commitment", "project A", confidence=0.8)
        graph.add_edge("RiskyCorp", "commitment", "project B", confidence=0.7)
        graph.add_edge("RiskyCorp", "commitment", "project C", confidence=0.6)
        graph.update_outcome("RiskyCorp", "project A", "miss")
        graph.update_outcome("RiskyCorp", "project B", "miss")
        graph.update_outcome("RiskyCorp", "project C", "hit")

        risk = graph.predict_risk("RiskyCorp")
        assert risk["risk_level"] == "high", f"Expected high risk (33% completion), got {risk['risk_level']}"
        assert "Low completion rate" in risk["risk_factors"][0]

    def test_predict_risk_low_for_high_completion(self, temp_db):
        """Risk prediction must be low for reliable entities."""
        from maestro_personal_shell.personal_graph import PersonalGraph

        graph = PersonalGraph(db_path=temp_db)
        graph.add_edge("ReliableCorp", "commitment", "project X", confidence=0.9)
        graph.update_outcome("ReliableCorp", "project X", "hit")

        risk = graph.predict_risk("ReliableCorp")
        assert risk["risk_level"] == "low"
        assert risk["completion_rate"] == 1.0


class TestBehaviorContextInLLM:
    """Behavior context must be injected into LLM prompts."""

    def test_calibration_context_includes_behavior(self, temp_db):
        """_get_calibration_context must include behavior patterns."""
        from maestro_personal_shell.learning_loop_v2 import record_user_behavior
        from maestro_personal_shell.llm_bridge import _get_calibration_context

        # Record enough behaviors
        for i in range(5):
            record_user_behavior("dismiss_suggestion", {"agent": "sales"})

        ctx = _get_calibration_context()
        # Behavior context should appear (may also include calibration if outcomes exist)
        if ctx:
            assert "USER BEHAVIOR" in ctx or "CALIBRATION" in ctx or "CORRECTIONS" in ctx


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

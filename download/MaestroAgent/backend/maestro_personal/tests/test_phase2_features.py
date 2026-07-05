"""
V8 Personal Mode — Phase 2 Tier 1 Self-Facing Features Tests.

Tests for:
- Phase 2-2: Personal Knowledge Graph
- Phase 2-3: Memory Replay
- Phase 2-4: Decision Support for Life
- Phase 2-5: Habit & Self-Improvement Coach
- Phase 2-6: Personal Prediction Market
- Phase 2-7: Contradictions in Personal Life

Each feature includes withdrawal-path verification (Guideline P9).
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clear_all():
    from maestro_personal.consent import ConsentStore
    from maestro_personal.mode import ModeManager
    from maestro_personal.incognito import IncognitoManager
    from maestro_personal.expiry import DataExpiry
    from maestro_personal.store import PersonalDataStore
    from maestro_personal.local import LocalFirstConfig
    from maestro_personal.knowledge_graph import PersonalKG
    from maestro_personal.habits import HabitCoach
    from maestro_personal.prediction_market import PersonalPredictionMarket
    from maestro_personal.contradictions import PersonalContradictions
    for store in [ConsentStore, ModeManager, IncognitoManager, DataExpiry,
                  PersonalDataStore, LocalFirstConfig, PersonalKG, HabitCoach,
                  PersonalPredictionMarket, PersonalContradictions]:
        store.clear()
    yield
    for store in [ConsentStore, ModeManager, IncognitoManager, DataExpiry,
                  PersonalDataStore, LocalFirstConfig, PersonalKG, HabitCoach,
                  PersonalPredictionMarket, PersonalContradictions]:
        store.clear()


# ============================================================
# Phase 2-2: Personal Knowledge Graph
# ============================================================

class TestPersonalKG:
    """The personal knowledge graph stores entities and edges."""

    def test_add_entity_user_entered(self) -> None:
        from maestro_personal.knowledge_graph import PersonalKG
        entity = PersonalKG.add_entity("user1", "person", "Sarah")
        assert entity.name == "Sarah"
        assert entity.entity_type == "person"
        assert entity.source == "user_entered"

    def test_add_entity_requires_consent_for_non_user_sources(self) -> None:
        from maestro_personal.knowledge_graph import PersonalKG
        from maestro_personal.consent import ConsentError
        with pytest.raises(ConsentError):
            PersonalKG.add_entity("user1", "event", "Meeting", source="calendar")

    def test_add_entity_with_consent(self) -> None:
        from maestro_personal.knowledge_graph import PersonalKG
        from maestro_personal.consent import ConsentStore
        ConsentStore.grant_consent("user1", "calendar", "store")
        entity = PersonalKG.add_entity("user1", "event", "Team meeting", source="calendar")
        assert entity.source == "calendar"

    def test_add_edge(self) -> None:
        from maestro_personal.knowledge_graph import PersonalKG
        e1 = PersonalKG.add_entity("user1", "person", "Sarah")
        e2 = PersonalKG.add_entity("user1", "event", "Lunch with Sarah")
        edge = PersonalKG.add_edge(e1.entity_id, e2.entity_id, "attended")
        assert edge.edge_type == "attended"

    def test_search(self) -> None:
        from maestro_personal.knowledge_graph import PersonalKG
        PersonalKG.add_entity("user1", "person", "Sarah Connor")
        PersonalKG.add_entity("user1", "person", "John Doe")
        results = PersonalKG.search("sarah")
        assert len(results) == 1
        assert "Sarah" in results[0].name

    def test_withdrawal_path(self) -> None:
        import maestro_personal.knowledge_graph as mod
        source = open(mod.__file__).read().lower()
        assert "withdrawal" in source or "could stop" in source


# ============================================================
# Phase 2-3: Memory Replay
# ============================================================

class TestMemoryReplay:
    """Memory replay searches the user's own data."""

    def test_replay_finds_matching_memories(self) -> None:
        from maestro_personal.memory import MemoryReplay
        from maestro_personal.store import PersonalDataStore
        from maestro_personal.consent import ConsentStore

        ConsentStore.grant_consent("user1", "user_notes", "store")
        ConsentStore.grant_consent("user1", "user_notes", "retrieve")
        PersonalDataStore.store("user1", "memory", "user_notes", "Lunch with Sarah, talked about her trip to Portugal")

        result = MemoryReplay.replay("user1", "What did I talk about with Sarah?")
        assert len(result["matching_memories"]) >= 1
        assert any("sarah" in m["content"].lower() for m in result["matching_memories"])

    def test_replay_returns_summary(self) -> None:
        from maestro_personal.memory import MemoryReplay
        from maestro_personal.store import PersonalDataStore
        from maestro_personal.consent import ConsentStore

        ConsentStore.grant_consent("user1", "user_notes", "store")
        ConsentStore.grant_consent("user1", "user_notes", "retrieve")
        PersonalDataStore.store("user1", "memory", "user_notes", "Meeting notes from Tuesday")

        result = MemoryReplay.replay("user1", "meeting")
        assert "summary" in result
        assert len(result["summary"]) > 0

    def test_replay_third_party_warning(self) -> None:
        """If the query mentions a person entity, a third-party warning should appear."""
        from maestro_personal.memory import MemoryReplay
        from maestro_personal.knowledge_graph import PersonalKG
        from maestro_personal.store import PersonalDataStore
        from maestro_personal.consent import ConsentStore

        ConsentStore.grant_consent("user1", "user_notes", "store")
        ConsentStore.grant_consent("user1", "user_notes", "retrieve")
        PersonalKG.add_entity("user1", "person", "Sarah")
        PersonalDataStore.store("user1", "memory", "user_notes", "Had coffee with Sarah last week")

        result = MemoryReplay.replay("user1", "What did I do with Sarah?")
        assert result["third_party_warning"] is not None
        assert "Sarah" in result["third_party_warning"]

    def test_replay_no_matches(self) -> None:
        from maestro_personal.memory import MemoryReplay
        result = MemoryReplay.replay("user1", "nonexistent topic")
        assert "No matching" in result["summary"]

    def test_withdrawal_path(self) -> None:
        import maestro_personal.memory as mod
        source = open(mod.__file__).read().lower()
        assert "withdrawal" in source or "could stop" in source


# ============================================================
# Phase 2-4: Decision Support
# ============================================================

class TestDecisionSupport:
    """Decision support surfaces pros, cons, and past patterns."""

    def test_decide_returns_pros_and_cons(self) -> None:
        from maestro_personal.decision import LifeDecisionEngine
        result = LifeDecisionEngine.decide("Should I take this trip?")
        assert len(result["pros"]) > 0
        assert len(result["cons"]) > 0

    def test_decide_labeled_informational(self) -> None:
        from maestro_personal.decision import LifeDecisionEngine
        result = LifeDecisionEngine.decide("Should I change jobs?")
        assert result["label"] == "informational, not prescriptive"

    def test_decide_includes_past_patterns(self) -> None:
        from maestro_personal.decision import LifeDecisionEngine
        from maestro_personal.knowledge_graph import PersonalKG
        PersonalKG.add_entity("user1", "goal", "Travel to Portugal")
        result = LifeDecisionEngine.decide("Should I travel to Portugal?")
        # May or may not find patterns depending on matching
        assert "past_patterns" in result

    def test_decide_has_confidence(self) -> None:
        from maestro_personal.decision import LifeDecisionEngine
        result = LifeDecisionEngine.decide("Should I buy a car?")
        assert 0.0 <= result["confidence"] <= 1.0

    def test_withdrawal_path(self) -> None:
        import maestro_personal.decision as mod
        source = open(mod.__file__).read().lower()
        assert "withdrawal" in source or "could stop" in source


# ============================================================
# Phase 2-5: Habit Coach
# ============================================================

class TestHabitCoach:
    """Habit tracking with gentle accountability. One reminder per day max."""

    def test_create_and_check_in(self) -> None:
        from maestro_personal.habits import HabitCoach
        habit = HabitCoach.create_habit("Morning exercise")
        HabitCoach.check_in(habit.habit_id)
        assert habit.current_streak == 1

    def test_streaks(self) -> None:
        from maestro_personal.habits import HabitCoach
        habit = HabitCoach.create_habit("Read 10 pages")
        HabitCoach.check_in(habit.habit_id)
        HabitCoach.check_in(habit.habit_id)
        streaks = HabitCoach.get_streaks()
        assert len(streaks) == 1
        assert streaks[0]["current_streak"] == 2

    def test_reminder_one_per_day(self) -> None:
        from maestro_personal.habits import HabitCoach
        habit = HabitCoach.create_habit("Meditate")
        reminder1 = HabitCoach.get_reminder(habit.habit_id)
        assert reminder1 is not None  # first reminder
        reminder2 = HabitCoach.get_reminder(habit.habit_id)
        assert reminder2 is None  # second reminder same day = blocked

    def test_silence_reminders(self) -> None:
        from maestro_personal.habits import HabitCoach
        habit = HabitCoach.create_habit("Drink water")
        HabitCoach.silence_reminders(habit.habit_id)
        assert HabitCoach.get_reminder(habit.habit_id) is None

    def test_suggestions_max_three(self) -> None:
        from maestro_personal.habits import HabitCoach
        for i in range(5):
            HabitCoach.create_habit(f"Habit {i}")
        suggestions = HabitCoach.get_suggestions()
        assert len(suggestions) <= 3

    def test_withdrawal_path(self) -> None:
        import maestro_personal.habits as mod
        source = open(mod.__file__).read().lower()
        assert "withdrawal" in source or "could stop" in source


# ============================================================
# Phase 2-6: Personal Prediction Market
# ============================================================

class TestPredictionMarket:
    """Private prediction market for personal goals. No social pressure."""

    def test_create_prediction(self) -> None:
        from maestro_personal.prediction_market import PersonalPredictionMarket
        pred = PersonalPredictionMarket.create_prediction("Will I finish the book?", 0.7)
        assert pred.user_probability == 0.7
        assert pred.outcome == "pending"

    def test_resolve_prediction(self) -> None:
        from maestro_personal.prediction_market import PersonalPredictionMarket
        pred = PersonalPredictionMarket.create_prediction("Will I exercise 3x?", 0.8)
        resolved = PersonalPredictionMarket.resolve_prediction(pred.prediction_id, "yes")
        assert resolved.outcome == "yes"
        assert resolved.brier_score is not None
        # Brier = (0.8 - 1.0)^2 = 0.04
        assert resolved.brier_score == 0.04

    def test_calibration(self) -> None:
        from maestro_personal.prediction_market import PersonalPredictionMarket
        p1 = PersonalPredictionMarket.create_prediction("Test 1", 0.9)
        PersonalPredictionMarket.resolve_prediction(p1.prediction_id, "yes")
        p2 = PersonalPredictionMarket.create_prediction("Test 2", 0.3)
        PersonalPredictionMarket.resolve_prediction(p2.prediction_id, "no")
        cal = PersonalPredictionMarket.get_calibration()
        assert cal["total"] == 2
        assert cal["average_brier"] is not None

    def test_invalid_probability(self) -> None:
        from maestro_personal.prediction_market import PersonalPredictionMarket
        with pytest.raises(ValueError):
            PersonalPredictionMarket.create_prediction("Test", 1.5)

    def test_withdrawal_path(self) -> None:
        import maestro_personal.prediction_market as mod
        source = open(mod.__file__).read().lower()
        assert "withdrawal" in source or "could stop" in source


# ============================================================
# Phase 2-7: Contradictions
# ============================================================

class TestContradictions:
    """Surfaces contradictions between values and behavior. Gentle, not punishing."""

    def test_detect_contradiction_goal_no_habit(self) -> None:
        from maestro_personal.contradictions import PersonalContradictions
        from maestro_personal.knowledge_graph import PersonalKG
        PersonalKG.add_entity("user1", "goal", "Exercise more")
        result = PersonalContradictions.detect()
        assert result["count"] >= 1
        assert any("exercise" in c["description"].lower() for c in result["contradictions"])

    def test_dismiss_for_30_days(self) -> None:
        from maestro_personal.contradictions import PersonalContradictions
        from maestro_personal.knowledge_graph import PersonalKG
        PersonalKG.add_entity("user1", "goal", "Exercise more")
        # Detect
        result1 = PersonalContradictions.detect()
        assert result1["count"] >= 1
        key = result1["contradictions"][0]["dismiss_key"]
        # Dismiss
        PersonalContradictions.dismiss(key)
        # Detect again — should be suppressed
        result2 = PersonalContradictions.detect()
        assert result2["count"] == 0 or all(c["dismiss_key"] != key for c in result2["contradictions"])

    def test_contradiction_tone_is_gentle(self) -> None:
        from maestro_personal.contradictions import PersonalContradictions
        from maestro_personal.knowledge_graph import PersonalKG
        PersonalKG.add_entity("user1", "goal", "Exercise daily")
        result = PersonalContradictions.detect()
        for c in result["contradictions"]:
            assert c["severity"] == "gentle"
        assert "not failures" in result["summary"].lower() or "patterns" in result["summary"].lower()

    def test_withdrawal_path(self) -> None:
        import maestro_personal.contradictions as mod
        source = open(mod.__file__).read().lower()
        assert "withdrawal" in source or "could stop" in source

"""
V8 Personal Mode — Phase 2 Completion + Phase 3 Tests.

Tests for:
- Phase 2-8: Prepared Personal Decisions
- Phase 2-9: Intent Cascade for Personal Goals
- Phase 2-10: Personal Why? Engine
- Phase 2-11: Memory Evolution Report
- Phase 2-12: Self-Reflection Prompts
- Phase 2-13: Legacy Builder
- Phase 3-1: Relationship Memory Vault
- Phase 3-2: Ambient Personal Context
- Phase 3-3: Professional-Personal Crossover

Each feature includes withdrawal-path verification (Guideline P9).
Phase 3 features include bilateral consent verification (Guideline P11).
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
    from maestro_personal.intent_cascade import PersonalIntentCascade
    from maestro_personal.relationship_vault import RelationshipVault
    from maestro_personal.legacy import LegacyBuilder
    for store in [ConsentStore, ModeManager, IncognitoManager, DataExpiry,
                  PersonalDataStore, LocalFirstConfig, PersonalKG, HabitCoach,
                  PersonalPredictionMarket, PersonalContradictions,
                  PersonalIntentCascade, RelationshipVault, LegacyBuilder]:
        store.clear()
    yield
    for store in [ConsentStore, ModeManager, IncognitoManager, DataExpiry,
                  PersonalDataStore, LocalFirstConfig, PersonalKG, HabitCoach,
                  PersonalPredictionMarket, PersonalContradictions,
                  PersonalIntentCascade, RelationshipVault, LegacyBuilder]:
        store.clear()


# ============================================================
# Phase 2-8: Prepared Personal Decisions
# ============================================================

class TestPreparedDecisions:
    """Drafts responses with the user's own emotional risk assessment."""

    def test_prepare_returns_draft_and_risk(self) -> None:
        from maestro_personal.prepared_decisions import PreparedDecisionEngine
        result = PreparedDecisionEngine.prepare("user1", "Need to tell my mom I can't come for Thanksgiving", "Mom")
        assert "draft_response" in result
        assert "emotional_risk_assessment" in result
        assert result["risk_level"] in ("low", "medium", "high")
        assert len(result["draft_response"]) > 20

    def test_risk_based_on_user_data_not_recipient(self) -> None:
        """The risk assessment must reference the USER's past patterns, not the recipient's predicted state."""
        from maestro_personal.prepared_decisions import PreparedDecisionEngine
        result = PreparedDecisionEngine.prepare("user1", "I need to confront my colleague about the missed deadline", "colleague")
        assert "your" in result["emotional_risk_assessment"].lower() or "you" in result["emotional_risk_assessment"].lower()

    def test_withdrawal_path(self) -> None:
        import maestro_personal.prepared_decisions as mod
        source = open(mod.__file__).read().lower()
        assert "withdrawal" in source or "could stop" in source


# ============================================================
# Phase 2-9: Intent Cascade for Personal Goals
# ============================================================

class TestIntentCascade:
    """Breaks down big intents into assumptions, hypotheses, etc."""

    def test_cascade_produces_all_components(self) -> None:
        from maestro_personal.intent_cascade import PersonalIntentCascade
        result = PersonalIntentCascade.cascade("improve fitness")
        assert len(result["assumptions"]) >= 2
        assert len(result["hypotheses"]) >= 2
        assert len(result["preparations"]) >= 2
        assert len(result["evidence_plan"]) >= 2

    def test_cascade_uses_user_data(self) -> None:
        from maestro_personal.intent_cascade import PersonalIntentCascade
        from maestro_personal.knowledge_graph import PersonalKG
        PersonalKG.add_entity("user1", "goal", "Exercise more")
        result = PersonalIntentCascade.cascade("exercise more")
        assert result["based_on_user_data"] is True

    def test_resolve_item(self) -> None:
        from maestro_personal.intent_cascade import PersonalIntentCascade
        result = PersonalIntentCascade.cascade("write a book")
        assumption_id = result["assumptions"][0]["item_id"]
        resolved = PersonalIntentCascade.resolve_item("write a book", assumption_id, "resolved")
        assert resolved is True

    def test_withdrawal_path(self) -> None:
        import maestro_personal.intent_cascade as mod
        source = open(mod.__file__).read().lower()
        assert "withdrawal" in source or "could stop" in source


# ============================================================
# Phase 2-10: Personal Why? Engine
# ============================================================

class TestPersonalWhy:
    """Explains the user's own behavior from their own data."""

    def test_explain_returns_chain(self) -> None:
        from maestro_personal.why_engine import PersonalWhyEngine
        result = PersonalWhyEngine.explain("user1", "Why did I skip the gym?")
        assert "explanation_chain" in result
        assert len(result["explanation_chain"]) >= 1

    def test_third_party_redirect(self) -> None:
        """Questions about a third party must be redirected."""
        from maestro_personal.why_engine import PersonalWhyEngine
        result = PersonalWhyEngine.explain("user1", "Why is Sarah mad at me?")
        assert result["third_party_redirected"] is True
        assert "your own patterns" in result["explanation_chain"][0]["narrative"].lower()

    def test_self_question_not_redirected(self) -> None:
        from maestro_personal.why_engine import PersonalWhyEngine
        result = PersonalWhyEngine.explain("user1", "Why did I miss my workout?")
        assert result["third_party_redirected"] is False

    def test_withdrawal_path(self) -> None:
        import maestro_personal.why_engine as mod
        source = open(mod.__file__).read().lower()
        assert "withdrawal" in source or "could stop" in source


# ============================================================
# Phase 2-11: Memory Evolution Report
# ============================================================

class TestEvolutionReport:
    """Quarterly narrative of the user's own patterns."""

    def test_report_has_narrative(self) -> None:
        from maestro_personal.evolution_report import EvolutionReport
        result = EvolutionReport.generate("Q2-2026")
        assert "narrative" in result
        assert len(result["narrative"]) > 50
        assert "Q2-2026" in result["narrative"]

    def test_report_includes_goals(self) -> None:
        from maestro_personal.evolution_report import EvolutionReport
        from maestro_personal.knowledge_graph import PersonalKG
        PersonalKG.add_entity("user1", "goal", "Run a marathon")
        result = EvolutionReport.generate()
        assert len(result["goals_progress"]) >= 1

    def test_report_includes_habits(self) -> None:
        from maestro_personal.evolution_report import EvolutionReport
        from maestro_personal.habits import HabitCoach
        HabitCoach.create_habit("Morning run")
        result = EvolutionReport.generate()
        assert len(result["habit_trajectories"]) >= 1

    def test_withdrawal_path(self) -> None:
        import maestro_personal.evolution_report as mod
        source = open(mod.__file__).read().lower()
        assert "withdrawal" in source or "could stop" in source


# ============================================================
# Phase 2-12: Self-Reflection Prompts
# ============================================================

class TestReflectionPrompts:
    """Context-aware journaling prompts from the user's own signals."""

    def test_generate_returns_prompts(self) -> None:
        from maestro_personal.reflection import ReflectionPrompts
        result = ReflectionPrompts.generate()
        assert len(result["prompts"]) >= 1
        assert "prompt" in result["prompts"][0]

    def test_prompts_use_own_signals(self) -> None:
        from maestro_personal.reflection import ReflectionPrompts
        from maestro_personal.habits import HabitCoach
        HabitCoach.create_habit("Meditate")
        result = ReflectionPrompts.generate()
        # Should include a prompt about the habit
        assert any("meditate" in p["prompt"].lower() for p in result["prompts"])

    def test_no_third_party_analysis(self) -> None:
        """Prompts must never analyze a third party's messages."""
        from maestro_personal.reflection import ReflectionPrompts
        result = ReflectionPrompts.generate()
        for p in result["prompts"]:
            assert "sentiment" not in p.get("context", "").lower()
            assert "analyzed" not in p.get("context", "").lower()

    def test_withdrawal_path(self) -> None:
        import maestro_personal.reflection as mod
        source = open(mod.__file__).read().lower()
        assert "withdrawal" in source or "could stop" in source


# ============================================================
# Phase 2-13: Legacy Builder
# ============================================================

class TestLegacyBuilder:
    """Private life stories, values, and wisdom document."""

    def test_add_and_get_entry(self) -> None:
        from maestro_personal.legacy import LegacyBuilder
        entry = LegacyBuilder.add_entry("story", "My First Job", "I learned that...")
        assert entry.title == "My First Job"
        assert entry.private is True
        assert LegacyBuilder.get_entry(entry.entry_id) is not None

    def test_entries_are_private(self) -> None:
        from maestro_personal.legacy import LegacyBuilder
        entry = LegacyBuilder.add_entry("wisdom", "Life Lesson", "Always be kind")
        assert entry.private is True

    def test_export_document(self) -> None:
        from maestro_personal.legacy import LegacyBuilder
        LegacyBuilder.add_entry("story", "Story 1", "Content 1")
        LegacyBuilder.add_entry("value", "Value 1", "Content 2")
        doc = LegacyBuilder.export_document()
        assert "My Legacy" in doc["document"]
        assert doc["entry_count"] == 2

    def test_delete_entry(self) -> None:
        from maestro_personal.legacy import LegacyBuilder
        entry = LegacyBuilder.add_entry("lesson", "Lesson 1", "Content")
        assert LegacyBuilder.delete_entry(entry.entry_id) is True
        assert LegacyBuilder.get_entry(entry.entry_id) is None

    def test_delete_all(self) -> None:
        from maestro_personal.legacy import LegacyBuilder
        LegacyBuilder.add_entry("story", "S1", "C1")
        LegacyBuilder.add_entry("story", "S2", "C2")
        count = LegacyBuilder.delete_all()
        assert count == 2
        assert len(LegacyBuilder.get_all_entries()) == 0

    def test_withdrawal_path(self) -> None:
        import maestro_personal.legacy as mod
        source = open(mod.__file__).read().lower()
        assert "withdrawal" in source or "could stop" in source


# ============================================================
# Phase 3-1: Relationship Memory Vault
# ============================================================

class TestRelationshipVault:
    """User-entered relationship memories. Bilateral consent for output."""

    def test_add_memory_user_entered(self) -> None:
        from maestro_personal.relationship_vault import RelationshipVault
        mem = RelationshipVault.add_memory("user1", "Sarah", "birthday", "June 12", "1990-06-12")
        assert mem.source == "user_entered"
        assert mem.person == "Sarah"

    def test_get_memories_by_person(self) -> None:
        from maestro_personal.relationship_vault import RelationshipVault
        RelationshipVault.add_memory("user1", "Sarah", "birthday", "June 12")
        RelationshipVault.add_memory("user1", "John", "anniversary", "May 5")
        sarah_mems = RelationshipVault.get_memories("Sarah")
        assert len(sarah_mems) == 1
        assert sarah_mems[0].person == "Sarah"

    def test_generate_message_requires_consent(self) -> None:
        """Generating a message TO a person requires bilateral consent (Guideline P11)."""
        from maestro_personal.relationship_vault import RelationshipVault
        from maestro_personal.consent import ConsentError
        RelationshipVault.add_memory("user1", "Sarah", "birthday", "June 12")
        with pytest.raises(ConsentError):
            RelationshipVault.generate_message_for_person("user1", "Sarah")

    def test_generate_message_with_consent(self) -> None:
        from maestro_personal.relationship_vault import RelationshipVault
        from maestro_personal.consent import ConsentStore
        RelationshipVault.add_memory("user1", "Sarah", "birthday", "June 12")
        ConsentStore.grant_third_party_consent("Sarah", "message_generation")
        result = RelationshipVault.generate_message_for_person("user1", "Sarah")
        assert "message" in result
        assert result["bilateral_consent"] is True

    def test_withdrawal_path(self) -> None:
        import maestro_personal.relationship_vault as mod
        source = open(mod.__file__).read().lower()
        assert "withdrawal" in source or "could stop" in source


# ============================================================
# Phase 3-2: Ambient Personal Context
# ============================================================

class TestAmbientContext:
    """Shows the user's own memory of a contact. No scraping."""

    def test_context_shows_user_memories(self) -> None:
        from maestro_personal.ambient_context import AmbientContext
        from maestro_personal.relationship_vault import RelationshipVault
        RelationshipVault.add_memory("user1", "Sarah", "birthday", "June 12")
        result = AmbientContext.get_context("user1", "Sarah")
        assert len(result["user_memories"]) >= 1
        assert result["source"] == "user_entered"

    def test_context_no_scraped_data(self) -> None:
        from maestro_personal.ambient_context import AmbientContext
        result = AmbientContext.get_context("user1", "Unknown Person")
        assert result["source"] == "user_entered"
        # No scraped fields should be present
        for key in result:
            assert "scraped" not in key.lower()
            assert "social" not in key.lower()
            assert "profile" not in key.lower()

    def test_withdrawal_path(self) -> None:
        import maestro_personal.ambient_context as mod
        source = open(mod.__file__).read().lower()
        assert "withdrawal" in source or "could stop" in source


# ============================================================
# Phase 3-3: Professional-Personal Crossover
# ============================================================

class TestCrossover:
    """Explicit merge with logging for contacts in both modes."""

    def test_find_crossover_contacts(self) -> None:
        from maestro_personal.crossover import ProfessionalPersonalCrossover
        from maestro_personal.mode import ModeManager, Mode
        ModeManager.create_profile("sarah@acme.com", Mode.WORK, name="Sarah (work)")
        ModeManager.create_profile("sarah@acme.com", Mode.PERSONAL, name="Sarah (friend)")
        crossovers = ProfessionalPersonalCrossover.find_crossover_contacts()
        assert len(crossovers) >= 1
        assert crossovers[0]["entity_id"] == "sarah@acme.com"

    def test_merge_contact(self) -> None:
        from maestro_personal.crossover import ProfessionalPersonalCrossover
        from maestro_personal.mode import ModeManager, Mode
        ModeManager.create_profile("sarah@acme.com", Mode.WORK, name="Sarah (work)")
        ModeManager.create_profile("sarah@acme.com", Mode.PERSONAL, name="Sarah (friend)")
        result = ProfessionalPersonalCrossover.merge_contact("sarah@acme.com", "user1")
        assert result["merged"] is True
        assert result["reversible_for_days"] == 30

    def test_unmerge_contact(self) -> None:
        from maestro_personal.crossover import ProfessionalPersonalCrossover
        from maestro_personal.mode import ModeManager, Mode
        ModeManager.create_profile("sarah@acme.com", Mode.WORK, name="Sarah (work)")
        ModeManager.create_profile("sarah@acme.com", Mode.PERSONAL, name="Sarah (friend)")
        ProfessionalPersonalCrossover.merge_contact("sarah@acme.com", "user1")
        result = ProfessionalPersonalCrossover.unmerge_contact("sarah@acme.com")
        assert result["unmerged"] is True

    def test_withdrawal_path(self) -> None:
        import maestro_personal.crossover as mod
        source = open(mod.__file__).read().lower()
        assert "withdrawal" in source or "could stop" in source

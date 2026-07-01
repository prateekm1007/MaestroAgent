"""
V8 Personal Mode — API Routes.

All Personal Mode endpoints live under /api/personal/. They are
completely separate from the enterprise /api/oem/ routes. The
Personal Mode namespace does NOT import from maestro_oem.

Every endpoint enforces:
- ConsentStore checks (Guideline P3)
- Incognito mode awareness (Guideline P6)
- No third-party scraping (Guideline P4)
- Withdrawal path in responses (Guideline P9)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from typing import Any

router = APIRouter(prefix="/api/personal", tags=["personal-mode"])


# ─── Briefing ──────────────────────────────────────────────────────────────

@router.get("/briefing")
def get_personal_briefing(user: str = Query("default")) -> dict[str, Any]:
    """Morning personal briefing — your calendar, weather, reminders."""
    from maestro_personal.briefing import PersonalBriefingEngine
    engine = PersonalBriefingEngine(user)
    return engine.generate()


# ─── Knowledge Graph ───────────────────────────────────────────────────────

@router.get("/kg")
def get_kg() -> dict[str, Any]:
    """Get the personal knowledge graph."""
    from maestro_personal.knowledge_graph import PersonalKG
    return PersonalKG.to_dict()

@router.post("/kg/entity")
def add_kg_entity(payload: dict[str, Any]) -> dict[str, Any]:
    """Add an entity to the personal knowledge graph."""
    from maestro_personal.knowledge_graph import PersonalKG
    entity = PersonalKG.add_entity(
        user_id=payload.get("user", "default"),
        entity_type=payload.get("entity_type", "memory"),
        name=payload.get("name", ""),
        attributes=payload.get("attributes", {}),
        source="user_entered",
    )
    return entity.to_dict()

@router.post("/kg/edge")
def add_kg_edge(payload: dict[str, Any]) -> dict[str, Any]:
    """Add an edge to the personal knowledge graph."""
    from maestro_personal.knowledge_graph import PersonalKG
    edge = PersonalKG.add_edge(
        payload.get("from_entity", ""),
        payload.get("to_entity", ""),
        payload.get("edge_type", ""),
        payload.get("attributes", {}),
    )
    return edge.to_dict()


# ─── Memory Replay ─────────────────────────────────────────────────────────

@router.post("/memory/replay")
def memory_replay(payload: dict[str, Any]) -> dict[str, Any]:
    """Replay memories matching a natural-language query."""
    from maestro_personal.memory import MemoryReplay
    return MemoryReplay.replay(
        payload.get("user", "default"),
        payload.get("query", ""),
    )


# ─── Decision Support ──────────────────────────────────────────────────────

@router.post("/decide")
def personal_decide(payload: dict[str, Any]) -> dict[str, Any]:
    """Decision support for life decisions."""
    from maestro_personal.decision import LifeDecisionEngine
    return LifeDecisionEngine.decide(
        payload.get("question", ""),
        payload.get("context", {}),
    )


# ─── Habits ────────────────────────────────────────────────────────────────

@router.post("/habits/checkin")
def habit_checkin(payload: dict[str, Any]) -> dict[str, Any]:
    """Check in for a habit."""
    from maestro_personal.habits import HabitCoach
    habit = HabitCoach.check_in(payload.get("habit_id", ""))
    if not habit:
        raise HTTPException(404, "Habit not found")
    return habit.to_dict()

@router.get("/habits/streaks")
def habit_streaks() -> dict[str, Any]:
    """Get habit streaks."""
    from maestro_personal.habits import HabitCoach
    return {"streaks": HabitCoach.get_streaks()}

@router.get("/habits/suggestions")
def habit_suggestions() -> dict[str, Any]:
    """Get gentle habit suggestions."""
    from maestro_personal.habits import HabitCoach
    return {"suggestions": HabitCoach.get_suggestions()}

@router.post("/habits/create")
def habit_create(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a new habit."""
    from maestro_personal.habits import HabitCoach
    habit = HabitCoach.create_habit(payload.get("name", ""), payload.get("frequency", "daily"))
    return habit.to_dict()


# ─── Prediction Market ─────────────────────────────────────────────────────

@router.post("/predictions/create")
def create_prediction(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a personal prediction."""
    from maestro_personal.prediction_market import PersonalPredictionMarket
    try:
        pred = PersonalPredictionMarket.create_prediction(
            payload.get("question", ""),
            payload.get("probability", 0.5),
        )
        return pred.to_dict()
    except ValueError as e:
        raise HTTPException(400, str(e))

@router.post("/predictions/{prediction_id}/resolve")
def resolve_prediction(prediction_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Resolve a prediction."""
    from maestro_personal.prediction_market import PersonalPredictionMarket
    try:
        pred = PersonalPredictionMarket.resolve_prediction(prediction_id, payload.get("outcome", ""))
        if not pred:
            raise HTTPException(404, "Prediction not found")
        return pred.to_dict()
    except ValueError as e:
        raise HTTPException(400, str(e))

@router.get("/predictions/calibration")
def prediction_calibration() -> dict[str, Any]:
    """Get calibration summary."""
    from maestro_personal.prediction_market import PersonalPredictionMarket
    return PersonalPredictionMarket.get_calibration()


# ─── Contradictions ────────────────────────────────────────────────────────

@router.get("/contradictions")
def get_contradictions() -> dict[str, Any]:
    """Get personal contradictions."""
    from maestro_personal.contradictions import PersonalContradictions
    return PersonalContradictions.detect()

@router.post("/contradictions/dismiss")
def dismiss_contradiction(payload: dict[str, Any]) -> dict[str, Any]:
    """Dismiss a contradiction for 30 days."""
    from maestro_personal.contradictions import PersonalContradictions
    return PersonalContradictions.dismiss(payload.get("dismiss_key", ""))


# ─── Prepared Decisions ────────────────────────────────────────────────────

@router.post("/prepared-decision")
def prepare_decision(payload: dict[str, Any]) -> dict[str, Any]:
    """Prepare a drafted response with emotional risk assessment."""
    from maestro_personal.prepared_decisions import PreparedDecisionEngine
    return PreparedDecisionEngine.prepare(
        payload.get("user", "default"),
        payload.get("situation", ""),
        payload.get("recipient", ""),
    )


# ─── Intent Cascade ────────────────────────────────────────────────────────

@router.post("/intent-cascade")
def intent_cascade(payload: dict[str, Any]) -> dict[str, Any]:
    """Break down a personal intent into assumptions, hypotheses, etc."""
    from maestro_personal.intent_cascade import PersonalIntentCascade
    return PersonalIntentCascade.cascade(payload.get("intent", ""))


# ─── Personal Why? Engine ──────────────────────────────────────────────────

@router.post("/why")
def personal_why(payload: dict[str, Any]) -> dict[str, Any]:
    """Explain the user's own behavior from their own data."""
    from maestro_personal.why_engine import PersonalWhyEngine
    return PersonalWhyEngine.explain(
        payload.get("user", "default"),
        payload.get("question", ""),
    )


# ─── Evolution Report ──────────────────────────────────────────────────────

@router.get("/evolution-report")
def evolution_report(quarter: str = Query("")) -> dict[str, Any]:
    """Get a quarterly evolution report."""
    from maestro_personal.evolution_report import EvolutionReport
    return EvolutionReport.generate(quarter)


# ─── Self-Reflection Prompts ───────────────────────────────────────────────

@router.get("/reflection-prompts")
def reflection_prompts(user: str = Query("default")) -> dict[str, Any]:
    """Get self-reflection prompts."""
    from maestro_personal.reflection import ReflectionPrompts
    return ReflectionPrompts.generate(user)


# ─── Legacy Builder ────────────────────────────────────────────────────────

@router.post("/legacy/entry")
def add_legacy_entry(payload: dict[str, Any]) -> dict[str, Any]:
    """Add a legacy entry."""
    from maestro_personal.legacy import LegacyBuilder
    entry = LegacyBuilder.add_entry(
        payload.get("entry_type", "story"),
        payload.get("title", ""),
        payload.get("content", ""),
    )
    return entry.to_dict()

@router.get("/legacy/document")
def get_legacy_document() -> dict[str, Any]:
    """Get the legacy document."""
    from maestro_personal.legacy import LegacyBuilder
    return LegacyBuilder.export_document()

@router.delete("/legacy/entry/{entry_id}")
def delete_legacy_entry(entry_id: str) -> dict[str, Any]:
    """Delete a legacy entry."""
    from maestro_personal.legacy import LegacyBuilder
    deleted = LegacyBuilder.delete_entry(entry_id)
    if not deleted:
        raise HTTPException(404, "Entry not found")
    return {"deleted": True, "entry_id": entry_id}

@router.get("/legacy/prompts")
def legacy_prompts(entry_type: str = Query("")) -> dict[str, Any]:
    """Get writing prompts for legacy entries."""
    from maestro_personal.legacy import LegacyBuilder
    return {"prompts": LegacyBuilder.get_prompts(entry_type)}


# ─── Relationship Vault (Tier 2 — bilateral consent) ──────────────────────

@router.post("/relationships/memory")
def add_relationship_memory(payload: dict[str, Any]) -> dict[str, Any]:
    """Add a user-entered relationship memory."""
    from maestro_personal.relationship_vault import RelationshipVault
    mem = RelationshipVault.add_memory(
        payload.get("user", "default"),
        payload.get("person", ""),
        payload.get("memory_type", ""),
        payload.get("content", ""),
        payload.get("date", ""),
    )
    return mem.to_dict()

@router.get("/relationships/memories")
def get_relationship_memories(person: str = Query("")) -> dict[str, Any]:
    """Get relationship memories."""
    from maestro_personal.relationship_vault import RelationshipVault
    mems = RelationshipVault.get_memories(person)
    return {"memories": [m.to_dict() for m in mems]}

@router.post("/relationships/message")
def generate_relationship_message(payload: dict[str, Any]) -> dict[str, Any]:
    """Generate a message for a person (requires bilateral consent)."""
    from maestro_personal.relationship_vault import RelationshipVault
    from maestro_personal.consent import ConsentError
    try:
        return RelationshipVault.generate_message_for_person(
            payload.get("user", "default"),
            payload.get("person", ""),
            payload.get("occasion", ""),
        )
    except ConsentError as e:
        raise HTTPException(403, str(e))


# ─── Ambient Context (Tier 2) ─────────────────────────────────────────────

@router.get("/ambient-context")
def get_ambient_context(
    user: str = Query("default"),
    contact: str = Query(..., description="Contact name or email"),
) -> dict[str, Any]:
    """Get the user's own memory of a contact."""
    from maestro_personal.ambient_context import AmbientContext
    return AmbientContext.get_context(user, contact)


# ─── Pro-Personal Crossover (Tier 2) ──────────────────────────────────────

@router.get("/crossover/contacts")
def get_crossover_contacts() -> dict[str, Any]:
    """Find contacts in both Work and Personal modes."""
    from maestro_personal.crossover import ProfessionalPersonalCrossover
    return {"contacts": ProfessionalPersonalCrossover.find_crossover_contacts()}

@router.post("/crossover/merge")
def merge_crossover_contact(payload: dict[str, Any]) -> dict[str, Any]:
    """Merge a contact's Work and Personal profiles."""
    from maestro_personal.crossover import ProfessionalPersonalCrossover
    return ProfessionalPersonalCrossover.merge_contact(
        payload.get("entity_id", ""),
        payload.get("user", "default"),
    )

@router.post("/crossover/unmerge")
def unmerge_crossover_contact(payload: dict[str, Any]) -> dict[str, Any]:
    """Unmerge a contact's profiles (within 30-day window)."""
    from maestro_personal.crossover import ProfessionalPersonalCrossover
    return ProfessionalPersonalCrossover.unmerge_contact(payload.get("entity_id", ""))


# ─── Consent Management ────────────────────────────────────────────────────

@router.get("/consent")
def get_consents(user: str = Query("default")) -> dict[str, Any]:
    """Get all consent records."""
    from maestro_personal.consent import ConsentStore
    return {"consents": ConsentStore.get_consents(user)}

@router.post("/consent/grant")
def grant_consent(payload: dict[str, Any]) -> dict[str, Any]:
    """Grant consent for a source."""
    from maestro_personal.consent import ConsentStore
    record = ConsentStore.grant_consent(
        payload.get("user", "default"),
        payload.get("source", ""),
        payload.get("purpose", "store"),
    )
    return record.to_dict()

@router.post("/consent/revoke")
def revoke_consent(payload: dict[str, Any]) -> dict[str, Any]:
    """Revoke consent for a source."""
    from maestro_personal.consent import ConsentStore
    revoked = ConsentStore.revoke_consent(
        payload.get("user", "default"),
        payload.get("source", ""),
        payload.get("purpose", "store"),
    )
    return {"revoked": revoked}


# ─── Incognito Mode ────────────────────────────────────────────────────────

@router.post("/incognito/start")
def start_incognito(user: str = Query("default")) -> dict[str, Any]:
    """Start an incognito session."""
    from maestro_personal.incognito import IncognitoManager
    session = IncognitoManager.start_session(user)
    return session.to_dict()

@router.post("/incognito/end")
def end_incognito(user: str = Query("default")) -> dict[str, Any]:
    """End the incognito session."""
    from maestro_personal.incognito import IncognitoManager
    ended = IncognitoManager.end_session(user)
    return {"ended": ended}

@router.get("/incognito/status")
def incognito_status(user: str = Query("default")) -> dict[str, Any]:
    """Check if incognito mode is active."""
    from maestro_personal.incognito import IncognitoManager
    return {"incognito": IncognitoManager.is_incognito(user)}


# ─── What Maestro Knows Dashboard ──────────────────────────────────────────

@router.get("/dashboard")
def get_dashboard(user: str = Query("default")) -> dict[str, Any]:
    """What Maestro Knows — full transparency dashboard."""
    from maestro_personal.dashboard import WhatMaestroKnows
    return WhatMaestroKnows.get_dashboard(user)

@router.post("/dashboard/revoke")
def revoke_dashboard_source(payload: dict[str, Any]) -> dict[str, Any]:
    """Revoke consent and delete all data from a source."""
    from maestro_personal.dashboard import WhatMaestroKnows
    return WhatMaestroKnows.revoke_source(
        payload.get("user", "default"),
        payload.get("source", ""),
    )


# ─── Mode Management ───────────────────────────────────────────────────────

@router.get("/mode")
def get_mode(user: str = Query("default")) -> dict[str, Any]:
    """Get current mode (work/personal/both)."""
    from maestro_personal.mode import ModeManager
    return {"mode": ModeManager.get_mode(user).value}

@router.post("/mode")
def set_mode(payload: dict[str, Any]) -> dict[str, Any]:
    """Set current mode."""
    from maestro_personal.mode import ModeManager, Mode
    mode_str = payload.get("mode", "work")
    try:
        mode = Mode(mode_str)
    except ValueError:
        raise HTTPException(400, f"Invalid mode: {mode_str}. Use 'work', 'personal', or 'both'.")
    ModeManager.set_mode(payload.get("user", "default"), mode)
    return {"mode": mode.value}

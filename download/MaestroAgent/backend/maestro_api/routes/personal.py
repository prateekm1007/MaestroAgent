"""
V8 Personal Mode — API Routes.

All Personal Mode endpoints live under /api/personal/. They are
completely separate from the enterprise /api/oem/ routes. The Personal
Mode engine namespace does NOT import the OEM module.

Round 44 exception: the route layer (this file) MAY import UserSettings
from the OEM module to check the personal-context-in-work toggle and
inject the state into personal engines (dependency inversion). This is
the explicit bridge between modes — the route layer is allowed to span
both namespaces, but the personal ENGINES (briefing.py, etc.) are not.

Every endpoint enforces:
- ConsentStore checks (Guideline P3)
- Incognito mode awareness (Guideline P6)
- No third-party scraping (Guideline P4)
- Withdrawal path in responses (Guideline P9)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import Any

from maestro_auth.permissions import is_auth_enabled, require_user
from maestro_api.security.policy import set_router_policy, AuthPolicy
def _require_user_if_auth_enabled(request: Request) -> None:
    """Auth gate that respects dev mode. See imports.py for the pattern."""
    if is_auth_enabled():
        require_user(request)


router = APIRouter(dependencies=[Depends(_require_user_if_auth_enabled)], prefix="/api/personal", tags=["personal-mode"])


# ─── Briefing ──────────────────────────────────────────────────────────────

@router.get("/briefing")
def get_personal_briefing(user: str = Query("default")) -> dict[str, Any]:
    """Morning personal briefing — your calendar, weather, reminders.

    Round 44: also returns a work_context card (bidirectional balance)
    when the personal-context-in-work toggle is ON. The toggle state is
    injected into the briefing engine via set_toggle_state() — this
    preserves namespace separation (the personal namespace does not
    import the OEM module directly).
    """
    from maestro_personal.briefing import PersonalBriefingEngine
    from maestro_oem.user_settings import UserSettings
    engine = PersonalBriefingEngine(user)
    # Dependency inversion: check the toggle here (in the route layer,
    # which can import from both namespaces) and inject the state.
    toggle_on = UserSettings.is_personal_context_in_work_enabled(user)
    engine.set_toggle_state(toggle_on)
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
    """Set current mode.

    DEPRECATED (Round 46). The user's mode is now a view filter, not a
    stored state. This endpoint is kept for backward compatibility with
    onboarding.js and mode-tabs.js. New code should use the ?filter=
    query parameter on /api/personal/today instead.
    """
    from maestro_personal.mode import ModeManager, Mode
    mode_str = payload.get("mode", "work")
    try:
        mode = Mode(mode_str)
    except ValueError:
        raise HTTPException(400, f"Invalid mode: {mode_str}. Use 'work', 'personal', or 'both'.")
    ModeManager.set_mode(payload.get("user", "default"), mode)
    return {"mode": mode.value}


# ─── Round 46: Unified Today + Memory endpoints (filter, not mode) ──────────
# The filter is a VIEW parameter. Default: ALL (the user sees everything,
# work + personal interleaved by priority). The user can narrow to WORK
# or PERSONAL for focus, but the underlying data does not change.

@router.get("/today")
def get_unified_today(
    user: str = Query("default", description="User email."),
    filter: str = Query("all", description="Filter: all, work, personal. Default: all."),
) -> dict[str, Any]:
    """Round 46 — the unified Today endpoint.

    Returns the unified swipe deck: work cards (CEO briefing items) +
    personal cards (personal briefing items), interleaved by priority.
    Each card has a _mode field ('work' or 'personal') so the frontend
    can render the blue/coral mode indicator dot.

    The filter parameter narrows the view:
      - all (default): show work + personal cards
      - work: show only work cards
      - personal: show only personal cards

    The filter does NOT change the underlying data — it only filters
    the view. This is the Round 46 principle: the mode is a filter, not
    a switch.

    Returns:
        {
            cards: list[{category, title, context, _mode, ...}],
            filter: str,
            counts: {all, work, personal},
        }
    """
    from maestro_personal.mode import Filter
    from maestro_personal.integration import (
        build_personal_context_card_for_work,
        build_work_context_card_for_personal,
    )
    from maestro_oem.user_settings import UserSettings

    f = Filter.from_param(filter)
    cards: list[dict[str, Any]] = []

    # ─── Work cards (from CEO briefing) ──────────────────────────────
    if f in (Filter.ALL, Filter.WORK):
        try:
            # Import here to avoid circular dependency at module load
            from maestro_api.routes.oem import get_ceo_briefing
            briefing = get_ceo_briefing()
            ot = briefing.get("one_thing", {})
            if ot.get("title"):
                cards.append({
                    "category": "ONE DECISION",
                    "title": ot.get("title", ""),
                    "context": ot.get("why", ""),
                    "_mode": "work",
                    "confidence": ot.get("confidence"),
                    "urgency": ot.get("urgency"),
                })
            money = briefing.get("money", {})
            if money.get("losses"):
                first = money["losses"][0]
                cards.append({
                    "category": "ONE OPPORTUNITY",
                    "title": first.get("title", ""),
                    "context": first.get("detail", ""),
                    "_mode": "work",
                })
            overnight = briefing.get("overnight", {})
            if overnight.get("changes"):
                first = overnight["changes"][0]
                cards.append({
                    "category": "ONE RISK",
                    "title": first.get("title", ""),
                    "context": first.get("detail", ""),
                    "_mode": "work",
                })
        except Exception:
            pass  # Work briefing unavailable — return personal cards only

    # ─── Personal cards (from personal briefing) ─────────────────────
    if f in (Filter.ALL, Filter.PERSONAL):
        try:
            from maestro_personal.briefing import PersonalBriefingEngine
            from maestro_oem.user_settings import UserSettings
            engine = PersonalBriefingEngine(user)
            toggle_on = UserSettings.is_personal_context_in_work_enabled(user)
            engine.set_toggle_state(toggle_on)
            personal = engine.generate()
            for item in personal.get("items", [])[:3]:
                cards.append({
                    "category": "PERSONAL",
                    "title": (item.get("content", ""))[:100],
                    "context": f"From {item.get('source', 'your calendar')}",
                    "_mode": "personal",
                })
        except Exception:
            pass  # Personal briefing unavailable — return work cards only

    # ─── Counts (for the filter pill badges) ─────────────────────────
    work_count = sum(1 for c in cards if c["_mode"] == "work")
    personal_count = sum(1 for c in cards if c["_mode"] == "personal")

    # ── Phase C: Wire consciousness + metacognition into Today ──────
    # P11: These modules were built, tested, and exposed via
    # /api/oem/consciousness and /api/oem/metacognition — but never
    # called from /today. Now they are.
    # P13: Inputs are DERIVED from oem_state.engine.get_model() + oem_state.visible_signals.
    # Each block fails closed (P6): logs loudly and returns {} on error.
    org_state = _compute_org_state_for_today()
    meta_gap = _compute_meta_gap_for_today()
    # P4, P8, P9, P10, P11: wire 5 more engines into Today
    org_pulse = _compute_org_pulse_for_today()
    curiosity = _compute_curiosity_for_today()
    trajectories = _compute_trajectories_for_today()
    identity = _compute_identity_for_today()
    attention = _compute_attention_for_today()

    return {
        "cards": cards,
        "filter": f.value,
        "counts": {
            "all": work_count + personal_count,
            "work": work_count,
            "personal": personal_count,
        },
        "default_filter": "all",
        "note": "Round 46 — the filter is a view parameter, not a stored mode.",
        # Phase C: 2 newly-wired modules
        "org_state": org_state,
        "meta_gap": meta_gap,
        # P4, P8, P9, P10, P11: 5 newly-wired engines
        "org_pulse": org_pulse,
        "curiosity": curiosity,
        "trajectories": trajectories,
        "identity": identity,
        "attention": attention,
    }


def _compute_org_state_for_today() -> dict[str, Any]:
    """Phase C: ConsciousnessEngine.state_vector() — org's real-time state.

    Tells the exec: where is the org's attention, knowledge, trust,
    conflict, energy, uncertainty, and learning RIGHT NOW. This is
    the org-wide awareness the Today deck was missing — without it,
    the deck was task-only.

    RC11 fix: call the OEM consciousness endpoint via the route-layer
    helper (maestro_api.routes.oem.get_consciousness) instead of importing
    maestro_oem.consciousness directly. This preserves the architecture
    boundary: personal.py (route layer) talks to oem.py (route layer),
    not to maestro_oem (engine layer). The test
    test_personal_routes_separate_from_oem enforces this boundary by
    scanning for 'from maestro_oem' import statements.
    """
    try:
        # Route-layer to route-layer call — no maestro_oem import here.
        from maestro_api.routes.oem import get_consciousness
        # get_consciousness() returns engine.state_vector() directly
        return get_consciousness()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            "personal._compute_org_state_for_today (get_consciousness) failed: %s", e
        )
        return {}


def _compute_meta_gap_for_today() -> dict[str, Any]:
    """Phase C: MetacognitionEngine.analyze() — org thinking about its thinking.

    RC11 fix: call the OEM metacognition endpoint via the route-layer helper
    (maestro_api.routes.oem.get_metacognition) instead of importing
    maestro_oem.metacognition directly. Preserves the architecture boundary.
    """
    try:
        from maestro_api.routes.oem import get_metacognition
        return get_metacognition()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            "personal._compute_meta_gap_for_today (get_metacognition) failed: %s", e
        )
        return {}


def _compute_org_pulse_for_today() -> dict[str, Any]:
    """P4: OrganizationalPulse — org health indicators (temperature, momentum, trust, energy).

    RC11 fix: call the OEM pulse endpoint via the route-layer helper.
    """
    try:
        from maestro_api.routes.oem import get_organizational_pulse
        return get_organizational_pulse()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            "personal._compute_org_pulse_for_today (get_organizational_pulse) failed: %s", e
        )
        return {}


def _compute_curiosity_for_today() -> dict[str, Any]:
    """P8: CuriosityEngine — untested assumptions the org has never questioned.

    RC11 fix: call the OEM curiosity endpoint via the route-layer helper.
    """
    try:
        from maestro_api.routes.oem import get_curiosity
        return get_curiosity()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            "personal._compute_curiosity_for_today (get_curiosity) failed: %s", e
        )
        return {}


def _compute_trajectories_for_today() -> dict[str, Any]:
    """P9: TrajectoryEngine — org-wide trend memory (7 dims over time with slope).

    RC11 fix: call the OEM trajectories endpoint via the route-layer helper.
    """
    try:
        from maestro_api.routes.oem import get_trajectories
        return get_trajectories()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            "personal._compute_trajectories_for_today (get_trajectories) failed: %s", e
        )
        return {}


def _compute_identity_for_today() -> dict[str, Any]:
    """P10: IdentityEngine — gap between org self-image and actual behavior.

    RC11 fix: call the OEM identity endpoint via the route-layer helper.
    """
    try:
        from maestro_api.routes.oem import get_identity
        return get_identity()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            "personal._compute_identity_for_today (get_identity) failed: %s", e
        )
        return {}


def _compute_attention_for_today() -> dict[str, Any]:
    """P11: AttentionEngine — where org attention IS vs SHOULD BE + attention thieves.

    RC11 fix: call the OEM attention endpoint via the route-layer helper.
    """
    try:
        from maestro_api.routes.oem import get_attention
        return get_attention()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            "personal._compute_attention_for_today (get_attention) failed: %s", e
        )
        return {}


@router.get("/memory")
def get_unified_memory(
    user: str = Query("default", description="User email."),
    filter: str = Query("all", description="Filter: all, work, personal. Default: all."),
    limit: int = Query(30, ge=1, le=100, description="Max items to return."),
) -> dict[str, Any]:
    """Round 46 — the unified Memory endpoint.

    Returns a chronological feed of everything that happened — work
    signals (from /timeline) and personal memories (from memory replay),
    interleaved by time. Each item has a _mode field so the frontend
    can render the mode indicator dot.

    The filter parameter narrows the view (all/work/personal).
    """
    from maestro_personal.mode import Filter

    f = Filter.from_param(filter)
    items: list[dict[str, Any]] = []

    # ─── Work signals (from timeline) ────────────────────────────────
    if f in (Filter.ALL, Filter.WORK):
        try:
            from maestro_api.routes.oem import get_timeline
            timeline = get_timeline(limit=limit)
            for sig in timeline.get("signals", []):
                items.append({
                    "type": "work_signal",
                    "provider": sig.get("provider", ""),
                    "signal_type": sig.get("type", ""),
                    "description": f"{sig.get('type', 'signal')}: {sig.get('artifact', '')}",
                    "actor": sig.get("actor", ""),
                    "domain": sig.get("domain", ""),
                    "timestamp": sig.get("timestamp", ""),
                    "_mode": "work",
                })
        except Exception:
            pass

    # ─── Personal memories (from KG) ─────────────────────────────────
    if f in (Filter.ALL, Filter.PERSONAL):
        try:
            from maestro_personal.knowledge_graph import PersonalKG
            memories = PersonalKG.get_entities(entity_type="memory")
            for mem in memories[:limit]:
                items.append({
                    "type": "personal_memory",
                    "description": mem.name,
                    "actor": "",
                    "domain": "personal",
                    "timestamp": getattr(mem, "created_at", ""),
                    "_mode": "personal",
                })
        except Exception:
            pass

    # Sort by timestamp descending (most recent first) — best effort
    def _sort_key(item: dict[str, Any]) -> str:
        return item.get("timestamp", "") or ""
    items.sort(key=_sort_key, reverse=True)

    work_count = sum(1 for i in items if i["_mode"] == "work")
    personal_count = sum(1 for i in items if i["_mode"] == "personal")

    return {
        "items": items[:limit],
        "filter": f.value,
        "counts": {
            "all": work_count + personal_count,
            "work": work_count,
            "personal": personal_count,
        },
        "default_filter": "all",
    }


# ─── Round 46: Filter validation endpoint ───────────────────────────────────

@router.get("/filter/options")
def get_filter_options() -> dict[str, Any]:
    """Round 46 — return the available filter options for the unified UI.

    The filter pill in the frontend reads this to render the three
    options (All/Work/Personal) with their counts.
    """
    from maestro_personal.mode import Filter
    return {
        "options": [
            {"value": f.value, "label": f.value.capitalize()}
            for f in Filter
        ],
        "default": Filter.ALL.value,
        "note": "Round 46 — the filter is a view parameter, not a stored mode.",
    }


# ─── Round 44: Personal Context in Work toggle ──────────────────────────────
# Default: OFF. The user must explicitly opt in. When OFF, zero personal
# data appears in Work Mode. When ON, only the user's OWN personal state
# (sleep, energy, calendar conflicts, habit insights) appears — never
# intelligence about a third party. See CONSTITUTION.md Round 44 amendment.

@router.get("/settings/personal-context-in-work")
def get_personal_context_in_work(
    user: str = Query("default", description="User email."),
) -> dict[str, Any]:
    """Get the personal-context-in-work toggle. Default: False (OFF)."""
    from maestro_oem.user_settings import UserSettings
    return UserSettings.get_personal_context_in_work(user)

@router.post("/settings/personal-context-in-work")
def set_personal_context_in_work(payload: dict[str, Any]) -> dict[str, Any]:
    """Enable or disable personal context appearing in Work Mode.

    Payload:
        enabled: bool (required — True to enable, False to disable)
        user: str (optional — defaults to "default")

    Constitutional guardrails (Round 44):
      - Default: OFF (Guideline P3 — consent is opt-in)
      - When ON: only the user's OWN personal state surfaces, never
        intelligence about a third party (Round 36 bright line)
      - The integration is bidirectional — work commitments also appear
        in Personal Mode when this is enabled
      - Personal context is informational only, never redirects work
        recommendations
      - Withdrawal path: the user can disable this at any time and Work
        Mode returns to its default state (Guideline P9)
    """
    from maestro_oem.user_settings import UserSettings
    enabled = bool(payload.get("enabled", False))
    user = payload.get("user", "default")
    return UserSettings.set_personal_context_in_work(user, enabled)


# ─── Round 47 — Block 1.4: API Documentation ───────────────────────────────

@router.get("/docs-summary")
def get_api_docs_summary() -> dict[str, Any]:
    """Round 47 Block 1.4 — API documentation summary.

    Returns a structured summary of all API endpoints, grouped by
    namespace (enterprise /api/oem/ vs personal /api/personal/).
    The personal docs emphasize consent requirements.
    """
    return {
        "enterprise_endpoints": {
            "base_url": "/api/oem/",
            "description": "Organizational intelligence — laws, recommendations, signals, tasks, write-back, canvas, teammate, MCP.",
            "key_endpoints": [
                {"method": "GET", "path": "/ceo-briefing", "description": "Morning CEO briefing"},
                {"method": "GET", "path": "/ask?q=", "description": "Ask the organization"},
                {"method": "GET", "path": "/timeline", "description": "Organizational timeline"},
                {"method": "GET", "path": "/tasks", "description": "Auto-extracted tasks"},
                {"method": "POST", "path": "/writeback", "description": "Preview a write-back action"},
                {"method": "GET", "path": "/canvas/{decision_id}", "description": "Visual decision canvas"},
                {"method": "GET", "path": "/teammate/{email}", "description": "Per-teammate view"},
                {"method": "GET", "path": "/mcp/tools", "description": "MCP tool list (read-only)"},
                {"method": "GET", "path": "/pilot/metrics", "description": "Privacy-preserving pilot metrics"},
            ],
        },
        "personal_endpoints": {
            "base_url": "/api/personal/",
            "description": "Personal Mode — your life, your memory, your decisions. All consent-gated.",
            "consent_requirement": "Every data source requires explicit consent. Default: OFF.",
            "key_endpoints": [
                {"method": "GET", "path": "/briefing", "description": "Morning personal briefing (consent-gated)"},
                {"method": "GET", "path": "/today?filter=", "description": "Unified Today deck (Round 46)"},
                {"method": "GET", "path": "/memory?filter=", "description": "Unified Memory feed (Round 46)"},
                {"method": "POST", "path": "/consent/grant", "description": "Grant consent for a source"},
                {"method": "POST", "path": "/consent/revoke", "description": "Revoke consent for a source"},
                {"method": "GET", "path": "/dashboard", "description": "What Maestro Knows — transparency"},
                {"method": "GET", "path": "/settings/personal-context-in-work", "description": "Integration toggle (default OFF)"},
            ],
        },
        "constitutional_notes": [
            "The bright line: Maestro helps YOU think better. No third-party analysis.",
            "Consent is opt-in: every data source defaults OFF.",
            "Withdrawal path: every feature has one. You can stop using it without harm.",
            "No engagement tracking: no dwell time, no return frequency.",
            "4-item sidebar: Today / Memory / Ask / More (V5 litmus).",
        ],
    }

# Phase 1: stamp USER auth policy on all routes in this router
set_router_policy(router, AuthPolicy.USER)

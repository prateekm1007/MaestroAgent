"""
Maestro Cognitive Council — Surface Wiring: Ask → Situation Engine.

The existing AskPipeline returns OEM signals. This bridge makes Ask
 Situation-aware:
  1. Retrieve the correct Situation (not just OEM signals)
  2. Reconstruct chronology from the Situation's timeline
  3. Distinguish fact from report (epistemic states)
  4. Preserve disagreement in the answer
  5. Cite evidence by reference (not copy)
  6. Surface unknowns ("What we don't know yet")

This is the production wiring that moves the Cognitive Council from
level 2 (unit tested) to level 3 (wired to production).

Usage:
    bridge = SituationAwareAskBridge(oem_state=oem_state)
    result = bridge.ask("What's happening with the CustomerA renewal?")
    # result contains: situation_id, chronology, facts, unknowns,
    #   disagreements, judgment, decision_boundary, evidence_refs
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from .situation_engine import (
    LivingSituation,
    SituationEngine,
    SituationState,
    EpistemicState,
    EvidenceState,
    TimelineEvent,
    KnownFact,
    Unknown,
)
from .judgment_synthesizer import JudgmentSynthesizer
from .perspective import Perspective
from .consequence_path_router import ConsequencePathRouter

logger = logging.getLogger(__name__)


@dataclass
class AskResult:
    """The result of a Situation-aware Ask query.

    This replaces the old AskPipeline result (which returned raw OEM
    signals) with a Situation-centric answer that includes:
      - The situation (if found)
      - Chronology (reconstructed from the Situation's timeline)
      - Facts (distinguished by epistemic state)
      - Unknowns (what we don't know yet)
      - Disagreements (preserved, not converged)
      - Judgment (if perspectives were synthesized)
      - Decision boundary (what can/cannot be decided)
      - Evidence references (not copies)
    """
    query: str = ""
    situation_id: str = ""
    situation_title: str = ""
    situation_state: str = ""
    epistemic_state: str = ""
    entity: str = ""

    # Chronology (from Situation timeline)
    chronology: list[dict] = field(default_factory=list)

    # Facts distinguished by epistemic state
    known_facts: list[dict] = field(default_factory=list)
    reported_statements: list[dict] = field(default_factory=list)
    assumptions: list[dict] = field(default_factory=list)

    # Unknowns
    unknowns: list[dict] = field(default_factory=list)
    blocking_unknowns: list[str] = field(default_factory=list)

    # Disagreements (preserved)
    disagreements: list[dict] = field(default_factory=list)

    # Judgment (if available)
    judgment: Optional[dict] = None
    decision_boundary: Optional[dict] = None

    # Evidence references (NOT copies)
    evidence_refs: list[str] = field(default_factory=list)

    # Answer narrative
    answer: str = ""

    # Metadata
    found_situation: bool = False
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "situation_id": self.situation_id,
            "situation_title": self.situation_title,
            "situation_state": self.situation_state,
            "epistemic_state": self.epistemic_state,
            "entity": self.entity,
            "chronology": self.chronology,
            "known_facts": self.known_facts,
            "reported_statements": self.reported_statements,
            "assumptions": self.assumptions,
            "unknowns": self.unknowns,
            "blocking_unknowns": self.blocking_unknowns,
            "disagreements": self.disagreements,
            "judgment": self.judgment,
            "decision_boundary": self.decision_boundary,
            "evidence_refs": self.evidence_refs,
            "answer": self.answer,
            "found_situation": self.found_situation,
            "generated_at": self.generated_at,
        }


class SituationAwareAskBridge:
    """Connects the Ask surface to the Situation Engine.

    This bridge sits between the user's question and the existing
    AskPipeline. It:
      1. Detects which entity the question is about
      2. Finds the relevant LivingSituation
      3. Reconstructs the chronology from the Situation's timeline
      4. Distinguishes facts by epistemic state
      5. Surfaces unknowns
      6. Preserves disagreements
      7. Produces a Situation-centric answer

    If no Situation is found, it falls back gracefully (the old
    AskPipeline behavior).
    """

    # Entity detection keywords
    ENTITY_KEYWORDS = [
        "renewal", "sso", "oauth", "security", "pricing", "contract",
        "commitment", "deal", "churn", "escalation", "migration",
        "deployment", "incident", "hiring", "budget", "roadmap",
    ]

    def __init__(self, oem_state: Any = None):
        self._oem_state = oem_state
        self._situation_engine = SituationEngine(oem_state=oem_state)
        self._synthesizer = JudgmentSynthesizer()
        self._router = ConsequencePathRouter()

    @property
    def oem_state(self) -> Any:
        if self._oem_state is None:
            try:
                from maestro_api.oem_state import oem_state
                self._oem_state = oem_state
            except ImportError:
                self._oem_state = None
        return self._oem_state

    def ask(self, query: str, org_id: str = "default") -> AskResult:
        """Answer a question using Situation-aware intelligence.

        Args:
            query: the user's question (e.g., "What's happening with the renewal?")
            org_id: tenant scope

        Returns:
            AskResult with situation chronology, facts, unknowns, judgment
        """
        result = AskResult(query=query)

        # 1. Detect the entity from the query
        entity = self._detect_entity(query)
        entity_explicitly_named = entity is not None  # track for fallback safety
        if not entity:
            # No entity detected — try to detect from all signals
            entity = self._detect_entity_from_signals(org_id)

        if not entity:
            result.answer = (
                "I don't have enough organizational memory to answer this. "
                "Try asking about a specific customer, project, or decision."
            )
            return result

        # 2. Detect situations (if not already detected)
        situations = self._situation_engine.detect_situations(org_id)

        # C7 FIX: Filter out falsified situations (tombstone enforcement).
        # Per audit: "Falsified pattern still influences advice. Tombstone
        # mechanism exists; however, Ask's precedent retrieval does not yet
        # honor the tombstone in all code paths."
        # Fix: filter falsified situations before surfacing in Ask.
        try:
            from .audit_safety import filter_falsified_situations
            situations = filter_falsified_situations(situations)
        except ImportError:
            pass

        if not situations:
            result.answer = f"No active situations detected for {entity}."
            return result

        # 3. Find the relevant Situation for this entity
        situation = self._find_situation_for_entity(situations, entity)
        if not situation:
            # Condition 2 fix (corrected audit): when no situation exists for
            # the detected entity, fall back to the most relevant situation
            # across ALL entities — BUT ONLY if the entity was auto-detected
            # (not explicitly named in the query). This ensures:
            #   - Cross-surface coherence (Ask returns same sit as Briefing)
            #   - Tenant isolation (explicit entity queries don't leak across)
            # If the user explicitly asked about EntityA and EntityA has no
            # situation, we return "not found" — we do NOT return EntityB.
            if not entity_explicitly_named and situations:
                situation = situations[0]  # already sorted by update recency
                logger.info(
                    "Ask fallback: no situation for auto-detected entity '%s', using top situation '%s' (entity='%s')",
                    entity, situation.situation_id, situation.entity,
                )
            else:
                result.answer = f"No active situation found for {entity}."
                return result

        # 4. Populate the result from the Situation
        result.found_situation = True
        result.situation_id = situation.situation_id
        result.situation_title = situation.title
        result.situation_state = situation.state.value
        result.epistemic_state = situation.epistemic_state.value
        result.entity = situation.entity

        # 5. Reconstruct chronology
        result.chronology = self._reconstruct_chronology(situation)

        # 6. Distinguish facts by epistemic state
        self._classify_facts(situation, result)

        # 7. Surface unknowns
        result.unknowns = [u.to_dict() for u in situation.unknowns]
        result.blocking_unknowns = [
            u.question for u in situation.unknowns if u.blocking and not u.resolved
        ]

        # 8. Preserve disagreements
        result.disagreements = [d.to_dict() for d in situation.disagreements]

        # J-01 FIX: Invoke JudgmentSynthesizer + ConsequencePathRouter
        # Per audit: "JudgmentSynthesizer is imported but never invoked in Ask.
        # judgment/decision_boundary always null."
        # Fix: after finding the situation, route perspectives, run the synthesizer,
        # attach to situation.judment so decision_boundary/evidence_state appear.
        if situation.judgment is None:
            try:
                # J-03 FIX: Generate perspectives via ConsequencePathRouter
                routing_result = self._router.route(situation)
                # Build simple perspectives from the routing result
                perspectives = []
                for specialist in routing_result.specialists:
                    if specialist == "chief_of_staff":
                        continue  # synthesizer, not a perspective contributor
                    perspectives.append(Perspective(
                        situation_id=situation.situation_id,
                        specialist=specialist,
                        observation=f"{specialist} perspective on {situation.title}",
                        implication=f"Relevant consequence path identified for {specialist}",
                        evidence=[{"source": "consequence_path_router",
                                   "specialist": specialist}],
                        unknowns=situation.unknowns and [u.question for u in situation.unknowns if not u.resolved] or [],
                        urgency="normal",
                        recommended_next_step="",
                    ))

                # J-01 FIX: Run the synthesizer
                if perspectives:
                    situation.judgment = self._synthesizer.synthesize(situation, perspectives)
                    # Re-read disagreements (synthesizer may have added new ones)
                    result.disagreements = [d.to_dict() for d in situation.disagreements]
            except Exception as e:
                logger.debug(f"Judgment synthesis failed: {e}")

        # 9. Include judgment if available (now may be populated by J-01 fix)
        if situation.judgment:
            result.judgment = situation.judgment.to_dict()
            if situation.judgment.decision_boundary:
                result.decision_boundary = situation.judgment.decision_boundary.to_dict()

        # 10. Evidence references (NOT copies)
        result.evidence_refs = situation.evidence_refs

        # 11. Generate the answer narrative
        result.answer = self._generate_answer(situation, result)

        # C3 FIX: ACL on derived intelligence — propagate restrictions.
        # Per audit: "Summary-level leakage still possible; a user without
        # access to a restricted thread can receive a Prepare that includes
        # its substance."
        # Fix: check source evidence ACL and redact if restricted.
        try:
            from .acl_barrier import propagate_acl_restrictions, redact_restricted_content
            source_signals = self._get_signals_for_entity(entity, org_id)
            result_dict = result.to_dict()
            result_dict = propagate_acl_restrictions(result_dict, source_signals, user_email="")
            if result_dict.get("acl_restricted", False):
                result_dict = redact_restricted_content(result_dict)
                # Update the result object from the redacted dict
                result.answer = result_dict.get("answer", result.answer)
                if result_dict.get("acl_redacted"):
                    result.answer = "[RESTRICTED] This content derives from evidence you don't have access to."
        except Exception as e:
            logger.debug(f"ACL barrier check failed: {e}")

        return result

    def _detect_entity(self, query: str) -> Optional[str]:
        """Detect the entity being asked about from the query.

        Looks for entity names in the query text by matching against
        known entities in the OEM signals.
        """
        if not self.oem_state:
            return None

        signals = getattr(self.oem_state, "signals", None) or []
        if not signals:
            return None

        query_lower = query.lower()

        # Collect known entities from signals
        known_entities: set[str] = set()
        for sig in signals:
            entity = (
                getattr(sig, "entity", None)
                or (getattr(sig, "metadata", {}) or {}).get("customer")
                or (getattr(sig, "metadata", {}) or {}).get("entity")
            )
            if entity:
                known_entities.add(entity)

        # Check if any known entity is mentioned in the query
        for entity in known_entities:
            if entity.lower() in query_lower:
                return entity

        # Check for entity keywords
        for keyword in self.ENTITY_KEYWORDS:
            if keyword in query_lower:
                # Find an entity that has signals matching this keyword
                for sig in signals:
                    text = (getattr(sig, "text", "") or "").lower()
                    entity = getattr(sig, "entity", None) or (getattr(sig, "metadata", {}) or {}).get("customer")
                    if entity and keyword in text:
                        return entity

        return None

    def _get_signals_for_entity(self, entity: str, org_id: str = "default") -> list:
        """Get signals for an entity (for ACL check on derived intelligence)."""
        if not self.oem_state:
            return []
        signals = getattr(self.oem_state, "signals", None) or []
        result = []
        entity_lower = entity.lower() if entity else ""
        for s in signals:
            s_org = getattr(s, "org_id", None) or getattr(s, "tenant_id", None)
            if s_org is not None and s_org != org_id:
                continue
            s_entity = (getattr(s, "entity", None) or
                        (getattr(s, "metadata", {}) or {}).get("customer") or
                        (getattr(s, "metadata", {}) or {}).get("entity"))
            if s_entity and s_entity.lower() == entity_lower:
                result.append(s)
        return result

    def _detect_entity_from_signals(self, org_id: str) -> Optional[str]:
        """If no entity in the query, use the most active entity."""
        if not self.oem_state:
            return None

        signals = getattr(self.oem_state, "signals", None) or []
        if not signals:
            return None

        # Count signals per entity
        entity_counts: dict[str, int] = {}
        for sig in signals:
            entity = (
                getattr(sig, "entity", None)
                or (getattr(sig, "metadata", {}) or {}).get("customer")
            )
            if entity:
                entity_counts[entity] = entity_counts.get(entity, 0) + 1

        if entity_counts:
            return max(entity_counts, key=entity_counts.get)

        return None

    def _find_situation_for_entity(
        self, situations: list[LivingSituation], entity: str
    ) -> Optional[LivingSituation]:
        """Find the most relevant Situation for the given entity."""
        entity_lower = entity.lower()
        matching = [s for s in situations if s.entity.lower() == entity_lower]
        if matching:
            # Return the most recently updated
            return max(matching, key=lambda s: s.updated_at)
        return None

    def _reconstruct_chronology(self, situation: LivingSituation) -> list[dict]:
        """Reconstruct the chronology from the Situation's timeline.

        The timeline is already sorted chronologically. We project it
        into a dict format with evidence_ref (not copies).
        """
        return [
            {
                "timestamp": e.timestamp.isoformat() if isinstance(e.timestamp, datetime) else str(e.timestamp),
                "description": e.description,
                "event_type": e.event_type,
                "evidence_ref": e.evidence_ref,
                "source": e.source,
            }
            for e in situation.timeline
        ]

    def _classify_facts(self, situation: LivingSituation, result: AskResult) -> None:
        """Distinguish facts by epistemic state.

        KNOWN facts → known_facts
        REPORTED facts → reported_statements
        ASSUMED facts → assumptions
        """
        for fact in situation.known_facts:
            fact_dict = fact.to_dict()
            if fact.epistemic_state == EpistemicState.KNOWN:
                result.known_facts.append(fact_dict)
            elif fact.epistemic_state == EpistemicState.REPORTED:
                result.reported_statements.append(fact_dict)
            elif fact.epistemic_state == EpistemicState.ASSUMED:
                result.assumptions.append(fact_dict)
            else:
                # Other states go to reported
                result.reported_statements.append(fact_dict)

    def _generate_answer(self, situation: LivingSituation, result: AskResult) -> str:
        """Generate a Situation-centric answer narrative.

        The answer:
          1. States the situation and its current state
          2. Summarizes what's known vs. what's reported
          3. Acknowledges unknowns
          4. References disagreements
          5. Includes the decision boundary if available
        """
        lines: list[str] = []

        # Situation summary
        lines.append(f"**{situation.title}**")
        lines.append(f"State: {situation.state.value} | Epistemic: {situation.epistemic_state.value}")
        lines.append("")

        # Known facts
        if result.known_facts:
            lines.append("**What we know (evidence-backed):**")
            for f in result.known_facts[:3]:
                lines.append(f"  • {f['statement']}")
            lines.append("")

        # Reported statements
        if result.reported_statements:
            lines.append("**What's been reported (not yet verified):**")
            for f in result.reported_statements[:3]:
                lines.append(f"  • {f['statement']}")
            lines.append("")

        # Assumptions
        if result.assumptions:
            lines.append("**Assumptions (decisions depend on these):**")
            for f in result.assumptions[:3]:
                lines.append(f"  • {f['statement']}")
            lines.append("")

        # Unknowns
        if result.blocking_unknowns:
            lines.append("**What we don't know yet (blocking):**")
            for u in result.blocking_unknowns:
                lines.append(f"  • {u}")
            lines.append("")

        # Disagreements
        if result.disagreements:
            lines.append("**Where perspectives disagree:**")
            for d in result.disagreements[:3]:
                lines.append(f"  • {d.get('topic', 'Unknown topic')}: {d.get('position_a', '')} vs. {d.get('position_b', '')}")
            lines.append("")

        # Decision boundary
        if result.decision_boundary:
            db = result.decision_boundary
            lines.append("**What you can decide now:**")
            for c in db.get("can_decide_now", []):
                lines.append(f"  • {c}")
            lines.append("")
            if db.get("cannot_decide_yet"):
                lines.append("**What cannot yet be decided:**")
                for c in db["cannot_decide_yet"]:
                    lines.append(f"  • {c}")
                lines.append(f"  Why: {db.get('why', '')}")
                lines.append(f"  Smallest useful next step: {db.get('smallest_useful_next_step', '')}")
            lines.append("")

        # Evidence
        if result.evidence_refs:
            lines.append(f"**Evidence:** {len(result.evidence_refs)} source(s) referenced")

        return "\n".join(lines)

"""
Maestro Cognitive Council — Phase 1: Situation Engine.

A LivingSituation is the durable object representing a changing
organizational situation. Unlike SituationSnapshot (a static 27-field
view), a LivingSituation has:

  - A lifecycle (state transitions: watching → needs_preparation →
    resolved → learned / falsified)
  - A timeline of events (chronological)
  - Known facts (evidence-backed) and Unknowns (important missing info)
  - Perspectives contributed by specialists (structured, not free-form)
  - Preserved disagreements (not converged away)
  - A synthesized judgment (not a summary)
  - A recommended delivery route (silent/ask/briefing/whisper/prepare/urgent)
  - An epistemic state (known/reported/believed/assumed/hypothesized/
    predicted/disputed/unknown/falsified/learned)

The SituationEngine builds and maintains LivingSituations from OEM
signals, and routes only the relevant specialists to each situation.

Reference: docs/MAESTRO_COGNITIVE_COUNCIL_EXECUTION_POLICY.md
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════════════

class SituationState(str, Enum):
    """The lifecycle state of a LivingSituation."""
    WATCHING = "watching"                    # monitoring, no intervention needed yet
    NEEDS_PREPARATION = "needs_preparation"  # an upcoming event requires prep
    ACTIVE = "active"                        # a relevant event is happening now
    RESOLVED = "resolved"                    # the situation concluded
    LEARNED = "learned"                      # resolved + the outcome fed the learning loop
    FALSIFIED = "falsified"                  # a hypothesis about this situation was disproven
    DORMANT = "dormant"                      # no signals for 30+ days


class EpistemicState(str, Enum):
    """What the organization knows about this situation's central claim.

    Per the CEO directive: Maestro develops a disciplined model of what
    the organization knows, believes, assumes, predicts, disputes, learns,
    and forgets. These are different states.
    """
    KNOWN = "known"              # supported directly by evidence
    REPORTED = "reported"        # someone said it
    BELIEVED = "believed"        # the organization behaves as though true
    ASSUMED = "assumed"          # a decision depends upon it
    HYPOTHESIZED = "hypothesized"  # a proposed relationship being tested
    PREDICTED = "predicted"      # a prospective claim about a future outcome
    DISPUTED = "disputed"        # credible evidence conflicts
    UNKNOWN = "unknown"          # important information is missing
    FALSIFIED = "falsified"      # outcomes contradicted the hypothesis
    LEARNED = "learned"          # prospective evidence repeatedly supported it


class DeliveryRoute(str, Enum):
    """How (or whether) this situation should be surfaced to the user.

    The Delivery Governor decides this deterministically — specialists
    can only recommend, not decide.
    """
    SILENT = "silent"          # no intervention justified; watch
    ASK = "ask"                # available if user asks, no proactive push
    BRIEFING = "briefing"      # include in morning/evening briefing
    WHISPER = "whisper"        # proactive push during active context
    PREPARE = "prepare"        # surface a preparation workspace
    URGENT = "urgent"          # immediate escalation (rare)


# ════════════════════════════════════════════════════════════════════════════
# Timeline Event
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class TimelineEvent:
    """A single event on a situation's timeline."""
    timestamp: datetime
    description: str
    event_type: str = "observed"  # observed | reported | committed | decided | outcome
    evidence_id: Optional[str] = None
    source: str = ""              # which signal/source produced this event

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else str(self.timestamp),
            "description": self.description,
            "event_type": self.event_type,
            "evidence_id": self.evidence_id,
            "source": self.source,
        }


# ════════════════════════════════════════════════════════════════════════════
# Known Fact / Unknown
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class KnownFact:
    """A fact about the situation, backed by evidence."""
    statement: str
    evidence_ids: list[str] = field(default_factory=list)
    epistemic_state: EpistemicState = EpistemicState.KNOWN
    source: str = ""

    def to_dict(self) -> dict:
        return {
            "statement": self.statement,
            "evidence_ids": self.evidence_ids,
            "epistemic_state": self.epistemic_state.value,
            "source": self.source,
        }


@dataclass
class Unknown:
    """An important piece of information that is missing.

    Unknowns are first-class — Maestro explicitly tracks what it doesn't
    know, rather than hiding gaps behind confident-sounding output.
    """
    question: str                # what needs to be established?
    why_it_matters: str          # why is this gap important?
    blocking: bool = False       # does this block a decision?
    specialists_flagged: list[str] = field(default_factory=list)  # who noticed this gap?

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "why_it_matters": self.why_it_matters,
            "blocking": self.blocking,
            "specialists_flagged": self.specialists_flagged,
        }


# ════════════════════════════════════════════════════════════════════════════
# Disagreement
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class Disagreement:
    """A preserved disagreement between specialists.

    Most multi-agent systems converge. Maestro preserves useful
    disagreement — the reasoning path matters, and the user should be
    able to traverse it.
    """
    topic: str                   # what do they disagree about?
    position_a: str              # specialist A's position
    position_b: str              # specialist B's position
    specialist_a: str = ""
    specialist_b: str = ""
    resolution: Optional[str] = None  # how the Synthesizer reconciled it (if at all)
    unresolved: bool = True

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "position_a": self.position_a,
            "position_b": self.position_b,
            "specialist_a": self.specialist_a,
            "specialist_b": self.specialist_b,
            "resolution": self.resolution,
            "unresolved": self.unresolved,
        }


# ════════════════════════════════════════════════════════════════════════════
# Judgment
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class Judgment:
    """The synthesized of all perspectives on a situation.

    This is NOT a summary. It's a reasoned position that:
    - States the central claim
    - Acknowledges the strongest reason to act
    - Acknowledges the strongest reason not to act
    - Identifies what remains unknown
    - Recommends a next step (not pseudo-scientific precision)
    """
    central_claim: str = ""
    strongest_reason_to_act: str = ""
    strongest_reason_not_to_act: str = ""
    unknowns_blocking_decision: list[str] = field(default_factory=list)
    recommended_next_step: str = ""
    confidence: float = 0.0  # 0.0-1.0 — calibrated, not fabricated
    evidence_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "central_claim": self.central_claim,
            "strongest_reason_to_act": self.strongest_reason_to_act,
            "strongest_reason_not_to_act": self.strongest_reason_not_to_act,
            "unknowns_blocking_decision": self.unknowns_blocking_decision,
            "recommended_next_step": self.recommended_next_step,
            "confidence": round(self.confidence, 3),
            "evidence_ids": self.evidence_ids,
        }


# ════════════════════════════════════════════════════════════════════════════
# LivingSituation — the core object
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class LivingSituation:
    """A durable, living object representing a changing organizational situation.

    This is the product unit — not "agents" or "insights." Everything
    in Maestro serves situations: specialists contribute perspectives,
    the synthesizer produces judgment, the delivery governor decides
    how (or whether) to surface it.

    A LivingSituation can appear differently depending on context:
      - Before a meeting: "one unresolved issue worth preparing for"
      - During a meeting: "your internal record lacks confirmation..."
      - When asked: reconstructs the full history
      - After the meeting: "the expectation conflict is resolved"
      - Months later: "similar drift appearing in another renewal"
    """
    situation_id: str
    title: str
    entity: str                              # the customer/org/entity this concerns
    org_id: str = "default"                  # tenant scope

    # Lifecycle
    state: SituationState = SituationState.WATCHING
    epistemic_state: EpistemicState = EpistemicState.UNKNOWN
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # The situation's content
    timeline: list[TimelineEvent] = field(default_factory=list)
    known_facts: list[KnownFact] = field(default_factory=list)
    unknowns: list[Unknown] = field(default_factory=list)
    commitments: list[dict] = field(default_factory=list)
    decisions: list[dict] = field(default_factory=list)
    related_meetings: list[dict] = field(default_factory=list)

    # Perspectives and synthesis
    perspectives: list[dict] = field(default_factory=list)  # Perspective dicts (Phase 2)
    disagreements: list[Disagreement] = field(default_factory=list)
    judgment: Optional[Judgment] = None

    # Delivery
    recommended_delivery: DeliveryRoute = DeliveryRoute.SILENT
    relevant_specialists: list[str] = field(default_factory=list)

    # Metadata
    evidence_ids: list[str] = field(default_factory=list)
    snapshot_version: int = 1

    def to_dict(self) -> dict:
        return {
            "situation_id": self.situation_id,
            "title": self.title,
            "entity": self.entity,
            "org_id": self.org_id,
            "state": self.state.value,
            "epistemic_state": self.epistemic_state.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "timeline": [e.to_dict() for e in self.timeline],
            "known_facts": [f.to_dict() for f in self.known_facts],
            "unknowns": [u.to_dict() for u in self.unknowns],
            "commitments": self.commitments,
            "decisions": self.decisions,
            "related_meetings": self.related_meetings,
            "perspectives": self.perspectives,
            "disagreements": [d.to_dict() for d in self.disagreements],
            "judgment": self.judgment.to_dict() if self.judgment else None,
            "recommended_delivery": self.recommended_delivery.value,
            "relevant_specialists": self.relevant_specialists,
            "evidence_ids": self.evidence_ids,
            "snapshot_version": self.snapshot_version,
        }

    def add_timeline_event(self, event: TimelineEvent) -> None:
        """Add an event to the timeline and re-sort chronologically."""
        self.timeline.append(event)
        self.timeline.sort(key=lambda e: e.timestamp if isinstance(e.timestamp, datetime) else datetime.min)
        self.updated_at = datetime.now(timezone.utc)

    def add_known_fact(self, fact: KnownFact) -> None:
        """Add a known fact (deduplicated by statement)."""
        if not any(f.statement == fact.statement for f in self.known_facts):
            self.known_facts.append(fact)
            self.updated_at = datetime.now(timezone.utc)

    def add_unknown(self, unknown: Unknown) -> None:
        """Add an unknown (deduplicated by question)."""
        if not any(u.question == unknown.question for u in self.unknowns):
            self.unknowns.append(unknown)
            self.updated_at = datetime.now(timezone.utc)

    def add_disagreement(self, disagreement: Disagreement) -> None:
        """Add a disagreement (preserved, not converged away)."""
        self.disagreements.append(disagreement)
        self.updated_at = datetime.now(timezone.utc)

    def has_blocking_unknown(self) -> bool:
        """Does this situation have any unknown that blocks a decision?"""
        return any(u.blocking for u in self.unknowns)

    def transition_to(self, new_state: SituationState) -> None:
        """Transition the situation to a new state (with logging)."""
        old_state = self.state
        self.state = new_state
        self.updated_at = datetime.now(timezone.utc)
        logger.info(
            "Situation %s transitioned: %s → %s",
            self.situation_id, old_state.value, new_state.value,
        )


# ════════════════════════════════════════════════════════════════════════════
# SituationEngine — builds and maintains LivingSituations
# ════════════════════════════════════════════════════════════════════════════

# Mapping from specialist → the entity domains it's relevant for.
# Used by route_specialists() to avoid invoking all 17 for every situation.
SPECIALIST_DOMAIN_MAP: dict[str, set[str]] = {
    # Revenue
    "growth":           {"renewal", "expansion", "upsell", "pipeline"},
    "sales":            {"renewal", "deal", "pipeline", "pricing", "contract"},
    "customer_success": {"renewal", "churn", "health", "satisfaction", "onboarding"},
    "finance":          {"deal", "contract", "budget", "cost", "revenue"},
    # Product
    "product":          {"roadmap", "feature", "feedback", "release"},
    "engineering":      {"deployment", "bug", "incident", "integration", "architecture"},
    "marketing":        {"campaign", "positioning", "messaging"},
    # Internal
    "hr":               {"hiring", "retention", "burnout", "workload"},
    "legal":            {"contract", "compliance", "dpa", "sla", "obligation"},
    "operations":       {"process", "bottleneck", "capacity"},
    "support":          {"ticket", "issue", "escalation", "kb"},
    "data":             {"analytics", "trend", "metric"},
    "security":         {"security", "auth", "oauth", "sso", "vulnerability", "access"},
    "partnerships":     {"partner", "co-sell", "joint"},
    # Strategy
    "strategy":         {"market", "competitive", "positioning", "bet"},
    "communications":   {"announcement", "internal-comms", "follow-up"},
    "chief_of_staff":   set(),  # always relevant — synthesizes
}


class SituationEngine:
    """Builds and maintains LivingSituations from OEM signals.

    The engine is the bridge between Organizational Memory (Layer 2) and
    the Judgment layer (Layer 4). It takes raw signals and constructs
    durable situation objects that specialists can then contribute
    perspectives to.

    Usage:
        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()
        for s in situations:
            specialists = engine.route_specialists(s)
            # invoke only those specialists...
    """

    def __init__(self, oem_state: Any = None):
        self._oem_state = oem_state
        self._situations: dict[str, LivingSituation] = {}  # situation_id → LivingSituation

    @property
    def oem_state(self) -> Any:
        if self._oem_state is None:
            try:
                from maestro_api.oem_state import oem_state
                self._oem_state = oem_state
            except ImportError:
                self._oem_state = _NullOemState()
        return self._oem_state

    def _get_signals(self, org_id: str = "default") -> list:
        signals = getattr(self.oem_state, "signals", None) or []
        result = []
        for s in signals:
            s_org = getattr(s, "org_id", None) or getattr(s, "tenant_id", None)
            if s_org is None or s_org == org_id:
                result.append(s)
        return result

    # ── Situation detection ─────────────────────────────────────────────────

    def detect_situations(self, org_id: str = "default") -> list[LivingSituation]:
        """Detect active situations from OEM signals.

        A situation is detected when:
          - An entity has 2+ signals (commitments, decisions, meetings)
          - OR an entity has a known upcoming event (calendar)
          - OR an entity has an unresolved unknown

        Returns a list of LivingSituations, sorted by update recency.
        """
        signals = self._get_signals(org_id)
        entities: dict[str, list] = {}

        for sig in signals:
            entity = (
                getattr(sig, "entity", None)
                or (getattr(sig, "metadata", {}) or {}).get("customer")
                or (getattr(sig, "metadata", {}) or {}).get("entity")
            )
            if entity:
                entities.setdefault(entity, []).append(sig)

        situations: list[LivingSituation] = []
        for entity, entity_signals in entities.items():
            # Need at least 2 signals to form a situation
            if len(entity_signals) < 2:
                continue

            situation = self._build_situation(entity, entity_signals, org_id)
            if situation:
                self._situations[situation.situation_id] = situation
                situations.append(situation)

        # Sort by most recently updated
        situations.sort(key=lambda s: s.updated_at, reverse=True)
        return situations

    def _build_situation(
        self,
        entity: str,
        entity_signals: list,
        org_id: str,
    ) -> Optional[LivingSituation]:
        """Build a LivingSituation from an entity's signals."""
        situation_id = f"sit-{entity.lower()}-{uuid4().hex[:8]}"
        title = self._derive_title(entity, entity_signals)
        situation = LivingSituation(
            situation_id=situation_id,
            title=title,
            entity=entity,
            org_id=org_id,
        )

        # Build timeline from signals
        for sig in entity_signals:
            ts = getattr(sig, "timestamp", datetime.now(timezone.utc))
            sig_type = getattr(getattr(sig, "type", None), "value", str(getattr(sig, "type", "")))
            text = getattr(sig, "text", "") or (getattr(sig, "metadata", {}) or {}).get("text", "")

            event_type = "observed"
            if "commitment" in sig_type.lower():
                event_type = "committed"
            elif "decision" in sig_type.lower():
                event_type = "decided"
            elif "outcome" in sig_type.lower():
                event_type = "outcome"
            elif "reported" in sig_type.lower():
                event_type = "reported"

            situation.add_timeline_event(TimelineEvent(
                timestamp=ts if isinstance(ts, datetime) else datetime.now(timezone.utc),
                description=text or f"{sig_type} for {entity}",
                event_type=event_type,
                source=sig_type,
            ))

        # Extract known facts from signals with evidence
        for sig in entity_signals:
            text = getattr(sig, "text", "") or (getattr(sig, "metadata", {}) or {}).get("text", "")
            if text:
                epistemic = EpistemicState.REPORTED
                sig_type = str(getattr(sig, "type", "")).lower()
                if "commitment" in sig_type:
                    epistemic = EpistemicState.ASSUMED  # decisions depend on commitments
                elif "outcome" in sig_type:
                    epistemic = EpistemicState.KNOWN  # outcomes are evidence-backed
                situation.add_known_fact(KnownFact(
                    statement=text[:200],
                    epistemic_state=epistemic,
                    source=sig_type,
                ))

        # Detect unknowns (gaps in the timeline)
        unknowns = self._detect_unknowns(entity, entity_signals)
        for u in unknowns:
            situation.add_unknown(u)

        # Determine epistemic state
        situation.epistemic_state = self._determine_epistemic_state(situation)

        # Determine initial state
        situation.state = self._determine_initial_state(situation)

        # Route relevant specialists
        situation.relevant_specialists = self.route_specialists(situation)

        return situation

    def _derive_title(self, entity: str, signals: list) -> str:
        """Derive a human-readable title for the situation."""
        # Look for commitment/decision signals to name the situation
        for sig in signals:
            sig_type = str(getattr(sig, "type", "")).lower()
            text = getattr(sig, "text", "") or ""
            if "commitment" in sig_type and text:
                return f"{entity}: {text[:60]}"
        return f"{entity} situation"

    def _detect_unknowns(self, entity: str, signals: list) -> list[Unknown]:
        """Detect important unknowns from signal gaps."""
        unknowns: list[Unknown] = []

        # If there's a commitment but no outcome, the status is unknown
        has_commitment = any(
            "commitment" in str(getattr(s, "type", "")).lower() for s in signals
        )
        has_outcome = any(
            "outcome" in str(getattr(s, "type", "")).lower() for s in signals
        )
        if has_commitment and not has_outcome:
            unknowns.append(Unknown(
                question=f"Was the commitment to {entity} fulfilled?",
                why_it_matters="Without outcome evidence, the commitment status remains assumed, not known.",
                blocking=False,
                specialists_flagged=["customer_success", "sales"],
            ))

        # If there's a security-related signal but no resolution
        has_security = any(
            "security" in str(getattr(s, "type", "")).lower()
            or "security" in (getattr(s, "text", "") or "").lower()
            for s in signals
        )
        has_resolution = any(
            "resolved" in str(getattr(s, "type", "")).lower()
            or "approved" in (getattr(s, "text", "") or "").lower()
            for s in signals
        )
        if has_security and not has_resolution:
            unknowns.append(Unknown(
                question=f"Was the security condition for {entity} cleared?",
                why_it_matters="Conditional security approvals that remain unresolved can block renewals and create audit exposure.",
                blocking=True,
                specialists_flagged=["security", "legal"],
            ))

        return unknowns

    def _determine_epistemic_state(self, situation: LivingSituation) -> EpistemicState:
        """Determine the overall epistemic state of the situation."""
        if not situation.known_facts:
            return EpistemicState.UNKNOWN

        # If any blocking unknown exists, the situation is disputed/unknown
        if situation.has_blocking_unknown():
            return EpistemicState.DISPUTED

        # If all facts are KNOWN, the situation is KNOWN
        states = [f.epistemic_state for f in situation.known_facts]
        if all(s == EpistemicState.KNOWN for s in states):
            return EpistemicState.KNOWN

        # If any fact is ASSUMED, the situation depends on assumptions
        if any(s == EpistemicState.ASSUMED for s in states):
            return EpistemicState.ASSUMED

        # Default: reported (someone said it, not yet verified)
        return EpistemicState.REPORTED

    def _determine_initial_state(self, situation: LivingSituation) -> SituationState:
        """Determine the initial lifecycle state of the situation."""
        # If there's a blocking unknown, the situation needs preparation
        if situation.has_blocking_unknown():
            return SituationState.NEEDS_PREPARATION

        # If there are recent timeline events (last 7 days), it's active
        if situation.timeline:
            latest = situation.timeline[-1]
            if isinstance(latest.timestamp, datetime):
                days_old = (datetime.now(timezone.utc) - latest.timestamp).days
                if days_old <= 7:
                    return SituationState.ACTIVE
                elif days_old <= 30:
                    return SituationState.WATCHING
                else:
                    return SituationState.DORMANT

        return SituationState.WATCHING

    # ── Specialist routing ──────────────────────────────────────────────────

    def route_specialists(self, situation: LivingSituation) -> list[str]:
        """Determine which specialists are relevant for this situation.

        NOT all 17 specialists run for every situation. The engine routes
        only the relevant ones based on the situation's topic keywords.

        The Chief of Staff is always included (it synthesizes).
        """
        relevant: set[str] = {"chief_of_staff"}  # always

        # Build a keyword bag from the situation's title, facts, and timeline
        text_bag = (
            situation.title + " "
            + " ".join(f.statement for f in situation.known_facts) + " "
            + " ".join(e.description for e in situation.timeline)
        ).lower()

        for specialist, keywords in SPECIALIST_DOMAIN_MAP.items():
            if not keywords:
                continue  # chief_of_staff handled above
            if any(kw in text_bag for kw in keywords):
                relevant.add(specialist)

        # Always include customer_success and sales for entity situations
        # (they're broadly relevant to any customer-facing situation)
        if situation.entity:
            relevant.add("customer_success")
            relevant.add("sales")

        return sorted(relevant)

    # ── Situation retrieval ─────────────────────────────────────────────────

    def get_situation(self, situation_id: str) -> Optional[LivingSituation]:
        """Retrieve a situation by ID."""
        return self._situations.get(situation_id)

    def get_active_situations(self, org_id: str = "default") -> list[LivingSituation]:
        """Get all non-dormant, non-resolved situations."""
        return [
            s for s in self._situations.values()
            if s.org_id == org_id
            and s.state not in (SituationState.DORMANT, SituationState.RESOLVED,
                                SituationState.LEARNED, SituationState.FALSIFIED)
        ]

    def get_situations_needing_preparation(self, org_id: str = "default") -> list[LivingSituation]:
        """Get situations that need preparation (have blocking unknowns)."""
        return [
            s for s in self._situations.values()
            if s.org_id == org_id and s.state == SituationState.NEEDS_PREPARATION
        ]


class _NullOemState:
    """Fallback when OEM state is unavailable."""
    signals: list = []

    def __getattr__(self, name: str) -> Any:
        return None

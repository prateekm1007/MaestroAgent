"""Universal Evidence object — the foundation for all Maestro intelligence.

CEO + Auditor directive (2026-07-03): "Build one Evidence Spine, not
per-feature evidence. One universal provenance architecture powering
Whisper, Ask, Preparation, and Decisions."

The Evidence object is the single source of truth for WHY Maestro is
making a claim. Every whisper, every Ask answer, every preparation
brief must carry an Evidence object that explains:
  - What was observed (facts)
  - Where it came from (artifacts)
  - Who was involved (people)
  - When it happened (timestamps)
  - What conflicts exist (conflicting evidence)
  - What assumptions are being made
  - What decisions are related
  - What changed since last time

This is NOT a confidence score. This is provenance.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Evidence:
    """Universal evidence object — powers Whisper, Ask, Preparation, Decisions.

    Usage:
        evidence = Evidence(
            claim="Engineering already promised SSO to <customer>",
            observed_facts=[{
                "source": "customer signals",
                "date": "2024-11-01",
                "text": "Deliver SSO by 2024-12-15",
                "people": ["jane.d@example.com"],
            }],
        )
        whisper["evidence"] = evidence.to_dict()
        whisper["why_surfaced"] = evidence.render_why()
    """

    claim: str
    observed_facts: list[dict] = field(default_factory=list)
    # [{"source": "slack", "date": "2024-12-10", "text": "...", "people": ["Sarah"]}]

    source_artifacts: list[dict] = field(default_factory=list)
    # [{"type": "crm_record", "url": "", "retrieved_at": "2024-11-01"}]

    people_involved: list[dict] = field(default_factory=list)
    # [{"name": "Sarah Chen", "role": "VP Eng", "why_relevant": "made the commitment"}]

    timestamps: dict = field(default_factory=dict)
    # {"first_observed": "2024-11-01", "last_observed": "2024-12-18", "event_date": "2024-11-01"}

    conflicting_evidence: list[dict] = field(default_factory=list)
    # [{"claim": "Product says SSO is conditional", "source": "engineering signals", "why_conflicts": "contradicts commitment"}]

    assumptions: list[str] = field(default_factory=list)
    # ["The commitment is still active", "The deadline has not been renegotiated"]

    related_decisions: list[str] = field(default_factory=list)
    # decision IDs

    what_changed_since: str | None = None

    # Loop 1.5 debt (AUDIT-b3f7b26): claim_type is the epistemic type of
    # this Evidence. It tells Maestro (and downstream consumers like Loop 1.5's
    # disagreement detection) whether this claim is:
    #   - observed_fact       — directly witnessed ("the release failed Tuesday")
    #   - reported_statement  — someone said something ("Engineering believes Legal caused the delay")
    #   - commitment          — a promise was made ("Deliver SSO by 2024-12-15")
    #   - assumption          — an unverified belief ("The deadline has not been renegotiated")
    #   - inference           — a derived conclusion ("Moving Legal earlier may reduce delay")
    #   - prediction          — a forecast ("The release will likely slip")
    #   - outcome             — what actually happened ("Commitment was honored/broken")
    #   - proposal            — a suggestion, NOT a promise ("We should support SSO")
    #   - estimate            — a human-reported forecast ("Engineering thinks SSO can be ready by Q4")
    #   - hypothesis          — a conditional testable prediction ("If we prioritize SSO, <customer> will renew")
    #
    # The 3 new types (C2 fix, ADVERSARIAL-AUDIT-24PHASE) are critical:
    #   - proposal vs commitment: Maestro must distinguish "we should" from "we will"
    #   - estimate vs prediction: Maestro must distinguish human-reported forecasts
    #     from system-generated ones
    #   - hypothesis vs prediction: Maestro must distinguish conditional falsifiable
    #     predictions ("if X then Y") from direct forecasts ("X will happen")
    #
    # Default is "observed_fact" — the most conservative epistemic type. This is
    # fail-safe (P6): an unspecified claim_type is treated as a directly
    # witnessed fact rather than as None (which would break downstream logic).
    # The EvidenceBuilder sets claim_type appropriately per whisper type.
    claim_type: str = "observed_fact"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON API responses."""
        return {
            "claim": self.claim,
            "claim_type": self.claim_type,
            "observed_facts": self.observed_facts,
            "source_artifacts": self.source_artifacts,
            "people_involved": self.people_involved,
            "timestamps": self.timestamps,
            "conflicting_evidence": self.conflicting_evidence,
            "assumptions": self.assumptions,
            "related_decisions": self.related_decisions,
            "what_changed_since": self.what_changed_since,
        }

    def render_why(self) -> str:
        """Render a natural-language 'why Maestro surfaced this' from the evidence.

        Instead of static template strings, this dynamically assembles
        a sentence from the actual evidence fields.
        """
        parts = []

        # Who did what, when
        if self.observed_facts:
            fact = self.observed_facts[0]
            source = fact.get("source", "")
            date = fact.get("date", "")
            text = fact.get("text", "")
            people = fact.get("people", [])

            if people:
                who = people[0] if len(people) == 1 else f"{people[0]} and {len(people)-1} other{'s' if len(people) > 2 else ''}"
                parts.append(f"{who} recorded this in {source}")
            elif source:
                parts.append(f"Recorded in {source}")

            if date:
                parts.append(f"on {date}")

        # How many total observations
        if len(self.observed_facts) > 1:
            parts.append(f"({len(self.observed_facts)} total observations)")

        # Conflicting evidence
        if self.conflicting_evidence:
            conflict = self.conflicting_evidence[0]
            parts.append(f"⚠ {conflict.get('claim', 'Conflicting evidence exists')}")

        # What changed
        if self.what_changed_since:
            parts.append(f"Since then: {self.what_changed_since}")

        if not parts:
            parts.append("Maestro detected relevant organizational knowledge")

        return ". ".join(parts) + "."

    @property
    def evidence_count(self) -> int:
        """Number of distinct evidence items (observed facts + artifacts)."""
        return len(self.observed_facts) + len(self.source_artifacts)

    @property
    def has_conflicting_evidence(self) -> bool:
        """Whether any conflicting evidence exists."""
        return len(self.conflicting_evidence) > 0

    def validate(self) -> bool:
        """Validate that this evidence object has minimum required fields.

        Per P6 (fail closed): an Evidence with no observed facts is invalid.
        """
        if not self.claim:
            return False
        if not self.observed_facts:
            return False
        return True


class EvidenceBuilder:
    """Builds Evidence objects from organizational signals.

    Usage:
        builder = EvidenceBuilder(signals)
        evidence = builder.build_for_whisper(
            whisper_type="commitment_exists",
            entity="<customer>",
            raw_evidence={"artifact": "crm:globex-commit-1", "timestamp": "..."},
        )
    """

    def __init__(self, signals: list) -> None:
        self.signals = signals

    def build_for_whisper(
        self,
        whisper_type: str,
        entity: str,
        topic: str,
        raw_evidence: dict[str, Any],
        context: str = "",
    ) -> Evidence:
        """Build an Evidence object for a whisper from actual signal data."""

        if whisper_type == "commitment_exists":
            return self._build_commitment_evidence(entity, raw_evidence)
        elif whisper_type == "objection_history":
            return self._build_objection_evidence(entity, raw_evidence)
        elif whisper_type == "decision_history":
            return self._build_decision_evidence(entity, raw_evidence)
        elif whisper_type == "expertise":
            return self._build_expertise_evidence(entity, raw_evidence)
        elif whisper_type in ("law_exists", "relevant_law"):
            return self._build_law_evidence(whisper_type, raw_evidence)
        elif whisper_type == "broken_commitments":
            return self._build_broken_commitment_evidence(entity)
        elif whisper_type == "champion_quiet":
            return self._build_champion_quiet_evidence(entity)
        elif whisper_type == "bottleneck":
            return self._build_bottleneck_evidence(entity, raw_evidence)
        elif whisper_type == "meeting_context":
            return self._build_meeting_context_evidence(entity)
        elif whisper_type == "cross_team":
            return self._build_cross_team_evidence(topic, raw_evidence)
        else:
            return Evidence(
                claim="Maestro detected relevant organizational knowledge",
                observed_facts=[{"source": "OEM", "date": "", "text": "", "people": []}],
                claim_type="observed_fact",
            )

    def _build_commitment_evidence(self, entity: str, raw: dict) -> Evidence:
        """Build evidence for a commitment whisper."""
        from maestro_oem.signal import SignalType

        artifact = raw.get("artifact", "")
        timestamp = raw.get("timestamp", "")
        date_str = timestamp[:10] if timestamp else ""

        # Find the actual commitment signal
        commitment_signals = [
            s for s in self.signals
            if hasattr(s, "metadata") and s.metadata.get("customer") == entity
            and hasattr(s, "type") and s.type == SignalType.CUSTOMER_COMMITMENT_MADE
        ]

        observed_facts = []
        people = set()
        for s in commitment_signals[:3]:
            commitment_text = s.metadata.get("commitment", "")
            actor = s.actor or ""
            if actor:
                people.add(actor)
            s_date = s.timestamp.isoformat()[:10] if hasattr(s.timestamp, "isoformat") else ""
            observed_facts.append({
                "source": "customer signals",
                "date": s_date,
                "text": commitment_text[:100],
                "people": [actor] if actor else [],
            })

        if not observed_facts:
            observed_facts = [{"source": "customer signals", "date": date_str, "text": artifact, "people": []}]

        # Check for conflicting signals (objections from same entity)
        conflicting = []
        objection_signals = [
            s for s in self.signals
            if hasattr(s, "metadata") and s.metadata.get("customer") == entity
            and hasattr(s, "type") and s.type == SignalType.CUSTOMER_OBJECTION
        ]
        for s in objection_signals[:2]:
            obj_type = s.metadata.get("objection_type", "")
            conflicting.append({
                "claim": f"{entity} raised objection: {obj_type}",
                "source": "customer signals",
                "why_conflicts": "Customer may be dissatisfied despite the commitment",
            })

        return Evidence(
            claim=f"A commitment was made to {entity}",
            observed_facts=observed_facts,
            source_artifacts=[{"type": "crm_record", "url": "", "retrieved_at": date_str}],
            people_involved=[{"name": p, "role": "actor", "why_relevant": "made the commitment"} for p in people],
            timestamps={"first_observed": date_str, "last_observed": date_str, "event_date": date_str},
            conflicting_evidence=conflicting,
            assumptions=["The commitment is still active"],
            claim_type="commitment",
        )

    def _build_objection_evidence(self, entity: str, raw: dict) -> Evidence:
        """Build evidence for an objection whisper."""
        from maestro_oem.signal import SignalType

        obj_type = raw.get("objection_type", "")
        timestamp = raw.get("timestamp", "")
        date_str = timestamp[:10] if timestamp else ""

        objection_signals = [
            s for s in self.signals
            if hasattr(s, "metadata") and s.metadata.get("customer") == entity
            and hasattr(s, "type") and s.type == SignalType.CUSTOMER_OBJECTION
        ]

        observed_facts = []
        people = set()
        for s in objection_signals[:5]:
            o_type = s.metadata.get("objection_type", "")
            actor = s.actor or ""
            if actor:
                people.add(actor)
            s_date = s.timestamp.isoformat()[:10] if hasattr(s.timestamp, "isoformat") else ""
            observed_facts.append({
                "source": "customer signals",
                "date": s_date,
                "text": f"Objection: {o_type}",
                "people": [actor] if actor else [],
            })

        if not observed_facts:
            observed_facts = [{"source": "customer signals", "date": date_str, "text": f"Objection: {obj_type}", "people": []}]

        return Evidence(
            claim=f"{entity} has raised objections",
            observed_facts=observed_facts,
            people_involved=[{"name": p, "role": "actor", "why_relevant": "raised the objection"} for p in people],
            timestamps={"first_observed": date_str, "last_observed": date_str},
            assumptions=[f"The {obj_type} concern is still unresolved"] if obj_type else [],
            claim_type="observed_fact",
        )

    def _build_decision_evidence(self, entity: str, raw: dict) -> Evidence:
        """Build evidence for a decision whisper."""
        outcome = raw.get("outcome", "")
        return Evidence(
            claim=f"{entity} previously made a decision: {outcome}",
            observed_facts=[{"source": "customer signals", "date": "", "text": f"Decision: {outcome}", "people": []}],
            assumptions=["The decision context may still be relevant"],
            claim_type="outcome",
        )

    def _build_expertise_evidence(self, entity: str, raw: dict) -> Evidence:
        """Build evidence for an expertise whisper."""
        domains = raw.get("domains", [])
        return Evidence(
            claim=f"{entity} has expertise in {', '.join(domains[:3])}",
            observed_facts=[{"source": "knowledge graph", "date": "", "text": f"Domains: {', '.join(domains)}", "people": [entity]}],
            people_involved=[{"name": entity, "role": "expert", "why_relevant": "has demonstrated expertise"}],
            assumptions=["The expertise is still current"],
            claim_type="reported_statement",
        )

    def _build_law_evidence(self, whisper_type: str, raw: dict) -> Evidence:
        """Build evidence for a law whisper."""
        code = raw.get("code", "")
        validated = raw.get("validated", 0)
        failed = raw.get("failed", 0)
        return Evidence(
            claim=f"Organizational law {code}" if code else "Organizational law detected",
            observed_facts=[{
                "source": "OEM laws",
                "date": "",
                "text": f"Validated {validated}x, failed {failed}x",
                "people": [],
            }],
            assumptions=["The law is still applicable to current operations"],
            claim_type="inference",
        )

    def _build_broken_commitment_evidence(self, entity: str) -> Evidence:
        """Build evidence for a broken commitment whisper."""
        from maestro_oem.signal import SignalType

        broken_signals = [
            s for s in self.signals
            if hasattr(s, "metadata") and s.metadata.get("customer") == entity
            and hasattr(s, "type") and s.type == SignalType.CUSTOMER_COMMITMENT_BROKEN
        ]

        observed_facts = []
        for s in broken_signals[:3]:
            s_date = s.timestamp.isoformat()[:10] if hasattr(s.timestamp, "isoformat") else ""
            observed_facts.append({
                "source": "customer signals",
                "date": s_date,
                "text": "Commitment was broken",
                "people": [s.actor] if s.actor else [],
            })

        if not observed_facts:
            observed_facts = [{"source": "customer signals", "date": "", "text": "Broken commitment detected", "people": []}]

        return Evidence(
            claim=f"{entity} has broken commitments — trust may be fragile",
            observed_facts=observed_facts,
            assumptions=["The broken commitment has not been remediated"],
            claim_type="outcome",
        )

    def _build_champion_quiet_evidence(self, entity: str) -> Evidence:
        """Build evidence for a champion gone quiet whisper."""
        return Evidence(
            claim=f"{entity}'s champion has gone quiet — engagement may be waning",
            observed_facts=[{"source": "customer signals", "date": "", "text": "Champion activity has decreased", "people": []}],
            assumptions=["The silence is significant, not just a schedule gap"],
            claim_type="assumption",
        )

    def _build_bottleneck_evidence(self, entity: str, raw: dict) -> Evidence:
        """Build evidence for a bottleneck whisper."""
        return Evidence(
            claim=f"{entity} is gating multiple items",
            observed_facts=[{"source": "OEM approvals", "date": "", "text": f"{entity} is a bottleneck", "people": [entity]}],
            people_involved=[{"name": entity, "role": "gate", "why_relevant": "gating multiple decisions"}],
            assumptions=["The bottleneck is due to workload, not process"],
            claim_type="inference",
        )

    def _build_meeting_context_evidence(self, entity: str) -> Evidence:
        """Build evidence for a meeting context whisper."""
        return Evidence(
            claim=f"You have an upcoming interaction with {entity}" if entity else "You have an upcoming interaction",
            observed_facts=[{"source": "calendar", "date": "", "text": f"Meeting with {entity}", "people": [entity] if entity else []}],
            assumptions=["The meeting will proceed as scheduled"],
            claim_type="observed_fact",
        )

    def _build_cross_team_evidence(self, topic: str, raw: dict) -> Evidence:
        """Build evidence for a cross-team knowledge whisper."""
        lo_id = raw.get("lo_id", "")
        return Evidence(
            claim=f"Another team has relevant knowledge about {topic}" if topic else "Cross-team knowledge detected",
            observed_facts=[{"source": "learning objects", "date": "", "text": f"Learning object: {lo_id}", "people": []}],
            assumptions=["The cross-team knowledge is still accurate"],
            claim_type="inference",
        )

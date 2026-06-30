"""Organizational Whisper — surface what the organization knows but hasn't said.

Like Cluely, but instead of helping one person, it helps the organization.

When you're in a meeting, writing a proposal, or about to make a decision,
the Whisper surfaces things your organization already knows that are
relevant but that nobody has said yet:

  - "Engineering already promised this."
  - "Support solved this."
  - "Legal already approved this wording."
  - "Customer Success warned about this."
  - "Finance rejected this last quarter."
  - "Two similar customers accepted Option B."
  - "This contradicts Law L-0003."

The Whisper is NOT a chatbot. It's a contextual surfacing engine that
reads the OEM and produces only what's relevant to the current context.

Privacy by design:
  - No keystroke logging
  - No content inspection
  - Uses only the OEM's existing signal data
  - Surfaces only business-relationship knowledge
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


class OrganizationalWhisper:
    """Surfaces what the organization knows but hasn't said.

    Usage:
        whisper = OrganizationalWhisper(model, signals)
        insights = whisper.for_context(
            context="meeting",
            entity="Globex",
            topic="pricing",
        )
    """

    def __init__(self, model: Any, signals: list) -> None:
        self.model = model
        self.signals = signals

    def for_context(
        self,
        context: str = "",
        entity: str = "",
        topic: str = "",
        user: str = "",
    ) -> dict[str, Any]:
        """Surface organizational knowledge relevant to the current context.

        Args:
            context: "meeting" | "proposal" | "decision" | "email" | "review"
            entity: The entity being discussed (customer name, law code, person)
            topic: The topic (pricing, security, timeline, etc.)
            user: The current user's email

        Returns:
          - whispers: list of things the org knows
          - warnings: list of things to watch out for
          - precedents: list of similar past situations
          - confidence: overall confidence in the whispers
        """
        whispers: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        precedents: list[dict[str, Any]] = []

        # Entity-specific whispers
        if entity:
            whispers.extend(self._entity_whispers(entity))
            warnings.extend(self._entity_warnings(entity))
            precedents.extend(self._entity_precedents(entity))

        # Topic-specific whispers
        if topic:
            whispers.extend(self._topic_whispers(topic))
            warnings.extend(self._topic_warnings(topic))

        # Context-specific whispers
        if context:
            whispers.extend(self._context_whispers(context, entity))

        # Cross-team knowledge surfacing
        whispers.extend(self._cross_team_knowledge(entity, topic))

        # Deduplicate by text
        seen = set()
        unique_whispers = []
        for w in whispers:
            key = w.get("text", "")[:80].lower()
            if key not in seen:
                seen.add(key)
                unique_whispers.append(w)

        confidence = self._compute_confidence(unique_whispers)

        return {
            "context": context,
            "entity": entity,
            "topic": topic,
            "user": user,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "whispers": unique_whispers[:10],
            "warnings": warnings[:5],
            "precedents": precedents[:5],
            "confidence": confidence,
            "narrative": self._narrative(unique_whispers, warnings),
        }

    def _entity_whispers(self, entity: str) -> list[dict[str, Any]]:
        """What does the org know about this entity?"""
        whispers = []

        # Check if entity is a customer
        from maestro_oem.signal import SignalType
        customer_signals = [s for s in self.signals
                           if s.metadata.get("customer") == entity]

        if customer_signals:
            # What commitments have been made?
            commitments = [s for s in customer_signals
                          if s.type == SignalType.CUSTOMER_COMMITMENT_MADE]
            for c in commitments:
                whispers.append({
                    "type": "commitment_exists",
                    "text": f"Engineering already promised: {c.metadata.get('commitment', '')[:80]}",
                    "source": "customer signals",
                    "confidence": 1.0,
                    "evidence": {"artifact": c.artifact, "timestamp": c.timestamp.isoformat()},
                })

            # What objections have been raised?
            objections = [s for s in customer_signals
                         if s.type == SignalType.CUSTOMER_OBJECTION]
            for o in objections:
                whispers.append({
                    "type": "objection_history",
                    "text": f"{entity} previously objected to: {o.metadata.get('objection_type', '')}",
                    "source": "customer signals",
                    "confidence": 1.0,
                    "evidence": {"artifact": o.artifact, "timestamp": o.timestamp.isoformat()},
                })

            # What decisions have been made?
            decisions = [s for s in customer_signals
                        if s.type == SignalType.CUSTOMER_DECISION]
            for d in decisions:
                outcome = d.metadata.get("decision_outcome", "unknown")
                whispers.append({
                    "type": "decision_history",
                    "text": f"{entity} previously decided: {outcome}",
                    "source": "customer signals",
                    "confidence": 1.0,
                    "evidence": {"artifact": d.artifact, "outcome": outcome},
                })

        # Check if entity is a person
        person_signals = [s for s in self.signals if s.actor == entity
                         or s.metadata.get("contact") == entity]
        if person_signals:
            # What does this person know?
            domains = set()
            for s in person_signals:
                domain = s.metadata.get("domain", "")
                if domain:
                    domains.add(domain)
            if domains:
                whispers.append({
                    "type": "expertise",
                    "text": f"{entity} has expertise in: {', '.join(domains)}",
                    "source": "knowledge graph",
                    "confidence": 0.8,
                    "evidence": {"domains": list(domains)},
                })

        # Check if entity is a law code
        if entity in self.model.laws:
            law = self.model.laws[entity]
            whispers.append({
                "type": "law_exists",
                "text": f"Organizational law {entity}: {law.statement[:80]}",
                "source": "OEM laws",
                "confidence": law.confidence,
                "evidence": {"validated": law.validated_runtimes, "failed": law.failed_runtimes},
            })

        return whispers

    def _entity_warnings(self, entity: str) -> list[dict[str, Any]]:
        """What should you watch out for with this entity?"""
        warnings = []

        from maestro_oem.signal import SignalType
        customer_signals = [s for s in self.signals
                           if s.metadata.get("customer") == entity]

        if customer_signals:
            # Broken commitments
            broken = [s for s in customer_signals if s.type == SignalType.CUSTOMER_COMMITMENT_BROKEN]
            if broken:
                warnings.append({
                    "type": "broken_commitments",
                    "text": f"{entity} has {len(broken)} broken commitment(s). Trust may be fragile.",
                    "severity": "high",
                })

            # Champion quiet
            quiet = [s for s in customer_signals if s.type == SignalType.CUSTOMER_CHAMPION_QUIET]
            if quiet:
                warnings.append({
                    "type": "champion_quiet",
                    "text": f"{entity}'s champion has gone quiet. Engagement may be waning.",
                    "severity": "high",
                })

            # Open objections
            objections = [s for s in customer_signals if s.type == SignalType.CUSTOMER_OBJECTION]
            if objections:
                warnings.append({
                    "type": "open_objections",
                    "text": f"{entity} has {len(objections)} open objection(s).",
                    "severity": "medium",
                })

        # Check if entity is a bottleneck
        try:
            bottlenecks = self.model.approvals.get_bottlenecks(min_count=2)
            for bn in bottlenecks:
                if bn["gate"] == entity:
                    warnings.append({
                        "type": "bottleneck",
                        "text": f"{entity} is gating {bn['items_gated']} items. They may be overloaded.",
                        "severity": "medium",
                    })
        except Exception:
            pass

        return warnings

    def _entity_precedents(self, entity: str) -> list[dict[str, Any]]:
        """What has happened with this entity before?"""
        precedents = []

        from maestro_oem.signal import SignalType
        entity_signals = [s for s in self.signals
                         if s.metadata.get("customer") == entity
                         or s.actor == entity]

        # Group by type
        by_type: dict[str, int] = {}
        for s in entity_signals:
            t = s.type.value
            by_type[t] = by_type.get(t, 0) + 1

        for sig_type, count in by_type.items():
            if count >= 2:
                precedents.append({
                    "type": "pattern",
                    "text": f"{entity} has {count} {sig_type} signal(s) — a recurring pattern.",
                    "count": count,
                })

        return precedents

    def _topic_whispers(self, topic: str) -> list[dict[str, Any]]:
        """What does the org know about this topic?"""
        whispers = []
        topic_lower = topic.lower()

        # Search laws for this topic
        for law in self.model.laws.values():
            if topic_lower in law.statement.lower():
                whispers.append({
                    "type": "relevant_law",
                    "text": f"Relevant law: {law.statement[:80]}",
                    "source": "OEM laws",
                    "confidence": law.confidence,
                    "evidence": {"code": law.code},
                })

        # Search LOs for this topic
        from maestro_oem.learning_object import LearningObjectType
        for lo in self.model.learning_objects.values():
            if topic_lower in lo.title.lower() or topic_lower in lo.description.lower():
                whispers.append({
                    "type": "relevant_evidence",
                    "text": f"Past evidence: {lo.title[:80]}",
                    "source": "learning objects",
                    "confidence": lo.confidence,
                    "evidence": {"lo_id": str(lo.lo_id)},
                })

        return whispers

    def _topic_warnings(self, topic: str) -> list[dict[str, Any]]:
        """Warnings about this topic."""
        warnings = []
        topic_lower = topic.lower()

        # Check for challenged laws on this topic
        for law in self.model.laws.values():
            if topic_lower in law.statement.lower() and law.failed_runtimes > 0:
                warnings.append({
                    "type": "challenged_pattern",
                    "text": f"The pattern '{law.statement[:60]}' has {law.failed_runtimes} failures. Be cautious.",
                    "severity": "medium",
                })

        return warnings

    def _context_whispers(self, context: str, entity: str) -> list[dict[str, Any]]:
        """Context-specific whispers."""
        whispers = []

        if context == "meeting":
            # Surface what the org knows that hasn't been said
            if entity:
                whispers.append({
                    "type": "meeting_context",
                    "text": f"Review {entity}'s relationship memory before the meeting.",
                    "source": "context",
                    "confidence": 0.5,
                })

        elif context == "decision":
            # Surface alternatives and precedents
            whispers.append({
                "type": "decision_context",
                "text": "Check the Time Machine for similar past decisions before committing.",
                "source": "context",
                "confidence": 0.5,
            })

        elif context == "proposal":
            # Surface related RFCs and approvals
            whispers.append({
                "type": "proposal_context",
                "text": "Check for duplicate work — someone may have already proposed this.",
                "source": "context",
                "confidence": 0.5,
            })

        return whispers

    def _cross_team_knowledge(self, entity: str, topic: str) -> list[dict[str, Any]]:
        """Surface knowledge from other teams that's relevant here."""
        whispers = []

        # Find LOs that involve multiple providers (cross-team signals)
        from collections import defaultdict
        provider_lo: dict[str, list] = defaultdict(list)
        for lo in self.model.learning_objects.values():
            for p in lo.providers:
                provider_lo[p].append(lo)

        # If there's knowledge from a team the user isn't on, surface it
        for provider, los in provider_lo.items():
            if provider == "customer" and topic:
                # Customer Success knowledge
                for lo in los[:2]:
                    if topic.lower() in lo.title.lower() or topic.lower() in lo.description.lower():
                        whispers.append({
                            "type": "cross_team",
                            "text": f"Customer Success knows: {lo.title[:80]}",
                            "source": f"team:{provider}",
                            "confidence": lo.confidence,
                        })

        return whispers

    def _compute_confidence(self, whispers: list) -> float:
        if not whispers:
            return 0.0
        return sum(w.get("confidence", 0.5) for w in whispers) / len(whispers)

    def _narrative(self, whispers: list, warnings: list) -> str:
        if not whispers and not warnings:
            return "No organizational knowledge surfaced for this context."
        parts = []
        if whispers:
            parts.append(f"{len(whispers)} relevant insight(s) from the organization's memory.")
        if warnings:
            parts.append(f"{len(warnings)} warning(s) to watch for.")
        return " ".join(parts)

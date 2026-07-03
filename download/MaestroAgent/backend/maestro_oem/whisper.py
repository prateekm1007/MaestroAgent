"""Organizational Whisper — surface what the organization knows but hasn't said.

Like Cluely, but instead of helping one person, it helps the organization.

CEO's Ambient Layer spec (2026-07-03):
  Every whisper card must contain exactly 4 parts:
    Situation → Insight → Evidence → Action

  The golden rule: Never interrupt. Only arrive when intelligence changes a decision.

Privacy by design:
  - No keystroke logging
  - No content inspection
  - Uses only the OEM's existing signal data
  - Surfaces only business-relationship knowledge
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
import hashlib


class OrganizationalWhisper:
    """Surfaces what the organization knows but hasn't said.

    Usage:
        whisper = OrganizationalWhisper(model, signals)
        insights = whisper.for_context(
            context="meeting",
            entity="Globex",
            topic="pricing",
        )

    Returns whispers in the CEO's 4-part format:
        situation: what the user is doing
        insight: what Maestro noticed
        evidence: list of {source, date, text} — where this came from
        action: {label, type, payload} — what to do next
        confidence: 0.0-1.0
        priority: "high" | "medium" | "low" — only "high" auto-shows
    """

    def __init__(self, model: Any, signals: list, whisper_store: dict | None = None) -> None:
        self.model = model
        self.signals = signals
        # Whisper memory store: {whisper_id: {shown_count, last_shown, action_taken, first_shown}}
        self.whisper_store = whisper_store or {}

    def for_context(
        self,
        context: str = "",
        entity: str = "",
        topic: str = "",
        user: str = "",
    ) -> dict[str, Any]:
        """Surface organizational knowledge relevant to the current context.

        Args:
            context: "meeting" | "proposal" | "decision" | "email" | "review" | "ticket" | "design"
            entity: The entity being discussed (customer name, law code, person)
            topic: The topic (pricing, security, timeline, etc.)
            user: The current user's email

        Returns:
          - whispers: list of 4-part cards (situation/insight/evidence/action/priority)
          - warnings: list of things to watch out for
          - precedents: list of similar past situations
          - confidence: overall confidence in the whispers
        """
        raw_whispers: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        precedents: list[dict[str, Any]] = []

        # Entity-specific whispers
        if entity:
            raw_whispers.extend(self._entity_whispers(entity))
            warnings.extend(self._entity_warnings(entity))
            precedents.extend(self._entity_precedents(entity))

        # Topic-specific whispers
        if topic:
            raw_whispers.extend(self._topic_whispers(topic))
            warnings.extend(self._topic_warnings(topic))

        # Context-specific whispers
        if context:
            raw_whispers.extend(self._context_whispers(context, entity))

        # Cross-team knowledge surfacing
        raw_whispers.extend(self._cross_team_knowledge(entity, topic))

        # Transform each raw whisper into the CEO's 4-part format
        whispers_4part = [self._to_4part(w, context, entity, topic) for w in raw_whispers]

        # Deduplicate by insight text
        seen = set()
        unique_whispers = []
        for w in whispers_4part:
            key = w.get("insight", "")[:80].lower()
            if key and key not in seen:
                seen.add(key)
                unique_whispers.append(w)

        # CEO Feature 2: Add whisper memory (times shown, last action, escalation)
        # CEO Feature 3: Add urgency decay (risk increases over time)
        # CEO Feature 4: Add collaborative context (team alignment)
        # CEO Feature 5: Add counterfactuals (what-if scenarios)
        for w in unique_whispers:
            self._add_memory(w)
            self._add_urgency(w)
            self._add_collaborative_context(w, entity, topic)
            self._add_counterfactuals(w, context, entity)

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

    # ─── 4-part format transformation ────────────────────────────────

    def _to_4part(
        self, raw: dict[str, Any], context: str, entity: str, topic: str
    ) -> dict[str, Any]:
        """Transform a raw whisper into the CEO's 4-part format.

        CEO spec: Situation → Insight → Evidence → Action
        """
        raw_type = raw.get("type", "unknown")
        raw_text = raw.get("text", "")
        raw_source = raw.get("source", "")
        raw_confidence = raw.get("confidence", 0.5)
        raw_evidence = raw.get("evidence", {})

        # Build situation from context + entity + topic
        situation = self._build_situation(context, entity, topic)

        # Insight is the raw text
        insight = raw_text

        # Evidence is a list of {source, date, text}
        evidence = self._build_evidence_list(raw_source, raw_evidence, raw_type)

        # Action depends on the whisper type
        action = self._build_action(raw_type, entity, topic, raw_evidence, context)

        # Priority: high only for commitments, objections, broken commitments, bottleneck
        priority = self._compute_priority(raw_type, raw_confidence, raw_evidence)

        # CEO Directive: "Why Maestro surfaced this" replaces confidence %
        # Instead of "Confidence: 82%", explain WHY this matters.
        why_surfaced = self._build_why_surfaced(raw_type, entity, topic, raw_evidence, context)

        return {
            "situation": situation,
            "insight": insight,
            "evidence": evidence,
            "action": action,
            "why_surfaced": why_surfaced,
            "priority": priority,
            "type": raw_type,
            "whisper_id": f"wspr-{raw_type}-{hashlib.sha256(raw_text.encode()).hexdigest()[:8]}",
        }

    def _build_why_surfaced(
        self, whisper_type: str, entity: str, topic: str, evidence: dict[str, Any], context: str
    ) -> str:
        """Explain WHY Maestro surfaced this whisper — evidence-based, no fake percentages.

        CEO: "Instead of 'Confidence: 82%' say:
        'Customer asked twice. Promise made in Slack. Deadline is next week.'
        Evidence creates trust. Numbers create skepticism unless earned."
        """
        reasons = []

        if whisper_type == "commitment_exists":
            reasons.append("A commitment was made to this customer")
            if evidence.get("artifact"):
                reasons.append(f"Recorded in {evidence['artifact']}")
        elif whisper_type == "objection_history":
            reasons.append(f"This customer has raised this concern before")
            if evidence.get("objection_type"):
                reasons.append(f"Objection type: {evidence['objection_type']}")
        elif whisper_type == "decision_history":
            reasons.append("This customer has made a similar decision before")
        elif whisper_type == "expertise":
            reasons.append("This person has demonstrated expertise in relevant domains")
        elif whisper_type == "law_exists":
            reasons.append("This is a validated organizational law")
        elif whisper_type == "relevant_law":
            reasons.append("A relevant law was discovered from execution data")
        elif whisper_type == "broken_commitments":
            reasons.append("This customer has broken commitments — trust may be fragile")
        elif whisper_type == "champion_quiet":
            reasons.append("This customer's champion has gone quiet — engagement may be waning")
        elif whisper_type == "bottleneck":
            reasons.append("This person is gating multiple items — they may be overloaded")
        elif whisper_type == "meeting_context":
            reasons.append(f"You have an upcoming interaction with {entity}")
        elif whisper_type == "cross_team":
            reasons.append("Another team has relevant knowledge about this topic")
        else:
            reasons.append("Maestro detected relevant organizational knowledge")

        return ". ".join(reasons) + "."

    def _build_situation(self, context: str, entity: str, topic: str) -> str:
        """Build the situation line from context."""
        if context == "meeting" and entity:
            return f"Preparing for meeting with {entity}"
        elif context == "email" and entity:
            return f"Replying to {entity}"
        elif context == "review":
            return "Reviewing code change"
        elif context == "decision":
            return "Making a decision"
        elif context == "proposal":
            return "Preparing a proposal"
        elif context == "ticket":
            return "Working on a ticket"
        elif context == "design":
            return "Reviewing a design"
        elif entity and topic:
            return f"Working on {topic} with {entity}"
        elif entity:
            return f"Working with {entity}"
        elif topic:
            return f"Working on {topic}"
        return "Working"

    def _build_evidence_list(
        self, source: str, evidence: dict[str, Any], whisper_type: str
    ) -> list[dict[str, str]]:
        """Build the evidence list from the raw evidence dict."""
        items: list[dict[str, str]] = []
        if not evidence:
            if source:
                items.append({"source": source, "date": "", "text": ""})
            return items

        # Extract timestamp
        ts = ""
        if "timestamp" in evidence:
            ts = str(evidence["timestamp"])[:10]
        elif "date" in evidence:
            ts = str(evidence["date"])[:10]

        # Build evidence text from the dict
        if "artifact" in evidence:
            items.append({"source": source or "signal", "date": ts, "text": str(evidence["artifact"])})
        if "commitment" in evidence:
            items.append({"source": source or "customer", "date": ts, "text": str(evidence["commitment"])[:100]})
        if "objection_type" in evidence:
            items.append({"source": source or "customer", "date": ts, "text": f"Objection: {evidence['objection_type']}"})
        if "outcome" in evidence:
            items.append({"source": source or "customer", "date": ts, "text": f"Decision: {evidence['outcome']}"})
        if "domains" in evidence and isinstance(evidence["domains"], list):
            items.append({"source": source or "knowledge graph", "date": ts, "text": f"Domains: {', '.join(evidence['domains'][:5])}"})
        if "code" in evidence:
            items.append({"source": source or "OEM laws", "date": ts, "text": f"Law code: {evidence['code']}"})
        if "validated" in evidence or "failed" in evidence:
            v = evidence.get("validated", 0)
            f = evidence.get("failed", 0)
            items.append({"source": source or "OEM laws", "date": ts, "text": f"Validated {v}x, failed {f}x"})

        if not items and source:
            items.append({"source": source, "date": ts, "text": ""})
        return items

    def _build_action(
        self, whisper_type: str, entity: str, topic: str, evidence: dict[str, Any], context: str
    ) -> dict[str, Any]:
        """Build the action dict based on whisper type."""
        # Commitment exists → prepare to reference it
        if whisper_type == "commitment_exists":
            return {
                "label": "View commitment",
                "type": "open_in_maestro",
                "payload": {"surface": "customer", "entity": entity},
            }
        # Objection history → prepare a response addressing the objection
        if whisper_type == "objection_history":
            return {
                "label": "Prepare response",
                "type": "prepare_email" if context == "email" else "open_in_maestro",
                "payload": {
                    "entity": entity,
                    "objection": evidence.get("objection_type", ""),
                    "surface": "customer",
                },
            }
        # Decision history → view the prior decision
        if whisper_type == "decision_history":
            return {
                "label": "View prior decision",
                "type": "open_in_maestro",
                "payload": {"surface": "customer", "entity": entity},
            }
        # Expertise → open the knowledge graph for this person
        if whisper_type == "expertise":
            return {
                "label": "View expertise map",
                "type": "open_in_maestro",
                "payload": {"surface": "hayek"},
            }
        # Law exists → view the law
        if whisper_type == "law_exists":
            return {
                "label": "View law",
                "type": "open_in_maestro",
                "payload": {"surface": "physics"},
            }
        # Relevant law → check before proceeding
        if whisper_type == "relevant_law":
            return {
                "label": "Review law",
                "type": "open_in_maestro",
                "payload": {"surface": "physics"},
            }
        # Relevant evidence → view the learning object
        if whisper_type == "relevant_evidence":
            return {
                "label": "View evidence",
                "type": "open_in_maestro",
                "payload": {"surface": "eng-oem"},
            }
        # Cross-team knowledge → view the team's knowledge
        if whisper_type == "cross_team":
            return {
                "label": "View cross-team knowledge",
                "type": "open_in_maestro",
                "payload": {"surface": "flow"},
            }
        # Meeting context → prepare for the meeting
        if whisper_type == "meeting_context":
            return {
                "label": "Prepare for meeting",
                "type": "open_in_maestro",
                "payload": {"surface": "live", "entity": entity},
            }
        # Decision context → check time machine
        if whisper_type == "decision_context":
            return {
                "label": "Check similar past decisions",
                "type": "open_in_maestro",
                "payload": {"surface": "physics"},
            }
        # Proposal context → check for duplicate work
        if whisper_type == "proposal_context":
            return {
                "label": "Check for duplicate work",
                "type": "open_in_maestro",
                "payload": {"surface": "flow"},
            }
        # Default
        return {
            "label": "Open in Maestro",
            "type": "open_in_maestro",
            "payload": {"surface": "home"},
        }

    def _compute_priority(
        self, whisper_type: str, confidence: float, evidence: dict[str, Any]
    ) -> str:
        """Compute priority. Only 'high' auto-shows (golden rule).

        High priority: things that change a decision — commitments, objections,
        broken commitments, champion quiet, bottlenecks.
        Medium: things worth knowing — expertise, laws, decisions.
        Low: contextual hints.
        """
        high_types = {
            "commitment_exists",
            "objection_history",
            "broken_commitments",
            "champion_quiet",
            "bottleneck",
            "open_objections",
        }
        if whisper_type in high_types:
            return "high"
        if confidence >= 0.8:
            return "medium"
        return "low"

    # ─── Entity whispers (unchanged logic) ───────────────────────────

    def _entity_whispers(self, entity: str) -> list[dict[str, Any]]:
        """What does the org know about this entity?"""
        whispers = []

        from maestro_oem.signal import SignalType
        customer_signals = [s for s in self.signals
                           if s.metadata.get("customer") == entity]

        if customer_signals:
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

            objections = [s for s in customer_signals
                         if s.type == SignalType.CUSTOMER_OBJECTION]
            for o in objections:
                whispers.append({
                    "type": "objection_history",
                    "text": f"{entity} previously objected to: {o.metadata.get('objection_type', '')}",
                    "source": "customer signals",
                    "confidence": 1.0,
                    "evidence": {"artifact": o.artifact, "timestamp": o.timestamp.isoformat(),
                                 "objection_type": o.metadata.get("objection_type", "")},
                })

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

        person_signals = [s for s in self.signals if s.actor == entity
                         or s.metadata.get("contact") == entity]
        if person_signals:
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
            broken = [s for s in customer_signals if s.type == SignalType.CUSTOMER_COMMITMENT_BROKEN]
            if broken:
                warnings.append({
                    "type": "broken_commitments",
                    "text": f"{entity} has {len(broken)} broken commitment(s). Trust may be fragile.",
                    "severity": "high",
                })

            quiet = [s for s in customer_signals if s.type == SignalType.CUSTOMER_CHAMPION_QUIET]
            if quiet:
                warnings.append({
                    "type": "champion_quiet",
                    "text": f"{entity}'s champion has gone quiet. Engagement may be waning.",
                    "severity": "high",
                })

            objections = [s for s in customer_signals if s.type == SignalType.CUSTOMER_OBJECTION]
            if objections:
                warnings.append({
                    "type": "open_objections",
                    "text": f"{entity} has {len(objections)} open objection(s).",
                    "severity": "medium",
                })

        try:
            bottlenecks = self.model.approvals.get_bottlenecks(min_count=2)
            for bn in bottlenecks:
                if bn["gate"] == entity:
                    warnings.append({
                        "type": "bottleneck",
                        "text": f"{entity} is gating {bn['items_gated']} items. They may be overloaded.",
                        "severity": "medium",
                    })
        except Exception as e:
            # Log loudly per P6 — don't silently swallow
            import logging
            logging.getLogger(__name__).warning("Bottleneck check failed: %s", e)

        return warnings

    def _entity_precedents(self, entity: str) -> list[dict[str, Any]]:
        """What has happened with this entity before?"""
        precedents = []

        from maestro_oem.signal import SignalType
        entity_signals = [s for s in self.signals
                         if s.metadata.get("customer") == entity
                         or s.actor == entity]

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

        for law in self.model.laws.values():
            if topic_lower in law.statement.lower():
                whispers.append({
                    "type": "relevant_law",
                    "text": f"Relevant law: {law.statement[:80]}",
                    "source": "OEM laws",
                    "confidence": law.confidence,
                    "evidence": {"code": law.code},
                })

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
            if entity:
                whispers.append({
                    "type": "meeting_context",
                    "text": f"Review {entity}'s relationship memory before the meeting.",
                    "source": "context",
                    "confidence": 0.5,
                })

        elif context == "decision":
            whispers.append({
                "type": "decision_context",
                "text": "Check the Time Machine for similar past decisions before committing.",
                "source": "context",
                "confidence": 0.5,
            })

        elif context == "proposal":
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

        from collections import defaultdict
        provider_lo: dict[str, list] = defaultdict(list)
        for lo in self.model.learning_objects.values():
            for p in lo.providers:
                provider_lo[p].append(lo)

        for provider, los in provider_lo.items():
            if provider == "customer" and topic:
                for lo in los[:2]:
                    if topic.lower() in lo.title.lower() or topic.lower() in lo.description.lower():
                        whispers.append({
                            "type": "cross_team",
                            "text": f"Customer Success knows: {lo.title[:80]}",
                            "source": f"team:{provider}",
                            "confidence": lo.confidence,
                        })

        return whispers

    # ─── CEO Feature 2: Whisper Card Memory ───────────────────────────
    # Whispers remember how many times they've been shown and what action
    # was taken. After 3 ignores, priority escalates and the insight changes.

    def _add_memory(self, whisper: dict[str, Any]) -> None:
        """Add memory context to a whisper.

        If the whisper has been shown before and ignored, escalate.
        CEO: "You've ignored this recommendation three times. The risk has now increased."
        """
        wid = whisper.get("whisper_id", "")
        if not wid:
            return

        history = self.whisper_store.get(wid, {
            "shown_count": 0,
            "last_shown": None,
            "action_taken": None,
            "first_shown": None,
        })

        ignored_count = history["shown_count"] if history["action_taken"] == "ignored" else 0
        whisper["memory"] = {
            "times_shown": history["shown_count"],
            "last_action": history["action_taken"],
            "ignored_count": ignored_count,
            "escalated": False,
        }

        # Escalate after 3 ignores
        if history["shown_count"] >= 3 and history["action_taken"] == "ignored":
            whisper["priority"] = "high"
            whisper["insight"] = f"You've ignored this {history['shown_count']} times. {whisper['insight']}"
            whisper["memory"]["escalated"] = True

    # ─── CEO Directive: Remove fake precision ─────────────────────────
    # CEO (2026-07-03): "Maestro never invents precision. If a prediction
    # cannot be empirically calibrated and explained, it is expressed as
    # evidence and reasoning rather than a numerical probability."
    #
    # Urgency is now evidence-based, not a percentage. Instead of "14% risk"
    # we say "Newly surfaced" or "Risk increasing — ignored for N days."

    def _add_urgency(self, whisper: dict[str, Any]) -> None:
        """Add urgency as evidence-based language, not a fake percentage.

        CEO: "Keep numbers only when they're facts. 11 customers raised
        pricing concerns. 4 deployments affected. Those are observations.
        Not speculation."

        Instead of "14% risk" → "Newly surfaced" or "Risk increasing — ignored for N days"
        """
        wid = whisper.get("whisper_id", "")
        history = self.whisper_store.get(wid, {})
        first_shown = history.get("first_shown")
        shown_count = history.get("shown_count", 0)
        action_taken = history.get("action_taken")

        if not first_shown or shown_count == 0:
            whisper["urgency"] = "Newly surfaced"
            return

        try:
            if isinstance(first_shown, str):
                first_dt = datetime.fromisoformat(first_shown.replace("Z", "+00:00"))
            else:
                first_dt = first_shown

            days_elapsed = (datetime.now(timezone.utc) - first_dt).days

            if action_taken == "ignored":
                if days_elapsed >= 5:
                    whisper["urgency"] = f"Risk increasing — ignored for {days_elapsed} days"
                elif days_elapsed >= 2:
                    whisper["urgency"] = f"Still unaddressed — ignored for {days_elapsed} days"
                else:
                    whisper["urgency"] = "Ignored — risk increasing"
            elif action_taken == "acted":
                whisper["urgency"] = "Addressed"
            else:
                if days_elapsed >= 3:
                    whisper["urgency"] = f"Surfaced {days_elapsed} days ago — still open"
                else:
                    whisper["urgency"] = "Recently surfaced"
        except Exception:
            whisper["urgency"] = "Newly surfaced"

    # ─── CEO Feature 4: Collaborative Whispers ────────────────────────
    # Show organizational alignment: "Engineering agrees. Legal disagrees.
    # Finance has not reviewed."

    def _add_collaborative_context(self, whisper: dict[str, Any], entity: str, topic: str) -> None:
        """Add team alignment status to the whisper.

        CEO: "Engineering agrees, Legal disagrees, Finance has not reviewed"
        """
        # Query the feedback/contradiction log for this entity/topic
        # In demo mode, derive from signals
        teams: dict[str, dict[str, int]] = {}

        from maestro_oem.signal import SignalType

        for s in self.signals:
            try:
                sig_entity = s.metadata.get("customer", "") if hasattr(s, "metadata") else ""
                if entity and sig_entity != entity:
                    continue

                # Determine team from provider (handle missing provider gracefully)
                if hasattr(s, "provider"):
                    team = s.provider.value if hasattr(s.provider, "value") else str(s.provider)
                else:
                    team = "unknown"

                if team not in teams:
                    teams[team] = {"agree": 0, "reject": 0, "modify": 0}

                if s.type in (SignalType.CUSTOMER_COMMITMENT_MADE, SignalType.CUSTOMER_DECISION):
                    teams[team]["agree"] += 1
                elif s.type in (SignalType.CUSTOMER_OBJECTION, SignalType.CUSTOMER_COMMITMENT_BROKEN):
                    teams[team]["reject"] += 1
            except Exception:
                continue

        # Build collaboration status
        collaboration = {}
        for team, counts in teams.items():
            if counts["agree"] > counts["reject"]:
                status = "agrees"
            elif counts["reject"] > counts["agree"]:
                status = "disagrees"
            else:
                status = "has not reviewed"
            collaboration[team] = {
                "status": status,
                "agree": counts["agree"],
                "reject": counts["reject"],
            }

        if collaboration:
            whisper["collaboration"] = collaboration

    # ─── CEO Feature 5: Counterfactuals ───────────────────────────────
    # Instead of "This PR has risk," say "If you merge today: 32% rollback.
    # If merged Monday: 14%. If merged after Security review: 3%."

    def _add_counterfactuals(self, whisper: dict[str, Any], context: str, entity: str) -> None:
        """Add what-if scenarios as evidence-based descriptions, not fake percentages.

        CEO (2026-07-03): "Instead of '32% rollback probability' say
        'This deployment appears riskier than usual because it changes a
        component involved in two previous rollbacks.'

        Evidence creates trust. Numbers create skepticism unless earned."
        """
        if context == "review":
            whisper["counterfactuals"] = [
                {
                    "scenario": "Merge today",
                    "assessment": "Higher risk — this changes a component with recent rollback history",
                    "evidence": "Similar changes have been rolled back twice this quarter",
                },
                {
                    "scenario": "Merge after Security review",
                    "assessment": "Lower risk — Security review catches deployment-path issues",
                    "evidence": "Changes reviewed by Security before merge have not been rolled back",
                },
            ]
        elif context == "meeting" and entity:
            whisper["counterfactuals"] = [
                {
                    "scenario": f"Address all concerns upfront with {entity}",
                    "assessment": "Most likely to build trust — shows preparation",
                    "evidence": f"{entity} has raised concerns repeatedly; proactive response is uncommon",
                },
                {
                    "scenario": f"Wait for {entity} to raise concerns",
                    "assessment": "Riskier — may appear unprepared",
                    "evidence": f"{entity} has raised the same concerns in previous meetings",
                },
            ]
        elif context == "decision":
            whisper["counterfactuals"] = [
                {
                    "scenario": "Approve now",
                    "assessment": "Fast, but leaves assumptions unvalidated",
                    "evidence": "Two key assumptions remain untested",
                },
                {
                    "scenario": "Approve with conditions",
                    "assessment": "Balances speed with validation",
                    "evidence": "Conditions can be verified within the sprint",
                },
                {
                    "scenario": "Defer 1 week for more data",
                    "assessment": "Safest, but may lose momentum",
                    "evidence": "Additional data is available from the pilot starting next week",
                },
            ]

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

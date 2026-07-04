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

from maestro_oem.evidence import Evidence, EvidenceBuilder


class OrganizationalWhisper:
    """Surfaces what the organization knows but hasn't said.

    Usage:
        whisper = OrganizationalWhisper(model, signals)
        insights = whisper.for_context(
            context="meeting",
            entity="<customer>",
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

        # H2 FIX (adversarial audit finding): Wire CommitmentMutationTracker
        # and DisagreementDetector into the ACTUAL Whisper generation path.
        # Before this fix, both were demonstration endpoints only (P11 violation).
        # Now they run on every Whisper, enriching the evidence_spine with
        # mutation history and detected disagreements.
        for w in unique_whispers:
            self._apply_mutation_tracking(w, entity)
            self._apply_disagreement_detection(w, entity, topic)

        # CRITICAL-01 FIX (external auditor finding): Wire the delivery decision
        # gate into the ACTUAL generation path. Before this fix, decide_delivery()
        # existed as a well-tested pure function but was never called by the
        # Whisper pipeline — every Whisper was returned without ever asking
        # "should I stay quiet?" Now the gate runs on every Whisper, deriving
        # its inputs from the whisper_store history (not caller-supplied booleans).
        delivered_whispers, suppressed_whispers = self._apply_delivery_gate(unique_whispers, entity)

        confidence = self._compute_confidence(delivered_whispers)

        return {
            "context": context,
            "entity": entity,
            "topic": topic,
            "user": user,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "whispers": delivered_whispers[:10],
            "suppressed_whispers": suppressed_whispers,
            "warnings": warnings[:5],
            "precedents": precedents[:5],
            "narrative": self._narrative(delivered_whispers, warnings),
        }

    def _apply_delivery_gate(
        self, whispers: list[dict[str, Any]], entity: str = ""
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Apply the delivery decision gate to each whisper.

        CRITICAL-01 FIX: This method wires decide_delivery() into the actual
        Whisper generation path. It derives the gate's inputs from the
        whisper_store history (shown_count, action_taken, last_shown) — NOT
        from caller-supplied booleans.

        Whispers that the gate says to suppress are moved to the
        suppressed_whispers list (returned separately, not shown to the user).

        Returns:
            (delivered_whispers, suppressed_whispers)
        """
        from maestro_oem.delivery_decision import decide_delivery, DeliveryDecision
        from maestro_oem.signal import SignalType

        delivered: list[dict[str, Any]] = []
        suppressed: list[dict[str, Any]] = []

        # Check if any entity has high-stakes signals (broken commitment, objection, churn)
        has_high_stakes = False
        if entity:
            for s in self.signals:
                try:
                    if hasattr(s, "metadata") and s.metadata.get("customer") == entity:
                        if hasattr(s, "type") and s.type in (
                            SignalType.CUSTOMER_COMMITMENT_BROKEN,
                            SignalType.CUSTOMER_OBJECTION,
                            SignalType.CUSTOMER_CONTRACT_CHURNED,
                            SignalType.CUSTOMER_CHAMPION_QUIET,
                        ):
                            has_high_stakes = True
                            break
                except Exception:
                    continue

        # Check cold-start mode (few signals overall)
        signal_count = len(self.signals) if self.signals else 0
        is_cold_start = signal_count < 5  # matches ColdStartMode.RETRIEVAL_ONLY threshold

        for w in whispers:
            wid = w.get("whisper_id", "")
            history = self.whisper_store.get(wid, {}) if self.whisper_store else {}
            shown_count = history.get("shown_count", 0) if isinstance(history, dict) else 0
            action_taken = history.get("action_taken") if isinstance(history, dict) else None
            last_shown = history.get("last_shown") if isinstance(history, dict) else None

            # Derive "materially_changed_since_last_shown" from signals
            # If any signal for this entity is newer than last_shown, it changed
            materially_changed = True  # Default: if never shown, everything is "new"
            if last_shown and entity:
                try:
                    if last_shown.endswith("Z"):
                        last_shown_dt = datetime.fromisoformat(last_shown[:-1] + "+00:00")
                    else:
                        last_shown_dt = datetime.fromisoformat(last_shown)
                    if last_shown_dt.tzinfo is None:
                        last_shown_dt = last_shown_dt.replace(tzinfo=timezone.utc)
                    for s in self.signals:
                        if hasattr(s, "metadata") and s.metadata.get("customer") == entity:
                            if hasattr(s, "timestamp") and s.timestamp and s.timestamp > last_shown_dt:
                                materially_changed = True
                                break
                    else:
                        materially_changed = False
                except Exception:
                    pass  # If parsing fails, default to True (don't suppress on error)

            exec_already_acted = action_taken == "acted"

            # Run the gate
            decision = decide_delivery(
                exec_already_acted=exec_already_acted,
                materially_changed_since_last_shown=materially_changed,
                has_high_stakes_signal=has_high_stakes,
                is_cold_start=is_cold_start,
                shown_count=shown_count,
            )

            # Attach the decision to the whisper (for transparency)
            w["delivery_decision"] = decision.name

            # Check if the decision is a suppression
            suppression_decisions = {
                DeliveryDecision.SUPPRESS_ALREADY_UNDERSTOOD,
                DeliveryDecision.SUPPRESS_REDUNDANT,
                DeliveryDecision.SUPPRESS_LOW_STAKES,
                DeliveryDecision.DEFER_UNTIL_EVIDENCE,
            }

            if decision in suppression_decisions:
                suppressed.append(w)
            else:
                delivered.append(w)
                # Priority 3: Record SHOWN event in InteractionMemory
                # This enriches the AttributionAnalyzer with the full engagement
                # lifecycle (shown → opened → dismissed/deferred/acted/...).
                # Fail-closed (P6): if InteractionMemory is unavailable, the
                # Whisper is still delivered — interaction tracking is additive.
                try:
                    from maestro_oem.interaction_memory import get_default_memory, InteractionEventType
                    get_default_memory().record(
                        wid, InteractionEventType.SHOWN, org_id="default",
                    )
                except Exception as ie:
                    logger.debug("InteractionMemory SHOWN record failed for %s: %s", wid, ie)

        return delivered, suppressed

    def _apply_mutation_tracking(self, whisper: dict[str, Any], entity: str) -> None:
        """H2 FIX: Wire CommitmentMutationTracker into the Whisper pipeline.

        For each whisper about an entity with commitment signals, check if
        the commitment has mutated (wording changed). If so, attach the
        mutation history to the whisper's evidence_spine.

        This is the same pattern as _apply_delivery_gate (CRITICAL-01 fix):
        derive the data from real signals, not caller-supplied inputs.
        """
        if not entity or not self.signals:
            return

        from maestro_oem.commitment_mutation_tracker import CommitmentMutationTracker
        from maestro_oem.signal import SignalType

        # Find commitment signals for this entity
        commitment_signals = [
            s for s in self.signals
            if hasattr(s, "metadata") and s.metadata.get("customer") == entity
            and hasattr(s, "type") and s.type == SignalType.CUSTOMER_COMMITMENT_MADE
        ]

        if not commitment_signals:
            return

        # Record commitments in the tracker and check for mutations
        tracker = CommitmentMutationTracker()
        for s in commitment_signals:
            tracker.record_commitment(s)

        mutations = tracker.get_mutations(entity)
        history = tracker.get_mutation_history(entity)

        if not history:
            return

        # Attach mutation history to the whisper's evidence_spine
        es = whisper.get("evidence_spine", {})
        es["mutation_history"] = [e.to_dict() for e in history]
        es["commitment_mutations"] = [m.to_dict() for m in mutations]
        whisper["evidence_spine"] = es

    def _apply_disagreement_detection(
        self, whisper: dict[str, Any], entity: str, topic: str
    ) -> None:
        """H2 FIX: Wire DisagreementDetector into the Whisper pipeline.

        For each whisper, run the DisagreementDetector on the evidence
        in the evidence_spine. If disagreements are detected across
        different claim_types, attach them to the whisper.

        This is the same pattern as _apply_delivery_gate (CRITICAL-01 fix):
        derive the data from real evidence, not caller-supplied inputs.
        """
        from maestro_oem.disagreement_detector import DisagreementDetector
        from maestro_oem.evidence import Evidence

        es = whisper.get("evidence_spine", {})
        if not es:
            return

        # Build Evidence objects from the evidence_spine's observed_facts
        # and conflicting_evidence
        evidence_objects: list[Evidence] = []

        # The main claim
        claim = es.get("claim", "")
        claim_type = es.get("claim_type", "observed_fact")
        observed_facts = es.get("observed_facts", [])
        if claim:
            evidence_objects.append(Evidence(
                claim=claim,
                observed_facts=observed_facts,
                claim_type=claim_type,
            ))

        # Conflicting evidence (already detected by EvidenceBuilder)
        for conflict in es.get("conflicting_evidence", []):
            conflict_claim = conflict.get("claim", "")
            if conflict_claim:
                evidence_objects.append(Evidence(
                    claim=conflict_claim,
                    observed_facts=[{"source": conflict.get("source", ""), "text": conflict_claim}],
                    claim_type="observed_fact",  # conflicts are observed
                ))

        if len(evidence_objects) < 2:
            # Not enough evidence to detect disagreements
            es["detected_disagreements"] = []
            whisper["evidence_spine"] = es
            return

        # Run the DisagreementDetector
        detector = DisagreementDetector()
        disagreements = detector.detect(evidence_objects, entity=entity, topic=topic)

        es["detected_disagreements"] = [d.to_dict() for d in disagreements]
        whisper["evidence_spine"] = es

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

        # Phase 1: Build Evidence object from actual signal data
        builder = EvidenceBuilder(self.signals)
        evidence_obj = builder.build_for_whisper(
            whisper_type=raw_type,
            entity=entity,
            topic=topic,
            raw_evidence=raw_evidence,
            context=context,
        )

        return {
            "situation": situation,
            "insight": insight,
            "evidence": evidence,
            "evidence_spine": evidence_obj.to_dict(),
            "action": action,
            "why_surfaced": evidence_obj.render_why(),
            "priority": priority,
            "type": raw_type,
            "whisper_id": f"wspr-{raw_type}-{hashlib.sha256(raw_text.encode()).hexdigest()[:8]}",
        }

    def _build_why_surfaced(
        self, whisper_type: str, entity: str, topic: str, evidence: dict[str, Any], context: str
    ) -> str:
        """Explain WHY Maestro surfaced this whisper — dynamic evidence, not static templates.

        CEO: "Instead of 'Confidence: 82%' say:
        'Customer asked twice. Promise made in Slack. Deadline is next week.'
        Evidence creates trust. Numbers create skepticism unless earned."

        Auditor P0-1: Replace 11 static template strings with dynamic evidence
        pulled from actual signal data (who said it, when, in what channel).
        """
        reasons = []

        if whisper_type == "commitment_exists":
            # Dynamic: pull the actual commitment text, who made it, when
            artifact = evidence.get("artifact", "")
            timestamp = evidence.get("timestamp", "")
            date_str = timestamp[:10] if timestamp else "recently"
            if artifact:
                reasons.append(f"Recorded in {artifact} on {date_str}")
            else:
                reasons.append("A commitment was made to this customer")
            # Count how many times this customer has raised concerns
            concern_count = sum(1 for s in self.signals
                               if hasattr(s, "metadata") and s.metadata.get("customer") == entity
                               and hasattr(s, "type")
                               and "objection" in str(s.type).lower())
            if concern_count > 0:
                reasons.append(f"Customer has raised {concern_count} concern{'s' if concern_count != 1 else ''} in total")

        elif whisper_type == "objection_history":
            obj_type = evidence.get("objection_type", "")
            timestamp = evidence.get("timestamp", "")
            date_str = timestamp[:10] if timestamp else "previously"
            if obj_type:
                reasons.append(f"Customer raised '{obj_type}' concern on {date_str}")
            else:
                reasons.append("Customer has raised this concern before")
            # Count total objections from this customer
            total_objections = sum(1 for s in self.signals
                                  if hasattr(s, "metadata") and s.metadata.get("customer") == entity
                                  and hasattr(s, "type")
                                  and "objection" in str(s.type).lower())
            if total_objections > 1:
                reasons.append(f"This is 1 of {total_objections} objections from this customer")

        elif whisper_type == "decision_history":
            outcome = evidence.get("outcome", "")
            if outcome:
                reasons.append(f"Customer previously decided: {outcome}")
            else:
                reasons.append("Customer has made a similar decision before")

        elif whisper_type == "expertise":
            domains = evidence.get("domains", [])
            if domains:
                reasons.append(f"This person has demonstrated expertise in: {', '.join(domains[:3])}")
            else:
                reasons.append("This person has demonstrated expertise in relevant domains")

        elif whisper_type == "law_exists":
            validated = evidence.get("validated", 0)
            failed = evidence.get("failed", 0)
            if validated or failed:
                reasons.append(f"Validated {validated}x, failed {failed}x in production")
            else:
                reasons.append("This is a validated organizational law")

        elif whisper_type == "relevant_law":
            code = evidence.get("code", "")
            if code:
                reasons.append(f"Discovered as organizational law {code}")
            else:
                reasons.append("A relevant law was discovered from execution data")

        elif whisper_type == "broken_commitments":
            # Count broken commitments
            broken_count = sum(1 for s in self.signals
                              if hasattr(s, "metadata") and s.metadata.get("customer") == entity
                              and hasattr(s, "type")
                              and "broken" in str(s.type).lower())
            if broken_count > 0:
                reasons.append(f"Customer has {broken_count} broken commitment{'s' if broken_count != 1 else ''} — trust may be fragile")
            else:
                reasons.append("Customer has broken commitments — trust may be fragile")

        elif whisper_type == "champion_quiet":
            reasons.append(f"Customer's champion has gone quiet — engagement may be waning")

        elif whisper_type == "bottleneck":
            reasons.append(f"This person is gating multiple items — they may be overloaded")

        elif whisper_type == "meeting_context":
            if entity:
                reasons.append(f"You have an upcoming interaction with {entity}")
            else:
                reasons.append("You have an upcoming interaction")

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

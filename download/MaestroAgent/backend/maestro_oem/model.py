"""
ExecutionModel — the living OEM state.

This is NOT a rebuild-every-time model. It is incrementally updated.

Every signal that arrives produces a ModelDelta — a set of changes
to the model's state. The model applies the delta and records a receipt.

The model maintains:
- Execution Health (velocity, throughput, incident rate)
- Knowledge Flow (who knows what, where it dies)
- Hidden Expertise (undocumented experts)
- Decision Velocity (how fast decisions are made)
- Approval Network (who approves what)
- Risk Surface (departure risks, bottleneck risks)
- Current Reality (what's true right now)
- Execution Capacity (what the org can do)
- Confidence Surface (how reliable each insight is)
- Organizational Laws (validated patterns)
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from maestro_oem.confidence import ConfidenceCalculator
from maestro_oem.law import LawStatus, OrganizationalLaw
from maestro_oem.learning_object import LearningObject, LearningObjectType
from maestro_oem.pattern import Pattern, PatternDetector, PatternType
from maestro_oem.receipt import Receipt, ReceiptChain
from maestro_oem.signal import ExecutionSignal, SignalProvider, SignalType


class ExecutionHealth(BaseModel):
    """Real-time execution health metrics."""
    decision_velocity_days: float = 0.0  # Median decision-to-action time
    release_frequency: float = 0.0  # Releases per week
    incident_rate: float = 0.0  # P1s per week
    velocity_trend: float = 0.0  # Positive = improving
    p1_cluster_risk: float = 0.0  # Probability of velocity drop

    def update_from_signal(self, signal: ExecutionSignal) -> dict[str, Any]:
        """Update health metrics from a signal. Returns what changed."""
        changes: dict[str, Any] = {}

        if signal.type == SignalType.PR_MERGED:
            self.release_frequency += 0.1  # Small increment per merge
            changes["release_frequency"] = self.release_frequency

        elif signal.type == SignalType.INCIDENT or (
            signal.type == SignalType.ISSUE_CREATED
            and signal.metadata.get("priority", "").upper() in ("P1", "P0", "CRITICAL")
        ):
            self.incident_rate += 1.0
            if self.incident_rate >= 3:
                self.p1_cluster_risk = min(1.0, self.incident_rate * 0.15)
            changes["incident_rate"] = self.incident_rate
            changes["p1_cluster_risk"] = self.p1_cluster_risk

        elif signal.type == SignalType.SPRINT_COMPLETED:
            self.decision_velocity_days = max(1.0, self.decision_velocity_days - 0.1)
            changes["decision_velocity_days"] = self.decision_velocity_days

        elif signal.type in (SignalType.DECISION_SIGNAL, SignalType.MEETING_COMPLETED):
            if signal.decision:
                self.decision_velocity_days = max(0.5, self.decision_velocity_days - 0.05)
                changes["decision_velocity_days"] = self.decision_velocity_days

        return changes


class KnowledgeGraph(BaseModel):
    """Who knows what, and where knowledge lives."""
    # entity -> set of domains they have expertise in
    expertise: dict[str, set[str]] = Field(default_factory=lambda: defaultdict(set))
    # entity -> influence score (computed from review/approval patterns)
    influence: dict[str, float] = Field(default_factory=lambda: defaultdict(float))
    # domain -> set of entities who hold this knowledge
    domain_holders: dict[str, set[str]] = Field(default_factory=lambda: defaultdict(set))
    # entity -> entities they collaborate with
    collaboration: dict[str, set[str]] = Field(default_factory=lambda: defaultdict(set))
    # artifacts -> entities who touched them
    artifact_authors: dict[str, set[str]] = Field(default_factory=lambda: defaultdict(set))

    def update_from_signal(self, signal: ExecutionSignal) -> dict[str, Any]:
        changes: dict[str, Any] = {}

        if signal.type in (SignalType.PR_OPENED, SignalType.PR_MERGED, SignalType.COMMIT):
            domain = signal.metadata.get("domain", "engineering")
            self.expertise[signal.actor].add(domain)
            self.domain_holders[domain].add(signal.actor)
            self.artifact_authors[signal.artifact].add(signal.actor)
            # Increment influence for active contributors
            self.influence[signal.actor] += 0.5
            changes["expertise_added"] = {"actor": signal.actor, "domain": domain}

        elif signal.type == SignalType.PR_REVIEWED:
            reviewer = signal.metadata.get("reviewer", "")
            if reviewer:
                self.influence[reviewer] += 1.0  # Reviews are high-influence
                self.collaboration[reviewer].add(signal.actor)
                changes["influence_updated"] = {"reviewer": reviewer}

        elif signal.type in (SignalType.PAGE_CREATED, SignalType.PAGE_EDITED):
            domain = signal.metadata.get("domain", "documentation")
            self.expertise[signal.actor].add(domain)
            self.domain_holders[domain].add(signal.actor)
            changes["knowledge_documented"] = {"actor": signal.actor, "domain": domain}

        elif signal.type in (SignalType.MESSAGE_SENT, SignalType.THREAD_STARTED,
                             SignalType.DECISION_SIGNAL, SignalType.CONFLICT,
                             SignalType.AGREEMENT, SignalType.QUESTION_ASKED):
            channel = signal.metadata.get("channel", "general")
            # Slack messages contribute to collaboration graph
            participants = signal.metadata.get("participants", [])
            for p in participants:
                if p != signal.actor:
                    self.collaboration[signal.actor].add(p)
            changes["collaboration_updated"] = {"actor": signal.actor, "channel": channel}

        return changes

    def get_hidden_experts(self) -> list[dict[str, Any]]:
        """Find entities with high influence but no formal documentation."""
        experts: list[dict[str, Any]] = []
        for entity, score in self.influence.items():
            if score >= 5.0:  # Threshold for "high influence"
                documented_domains = self.expertise.get(entity, set())
                # If their expertise isn't documented in Confluence
                has_docs = any(
                    entity in holders
                    for holders in self.domain_holders.values()
                    if "documentation" in holders or "confluence" in holders
                )
                if not has_docs and score > 5.0:
                    experts.append({
                        "entity": entity,
                        "influence": score,
                        "domains": list(documented_domains),
                        "undocumented": True,
                    })
        return sorted(experts, key=lambda x: x["influence"], reverse=True)

    def get_concentration_risk(self) -> dict[str, float]:
        """Find domains where knowledge is concentrated in 1 person."""
        risks: dict[str, float] = {}
        for domain, holders in self.domain_holders.items():
            if len(holders) == 1:
                entity = list(holders)[0]
                risks[domain] = self.influence.get(entity, 0)
        return risks


class ApprovalNetwork(BaseModel):
    """Who approves what, and where the gates are."""
    # gate -> count of items gated
    gate_counts: dict[str, int] = Field(default_factory=lambda: defaultdict(int))
    # gate -> total delay days
    gate_delays: dict[str, float] = Field(default_factory=lambda: defaultdict(float))
    # entity -> approval count
    approvers: dict[str, int] = Field(default_factory=lambda: defaultdict(int))

    def update_from_signal(self, signal: ExecutionSignal) -> dict[str, Any]:
        changes: dict[str, Any] = {}

        if signal.type == SignalType.ISSUE_TRANSITIONED:
            transition = signal.metadata.get("transition", "")
            if "approve" in transition.lower() or "review" in transition.lower():
                self.approvers[signal.actor] += 1
                changes["approval_recorded"] = {"approver": signal.actor}

        elif signal.type in (SignalType.MESSAGE_SENT, SignalType.THREAD_STARTED):
            # Detect approval-seeking patterns in Slack
            text = signal.metadata.get("text", "").lower()
            if any(w in text for w in ["approve", "sign off", "review", "ok to"]):
                gate = signal.metadata.get("channel", signal.actor)
                self.gate_counts[gate] += 1
                changes["gate_detected"] = {"gate": gate, "count": self.gate_counts[gate]}

        elif signal.type == SignalType.ISSUE_ASSIGNED:
            # Assignment to a specific person can indicate a gate
            assignee = signal.metadata.get("assignee", "")
            if assignee:
                self.gate_counts[assignee] += 1
                changes["gate_detected"] = {"gate": assignee, "count": self.gate_counts[assignee]}

        return changes

    def get_bottlenecks(self, min_count: int = 3) -> list[dict[str, Any]]:
        """Find approval gates that are bottlenecks."""
        bottlenecks: list[dict[str, Any]] = []
        for gate, count in self.gate_counts.items():
            if count >= min_count:
                avg_delay = self.gate_delays.get(gate, 0) / count if count > 0 else 0
                bottlenecks.append({
                    "gate": gate,
                    "items_gated": count,
                    "avg_delay_days": avg_delay,
                })
        return sorted(bottlenecks, key=lambda x: x["items_gated"], reverse=True)


class RiskSurface(BaseModel):
    """Active risks the OEM has detected."""
    departure_risks: dict[str, float] = Field(default_factory=dict)  # entity -> probability
    bottleneck_risks: dict[str, float] = Field(default_factory=dict)
    duplicate_work: list[dict[str, Any]] = Field(default_factory=list)

    def add_departure_risk(self, entity: str, probability: float) -> None:
        existing = self.departure_risks.get(entity, 0)
        self.departure_risks[entity] = max(existing, probability)

    def add_bottleneck_risk(self, gate: str, probability: float) -> None:
        existing = self.bottleneck_risks.get(gate, 0)
        self.bottleneck_risks[gate] = max(existing, probability)


class ModelDelta(BaseModel):
    """A set of changes produced by processing a signal."""
    signal_id: UUID
    signal_type: str
    provider: str
    health_changes: dict[str, Any] = Field(default_factory=dict)
    knowledge_changes: dict[str, Any] = Field(default_factory=dict)
    approval_changes: dict[str, Any] = Field(default_factory=dict)
    new_learning_objects: list[UUID] = Field(default_factory=list)
    new_patterns: list[UUID] = Field(default_factory=list)
    new_laws: list[str] = Field(default_factory=list)  # Law codes
    law_updates: list[str] = Field(default_factory=list)  # Law codes
    risk_changes: dict[str, Any] = Field(default_factory=dict)
    receipts: list[Receipt] = Field(default_factory=list)


class ExecutionModel(BaseModel):
    """
    The Organizational Execution Model.

    This is the living model. It is updated incrementally — never rebuilt.
    Every signal produces a ModelDelta that is applied to the model.
    """

    # Allow PatternDetector (non-pydantic type) as a field
    model_config = {"arbitrary_types_allowed": True}

    # The actual state
    health: ExecutionHealth = Field(default_factory=ExecutionHealth)
    knowledge: KnowledgeGraph = Field(default_factory=KnowledgeGraph)
    approvals: ApprovalNetwork = Field(default_factory=ApprovalNetwork)
    risks: RiskSurface = Field(default_factory=RiskSurface)

    # Learning objects (evidence units)
    learning_objects: dict[UUID, LearningObject] = Field(default_factory=dict)

    # Detected patterns
    pattern_detector: PatternDetector = Field(default_factory=PatternDetector)

    # Organizational laws
    laws: dict[str, OrganizationalLaw] = Field(default_factory=dict)
    next_law_number: int = 1

    # Receipt chains (provenance)
    receipt_chains: dict[str, ReceiptChain] = Field(default_factory=dict)  # target -> chain

    # Signal log
    processed_signals: list[UUID] = Field(default_factory=list)
    connected_providers: set[str] = Field(default_factory=set)

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def process_signal(self, signal: ExecutionSignal) -> ModelDelta:
        """
        Process a single signal and update the model.

        This is the core function. Every signal changes the model.
        Returns a ModelDelta describing what changed.
        """
        if signal.signal_id in self.processed_signals:
            return ModelDelta(
                signal_id=signal.signal_id,
                signal_type=signal.type.value,
                provider=signal.provider.value,
            )

        self.processed_signals.append(signal.signal_id)
        self.connected_providers.add(signal.provider.value)
        self.last_updated = datetime.now(timezone.utc)

        delta = ModelDelta(
            signal_id=signal.signal_id,
            signal_type=signal.type.value,
            provider=signal.provider.value,
        )

        # 1. Update health metrics
        health_changes = self.health.update_from_signal(signal)
        delta.health_changes = health_changes

        # 2. Update knowledge graph
        knowledge_changes = self.knowledge.update_from_signal(signal)
        delta.knowledge_changes = knowledge_changes

        # 3. Update approval network
        approval_changes = self.approvals.update_from_signal(signal)
        delta.approval_changes = approval_changes

        # 4. Generate LearningObjects from this signal
        los = self._generate_learning_objects(signal)
        for lo in los:
            self.learning_objects[lo.lo_id] = lo
            delta.new_learning_objects.append(lo.lo_id)
            self._add_receipt(signal, lo.lo_id, "learning_object.created", str(lo.lo_id), delta)

        # 5. Detect patterns from accumulated LOs
        all_los = list(self.learning_objects.values())
        law_candidates = self.pattern_detector.detect(all_los)
        for pattern in law_candidates:
            if pattern.is_law_candidate:
                law = self._promote_to_law(pattern, signal)
                if law:
                    delta.new_laws.append(law.code)
                    delta.law_updates.append(law.code)
                    self._add_receipt(signal, law.law_id, "law.created", law.code, delta)

        # 6. Update existing laws with new evidence
        self._update_laws_from_signal(signal, delta)

        # 7. Update risks
        self._update_risks(signal, delta)

        # 8. Recompute all confidence scores
        self._recompute_confidence()

        return delta

    def _generate_learning_objects(self, signal: ExecutionSignal) -> list[LearningObject]:
        """Generate LearningObjects from a signal. Provider-specific logic lives in providers/."""
        los: list[LearningObject] = []

        # GitHub signals → engineering LOs
        if signal.provider == SignalProvider.GITHUB:
            los.extend(self._github_to_los(signal))
        elif signal.provider == SignalProvider.JIRA:
            los.extend(self._jira_to_los(signal))
        elif signal.provider == SignalProvider.SLACK:
            los.extend(self._slack_to_los(signal))
        elif signal.provider == SignalProvider.CONFLUENCE:
            los.extend(self._confluence_to_los(signal))
        elif signal.provider == SignalProvider.GMAIL:
            los.extend(self._gmail_to_los(signal))

        return los

    def _github_to_los(self, signal: ExecutionSignal) -> list[LearningObject]:
        """GitHub signals produce engineering LearningObjects."""
        los: list[LearningObject] = []

        if signal.type == SignalType.PR_REVIEWED:
            reviewer = signal.metadata.get("reviewer", "")
            author = signal.actor
            domain = signal.metadata.get("domain", "engineering")
            lo = LearningObject(
                type=LearningObjectType.REVIEW_PATTERN,
                title=f"{reviewer} reviewed {author}'s PR in {domain}",
                description=f"Code review in {domain} — reviewer: {reviewer}, author: {author}",
                entities=[reviewer, author],
                artifacts=[signal.artifact],
                providers={"github"},
                metadata={"reviewer": reviewer, "author": author, "domain": domain},
            )
            lo.add_evidence(signal.signal_id, "github")
            los.append(lo)

        elif signal.type == SignalType.PR_MERGED:
            domain = signal.metadata.get("domain", "engineering")
            lo = LearningObject(
                type=LearningObjectType.RELEASE_PATTERN,
                title=f"PR merged in {domain} by {signal.actor}",
                description=f"Release pattern: {signal.actor} merged {signal.artifact}",
                entities=[signal.actor],
                artifacts=[signal.artifact],
                providers={"github"},
                metadata={"domain": domain},
            )
            lo.add_evidence(signal.signal_id, "github")
            los.append(lo)

        elif signal.type == SignalType.COMMIT:
            # Track who touches what domain
            domain = signal.metadata.get("domain", "engineering")
            lo = LearningObject(
                type=LearningObjectType.HIDDEN_EXPERT,
                title=f"{signal.actor} committed to {domain}",
                description=f"Contribution pattern: {signal.actor} in {domain}",
                entities=[signal.actor],
                artifacts=[signal.artifact],
                providers={"github"},
                metadata={"domain": domain},
            )
            lo.add_evidence(signal.signal_id, "github")
            los.append(lo)

        return los

    def _jira_to_los(self, signal: ExecutionSignal) -> list[LearningObject]:
        """Jira signals produce delivery LearningObjects."""
        los: list[LearningObject] = []

        if signal.type == SignalType.ISSUE_TRANSITIONED:
            transition = signal.metadata.get("transition", "")
            assignee = signal.metadata.get("assignee", signal.actor)
            if "approve" in transition.lower() or "review" in transition.lower():
                lo = LearningObject(
                    type=LearningObjectType.APPROVAL_GATE,
                    title=f"{assignee} approved/reviewed {signal.artifact}",
                    description=f"Approval gate: {assignee} — transition: {transition}",
                    entities=[assignee],
                    artifacts=[signal.artifact],
                    providers={"jira"},
                    metadata={"gate": assignee, "transition": transition},
                )
                lo.add_evidence(signal.signal_id, "jira")
                los.append(lo)

        elif signal.type == SignalType.ISSUE_CREATED:
            priority = signal.metadata.get("priority", "medium")
            if priority.upper() in ("P1", "P0", "CRITICAL"):
                lo = LearningObject(
                    type=LearningObjectType.INCIDENT_PATTERN,
                    title=f"P1 incident: {signal.artifact}",
                    description=f"High-priority issue created: {signal.artifact}",
                    entities=[signal.actor],
                    artifacts=[signal.artifact],
                    providers={"jira"},
                    metadata={"priority": priority},
                )
                lo.add_evidence(signal.signal_id, "jira")
                los.append(lo)

        elif signal.type == SignalType.SPRINT_COMPLETED:
            velocity = signal.metadata.get("velocity", 0)
            lo = LearningObject(
                type=LearningObjectType.VELOCITY_DROP,
                title=f"Sprint completed — velocity: {velocity}",
                description=f"Sprint velocity: {velocity} points",
                entities=[signal.team],
                artifacts=[signal.artifact],
                providers={"jira"},
                metadata={"velocity": velocity},
            )
            lo.add_evidence(signal.signal_id, "jira")
            los.append(lo)

        return los

    def _slack_to_los(self, signal: ExecutionSignal) -> list[LearningObject]:
        """Slack signals produce decision-graph LearningObjects."""
        los: list[LearningObject] = []

        if signal.type == SignalType.DECISION_SIGNAL:
            lo = LearningObject(
                type=LearningObjectType.DECISION_PATTERN,
                title=f"Decision signal from {signal.actor}",
                description=f"Decision pattern detected in Slack: {signal.metadata.get('text', '')[:100]}",
                entities=[signal.actor],
                artifacts=[signal.artifact],
                providers={"slack"},
                metadata={"channel": signal.metadata.get("channel", "")},
            )
            lo.add_evidence(signal.signal_id, "slack")
            los.append(lo)

        elif signal.type == SignalType.QUESTION_ASKED:
            # Questions are unique to Slack — they represent knowledge friction / bottleneck
            participants = signal.metadata.get("participants", [])
            lo = LearningObject(
                type=LearningObjectType.BOTTLENECK,
                title=f"Question asked by {signal.actor} — knowledge friction",
                description=f"Question in {signal.metadata.get('channel', '')}: {signal.metadata.get('text', '')[:80]}",
                entities=[signal.actor] + participants,
                artifacts=[signal.artifact],
                providers={"slack"},
                metadata={"channel": signal.metadata.get("channel", ""), "question": True},
            )
            lo.add_evidence(signal.signal_id, "slack")
            los.append(lo)

        elif signal.type == SignalType.AGREEMENT:
            # Agreements are unique to Slack — they represent consensus
            participants = signal.metadata.get("participants", [])
            lo = LearningObject(
                type=LearningObjectType.REVIEW_PATTERN,
                title=f"Agreement reached — {len(participants)} participants aligned",
                description=f"Consensus signal in {signal.metadata.get('channel', '')}",
                entities=participants,
                artifacts=[signal.artifact],
                providers={"slack"},
                metadata={"channel": signal.metadata.get("channel", ""), "agreement": True},
            )
            lo.add_evidence(signal.signal_id, "slack")
            los.append(lo)

        elif signal.type == SignalType.CONFLICT:
            participants = signal.metadata.get("participants", [])
            lo = LearningObject(
                type=LearningObjectType.DECISION_PATTERN,
                title=f"Conflict detected between {len(participants)} participants",
                description=f"Organizational disagreement in {signal.metadata.get('channel', '')}",
                entities=participants,
                artifacts=[signal.artifact],
                providers={"slack"},
                metadata={"conflict": True, "participants": participants},
            )
            lo.add_evidence(signal.signal_id, "slack")
            los.append(lo)

        return los

    def _confluence_to_los(self, signal: ExecutionSignal) -> list[LearningObject]:
        """Confluence signals produce knowledge-graph LearningObjects."""
        los: list[LearningObject] = []

        if signal.type == SignalType.PAGE_CREATED:
            domain = signal.metadata.get("domain", "documentation")
            lo = LearningObject(
                type=LearningObjectType.HIDDEN_EXPERT,
                title=f"Documentation created by {signal.actor} in {domain}",
                description=f"Knowledge documented: {signal.artifact}",
                entities=[signal.actor],
                artifacts=[signal.artifact],
                providers={"confluence"},
                metadata={"domain": domain},
            )
            lo.add_evidence(signal.signal_id, "confluence")
            los.append(lo)

        elif signal.type == SignalType.RFC_CREATED:
            # RFCs are unique to Confluence — they represent formal proposals
            domain = signal.metadata.get("domain", "planning")
            lo = LearningObject(
                type=LearningObjectType.APPROVAL_GATE,
                title=f"RFC created by {signal.actor}: {signal.metadata.get('title', '')}",
                description=f"Formal proposal: {signal.artifact} — domain: {domain}",
                entities=[signal.actor],
                artifacts=[signal.artifact],
                providers={"confluence"},
                metadata={"domain": domain, "rfc": True},
            )
            lo.add_evidence(signal.signal_id, "confluence")
            los.append(lo)

        elif signal.type == SignalType.POSTMORTEM_CREATED:
            has_owner = signal.metadata.get("has_owner", False)
            # Postmortems without owners → knowledge death (lesson created but never acted on)
            lo_type = LearningObjectType.INCIDENT_PATTERN if has_owner else LearningObjectType.KNOWLEDGE_DEATH
            lo = LearningObject(
                type=lo_type,
                title=f"Postmortem created — owner: {'yes' if has_owner else 'NO'}",
                description=f"Postmortem: {signal.artifact} — owner assignment: {has_owner}",
                entities=[signal.actor],
                artifacts=[signal.artifact],
                providers={"confluence"},
                metadata={"has_owner": has_owner},
            )
            lo.add_evidence(signal.signal_id, "confluence")
            los.append(lo)

        return los

    def _gmail_to_los(self, signal: ExecutionSignal) -> list[LearningObject]:
        """Gmail signals produce decision-velocity LearningObjects."""
        los: list[LearningObject] = []

        if signal.type == SignalType.MEETING_COMPLETED:
            participants = signal.metadata.get("participants", [])
            lo = LearningObject(
                type=LearningObjectType.DECISION_PATTERN,
                title=f"Meeting completed — {len(participants)} participants",
                description=f"Decision velocity signal: meeting with {len(participants)} people",
                entities=participants,
                artifacts=[signal.artifact],
                providers={"gmail"},
                metadata={"participants": participants, "duration": signal.metadata.get("duration", 0)},
            )
            lo.add_evidence(signal.signal_id, "gmail")
            los.append(lo)

        elif signal.type == SignalType.EMAIL_SENT:
            # External communication pattern — unique to Gmail
            recipient = signal.metadata.get("recipient", "")
            if recipient and "external" in signal.metadata.get("recipient_type", "").lower():
                lo = LearningObject(
                    type=LearningObjectType.HANDOFF_DELAY,
                    title=f"External communication: {signal.actor} → {recipient}",
                    description=f"External email pattern — may indicate customer or vendor interaction",
                    entities=[signal.actor, recipient],
                    artifacts=[signal.artifact],
                    providers={"gmail"},
                    metadata={"recipient": recipient, "external": True},
                )
                lo.add_evidence(signal.signal_id, "gmail")
                los.append(lo)

        return los

    def _promote_to_law(self, pattern: Pattern, signal: ExecutionSignal) -> OrganizationalLaw | None:
        """Promote a pattern to a law if it qualifies."""
        # Check if we already have a law for this pattern
        for existing in self.laws.values():
            if pattern.description in existing.statement:
                existing.add_validation(signal.signal_id)
                return existing

        # Create new law
        code = f"L-{self.next_law_number:04d}"
        self.next_law_number += 1

        law = OrganizationalLaw(
            code=code,
            statement=pattern.description,
            condition=pattern.description,
            outcome=f"Predicted by pattern with strength {pattern.strength:.2f}",
            status=LawStatus.CANDIDATE,
            pattern_ids=[pattern.pattern_id],
            providers=pattern.providers,
            evidence_count=pattern.evidence_count,
            validated_runtimes=1,
        )
        law.add_validation(signal.signal_id)
        self.laws[code] = law
        return law

    def _update_laws_from_signal(self, signal: ExecutionSignal, delta: ModelDelta) -> None:
        """Update existing laws with new evidence from a signal."""
        for law in self.laws.values():
            # If the signal type is relevant to the law's condition
            if self._signal_relevant_to_law(signal, law):
                if signal.metadata.get("contradicts", False):
                    law.add_counter_example(signal.signal_id)
                else:
                    law.add_validation(signal.signal_id)
                delta.law_updates.append(law.code)
                self._add_receipt(signal, law.law_id, "law.evidence_added", law.code, delta)

    def _signal_relevant_to_law(self, signal: ExecutionSignal, law: OrganizationalLaw) -> bool:
        """Check if a signal is relevant to a law."""
        # Simple heuristic: if the law's condition mentions the signal type
        signal_type_str = signal.type.value.lower()
        condition_lower = law.condition.lower()
        # Check for keyword overlap
        keywords = signal_type_str.split(".")
        return any(kw in condition_lower for kw in keywords if len(kw) > 2)

    def _update_risks(self, signal: ExecutionSignal, delta: ModelDelta) -> None:
        """Update risk surface from signal."""
        if signal.type == SignalType.INCIDENT or (
            signal.type == SignalType.ISSUE_CREATED
            and signal.metadata.get("priority", "").upper() in ("P1", "P0", "CRITICAL")
        ):
            # P1 cluster risk
            self.risks.add_bottleneck_risk(
                signal.team,
                min(1.0, self.health.p1_cluster_risk + 0.1)
            )
            delta.risk_changes["p1_cluster"] = self.health.p1_cluster_risk

        # Departure risk from Slack patterns — check all Slack signal types
        if signal.provider == SignalProvider.SLACK:
            text = signal.metadata.get("text", "").lower()
            departure_keywords = ["leaving", "resign", "quit", "new job", "new opportunity", "offer"]
            if any(w in text for w in departure_keywords):
                self.risks.add_departure_risk(signal.actor, 0.71)
                delta.risk_changes["departure_risk"] = {"entity": signal.actor, "probability": 0.71}

    def _add_receipt(
        self,
        signal: ExecutionSignal,
        target_id: UUID,
        change: str,
        target: str,
        delta: ModelDelta,
    ) -> None:
        """Add a receipt to the delta and the chain."""
        receipt = Receipt(
            signal_id=signal.signal_id,
            signal_type=signal.type.value,
            signal_provider=signal.provider.value,
            signal_timestamp=signal.timestamp,
            signal_actor=signal.actor,
            signal_artifact=signal.artifact,
            oem_change=change,
            oem_target=target,
        )
        delta.receipts.append(receipt)

        # Add to chain
        chain = self.receipt_chains.setdefault(target, ReceiptChain(target=target, target_type="auto"))
        chain.add(receipt)

    def _recompute_confidence(self) -> None:
        """Recompute all confidence scores after a model update."""
        calc = ConfidenceCalculator()

        for lo in self.learning_objects.values():
            lo.confidence = calc.compute_lo_confidence(
                evidence_count=lo.evidence_count,
                contradiction_count=lo.contradiction_count,
                providers=lo.providers,
                first_seen=lo.first_seen,
                last_seen=lo.last_seen,
            )

        for law in self.laws.values():
            law.confidence = calc.compute_law_confidence(
                validated_runtimes=law.validated_runtimes,
                failed_runtimes=law.failed_runtimes,
                evidence_count=law.evidence_count,
                providers=law.providers,
                last_validated=law.last_validated,
            )

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of the current model state."""
        return {
            "providers_connected": list(self.connected_providers),
            "signals_processed": len(self.processed_signals),
            "learning_objects": len(self.learning_objects),
            "patterns_detected": len(self.pattern_detector.patterns),
            "laws_inferred": len(self.laws),
            "validated_laws": sum(1 for l in self.laws.values() if l.status == LawStatus.VALIDATED),
            "unknown_laws": sum(1 for l in self.laws.values() if l.status == LawStatus.UNKNOWN_TO_LEADERSHIP),
            "hidden_experts": len(self.knowledge.get_hidden_experts()),
            "bottlenecks": len(self.approvals.get_bottlenecks()),
            "concentration_risks": len(self.knowledge.get_concentration_risk()),
            "departure_risks": len(self.risks.departure_risks),
            "decision_velocity_days": self.health.decision_velocity_days,
            "release_frequency": self.health.release_frequency,
            "incident_rate": self.health.incident_rate,
            "p1_cluster_risk": self.health.p1_cluster_risk,
            "last_updated": self.last_updated.isoformat(),
        }

    def get_provenance_chain(self, target: str) -> list[dict[str, Any]]:
        """Get the full provenance chain for a law, LO, or recommendation."""
        chain = self.receipt_chains.get(target)
        if chain:
            return chain.to_display()
        return []

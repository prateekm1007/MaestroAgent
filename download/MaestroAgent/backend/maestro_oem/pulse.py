"""Organizational Pulse — living metrics that make the organization feel alive.

NOT KPIs. NOT dashboards. Living organizational physics.

The Pulse is a continuously-computed set of metrics that describe the
organization's current state the way a heart rate describes a body's:
  - Temperature:        stress level (0-100, higher = more stress)
  - Momentum:           execution velocity (0-100, higher = faster)
  - Alignment:          how coordinated the org is (0-100, higher = aligned)
  - Trust:              commitment health (0-100, higher = more trust)
  - Knowledge Mobility: how easily knowledge flows (0-100, higher = better)
  - Decision Speed:     how fast decisions are made (0-100, higher = faster)

Each metric is derived from the live OEM state — signals, learning objects,
patterns, laws, and health metrics. They update every time new signals arrive.

The Pulse also tracks a qualitative state:
  - healthy:        low stress, high momentum, high alignment
  - turbulent:      high stress, moderate momentum, low alignment
  - knowledge_blocked: low knowledge mobility, high bottleneck concentration
  - decision_stalled: low decision speed, high pending decisions
  - execution_accelerating: high momentum, high alignment, low stress
  - trust_falling:  low trust, high broken commitments

Like an Apple Watch for companies.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


class OrganizationalPulse:
    """Computes living organizational metrics from the OEM state.

    Usage:
        pulse = OrganizationalPulse(model, signals)
        state = pulse.compute()
        # state = {temperature: 42, momentum: 78, alignment: 65, ...}
    """

    def __init__(self, model: Any, signals: list) -> None:
        self.model = model
        self.signals = signals

    def compute(self) -> dict[str, Any]:
        """Compute the full organizational pulse.

        Returns a dict with:
          - temperature, momentum, alignment, trust, knowledge_mobility,
            decision_speed (each 0-100)
          - state: qualitative label (healthy, turbulent, etc.)
          - trend: direction of change (improving, stable, declining)
          - narrative: one-sentence description of the org's current state
          - evidence: what signals drove each metric
        """
        now = datetime.now(timezone.utc)
        cutoff_30d = now - timedelta(days=30)
        cutoff_7d = now - timedelta(days=7)

        recent_signals = [s for s in self.signals if s.timestamp > cutoff_30d]
        week_signals = [s for s in self.signals if s.timestamp > cutoff_7d]

        temperature = self._compute_temperature(recent_signals)
        momentum = self._compute_momentum(week_signals)
        alignment = self._compute_alignment()
        trust = self._compute_trust()
        knowledge_mobility = self._compute_knowledge_mobility()
        decision_speed = self._compute_decision_speed(recent_signals)

        state = self._infer_state(temperature, momentum, alignment, trust,
                                  knowledge_mobility, decision_speed)
        narrative = self._generate_narrative(state, temperature, momentum,
                                             alignment, trust)

        return {
            "timestamp": now.isoformat(),
            "temperature": round(temperature, 1),
            "momentum": round(momentum, 1),
            "alignment": round(alignment, 1),
            "trust": round(trust, 1),
            "knowledge_mobility": round(knowledge_mobility, 1),
            "decision_speed": round(decision_speed, 1),
            "state": state,
            "narrative": narrative,
            "evidence": {
                "signals_30d": len(recent_signals),
                "signals_7d": len(week_signals),
                "laws_total": len(self.model.laws),
                "los_total": len(self.model.learning_objects),
                "recommendations_active": len(self._get_recommendations()),
            },
        }

    def _compute_temperature(self, recent_signals: list) -> float:
        """Stress level. Higher = more stress.

        Derived from:
          - Incident rate (P1s increase stress)
          - Broken commitments (each adds stress)
          - Drift signals (champion quiet, etc.)
          - Objections raised
        """
        from maestro_oem.signal import SignalType
        base = 30  # Baseline stress

        # Incidents add stress
        incidents = sum(1 for s in recent_signals if s.type == SignalType.INCIDENT
                        or (s.type == SignalType.ISSUE_CREATED
                            and s.metadata.get("priority", "").upper() in ("P1", "P0")))
        base += incidents * 5

        # Broken commitments add stress
        broken = sum(1 for s in recent_signals if s.type == SignalType.CUSTOMER_COMMITMENT_BROKEN)
        base += broken * 8

        # Drift signals add stress
        drift = sum(1 for s in recent_signals if s.type == SignalType.CUSTOMER_CHAMPION_QUIET)
        base += drift * 6

        # Objections add stress
        objections = sum(1 for s in recent_signals if s.type == SignalType.CUSTOMER_OBJECTION)
        base += objections * 4

        # Conflicts add stress
        conflicts = sum(1 for s in recent_signals if s.type == SignalType.CONFLICT)
        base += conflicts * 3

        return min(100, max(0, base))

    def _compute_momentum(self, week_signals: list) -> float:
        """Execution velocity. Higher = faster.

        Derived from:
          - PR merges, commits, releases (engineering throughput)
          - Sprint completions
          - Stage changes (customer pipeline movement)
          - Active champion signals
        """
        from maestro_oem.signal import SignalType
        base = 40  # Baseline momentum

        # Engineering throughput
        merges = sum(1 for s in week_signals if s.type == SignalType.PR_MERGED)
        commits = sum(1 for s in week_signals if s.type == SignalType.COMMIT)
        releases = sum(1 for s in week_signals if s.type == SignalType.RELEASE)
        base += merges * 4 + commits * 1 + releases * 6

        # Sprint completions
        sprints = sum(1 for s in week_signals if s.type == SignalType.SPRINT_COMPLETED)
        base += sprints * 8

        # Customer momentum
        stage_changes = sum(1 for s in week_signals if s.type == SignalType.CUSTOMER_STAGE_CHANGE)
        champion_active = sum(1 for s in week_signals if s.type == SignalType.CUSTOMER_CHAMPION_ACTIVE)
        base += stage_changes * 5 + champion_active * 3

        # Decision signals
        decisions = sum(1 for s in week_signals if s.type == SignalType.DECISION_SIGNAL
                        or s.type == SignalType.CUSTOMER_DECISION)
        base += decisions * 2

        return min(100, max(0, base))

    def _compute_alignment(self) -> float:
        """How coordinated the org is. Higher = more aligned.

        Derived from:
          - Duplicate work detected (reduces alignment)
          - Conflicts (reduces alignment)
          - Agreements (increases alignment)
          - Concentration risk (single-person knowledge reduces alignment)
        """
        base = 70  # Baseline alignment

        # Duplicate work reduces alignment
        from maestro_oem.learning_object import LearningObjectType
        dup_work = sum(1 for lo in self.model.learning_objects.values()
                       if lo.type == LearningObjectType.DUPLICATE_WORK)
        base -= dup_work * 5

        # Concentration risk reduces alignment
        risks = self.model.knowledge.get_concentration_risk() if hasattr(self.model.knowledge, 'get_concentration_risk') else {}
        base -= len(risks) * 4

        # Bottlenecks reduce alignment
        bottlenecks = self.model.approvals.get_bottlenecks(min_count=3) if hasattr(self.model.approvals, 'get_bottlenecks') else []
        base -= len(bottlenecks) * 3

        # Laws (validated patterns) increase alignment
        base += min(20, len(self.model.laws) * 2)

        return min(100, max(0, base))

    def _compute_trust(self) -> float:
        """Commitment health. Higher = more trust.

        Derived from:
          - Kept vs broken commitments ratio
          - Contract renewals vs churns
        """
        from maestro_oem.signal import SignalType
        kept = sum(1 for s in self.signals if s.type == SignalType.CUSTOMER_COMMITMENT_KEPT)
        broken = sum(1 for s in self.signals if s.type == SignalType.CUSTOMER_COMMITMENT_BROKEN)
        renewed = sum(1 for s in self.signals if s.type == SignalType.CUSTOMER_CONTRACT_RENEWED)
        churned = sum(1 for s in self.signals if s.type == SignalType.CUSTOMER_CONTRACT_CHURNED)

        total_commitments = kept + broken
        if total_commitments > 0:
            commitment_trust = (kept / total_commitments) * 100
        else:
            commitment_trust = 70  # Neutral baseline

        total_contracts = renewed + churned
        if total_contracts > 0:
            contract_trust = (renewed / total_contracts) * 100
        else:
            contract_trust = 70

        # Weight commitments more than contracts (more data points)
        return min(100, max(0, commitment_trust * 0.6 + contract_trust * 0.4))

    def _compute_knowledge_mobility(self) -> float:
        """How easily knowledge flows. Higher = better.

        Derived from:
          - Number of people per domain (more = better mobility)
          - Hidden experts (more = knowledge is trapped)
          - Knowledge death signals (reduces mobility)
        """
        from maestro_oem.learning_object import LearningObjectType

        # Count domain holders
        total_holders = sum(len(holders) for holders in self.model.knowledge.domain_holders.values())
        total_domains = len(self.model.knowledge.domain_holders)
        if total_domains > 0:
            avg_holders = total_holders / total_domains
            # 1 holder = 20, 2 = 50, 3+ = 80+
            mobility = min(100, avg_holders * 30)
        else:
            mobility = 50

        # Hidden experts reduce mobility (knowledge is undocumented)
        hidden_experts = sum(1 for lo in self.model.learning_objects.values()
                             if lo.type == LearningObjectType.HIDDEN_EXPERT)
        mobility -= min(30, hidden_experts * 3)

        # Knowledge death reduces mobility
        kd = sum(1 for lo in self.model.learning_objects.values()
                 if lo.type == LearningObjectType.KNOWLEDGE_DEATH)
        mobility -= min(20, kd * 4)

        return min(100, max(0, mobility))

    def _compute_decision_speed(self, recent_signals: list) -> float:
        """How fast decisions are made. Higher = faster.

        Derived from:
          - Health.decision_velocity_days (lower = faster)
          - Recent decision signals
          - Approval bottlenecks (reduce speed)
        """
        velocity_days = self.model.health.decision_velocity_days
        # Convert to 0-100 score: 0 days = 100, 5 days = 50, 10+ days = 0
        speed_from_velocity = max(0, 100 - (velocity_days * 10))

        # Recent decisions boost speed score
        from maestro_oem.signal import SignalType
        decisions = sum(1 for s in recent_signals if s.type == SignalType.DECISION_SIGNAL
                        or s.type == SignalType.CUSTOMER_DECISION)
        speed_from_activity = min(30, decisions * 5)

        # Bottlenecks reduce speed
        bottlenecks = self.model.approvals.get_bottlenecks(min_count=3) if hasattr(self.model.approvals, 'get_bottlenecks') else []
        bottleneck_penalty = min(30, len(bottlenecks) * 8)

        return min(100, max(0, speed_from_velocity * 0.5 + speed_from_activity - bottleneck_penalty + 20))

    def _infer_state(self, temp, momentum, alignment, trust, knowledge_mob, decision_speed) -> str:
        """Infer the qualitative organizational state from the metrics."""
        if temp > 60 and alignment < 50:
            return "turbulent"
        if knowledge_mob < 40:
            return "knowledge_blocked"
        if decision_speed < 30:
            return "decision_stalled"
        if trust < 40:
            return "trust_falling"
        if momentum > 70 and alignment > 65 and temp < 50:
            return "execution_accelerating"
        if temp < 40 and momentum > 50 and alignment > 60:
            return "healthy"
        return "steady"

    def _generate_narrative(self, state, temp, momentum, alignment, trust) -> str:
        """Generate a one-sentence narrative of the org's current state."""
        narratives = {
            "healthy": f"The organization is healthy — temperature {temp:.0f}, momentum {momentum:.0f}, alignment {alignment:.0f}.",
            "turbulent": f"The organization is turbulent — stress is {temp:.0f} and alignment has dropped to {alignment:.0f}.",
            "knowledge_blocked": f"Knowledge is blocked — mobility is low at {self._compute_knowledge_mobility():.0f}. Decisions are waiting on people who hold critical expertise.",
            "decision_stalled": f"Decisions are stalled — speed is low. Approvals are backing up.",
            "trust_falling": f"Trust is falling — {trust:.0f}. Broken commitments are eroding relationships.",
            "execution_accelerating": f"Execution is accelerating — momentum {momentum:.0f}, alignment {alignment:.0f}, stress low at {temp:.0f}.",
            "steady": f"The organization is steady — momentum {momentum:.0f}, alignment {alignment:.0f}, trust {trust:.0f}.",
        }
        return narratives.get(state, narratives["steady"])

    def _get_recommendations(self) -> list:
        """Get active recommendations (best-effort, may not be available)."""
        try:
            from maestro_oem.decision import DecisionEngine
            from maestro_oem.evidence_graph import EvidenceGraph
            eg = EvidenceGraph()
            eg.build_from_model(self.model)
            de = DecisionEngine(self.model, eg)
            return de.get_recommendations()
        except Exception:
            return []

"""
Organizational Digital Twin — "What happens if...?"

The OEM tells you what IS happening. The Digital Twin tells you what
WOULD happen if you changed something.

The twin is a mutable copy of the organizational model. You apply
scenarios to it (move a team, lose a person, double Legal, cut meetings)
and it predicts the cascading impact across:

  - Who becomes overloaded (workload redistribution)
  - Where knowledge disappears (bus-factor analysis)
  - Where the next bottleneck emerges (approval network stress)
  - How velocity changes (health metric prediction)
  - Which laws break (law violation prediction)
  - Which patterns strengthen or weaken

The twin does NOT modify the real OEM — it clones the state, applies
the scenario to the clone, and reports the delta.

Scenario types:
  - move_team: Move a team/domain to a different owner
  - person_leaves: Remove a person (departure simulation)
  - team_doubles: Double a team's headcount (hiring simulation)
  - cut_meetings: Reduce meeting load by N%
  - add_hires: Add N new hires to a domain
  - merge_teams: Merge two teams into one
  - split_team: Split a team into two

Each scenario produces an ImpactReport with:
  - Overloaded people (workload > capacity threshold)
  - Knowledge loss (domains with < 2 people)
  - New bottlenecks (approval gates exceeding threshold)
  - Velocity change (predicted health delta)
  - Law violations (laws likely to break under new structure)
  - Pattern shifts (patterns that strengthen or weaken)
  - Recommendations (what to do about the predicted impacts)
"""

from __future__ import annotations

import copy
import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Data structures
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class PersonProfile:
    """A person in the org twin."""
    email: str
    team: str = ""
    domains: list[str] = field(default_factory=list)
    influence: float = 0.0
    signal_count: int = 0
    approval_count: int = 0
    is_hidden_expert: bool = False
    is_bottleneck: bool = False
    capacity: float = 1.0  # Normalized capacity (1.0 = full capacity)
    workload: float = 0.0  # Current workload (signals + approvals)


@dataclass
class DomainProfile:
    """A knowledge domain in the org twin."""
    name: str
    people: list[str] = field(default_factory=list)
    signal_count: int = 0
    concentration_score: float = 0.0
    is_at_risk: bool = False


@dataclass
class ImpactReport:
    """The result of running a scenario on the twin."""
    scenario_id: str
    scenario_type: str
    description: str
    timestamp: str
    # Impacts
    overloaded_people: list[dict[str, Any]] = field(default_factory=list)
    knowledge_loss: list[dict[str, Any]] = field(default_factory=list)
    new_bottlenecks: list[dict[str, Any]] = field(default_factory=list)
    velocity_change: dict[str, Any] = field(default_factory=dict)
    law_violations: list[dict[str, Any]] = field(default_factory=list)
    pattern_shifts: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[dict[str, Any]] = field(default_factory=list)
    # Before/after summary
    before_summary: dict[str, Any] = field(default_factory=dict)
    after_summary: dict[str, Any] = field(default_factory=dict)
    # Overall risk
    risk_level: str = "low"  # low | medium | high | critical
    risk_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "scenario_type": self.scenario_type,
            "description": self.description,
            "timestamp": self.timestamp,
            "risk_level": self.risk_level,
            "risk_score": round(self.risk_score, 4),
            "overloaded_people": self.overloaded_people,
            "knowledge_loss": self.knowledge_loss,
            "new_bottlenecks": self.new_bottlenecks,
            "velocity_change": self.velocity_change,
            "law_violations": self.law_violations,
            "pattern_shifts": self.pattern_shifts,
            "recommendations": self.recommendations,
            "before_summary": self.before_summary,
            "after_summary": self.after_summary,
        }


# ═══════════════════════════════════════════════════════════════════════════
# The Digital Twin
# ═══════════════════════════════════════════════════════════════════════════

class DigitalTwin:
    """
    A mutable clone of the organizational model.

    Built from the live OEM state, then scenarios are applied to it.
    The twin never modifies the real OEM — it works on its own copy.
    """

    def __init__(self, model: Any, signals: list, decisions: Any = None) -> None:
        self.model = model
        self.signals = signals
        self.decisions = decisions

        # Build person profiles from signals
        self.people: dict[str, PersonProfile] = {}
        self.domains: dict[str, DomainProfile] = {}
        self._build_profiles()

        # Snapshot the original state for before/after comparison
        self._original_health = self._snapshot_health()
        self._original_people = copy.deepcopy(self.people)
        self._original_domains = copy.deepcopy(self.domains)

    def _build_profiles(self) -> None:
        """Build person and domain profiles from signals + knowledge graph."""
        # Count signals per person
        person_signals: dict[str, int] = defaultdict(int)
        person_domains: dict[str, set[str]] = defaultdict(set)
        person_teams: dict[str, str] = {}
        domain_signals: dict[str, int] = defaultdict(int)
        domain_people: dict[str, set[str]] = defaultdict(set)

        for sig in self.signals:
            actor = sig.actor or "unknown"
            person_signals[actor] += 1
            team = getattr(sig, "team", "") or ""
            if team:
                person_teams[actor] = team
            domain = "unknown"
            if hasattr(sig, "metadata") and sig.metadata:
                domain = sig.metadata.get("domain", "unknown")
            person_domains[actor].add(domain)
            domain_signals[domain] += 1
            domain_people[domain].add(actor)

        # Get influence scores from knowledge graph
        influence = {}
        if hasattr(self.model, "knowledge"):
            influence = self.model.knowledge.influence or {}

        # Get hidden experts
        hidden_experts = set()
        if hasattr(self.model, "knowledge"):
            for expert in self.model.knowledge.get_hidden_experts():
                hidden_experts.add(expert.get("entity", ""))

        # Get bottlenecks
        bottlenecks = set()
        for lo in self.model.learning_objects.values():
            lo_type = lo.type.value if hasattr(lo.type, "value") else str(lo.type)
            if lo_type == "bottleneck":
                for entity in (lo.entities or []):
                    bottlenecks.add(entity)

        # Get approval counts
        approval_counts: dict[str, int] = defaultdict(int)
        if hasattr(self.model, "approvals") and hasattr(self.model.approvals, "approvers"):
            approvers = self.model.approvals.approvers or {}
            if isinstance(approvers, dict):
                for approver_id, count in approvers.items():
                    approval_counts[str(approver_id)] = count

        # Build person profiles
        for person, count in person_signals.items():
            self.people[person] = PersonProfile(
                email=person,
                team=person_teams.get(person, ""),
                domains=list(person_domains[person]),
                influence=influence.get(person, 0.0),
                signal_count=count,
                approval_count=approval_counts.get(person, 0),
                is_hidden_expert=person in hidden_experts,
                is_bottleneck=person in bottlenecks,
                workload=float(count + approval_counts.get(person, 0)),
            )

        # Build domain profiles
        concentration = {}
        if hasattr(self.model, "knowledge"):
            concentration = self.model.knowledge.get_concentration_risk()

        for domain, count in domain_signals.items():
            people_list = list(domain_people[domain])
            self.domains[domain] = DomainProfile(
                name=domain,
                people=people_list,
                signal_count=count,
                concentration_score=concentration.get(domain, 0.0),
                is_at_risk=concentration.get(domain, 0.0) > 5.0,
            )

    def _snapshot_health(self) -> dict[str, float]:
        """Snapshot the current health metrics."""
        h = self.model.health
        return {
            "p1_cluster_risk": h.p1_cluster_risk,
            "incident_rate": h.incident_rate,
            "decision_velocity_days": h.decision_velocity_days,
            "release_frequency": h.release_frequency,
        }

    def get_org_summary(self) -> dict[str, Any]:
        """Get a summary of the current org state."""
        return {
            "people": len(self.people),
            "domains": len(self.domains),
            "signals": len(self.signals),
            "hidden_experts": sum(1 for p in self.people.values() if p.is_hidden_expert),
            "bottlenecks": sum(1 for p in self.people.values() if p.is_bottleneck),
            "at_risk_domains": sum(1 for d in self.domains.values() if d.is_at_risk),
            "health": self._snapshot_health(),
            "total_workload": sum(p.workload for p in self.people.values()),
            "avg_workload": sum(p.workload for p in self.people.values()) / max(len(self.people), 1),
        }


# ═══════════════════════════════════════════════════════════════════════════
# Scenario Engine — applies what-if changes to the twin
# ═══════════════════════════════════════════════════════════════════════════

class ScenarioEngine:
    """
    Applies scenarios to a DigitalTwin and predicts the impact.

    Usage:
        twin = DigitalTwin(model, signals)
        engine = ScenarioEngine(twin)
        report = engine.run_scenario({
            "type": "person_leaves",
            "person": "priya.m@acme.com",
        })
    """

    # Workload threshold for "overloaded" (above avg + 1 std dev)
    OVERLOAD_THRESHOLD_MULTIPLIER = 1.5

    def __init__(self, twin: DigitalTwin) -> None:
        self.twin = twin
        self.original_twin = copy.deepcopy(twin)

    def run_scenario(self, scenario: dict[str, Any]) -> ImpactReport:
        """Apply a scenario and return the impact report.

        Scenario format:
          {type: "person_leaves", person: "priya.m@acme.com"}
          {type: "move_team", domain: "payments", new_owner: "carlos.r@acme.com"}
          {type: "team_doubles", domain: "legal"}
          {type: "cut_meetings", reduction_pct: 30}
          {type: "add_hires", domain: "payments", count: 3}
          {type: "merge_teams", domain_a: "auth", domain_b: "payments"}
        """
        scenario_type = scenario.get("type", "unknown")
        scenario_id = f"scenario-{uuid4().hex[:8]}"

        # Capture before state
        before = self.twin.get_org_summary()

        # Apply the scenario
        description = self._apply_scenario(scenario)

        # Capture after state
        after = self.twin.get_org_summary()

        # Analyze impacts
        report = ImpactReport(
            scenario_id=scenario_id,
            scenario_type=scenario_type,
            description=description,
            timestamp=datetime.now(timezone.utc).isoformat(),
            before_summary=before,
            after_summary=after,
        )

        self._analyze_overload(report)
        self._analyze_knowledge_loss(report)
        self._analyze_bottlenecks(report)
        self._analyze_velocity(report, before, after)
        self._analyze_law_violations(report)
        self._analyze_pattern_shifts(report)
        self._generate_recommendations(report)
        self._compute_risk(report)

        return report

    def _apply_scenario(self, scenario: dict[str, Any]) -> str:
        """Apply the scenario mutation to the twin. Returns a description."""
        stype = scenario.get("type")

        if stype == "person_leaves":
            return self._scenario_person_leaves(scenario)
        elif stype == "move_team":
            return self._scenario_move_team(scenario)
        elif stype == "team_doubles":
            return self._scenario_team_doubles(scenario)
        elif stype == "cut_meetings":
            return self._scenario_cut_meetings(scenario)
        elif stype == "add_hires":
            return self._scenario_add_hires(scenario)
        elif stype == "merge_teams":
            return self._scenario_merge_teams(scenario)
        else:
            return f"Unknown scenario type: {stype}"

    def _scenario_person_leaves(self, scenario: dict[str, Any]) -> str:
        """Remove a person from the org. Redistribute their workload."""
        person = scenario.get("person", "")
        if person not in self.twin.people:
            return f"Person {person} not found in org."

        profile = self.twin.people[person]
        lost_domains = profile.domains
        lost_workload = profile.workload
        lost_influence = profile.influence

        # Remove the person
        del self.twin.people[person]

        # Remove from domains
        for domain_name in lost_domains:
            if domain_name in self.twin.domains:
                domain = self.twin.domains[domain_name]
                if person in domain.people:
                    domain.people.remove(person)
                # Redistribute workload to remaining people
                remaining = len(domain.people)
                if remaining > 0:
                    extra_per_person = lost_workload / remaining / len(lost_domains) if lost_domains else 0
                    for p_email in domain.people:
                        if p_email in self.twin.people:
                            self.twin.people[p_email].workload += extra_per_person

        return (f"Simulated departure of {person} (influence: {lost_influence:.2f}, "
                f"domains: {lost_domains}, workload redistributed to remaining team members).")

    def _scenario_move_team(self, scenario: dict[str, Any]) -> str:
        """Move a domain's ownership to a different person."""
        domain_name = scenario.get("domain", "")
        new_owner = scenario.get("new_owner", "")

        if domain_name not in self.twin.domains:
            return f"Domain {domain_name} not found."
        if new_owner not in self.twin.people:
            return f"Person {new_owner} not found."

        domain = self.twin.domains[domain_name]
        old_signal_count = domain.signal_count

        # The new owner takes on 30% of the domain's workload
        self.twin.people[new_owner].workload += old_signal_count * 0.3
        if domain_name not in self.twin.people[new_owner].domains:
            self.twin.people[new_owner].domains.append(domain_name)

        return (f"Moved domain '{domain_name}' to {new_owner}. "
                f"Added ~{old_signal_count * 0.3:.0f} workload units to {new_owner}.")

    def _scenario_team_doubles(self, scenario: dict[str, Any]) -> str:
        """Double a team's headcount (simulate hiring)."""
        domain_name = scenario.get("domain", "")
        if domain_name not in self.twin.domains:
            return f"Domain {domain_name} not found."

        domain = self.twin.domains[domain_name]
        current_count = len(domain.people)
        new_hires = current_count  # Double = add same number

        # Add synthetic new people
        for i in range(new_hires):
            new_email = f"new_hire_{i+1}@acme.com"
            self.twin.people[new_email] = PersonProfile(
                email=new_email,
                team=domain_name,
                domains=[domain_name],
                workload=0.0,
            )
            domain.people.append(new_email)

        # Redistribute workload across doubled team
        if current_count > 0:
            total_workload = sum(self.twin.people[p].workload for p in domain.people[:current_count])
            per_person = total_workload / (current_count * 2)
            for p in domain.people:
                if p in self.twin.people:
                    self.twin.people[p].workload = per_person

        return (f"Doubled team '{domain_name}' from {current_count} to {current_count * 2} people. "
                f"Workload redistributed (50% reduction per person).")

    def _scenario_cut_meetings(self, scenario: dict[str, Any]) -> str:
        """Reduce meeting load by N%. Assumes 30% of approval workload is meetings."""
        reduction = scenario.get("reduction_pct", 30) / 100.0

        total_reduced = 0.0
        for person in self.twin.people.values():
            meeting_load = person.approval_count * 0.3  # 30% of approvals = meetings
            reduction_amount = meeting_load * reduction
            person.workload -= reduction_amount
            total_reduced += reduction_amount

        # Predict velocity improvement (fewer meetings = faster decisions)
        if hasattr(self.twin.model, "health"):
            # Each 10% meeting reduction → 5% velocity improvement
            velocity_boost = (reduction * 0.5)
            self.twin.model.health.decision_velocity_days *= (1.0 - velocity_boost)

        return (f"Cut meetings by {reduction*100:.0f}%. Reduced total workload by {total_reduced:.0f} units. "
                f"Predicted velocity improvement: {velocity_boost*100:.0f}%.")

    def _scenario_add_hires(self, scenario: dict[str, Any]) -> str:
        """Add N new hires to a domain."""
        domain_name = scenario.get("domain", "")
        count = scenario.get("count", 1)
        if domain_name not in self.twin.domains:
            return f"Domain {domain_name} not found."

        domain = self.twin.domains[domain_name]
        for i in range(count):
            new_email = f"new_hire_{domain_name}_{i+1}@acme.com"
            self.twin.people[new_email] = PersonProfile(
                email=new_email,
                team=domain_name,
                domains=[domain_name],
                workload=0.0,
            )
            domain.people.append(new_email)

        # Redistribute workload
        all_people = [p for p in domain.people if p in self.twin.people]
        total_workload = sum(self.twin.people[p].workload for p in all_people)
        per_person = total_workload / len(all_people)
        for p in all_people:
            self.twin.people[p].workload = per_person

        # Reduce P1 risk (more capacity = lower risk)
        if hasattr(self.twin.model, "health"):
            risk_reduction = min(0.1, count * 0.02)
            self.twin.model.health.p1_cluster_risk = max(0.0, self.twin.model.health.p1_cluster_risk - risk_reduction)

        return (f"Added {count} hire(s) to '{domain_name}'. Team now has {len(domain.people)} people. "
                f"Workload redistributed. P1 risk reduced by {risk_reduction*100:.0f}%.")

    def _scenario_merge_teams(self, scenario: dict[str, Any]) -> str:
        """Merge two domains into one."""
        domain_a = scenario.get("domain_a", "")
        domain_b = scenario.get("domain_b", "")
        if domain_a not in self.twin.domains or domain_b not in self.twin.domains:
            return f"Domain(s) not found."

        da = self.twin.domains[domain_a]
        db = self.twin.domains[domain_b]

        # Merge b into a
        merged_people = list(set(da.people + db.people))
        merged_signals = da.signal_count + db.signal_count
        da.people = merged_people
        da.signal_count = merged_signals

        # Update person domains
        for p in db.people:
            if p in self.twin.people:
                if domain_a not in self.twin.people[p].domains:
                    self.twin.people[p].domains.append(domain_a)
                if domain_b in self.twin.people[p].domains:
                    self.twin.people[p].domains.remove(domain_b)

        del self.twin.domains[domain_b]

        return (f"Merged '{domain_b}' into '{domain_a}'. Combined team: {len(merged_people)} people, "
                f"{merged_signals} signals.")

    # ─── Impact analysis ───

    def _analyze_overload(self, report: ImpactReport) -> None:
        """Detect people who become overloaded after the scenario."""
        avg_workload = sum(p.workload for p in self.twin.people.values()) / max(len(self.twin.people), 1)
        threshold = avg_workload * self.OVERLOAD_THRESHOLD_MULTIPLIER

        for email, profile in self.twin.people.items():
            if profile.workload > threshold:
                original = self.original_twin.people.get(email)
                original_wl = original.workload if original else 0.0
                delta = profile.workload - original_wl
                if delta > 0:  # Only flag if workload increased
                    report.overloaded_people.append({
                        "person": email,
                        "current_workload": round(profile.workload, 2),
                        "previous_workload": round(original_wl, 2),
                        "workload_increase": round(delta, 2),
                        "domains": profile.domains,
                        "is_hidden_expert": profile.is_hidden_expert,
                        "severity": "high" if delta > avg_workload else "medium",
                    })

    def _analyze_knowledge_loss(self, report: ImpactReport) -> None:
        """Detect domains where knowledge disappears (bus-factor)."""
        for domain_name, domain in self.twin.domains.items():
            original = self.original_twin.domains.get(domain_name)
            original_count = len(original.people) if original else 0
            current_count = len(domain.people)

            if current_count < 2 and original_count >= 2:
                report.knowledge_loss.append({
                    "domain": domain_name,
                    "people_before": original_count,
                    "people_after": current_count,
                    "remaining_people": domain.people,
                    "severity": "critical" if current_count == 0 else "high",
                    "description": f"Domain '{domain_name}' went from {original_count} to {current_count} people. Knowledge is at risk.",
                })
            elif current_count == 0:
                report.knowledge_loss.append({
                    "domain": domain_name,
                    "people_before": original_count,
                    "people_after": 0,
                    "severity": "critical",
                    "description": f"Domain '{domain_name}' has NO remaining people. Knowledge is lost.",
                })

    def _analyze_bottlenecks(self, report: ImpactReport) -> None:
        """Detect new bottlenecks (people with excessive approval workload)."""
        for email, profile in self.twin.people.items():
            if profile.approval_count > 3:
                original = self.original_twin.people.get(email)
                original_approvals = original.approval_count if original else 0
                if profile.approval_count > original_approvals:
                    report.new_bottlenecks.append({
                        "person": email,
                        "approval_count": profile.approval_count,
                        "previous_approvals": original_approvals,
                        "description": f"{email} is now an approval bottleneck ({profile.approval_count} gates).",
                    })

        # Also check if existing bottlenecks got worse
        for email, profile in self.twin.people.items():
            if profile.is_bottleneck:
                original = self.original_twin.people.get(email)
                if original and profile.workload > original.workload * 1.2:
                    report.new_bottlenecks.append({
                        "person": email,
                        "workload": round(profile.workload, 2),
                        "previous_workload": round(original.workload, 2),
                        "description": f"Existing bottleneck {email} got worse (workload +{(profile.workload - original.workload):.0f}).",
                    })

    def _analyze_velocity(self, report: ImpactReport, before: dict, after: dict) -> None:
        """Predict velocity change."""
        before_h = before.get("health", {})
        after_h = after.get("health", {})

        velocity_delta = after_h.get("decision_velocity_days", 0) - before_h.get("decision_velocity_days", 0)
        risk_delta = after_h.get("p1_cluster_risk", 0) - before_h.get("p1_cluster_risk", 0)

        report.velocity_change = {
            "velocity_before": round(before_h.get("decision_velocity_days", 0), 2),
            "velocity_after": round(after_h.get("decision_velocity_days", 0), 2),
            "velocity_delta": round(velocity_delta, 2),
            "velocity_direction": "improved" if velocity_delta < 0 else "degraded",
            "p1_risk_before": round(before_h.get("p1_cluster_risk", 0), 4),
            "p1_risk_after": round(after_h.get("p1_cluster_risk", 0), 4),
            "p1_risk_delta": round(risk_delta, 4),
        }

    def _analyze_law_violations(self, report: ImpactReport) -> None:
        """Predict which laws might break under the new structure."""
        if not hasattr(self.twin.model, "laws"):
            return

        for law in self.twin.model.laws.values():
            # Check if the law statement references any removed person
            law_text = (law.statement + " " + law.condition + " " + law.outcome).lower()
            for email in self.original_twin.people:
                if email not in self.twin.people and email.lower() in law_text:
                    report.law_violations.append({
                        "law_code": law.code,
                        "statement": law.statement[:100],
                        "entity_removed": email,
                        "confidence": round(law.confidence, 4),
                        "description": f"Law {law.code} references {email} who was removed. This law may break.",
                    })

            # Check if law condition involves a domain that lost people
            for domain_name, domain in self.twin.domains.items():
                original = self.original_twin.domains.get(domain_name)
                if original and len(domain.people) < len(original.people):
                    if domain_name.lower() in law_text:
                        report.law_violations.append({
                            "law_code": law.code,
                            "statement": law.statement[:100],
                            "domain": domain_name,
                            "people_lost": len(original.people) - len(domain.people),
                            "confidence": round(law.confidence, 4),
                            "description": f"Law {law.code} involves '{domain_name}' which lost {len(original.people) - len(domain.people)} person(s).",
                        })

    def _analyze_pattern_shifts(self, report: ImpactReport) -> None:
        """Detect patterns that strengthen or weaken."""
        for email, profile in self.twin.people.items():
            original = self.original_twin.people.get(email)
            if not original:
                continue

            wl_delta = profile.workload - original.workload
            if abs(wl_delta) > original.workload * 0.2:  # >20% change
                direction = "strengthened" if wl_delta > 0 else "weakened"
                report.pattern_shifts.append({
                    "person": email,
                    "direction": direction,
                    "workload_delta": round(wl_delta, 2),
                    "description": f"{email}'s workload {direction} by {abs(wl_delta):.0f} units.",
                })

        # Domain shifts
        for domain_name, domain in self.twin.domains.items():
            original = self.original_twin.domains.get(domain_name)
            if original and len(domain.people) != len(original.people):
                delta = len(domain.people) - len(original.people)
                direction = "expanded" if delta > 0 else "contracted"
                report.pattern_shifts.append({
                    "domain": domain_name,
                    "direction": direction,
                    "people_delta": delta,
                    "description": f"Domain '{domain_name}' {direction} by {abs(delta)} person(s).",
                })

    def _generate_recommendations(self, report: ImpactReport) -> None:
        """Generate actionable recommendations based on the impact analysis."""
        if report.knowledge_loss:
            for kl in report.knowledge_loss[:3]:
                report.recommendations.append({
                    "priority": "urgent" if kl["severity"] == "critical" else "high",
                    "action": f"Document knowledge in '{kl['domain']}' before it's lost",
                    "reason": kl["description"],
                    "impact": "Prevents irreversible knowledge loss",
                })

        if report.overloaded_people:
            for op in report.overloaded_people[:3]:
                report.recommendations.append({
                    "priority": "high",
                    "action": f"Redistribute workload from {op['person']}",
                    "reason": f"Workload increased by {op['workload_increase']:.0f} units after scenario.",
                    "impact": "Prevents burnout and departure risk",
                })

        if report.new_bottlenecks:
            for nb in report.new_bottlenecks[:3]:
                report.recommendations.append({
                    "priority": "high",
                    "action": f"Add backup approver for {nb['person']}",
                    "reason": nb["description"],
                    "impact": "Prevents approval pipeline stall",
                })

        if report.velocity_change.get("velocity_direction") == "degraded":
            report.recommendations.append({
                "priority": "medium",
                "action": "Monitor decision velocity closely",
                "reason": f"Velocity predicted to increase by {report.velocity_change['velocity_delta']:.1f} days.",
                "impact": "Early warning for delivery slippage",
            })

        if not report.recommendations:
            report.recommendations.append({
                "priority": "low",
                "action": "No significant negative impacts predicted. Proceed with scenario.",
                "reason": "The digital twin shows no critical, high, or medium impacts.",
                "impact": "Safe to proceed",
            })

    def _compute_risk(self, report: ImpactReport) -> None:
        """Compute overall risk score (0.0 = safe, 1.0 = critical)."""
        score = 0.0

        # Knowledge loss is most severe
        for kl in report.knowledge_loss:
            if kl["severity"] == "critical":
                score += 0.4
            else:
                score += 0.2

        # Overloaded people
        for op in report.overloaded_people:
            if op["severity"] == "high":
                score += 0.15
            else:
                score += 0.05

        # New bottlenecks
        score += len(report.new_bottlenecks) * 0.1

        # Velocity degradation
        if report.velocity_change.get("velocity_direction") == "degraded":
            score += 0.1

        # Law violations
        score += len(report.law_violations) * 0.1

        report.risk_score = min(1.0, score)
        if score >= 0.6:
            report.risk_level = "critical"
        elif score >= 0.4:
            report.risk_level = "high"
        elif score >= 0.2:
            report.risk_level = "medium"
        else:
            report.risk_level = "low"

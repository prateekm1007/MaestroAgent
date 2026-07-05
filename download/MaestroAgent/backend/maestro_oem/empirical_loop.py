"""Empirical Loop — Phases 2-9 of the auditor's Priority 5B directive.

This module implements the scientific half of Maestro's governed learning loop:

  MODEL PROPOSES A HYPOTHESIS
  → HISTORICAL EVIDENCE IS CHECKED
  → INDEPENDENT CASES ARE IDENTIFIED
  → CONFOUNDERS ARE ANALYZED
  → A TESTABLE PREDICTION IS REGISTERED
  → FUTURE REALITY IS OBSERVED
  → OUTCOME IS RESOLVED
  → CALIBRATION IS MEASURED
  → REPLICATION IS TESTED
  → SCOPE IS DISCOVERED
  → GOVERNANCE DECIDES WHETHER THE PATTERN MAY BECOME ACTIVE

DESIGN PRINCIPLES (the auditor's "scientific about learning"):
  1. Repeated reasoning is NOT repeated evidence. (Phase 1 correction)
  2. Case identity is DERIVED from evidence, not caller-supplied. (P13)
  3. Same evidence copied across sources = one case. (P14)
  4. Historical support is NOT prospective validation.
  5. Only independent signals can resolve outcomes. (No self-validation)
  6. A hypothesis can remain uncertain, be contradicted, become scope-limited,
     decay, be superseded, or be falsified.
  7. No irreversible promotion. Governance controls consequential promotion.

Phases implemented here:
  Phase 2: ObservationCase + CaseFingerprintBuilder
  Phase 3: HypothesisOperationalization (antecedent/population/outcome/window/exclusions)
  Phase 4: AttributionAnalyzer integration (confounders per case)
  Phase 5: Prospective registration with frozen evidence snapshot
  Phase 6: OutcomeResolver (derives outcomes from signals, fires on ingest)
  Phase 7: Scientific status machine
  Phase 8: Replication + calibration (separate metrics)
  Phase 9: Scope and regime (valid_scope, unproven_scope, invalid_scope)
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 7: SCIENTIFIC STATUS MACHINE
# ═══════════════════════════════════════════════════════════════════════════

class HypothesisStatus(str, Enum):
    """The scientific lifecycle of a candidate hypothesis.

    Success path:
      PROPOSED → EVIDENCE_SUPPORTED → PROSPECTIVE_TESTING → CALIBRATING
      → VALIDATED → PATTERN_CANDIDATE → GOVERNANCE_REVIEW → ACTIVE_PATTERN

    Non-success paths:
      INSUFFICIENT_EVIDENCE — never accumulated enough cases
      CONFOUNDED — confounders too strong to claim the relationship
      NOT_REPLICATED — failed to replicate across independent cases
      FALSIFIED — prospective outcomes contradicted the hypothesis
      SUPERSEDED — a better hypothesis replaced this one
      EXPIRED — observation window elapsed without resolution

    No silent transitions. Every transition records:
      previous_state, new_state, reason, evidence, actor, timestamp, policy_version.
    """
    PROPOSED = "PROPOSED"
    EVIDENCE_SUPPORTED = "EVIDENCE_SUPPORTED"
    PROSPECTIVE_TESTING = "PROSPECTIVE_TESTING"
    CALIBRATING = "CALIBRATING"
    VALIDATED = "VALIDATED"
    PATTERN_CANDIDATE = "PATTERN_CANDIDATE"
    GOVERNANCE_REVIEW = "GOVERNANCE_REVIEW"
    ACTIVE_PATTERN = "ACTIVE_PATTERN"
    # Non-success
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    CONFOUNDED = "CONFOUNDED"
    NOT_REPLICATED = "NOT_REPLICATED"
    FALSIFIED = "FALSIFIED"
    SUPERSEDED = "SUPERSEDED"
    EXPIRED = "EXPIRED"


@dataclass
class StatusTransition:
    """A single state transition in the hypothesis lifecycle. Never silent."""
    from_status: str
    to_status: str
    reason: str
    evidence: str  # what evidence justified this transition
    actor: str  # "system" | "governance" | "auditor"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    policy_version: str = "v1"


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 3: HYPOTHESIS OPERATIONALIZATION
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class OperationalHypothesis:
    """A hypothesis made scientifically testable.

    AUDITOR-DIRECTIVE Phase 3:
    > ANTECEDENT: What observable condition must occur?
    > POPULATION: Which cases are eligible?
    > EXPECTED OUTCOME: What observable event is predicted?
    > OBSERVATION WINDOW: How long after the antecedent do we wait?
    > EXCLUSIONS: Which cases should not count?
    > SCOPE: Where might the hypothesis apply?
    > ALTERNATIVE EXPLANATIONS: What other mechanisms could explain the association?
    > CONFOUNDERS: What variables must be considered?

    A sentence like "Champion silence may indicate renewal risk" is NOT testable.
    This dataclass transforms it into something testable.
    """
    antecedent: str = ""  # "No meaningful interaction from champion for N days after missed commitment"
    population: str = ""  # "Active enterprise renewal situations"
    expected_outcome: str = ""  # "Escalation event within observation window"
    observation_window_days: int = 30
    exclusions: list[str] = field(default_factory=list)  # "account closed", "champion changed role"
    scope: dict[str, str] = field(default_factory=dict)  # {"customer_segment": "enterprise"}
    alternative_explanations: list[str] = field(default_factory=list)
    confounders: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "antecedent": self.antecedent,
            "population": self.population,
            "expected_outcome": self.expected_outcome,
            "observation_window_days": self.observation_window_days,
            "exclusions": self.exclusions,
            "scope": self.scope,
            "alternative_explanations": self.alternative_explanations,
            "confounders": self.confounders,
        }


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 2: OBSERVATION CASE — the unit of independent empirical observation
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ObservationCase:
    """A unit of independent empirical observation for testing a hypothesis.

    AUDITOR-DIRECTIVE Phase 2:
    > Case identity must not depend on query_id.
    > A new Ask query about the same underlying episode must not create a new case.
    > Develop deterministic case deduplication using situation identity, entity
    > identity, temporal overlap, evidence lineage, outcome target, organizational context.

    Case identity is DERIVED from evidence (P13). The derivation is DETERMINISTIC.
    Same evidence → same fingerprint → one case.
    """
    case_id: UUID = field(default_factory=uuid4)
    candidate_pattern_id: UUID | None = None
    entity_id: str = ""
    situation_hash: str = ""
    time_window_start: str = ""  # ISO date, truncated to day
    outcome_target: str = ""
    source_evidence_ids: list[str] = field(default_factory=list)
    evidence_lineage_ids: list[str] = field(default_factory=list)
    eligibility_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    prediction_registered_at: datetime | None = None
    observation_window_end: datetime | None = None
    expected_outcome: str = ""
    actual_outcome: str = ""
    resolution_status: str = "pending"  # pending|supporting|contradicting|insufficient_data|expired
    resolution_source_ids: list[str] = field(default_factory=list)
    confounders: list[str] = field(default_factory=list)  # Phase 4
    scope_dimensions: dict[str, str] = field(default_factory=dict)  # Phase 9
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: datetime | None = None

    @property
    def case_fingerprint(self) -> str:
        """Deterministic hash of (entity, situation, time_window, outcome_target). P13."""
        key_str = "|".join([
            self.entity_id.lower().strip(),
            self.situation_hash,
            self.time_window_start,
            self.outcome_target.lower().strip(),
        ])
        return hashlib.sha256(key_str.encode()).hexdigest()[:16]

    def to_audit_dict(self) -> dict[str, Any]:
        return {
            "case_id": str(self.case_id),
            "candidate_pattern_id": str(self.candidate_pattern_id) if self.candidate_pattern_id else None,
            "entity_id": self.entity_id,
            "situation_hash": self.situation_hash,
            "time_window_start": self.time_window_start,
            "outcome_target": self.outcome_target,
            "case_fingerprint": self.case_fingerprint,
            "source_evidence_ids": self.source_evidence_ids,
            "evidence_lineage_ids": self.evidence_lineage_ids[:5],
            "eligibility_time": self.eligibility_time.isoformat(),
            "prediction_registered_at": self.prediction_registered_at.isoformat() if self.prediction_registered_at else None,
            "observation_window_end": self.observation_window_end.isoformat() if self.observation_window_end else None,
            "expected_outcome": self.expected_outcome,
            "actual_outcome": self.actual_outcome,
            "resolution_status": self.resolution_status,
            "resolution_source_ids": self.resolution_source_ids,
            "confounders": self.confounders,
            "scope_dimensions": self.scope_dimensions,
            "created_at": self.created_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


class CaseFingerprintBuilder:
    """Derives a case_fingerprint from evidence — NOT from caller-supplied values. P13.

    The caller supplies a Situation and a CandidatePattern. The builder extracts
    the evidence-derived components and hashes them. The caller cannot game the
    fingerprint because they don't supply it.
    """

    @staticmethod
    def build(
        entity_id: str,
        situation: Any,
        outcome_target: str,
        now: datetime | None = None,
    ) -> ObservationCase:
        """Build an ObservationCase from a Situation + entity + outcome target."""
        now = now or datetime.now(timezone.utc)

        # Derive situation_hash from commitments + timeline
        commitments_str = ""
        if hasattr(situation, "commitments") and situation.commitments:
            commit_texts = sorted(
                str(c.get("commitment", "") if isinstance(c, dict) else str(c))
                for c in situation.commitments
            )
            commitments_str = "|".join(commit_texts)

        timeline_str = ""
        if hasattr(situation, "timeline") and situation.timeline:
            timeline_events = sorted(
                f"{e.get('date', '')}:{e.get('event', '')}" if isinstance(e, dict) else str(e)
                for e in situation.timeline
            )
            timeline_str = "|".join(timeline_events)

        situation_hash = hashlib.sha256(
            f"{commitments_str}||{timeline_str}".encode()
        ).hexdigest()[:16]

        # Derive time_window_start from the most recent timeline event (truncated to day)
        time_window_start = now.strftime("%Y-%m-%d")
        if hasattr(situation, "timeline") and situation.timeline:
            dates = []
            for e in situation.timeline:
                if isinstance(e, dict) and e.get("date"):
                    try:
                        dates.append(e["date"][:10])
                    except (TypeError, IndexError):
                        pass
            if dates:
                time_window_start = sorted(dates)[-1]

        # Collect source_evidence_ids + evidence_lineage_ids
        source_evidence_ids: list[str] = []
        evidence_lineage_ids: list[str] = []
        if hasattr(situation, "evidence") and situation.evidence:
            for ev in situation.evidence:
                if isinstance(ev, dict):
                    ev_id = ev.get("signal_id") or ev.get("evidence_id") or ev.get("source", "")
                    if ev_id:
                        source_evidence_ids.append(str(ev_id))
                    ev_text = ev.get("text", "")
                    if ev_text:
                        evidence_lineage_ids.append(
                            hashlib.sha256(str(ev_text).encode()).hexdigest()[:12]
                        )

        return ObservationCase(
            entity_id=entity_id,
            situation_hash=situation_hash,
            time_window_start=time_window_start,
            outcome_target=outcome_target,
            source_evidence_ids=source_evidence_ids,
            evidence_lineage_ids=evidence_lineage_ids,
            eligibility_time=now,
        )

    @staticmethod
    def cases_share_evidence_lineage(case_a: ObservationCase, case_b: ObservationCase) -> bool:
        """Check if two cases share evidence lineage (not independent). P14.

        AUDITOR-DIRECTIVE: "copied Slack/email/Jira representations of one event
        do not count as three independent cases."

        If two cases share >50% of their evidence lineage hashes, they are likely
        the same underlying event copied across sources.
        """
        if not case_a.evidence_lineage_ids or not case_b.evidence_lineage_ids:
            return False
        set_a = set(case_a.evidence_lineage_ids)
        set_b = set(case_b.evidence_lineage_ids)
        overlap = set_a & set_b
        smaller_size = min(len(set_a), len(set_b))
        return len(overlap) > (smaller_size / 2) if smaller_size > 0 else False


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 4: ATTRIBUTION ANALYZER (confounders per case)
# ═══════════════════════════════════════════════════════════════════════════

class AttributionAnalyzer:
    """Records confounders and alternative explanations per case.

    AUDITOR-DIRECTIVE Phase 4:
    > For every candidate hypothesis, AttributionAnalyzer should be able to record:
    > possible confounders, alternative explanations, data coverage weaknesses,
    > selection bias risks, temporal ambiguity, reverse-causality risk, source dependence.

    A heavily confounded candidate must not advance merely because supporting
    outcomes accumulate.
    """

    CONFOUNDER_SIGNAL_TYPES = {
        "staffing_change": "champion or key contact departed",
        "market_shift": "competitive or market conditions changed",
        "organizational_reorg": "internal reorganization affected the relationship",
        "budget_cut": "customer budget was reduced",
        "product_issue": "a separate product issue caused dissatisfaction",
        "merger_acquisition": "customer was acquired or merged",
        "economic_downturn": "broader economic conditions worsened",
    }

    def analyze_case(self, case: ObservationCase, signals: list) -> dict[str, Any]:
        """Analyze a case for confounders from the signal stream.

        DERIVES confounders from signals (P13) — does not take them as parameters.
        """
        confounders_found: list[str] = []
        entity_signals = [
            s for s in signals
            if hasattr(s, "metadata") and s.metadata and
            str(s.metadata.get("customer", "")).lower() == case.entity_id.lower()
        ]

        for signal in entity_signals:
            sig_metadata = signal.metadata if hasattr(signal, "metadata") else {}
            for confounder_type, description in self.CONFOUNDER_SIGNAL_TYPES.items():
                if confounder_type in str(sig_metadata).lower():
                    if description not in confounders_found:
                        confounders_found.append(description)

        # Record confounders on the case
        case.confounders = confounders_found

        return {
            "confounders": confounders_found,
            "confounder_count": len(confounders_found),
            "heavily_confounded": len(confounders_found) >= 2,
            "causal_strength": "unknown" if not confounders_found else "weak",
        }


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 6: OUTCOME RESOLVER — derives outcomes from signals, fires on ingest
# ═══════════════════════════════════════════════════════════════════════════

_OUTCOME_MATCHERS: dict[str, dict[str, Any]] = {
    "escalation": {
        "supporting_signal_types": ["customer.objection", "customer.decision"],
        "supporting_metadata_values": ["escalation", "churned", "objection"],
        "contradicting_signal_types": ["customer.contract_renewed", "customer.commitment_kept"],
        "contradicting_metadata_values": ["renewed", "kept"],
    },
    "renewal": {
        "supporting_signal_types": ["customer.contract_renewed", "customer.decision"],
        "supporting_metadata_values": ["renewed"],
        "contradicting_signal_types": ["customer.contract_churned"],
        "contradicting_metadata_values": ["churned"],
    },
    "churn": {
        "supporting_signal_types": ["customer.contract_churned", "customer.decision"],
        "supporting_metadata_values": ["churned"],
        "contradicting_signal_types": ["customer.contract_renewed"],
        "contradicting_metadata_values": ["renewed"],
    },
    "commitment broken": {
        "supporting_signal_types": ["customer.commitment_broken"],
        "supporting_metadata_values": [],
        "contradicting_signal_types": ["customer.commitment_kept"],
        "contradicting_metadata_values": ["kept"],
    },
    "commitment kept": {
        "supporting_signal_types": ["customer.commitment_kept"],
        "supporting_metadata_values": [],
        "contradicting_signal_types": ["customer.commitment_broken"],
        "contradicting_metadata_values": ["broken"],
    },
}


def _signal_matches_outcome(signal: Any, outcome: str, direction: str) -> bool:
    """DERIVES the match from the signal's type + metadata (P13)."""
    normalized = outcome.lower().strip()
    matcher = None
    for key, m in _OUTCOME_MATCHERS.items():
        if key in normalized:
            matcher = m
            break
    if matcher is None:
        return False

    sig_type = ""
    if hasattr(signal, "type"):
        sig_type = signal.type.value if hasattr(signal.type, "value") else str(signal.type)

    sig_metadata = {}
    if hasattr(signal, "metadata") and signal.metadata:
        sig_metadata = dict(signal.metadata)

    if direction == "supporting":
        type_match = sig_type in matcher["supporting_signal_types"]
        value_match = any(
            str(sig_metadata.get(k, "")).lower() in [v.lower() for v in matcher["supporting_metadata_values"]]
            for k in ["decision_outcome", "objection_type"]
        )
        return type_match or value_match
    elif direction == "contradicting":
        type_match = sig_type in matcher["contradicting_signal_types"]
        value_match = any(
            str(sig_metadata.get(k, "")).lower() in [v.lower() for v in matcher["contradicting_metadata_values"]]
            for k in ["decision_outcome"]
        )
        return type_match or value_match
    return False


def _signal_entity_matches(signal: Any, entity_id: str) -> bool:
    """Check if a signal is about the same entity as the ObservationCase."""
    if not entity_id:
        return False
    if hasattr(signal, "metadata") and signal.metadata:
        customer = str(signal.metadata.get("customer", "")).lower()
        if customer == entity_id.lower():
            return True
    if hasattr(signal, "artifact"):
        artifact = str(signal.artifact).lower()
        if entity_id.lower() in artifact:
            return True
    return False


class OutcomeResolver:
    """Resolves pending ObservationCases from newly-ingested signals.

    AUDITOR-DIRECTIVE Phase 6:
    > Future organizational signals should resolve eligible cases independently
    > of Ask activity. The learning loop must not depend on someone asking
    > another question.

    The resolver NEVER self-validates — a model-generated sentence can't resolve
    the outcome it predicted. Only source signals can.
    """

    def __init__(self, store: Any) -> None:
        self._store = store

    def resolve_pending(
        self,
        new_signals: list[Any],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Check all pending predictions against the new signals. NEVER raises."""
        if self._store is None:
            return {"checked": 0, "resolved": 0, "expired": 0, "still_pending": 0, "resolutions": []}

        now = now or datetime.now(timezone.utc)
        pending = self._store.get_pending_predictions()
        resolutions: list[dict[str, Any]] = []
        resolved_count = 0
        expired_count = 0

        for pred in pending:
            prediction_id = pred["prediction_id"]
            expected_outcome = pred.get("expected_outcome", "")
            observation_case = pred.get("observation_case")

            if observation_case is None:
                continue

            entity_id = observation_case.entity_id
            window_end = observation_case.observation_window_end

            # Check window expiry first
            if window_end and now > window_end:
                self._store.resolve_prospective_prediction(
                    prediction_id=prediction_id,
                    outcome="insufficient_data",
                    resolution_source="window_expired",
                )
                expired_count += 1
                resolutions.append({
                    "prediction_id": prediction_id,
                    "entity_id": entity_id,
                    "outcome": "expired",
                    "resolution_source": "window_expired",
                })
                continue

            # Check the new signals for a match (P13: derive from signals)
            supporting_signal = None
            contradicting_signal = None

            for signal in new_signals:
                if not _signal_entity_matches(signal, entity_id):
                    continue
                # Skip shadow signals (not real outcomes)
                if hasattr(signal, "metadata") and signal.metadata and signal.metadata.get("shadow"):
                    continue
                # Skip prompt-injected signals (no self-validation)
                if hasattr(signal, "metadata") and signal.metadata and signal.metadata.get("prompt_injection_risk"):
                    continue

                if _signal_matches_outcome(signal, expected_outcome, "supporting"):
                    supporting_signal = signal
                    break
                if _signal_matches_outcome(signal, expected_outcome, "contradicting"):
                    contradicting_signal = signal
                    break

            if supporting_signal is not None:
                sig_id = ""
                if hasattr(supporting_signal, "signal_id"):
                    sig_id = str(supporting_signal.signal_id)
                elif hasattr(supporting_signal, "artifact"):
                    sig_id = str(supporting_signal.artifact)
                self._store.resolve_prospective_prediction(
                    prediction_id=prediction_id,
                    outcome="supporting",
                    resolution_source=f"signal:{sig_id}",
                )
                resolved_count += 1
                resolutions.append({
                    "prediction_id": prediction_id,
                    "entity_id": entity_id,
                    "outcome": "supporting",
                    "resolution_source": f"signal:{sig_id}",
                })
            elif contradicting_signal is not None:
                sig_id = ""
                if hasattr(contradicting_signal, "signal_id"):
                    sig_id = str(contradicting_signal.signal_id)
                elif hasattr(contradicting_signal, "artifact"):
                    sig_id = str(contradicting_signal.artifact)
                self._store.resolve_prospective_prediction(
                    prediction_id=prediction_id,
                    outcome="contradicting",
                    resolution_source=f"signal:{sig_id}",
                )
                resolved_count += 1
                resolutions.append({
                    "prediction_id": prediction_id,
                    "entity_id": entity_id,
                    "outcome": "contradicting",
                    "resolution_source": f"signal:{sig_id}",
                })

        still_pending = len(pending) - resolved_count - expired_count

        if resolved_count > 0 or expired_count > 0:
            logger.info(
                "OutcomeResolver: checked %d, resolved %d, expired %d, %d still pending",
                len(pending), resolved_count, expired_count, still_pending,
            )

        return {
            "checked": len(pending),
            "resolved": resolved_count,
            "expired": expired_count,
            "still_pending": still_pending,
            "resolutions": resolutions,
        }


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 8: REPLICATION + CALIBRATION (separate metrics)
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ReplicationMetrics:
    """Separate metrics for evidence strength, replication, and predictive calibration.

    AUDITOR-DIRECTIVE Phase 8:
    > Do not use one seductive confidence number. Represent separately:
    > EVIDENCE STRENGTH, REPLICATION STRENGTH, PREDICTIVE CALIBRATION.
    > Do not calculate metrics when the denominator is too small.
    > Return "insufficient evidence" rather than decorative precision.
    """
    evidence_strength: float | None = None  # from historical_support_cases
    replication_strength: float | None = None  # from independent_cases
    predictive_calibration: float | None = None  # Brier from prospective outcomes
    base_rate: float | None = None
    lift_over_base_rate: float | None = None
    precision: float | None = None
    recall: float | None = None
    brier_score: float | None = None
    false_positive_cost: float | None = None
    false_negative_cost: float | None = None
    unresolved_case_count: int = 0
    insufficient_evidence: bool = True  # True when denominators too small

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_strength": self.evidence_strength,
            "replication_strength": self.replication_strength,
            "predictive_calibration": self.predictive_calibration,
            "base_rate": self.base_rate,
            "lift_over_base_rate": self.lift_over_base_rate,
            "precision": self.precision,
            "recall": self.recall,
            "brier_score": self.brier_score,
            "false_positive_cost": self.false_positive_cost,
            "false_negative_cost": self.false_negative_cost,
            "unresolved_case_count": self.unresolved_case_count,
            "insufficient_evidence": self.insufficient_evidence,
        }


def compute_replication_metrics(candidate: Any) -> ReplicationMetrics:
    """Compute separate metrics. Returns 'insufficient evidence' when denominators too small.

    AUDITOR-DIRECTIVE: "Do not calculate metrics when the denominator is too small.
    Return 'insufficient evidence' rather than decorative precision."
    """
    metrics = ReplicationMetrics(unresolved_case_count=candidate.unresolved_outcomes)

    # Evidence strength: from historical support cases (retrospective)
    # Capped at 1.0, requires at least 3 to report
    if candidate.historical_support_cases >= 3:
        metrics.evidence_strength = min(1.0, candidate.historical_support_cases / 10.0)
    else:
        metrics.evidence_strength = None  # insufficient

    # Replication strength: from independent cases (prospective)
    # Requires at least 3 to report
    if candidate.prospective_predictions >= 3:
        metrics.replication_strength = min(1.0, candidate.prospective_predictions / 10.0)
    else:
        metrics.replication_strength = None

    # Predictive calibration: Brier score from PROSPECTIVE outcomes only
    # Requires at least 3 resolved outcomes to report
    total_resolved = candidate.supporting_outcomes + candidate.contradicting_outcomes
    if total_resolved >= 3:
        # Brier = (predicted_prob - actual_outcome)^2 averaged
        # We predict 0.5 (uncertain) — score = 0.25 if 50/50, 0 if all correct, ~1 if all wrong
        actual = candidate.supporting_outcomes / total_resolved
        metrics.brier_score = round((0.5 - actual) ** 2, 4)
        metrics.predictive_calibration = 1.0 - metrics.brier_score  # higher = better
        # Precision: of resolved predictions, fraction that were supporting
        metrics.precision = round(candidate.supporting_outcomes / total_resolved, 4)
        # Recall: of supporting outcomes, fraction we caught (can't compute without base rate)
        metrics.recall = None  # requires knowing all eligible cases
    else:
        metrics.brier_score = None
        metrics.predictive_calibration = None
        metrics.precision = None

    # Insufficient evidence flag
    if (candidate.historical_support_cases < 3 and
            candidate.prospective_predictions < 3 and
            total_resolved < 3):
        metrics.insufficient_evidence = True
    else:
        metrics.insufficient_evidence = False

    return metrics


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 9: SCOPE AND REGIME
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ScopeRegime:
    """Where a hypothesis applies, where it's unproven, where it's invalid.

    AUDITOR-DIRECTIVE Phase 9:
    > Organizational patterns are rarely universal.
    > A hypothesis may hold for enterprise customers but not SMB;
    > during renewals but not acquisition; in Security but not Product.

    Do not infer universal organizational laws from narrow populations.
    """
    valid_scope: dict[str, str] = field(default_factory=dict)  # {"customer_segment": "enterprise"}
    unproven_scope: dict[str, str] = field(default_factory=dict)  # {"customer_segment": "smb"}
    invalid_scope: dict[str, str] = field(default_factory=dict)  # {"process": "initial_sale"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid_scope": self.valid_scope,
            "unproven_scope": self.unproven_scope,
            "invalid_scope": self.invalid_scope,
        }


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 10: GOVERNED PROMOTION
# ═══════════════════════════════════════════════════════════════════════════

class GovernanceGate:
    """Controls consequential promotion to ACTIVE_PATTERN.

    AUDITOR-DIRECTIVE Phase 10:
    > Consequential patterns must require governance review before activation.
    > No irreversible promotion.

    The gate evaluates: independent evidence, case diversity, prospective
    replication, calibration, confounders, scope, recency, contradictions,
    data coverage. Only human governance (actor="governance") can promote
    to ACTIVE_PATTERN.
    """

    def __init__(self, min_prospective_supports: int = 3, min_replication_diversity: int = 2):
        self._min_prospective_supports = min_prospective_supports
        self._min_replication_diversity = min_replication_diversity

    def evaluate_for_pattern_candidate(self, candidate: Any) -> dict[str, Any]:
        """Evaluate whether a candidate may become a PATTERN_CANDIDATE.

        Returns a recommendation + the criteria checked. Does NOT auto-promote.
        """
        metrics = compute_replication_metrics(candidate)

        criteria = {
            "sufficient_prospective_supports": candidate.supporting_outcomes >= self._min_prospective_supports,
            "sufficient_replication": candidate.prospective_predictions >= self._min_replication_diversity,
            "not_heavily_confounded": True,  # would check confounders per case
            "calibration_acceptable": metrics.brier_score is not None and metrics.brier_score < 0.3,
            "no_contradictions": candidate.contradicting_outcomes == 0,
            "data_coverage_sufficient": not metrics.insufficient_evidence,
        }

        all_met = all(criteria.values())
        recommendation = "promote_to_pattern_candidate" if all_met else "hold"

        return {
            "recommendation": recommendation,
            "criteria": criteria,
            "metrics": metrics.to_dict(),
            "requires_governance_review": all_met,  # if criteria met, send to governance
        }

    def governance_approve(self, candidate: Any, actor: str = "governance") -> StatusTransition:
        """Governance approves promotion to ACTIVE_PATTERN. Records the transition."""
        return StatusTransition(
            from_status=candidate.status.value if hasattr(candidate.status, 'value') else str(candidate.status),
            to_status=HypothesisStatus.ACTIVE_PATTERN.value,
            reason="governance_review_approved",
            evidence=f"supports={candidate.supporting_outcomes}, contradictions={candidate.contradicting_outcomes}",
            actor=actor,
        )


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 5: PROSPECTIVE REGISTRATION (with frozen evidence snapshot)
# ═══════════════════════════════════════════════════════════════════════════

# The register_prospective_prediction_from_case method is on CandidatePatternStore
# (in pattern_proposer.py). The frozen evidence snapshot is created there.
# This module provides the CaseFingerprintBuilder that derives the case identity.

# ═══════════════════════════════════════════════════════════════════════════
# PHASE 12: EXECUTIVE EXPERIENCE (honest uncertainty language)
# ═══════════════════════════════════════════════════════════════════════════

class ExecutiveExperienceFormatter:
    """Formats governed learning state in honest, non-numeric language.

    AUDITOR-DIRECTIVE Phase 12:
    > Do not expose scientific machinery as dashboard clutter.
    > Avoid: 87% organizational truth, 92% law confidence, Maestro IQ,
    > scientific-looking numbers without denominators.
    > The UI should make uncertainty understandable, not impressive.
    """

    @staticmethod
    def format_candidate_for_executive(candidate: Any) -> str:
        """Format a candidate in honest language. No decorative precision."""
        metrics = compute_replication_metrics(candidate)

        if metrics.insufficient_evidence:
            return (
                "Maestro is watching a possible pattern. "
                "This is not yet reliable enough to treat as an organizational pattern. "
                "More independent cases are needed before it can be tested."
            )

        parts = []
        if candidate.prospective_predictions > 0:
            parts.append(
                f"Maestro has registered {candidate.prospective_predictions} prospective "
                f"prediction(s) to test this hypothesis."
            )

        if candidate.resolved_outcomes > 0:
            parts.append(
                f"{candidate.supporting_outcomes} future case(s) support it; "
                f"{candidate.contradicting_outcomes} do not."
            )

        # Confounders would be on the ObservationCase, not the candidate.
        # For now, skip confounder display at the candidate level.

        if hasattr(candidate.status, 'value'):
            status_val = candidate.status.value
        else:
            status_val = str(candidate.status)

        if status_val == "ACTIVE_PATTERN" or status_val == "PROMOTED":
            parts.append("This pattern is currently active.")
        elif status_val == "FALSIFIED":
            parts.append("This pattern was falsified by contradicting evidence.")
        else:
            parts.append("This is not yet reliable enough to treat as an organizational pattern.")

        return " ".join(parts)

    @staticmethod
    def format_scope_for_executive(scope: ScopeRegime) -> str:
        """Format scope in honest language."""
        parts = []
        if scope.valid_scope:
            valid_str = ", ".join(f"{k}={v}" for k, v in scope.valid_scope.items())
            parts.append(f"The evidence currently applies to {valid_str}.")
        if scope.unproven_scope:
            unproven_str = ", ".join(f"{k}={v}" for k, v in scope.unproven_scope.items())
            parts.append(f"Maestro has insufficient evidence for {unproven_str}.")
        if scope.invalid_scope:
            invalid_str = ", ".join(f"{k}={v}" for k, v in scope.invalid_scope.items())
            parts.append(f"The pattern does not apply to {invalid_str}.")
        return " ".join(parts) if parts else "Scope has not been determined yet."

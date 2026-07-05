"""PatternProposer — candidate hypothesis generation (Priority 5A).

AUDITOR-CORRECTION (2026-07-05):
> Repeated reasoning runs are not prospective observations.
> A model may propose what Maestro should investigate.
> Only independent reality may teach Maestro what to believe.

The counters are SEPARATED and must never be conflated:
  - reasoning_mentions: how many times the model proposed this (NOT evidence)
  - historical_support_cases: distinct historical episodes (retrospective only)
  - prospective_predictions: predictions registered BEFORE outcome known
  - resolved_outcomes / supporting_outcomes / contradicting_outcomes

A candidate with reasoning_mentions=27, prospective_predictions=0 is NOT validated.
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


class CandidateStatus(str, Enum):
    """The canonical lifecycle of a candidate hypothesis.

    AUDITOR-CORRECTION (Gap 2): This is the ONE authoritative status enum.
    The 14-state HypothesisStatus in empirical_loop.py is deprecated — it
    created a parallel epistemic state machine that caused the formatter bug.
    This enum now has all the states needed for the full lifecycle.

    Success path:
      HYPOTHESIS → TESTING → ACTIVE_PATTERN → SCOPE_LIMITED (if scope narrows)
      → SUPERSEDED (if a better hypothesis replaces it)

    Non-success paths:
      FALSIFIED — prospective outcomes contradicted the hypothesis
      SUPERSEDED — a better hypothesis replaced this one
      SCOPE_LIMITED — the pattern only applies in a narrow scope
    """
    HYPOTHESIS = "HYPOTHESIS"          # proposed, not yet tested
    TESTING = "TESTING"                # 3+ prospective supports, being calibrated
    ACTIVE_PATTERN = "ACTIVE_PATTERN"  # governance-approved, available to cognition
    SCOPE_LIMITED = "SCOPE_LIMITED"    # active but only in a narrow scope
    FALSIFIED = "FALSIFIED"            # 3+ prospective contradictions
    SUPERSEDED = "SUPERSEDED"          # replaced by a better hypothesis


@dataclass
class CandidatePattern:
    """A candidate organizational pattern proposed by the Reasoning Plane.

    The counters are SEPARATED (AUDITOR-CORRECTION):
      reasoning_mentions: NOT empirical evidence. Never triggers promotion.
      prospective_predictions: registered BEFORE outcome. The only path to empirical support.
      supporting_outcomes: resolved prospective predictions where predicted outcome occurred.
    """
    candidate_id: UUID = field(default_factory=uuid4)
    hypothesis: str = ""
    claim_text: str = ""
    claim_type: str = "inference"
    business_inference_phrases: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    evidence_citation_numbers: list[int] = field(default_factory=list)
    status: CandidateStatus = CandidateStatus.HYPOTHESIS
    reasoning_mentions: int = 1
    historical_support_cases: int = 0
    independent_cases: int = 0
    prospective_predictions: int = 0
    resolved_outcomes: int = 0
    supporting_outcomes: int = 0
    contradicting_outcomes: int = 0
    unresolved_outcomes: int = 0
    first_detected: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_detected: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    proposal_query_ids: list[str] = field(default_factory=list)
    calibration_score: float | None = None
    # Phase 9: Scope — where the pattern applies, is unproven, is invalid
    valid_scope: dict[str, str] = field(default_factory=dict)
    unproven_scope: dict[str, str] = field(default_factory=dict)
    invalid_scope: dict[str, str] = field(default_factory=dict)
    # Phase 10: Governance — who approved, when, why
    governance_approved_by: str = ""
    governance_approved_at: datetime | None = None

    @property
    def dedup_key(self) -> str:
        normalized = re.sub(r'\s+', ' ', self.hypothesis.lower().strip())
        entities_str = ','.join(sorted(e.lower() for e in self.entities))
        return hashlib.sha256(f"{normalized}|{entities_str}".encode()).hexdigest()[:16]

    def to_audit_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": str(self.candidate_id),
            "hypothesis": self.hypothesis,
            "claim_text": self.claim_text[:200],
            "claim_type": self.claim_type,
            "business_inference_phrases": self.business_inference_phrases,
            "entities": self.entities,
            "status": self.status.value,
            "reasoning_mentions": self.reasoning_mentions,
            "historical_support_cases": self.historical_support_cases,
            "prospective_predictions": self.prospective_predictions,
            "resolved_outcomes": self.resolved_outcomes,
            "supporting_outcomes": self.supporting_outcomes,
            "contradicting_outcomes": self.contradicting_outcomes,
            "unresolved_outcomes": self.unresolved_outcomes,
            "calibration_score": self.calibration_score,
        }


class CandidatePatternStore:
    """In-memory store. upsert() increments reasoning_mentions — NOT evidence.

    The ONLY path to empirical support is:
      1. register_prospective_prediction() — before outcome known
      2. resolve_prospective_prediction() — after outcome, from independent signals
    """

    def __init__(self) -> None:
        self._candidates: dict[str, CandidatePattern] = {}
        self._predictions: dict[str, dict[str, Any]] = {}

    def upsert(self, candidate: CandidatePattern, query_id: str = "") -> CandidatePattern:
        """Insert or update. Increments reasoning_mentions — NO status change."""
        key = candidate.dedup_key
        if key in self._candidates:
            existing = self._candidates[key]
            existing.reasoning_mentions += 1
            existing.last_detected = datetime.now(timezone.utc)
            if query_id and query_id not in existing.proposal_query_ids:
                existing.proposal_query_ids.append(query_id)
            return existing
        else:
            if query_id and query_id not in candidate.proposal_query_ids:
                candidate.proposal_query_ids.append(query_id)
            self._candidates[key] = candidate
            return candidate

    def get_all(self) -> list[CandidatePattern]:
        return list(self._candidates.values())

    def get_by_status(self, status: CandidateStatus) -> list[CandidatePattern]:
        return [c for c in self._candidates.values() if c.status == status]

    def get_worth_testing(self, min_mentions: int = 3) -> list[CandidatePattern]:
        """Candidates worth investigating — does NOT promote them."""
        return [
            c for c in self._candidates.values()
            if c.reasoning_mentions >= min_mentions and c.status == CandidateStatus.HYPOTHESIS
        ]

    def register_prospective_prediction(
        self,
        candidate_id: UUID,
        case_fingerprint: str,
        expected_outcome: str,
        observation_window_days: int = 30,
        evidence_snapshot: dict[str, Any] | None = None,
    ) -> str | None:
        """Register a prediction BEFORE outcome is known. The only path to empirical support."""
        candidate = None
        for c in self._candidates.values():
            if c.candidate_id == candidate_id:
                candidate = c
                break
        if candidate is None:
            return None

        for pred in self._predictions.values():
            if pred["case_fingerprint"] == case_fingerprint:
                logger.info("CandidatePatternStore: rejected duplicate prediction (case=%s)", case_fingerprint[:16])
                return None

        prediction_id = f"pred-{uuid4().hex[:12]}"
        self._predictions[prediction_id] = {
            "prediction_id": prediction_id,
            "candidate_id": str(candidate_id),
            "case_fingerprint": case_fingerprint,
            "expected_outcome": expected_outcome,
            "observation_window_days": observation_window_days,
            "registered_at": datetime.now(timezone.utc),
            "evidence_snapshot": evidence_snapshot or {},
            "status": "pending",
            "resolved_at": None,
            "resolution_source": None,
            "observation_case": None,
        }
        candidate.prospective_predictions += 1
        candidate.unresolved_outcomes += 1
        return prediction_id

    def register_prospective_prediction_from_case(
        self,
        candidate_id: UUID,
        observation_case: Any,  # ObservationCase from empirical_loop.py
        expected_outcome: str,
        observation_window_days: int = 30,
    ) -> str | None:
        """Register from a DERIVED ObservationCase. P13: fingerprint is derived, not supplied.

        AUDITOR-DIRECTIVE Phase 2 + Phase 5:
        - Case identity derived from evidence (situation + entity + time + outcome)
        - Evidence snapshot frozen at registration time (prevents future-information leakage)
        - Rejects duplicate cases (same derived fingerprint)
        - Rejects evidence-lineage-overlapping cases (P14: same event copied across sources)
        """
        case_fingerprint = observation_case.case_fingerprint

        # P14: reject if evidence lineage overlaps with existing case for same candidate
        from maestro_oem.empirical_loop import CaseFingerprintBuilder
        for pred in self._predictions.values():
            if pred.get("case_fingerprint") == case_fingerprint:
                logger.info("CandidatePatternStore: rejected duplicate (derived fingerprint=%s)", case_fingerprint[:16])
                return None
            if pred.get("candidate_id") == str(candidate_id):
                existing_case = pred.get("observation_case")
                if existing_case and CaseFingerprintBuilder.cases_share_evidence_lineage(observation_case, existing_case):
                    logger.info("CandidatePatternStore: rejected (evidence lineage overlaps case %s)", pred.get("prediction_id"))
                    return None

        # Freeze the evidence snapshot
        evidence_snapshot = {
            "source_evidence_ids": list(observation_case.source_evidence_ids),
            "evidence_lineage_ids": list(observation_case.evidence_lineage_ids),
            "situation_hash": observation_case.situation_hash,
            "time_window_start": observation_case.time_window_start,
            "frozen_at": datetime.now(timezone.utc).isoformat(),
        }

        prediction_id = self.register_prospective_prediction(
            candidate_id=candidate_id,
            case_fingerprint=case_fingerprint,
            expected_outcome=expected_outcome,
            observation_window_days=observation_window_days,
            evidence_snapshot=evidence_snapshot,
        )

        if prediction_id is not None:
            observation_case.prediction_registered_at = datetime.now(timezone.utc)
            observation_case.observation_window_end = (
                datetime.now(timezone.utc) + timedelta(days=observation_window_days)
            )
            observation_case.expected_outcome = expected_outcome
            observation_case.candidate_pattern_id = candidate_id
            # Attach the case to the prediction so the resolver can use it
            self._predictions[prediction_id]["observation_case"] = observation_case

        return prediction_id

    def resolve_prospective_prediction(
        self,
        prediction_id: str,
        outcome: str,
        resolution_source: str = "",
    ) -> bool:
        """Resolve a prediction AFTER outcome observed (from independent signals)."""
        pred = self._predictions.get(prediction_id)
        if pred is None or pred["status"] != "pending":
            return False

        pred["status"] = outcome
        pred["resolved_at"] = datetime.now(timezone.utc)
        pred["resolution_source"] = resolution_source

        candidate_id = UUID(pred["candidate_id"])
        for c in self._candidates.values():
            if c.candidate_id == candidate_id:
                c.unresolved_outcomes = max(0, c.unresolved_outcomes - 1)
                c.resolved_outcomes += 1
                if outcome == "supporting":
                    c.supporting_outcomes += 1
                elif outcome == "contradicting":
                    c.contradicting_outcomes += 1
                total = c.supporting_outcomes + c.contradicting_outcomes
                if total > 0:
                    actual = c.supporting_outcomes / total
                    c.calibration_score = round((0.5 - actual) ** 2, 4)
                # Auto-falsify: 3+ prospective contradictions, 0 supports
                if c.contradicting_outcomes >= 3 and c.supporting_outcomes == 0:
                    c.status = CandidateStatus.FALSIFIED
                    logger.info("CandidatePattern %s falsified (%d prospective contradictions)", c.candidate_id, c.contradicting_outcomes)
                # Auto-promote: 3+ prospective supports (NOT reasoning_mentions)
                if c.supporting_outcomes >= 3 and c.status == CandidateStatus.HYPOTHESIS:
                    c.status = CandidateStatus.TESTING
                    logger.info("CandidatePattern %s promoted to TESTING (%d prospective supports)", c.candidate_id, c.supporting_outcomes)
                return True
        return False

    def governance_approve(
        self,
        candidate_id: UUID,
        actor: str = "governance",
        valid_scope: dict[str, str] | None = None,
        unproven_scope: dict[str, str] | None = None,
        invalid_scope: dict[str, str] | None = None,
    ) -> bool:
        """Governance approves a candidate for active operational use.

        AUDITOR-DIRECTIVE Phase 10:
        > Consequential patterns must require governance review before activation.
        > No irreversible promotion.

        Promotes TESTING → ACTIVE_PATTERN (or SCOPE_LIMITED if scope is narrow).
        Records the governance approval (actor, timestamp). Only governance
        (a human) can make this transition — the system never auto-promotes
        to ACTIVE_PATTERN.

        Returns True if approved, False if candidate not found or not in TESTING.
        """
        for c in self._candidates.values():
            if c.candidate_id == candidate_id:
                if c.status != CandidateStatus.TESTING:
                    logger.warning(
                        "governance_approve: candidate %s is %s, not TESTING — cannot approve",
                        c.candidate_id, c.status.value,
                    )
                    return False
                # Set scope
                if valid_scope:
                    c.valid_scope = valid_scope
                if unproven_scope:
                    c.unproven_scope = unproven_scope
                if invalid_scope:
                    c.invalid_scope = invalid_scope
                # If scope is narrow, use SCOPE_LIMITED; otherwise ACTIVE_PATTERN
                if invalid_scope or (valid_scope and len(valid_scope) < 3):
                    c.status = CandidateStatus.SCOPE_LIMITED
                else:
                    c.status = CandidateStatus.ACTIVE_PATTERN
                c.governance_approved_by = actor
                c.governance_approved_at = datetime.now(timezone.utc)
                logger.info(
                    "CandidatePattern %s governance-approved → %s (by %s)",
                    c.candidate_id, c.status.value, actor,
                )
                return True
        return False

    def narrow_scope(
        self,
        candidate_id: UUID,
        valid_scope: dict[str, str] | None = None,
        unproven_scope: dict[str, str] | None = None,
        invalid_scope: dict[str, str] | None = None,
    ) -> bool:
        """Narrow the scope of an active pattern (unlearning).

        AUDITOR-DIRECTIVE: "Maestro must not defend its previous belief."
        When contradictory evidence accumulates, the pattern narrows its scope
        or is falsified. This method narrows the scope — the pattern is still
        active but only in a narrower context.
        """
        for c in self._candidates.values():
            if c.candidate_id == candidate_id:
                if valid_scope:
                    c.valid_scope = valid_scope
                if unproven_scope:
                    c.unproven_scope = unproven_scope
                if invalid_scope:
                    c.invalid_scope = invalid_scope
                if c.status == CandidateStatus.ACTIVE_PATTERN:
                    c.status = CandidateStatus.SCOPE_LIMITED
                logger.info(
                    "CandidatePattern %s scope narrowed → %s",
                    c.candidate_id, c.status.value,
                )
                return True
        return False

    def get_pending_predictions(self) -> list[dict[str, Any]]:
        return [p for p in self._predictions.values() if p["status"] == "pending"]

    def summary(self) -> dict[str, Any]:
        all_candidates = list(self._candidates.values())
        return {
            "total_candidates": len(all_candidates),
            "hypothesis": sum(1 for c in all_candidates if c.status == CandidateStatus.HYPOTHESIS),
            "testing": sum(1 for c in all_candidates if c.status == CandidateStatus.TESTING),
            "promoted": sum(1 for c in all_candidates if c.status == CandidateStatus.PROMOTED),
            "falsified": sum(1 for c in all_candidates if c.status == CandidateStatus.FALSIFIED),
            "worth_testing": len(self.get_worth_testing()),
            "pending_predictions": len(self.get_pending_predictions()),
        }


_HYPOTHESIS_TEMPLATES = {
    "at risk": "{entity} may be at risk when {condition}",
    "should": "the organization should consider {action} for {entity}",
    "recommend": "it may be worth recommending {action} for {entity}",
    "must": "{entity} may require {action}",
    "will likely": "{entity} will likely {outcome}",
    "may": "{entity} may {outcome}",
    "might": "{entity} might {outcome}",
    "could lead": "{condition} could lead to {outcome} for {entity}",
    "suggests": "the evidence suggests {entity} {outcome}",
    "indicates that": "the evidence indicates that {entity} {outcome}",
    "implies": "the evidence implies {entity} {outcome}",
}


class PatternProposer:
    """Extracts candidate patterns from ClaimVerifier-labeled claims.

    DETERMINISTIC — uses rules, not LLM. The LLM already did the reasoning.
    NEVER AUTO-ACTIVATES. NEVER CLAIMS CAUSATION. IDEMPOTENT.
    """

    def __init__(self, store: CandidatePatternStore | None = None) -> None:
        self._store = store

    def propose(
        self,
        claims: list[dict],
        entities: list[str],
        query_id: str = "",
    ) -> list[CandidatePattern]:
        """Extract candidates from 'inference' and 'business_inference' claims.

        Skips 'fact' (already established), 'filler' (no content), 'unsupported'
        (no citations to validate against).
        """
        candidates = []
        for claim in claims:
            claim_type = claim.get("claim_type", "")
            if claim_type != "inference":
                continue

            claim_text = claim.get("text", "")
            citations = claim.get("citation_numbers", [])
            business_phrases = claim.get("business_inference_phrases", [])

            hypothesis = self._build_hypothesis(claim_text, entities, business_phrases)
            if not hypothesis:
                continue

            candidate = CandidatePattern(
                hypothesis=hypothesis,
                claim_text=claim_text,
                claim_type="business_inference" if business_phrases else "inference",
                business_inference_phrases=business_phrases,
                entities=list(entities),
                evidence_citation_numbers=list(citations),
            )
            candidates.append(candidate)

        if self._store is not None:
            for c in candidates:
                self._store.upsert(c, query_id=query_id)
            seen_keys = set()
            result = []
            for c in candidates:
                if c.dedup_key not in seen_keys:
                    stored = self._store._candidates.get(c.dedup_key, c)
                    result.append(stored)
                    seen_keys.add(c.dedup_key)
            return result

        return candidates

    def _build_hypothesis(self, claim_text: str, entities: list[str], business_phrases: list[str]) -> str:
        claim_lower = claim_text.lower().strip()
        clean_claim = re.sub(r'\[\d+(?:\s*,\s*\d+)*\]', '', claim_text).strip()
        if len(clean_claim) > 150:
            clean_claim = clean_claim[:147] + "..."
        entity_str = entities[0] if entities else "the entity"

        if business_phrases:
            phrase = business_phrases[0]
            template = _HYPOTHESIS_TEMPLATES.get(phrase)
            if template:
                phrase_idx = claim_lower.find(phrase)
                if phrase_idx >= 0:
                    after_phrase = claim_text[phrase_idx + len(phrase):].strip().rstrip('.')
                    hypothesis = f"the evidence may indicate that {entity_str} {phrase} {after_phrase}".lower()
                    return hypothesis[0].upper() + hypothesis[1:] if hypothesis else ""
            return f"the evidence may indicate that {entity_str} exhibits a pattern worth testing: {clean_claim.lower()}"

        return f"the evidence may indicate a pattern worth testing: {clean_claim.lower()}"

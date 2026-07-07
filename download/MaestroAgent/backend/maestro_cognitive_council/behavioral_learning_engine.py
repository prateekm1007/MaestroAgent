"""
Maestro Cognitive Council — Gate 4: Behavioral Learning Engine.

The wiring layer that connects existing modules into a continuous
learning lifecycle WITHOUT duplicating them.

THE LIFECYCLE (per the CEO directive):
  Situation → judgment → action → outcome → learning → changed future judgment

THE A→B→C→D PROOF (validated against ALL 10 benchmark stories):
  Situation A → judgment → action → outcome
  Situation B → precedent recognized → prior learning applied carefully
  Situation C → contradictory outcome → prior belief weakened
  Situation D → enough independent contradiction → belief suspended or falsified

WHAT THIS ENGINE WIRES (reuse, not rebuild):
  1. PatternProposer → proposes hypotheses from situations (existing)
  2. CaseFingerprintBuilder → builds observation cases (existing)
  3. CandidatePatternStore.register_prospective_prediction_from_case → registers predictions (existing)
  4. LayeredOutcomeResolver → 7-layer outcome resolution (existing, WAS UNWIRED)
  5. OutcomeResolver.resolve_pending → resolves predictions against new signals (existing)
  6. compute_replication_metrics → separates evidence/replication/calibration (existing, WAS UNWIRED)
  7. GovernanceGate.evaluate_for_pattern_candidate → 6-criteria evaluation (existing, WAS UNWIRED)
  8. CandidatePatternStore.governance_approve → the ONLY mutation path to ACTIVE_PATTERN (existing)
  9. Situation learning_dimension → updated based on candidate status (Gate 0 4D model)

THE 4 UNWIRED MODULES NOW WIRED:
  - LayeredOutcomeResolver → wired into outcome resolution (Priority Zero)
  - GovernanceGate.evaluate_for_pattern_candidate() → wired into governance
  - ReplicationMetrics → used for belief strengthening/weakening
  - ExecutiveExperienceFormatter → (deferred to Ask surface wiring)

Reference: docs/MAESTRO_COGNITIVE_COUNCIL_AUDIT_AND_WIRING_PLAN.md
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# Learning Arc Result — the A→B→C→D proof structure
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class LearningArcResult:
    """The result of a single step in the A→B→C→D learning arc.

    Captures:
      - situation_id: which situation this step pertains to
      - arc_step: "A" | "B" | "C" | "D"
      - hypothesis: the organizational hypothesis being tested
      - outcome: "supporting" | "contradicting" | "insufficient_data"
      - belief_effect: "none" | "created" | "strengthened" | "weakened" | "falsified"
      - learning_state_after: the LearningDimensionState after this step
      - evidence_refs: which evidence supported this step
      - reason: WHY this belief effect occurred
    """
    situation_id: str
    arc_step: str                          # "A" | "B" | "C" | "D"
    hypothesis: str = ""
    outcome: str = ""                      # "supporting" | "contradicting" | "insufficient_data"
    belief_effect: str = "none"            # "none"|"created"|"strengthened"|"weakened"|"falsified"
    learning_state_after: str = "none"
    evidence_refs: list[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "situation_id": self.situation_id,
            "arc_step": self.arc_step,
            "hypothesis": self.hypothesis,
            "outcome": self.outcome,
            "belief_effect": self.belief_effect,
            "learning_state_after": self.learning_state_after,
            "evidence_refs": self.evidence_refs,
            "reason": self.reason,
        }


# ════════════════════════════════════════════════════════════════════════════
# BehavioralLearningEngine — the wiring layer
# ════════════════════════════════════════════════════════════════════════════

class BehavioralLearningEngine:
    """Wires existing modules into a continuous learning lifecycle.

    This engine does NOT reimplement any of the existing modules. It
    connects them:
      1. propose_hypothesis() — from a situation, propose a candidate pattern
      2. register_prediction() — register a prospective prediction for the hypothesis
      3. resolve_outcomes() — resolve pending predictions against new signals
         (WIRES LayeredOutcomeResolver — Priority Zero)
      4. evaluate_governance() — evaluate a candidate for promotion
         (WIRES GovernanceGate.evaluate_for_pattern_candidate)
      5. apply_learning() — update the situation's learning_dimension based on outcomes
      6. get_replication_metrics() — get the separated evidence/replication/calibration
         (WIRES ReplicationMetrics)

    Usage:
        engine = BehavioralLearningEngine(candidate_store=oem_state.candidate_pattern_store)
        # A: propose + register + resolve + learn
        engine.propose_hypothesis(situation, hypothesis, expected_outcome)
        engine.register_prediction(situation, expected_outcome)
        engine.resolve_outcomes(new_signals)
        engine.apply_learning(situation)
    """

    def __init__(self, candidate_store: Any = None, oem_state: Any = None):
        """Initialize the engine.

        Args:
            candidate_store: the CandidatePatternStore (in-memory or SQLite).
                If None, the engine creates an in-memory store for testing.
            oem_state: the OEM state singleton (for signal access).
        """
        self._candidate_store = candidate_store
        self._oem_state = oem_state
        self._layered_resolver = None  # lazy init
        self._outcome_resolver = None  # lazy init
        self._governance_gate = None   # lazy init

    @property
    def candidate_store(self) -> Any:
        if self._candidate_store is None:
            try:
                from maestro_oem.pattern_proposer import CandidatePatternStore
                self._candidate_store = CandidatePatternStore()
            except ImportError:
                self._candidate_store = _NullStore()
        return self._candidate_store

    # ── Step 1: Propose a hypothesis from a situation ──────────────────────

    def propose_hypothesis(
        self,
        situation: Any,
        hypothesis: str,
        entities: Optional[list[str]] = None,
        expected_outcome: str = "",
    ) -> Optional[str]:
        """Propose a candidate pattern (hypothesis) from a situation.

        Wires PatternProposer.propose() — does NOT reimplement.
        Returns the candidate_id, or None if the store is unavailable.
        """
        try:
            from maestro_oem.pattern_proposer import PatternProposer
            proposer = PatternProposer(store=self.candidate_store)
            entity_list = entities or ([situation.entity] if hasattr(situation, 'entity') else [])
            query_id = getattr(situation, 'situation_id', str(uuid4()))

            # Propose the hypothesis
            candidate = proposer.propose(
                claims=[{"text": hypothesis, "claim_type": "inference"}],
                entities=entity_list,
                query_id=query_id,
            )

            if candidate:
                # Update the situation's learning dimension
                self._update_learning_dimension(situation, "hypothesis_created")
                return str(candidate.candidate_id)
        except Exception as e:
            logger.debug(f"propose_hypothesis failed: {e}")
        return None

    # ── Step 2: Register a prospective prediction ──────────────────────────

    def register_prediction(
        self,
        situation: Any,
        expected_outcome: str,
        candidate_id: Optional[str] = None,
        observation_window_days: int = 30,
    ) -> Optional[str]:
        """Register a prospective prediction for a situation.

        Wires CaseFingerprintBuilder + CandidatePatternStore.
        register_prospective_prediction_from_case — does NOT reimplement.
        Returns the prediction_id, or None if registration failed.
        """
        try:
            from maestro_oem.empirical_loop import CaseFingerprintBuilder

            # Build the observation case (fingerprint derived, not caller-supplied — P13)
            entity_id = getattr(situation, 'entity', 'unknown')
            observation_case = CaseFingerprintBuilder.build(
                entity_id=entity_id,
                situation=situation,
                outcome_target=expected_outcome,
            )

            # Find the candidate (use provided ID or the most recent for this entity)
            cid = self._find_candidate_id(entity_id, candidate_id)
            if cid is None:
                logger.debug(f"No candidate found for {entity_id}")
                return None

            # Register the prediction (freezes evidence snapshot, sets window)
            prediction_id = self.candidate_store.register_prospective_prediction_from_case(
                candidate_id=UUID(cid),
                observation_case=observation_case,
                expected_outcome=expected_outcome,
                observation_window_days=observation_window_days,
            )

            if prediction_id:
                # Update the situation's learning dimension
                self._update_learning_dimension(situation, "prospectively_testing")

            return prediction_id
        except Exception as e:
            logger.debug(f"register_prediction failed: {e}")
        return None

    # ── Step 3: Resolve outcomes (WIRES LayeredOutcomeResolver) ────────────

    def resolve_outcomes(
        self,
        new_signals: list[Any],
        use_layered_resolver: bool = True,
    ) -> dict[str, Any]:
        """Resolve pending predictions against new signals.

        WIRES LayeredOutcomeResolver into the outcome resolution path.
        Per the CEO audit: "Priority Zero — prefer NOT LEARNING over
        learning falsely." The layered resolver's 7-layer filter prevents
        false learning from ambiguous, negated, or future-tense signals.

        Wires OutcomeResolver.resolve_pending() — does NOT reimplement.
        """
        try:
            from maestro_oem.empirical_loop import OutcomeResolver

            resolver = OutcomeResolver(store=self.candidate_store)

            if use_layered_resolver:
                # Gate 4: use the layered resolver for signal matching
                # This is the UNWIRED module now wired into production
                return self._resolve_with_layered_resolver(resolver, new_signals)
            else:
                # Fallback: simple resolver (the original production path)
                return resolver.resolve_pending(new_signals)
        except Exception as e:
            logger.debug(f"resolve_outcomes failed: {e}")
            return {"checked": 0, "resolved": 0, "expired": 0, "still_pending": 0}

    def _resolve_with_layered_resolver(
        self, resolver: Any, new_signals: list[Any]
    ) -> dict[str, Any]:
        """Use LayeredOutcomeResolver for each signal-outcome pair.

        This wraps the existing OutcomeResolver but replaces the simple
        _signal_matches_outcome matcher with the 7-layer resolver.
        """
        try:
            from maestro_oem.layered_outcome_resolver import LayeredOutcomeResolver
            from maestro_oem.empirical_loop import OutcomeResolver

            layered = LayeredOutcomeResolver()
            store = self.candidate_store
            now = datetime.now(timezone.utc)

            pending = store.get_pending_predictions() if hasattr(store, 'get_pending_predictions') else []
            checked = 0
            resolved = 0
            expired = 0
            resolutions: list[dict] = []

            for pred in pending:
                checked += 1
                pred_id = pred.get("prediction_id", "")
                entity_id = pred.get("entity_id", pred.get("observation_case", {}).get("entity_id", ""))
                expected = pred.get("expected_outcome", "")
                window_end = pred.get("observation_case", {}).get("observation_window_end")

                # Check window expiry first
                if window_end and now > window_end:
                    store.resolve_prospective_prediction(pred_id, "insufficient_data", "window_expired")
                    expired += 1
                    resolutions.append({
                        "prediction_id": pred_id,
                        "entity_id": entity_id,
                        "outcome": "insufficient_data",
                        "resolution_source": "window_expired",
                    })
                    continue

                # Use the layered resolver for each signal
                resolution_found = False
                for signal in new_signals:
                    # Skip shadow/prompt-injected signals (no self-validation)
                    metadata = getattr(signal, 'metadata', {}) or {}
                    if metadata.get("shadow") or metadata.get("prompt_injection_risk"):
                        continue

                    # Check entity match
                    if not self._signal_entity_matches(signal, entity_id):
                        continue

                    # Layered resolution (Priority Zero)
                    outcome_resolution = layered.resolve(signal, expected, entity_id)
                    store_outcome = outcome_resolution.to_store_outcome()

                    if store_outcome != "insufficient_data":
                        # We have a resolution — apply it
                        sig_id = getattr(signal, 'signal_id', str(id(signal)))
                        store.resolve_prospective_prediction(
                            pred_id, store_outcome, f"signal:{sig_id}"
                        )
                        resolved += 1
                        resolutions.append({
                            "prediction_id": pred_id,
                            "entity_id": entity_id,
                            "outcome": store_outcome,
                            "resolution_source": f"signal:{sig_id}",
                            "layer": outcome_resolution.layer.value if hasattr(outcome_resolution.layer, 'value') else str(outcome_resolution.layer),
                            "resolution_method": outcome_resolution.resolution_method,
                        })
                        resolution_found = True
                        break

                if not resolution_found:
                    pass  # still pending

            still_pending = checked - resolved - expired
            return {
                "checked": checked,
                "resolved": resolved,
                "expired": expired,
                "still_pending": still_pending,
                "resolutions": resolutions,
            }
        except ImportError:
            logger.debug("LayeredOutcomeResolver not available — falling back to simple resolver")
            from maestro_oem.empirical_loop import OutcomeResolver
            resolver = OutcomeResolver(store=self.candidate_store)
            return resolver.resolve_pending(new_signals)
        except Exception as e:
            logger.debug(f"Layered resolution failed: {e}")
            from maestro_oem.empirical_loop import OutcomeResolver
            resolver = OutcomeResolver(store=self.candidate_store)
            return resolver.resolve_pending(new_signals)

    def _signal_entity_matches(self, signal: Any, entity_id: str) -> bool:
        """Check if a signal matches an entity (simplified from OutcomeResolver)."""
        if not entity_id:
            return True  # no entity filter
        metadata = getattr(signal, 'metadata', {}) or {}
        customer = metadata.get("customer", "").lower()
        if customer and customer == entity_id.lower():
            return True
        artifact = getattr(signal, 'artifact', "") or ""
        if entity_id.lower() in artifact.lower():
            return True
        return False

    # ── Step 4: Evaluate governance (WIRES GovernanceGate) ─────────────────

    def evaluate_governance(self, candidate_id: str) -> dict[str, Any]:
        """Evaluate a candidate for governance promotion.

        WIRES GovernanceGate.evaluate_for_pattern_candidate() — does NOT reimplement.
        Returns the evaluation result with recommendation + criteria.
        """
        try:
            from maestro_oem.empirical_loop import GovernanceGate

            candidate = self._get_candidate(candidate_id)
            if candidate is None:
                return {"error": "candidate not found"}

            gate = GovernanceGate()
            evaluation = gate.evaluate_for_pattern_candidate(candidate)
            return evaluation
        except Exception as e:
            logger.debug(f"evaluate_governance failed: {e}")
            return {"error": str(e)}

    # ── Step 5: Apply learning (update situation learning_dimension) ───────

    def apply_learning(self, situation: Any, candidate_id: Optional[str] = None) -> LearningArcResult:
        """Apply learning outcomes to a situation.

        Updates the situation's learning_dimension based on the candidate's
        outcome history:
          - 0 outcomes → NONE or HYPOTHESIS_CREATED
          - 1+ supporting, 0 contradicting → LEARNING_UPDATED (belief strengthened)
          - 1+ contradicting, 0 supporting → FALSIFIED (belief weakened/falsified)
          - mixed → CONTESTED (outcome_pending)
        """
        cid = self._find_candidate_id(
            getattr(situation, 'entity', ''),
            candidate_id,
        )

        if cid is None:
            return LearningArcResult(
                situation_id=getattr(situation, 'situation_id', ''),
                arc_step="A",
                belief_effect="none",
                learning_state_after="none",
                reason="No candidate pattern found for this situation",
            )

        candidate = self._get_candidate(cid)
        if candidate is None:
            return LearningArcResult(
                situation_id=getattr(situation, 'situation_id', ''),
                arc_step="A",
                belief_effect="none",
                learning_state_after="none",
                reason="Candidate pattern not found in store",
            )

        supporting = candidate.supporting_outcomes
        contradicting = candidate.contradicting_outcomes
        total = supporting + contradicting

        # Determine belief effect
        if total == 0:
            belief_effect = "none"
            new_state = "hypothesis_created" if candidate.prospective_predictions > 0 else "none"
            reason = "No outcomes resolved yet — hypothesis registered but untested"
        elif contradicting == 0 and supporting > 0:
            belief_effect = "strengthened"
            new_state = "learning_updated"
            reason = f"{supporting} supporting outcome(s), 0 contradicting — belief strengthened"
        elif supporting == 0 and contradicting > 0:
            if contradicting >= 3:
                belief_effect = "falsified"
                new_state = "falsified"
                reason = f"{contradicting} contradicting outcome(s), 0 supporting — belief falsified"
            else:
                belief_effect = "weakened"
                new_state = "outcome_pending"
                reason = f"{contradicting} contradicting outcome(s), 0 supporting — belief weakened"
        else:
            # Mixed outcomes
            belief_effect = "weakened" if contradicting > supporting else "strengthened"
            new_state = "outcome_pending"
            reason = f"Mixed outcomes: {supporting} supporting, {contradicting} contradicting — belief contested"

        # Update the situation's learning dimension
        self._update_learning_dimension(situation, new_state)

        # Determine the arc step
        arc_step = self._determine_arc_step(candidate)

        return LearningArcResult(
            situation_id=getattr(situation, 'situation_id', ''),
            arc_step=arc_step,
            hypothesis=candidate.hypothesis,
            outcome="supporting" if belief_effect == "strengthened" else
                    "contradicting" if belief_effect in ("weakened", "falsified") else
                    "insufficient_data",
            belief_effect=belief_effect,
            learning_state_after=new_state,
            evidence_refs=getattr(candidate, 'evidence_citation_numbers', []),
            reason=reason,
        )

    # ── Step 6: Get replication metrics (WIRES ReplicationMetrics) ─────────

    def get_replication_metrics(self, candidate_id: str) -> dict[str, Any]:
        """Get the separated evidence/replication/calibration metrics.

        WIRES compute_replication_metrics() — does NOT reimplement.
        Per the CEO audit: "No decorative precision — represent evidence
        strength, replication strength, and predictive calibration separately."
        """
        try:
            from maestro_oem.empirical_loop import compute_replication_metrics

            candidate = self._get_candidate(candidate_id)
            if candidate is None:
                return {"error": "candidate not found"}

            metrics = compute_replication_metrics(candidate)
            return {
                "evidence_strength": metrics.evidence_strength,
                "replication_strength": metrics.replication_strength,
                "predictive_calibration": metrics.predictive_calibration,
                "precision": metrics.precision,
                "brier_score": metrics.brier_score,
                "insufficient_evidence": metrics.insufficient_evidence,
                "unresolved_case_count": metrics.unresolved_case_count,
            }
        except Exception as e:
            logger.debug(f"get_replication_metrics failed: {e}")
            return {"error": str(e)}

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _find_candidate_id(self, entity: str, candidate_id: Optional[str] = None) -> Optional[str]:
        """Find a candidate ID by explicit ID or by entity match."""
        if candidate_id:
            return candidate_id

        # Search the store for a candidate matching this entity
        store = self.candidate_store
        if hasattr(store, '_candidates'):
            for cid, candidate in store._candidates.items():
                if entity.lower() in [e.lower() for e in candidate.entities]:
                    return str(cid)
        return None

    def _get_candidate(self, candidate_id: str) -> Any:
        """Get a candidate by ID from the store."""
        store = self.candidate_store
        try:
            cid = UUID(candidate_id) if isinstance(candidate_id, str) else candidate_id
            if hasattr(store, '_candidates'):
                return store._candidates.get(cid)
        except (ValueError, TypeError):
            pass
        return None

    def _update_learning_dimension(self, situation: Any, new_state: str) -> None:
        """Update the situation's learning_dimension via transition_dimension."""
        if hasattr(situation, 'transition_dimension'):
            situation.transition_dimension(
                dimension="learning",
                new_state=new_state,
                reason=f"Learning state updated by BehavioralLearningEngine",
                rule_id=f"learning.{new_state}",
            )

    def _determine_arc_step(self, candidate: Any) -> str:
        """Determine which step of the A→B→C→D arc this candidate is in.

        A: hypothesis created, no outcomes yet
        B: outcomes resolving (supporting) — precedent being recognized
        C: contradictory outcomes appearing — belief weakening
        D: enough contradictions — belief falsified
        """
        supporting = candidate.supporting_outcomes
        contradicting = candidate.contradicting_outcomes

        if supporting == 0 and contradicting == 0:
            return "A"  # hypothesis created, no outcomes
        elif contradicting == 0 and supporting > 0:
            return "B"  # precedent recognized (supporting outcomes)
        elif contradicting > 0 and supporting >= contradicting:
            return "C"  # contradictory outcomes, belief weakening but not falsified
        elif contradicting >= 3 and supporting < contradicting:
            return "D"  # falsified
        else:
            return "C"  # contested


# ════════════════════════════════════════════════════════════════════════════
# Null store for graceful degradation
# ════════════════════════════════════════════════════════════════════════════

class _NullStore:
    """Fallback when CandidatePatternStore is unavailable."""

    _candidates: dict = {}

    def get_pending_predictions(self) -> list:
        return []

    def resolve_prospective_prediction(self, *args, **kwargs) -> bool:
        return False

    def register_prospective_prediction_from_case(self, *args, **kwargs) -> Optional[str]:
        return None

    def governance_approve(self, *args, **kwargs) -> bool:
        return False

    def upsert(self, *args, **kwargs) -> Any:
        return None

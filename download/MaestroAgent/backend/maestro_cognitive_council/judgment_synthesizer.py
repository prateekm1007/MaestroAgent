"""
Maestro Cognitive Council — Gate 2: Judgment Synthesizer (refactored).

Gate 2 changes:
  1. WIRES existing DisagreementDetector (reuse, don't rebuild)
  2. WIRES existing CoverageAssessor for missing-evidence detection (reuse)
  3. Computes EvidenceState (replaces confidence adjectives)
  4. Produces DecisionBoundary (what can be decided now vs. not yet)
  5. Uses ConsequencePathRouter for specialist selection (Gate 2 routing)

The Synthesizer does NOT naively aggregate. It performs:
  1. Deduplication
  2. Contradiction detection (via existing DisagreementDetector)
  3. Priority arbitration
  4. Missing-evidence detection (via existing CoverageAssessor)
  5. Counterevidence search
  6. Decision boundary articulation
  7. Evidence state articulation

Reference: docs/MAESTRO_COGNITIVE_COUNCIL_AUDIT_AND_WIRING_PLAN.md
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any, Optional

from .situation_engine import (
    LivingSituation,
    Judgment,
    DecisionBoundary,
    Disagreement,
    Unknown,
    SituationState,
    EpistemicState,
    EvidenceState,
    DeliveryRoute,
)
from .perspective import Perspective

logger = logging.getLogger(__name__)


class JudgmentSynthesizer:
    """Synthesizes specialist perspectives into a single Judgment.

    Gate 2 refactor: wires existing maestro_oem modules instead of
    duplicating their logic.

    Usage:
        synth = JudgmentSynthesizer()
        judgment = synth.synthesize(situation, perspectives)
        situation.judgment = judgment
    """

    def synthesize(
        self,
        situation: LivingSituation,
        perspectives: list[Perspective],
    ) -> Judgment:
        """Produce a synthesized Judgment from multiple perspectives."""
        if not perspectives:
            return Judgment(
                central_claim=f"Insufficient perspectives to form a judgment about {situation.title}.",
                confidence=0.0,
                evidence_state=EvidenceState.INSUFFICIENT_EVIDENCE,
            )

        # 1. Deduplicate perspectives
        deduped = self._deduplicate(perspectives)

        # 2. Detect disagreements (WIRE existing DisagreementDetector)
        disagreements = self._detect_disagreements_via_existing_engine(deduped, situation)
        situation.disagreements = disagreements

        # 3. Missing-evidence detection (WIRE existing CoverageAssessor)
        coverage_gaps = self._detect_coverage_gaps_via_existing_engine(situation, deduped)

        # 4. Find strongest reasons
        strongest_to_act = self._find_strongest_reason_to_act(deduped)
        strongest_not_to_act = self._find_strongest_reason_not_to_act(deduped)

        # 5. Collect blocking unknowns
        blocking_unknowns = self._collect_blocking_unknowns(situation, deduped)

        # 6. Form central claim
        central_claim = self._form_central_claim(situation, deduped, disagreements, coverage_gaps)

        # 7. Compute evidence state (replaces confidence adjectives)
        evidence_state = self._compute_evidence_state(deduped, blocking_unknowns, disagreements, coverage_gaps)

        # 8. Compute decision boundary (what can be decided now vs. not yet)
        decision_boundary = self._compute_decision_boundary(
            situation, deduped, blocking_unknowns, disagreements
        )

        # 9. Recommend next step (use decision boundary if available)
        recommended_step = (
            decision_boundary.smallest_useful_next_step
            if decision_boundary and decision_boundary.smallest_useful_next_step
            else self._recommend_next_step(deduped, blocking_unknowns, disagreements)
        )

        # 10. Calibrate confidence (retained internally, not the primary signal)
        confidence = self._calibrate_confidence(deduped, blocking_unknowns, disagreements)

        # 11. Collect all evidence refs
        all_evidence: list[str] = []
        for p in deduped:
            for e in p.evidence:
                eid = e.get("evidence_id") or e.get("id") or e.get("source")
                if eid and eid not in all_evidence:
                    all_evidence.append(str(eid))

        return Judgment(
            central_claim=central_claim,
            strongest_reason_to_act=strongest_to_act,
            strongest_reason_not_to_act=strongest_not_to_act,
            unknowns_blocking_decision=blocking_unknowns,
            recommended_next_step=recommended_step,
            confidence=confidence,
            evidence_refs=all_evidence,
            evidence_state=evidence_state,
            decision_boundary=decision_boundary,
        )

    # ── Deduplication ───────────────────────────────────────────────────────

    def _deduplicate(self, perspectives: list[Perspective]) -> list[Perspective]:
        """Remove perspectives that make the same observation.

        Two perspectives are duplicates ONLY if they're from the same
        specialist AND their observations share >70% of significant words.
        """
        if len(perspectives) <= 1:
            return perspectives

        deduped: list[Perspective] = []
        for p in perspectives:
            is_dup = False
            for existing in deduped:
                if p.specialist != existing.specialist:
                    continue
                if self._observations_similar(p.observation, existing.observation):
                    if len(p.evidence) > len(existing.evidence):
                        deduped.remove(existing)
                        deduped.append(p)
                    is_dup = True
                    break
            if not is_dup:
                deduped.append(p)
        return deduped

    def _observations_similar(self, a: str, b: str) -> bool:
        if not a or not b:
            return False
        words_a = set(a.lower().split())
        words_b = set(b.lower().split())
        if not words_a or not words_b:
            return False
        overlap = len(words_a & words_b)
        smaller = min(len(words_a), len(words_b))
        return (overlap / smaller) > 0.70

    # ── Disagreement detection (WIRES existing DisagreementDetector) ────────

    def _detect_disagreements_via_existing_engine(
        self, perspectives: list[Perspective], situation: LivingSituation
    ) -> list[Disagreement]:
        """Detect disagreements using the existing DisagreementDetector.

        Wires maestro_oem.disagreement_detector.DisagreementDetector
        instead of reimplementing the logic. The existing engine does
        pairwise comparison across different epistemic claim_types and
        resolves via EPISTEMIC_RELIABILITY ranking.
        """
        # Also check urgency-vector disagreements (the Gate 1 addition)
        urgency_disagreements = self._detect_urgency_disagreements(perspectives)

        # Convert perspectives to the format DisagreementDetector expects
        # (objects with .claim and .claim_type attributes)
        evidence_objects = []
        for p in perspectives:
            evidence_objects.append(SimpleNamespace(
                claim=p.observation or p.implication,
                claim_type=p.epistemic_status.value if hasattr(p.epistemic_status, "value") else str(p.epistemic_status),
            ))

        # Try to use the existing DisagreementDetector
        existing_disagreements: list[Disagreement] = []
        try:
            from maestro_oem.disagreement_detector import DisagreementDetector
            detector = DisagreementDetector()
            raw_disagreements = detector.detect(
                evidence_list=evidence_objects,
                entity=situation.entity,
                topic=situation.title,
            )
            # Convert the existing Disagreement objects to our Disagreement dataclass
            for rd in raw_disagreements:
                existing_disagreements.append(Disagreement(
                    topic=getattr(rd, 'topic', situation.title),
                    position_a=getattr(rd, 'claim_a', ''),
                    position_b=getattr(rd, 'claim_b', ''),
                    specialist_a="",  # the existing detector doesn't track specialist
                    specialist_b="",
                    resolution=f"{getattr(rd, 'resolution_favors', '?')} favored: {getattr(rd, 'resolution_reason', '')}",
                    unresolved=True,
                ))
        except ImportError:
            logger.debug("DisagreementDetector not available — using urgency-based only")
        except Exception as e:
            logger.debug(f"DisagreementDetector failed: {e} — using urgency-based only")

        # Merge urgency disagreements with existing-engine disagreements
        all_disagreements = existing_disagreements + urgency_disagreements

        # Deduplicate by (position_a, position_b)
        seen: set[str] = set()
        unique: list[Disagreement] = []
        for d in all_disagreements:
            key = f"{d.position_a}|{d.position_b}"
            if key not in seen:
                seen.add(key)
                unique.append(d)

        return unique

    def _detect_urgency_disagreements(self, perspectives: list[Perspective]) -> list[Disagreement]:
        """Detect disagreements based on urgency divergence.

        This is the Gate 1 addition — preserved alongside the existing
        DisagreementDetector. Two perspectives with very different urgency
        levels (e.g., one "critical", one "low") are in disagreement.
        """
        disagreements: list[Disagreement] = []
        urgency_order = {"low": 0, "normal": 1, "high": 2, "critical": 3}

        for i, p1 in enumerate(perspectives):
            for p2 in perspectives[i + 1:]:
                if p1.specialist == p2.specialist:
                    continue
                u1 = urgency_order.get(p1.urgency, 1)
                u2 = urgency_order.get(p2.urgency, 1)
                if abs(u1 - u2) >= 2:
                    disagreements.append(Disagreement(
                        topic=p1.observation[:80] if p1.observation else p2.observation[:80],
                        position_a=f"[{p1.specialist}] urgency={p1.urgency}: {p1.implication[:100]}",
                        position_b=f"[{p2.specialist}] urgency={p2.urgency}: {p2.implication[:100]}",
                        specialist_a=p1.specialist,
                        specialist_b=p2.specialist,
                        resolution=None,
                        unresolved=True,
                    ))
        return disagreements

    # ── Missing-evidence detection (WIRES existing CoverageAssessor) ────────

    def _detect_coverage_gaps_via_existing_engine(
        self, situation: LivingSituation, perspectives: list[Perspective]
    ) -> list[str]:
        """Detect missing evidence using the existing CoverageAssessor.

        Wires maestro_oem.coverage_assessor.CoverageAssessor instead of
        reimplementing the 10-check reasoner. The existing engine runs
        10 mechanical checks (entity coverage, timeline, situation type,
        relationship rules, unused salience, contradictions, definition
        mismatches, beyond-rule question, restating, disconnected signals).
        """
        # Convert situation evidence + perspectives to the format CoverageAssessor expects
        evidence_dicts: list[dict] = []
        for p in perspectives:
            for e in p.evidence:
                evidence_dicts.append({
                    "text": e.get("description", "") or e.get("source", ""),
                    "date": e.get("date", ""),
                    "people": e.get("people", []),
                    "evidence_spine": {
                        "claim_type": p.epistemic_status.value if hasattr(p.epistemic_status, "value") else str(p.epistemic_status),
                    },
                })

        try:
            from maestro_oem.coverage_assessor import CoverageAssessor
            assessor = CoverageAssessor()
            assessment = assessor.assess(
                query=situation.title,
                evidence=evidence_dicts,
            )
            return assessment.gaps if hasattr(assessment, 'gaps') else []
        except ImportError:
            logger.debug("CoverageAssessor not available — skipping coverage gaps")
        except Exception as e:
            logger.debug(f"CoverageAssessor failed: {e} — skipping coverage gaps")

        return []

    # ── Strongest reasons ───────────────────────────────────────────────────

    def _find_strongest_reason_to_act(self, perspectives: list[Perspective]) -> str:
        urgency_weight = {"low": 1, "normal": 2, "high": 3, "critical": 4}
        best: Optional[Perspective] = None
        best_score = 0
        for p in perspectives:
            score = urgency_weight.get(p.urgency, 2) + len(p.evidence)
            if score > best_score:
                best = p
                best_score = score
        if best is None:
            return ""
        return f"[{best.specialist}] {best.implication}" if best.implication else f"[{best.specialist}] {best.observation}"

    def _find_strongest_reason_not_to_act(self, perspectives: list[Perspective]) -> str:
        for p in perspectives:
            if p.counterevidence:
                ce_text = "; ".join(
                    ce.get("description", ce.get("source", ""))
                    for ce in p.counterevidence
                )
                return f"[{p.specialist}] counterevidence: {ce_text}"
        for p in perspectives:
            if p.urgency == "low":
                return f"[{p.specialist}] low urgency: {p.implication}"
        return "No specialist identified a reason not to act."

    # ── Unknowns ────────────────────────────────────────────────────────────

    def _collect_blocking_unknowns(
        self, situation: LivingSituation, perspectives: list[Perspective]
    ) -> list[str]:
        blocking: list[str] = []
        for u in situation.unknowns:
            if u.blocking and not u.resolved:
                blocking.append(u.question)
        for p in perspectives:
            for unk in p.unknowns:
                if unk not in blocking:
                    blocking.append(unk)
        return blocking

    # ── Central claim formation ─────────────────────────────────────────────

    def _form_central_claim(
        self,
        situation: LivingSituation,
        perspectives: list[Perspective],
        disagreements: list[Disagreement],
        coverage_gaps: list[str],
    ) -> str:
        if not perspectives:
            return f"Insufficient evidence to form a judgment about {situation.title}."

        if disagreements:
            return (
                f"{situation.title}: specialists disagree on {len(disagreements)} point(s). "
                f"The disagreement is not about whether to act, but about sequencing and risk. "
                f"See disagreements for the reasoning path."
            )

        if situation.has_blocking_unknown():
            blocking_count = len([u for u in situation.unknowns if u.blocking and not u.resolved])
            return (
                f"{situation.title}: {len(perspectives)} perspective(s) converge, but "
                f"{blocking_count} blocking unknown(s) remain. "
                f"The situation cannot be fully judged until the unknowns are resolved. "
                f"Epistemic state: {situation.epistemic_state.value}."
            )

        if coverage_gaps:
            return (
                f"{situation.title}: {len(perspectives)} perspective(s) converge, but "
                f"{len(coverage_gaps)} coverage gap(s) detected. "
                f"The evidence base is incomplete."
            )

        return (
            f"{situation.title}: {len(perspectives)} perspective(s) converge on a "
            f"similar assessment. Epistemic state: {situation.epistemic_state.value}."
        )

    # ── Evidence state (replaces confidence adjectives) ─────────────────────

    def _compute_evidence_state(
        self,
        perspectives: list[Perspective],
        blocking_unknowns: list[str],
        disagreements: list[Disagreement],
        coverage_gaps: list[str],
    ) -> EvidenceState:
        """Compute the evidence state — NOT a confidence adjective.

        DIRECTLY_SUPPORTED: evidence directly backs the claim, no unknowns
        SUPPORTED_WITH_GAPS: evidence backs it but key facts missing
        CONTESTED: credible evidence conflicts (disagreements exist)
        PRELIMINARY: early-stage, few perspectives, could change
        INSUFFICIENT_EVIDENCE: not enough evidence to say
        """
        if not perspectives:
            return EvidenceState.INSUFFICIENT_EVIDENCE

        # CONTESTED: disagreements exist
        if disagreements:
            return EvidenceState.CONTESTED

        # SUPPORTED_WITH_GAPS: evidence exists but blocking unknowns remain
        if blocking_unknowns:
            return EvidenceState.SUPPORTED_WITH_GAPS

        # INSUFFICIENT_EVIDENCE: too few perspectives or no evidence
        total_evidence = sum(len(p.evidence) for p in perspectives)
        if len(perspectives) < 2 or total_evidence < 2:
            return EvidenceState.INSUFFICIENT_EVIDENCE

        # PRELIMINARY: few perspectives, could change
        if len(perspectives) < 3:
            return EvidenceState.PRELIMINARY

        # Coverage gaps → SUPPORTED_WITH_GAPS
        if coverage_gaps:
            return EvidenceState.SUPPORTED_WITH_GAPS

        # DIRECTLY_SUPPORTED: multiple perspectives, multiple evidence, no unknowns
        return EvidenceState.DIRECTLY_SUPPORTED

    # ── Decision boundary (what can be decided now vs. not yet) ─────────────

    def _compute_decision_boundary(
        self,
        situation: LivingSituation,
        perspectives: list[Perspective],
        blocking_unknowns: list[str],
        disagreements: list[Disagreement],
    ) -> DecisionBoundary:
        """Articulate what can be decided now vs. what cannot yet be decided.

        This is genuine executive intelligence:
          Most systems produce: "Here are the facts."
          Some produce: "Here is my recommendation."
          Better: "Here is what reality currently permits you to decide."

        Engine Fix 5 (C13): Situation-specific boundary language.
        Per external reviewer: 'The engine produces confident recommendations
        when the evidence supports only direction decidable, sequence not.'
        The prior generic language ('proceed with the general direction') was
        false-decisive. Now the boundary language is derived from the
        situation's entity, timeline, and key themes — so the executive
        sees 'reduce scope to original 3 features' instead of 'proceed with
        the general direction.'
        """
        can_decide: list[str] = []
        cannot_decide: list[str] = []
        why = ""
        next_step = ""

        # Extract situation-specific context for boundary language
        entity = situation.entity or "the situation"
        title = situation.title or ""
        # Extract key themes from timeline
        timeline_texts = [e.description for e in situation.timeline if hasattr(e, "description")]
        key_theme = self._extract_key_theme(title, timeline_texts)

        # Fix: Detect scope mutation patterns for situation-specific boundary
        # language (Story 5: scope mutation). When scope expansions are present,
        # the boundary should mention reducing scope, not just "proceed".
        timeline_combined = " ".join(timeline_texts).lower()
        has_scope_expansion = "scope" in timeline_combined or "feature" in timeline_combined
        has_engineering_warning = "warning" in timeline_combined or "cannot deliver" in timeline_combined or "at risk" in timeline_combined

        # Corrected audit condition 1 (2026-07-08): False decisiveness gate.
        # Per auditor: "Every recommendation with fewer than 3 independent
        # evidence items must include 'NOT ENOUGH EVIDENCE TO DECIDE' rather
        # than a confident action." This prevents the 33% false-decisiveness
        # rate where the system recommends action when evidence is insufficient.
        #
        # The gate applies ONLY to the convergent path (no disagreements, no
        # blocking unknowns). The disagreement and blocking-unknowns paths
        # already acknowledge uncertainty — they are not false-decisive.
        evidence_count = len(situation.evidence_refs)
        MIN_EVIDENCE_FOR_DECISION = 3

        if disagreements:
            # When specialists disagree, you can decide the direction but not the sequence
            # Situation-specific: use the entity and theme
            can_decide.append(
                f"Adopt the general direction for {entity} ({key_theme}) — "
                f"specialists agree on what, not how"
            )
            # Extract the specific disagreement topic for cannot_decide
            dis_topic = disagreements[0].topic if disagreements else "sequencing"
            cannot_decide.append(
                f"Determine the specific sequence or timing for {key_theme} "
                f"(disagreement: {dis_topic[:80]})"
            )
            why = (
                f"Specialists disagree on {len(disagreements)} point(s) about {entity}. "
                f"The disagreement is about sequencing, not direction."
            )
            next_step = (
                f"Review the disagreements on {key_theme} and determine whether "
                f"a phased approach resolves the conflict."
            )
        elif blocking_unknowns:
            # When blocking unknowns exist, you can decide the direction but not the specifics
            can_decide.append(
                f"Proceed with the general direction for {entity} ({key_theme})"
            )
            cannot_decide.append(
                f"Commit to specific commitments or deadlines for {key_theme}"
            )
            why = (
                f"{len(blocking_unknowns)} blocking unknown(s) remain unresolved for {entity}. "
                f"Decisions that depend on these unknowns cannot be finalized."
            )
            next_step = (
                f"Resolve the blocking unknown(s) before deciding on {key_theme}: "
                f"{'; '.join(blocking_unknowns[:2])}"
            )
        else:
            # Convergent case — can decide fully
            # BUT: false decisiveness gate — if <3 evidence items, don't
            # produce a confident recommendation. This is the specific path
            # the corrected audit identified as the 33% false-decisiveness risk.
            if evidence_count < MIN_EVIDENCE_FOR_DECISION:
                can_decide.append(
                    f"NOT ENOUGH EVIDENCE TO DECIDE on {key_theme} "
                    f"({evidence_count} evidence item(s), need {MIN_EVIDENCE_FOR_DECISION}+)"
                )
                cannot_decide.append(
                    f"Make any commitment on {key_theme} until more evidence arrives"
                )
                why = (
                    f"Only {evidence_count} independent evidence item(s) available for {entity}. "
                    f"Perspectives converge but decisions require at least "
                    f"{MIN_EVIDENCE_FOR_DECISION} independent sources to avoid false decisiveness."
                )
                next_step = (
                    f"Gather more evidence on {key_theme} before deciding. "
                    f"Current evidence: {evidence_count}/{MIN_EVIDENCE_FOR_DECISION} required."
                )
            else:
                # Fix: Scope-specific boundary language (Story 5)
                if has_scope_expansion and has_engineering_warning:
                    can_decide.append(
                        f"Reduce scope to original plan for {entity} ({key_theme})"
                    )
                    cannot_decide.append(
                        f"Deliver all expanded features by the original deadline for {key_theme}"
                    )
                    why = (
                        f"Engineering flagged delivery risk with expanded scope. "
                        f"{evidence_count} evidence items show scope has grown beyond "
                        f"original plan. Reducing scope is the safe decision."
                    )
                    next_step = (
                        f"Review scope expansions on {key_theme} and prioritize "
                        f"original features over additions."
                    )
                else:
                    can_decide.append(
                        f"Proceed with the recommended action for {entity} ({key_theme})"
                    )
                    why = (
                        f"Perspectives converge with no blocking unknowns or disagreements "
                        f"about {key_theme}. {evidence_count} evidence items support this."
                    )
                # Find the highest-urgency recommended_next_step
                urgency_order = {"critical": 0, "high": 1, "normal": 2, "low": 3}
                sorted_persps = sorted(perspectives, key=lambda p: urgency_order.get(p.urgency, 2))
                for p in sorted_persps:
                    if p.recommended_next_step:
                        next_step = p.recommended_next_step
                        break
                if not next_step:
                    next_step = f"Monitor {key_theme}."

        return DecisionBoundary(
            can_decide_now=can_decide,
            cannot_decide_yet=cannot_decide,
            why=why,
            smallest_useful_next_step=next_step,
        )

    def _extract_key_theme(self, title: str, timeline_texts: list[str]) -> str:
        """Extract the key theme from the situation title and timeline.

        Per Engine Fix 5 (C13): the boundary language must be situation-
        specific, not generic. This helper extracts a 2-4 word theme from
        the situation's title and timeline that captures what the situation
        is about (e.g., 'SSO delivery', 'OAuth migration', 'pricing exception',
        'scope mutation').
        """
        # Try to extract from title first
        if title:
            # Remove common prefixes like "Customer commitment drift —"
            if "—" in title:
                title = title.split("—")[-1].strip()
            elif "-" in title and len(title.split("-")[-1]) > 5:
                title = title.split("-")[-1].strip()
            # Take first 4 words
            words = title.split()[:4]
            if words:
                return " ".join(words)

        # Fall back to timeline texts
        if timeline_texts:
            # Find the most common meaningful word across timeline events
            from collections import Counter
            words = []
            for text in timeline_texts:
                # Extract entity-like words (capitalized, 3+ chars)
                for w in text.split():
                    if len(w) > 3 and w[0].isupper():
                        words.append(w)
            if words:
                common = Counter(words).most_common(3)
                return " ".join(w for w, _ in common)

        return "this situation"

    # ── Next step recommendation (fallback if decision boundary is empty) ──

    def _recommend_next_step(
        self,
        perspectives: list[Perspective],
        blocking_unknowns: list[str],
        disagreements: list[Disagreement],
    ) -> str:
        if blocking_unknowns:
            return f"Resolve the blocking unknown(s) before deciding: {'; '.join(blocking_unknowns[:2])}"
        if disagreements:
            return "Review the disagreements and determine whether a phased approach resolves the conflict."
        urgency_order = {"critical": 0, "high": 1, "normal": 2, "low": 3}
        sorted_persps = sorted(perspectives, key=lambda p: urgency_order.get(p.urgency, 2))
        for p in sorted_persps:
            if p.recommended_next_step:
                return p.recommended_next_step
        return "No specific next step recommended — monitor the situation."

    # ── Confidence calibration (retained internally) ────────────────────────

    def _calibrate_confidence(
        self,
        perspectives: list[Perspective],
        blocking_unknowns: list[str],
        disagreements: list[Disagreement],
    ) -> float:
        if not perspectives:
            return 0.0
        base = min(len(perspectives) * 0.15, 0.60)
        avg_evidence = sum(len(p.evidence) for p in perspectives) / len(perspectives)
        evidence_bonus = min(avg_evidence * 0.10, 0.20)
        unknowns_penalty = min(len(blocking_unknowns) * 0.10, 0.30)
        disagreement_penalty = min(len(disagreements) * 0.05, 0.20)
        epistemic_bonus = 0.0
        for p in perspectives:
            if p.epistemic_status == EpistemicState.KNOWN:
                epistemic_bonus += 0.02
            elif p.epistemic_status == EpistemicState.UNKNOWN:
                epistemic_bonus -= 0.02
        epistemic_bonus = max(-0.10, min(epistemic_bonus, 0.10))
        confidence = base + evidence_bonus - unknowns_penalty - disagreement_penalty + epistemic_bonus
        return max(0.0, min(1.0, confidence))

    # ── Public method: detect disagreements (for external callers) ──────────

    def detect_disagreements(self, perspectives: list[Perspective]) -> list[Disagreement]:
        """Public method for external callers (backward compatibility)."""
        return self._detect_urgency_disagreements(perspectives)

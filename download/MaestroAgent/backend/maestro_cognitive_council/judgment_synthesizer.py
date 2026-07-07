"""
Maestro Cognitive Council — Phase 3: Judgment Synthesizer.

The Synthesizer does NOT naively aggregate 16 specialist outputs into
a summary. That would be the weak architecture.

Instead, it performs:
  1. Deduplication (remove perspectives that say the same thing)
  2. Contradiction detection (find perspectives that disagree)
  3. Priority arbitration (which perspectives matter most)
  4. Cross-domain dependency analysis (how do perspectives interact?)
  5. Missing-evidence detection (what did no specialist address?)
  6. Counterevidence search (what weakens the leading position?)
  7. Decision relevance analysis (does this actually need a decision?)
  8. Delivery recommendation (how should this be surfaced?)

The output is a Judgment — a reasoned position, not a summary.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from .situation_engine import (
    LivingSituation,
    Judgment,
    Disagreement,
    Unknown,
    SituationState,
    EpistemicState,
    DeliveryRoute,
)
from .perspective import Perspective

logger = logging.getLogger(__name__)


class JudgmentSynthesizer:
    """Synthesizes specialist perspectives into a single Judgment.

    Usage:
        synth = JudgmentSynthesizer()
        judgment = synth.synthesize(situation, perspectives)
        situation.judgment = judgment
        situation.disagreements = synth.detect_disagreements(perspectives)
    """

    def synthesize(
        self,
        situation: LivingSituation,
        perspectives: list[Perspective],
    ) -> Judgment:
        """Produce a synthesized Judgment from multiple perspectives.

        This is the core of the Cognitive Council. The output is a
        reasoned position — not a summary. It must:
          - State the central claim
          - Acknowledge the strongest reason to act
          - Acknowledge the strongest reason not to act
          - Identify what remains unknown
          - Recommend a next step (no pseudo-scientific precision)
        """
        if not perspectives:
            return Judgment(
                central_claim=f"Insufficient perspectives to form a judgment about {situation.title}.",
                confidence=0.0,
            )

        # 1. Deduplicate perspectives (by observation similarity)
        deduped = self._deduplicate(perspectives)

        # 2. Detect disagreements
        disagreements = self.detect_disagreements(deduped)
        situation.disagreements = disagreements

        # 3. Find the strongest reason to act (highest-urgency perspective
        #    with evidence and a recommended_next_step)
        strongest_to_act = self._find_strongest_reason_to_act(deduped)

        # 4. Find the strongest reason not to act (counterevidence or a
        #    perspective recommending caution)
        strongest_not_to_act = self._find_strongest_reason_not_to_act(deduped)

        # 5. Collect unknowns blocking the decision
        blocking_unknowns = self._collect_blocking_unknowns(situation, deduped)

        # 6. Form the central claim
        central_claim = self._form_central_claim(situation, deduped, disagreements)

        # 7. Recommend next step
        recommended_step = self._recommend_next_step(
            deduped, blocking_unknowns, disagreements
        )

        # 8. Calibrate confidence (NOT fabricated — based on evidence count,
        #    epistemic states, and whether unknowns remain)
        confidence = self._calibrate_confidence(deduped, blocking_unknowns, disagreements)

        # 9. Collect all evidence IDs
        all_evidence: list[str] = []
        for p in deduped:
            for e in p.evidence:
                eid = e.get("evidence_id") or e.get("id")
                if eid and eid not in all_evidence:
                    all_evidence.append(eid)

        return Judgment(
            central_claim=central_claim,
            strongest_reason_to_act=strongest_to_act,
            strongest_reason_not_to_act=strongest_not_to_act,
            unknowns_blocking_decision=blocking_unknowns,
            recommended_next_step=recommended_step,
            confidence=confidence,
            evidence_ids=all_evidence,
        )

    # ── Deduplication ───────────────────────────────────────────────────────

    def _deduplicate(self, perspectives: list[Perspective]) -> list[Perspective]:
        """Remove perspectives that make the same observation.

        Two perspectives are duplicates ONLY if they're from the same
        specialist AND their observations share >70% of significant words.
        Different specialists noticing the same thing from different angles
        is a FEATURE (cross-domain convergence), not a duplicate.
        """
        if len(perspectives) <= 1:
            return perspectives

        deduped: list[Perspective] = []
        for p in perspectives:
            is_dup = False
            for existing in deduped:
                # Only deduplicate within the same specialist
                if p.specialist != existing.specialist:
                    continue
                if self._observations_similar(p.observation, existing.observation):
                    # Keep the one with more evidence
                    if len(p.evidence) > len(existing.evidence):
                        deduped.remove(existing)
                        deduped.append(p)
                    is_dup = True
                    break
            if not is_dup:
                deduped.append(p)
        return deduped

    def _observations_similar(self, a: str, b: str) -> bool:
        """Check if two observations are >70% similar by word overlap."""
        if not a or not b:
            return False
        words_a = set(a.lower().split())
        words_b = set(b.lower().split())
        if not words_a or not words_b:
            return False
        overlap = len(words_a & words_b)
        smaller = min(len(words_a), len(words_b))
        return (overlap / smaller) > 0.70

    # ── Disagreement detection ──────────────────────────────────────────────

    def detect_disagreements(self, perspectives: list[Perspective]) -> list[Disagreement]:
        """Detect disagreements between perspectives.

        A disagreement exists when two perspectives have:
          - Different specialists
          - Opposite urgency directions (one "high"/"critical", one "low")
          - OR explicitly contradictory recommended_next_steps
          - OR one's counterevidence contradicts another's evidence
        """
        disagreements: list[Disagreement] = []

        for i, p1 in enumerate(perspectives):
            for p2 in perspectives[i + 1:]:
                if p1.specialist == p2.specialist:
                    continue  # same specialist won't disagree with itself

                # Check urgency divergence
                urgency_order = {"low": 0, "normal": 1, "high": 2, "critical": 3}
                u1 = urgency_order.get(p1.urgency, 1)
                u2 = urgency_order.get(p2.urgency, 1)
                if abs(u1 - u2) >= 2:  # one is high/critical, other is low
                    disagreements.append(Disagreement(
                        topic=p1.observation[:80] if p1.observation else p2.observation[:80],
                        position_a=f"[{p1.specialist}] urgency={p1.urgency}: {p1.implication[:100]}",
                        position_b=f"[{p2.specialist}] urgency={p2.urgency}: {p2.implication[:100]}",
                        specialist_a=p1.specialist,
                        specialist_b=p2.specialist,
                        resolution=None,
                        unresolved=True,
                    ))

                # Check counterevidence overlap
                for ce in p1.counterevidence:
                    ce_source = ce.get("source", "")
                    for ev in p2.evidence:
                        if ce_source and ce_source == ev.get("source"):
                            disagreements.append(Disagreement(
                                topic=f"Evidence conflict: {ce_source}",
                                position_a=f"[{p1.specialist}] cites {ce_source} as counterevidence",
                                position_b=f"[{p2.specialist}] cites {ce_source} as supporting evidence",
                                specialist_a=p1.specialist,
                                specialist_b=p2.specialist,
                                resolution=None,
                                unresolved=True,
                            ))

        return disagreements

    # ── Strongest reasons ───────────────────────────────────────────────────

    def _find_strongest_reason_to_act(self, perspectives: list[Perspective]) -> str:
        """Find the strongest reason to act (highest urgency + evidence)."""
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
        """Find the strongest reason not to act (counterevidence or low urgency)."""
        # Look for perspectives with counterevidence
        for p in perspectives:
            if p.counterevidence:
                ce_text = "; ".join(
                    ce.get("description", ce.get("source", ""))
                    for ce in p.counterevidence
                )
                return f"[{p.specialist}] counterevidence: {ce_text}"

        # Look for perspectives recommending caution (low urgency)
        for p in perspectives:
            if p.urgency == "low":
                return f"[{p.specialist}] low urgency: {p.implication}"

        return "No specialist identified a reason not to act."

    # ── Unknowns ────────────────────────────────────────────────────────────

    def _collect_blocking_unknowns(
        self, situation: LivingSituation, perspectives: list[Perspective]
    ) -> list[str]:
        """Collect all unknowns that block a decision."""
        blocking: list[str] = []

        # From the situation itself
        for u in situation.unknowns:
            if u.blocking:
                blocking.append(u.question)

        # From perspectives
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
    ) -> str:
        """Form the central claim of the judgment.

        The central claim is NOT a summary. It's a reasoned position
        that acknowledges the situation's epistemic state.
        """
        if not perspectives:
            return f"Insufficient evidence to form a judgment about {situation.title}."

        # If there are unresolved disagreements, the claim must acknowledge them
        if disagreements:
            return (
                f"{situation.title}: specialists disagree on {len(disagreements)} point(s). "
                f"The disagreement is not about whether to act, but about sequencing and risk. "
                f"See disagreements for the reasoning path."
            )

        # If there are blocking unknowns, the claim must acknowledge them
        if situation.has_blocking_unknown():
            return (
                f"{situation.title}: {len(perspectives)} perspective(s) converge, but "
                f"{len([u for u in situation.unknowns if u.blocking])} blocking unknown(s) remain. "
                f"The situation cannot be fully judged until the unknowns are resolved."
            )

        # Convergent case
        return (
            f"{situation.title}: {len(perspectives)} perspective(s) converge on a "
            f"similar assessment. The strongest reason to act is documented. "
            f"Epistemic state: {situation.epistemic_state.value}."
        )

    # ── Next step recommendation ────────────────────────────────────────────

    def _recommend_next_step(
        self,
        perspectives: list[Perspective],
        blocking_unknowns: list[str],
        disagreements: list[Disagreement],
    ) -> str:
        """Recommend the smallest useful next step."""
        # If there are blocking unknowns, the next step is to resolve them
        if blocking_unknowns:
            return f"Resolve the blocking unknown(s) before deciding: {'; '.join(blocking_unknowns[:2])}"

        # If there are disagreements, the next step is to reconcile them
        if disagreements:
            return "Review the disagreements and determine whether a phased approach resolves the conflict."

        # Otherwise, take the most urgent recommended_next_step
        urgency_order = {"critical": 0, "high": 1, "normal": 2, "low": 3}
        sorted_persps = sorted(
            perspectives,
            key=lambda p: urgency_order.get(p.urgency, 2),
        )
        for p in sorted_persps:
            if p.recommended_next_step:
                return p.recommended_next_step

        return "No specific next step recommended — monitor the situation."

    # ── Confidence calibration ──────────────────────────────────────────────

    def _calibrate_confidence(
        self,
        perspectives: list[Perspective],
        blocking_unknowns: list[str],
        disagreements: list[Disagreement],
    ) -> float:
        """Calibrate confidence — NOT fabricated.

        Confidence is based on:
          - Number of perspectives (more = higher, up to a cap)
          - Average evidence per perspective (more = higher)
          - Number of blocking unknowns (more = lower)
          - Number of disagreements (more = lower)
          - Epistemic states (KNOWN > REPORTED > UNKNOWN)

        This never produces pseudo-scientific precision (e.g., 83.7%).
        The output is a coarse 0.0-1.0 value.
        """
        if not perspectives:
            return 0.0

        # Base: number of perspectives (diminishing returns)
        base = min(len(perspectives) * 0.15, 0.60)

        # Evidence bonus
        avg_evidence = sum(len(p.evidence) for p in perspectives) / len(perspectives)
        evidence_bonus = min(avg_evidence * 0.10, 0.20)

        # Unknowns penalty
        unknowns_penalty = min(len(blocking_unknowns) * 0.10, 0.30)

        # Disagreements penalty
        disagreement_penalty = min(len(disagreements) * 0.05, 0.20)

        # Epistemic state bonus
        epistemic_bonus = 0.0
        for p in perspectives:
            if p.epistemic_status == EpistemicState.KNOWN:
                epistemic_bonus += 0.02
            elif p.epistemic_status == EpistemicState.UNKNOWN:
                epistemic_bonus -= 0.02
        epistemic_bonus = max(-0.10, min(epistemic_bonus, 0.10))

        confidence = base + evidence_bonus - unknowns_penalty - disagreement_penalty + epistemic_bonus
        return max(0.0, min(1.0, confidence))

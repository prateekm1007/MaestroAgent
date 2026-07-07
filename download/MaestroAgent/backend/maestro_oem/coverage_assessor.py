"""Coverage Assessor — the CEO's escalation mechanism.

CEO DIRECTIVE:
> The critical component is the Coverage Assessor.
> It should ask mechanically:
>   Did we understand the entities?
>   Did we understand the timeline?
>   Did we identify the relevant situation type?
>   Did known relationship rules explain the important evidence?
>   Are there high-salience evidence items unused by the synthesis?
>   Are there contradictions without an explanation?
>   Are there materially different definitions of the same concept?
>   Did the user ask a causal, comparative, counterfactual, or strategic question
>     beyond rule coverage?
>   Is the deterministic answer merely restating evidence?
>   Are important signals classified but semantically disconnected?

This is a much better escalation mechanism than:
  "If something is unclassified, call the LLM."

The Coverage Assessor evaluates REASONING COVERAGE, not category coverage.
A query can have perfectly classified evidence and still require reasoning
beyond the rule system (unknown relationship structure).

The assessor returns:
  - coverage_score: 0.0 (no coverage) to 1.0 (full coverage)
  - should_escalate: True if LLM is needed
  - gaps: list of specific coverage gaps
  - reasoning: why escalation is or isn't needed
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CoverageAssessment:
    """The result of assessing reasoning coverage.

    Every field is populated — no silent gaps.
    """
    coverage_score: float = 1.0  # 0.0 = no coverage, 1.0 = full coverage
    should_escalate: bool = False  # True if LLM is needed
    gaps: list[str] = field(default_factory=list)  # specific coverage gaps
    reasoning: str = ""  # why escalation is or isn't needed
    # Individual checks (for telemetry)
    entities_understood: bool = True
    timeline_understood: bool = True
    situation_type_identified: bool = True
    relationship_rules_explained: bool = True
    no_unused_high_salience: bool = True
    no_unexplained_contradictions: bool = True
    no_definition_mismatches: bool = True
    no_beyond_rule_question: bool = True
    not_merely_restating: bool = True
    no_disconnected_signals: bool = True

    def to_audit_dict(self) -> dict[str, Any]:
        return {
            "coverage_score": self.coverage_score,
            "should_escalate": self.should_escalate,
            "gaps": self.gaps,
            "reasoning": self.reasoning,
            "checks": {
                "entities_understood": self.entities_understood,
                "timeline_understood": self.timeline_understood,
                "situation_type_identified": self.situation_type_identified,
                "relationship_rules_explained": self.relationship_rules_explained,
                "no_unused_high_salience": self.no_unused_high_salience,
                "no_unexplained_contradictions": self.no_unexplained_contradictions,
                "no_definition_mismatches": self.no_definition_mismatches,
                "no_beyond_rule_question": self.no_beyond_rule_question,
                "not_merely_restating": self.not_merely_restating,
                "no_disconnected_signals": self.no_disconnected_signals,
            },
        }


class CoverageAssessor:
    """Assesses whether the deterministic reasoning layer has sufficient coverage.

    CEO DIRECTIVE:
    > Route on reasoning coverage, not category coverage.

    The assessor checks 10 mechanical questions. If any fails, the LLM is
    escalated. The questions are designed to catch:
    - Unknown classification (the old trigger)
    - Unknown relationship structure (the new trigger)
    - Questions beyond rule coverage (causal, comparative, counterfactual)
    - Evidence the rules can't connect (semantically disconnected)
    """

    # Question types that require reasoning beyond deterministic rules
    BEYOND_RULE_PATTERNS = [
        r"\bwhy\b", r"\bhow come\b", r"\bwhat if\b", r"\bsuppose\b",
        r"\bimagine\b", r"\bhypothesize\b", r"\bsimulate\b",
        r"\bcompare\b", r"\bversus\b", r"\bvs\b", r"\bbetter\b", r"\bworse\b",
        r"\bshould we\b", r"\bought we\b", r"\brecommend\b", r"\badvise\b",
        r"\bpredict\b", r"\bforecast\b", r"\bexpect\b",
        r"\broot cause\b", r"\bexplain why\b", r"\bunderstand why\b",
        r"\bwhich\b.*\b(healthiest|best|worst|riskiest|most|least)\b",
        r"\bwhat should\b", r"\bwhat would\b",
    ]

    # Signals that suggest definition mismatch (same concept, different meaning)
    DEFINITION_MISMATCH_PATTERNS = [
        r"\bunderstood.*as\b", r"\bmeant.*by\b", r"\bdefinition.*different\b",
        r"\binterpreted.*as\b", r"\bassumed.*meant\b",
        r"\bproduction.*availability\b", r"\bcomplete.*means\b",
    ]

    # Contradiction indicators
    CONTRADICTION_INDICATORS = [
        ("commitment", "negation"),  # commitment + pending condition
        ("outcome", "reported_statement"),  # completion claim + customer disagreement
        ("commitment", "outcome"),  # commitment + broken outcome
    ]

    def assess(
        self,
        query: str,
        evidence: list[dict[str, Any]],
        answer_parts: list[str] | None = None,
    ) -> CoverageAssessment:
        """Assess reasoning coverage. Returns CoverageAssessment.

        This is the main entry point. Called from _synthesize_async() to
        determine whether the LLM should be escalated.
        """
        assessment = CoverageAssessment()
        gaps = []

        if not evidence:
            assessment.coverage_score = 0.0
            assessment.should_escalate = False  # No evidence = no LLM either
            assessment.reasoning = "No evidence to reason about"
            return assessment

        # Group evidence by epistemic type
        claim_types = [e.get("evidence_spine", {}).get("claim_type", "unclassified") for e in evidence]
        known_types = {"commitment", "proposal", "negation", "outcome", "reported_statement"}
        unclassified_count = sum(1 for ct in claim_types if ct not in known_types)

        # ─── CHECK 1: Did we understand the entities? ────────────────────
        entities_in_evidence = set()
        for e in evidence:
            for p in e.get("people", []):
                entities_in_evidence.add(p)
        if not entities_in_evidence:
            assessment.entities_understood = False
            gaps.append("No people/actors identified in evidence")

        # ─── CHECK 2: Did we understand the timeline? ────────────────────
        dates = [e.get("date", "") for e in evidence if e.get("date")]
        if len(dates) < len(evidence) * 0.5:
            assessment.timeline_understood = False
            gaps.append("Less than 50% of evidence has dates — timeline unclear")

        # ─── CHECK 3: Did we identify the relevant situation type? ────────
        # A situation type is identified if at least one commitment or proposal exists
        has_commitment = "commitment" in claim_types
        has_proposal = "proposal" in claim_types
        if not has_commitment and not has_proposal and unclassified_count > len(evidence) * 0.5:
            assessment.situation_type_identified = False
            gaps.append("No commitments or proposals identified, and >50% unclassified — situation type unclear")

        # ─── CHECK 4: Did known relationship rules explain the important evidence? ──
        # The RuleBasedSynthesizer has rules for:
        #   commitment + negation → pending conditions risk
        #   outcome + reported_statement → commitment dispute risk
        #   proposal + commitment → cautious-language risk
        # Check if there are relationship patterns the rules DON'T cover
        type_set = set(claim_types)
        has_covered_relationship = False
        for a, b in self.CONTRADICTION_INDICATORS:
            if a in type_set and b in type_set:
                has_covered_relationship = True
                break

        # If there are multiple types but no covered relationship, the rules
        # might not explain the evidence relationships
        if len(type_set) > 2 and not has_covered_relationship and unclassified_count == 0:
            assessment.relationship_rules_explained = False
            gaps.append("Multiple epistemic types present but no known relationship rule applies")

        # ─── CHECK 5: Are there high-salience evidence items unused? ──────
        # The RuleBasedSynthesizer uses: commitments, proposals, negations,
        # outcomes, reported_statements. If there are many unclassified items,
        # they're unused by the rules (though now surfaced in NOTES).
        if unclassified_count > 0:
            assessment.no_unused_high_salience = False
            gaps.append(f"{unclassified_count} unclassified evidence item(s) not used by relationship rules")

        # ─── CHECK 6: Are there contradictions without an explanation? ────
        # Check for outcome + negation (completion claim + pending condition)
        # without a commitment to contextualize them
        has_outcome = "outcome" in type_set
        has_negation = "negation" in type_set
        if has_outcome and has_negation and not has_commitment:
            assessment.no_unexplained_contradictions = False
            gaps.append("Outcome + negation present without a commitment to contextualize the contradiction")

        # ─── CHECK 7: Are there materially different definitions? ─────────
        all_text = " ".join(e.get("text", "") for e in evidence).lower()
        for pattern in self.DEFINITION_MISMATCH_PATTERNS:
            if re.search(pattern, all_text):
                # Definition mismatch detected — the rules CAN handle this
                # (it's the outcome + reported_statement relationship), but
                # only if both are classified. If either is unclassified,
                # the rule can't fire.
                has_reported = "reported_statement" in type_set
                if not has_reported:
                    assessment.no_definition_mismatches = False
                    gaps.append("Definition mismatch language detected but reported_statement not classified — rule can't fire")
                break

        # ─── CHECK 8: Did the user ask a beyond-rule question? ────────────
        query_lower = query.lower()
        for pattern in self.BEYOND_RULE_PATTERNS:
            if re.search(pattern, query_lower):
                assessment.no_beyond_rule_question = False
                gaps.append(f"Question contains '{pattern}' — requires reasoning beyond deterministic rules")
                break

        # ─── CHECK 9: Is the deterministic answer merely restating? ───────
        # If ALL evidence is the same type (e.g., all commitments), the
        # synthesizer can only list them — no cross-category reasoning possible
        if len(type_set) == 1 and unclassified_count == 0:
            single_type = list(type_set)[0]
            assessment.not_merely_restating = False
            gaps.append(f"All evidence is type '{single_type}' — synthesizer can only restate, not reason across categories")

        # ─── CHECK 10: Are important signals classified but disconnected? ─
        # If there are 3+ distinct known types but no covered relationship,
        # the signals are classified but the rules can't connect them
        if len(type_set & known_types) >= 3 and not has_covered_relationship:
            assessment.no_disconnected_signals = False
            gaps.append("3+ known epistemic types but no known relationship rule connects them")

        # ─── COMPUTE COVERAGE SCORE ──────────────────────────────────────
        checks = [
            assessment.entities_understood,
            assessment.timeline_understood,
            assessment.situation_type_identified,
            assessment.relationship_rules_explained,
            assessment.no_unused_high_salience,
            assessment.no_unexplained_contradictions,
            assessment.no_definition_mismatches,
            assessment.no_beyond_rule_question,
            assessment.not_merely_restating,
            assessment.no_disconnected_signals,
        ]
        passed = sum(1 for c in checks if c)
        assessment.coverage_score = passed / len(checks)

        # ─── DECIDE: should we escalate to LLM? ──────────────────────────
        # Escalate if any check fails. The CEO's directive is clear:
        # "Route on reasoning coverage, not category coverage."
        # A single gap means the deterministic path is insufficient.
        assessment.gaps = gaps  # AUDITOR-FIX: was missing — local gaps never assigned to assessment
        assessment.should_escalate = len(gaps) > 0

        if assessment.should_escalate:
            assessment.reasoning = f"Coverage insufficient ({passed}/{len(checks)} checks passed). Gaps: {'; '.join(gaps)}"
        else:
            assessment.reasoning = f"Coverage sufficient ({passed}/{len(checks)} checks passed). Deterministic synthesis is adequate."

        return assessment

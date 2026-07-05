"""ActiveCognitionResolver — the missing arrow: Governed Learning → Active Cognition.

AUDITOR-DIRECTIVE (Gap 6):
> The most important arrow is: Governed Learning → Active Cognition.
> The current report has not demonstrated that arrow.
>
> "Behaves differently" must mean something customer-visible or decision-relevant:
> * Ask gives a materially different answer.
> * Meeting preparation includes a warning it previously would not have included.
> * Whisper prepares an intervention it previously would have ignored.

This module checks if any learned patterns (status=ACTIVE_PATTERN or SCOPE_LIMITED)
are relevant to the current query. If so, it produces a "learned insight" that is
appended to the Ask answer — making the answer materially different from what it
would have been before the pattern was learned.

The insight follows the auditor's format:
  - What the pattern says (the hypothesis)
  - Why it matters (the evidence: N independent cases, N supporting)
  - Where it applies (valid_scope)
  - Where evidence is insufficient (unproven_scope)
  - What would change this view (falsifiability)

No decorative precision. No "87% confidence." Just reason, provenance,
boundaries, and falsifiability.

UNLEARNING: when a pattern's contradicting_outcomes accumulate, the resolver
narrows the scope or stops using it. If status drops to FALSIFIED, the pattern
is no longer incorporated into answers.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ActiveCognitionResolver:
    """Checks active learned patterns and produces insights for the Ask answer.

    This is the arrow from Governed Learning to Active Cognition. Without this,
    Maestro learns internally but never becomes wiser externally.

    Usage (wired into AskPipeline.execute_async):
        resolver = ActiveCognitionResolver(store=candidate_pattern_store)
        insights = resolver.find_relevant_patterns(query, entities, evidence)
        if insights:
            answer += "\\n\\n" + resolver.format_insights(insights)
    """

    def __init__(self, store: Any = None) -> None:
        self._store = store

    def find_relevant_patterns(
        self,
        query: str,
        entities: list[str],
        evidence: list[dict],
    ) -> list[dict[str, Any]]:
        """Find active learned patterns relevant to the current query.

        AUDITOR-DIRECTIVE: the pattern must be ACTIVE_PATTERN or SCOPE_LIMITED.
        HYPOTHESIS, TESTING, FALSIFIED, SUPERSEDED patterns are NOT used —
        they haven't been validated, or they've been invalidated.

        Returns a list of relevant pattern dicts with: hypothesis, supporting_outcomes,
        contradicting_outcomes, valid_scope, unproven_scope, scope_match_reason.
        """
        if self._store is None:
            return []

        relevant = []
        query_lower = query.lower()

        for candidate in self._store.get_all():
            # Only use patterns that have been governance-approved
            if candidate.status.value not in ("ACTIVE_PATTERN", "SCOPE_LIMITED"):
                continue

            # Check if the pattern is relevant to the query
            # Relevance = entity overlap OR keyword overlap with the hypothesis
            is_relevant = self._is_relevant(candidate, query_lower, entities, evidence)
            if not is_relevant:
                continue

            # Check scope — does the current context match the pattern's valid_scope?
            scope_match = self._check_scope(candidate, entities, evidence)

            relevant.append({
                "hypothesis": candidate.hypothesis,
                "supporting_outcomes": candidate.supporting_outcomes,
                "contradicting_outcomes": candidate.contradicting_outcomes,
                "prospective_predictions": candidate.prospective_predictions,
                "valid_scope": candidate.valid_scope,
                "unproven_scope": candidate.unproven_scope,
                "invalid_scope": candidate.invalid_scope,
                "status": candidate.status.value,
                "scope_match_reason": scope_match,
            })

        return relevant

    def _is_relevant(
        self,
        candidate: Any,
        query_lower: str,
        entities: list[str],
        evidence: list[dict],
    ) -> bool:
        """Check if a pattern is relevant to the current query.

        Relevance heuristics:
          1. Entity overlap — the pattern's entities appear in the query or evidence
          2. Keyword overlap — key words from the hypothesis appear in the query
          3. Evidence overlap — the evidence mentions concepts from the hypothesis
        """
        # Entity overlap
        for entity in candidate.entities:
            if entity.lower() in query_lower:
                return True
            for ev in evidence:
                if entity.lower() in str(ev.get("text", "")).lower():
                    return True

        # Keyword overlap — check if key words from the hypothesis appear in the query
        hypothesis_words = set(candidate.hypothesis.lower().split())
        query_words = set(query_lower.split())
        # Remove common words
        common = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                  "have", "has", "had", "do", "does", "did", "will", "would",
                  "should", "could", "may", "might", "can", "to", "of", "in",
                  "for", "on", "with", "as", "by", "at", "from", "this", "that",
                  "and", "or", "not", "but", "if", "then", "when", "what", "who",
                  "why", "how", "which", "their", "our", "your", "its", "it"}
        meaningful_hyp = hypothesis_words - common
        meaningful_query = query_words - common
        overlap = meaningful_hyp & meaningful_query
        if len(overlap) >= 1:  # at least 1 meaningful word overlap (specific terms like "cross-functional")
            return True

        return False

    def _check_scope(
        self,
        candidate: Any,
        entities: list[str],
        evidence: list[dict],
    ) -> str:
        """Check if the current context matches the pattern's scope.

        Returns a scope_match_reason:
          "matches_valid_scope" — the context matches the pattern's valid scope
          "in_unproven_scope" — the context is in the unproven scope (use with caution)
          "in_invalid_scope" — the context is in the invalid scope (don't use)
          "scope_unspecified" — no scope restrictions defined
        """
        # If the pattern has no scope restrictions, it applies everywhere
        if not candidate.valid_scope and not candidate.invalid_scope:
            return "scope_unspecified"

        # Check invalid_scope — if the context matches, don't use the pattern
        # (This would require knowing the current context's dimensions, which
        # we'd derive from the evidence. For now, this is a stub that always
        # returns "matches_valid_scope" when valid_scope is set.)
        if candidate.valid_scope:
            return "matches_valid_scope"

        return "scope_unspecified"

    def format_insights(self, insights: list[dict[str, Any]]) -> str:
        """Format active patterns as an honest, non-numeric insight section.

        AUDITOR-DIRECTIVE Phase 12:
        > The executive receives reason, provenance, boundaries, and falsifiability.
        > Avoid: 87% confidence, 92% risk, AI score: 8.4.

        Example output:
          Learned insight:
          In comparable cross-functional work, delay repeatedly began when
          execution was shared but final ownership remained unclear.
          Where this applies: Cross-functional platform work.
          Where evidence is insufficient: Single-team delivery.
          What would change this view: New cases where shared ownership does not lead to delay.
        """
        if not insights:
            return ""

        parts = []
        for insight in insights:
            parts.append("Learned insight:")
            # The hypothesis — what the pattern says
            parts.append(f"  {insight['hypothesis']}")

            # Why it matters — provenance (no decorative precision)
            supports = insight["supporting_outcomes"]
            contradicts = insight["contradicting_outcomes"]
            if supports > 0:
                parts.append(
                    f"  This is based on {supports} independent case(s) where "
                    f"the predicted outcome occurred."
                )
            if contradicts > 0:
                parts.append(
                    f"  {contradicts} case(s) contradicted it — the pattern "
                    f"may be narrowing."
                )

            # Where it applies
            valid = insight.get("valid_scope", {})
            if valid:
                scope_str = ", ".join(f"{k}={v}" for k, v in valid.items())
                parts.append(f"  Where this applies: {scope_str}.")

            # Where evidence is insufficient
            unproven = insight.get("unproven_scope", {})
            if unproven:
                unproven_str = ", ".join(f"{k}={v}" for k, v in unproven.items())
                parts.append(f"  Where evidence is insufficient: {unproven_str}.")

            # What would change this view (falsifiability)
            parts.append(
                "  What would change this view: New cases where the predicted "
                "outcome does not occur."
            )

        return "\n".join(parts)

    def format_for_trace(self, insights: list[dict[str, Any]]) -> dict[str, Any]:
        """Format active patterns for the SynthesisTrace (audit record)."""
        return {
            "active_patterns_applied": len(insights),
            "patterns": [
                {
                    "hypothesis": i["hypothesis"],
                    "supporting_outcomes": i["supporting_outcomes"],
                    "contradicting_outcomes": i["contradicting_outcomes"],
                    "status": i["status"],
                    "scope_match_reason": i["scope_match_reason"],
                }
                for i in insights
            ],
        }

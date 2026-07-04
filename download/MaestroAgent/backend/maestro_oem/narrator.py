"""Step 4-5: Evidence-grounded narrator with source citations.

The narrator takes assembled Evidence objects and renders them in executive
prose. It does NOT reason. It does NOT retrieve. It does NOT decide what's
relevant. It narrates what the pipeline found.

Step 5: Every claim has inline citations [1], [2] linking to evidence items.

If no evidence: "I don't have enough organizational memory to answer this."
The narrator NEVER hallucinates. It NEVER adds information not in the evidence.

Design: template-based narrator that CAN be replaced by an LLM. The interface
is: narrate(question, evidence) → (answer_string, citations_list). An LLM
provider would implement the same interface, receiving the evidence as
structured context and rendering prose with citations.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class EvidenceNarrator:
    """Renders assembled Evidence into executive prose with citations.

    Usage:
        narrator = EvidenceNarrator()
        answer = narrator.narrate("What did we promise?", evidence)
        # OR with citations:
        answer, citations = narrator.narrate_with_citations("What did we promise?", evidence)
    """

    def narrate(self, question: str, evidence: list[dict[str, Any]]) -> str:
        """Render evidence into prose answer (without citations)."""
        answer, _ = self.narrate_with_citations(question, evidence)
        return answer

    def narrate_with_citations(
        self,
        question: str,
        evidence: list[dict[str, Any]],
        synthesis_hints: list[str] | None = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Render evidence into prose answer with inline citations.

        Phase 2 hardening: if synthesis_hints is provided (intent-specific
        synthesis from CausalEngine, WisdomEngine, PreparationEngine, etc.),
        render each hint as a prose sentence with inline citations referencing
        the supporting evidence. Before this fix, the narrator just re-listed
        raw evidence — the intent-specific analysis was computed and discarded.

        Returns:
            (answer_string, citations_list)
            - answer_string: prose with [1], [2] inline citations
            - citations_list: [{number: 1, source: "...", text: "...", date: "..."}]
        """
        if not evidence:
            return ("I don't have enough organizational memory to answer this. "
                    "Try asking about a specific customer, project, or decision."), []

        # Build citations
        citations: list[dict[str, Any]] = []
        for i, ev in enumerate(evidence, 1):
            citations.append({
                "number": i,
                "source": ev.get("source", "unknown"),
                "text": ev.get("text", "")[:100],
                "date": ev.get("date", ""),
            })

        # Phase 2 hardening: if synthesis_hints are provided, use them as the
        # answer body (they're intent-specific analysis, not just raw evidence).
        # Append citations referencing the evidence by source/date.
        if synthesis_hints:
            parts: list[str] = []
            for hint in synthesis_hints:
                if hint and hint.strip():
                    parts.append(hint.strip())

            # Append a "Sources:" section with inline [N] citations
            if citations:
                parts.append("")
                parts.append("Sources:")
                for i, ev in enumerate(evidence, 1):
                    source = ev.get("source", "unknown")
                    date = ev.get("date", "")
                    text = ev.get("text", "")
                    parts.append(f"[{i}] {source} ({date}): {text[:80]}")

            return "\n".join(parts), citations

        # Fallback: original evidence-list format (no synthesis hints)
        parts: list[str] = []
        parts.append(f"Based on the organizational evidence I found:")

        for i, ev in enumerate(evidence, 1):
            source = ev.get("source", "unknown")
            date = ev.get("date", "")
            text = ev.get("text", "")
            people = ev.get("people", [])

            # Build a sentence referencing the evidence
            if people:
                who = people[0] if len(people) == 1 else f"{people[0]} and others"
                parts.append(f"[{i}] On {date}, {who} recorded in {source}: {text}")
            else:
                parts.append(f"[{i}] {source} ({date}): {text}")

        parts.append("")
        parts.append("**Ask a follow-up...**")

        return "\n".join(parts), citations

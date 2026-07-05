"""Rule-based synthesizer — produces synthesis without an LLM.

AUDITOR-DIRECTIVE (Priority 2):
> When the LLM is unavailable (which will be often under rate limiting),
> the template fallback must produce SYNTHESIS, not a data dump.
> Identify the commitment, check outcomes, flag disagreements,
> recommend action. Deterministic. No entropy. No API dependency.

Example output (rule-based synthesis, no LLM):
  We promised Globex SSO before renewal (Day 12, Day 30).

  STATUS: Mixed. Sales reports SSO work is complete (Day 50),
  but security approval is still conditional (Day 40).

  RISK: The customer expects production availability (Day 55),
  which may not match "work is complete" if security approval
  is still pending.

  RECOMMENDED ACTION: Clarify with security whether the completed
  work meets production standards before the renewal meeting.

This is DETERMINISTIC — same evidence → same synthesis. No entropy.
The LLM improves the prose; this provides the substance.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class RuleBasedSynthesizer:
    """Deterministic synthesizer — no LLM, no entropy, no API dependency.

    Produces a structured synthesis from evidence:
    1. WHAT WE PROMISED (commitments)
    2. STATUS (outcomes + negations)
    3. RISK (disagreements + contradictions)
    4. RECOMMENDED ACTION

    The synthesis is built from rules, not from an LLM. Same evidence →
    same output every time. Zero entropy.
    """

    def synthesize(
        self,
        query: str,
        evidence: list[dict[str, Any]],
        answer_parts: list[str] | None = None,
    ) -> str:
        """Produce a structured synthesis from evidence.

        Args:
            query: the original question
            evidence: list of evidence items with 'text', 'source', 'date',
                'people', and 'evidence_spine' with 'claim_type'
            answer_parts: the grouped answer_parts from _search_signals
                (optional — used for context)

        Returns:
            A structured synthesis string
        """
        if not evidence:
            return ("I don't have enough organizational memory to answer this. "
                    "Try asking about a specific customer, project, or decision.")

        # Group evidence by epistemic type
        commitments = [e for e in evidence if e.get("evidence_spine", {}).get("claim_type") == "commitment"]
        proposals = [e for e in evidence if e.get("evidence_spine", {}).get("claim_type") == "proposal"]
        negations = [e for e in evidence if e.get("evidence_spine", {}).get("claim_type") == "negation"]
        outcomes = [e for e in evidence if e.get("evidence_spine", {}).get("claim_type") == "outcome"]
        reported = [e for e in evidence if e.get("evidence_spine", {}).get("claim_type") == "reported_statement"]
        others = [e for e in evidence if e.get("evidence_spine", {}).get("claim_type") not in
                  ("commitment", "proposal", "negation", "outcome", "reported_statement")]

        sections = []

        # ─── 1. WHAT WE PROMISED ──────────────────────────────────────────
        promise_parts = []
        for e in commitments:
            text = self._clean_text(e.get("text", ""))
            date = e.get("date", "")
            people = e.get("people", [])
            who = people[0] if people else "the team"
            promise_parts.append(f"{who} committed to \"{text}\" ({date})")

        for e in proposals:
            text = self._clean_text(e.get("text", ""))
            date = e.get("date", "")
            people = e.get("people", [])
            who = people[0] if people else "the team"
            promise_parts.append(f"{who} suggested \"{text}\" ({date}) — cautious, not a firm promise")

        if promise_parts:
            sections.append("WHAT WE PROMISED:\n" + "\n".join(f"  • {p}" for p in promise_parts))

        # ─── 2. STATUS ─────────────────────────────────────────────────────
        status_parts = []
        for e in outcomes:
            text = self._clean_text(e.get("text", ""))
            date = e.get("date", "")
            people = e.get("people", [])
            who = people[0] if people else "the team"
            status_parts.append(f"{who} reported: \"{text}\" ({date})")

        for e in negations:
            text = self._clean_text(e.get("text", ""))
            date = e.get("date", "")
            people = e.get("people", [])
            who = people[0] if people else "the team"
            status_parts.append(f"{who} noted: \"{text}\" ({date}) — conditional or pending")

        if status_parts:
            sections.append("STATUS:\n" + "\n".join(f"  • {s}" for s in status_parts))

        # ─── 3. RISK ───────────────────────────────────────────────────────
        risk_parts = []

        # Check for contradictions: commitments vs negations
        if commitments and negations:
            risk_parts.append(
                "There are pending conditions that may affect whether "
                "the commitment can be fulfilled."
            )

        # Check for disagreements: reported statements that differ from outcomes
        if outcomes and reported:
            risk_parts.append(
                "The customer's understanding of the commitment may differ "
                "from what was internally reported as complete. This could "
                "lead to a commitment dispute."
            )

        # Check for proposals (cautious language) treated as commitments
        if proposals and commitments:
            risk_parts.append(
                "Some statements were cautious proposals, not firm commitments. "
                "Treating them as promises may create expectations that can't be met."
            )

        if risk_parts:
            sections.append("RISK:\n" + "\n".join(f"  • {r}" for r in risk_parts))

        # ─── 4. RECOMMENDED ACTION ─────────────────────────────────────────
        action_parts = []

        if negations and outcomes:
            action_parts.append(
                "Clarify whether the completed work meets all pending conditions "
                "(especially security or approval gates) before the next meeting."
            )

        if reported and (outcomes or commitments):
            action_parts.append(
                "Verify with the customer that their understanding of the commitment "
                "matches what was actually delivered."
            )

        if proposals and commitments:
            action_parts.append(
                "Distinguish between firm commitments and cautious proposals when "
                "discussing with the customer."
            )

        if action_parts:
            sections.append("RECOMMENDED ACTION:\n" + "\n".join(f"  • {a}" for a in action_parts))
        elif not risk_parts:
            # No risks found — the commitment is on track
            if commitments and not negations:
                sections.append("RECOMMENDED ACTION:\n  • No action needed — the commitment appears on track.")

        return "\n\n".join(sections) if sections else "Based on the evidence, no specific synthesis is available."

    def _clean_text(self, text: str) -> str:
        """Extract the meaningful text from a signal's evidence text.

        The evidence text includes artifact IDs and signal types mixed in.
        Extract just the body text for the synthesis.
        """
        # Remove artifact prefixes like "msg-day5 Globex"
        import re
        # Remove common prefixes
        text = re.sub(r'^(msg-\w+|crm:\w+|github:\w+|jira:\w+|slack:\w+)\s+', '', text)
        # Remove entity names that are just context (generic — no demo entity names)
        text = re.sub(r'\b(CustomerA|CustomerB|CustomerC)\b', '', text, flags=re.IGNORECASE)
        # Remove signal type strings
        text = re.sub(r'\b(customer\.\w+|message\.sent|pr\.\w+|issue\.\w+)\b', '', text, flags=re.IGNORECASE)
        # Remove email addresses (keep for people context but not in body)
        text = re.sub(r'\b[\w.]+@[\w.]+\b', '', text)
        # Clean up whitespace
        text = ' '.join(text.split())
        return text.strip()

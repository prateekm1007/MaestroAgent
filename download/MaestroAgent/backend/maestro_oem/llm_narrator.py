"""Priority 5: LLM Narration — constrained, evidence-grounded prose generation.

CEO directive (2026-07-04):
> LLM narration (deferred) — Prove the governed learning loop first.
> Then add LLM as constrained narrator.

The CEO's original vision: "LLM is the narrator, not the architecture."
The LLM receives structured evidence and renders prose. It NEVER reasons,
retrieves, or decides. It only narrates what the evidence says.

Constraints (the "constrained" in "constrained narrator"):
  1. GROUNDED: The LLM receives ONLY the evidence + the question. It must
     NEVER add information not in the evidence.
  2. CITED: Every claim in the output must have an inline citation [1][2]
     linking to an evidence item.
  3. FAIL-CLOSED (P6): When the LLM is unavailable (no provider, API error,
     timeout), fall back to the template-based EvidenceNarrator.
  4. CONSTRAINED: The system prompt explicitly tells the LLM: "You are a
     narrator. Do not reason. Do not retrieve. Do not decide. Narrate what
     the evidence says."
  5. HALLUCINATION GUARD: After the LLM generates prose, verify that each
     citation [N] maps to an actual evidence item. Strip hallucinated citations.

The LLMNarrator implements the same interface as EvidenceNarrator:
  narrate(question, evidence) → str
  narrate_with_citations(question, evidence) → (str, list[dict])

This makes it a drop-in replacement. The AskPipeline can use either.

Wiring (P11):
  - AskPipeline._get_narrator() can return an LLMNarrator when an LLM
    provider is configured, or an EvidenceNarrator when not.
  - The LLMNarrator wraps EvidenceNarrator as its fallback.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# ─── The constrained system prompt ─────────────────────────────────────────
# This is the heart of the "constrained narrator" design. The LLM is told
# exactly what it can and cannot do. It is a narrator, not a reasoner.

_SYSTEM_PROMPT = """You are Maestro's narrator. Your job is to narrate what the evidence says — nothing more.

CONSTRAINTS:
1. Narrate ONLY what the evidence explicitly states. Do not add information.
2. Do not reason, infer, or draw conclusions beyond the evidence.
3. Do not retrieve or search for additional information.
4. Do not make decisions or recommendations.
5. Every factual claim MUST have an inline citation [N] linking to the evidence item.
6. Citation numbers [1], [2], etc. correspond to the evidence items provided (1-indexed).
7. If the evidence is insufficient to answer the question, say so honestly.
8. Write in clear, executive-grade prose. Be concise.

You are a narrator, not an advisor. You render what the evidence says. The reasoning, retrieval, and decision-making have already been done by the pipeline. Your job is to make the evidence readable.

Format your response as prose with inline citations. Example:
"Based on the evidence, the team committed to delivering SSO by Q4 [1]. This commitment was confirmed in a follow-up email [2]."

Do NOT include a citations list — the system will append that separately.
Do NOT use markdown headers or bullet points — write flowing prose.
Do NOT add phrases like "Based on the evidence" if they don't fit — just narrate naturally with citations.
"""


class LLMNarrator:
    """Constrained LLM narrator — renders evidence into prose with citations.

    Implements the same interface as EvidenceNarrator:
        narrate(question, evidence) → str
        narrate_with_citations(question, evidence) → (str, list[dict])

    When an LLM provider is available, uses it to generate evidence-grounded
    prose. When unavailable (or on error), falls back to the template-based
    EvidenceNarrator (P6: fail-closed).

    The LLM is CONSTRAINED:
      - Receives ONLY the evidence + question (never raw signals or model state)
      - System prompt explicitly forbids reasoning, retrieval, decisions
      - Hallucinated citations are stripped (citation [N] must map to evidence item N)
      - Empty evidence → no LLM call (prevents hallucination from no context)
    """

    def __init__(self, llm_provider: Any = None) -> None:
        """Initialize the LLM narrator.

        Args:
            llm_provider: An optional LLM provider with an async complete()
                method. If None, falls back to the template EvidenceNarrator
                for all calls (P6: fail-closed).
        """
        self._llm_provider = llm_provider
        # Lazy-load the template narrator (fallback)
        self._template_narrator = None

    def _get_template_narrator(self):
        """Lazy-load the template EvidenceNarrator (fallback)."""
        if self._template_narrator is None:
            from maestro_oem.narrator import EvidenceNarrator
            self._template_narrator = EvidenceNarrator()
        return self._template_narrator

    def narrate(self, question: str, evidence: list[dict[str, Any]]) -> str:
        """Render evidence into prose answer (without citations list)."""
        answer, _ = self.narrate_with_citations(question, evidence)
        return answer

    def narrate_with_citations(
        self,
        question: str,
        evidence: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]]]:
        """Render evidence into prose answer with inline citations.

        Phase 6.3: Evidence flagged as 'epistemic_override' (prompt injection
        attempting to manipulate evidence classification) is EXCLUDED from the
        narrator context. The flagged content remains in the evidence graph
        for audit purposes, but it cannot influence the synthesized answer.

        Returns:
            (answer_string, citations_list)
            - answer_string: prose with [1], [2] inline citations
            - citations_list: [{number: 1, source: "...", text: "...", date: "..."}]

        When the LLM is unavailable or fails, falls back to the template
        EvidenceNarrator (P6: fail-closed).
        """
        # C-001 fix: Filter out ALL evidence flagged with ANY prompt injection risk.
        # The previous filter (Phase 6.3) only excluded epistemic_override.
        # The external audit found that instruction_override, data_exfiltration,
        # role_hijack, and other injection categories also flow into the LLM
        # prompt unsanitized. Now ALL flagged evidence is excluded.
        safe_evidence = [
            e for e in evidence
            if not e.get("prompt_injection_risk", {}).get("is_suspicious", False)
            and not e.get("prompt_injection_risk", {}).get("detected_patterns", [])
        ]
        if len(safe_evidence) < len(evidence):
            logger.warning(
                "LLMNarrator: excluded %d evidence item(s) flagged with prompt injection risk",
                len(evidence) - len(safe_evidence),
            )

        # Empty evidence → no LLM call (prevents hallucination)
        if not safe_evidence:
            return self._get_template_narrator().narrate_with_citations(question, safe_evidence)

        # No LLM provider → fall back to template (P6)
        if self._llm_provider is None:
            return self._get_template_narrator().narrate_with_citations(question, safe_evidence)

        # Try the LLM
        try:
            answer = self._call_llm(question, safe_evidence)
            # Strip hallucinated citations
            answer = self._strip_hallucinated_citations(answer, len(safe_evidence))
            # Build citations list from evidence
            citations = self._build_citations(evidence)
            return answer, citations
        except Exception as e:
            logger.warning("LLMNarrator: LLM call failed, falling back to template: %s", e)
            return self._get_template_narrator().narrate_with_citations(question, evidence)

    def _call_llm(self, question: str, evidence: list[dict[str, Any]]) -> str:
        """Call the LLM provider with a constrained prompt.

        Handles the async-to-sync bridge. If called from within an async
        context, uses the running loop; otherwise creates a new one.
        """
        user_prompt = self._build_user_prompt(question, evidence)

        # Async-to-sync bridge
        try:
            loop = asyncio.get_running_loop()
            # We're in an async context — create a task
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run,
                    self._llm_provider.complete(
                        system=_SYSTEM_PROMPT,
                        user=user_prompt,
                    )
                )
                response = future.result(timeout=30)
        except RuntimeError:
            # No running loop — use asyncio.run directly
            response = asyncio.run(
                self._llm_provider.complete(
                    system=_SYSTEM_PROMPT,
                    user=user_prompt,
                )
            )

        return response.text

    def _build_user_prompt(self, question: str, evidence: list[dict[str, Any]]) -> str:
        """Build the user prompt with the question + structured evidence.

        The evidence is formatted as a numbered list so the LLM can cite
        [1], [2], etc.
        """
        parts = [f"Question: {question}", "", "Evidence:"]
        for i, ev in enumerate(evidence, 1):
            source = ev.get("source", "unknown")
            date = ev.get("date", "")
            text = ev.get("text", "")
            people = ev.get("people", [])
            people_str = f" (involving: {', '.join(people)})" if people else ""
            parts.append(f"[{i}] {source} ({date}){people_str}: {text}")
        parts.append("")
        parts.append("Narrate what the evidence says about the question. Include inline citations [1], [2], etc.")
        return "\n".join(parts)

    def _strip_hallucinated_citations(self, text: str, evidence_count: int) -> str:
        """Remove citations [N] where N > evidence_count (hallucinated).

        The LLM might generate [99] when there are only 2 evidence items.
        This strips those hallucinated citations.
        """
        def replace_hallucinated(match):
            num = int(match.group(1))
            if num > evidence_count or num < 1:
                return ""  # Strip hallucinated citation
            return match.group(0)  # Keep valid citation

        return re.sub(r"\[(\d+)\]", replace_hallucinated, text)

    def _build_citations(self, evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Build the citations list from evidence items."""
        citations = []
        for i, ev in enumerate(evidence, 1):
            citations.append({
                "number": i,
                "source": ev.get("source", "unknown"),
                "text": ev.get("text", "")[:100],
                "date": ev.get("date", ""),
            })
        return citations

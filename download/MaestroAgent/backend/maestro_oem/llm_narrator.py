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


# ─── The evidence-grounded synthesis prompt ─────────────────────────────────
# AUDITOR-P11-FIX: The original prompt forbade reasoning ("Do not reason.
# Do not infer."). The external auditor's experiment proved this was too
# tight — it produced "insufficient information" refusals when the evidence
# clearly supported an answer. The new prompt ALLOWS synthesis across
# evidence but keeps the grounding, citation, and no-recommendations constraints.

_SYSTEM_PROMPT = """You are Maestro's executive synthesis narrator. Your job is to synthesize what the evidence says into a clear, executive-grade answer — and you may reason across the evidence to identify patterns, relationships, and implications that an executive would need to make a decision.

WHAT YOU MAY DO:
1. Synthesize: combine evidence items to identify patterns (e.g., "commitment made [1] then broken [2] suggests delivery risk").
2. Reason across evidence: if multiple evidence items together imply a conclusion, state the conclusion and cite every supporting item.
3. Recognize temporal patterns: if evidence shows a sequence (commitment → kept → renewed), narrate the sequence with citations.
4. Compare: when the question asks for comparison across entities, compare them using the evidence provided.
5. Identify gaps: if the evidence is insufficient to answer fully, say so honestly and explain what's missing.

WHAT YOU MAY NOT DO:
1. NEVER invent evidence. If a fact is not in the provided evidence, do not state it. Do not use outside knowledge about the world, the company, or the people mentioned.
2. NEVER make business recommendations or decisions (e.g., "you should fire the champion" or "we recommend renewing"). Your job is to make the evidence legible — the human makes the decision.
3. NEVER include a fact without an inline citation [N] linking to the evidence item that supports it.
4. NEVER hallucinate citations — [N] must refer to a real evidence item (1-indexed).

CITATION RULES:
- Citation numbers [1], [2], etc. correspond to the evidence items provided (1-indexed).
- Every factual claim MUST have at least one inline citation.
- A claim supported by multiple evidence items should list them: [1, 4, 6].
- If the evidence is genuinely insufficient to answer the question, say: "I don't have enough organizational memory to answer this" and explain what evidence would be needed.

STYLE:
- Write in clear, executive-grade prose. Be concise but complete.
- Answer the question directly — do not list raw evidence. Synthesize.
- Use flowing prose, not markdown headers or bullet points (unless the question explicitly asks for a list).
- Do NOT include a citations list at the end — the system appends that separately.

Example of good synthesis:
"The customer relationship is healthy. They committed to feature delivery by December 2024 [1] and that commitment was kept on December 10, 2024 [4]. The contract was renewed on January 5, 2025 [9], with the decision confirmed on December 20, 2024 [8]. Their champion remained active throughout this period [7]."

Example of BAD output (do not do this):
"Based on 10 signal(s): • crm:commit-1 ... • crm:mtg-1 ..." (raw signal listing — not synthesis)

Example of BAD output (do not do this):
"The evidence does not provide sufficient information to definitively declare which relationship is healthiest." (refusal to synthesize when the evidence clearly supports an answer — your job is to synthesize, not to be timid)
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

    def narrate(self, question: str, evidence: list[dict[str, Any]], synthesis_hints: list[str] | None = None) -> str:
        """Render evidence into prose answer (without citations list)."""
        answer, _ = self.narrate_with_citations(question, evidence, synthesis_hints=synthesis_hints)
        return answer

    def narrate_with_citations(
        self,
        question: str,
        evidence: list[dict[str, Any]],
        synthesis_hints: list[str] | None = None,
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
            return self._get_template_narrator().narrate_with_citations(question, safe_evidence, synthesis_hints=synthesis_hints)

        # No LLM provider → fall back to template (P6)
        if self._llm_provider is None:
            return self._get_template_narrator().narrate_with_citations(question, safe_evidence, synthesis_hints=synthesis_hints)

        # Try the LLM
        try:
            answer = self._call_llm(question, safe_evidence, synthesis_hints=synthesis_hints)
            # Strip hallucinated citations
            answer = self._strip_hallucinated_citations(answer, len(safe_evidence))
            # Build citations list from evidence
            citations = self._build_citations(evidence)
            return answer, citations
        except Exception as e:
            logger.warning("LLMNarrator: LLM call failed, falling back to template: %s", e)
            return self._get_template_narrator().narrate_with_citations(question, evidence, synthesis_hints=synthesis_hints)

    def _call_llm(self, question: str, evidence: list[dict[str, Any]], synthesis_hints: list[str] | None = None) -> str:
        """Call the LLM provider with a constrained prompt.

        Handles the async-to-sync bridge. If called from within an async
        context, uses the running loop; otherwise creates a new one.
        """
        user_prompt = self._build_user_prompt(question, evidence, synthesis_hints=synthesis_hints)

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

    def _build_user_prompt(self, question: str, evidence: list[dict[str, Any]], synthesis_hints: list[str] | None = None) -> str:
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
        # Phase 2 fix: include synthesis hints from organizational engines
        # (CausalEngine, WisdomEngine, ImaginationEngine, etc.) so the LLM
        # has the same context the template narrator uses. Before this fix,
        # the LLM got evidence but not synthesis — the hints were silently
        # dropped when LLMNarrator was active.
        if synthesis_hints:
            parts.append("Synthesis context from organizational engines:")
            for hint in synthesis_hints:
                if hint and hint.strip():
                    parts.append(f"  - {hint.strip()}")
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

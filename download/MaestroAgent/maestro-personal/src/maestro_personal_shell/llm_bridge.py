"""
LLM bridge — connects the Cognitive Council to actual LLMs.

This is the fix the external auditor demanded: connect maestro_llm
to the Cognitive Council so intelligence is LLM-powered, not
keyword-based.

The bridge:
1. Detects if an LLM provider is available (env vars or local Ollama)
2. If available: routes intelligence through LLM (Ask, Judgment, Perspectives)
3. If unavailable: falls back to the existing rule-based logic (graceful)

This means the product works in BOTH modes:
- With LLM: genuine AI orchestrator (the masterpiece)
- Without LLM: sophisticated rule-based system (the fallback)

The LLM is called for:
- Ask: RAG-grounded answer generation (not keyword templates)
- JudgmentSynthesizer: LLM-powered judgment synthesis (not string formatting)
- Nerve agents: LLM-powered insight generation (not heuristic thresholds)
- ConsequencePathRouter: LLM-powered semantic routing (not dictionary lookup)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
from typing import Any

logger = logging.getLogger(__name__)

# Singleton router — initialized once, reused across all calls
_router = None
_router_checked = False


# ---------------------------------------------------------------------------
# ZAI Router — in-house LLM provider (z-ai-web-dev-sdk CLI)
# ---------------------------------------------------------------------------

class ZAIResponse:
    """Response object compatible with maestro_llm's response interface."""

    def __init__(self, text: str) -> None:
        self.text = text


class ZAIRouter:
    """LLM router backed by the z-ai CLI (z-ai-web-dev-sdk).

    This makes real LLM intelligence available in any environment where
    the z-ai CLI is installed — no external API keys required.

    The CLI is invoked via subprocess; calls run in a thread pool to
    avoid blocking the async event loop.
    """

    def __init__(self) -> None:
        self.default_provider = "zai-glm"

    async def complete(
        self,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: int = 500,
    ) -> ZAIResponse:
        return await asyncio.to_thread(
            self._complete_sync, system, user, temperature, max_tokens
        )

    def _complete_sync(
        self,
        system: str,
        user: str,
        temperature: float,
        max_tokens: int,
    ) -> ZAIResponse:
        fd, output_path = tempfile.mkstemp(suffix=".json", prefix="zai_llm_")
        os.close(fd)

        try:
            cmd = [
                "z-ai", "chat",
                "-p", user,
                "-s", system,
                "-o", output_path,
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                raise RuntimeError(
                    f"z-ai CLI exited {result.returncode}: {result.stderr[:300]}"
                )

            with open(output_path) as f:
                data = json.load(f)

            text = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            if not text:
                raise RuntimeError("z-ai CLI returned empty content")

            return ZAIResponse(text=text)
        finally:
            try:
                os.unlink(output_path)
            except OSError:
                pass

    def health_check(self) -> bool:
        """Quick health check — verify the z-ai CLI is installed.

        We do NOT make an API call here because:
        1. It would add latency to every server startup
        2. Rate limits (429) would cause false negatives
        3. The actual LLM calls handle their own failures gracefully

        Instead, we verify the CLI binary exists. If it exists, we
        assume it works — individual calls will fall back to rules
        if the API is unavailable or rate limited.
        """
        return shutil.which("z-ai") is not None


def get_llm_router() -> Any:
    """Get or initialize the LLM router.

    Provider priority:
    1. maestro_llm cloud providers (OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.)
    2. Local Ollama (http://localhost:11434)
    3. z-ai CLI (z-ai-web-dev-sdk) — in-house, no API key needed

    Returns None if no provider is available.
    """
    global _router, _router_checked
    if _router_checked:
        return _router
    _router_checked = True

    # 1. Try maestro_llm cloud providers
    try:
        import sys
        sys.path.insert(0, "backend")
        from maestro_llm.router import LLMRouter

        if LLMRouter.has_env_provider():
            _router = LLMRouter.from_env_sync()
            logger.info(
                "LLM router initialized with cloud provider: %s",
                _router.default_provider,
            )
            return _router
    except Exception as e:
        logger.debug("maestro_llm cloud init skipped: %s", e)

    # 2. Try local Ollama
    try:
        import urllib.request
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
        try:
            import sys
            sys.path.insert(0, "backend")
            from maestro_llm.router import LLMRouter
            _router = LLMRouter.with_defaults()
            logger.info("LLM router initialized with local Ollama")
            return _router
        except Exception:
            pass
    except Exception:
        pass

    # 3. Try z-ai CLI (in-house, no API key needed)
    try:
        zai = ZAIRouter()
        if zai.health_check():
            _router = zai
            logger.info("LLM router initialized with z-ai CLI provider (GLM)")
            return _router
    except Exception as e:
        logger.debug("z-ai CLI init failed: %s", e)

    # No LLM available — return None (fallback to rule-based)
    logger.warning("No LLM provider available — using rule-based fallback")
    _router = None
    return None


def is_llm_available() -> bool:
    """Check if an LLM provider is available."""
    return get_llm_router() is not None


def get_llm_provider_name() -> str:
    """Return the active LLM provider name for transparency.

    Returns the provider name (e.g. 'openai', 'zai-glm', 'ollama') if
    an LLM is active, or 'none' if running in rule-based fallback mode.

    This is exposed in API responses so the user knows whether they
    are getting LLM-powered intelligence or rule-based heuristics.
    """
    router = get_llm_router()
    if not router:
        return "none"
    return str(getattr(router, "default_provider", "unknown"))


def reset_llm_router() -> None:
    """Reset the cached router (for testing)."""
    global _router, _router_checked
    _router = None
    _router_checked = False


async def llm_complete(
    system: str,
    user: str,
    temperature: float = 0.2,
    max_tokens: int = 500,
) -> str | None:
    """Call the LLM with a system + user prompt.

    Returns the LLM's text response, or None if no LLM is available
    or the call fails.
    """
    router = get_llm_router()
    if not router:
        return None

    try:
        response = await router.complete(
            system=system,
            user=user,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.text
    except Exception as e:
        logger.debug("LLM complete failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# LLM-powered intelligence functions
# ---------------------------------------------------------------------------


async def llm_generate_answer(
    query: str,
    situation: Any,
    source_sentence: str = "",
    situation_state: str = "",
    evidence_refs: list[dict] | None = None,
) -> str | None:
    """Generate an LLM-powered answer to the user's query.

    This replaces the keyword-based _generate_answer() in ask_bridge.py.
    The LLM receives the situation context + evidence and generates
    a grounded, Situation-centric answer.

    Returns None if no LLM is available (caller falls back to rule-based).
    """
    # Build the situation context for the LLM
    entity = getattr(situation, "entity", "unknown")
    title = getattr(situation, "title", entity)
    state = situation_state or str(getattr(situation, "state", "unknown"))

    # Build evidence summary
    evidence_text = source_sentence or "No specific evidence found."
    if evidence_refs:
        evidence_text += "\n\nAdditional evidence:\n"
        for ref in evidence_refs[:3]:
            if isinstance(ref, dict):
                evidence_text += f"- {ref.get('text', str(ref))}\n"
            else:
                evidence_text += f"- {str(ref)}\n"

    system_prompt = """You are Maestro, a personal intelligence companion. You answer questions about the user's commitments, meetings, and professional relationships based on verified evidence.

Rules:
1. ONLY use the provided evidence. Do not fabricate information.
2. If the evidence is insufficient to answer, say "I don't have enough information to answer that based on my current evidence."
3. Cite the source: "Based on: [quote the source sentence]"
4. Be concise — 2-4 sentences maximum.
5. If there's a decision boundary (can't decide yet), mention it.
6. Preserve the epistemic state: distinguish facts from reported statements from commitments."""

    user_prompt = f"""Question: {query}

Situation: {title}
Entity: {entity}
Current state: {state}

Evidence:
{evidence_text}

Answer the user's question based ONLY on the evidence above. If you cannot answer from this evidence, say so honestly."""

    return await llm_complete(system_prompt, user_prompt, temperature=0.1, max_tokens=300)


async def llm_synthesize_judgment(
    situation: Any,
    perspectives: list[Any],
) -> dict[str, Any] | None:
    """Use the LLM to synthesize a judgment from multiple perspectives.

    This replaces the rule-based JudgmentSynthesizer.synthesize() when
    an LLM is available. The LLM receives all perspectives and produces
    a genuine judgment with central claim, confidence, and decision boundary.

    Returns None if no LLM is available.
    """
    entity = getattr(situation, "entity", "unknown")
    title = getattr(situation, "title", entity)
    state = str(getattr(situation, "state", "unknown"))

    # Build perspectives summary
    persp_text = ""
    for p in perspectives[:5]:
        specialist = getattr(p, "specialist", getattr(p, "name", "specialist"))
        observation = getattr(p, "observation", getattr(p, "view", ""))
        persp_text += f"- {specialist}: {observation}\n"

    system_prompt = """You are the Maestro Cognitive Council's Judgment Synthesizer. Your job is to take multiple specialist perspectives on a situation and produce a single synthesized judgment.

Output format (JSON):
{
  "central_claim": "The key conclusion about this situation",
  "confidence": 0.0-1.0,
  "can_decide_now": ["what can be decided"],
  "cannot_decide_yet": ["what needs more evidence"],
  "decision_boundary": "The decision boundary in one sentence"
}

Rules:
1. Base confidence on evidence quantity and quality, not optimism.
2. If evidence is insufficient (fewer than 3 perspectives), confidence should be low.
3. "can_decide_now" = actions that don't need more information.
4. "cannot_decide_yet" = actions that need more evidence first.
5. The decision boundary should be honest: "safe to proceed" or "wait for X"."""

    user_prompt = f"""Situation: {title}
Entity: {entity}
State: {state}

Specialist perspectives:
{persp_text}

Synthesize these perspectives into a judgment."""

    result = await llm_complete(system_prompt, user_prompt, temperature=0.1, max_tokens=400)
    if not result:
        return None

    # Try to parse as JSON
    import json
    try:
        # Find JSON in the response
        start = result.find("{")
        end = result.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(result[start:end])
    except Exception:
        pass

    # If not JSON, return as plain text judgment
    return {"central_claim": result[:300], "confidence": 0.5, "decision_boundary": ""}


async def llm_generate_perspective(
    specialist: str,
    situation: Any,
    signals: list[Any],
) -> dict[str, Any] | None:
    """Use the LLM to generate a specialist perspective.

    This replaces the heuristic-based Nerve agent insights with
    genuine LLM-powered analysis. The LLM receives the situation +
    signals and produces a perspective from the specialist's viewpoint.

    Returns None if no LLM is available.
    """
    entity = getattr(situation, "entity", "unknown")
    title = getattr(situation, "title", entity)
    state = str(getattr(situation, "state", "unknown"))

    # Build signals summary
    signals_text = ""
    for s in signals[:10]:
        sig_text = getattr(s, "text", "")
        sig_type = getattr(s, "signal_type", str(getattr(s, "type", "")))
        signals_text += f"- [{sig_type}] {sig_text}\n"

    system_prompt = f"""You are the {specialist} specialist in the Maestro Cognitive Council. Analyze the situation from your professional perspective and provide an insight.

Output format (JSON):
{{
  "observation": "What you see from your specialist perspective",
  "implication": "Why it matters",
  "recommended_next_step": "The smallest useful action",
  "urgency": "high" | "medium" | "low",
  "confidence": 0.0-1.0
}}

Rules:
1. Be specific — cite the actual signals.
2. Be honest about confidence — if you're guessing, say so.
3. Focus on YOUR specialty ({specialist}).
4. If nothing warrants attention from your perspective, return low urgency with an explanation."""

    user_prompt = f"""Situation: {title}
Entity: {entity}
State: {state}

Available signals:
{signals_text}

Provide your {specialist} perspective on this situation."""

    result = await llm_complete(system_prompt, user_prompt, temperature=0.2, max_tokens=300)
    if not result:
        return None

    import json
    try:
        start = result.find("{")
        end = result.rfind("}") + 1
        if start >= 0 and end > start:
            parsed = json.loads(result[start:end])
            parsed["agent"] = specialist
            return parsed
    except Exception:
        pass

    # Fallback: return as plain text
    return {
        "agent": specialist,
        "observation": result[:200],
        "implication": "",
        "recommended_next_step": "",
        "urgency": "medium",
        "confidence": 0.5,
    }


async def llm_route_consequence(
    situation: Any,
) -> list[str] | None:
    """Use the LLM to route consequence paths semantically.

    This replaces the static CONSEQUENCE_GRAPH dictionary lookup with
    genuine LLM-powered semantic routing. The LLM reads the situation
    and identifies which specialists should be consulted and why.

    Returns None if no LLM is available.
    """
    entity = getattr(situation, "entity", "unknown")
    title = getattr(situation, "title", entity)
    state = str(getattr(situation, "state", "unknown"))

    system_prompt = """You are the Maestro Consequence Path Router. Given a situation, identify which specialists should be consulted and the consequence paths that connect them.

Available specialists: chief_of_staff, customer_success, sales, engineering, product, strategy, finance, legal, operations, hr, data, marketing, communications, growth

Output format: a JSON array of specialist names who should be consulted.
Example: ["customer_success", "sales", "legal"]

Rules:
1. Only include specialists relevant to the situation.
2. Consider consequence paths: who is affected, who depends on this, who can absorb failure.
3. Maximum 5 specialists per situation."""

    user_prompt = f"""Situation: {title}
Entity: {entity}
State: {state}

Which specialists should be consulted?"""

    result = await llm_complete(system_prompt, user_prompt, temperature=0.0, max_tokens=100)
    if not result:
        return None

    import json
    try:
        start = result.find("[")
        end = result.rfind("]") + 1
        if start >= 0 and end > start:
            return json.loads(result[start:end])
    except Exception:
        pass

    return None

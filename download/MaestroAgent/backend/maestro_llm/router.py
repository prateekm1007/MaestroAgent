"""LLMRouter — the single entry point for LLM calls.

Responsibilities
----------------
1. **Route per-call.** Pick a provider based on the caller's hint.
2. **Failover.** If a provider fails, try the next in the chain.
3. **Cost tracking.** Every call updates the cost ledger; the engine
   checks the budget before each call.
4. **Caching.** Idempotent calls (temperature 0) are cached for replay.
5. **Embedding.** Exposes `embed()` for the memory tiers.

The router is injected into every `RunContext`. Agents and verifiers
call `ctx.llm.complete(...)` without knowing which provider answered.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from maestro_llm.cost import CostLedger
from maestro_llm.providers import (
    AnthropicProvider,
    GrokProvider,
    GroqProvider,
    LLMRequest,
    LLMResponse,
    LMStudioProvider,
    OpenAIProvider,
    OpenRouterProvider,
    OllamaProvider,
    Provider,
)

logger = logging.getLogger(__name__)


@dataclass
class LLMRouter:
    """Model-agnostic LLM router with cost tracking and failover."""

    providers: dict[str, Provider] = field(default_factory=dict)
    ledger: CostLedger | None = None
    # Failover chain (tried in order).
    default_chain: list[str] = field(
        default_factory=lambda: ["groq", "ollama", "openai", "anthropic", "openrouter"]
    )
    default_provider: str = "ollama"
    default_model: str = "llama3.1:8b"
    # Per-provider default models (when caller doesn't specify).
    default_models: dict[str, str] = field(
        default_factory=lambda: {
            "ollama": "llama3.1:8b",
            "lmstudio": "local-model",
            "openai": "gpt-4o-mini",
            "anthropic": "claude-3-5-haiku",
            "openrouter": "openrouter/auto",
            "groq": "llama-3.3-70b-versatile",
            "grok": "grok-beta",
            "gemini": "gemini-2.0-flash",
            "deepseek": "deepseek-chat",
        }
    )
    # Cache for temperature=0 calls.
    _cache: dict[str, LLMResponse] = field(default_factory=dict)
    # Per-provider failure counts (for ad-hoc circuit breaking).
    _failure_counts: dict[str, int] = field(default_factory=dict)

    @classmethod
    def with_defaults(
        cls,
        ollama_base_url: str = "http://localhost:11434",
        openai_api_key: str | None = None,
        anthropic_api_key: str | None = None,
        openrouter_api_key: str | None = None,
        grok_api_key: str | None = None,
        ledger: CostLedger | None = None,
    ) -> "LLMRouter":
        providers: dict[str, Provider] = {
            "ollama": OllamaProvider(base_url=ollama_base_url),
            "lmstudio": LMStudioProvider(),
        }
        if openai_api_key:
            providers["openai"] = OpenAIProvider(api_key=openai_api_key)
        if anthropic_api_key:
            providers["anthropic"] = AnthropicProvider(api_key=anthropic_api_key)
        if openrouter_api_key:
            providers["openrouter"] = OpenRouterProvider(api_key=openrouter_api_key)
        if grok_api_key:
            providers["grok"] = GrokProvider(api_key=grok_api_key)
        return cls(providers=providers, ledger=ledger)

    @classmethod
    def from_env_sync(cls, ledger: CostLedger | None = None) -> "LLMRouter":
        """SYNC factory — read env vars and build a router without async I/O.

        AUDITOR-P11-FIX: The previous _get_llm_provider() in ask_pipeline.py
        called LLMRouter.from_env() (a non-existent method) inside asyncio.run().
        FastAPI runs inside an async event loop, so asyncio.run() raised
        RuntimeError. The code detected the running loop and silently returned
        None — making the LLMNarrator unreachable in production. This sync
        factory works inside OR outside an event loop.
        """
        import os
        providers: dict[str, Provider] = {}
        ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        providers["ollama"] = OllamaProvider(base_url=ollama_url)
        providers["lmstudio"] = LMStudioProvider()
        if os.environ.get("OPENAI_API_KEY"):
            providers["openai"] = OpenAIProvider(api_key=os.environ["OPENAI_API_KEY"])
        if os.environ.get("ANTHROPIC_API_KEY"):
            providers["anthropic"] = AnthropicProvider(api_key=os.environ["ANTHROPIC_API_KEY"])
        if os.environ.get("GROQ_API_KEY"):
            providers["groq"] = GroqProvider(api_key=os.environ["GROQ_API_KEY"])
        if os.environ.get("OPENROUTER_API_KEY"):
            providers["openrouter"] = OpenRouterProvider(api_key=os.environ["OPENROUTER_API_KEY"])
        if os.environ.get("XAI_API_KEY"):
            providers["grok"] = GrokProvider(api_key=os.environ["XAI_API_KEY"])
        if os.environ.get("GEMINI_API_KEY"):
            # Gemini has an OpenAI-compatible endpoint at generativelanguage.googleapis.com.
            # Reuse OpenAIProvider with the Gemini base_url + Bearer auth.
            gemini_base = os.environ.get(
                "GEMINI_BASE_URL",
                "https://generativelanguage.googleapis.com/v1beta/openai",
            )
            providers["gemini"] = OpenAIProvider(
                base_url=gemini_base,
                api_key=os.environ["GEMINI_API_KEY"],
            )
        if os.environ.get("DEEPSEEK_API_KEY"):
            # DeepSeek has an OpenAI-compatible API at api.deepseek.com.
            # Models: deepseek-chat (was v3, now v4-flash), deepseek-reasoner.
            deepseek_base = os.environ.get(
                "DEEPSEEK_BASE_URL",
                "https://api.deepseek.com/v1",
            )
            providers["deepseek"] = OpenAIProvider(
                base_url=deepseek_base,
                api_key=os.environ["DEEPSEEK_API_KEY"],
            )
        default_provider = (
            "groq" if "groq" in providers else
            "openai" if "openai" in providers else
            "anthropic" if "anthropic" in providers else
            "openrouter" if "openrouter" in providers else
            "grok" if "grok" in providers else
            "gemini" if "gemini" in providers else
            "deepseek" if "deepseek" in providers else
            "ollama"
        )
        router = cls(providers=providers, ledger=ledger, default_provider=default_provider)
        # Allow overriding the OpenRouter model via env var. The default
        # "openrouter/auto" routes to whatever OpenRouter picks, which may
        # be expensive. Setting OPENROUTER_MODEL to a specific low-cost model
        # (e.g. "openai/gpt-oss-120b" at $0.216/M tokens) keeps costs predictable.
        groq_model = os.environ.get("GROQ_MODEL")
        if groq_model and "groq" in providers:
            router.default_models["groq"] = groq_model
        openrouter_model = os.environ.get("OPENROUTER_MODEL")
        if openrouter_model and "openrouter" in providers:
            router.default_models["openrouter"] = openrouter_model
        # Allow overriding the Gemini model. Default is gemini-2.0-flash
        # (fast + cheap). Set GEMINI_MODEL to gemini-2.0-flash-lite for
        # even lower cost, or gemini-2.5-pro for higher quality.
        gemini_model = os.environ.get("GEMINI_MODEL")
        if gemini_model and "gemini" in providers:
            router.default_models["gemini"] = gemini_model
        # Allow overriding the DeepSeek model. Default is deepseek-chat
        # (v4-flash, fast + cheap). Set DEEPSEEK_MODEL to deepseek-reasoner
        # for higher quality reasoning.
        deepseek_model = os.environ.get("DEEPSEEK_MODEL")
        if deepseek_model and "deepseek" in providers:
            router.default_models["deepseek"] = deepseek_model
        return router

    @classmethod
    def has_env_provider(cls) -> bool:
        """True if any cloud LLM env var is set."""
        import os
        return any(os.environ.get(k) for k in [
            "GROQ_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
            "OPENROUTER_API_KEY", "XAI_API_KEY",
            "GEMINI_API_KEY", "DEEPSEEK_API_KEY",
        ])

    @classmethod
    async def auto_detect(cls, ledger: CostLedger | None = None) -> "LLMRouter":
        """Auto-detect available local LLM providers (Ollama, LM Studio).

        Probes common local endpoints and cloud env vars, then returns
        a router pre-configured with whatever it found. The default
        provider is set to the first available local provider (cost $0),
        falling back to the first cloud provider if no local one is up.

        This is the recommended factory for self-hosted deployments —
        it "just works" with whatever the user has running.
        """
        import os
        providers: dict[str, Provider] = {}

        # 1. Probe Ollama at the standard port.
        ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        ollama = OllamaProvider(base_url=ollama_url)
        try:
            if await ollama.health():
                providers["ollama"] = ollama
                # Auto-pick a default model if one is available.
                models = await ollama.list_models()
                if models:
                    # Prefer a medium-sized instruct model if present.
                    preferred = next(
                        (m for m in models if any(k in m.lower() for k in ("llama3.1", "llama3", "qwen2.5", "mistral"))),
                        models[0],
                    )
                    # We can't set default_models here (it's a class attr); we
                    # set it on the instance after construction.
                    providers["_ollama_default_model"] = preferred  # type: ignore[assignment]
        except Exception:
            pass

        # 2. Probe LM Studio at the standard port.
        lmstudio = LMStudioProvider()
        try:
            if await lmstudio.health():
                providers["lmstudio"] = lmstudio
        except Exception:
            pass

        # 3. Cloud providers from env vars.
        if os.environ.get("OPENAI_API_KEY"):
            providers["openai"] = OpenAIProvider(api_key=os.environ["OPENAI_API_KEY"])
        if os.environ.get("ANTHROPIC_API_KEY"):
            providers["anthropic"] = AnthropicProvider(api_key=os.environ["ANTHROPIC_API_KEY"])
        if os.environ.get("OPENROUTER_API_KEY"):
            providers["openrouter"] = OpenRouterProvider(api_key=os.environ["OPENROUTER_API_KEY"])
        if os.environ.get("XAI_API_KEY"):
            providers["grok"] = GrokProvider(api_key=os.environ["XAI_API_KEY"])

        # Pick default provider: prefer local (free), then cloud.
        ollama_default = providers.pop("_ollama_default_model", None)  # type: ignore[arg-type]
        default_provider = "ollama" if "ollama" in providers else (
            "lmstudio" if "lmstudio" in providers else (
                next(iter(providers)) if providers else "ollama"
            )
        )

        router = cls(providers=providers, ledger=ledger, default_provider=default_provider)
        if ollama_default and default_provider == "ollama":
            router.default_model = ollama_default
            router.default_models["ollama"] = ollama_default
        return router

    async def health_check_all(self) -> dict[str, bool]:
        """Check the health of every configured provider.

        Returns a map of provider name → reachable. Used by the
        `/api/doctor` endpoint and the installable PWA's health check.
        """
        results: dict[str, bool] = {}
        for name, prov in self.providers.items():
            try:
                results[name] = await prov.health()
            except Exception:
                results[name] = False
        return results

    async def list_all_models(self) -> dict[str, list[str]]:
        """List models for every provider that supports it."""
        results: dict[str, list[str]] = {}
        for name, prov in self.providers.items():
            try:
                models = await prov.list_models()
                if models:
                    results[name] = models
            except Exception:
                pass
        return results

    async def complete(
        self,
        system: str,
        user: str,
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        tools: list[str] | None = None,
        max_tokens: int | None = None,
        run_id: str = "",
        agent_id: str = "",
        extras: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """Make a chat completion. Handles failover + cost + caching."""
        provider = provider or self.default_provider
        model = model or self.default_models.get(provider, self.default_model)

        # Build the chain of providers to try.
        chain = self._build_chain(provider)

        # Cache key for temperature=0.
        cache_key = ""
        if temperature == 0.0:
            cache_key = self._cache_key(system, user, provider, model, tools)
            if cache_key in self._cache:
                cached = self._cache[cache_key]
                # Re-record cost from cache (so the ledger reflects usage).
                if self.ledger is not None and run_id:
                    await self.ledger.record(
                        run_id=run_id,
                        agent_id=agent_id,
                        provider=cached.provider,
                        model=cached.model,
                        prompt_tokens=cached.prompt_tokens,
                        completion_tokens=cached.completion_tokens,
                    )
                return cached

        request = LLMRequest(
            system=system,
            user=user,
            model=model,
            temperature=temperature,
            tools=tools or [],
            max_tokens=max_tokens,
            extras=extras or {},
        )

        last_exc: Exception | None = None
        for prov_name in chain:
            prov = self.providers.get(prov_name)
            if prov is None:
                continue
            try:
                # If we fell over to a different provider, we may need to
                # adjust the model to that provider's default.
                actual_model = model if prov_name == provider else self.default_models.get(prov_name, model)
                request.model = actual_model
                response = await prov.complete(request)
                response.provider = prov_name
                response.model = actual_model

                # Record cost.
                if self.ledger is not None and run_id:
                    cost = await self.ledger.record(
                        run_id=run_id,
                        agent_id=agent_id,
                        provider=prov_name,
                        model=actual_model,
                        prompt_tokens=response.prompt_tokens,
                        completion_tokens=response.completion_tokens,
                    )
                    response.cost_usd = cost
                else:
                    # Estimate cost without recording.
                    if self.ledger is not None:
                        response.cost_usd = self.ledger.price(
                            prov_name, actual_model,
                            response.prompt_tokens, response.completion_tokens,
                        )

                # Cache temperature=0 calls.
                if cache_key:
                    self._cache[cache_key] = response

                self._failure_counts[prov_name] = 0
                return response
            except Exception as exc:
                logger.warning(
                    "Provider %s failed (%s); trying next in chain", prov_name, exc
                )
                self._failure_counts[prov_name] = self._failure_counts.get(prov_name, 0) + 1
                last_exc = exc
                continue

        raise RuntimeError(
            f"All providers in chain {chain} failed. Last error: {last_exc}"
        )

    async def embed(self, text: str, provider: str | None = None, model: str | None = None) -> list[float]:
        """Embed text via the given provider (default: ollama)."""
        provider = provider or self.default_provider
        prov = self.providers.get(provider)
        if prov is None:
            raise ValueError(f"Unknown provider: {provider}")
        return await prov.embed(text, model)

    def _build_chain(self, start: str) -> list[str]:
        """Build a failover chain starting at `start`."""
        chain = [start]
        for p in self.default_chain:
            if p not in chain and p in self.providers:
                chain.append(p)
        return chain

    def _cache_key(
        self, system: str, user: str, provider: str, model: str, tools: list[str] | None
    ) -> str:
        h = hashlib.sha256()
        h.update(system.encode())
        h.update(b"\x00")
        h.update(user.encode())
        h.update(b"\x00")
        h.update(provider.encode())
        h.update(b"\x00")
        h.update(model.encode())
        if tools:
            h.update(b"\x00")
            h.update(json.dumps(sorted(tools)).encode())
        return h.hexdigest()

    def available_providers(self) -> list[str]:
        return list(self.providers.keys())

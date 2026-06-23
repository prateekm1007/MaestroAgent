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
        default_factory=lambda: ["ollama", "openai", "anthropic", "openrouter"]
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
            "grok": "grok-beta",
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

"""maestro_llm — model-agnostic LLM router with cost tracking & failover.

The router is the single entry point for all LLM calls in MaestroAgent.
It:

1. **Routes per-call.** Picks the best provider+model based on the
   caller's hint (capability, cost, latency).
2. **Tracks cost.** Every call updates the run's cost ledger; the
   engine checks the budget before each call.
3. **Falls over.** If a provider fails, the router tries the next in
   the failover chain (managed by `FallbackPolicy`).
4. **Caches.** Idempotent calls (same prompt + temperature ≤ 0) are
   cached to enable deterministic replay.
5. **Embeds.** The same router exposes `embed()` for the memory tiers.

Adding a provider
-----------------
1. Implement a `Provider` subclass.
2. Register it in the `PROVIDERS` dict at the bottom of this file.
3. Add it to the provider chain in your run config.
"""

from maestro_llm.router import LLMRouter, LLMResponse, LLMRequest
from maestro_llm.providers import (
    Provider,
    OllamaProvider,
    OpenAIProvider,
    AnthropicProvider,
    OpenRouterProvider,
    GrokProvider,
    LMStudioProvider,
)
from maestro_llm.cost import CostLedger, ModelPricing, DEFAULT_PRICING

__all__ = [
    "LLMRouter",
    "LLMResponse",
    "LLMRequest",
    "Provider",
    "OllamaProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "OpenRouterProvider",
    "GrokProvider",
    "LMStudioProvider",
    "CostLedger",
    "ModelPricing",
    "DEFAULT_PRICING",
]

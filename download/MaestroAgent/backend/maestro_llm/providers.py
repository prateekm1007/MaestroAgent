"""Provider adapters — one per LLM backend.

Each `Provider` exposes:
- `complete(request) -> LLMResponse` — chat completion.
- `embed(text) -> list[float]` — embedding (optional; some providers don't support this).
- `list_models() -> list[str]` — discover available models.

The providers are intentionally thin: they translate our `LLMRequest`
into the provider's SDK call and the response back into our
`LLMResponse`. All retry / failover / cost logic lives in the router,
not the providers.

Local-first providers (Ollama, LM Studio) get extra love: they're the
default and we make sure they work without API keys.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class LLMRequest:
    system: str
    user: str
    model: str
    temperature: float = 0.2
    tools: list[str] = field(default_factory=list)
    max_tokens: int | None = None
    # Provider-specific extras.
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] | None = None


class Provider(ABC):
    """Abstract LLM provider."""

    name: str = "abstract"

    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        self.base_url = base_url
        self.api_key = api_key

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse: ...

    async def embed(self, text: str, model: str | None = None) -> list[float]:
        """Default: no embedding support. Override in providers that do."""
        raise NotImplementedError(f"{self.name} does not support embeddings")

    async def list_models(self) -> list[str]:
        return []

    async def health(self) -> bool:
        return True


class OllamaProvider(Provider):
    """Local Ollama provider. Default for MaestroAgent."""

    name = "ollama"

    def __init__(self, base_url: str = "http://localhost:11434", api_key: str | None = None) -> None:
        super().__init__(base_url=base_url, api_key=api_key)
        self._client = httpx.AsyncClient(base_url=base_url, timeout=300.0)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        payload = {
            "model": request.model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            "stream": False,
            "options": {"temperature": request.temperature},
        }
        if request.max_tokens:
            payload["options"]["num_predict"] = request.max_tokens

        resp = await self._client.post("/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()
        text = data.get("message", {}).get("content", "")
        # Ollama returns eval_count as completion tokens.
        return LLMResponse(
            text=text,
            provider=self.name,
            model=request.model,
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
            raw=data,
        )

    async def embed(self, text: str, model: str | None = None) -> list[float]:
        model = model or "nomic-embed-text"
        resp = await self._client.post(
            "/api/embeddings", json={"model": model, "prompt": text}
        )
        resp.raise_for_status()
        return resp.json().get("embedding", [])

    async def list_models(self) -> list[str]:
        resp = await self._client.get("/api/tags")
        resp.raise_for_status()
        return [m["name"] for m in resp.json().get("models", [])]

    async def health(self) -> bool:
        try:
            resp = await self._client.get("/api/tags")
            return resp.status_code == 200
        except Exception:
            return False


class LMStudioProvider(OllamaProvider):
    """LM Studio — OpenAI-compatible API on localhost:1234."""

    name = "lmstudio"

    def __init__(self, base_url: str = "http://localhost:1234/v1", api_key: str | None = None) -> None:
        super().__init__(base_url=base_url, api_key=api_key)


class OpenAIProvider(Provider):
    """OpenAI-compatible provider (OpenAI, Azure, any compatible)."""

    name = "openai"

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        api_key: str | None = None,
    ) -> None:
        super().__init__(base_url=base_url, api_key=api_key)
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
            timeout=300.0,
        )

    async def complete(self, request: LLMRequest) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            "temperature": request.temperature,
        }
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens

        resp = await self._client.post("/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]
        text = choice["message"].get("content", "")
        usage = data.get("usage", {})
        return LLMResponse(
            text=text,
            provider=self.name,
            model=request.model,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            tool_calls=choice["message"].get("tool_calls", []),
            raw=data,
        )

    async def embed(self, text: str, model: str | None = None) -> list[float]:
        model = model or "text-embedding-3-small"
        resp = await self._client.post(
            "/embeddings", json={"model": model, "input": text}
        )
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]


class AnthropicProvider(Provider):
    """Anthropic Claude provider."""

    name = "anthropic"

    def __init__(
        self,
        base_url: str = "https://api.anthropic.com/v1",
        api_key: str | None = None,
    ) -> None:
        super().__init__(base_url=base_url, api_key=api_key)
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={
                "x-api-key": api_key or "",
                "anthropic-version": "2023-06-01",
            },
            timeout=300.0,
        )

    async def complete(self, request: LLMRequest) -> LLMResponse:
        payload = {
            "model": request.model,
            "max_tokens": request.max_tokens or 4096,
            "system": request.system,
            "messages": [{"role": "user", "content": request.user}],
            "temperature": request.temperature,
        }
        resp = await self._client.post("/messages", json=payload)
        resp.raise_for_status()
        data = resp.json()
        text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")
        usage = data.get("usage", {})
        return LLMResponse(
            text=text,
            provider=self.name,
            model=request.model,
            prompt_tokens=usage.get("input_tokens", 0),
            completion_tokens=usage.get("output_tokens", 0),
            raw=data,
        )


class OpenRouterProvider(OpenAIProvider):
    """OpenRouter — routes to many providers via OpenAI-compatible API."""

    name = "openrouter"

    def __init__(self, base_url: str = "https://openrouter.ai/api/v1", api_key: str | None = None) -> None:
        super().__init__(base_url=base_url, api_key=api_key)


class GroqProvider(OpenAIProvider):
    """Groq — fast LPU inference, OpenAI-compatible API.

    Free tier: 30 req/min, 1000 req/day on llama-3.3-70b-versatile.
    Sub-second responses even on 70B models.
    """

    name = "groq"

    def __init__(self, base_url: str = "https://api.groq.com/openai/v1", api_key: str | None = None) -> None:
        super().__init__(base_url=base_url, api_key=api_key)


class GrokProvider(OpenAIProvider):
    """xAI Grok — OpenAI-compatible."""

    name = "grok"

    def __init__(self, base_url: str = "https://api.x.ai/v1", api_key: str | None = None) -> None:
        super().__init__(base_url=base_url, api_key=api_key)

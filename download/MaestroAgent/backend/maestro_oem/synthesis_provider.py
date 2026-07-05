"""SynthesisProvider — production-grade LLM provider for Ask Maestro.

AUDITOR-DIRECTIVE (2026-07-05):
> initialize the provider/router during application lifespan startup;
> inject the initialized provider into the Ask service;
> make synthesis genuinely async end-to-end;
> define explicit timeout budgets;
> use circuit breaking;
> enforce concurrency limits;
> define deterministic fallback behavior;
> expose telemetry showing synthesis_mode = model | deterministic_fallback;
> never silently pretend the model path ran when it did not.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ProviderState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    failure_threshold: int = 3
    recovery_seconds: float = 60.0
    success_threshold: int = 1

    _state: ProviderState = field(default=ProviderState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _success_count: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0.0, init=False)

    @property
    def state(self) -> ProviderState:
        if self._state == ProviderState.OPEN:
            if time.time() - self._last_failure_time >= self.recovery_seconds:
                self._state = ProviderState.HALF_OPEN
                self._success_count = 0
                logger.info("CircuitBreaker: OPEN → HALF_OPEN (probing)")
        return self._state

    def record_success(self) -> None:
        if self._state == ProviderState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                self._state = ProviderState.CLOSED
                self._failure_count = 0
                logger.info("CircuitBreaker: HALF_OPEN → CLOSED (recovered)")
        else:
            self._failure_count = 0

    def record_failure(self) -> None:
        self._last_failure_time = time.time()
        if self._state == ProviderState.HALF_OPEN:
            self._state = ProviderState.OPEN
            self._success_count = 0
            logger.warning("CircuitBreaker: HALF_OPEN → OPEN (probe failed)")
        else:
            self._failure_count += 1
            if self._failure_count >= self.failure_threshold:
                self._state = ProviderState.OPEN
                logger.warning("CircuitBreaker: CLOSED → OPEN (%d failures)", self._failure_count)

    def should_fail_fast(self) -> bool:
        return self.state == ProviderState.OPEN


@dataclass
class SynthesisResult:
    text: str = ""
    model_used: str = ""
    provider_name: str = ""
    mode: str = "deterministic_fallback"
    fallback_reason: str = ""
    latency_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0


class SynthesisProvider:
    """Initialized ONCE during lifespan startup. Injected into AskPipeline.

    AUDITOR-FIX: The CircuitBreaker now wraps ALL providers — not just
    the from_env() path. A custom provider injected via wrap_provider()
    also gets circuit breaking, timeout, and concurrency limits.

    Before this fix, a custom provider (like the ZAIProvider in the
    1000-iteration test) bypassed the CircuitBreaker entirely, making
    988 unnecessary failed API calls. No code path should make 988
    failed API calls.
    """

    def __init__(
        self,
        router: Any = None,
        *,
        timeout_seconds: float = 30.0,
        max_concurrent: int = 5,
        circuit: CircuitBreaker | None = None,
        custom_provider: Any = None,
    ) -> None:
        self._router = router
        self._custom_provider = custom_provider
        self._timeout = timeout_seconds
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._circuit = circuit or CircuitBreaker()
        # Available if we have a router OR a custom provider
        if custom_provider is not None:
            self._available = bool(getattr(custom_provider, "available", True))
        else:
            self._available = router is not None and bool(getattr(router, "providers", {}))

    @classmethod
    def from_env(cls, *, timeout_seconds: float = 30.0, max_concurrent: int = 5) -> "SynthesisProvider":
        try:
            from maestro_llm.router import LLMRouter
            router = LLMRouter.from_env_sync()
            return cls(router=router, timeout_seconds=timeout_seconds, max_concurrent=max_concurrent)
        except Exception as e:
            logger.warning("SynthesisProvider.from_env failed: %s", e)
            return cls(router=None, timeout_seconds=timeout_seconds, max_concurrent=max_concurrent)

    @classmethod
    def wrap_provider(
        cls,
        provider: Any,
        *,
        timeout_seconds: float = 10.0,
        max_concurrent: int = 3,
        circuit: CircuitBreaker | None = None,
    ) -> "SynthesisProvider":
        """Wrap ANY async provider in a SynthesisProvider with CircuitBreaker.

        AUDITOR-FIX: Before this method, custom providers (like ZAIProvider)
        could be injected directly into AskPipeline, bypassing the
        CircuitBreaker. This made 988 unnecessary failed API calls in the
        1000-iteration test. Now, any custom provider MUST be wrapped:

            provider = SynthesisProvider.wrap_provider(my_custom_provider)
            pipe = AskPipeline(synthesis_provider=provider)

        The wrapped provider gets:
        - CircuitBreaker (3 failures → OPEN → probe after 60s)
        - Timeout (10s default — shorter for custom providers)
        - Concurrency limit (3 default — lower for custom providers)
        - Telemetry (synthesis_mode recorded in every answer)
        """
        return cls(
            router=None,
            custom_provider=provider,
            timeout_seconds=timeout_seconds,
            max_concurrent=max_concurrent,
            circuit=circuit,
        )

    @property
    def available(self) -> bool:
        return self._available

    @property
    def circuit_state(self) -> ProviderState:
        return self._circuit.state

    @property
    def default_model(self) -> str:
        if not self._available:
            return ""
        try:
            return self._router.default_models.get(
                self._router.default_provider, self._router.default_model
            )
        except Exception:
            return ""

    async def synthesize(self, system: str, user: str) -> SynthesisResult:
        """Call the LLM with circuit breaking, timeout, concurrency. NEVER raises.

        AUDITOR-FIX: Now handles BOTH router-based and custom provider paths.
        Both go through the CircuitBreaker — no code path bypasses it.
        """
        if not self._available:
            return SynthesisResult(mode="deterministic_fallback", fallback_reason="no_provider")

        if self._circuit.should_fail_fast():
            return SynthesisResult(mode="deterministic_fallback", fallback_reason="circuit_open")

        async with self._semaphore:
            t0 = time.time()
            try:
                if self._custom_provider is not None:
                    # Custom provider path (e.g., ZAIProvider)
                    response = await asyncio.wait_for(
                        self._custom_provider.synthesize(system, user),
                        timeout=self._timeout,
                    )
                else:
                    # Router-based path (LLMRouter)
                    response = await asyncio.wait_for(
                        self._router.complete(system=system, user=user, temperature=0.2),
                        timeout=self._timeout,
                    )
                latency_ms = int((time.time() - t0) * 1000)
                self._circuit.record_success()
                return SynthesisResult(
                    text=response.text,
                    model_used=getattr(response, "model_used", "") or getattr(response, "model", "") or self.default_model,
                    provider_name=getattr(response, "provider_name", "") or getattr(response, "provider", "") or "custom",
                    mode="model",
                    latency_ms=latency_ms,
                    prompt_tokens=getattr(response, "prompt_tokens", 0) or 0,
                    completion_tokens=getattr(response, "completion_tokens", 0) or 0,
                )
            except asyncio.TimeoutError:
                latency_ms = int((time.time() - t0) * 1000)
                self._circuit.record_failure()
                logger.warning("SynthesisProvider: timeout after %dms", latency_ms)
                return SynthesisResult(
                    mode="deterministic_fallback",
                    fallback_reason=f"timeout:{int(self._timeout)}s",
                    latency_ms=latency_ms,
                )
            except Exception as e:
                latency_ms = int((time.time() - t0) * 1000)
                self._circuit.record_failure()
                logger.warning("SynthesisProvider: error: %s", e)
                return SynthesisResult(
                    mode="deterministic_fallback",
                    fallback_reason=f"error:{type(e).__name__}:{str(e)[:100]}",
                    latency_ms=latency_ms,
                )

    def health_check(self) -> dict[str, Any]:
        return {
            "available": self._available,
            "circuit_state": self._circuit.state.value,
            "default_model": self.default_model,
            "timeout_seconds": self._timeout,
        }

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
    """Initialized ONCE during lifespan startup. Injected into AskPipeline."""

    def __init__(
        self,
        router: Any = None,
        *,
        timeout_seconds: float = 30.0,
        max_concurrent: int = 5,
        circuit: CircuitBreaker | None = None,
    ) -> None:
        self._router = router
        self._timeout = timeout_seconds
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._circuit = circuit or CircuitBreaker()
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
        """Call the LLM with circuit breaking, timeout, concurrency. NEVER raises."""
        if not self._available:
            return SynthesisResult(mode="deterministic_fallback", fallback_reason="no_provider")

        if self._circuit.should_fail_fast():
            return SynthesisResult(mode="deterministic_fallback", fallback_reason="circuit_open")

        async with self._semaphore:
            t0 = time.time()
            try:
                response = await asyncio.wait_for(
                    self._router.complete(system=system, user=user, temperature=0.2),
                    timeout=self._timeout,
                )
                latency_ms = int((time.time() - t0) * 1000)
                self._circuit.record_success()
                return SynthesisResult(
                    text=response.text,
                    model_used=getattr(response, "model", "") or self.default_model,
                    provider_name=getattr(response, "provider", "") or self._router.default_provider,
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

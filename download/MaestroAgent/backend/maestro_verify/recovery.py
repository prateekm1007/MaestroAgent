"""Recovery — failure recovery, model fallback, checkpoint resume.

The recovery layer is what makes MaestroAgent production-grade. When
something goes wrong (LLM provider 500s, tool times out, graph panics),
the recovery layer decides what to do:

1. **Retry with backoff.** Transient failures get retried.
2. **Model fallback.** If a provider is down, switch to a configured
   backup (the LLMRouter's failover chain).
3. **Checkpoint resume.** If the engine itself crashes, the next run
   resumes from the latest checkpoint.
4. **Circuit breaker.** A provider that fails repeatedly is taken out
   of rotation for a cooldown.
5. **HITL escalation.** If recovery is exhausted, pause the run and
   ask a human.

This module exposes `FailureRecovery` — a policy object that the engine
consults when catching exceptions. The actual retry/fallback logic for
LLM calls lives in the `LLMRouter`; this module is the higher-level
policy layer.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

logger = logging.getLogger(__name__)


class RecoveryAction(str, Enum):
    RETRY = "retry"
    FALLBACK = "fallback"
    PAUSE = "pause"
    FAIL = "fail"
    ESCALATE = "escalate"


@dataclass
class FallbackPolicy:
    """Per-run fallback policy."""

    # Provider failover chain — try in order.
    provider_chain: list[str] = field(default_factory=lambda: ["ollama", "openrouter", "anthropic"])
    # Max retries before fallback.
    max_retries: int = 2
    # Circuit breaker: open after N consecutive failures.
    circuit_breaker_threshold: int = 5
    # How long to keep a circuit open (seconds).
    circuit_breaker_cooldown: float = 60.0
    # Provider health tracking.
    _failure_counts: dict[str, int] = field(default_factory=dict)
    _circuit_open_until: dict[str, float] = field(default_factory=dict)

    def record_failure(self, provider: str) -> None:
        self._failure_counts[provider] = self._failure_counts.get(provider, 0) + 1
        if self._failure_counts[provider] >= self.circuit_breaker_threshold:
            self._circuit_open_until[provider] = time.time() + self.circuit_breaker_cooldown
            logger.warning(
                "Circuit opened for provider %s (%d failures)",
                provider, self._failure_counts[provider],
            )

    def record_success(self, provider: str) -> None:
        self._failure_counts[provider] = 0
        self._circuit_open_until.pop(provider, None)

    def is_available(self, provider: str) -> bool:
        until = self._circuit_open_until.get(provider)
        if until is None:
            return True
        if time.time() >= until:
            # Cooldown over — try again.
            self._circuit_open_until.pop(provider, None)
            self._failure_counts[provider] = 0
            return True
        return False

    def next_provider(self, current: str | None) -> str | None:
        """Return the next available provider after `current` in the chain."""
        started = False
        for p in self.provider_chain:
            if current is None:
                started = True
            if p == current and not started:
                started = True
                continue
            if started and self.is_available(p):
                return p
        # If we exhausted the chain after `current`, wrap to the start.
        for p in self.provider_chain:
            if self.is_available(p):
                return p
        return None


@dataclass
class FailureRecovery:
    """High-level recovery policy consulted by the engine on exceptions."""

    fallback: FallbackPolicy = field(default_factory=FallbackPolicy)

    def classify(self, exc: Exception) -> RecoveryAction:
        """Classify an exception and decide what to do."""
        from maestro_core.context import BudgetExhausted, IterationCapHit
        if isinstance(exc, (BudgetExhausted, IterationCapHit)):
            return RecoveryAction.PAUSE
        if isinstance(exc, PermissionError):
            return RecoveryAction.ESCALATE
        if isinstance(exc, TimeoutError):
            return RecoveryAction.RETRY
        # Default: retry a few times, then escalate.
        return RecoveryAction.RETRY

    def pick_fallback_provider(self, current: str | None) -> str | None:
        return self.fallback.next_provider(current)

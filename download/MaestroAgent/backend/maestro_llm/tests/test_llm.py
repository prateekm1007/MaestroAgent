"""Smoke tests for maestro_llm — cost tracking + pricing."""

from __future__ import annotations

from pathlib import Path

import pytest

from maestro_llm.cost import DEFAULT_PRICING, CostLedger, ModelPricing


def test_default_pricing_covers_marketed_models() -> None:
    for m in ["gpt-4o", "gpt-4o-mini", "claude-3-5-sonnet", "ollama:default"]:
        assert m in DEFAULT_PRICING, f"missing {m}"


def test_local_providers_are_zero_cost() -> None:
    assert DEFAULT_PRICING["ollama:default"].prompt == 0.0
    assert DEFAULT_PRICING["ollama:default"].completion == 0.0


def test_unknown_fallback_exists() -> None:
    assert "unknown" in DEFAULT_PRICING
    assert DEFAULT_PRICING["unknown"].prompt > 0


def test_price_computes_correctly() -> None:
    """gpt-4o: $2.5/1M prompt, $10/1M completion. 1000p+500c = 0.0025+0.005 = 0.0075."""
    ledger = CostLedger(db_path=":memory:")
    cost = ledger.price("openai", "gpt-4o", prompt_tokens=1000, completion_tokens=500)
    assert abs(cost - 0.0075) < 1e-9


def test_price_zero_tokens_is_zero() -> None:
    ledger = CostLedger(db_path=":memory:")
    assert ledger.price("openai", "gpt-4o", 0, 0) == 0.0


def test_price_unknown_model_uses_fallback() -> None:
    ledger = CostLedger(db_path=":memory:")
    cost = ledger.price("openai", "gpt-99-not-real", 1000, 0)
    expected = 1000 / 1_000_000 * DEFAULT_PRICING["unknown"].prompt
    assert abs(cost - expected) < 1e-9


async def test_record_and_total(tmp_path: Path) -> None:
    ledger = CostLedger(db_path=str(tmp_path / "c.db"))
    await ledger.record("r1", "a", "openai", "gpt-4o", 1000, 500)
    await ledger.record("r2", "a", "openai", "gpt-4o", 100, 50)
    assert await ledger.total_for_run("r1") > await ledger.total_for_run("r2")


async def test_total_nonexistent_run_is_zero(tmp_path: Path) -> None:
    ledger = CostLedger(db_path=str(tmp_path / "c.db"))
    assert await ledger.total_for_run("never") == 0.0

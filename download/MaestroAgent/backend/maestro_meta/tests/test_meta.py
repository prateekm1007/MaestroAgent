"""Smoke tests for maestro_meta — self-improving meta-agent recommendations."""

from __future__ import annotations

from maestro_meta import (
    MetaAgent,
    Recommendation,
    RecommendationKind,
    Severity,
)


def test_recommendation_defaults() -> None:
    r = Recommendation(
        kind=RecommendationKind.ADJUST_LLM_HINT,
        severity=Severity.WARN,
        title="t", description="d", target="x",
    )
    assert r.proposed_change == {}
    assert r.confidence == 0.0


def test_recommendation_kind_enum_values() -> None:
    assert RecommendationKind.ADJUST_LLM_HINT.value == "adjust_llm_hint"
    assert RecommendationKind.QUARANTINE_AGENT.value == "quarantine_agent"


def test_severity_enum_values() -> None:
    assert Severity.INFO.value == "info"
    assert Severity.CRITICAL.value == "critical"


def test_detect_cost_outliers_flags_2x_average() -> None:
    meta = MetaAgent(llm=None, checkpoints=None, ledger=None)
    data = [
        {"run_id": "r1", "provider": "openai", "model": "gpt-4o", "cost_usd": 1.0, "calls": 1},
        {"run_id": "r2", "provider": "openai", "model": "gpt-4o", "cost_usd": 1.0, "calls": 1},
        {"run_id": "r3", "provider": "openai", "model": "gpt-4o", "cost_usd": 5.0, "calls": 1},
    ]
    recs = meta._detect_cost_outliers(data)
    assert len(recs) == 1
    assert recs[0].severity is Severity.WARN


def test_detect_cost_outliers_no_outliers() -> None:
    meta = MetaAgent(llm=None, checkpoints=None, ledger=None)
    data = [
        {"run_id": "r1", "provider": "openai", "model": "gpt-4o", "cost_usd": 1.0, "calls": 1},
        {"run_id": "r2", "provider": "openai", "model": "gpt-4o", "cost_usd": 1.1, "calls": 1},
    ]
    assert meta._detect_cost_outliers(data) == []


def test_detect_cost_outliers_skips_under_3_samples() -> None:
    meta = MetaAgent(llm=None, checkpoints=None, ledger=None)
    data = [
        {"run_id": "r1", "provider": "openai", "model": "gpt-4o", "cost_usd": 1.0, "calls": 1},
        {"run_id": "r2", "provider": "openai", "model": "gpt-4o", "cost_usd": 100.0, "calls": 1},
    ]
    assert meta._detect_cost_outliers(data) == []


async def test_analyze_with_no_data_returns_empty() -> None:
    meta = MetaAgent(llm=None, checkpoints=None, ledger=None)
    assert await meta.analyze_recent_runs(limit=5) == []


def test_to_dict_serializes() -> None:
    meta = MetaAgent(llm=None, checkpoints=None, ledger=None)
    recs = [Recommendation(
        kind=RecommendationKind.PROMOTE_MEMORY, severity=Severity.INFO,
        title="t", description="d", target="m",
    )]
    out = meta.to_dict(recs)
    assert out[0]["kind"] == "promote_memory"

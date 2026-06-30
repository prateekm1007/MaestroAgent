"""Cost ledger — per-run cost tracking with provider-aware pricing.

The ledger is the source of truth for "how much has this run cost".
The engine reads `ledger.total_usd` before each LLM call to enforce
the run budget.

Pricing
-------
Pricing is per (provider, model) and is in USD per 1M tokens. We ship
a `DEFAULT_PRICING` table for common models. Users can override via
`maestro config set pricing.<provider>.<model> {prompt: ..., completion: ...}`.

The ledger writes to SQLite so costs survive crashes and can be
aggregated across runs for the analytics dashboard.
"""

from __future__ import annotations

from maestro_db import sqlite_compat as sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class ModelPricing:
    """USD per 1M tokens."""

    prompt: float
    completion: float


# Default pricing for common models (per 1M tokens, USD).
# Users should override with their negotiated rates.
DEFAULT_PRICING: dict[str, ModelPricing] = {
    # OpenAI
    "gpt-4o": ModelPricing(prompt=2.5, completion=10.0),
    "gpt-4o-mini": ModelPricing(prompt=0.15, completion=0.6),
    "gpt-4-turbo": ModelPricing(prompt=10.0, completion=30.0),
    "gpt-3.5-turbo": ModelPricing(prompt=0.5, completion=1.5),
    # Anthropic
    "claude-3-5-sonnet": ModelPricing(prompt=3.0, completion=15.0),
    "claude-3-5-haiku": ModelPricing(prompt=0.8, completion=4.0),
    "claude-3-opus": ModelPricing(prompt=15.0, completion=75.0),
    # OpenRouter (representative; actual varies by underlying model)
    "openrouter:default": ModelPricing(prompt=2.0, completion=6.0),
    # Grok
    "grok-2": ModelPricing(prompt=2.0, completion=10.0),
    "grok-beta": ModelPricing(prompt=5.0, completion=15.0),
    # Ollama / LM Studio — local, so $0 (but we still track token counts)
    "ollama:default": ModelPricing(prompt=0.0, completion=0.0),
    "lmstudio:default": ModelPricing(prompt=0.0, completion=0.0),
    # Fallback
    "unknown": ModelPricing(prompt=1.0, completion=3.0),
}


class CostLedger:
    """SQLite-backed cost ledger."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS cost_entries(
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        agent_id TEXT,
        provider TEXT NOT NULL,
        model TEXT NOT NULL,
        prompt_tokens INTEGER NOT NULL,
        completion_tokens INTEGER NOT NULL,
        cost_usd REAL NOT NULL,
        ts TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_cost_run ON cost_entries(run_id, ts);
    CREATE INDEX IF NOT EXISTS idx_cost_agent ON cost_entries(agent_id);
    """

    def __init__(
        self,
        db_path: str | Path = "maestro.db",
        pricing: dict[str, ModelPricing] | None = None,
    ) -> None:
        self.db_path = str(db_path)
        self.pricing = pricing or DEFAULT_PRICING
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript(self.SCHEMA)
            conn.commit()
        finally:
            conn.close()
        self._conn: sqlite3.Connection | None = None

    def _conn_get(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def price(self, provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Compute cost in USD for a call."""
        key = f"{provider}:{model}" if provider not in {"openai", "anthropic"} else model
        p = self.pricing.get(model) or self.pricing.get(key) or self.pricing.get("unknown", ModelPricing(1.0, 3.0))
        return (prompt_tokens / 1_000_000.0) * p.prompt + (completion_tokens / 1_000_000.0) * p.completion

    async def record(
        self,
        run_id: str,
        agent_id: str | None,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> float:
        cost = self.price(provider, model, prompt_tokens, completion_tokens)
        conn = self._conn_get()
        conn.execute(
            "INSERT INTO cost_entries (id, run_id, agent_id, provider, model, "
            "prompt_tokens, completion_tokens, cost_usd, ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                run_id,
                agent_id,
                provider,
                model,
                prompt_tokens,
                completion_tokens,
                cost,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        return cost

    async def total_for_run(self, run_id: str) -> float:
        conn = self._conn_get()
        row = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM cost_entries WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        return float(row["total"])

    async def breakdown_for_run(self, run_id: str) -> list[dict[str, Any]]:
        conn = self._conn_get()
        rows = conn.execute(
            "SELECT provider, model, SUM(prompt_tokens) AS prompt_tokens, "
            "SUM(completion_tokens) AS completion_tokens, SUM(cost_usd) AS cost_usd, "
            "COUNT(*) AS calls "
            "FROM cost_entries WHERE run_id = ? GROUP BY provider, model "
            "ORDER BY cost_usd DESC",
            (run_id,),
        ).fetchall()
        return [dict(r) for r in rows]

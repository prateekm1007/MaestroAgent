"""maestro_meta — self-improving meta-agent.

The meta-agent analyzes past runs to identify patterns and propose
optimizations to MaestroAgent workflows:

- Which agents consistently fail or overrun their budget?
- Which loops stagnate (score doesn't improve)?
- Which providers give the best cost/quality tradeoff per task type?
- Which templates produce the most successful runs?

It then proposes concrete changes:
- Adjust an agent's `llm_hint` to a cheaper model for low-stakes calls.
- Tighten a loop's `max_iterations` if it always exits via budget.
- Adjust a supervisor's decomposition prompt based on past success.
- Promote a frequently-recalled memory entry to long-term.

**Safety**: the meta-agent NEVER modifies the engine core or executes
code. It only produces *recommendations* (and optionally applies them
to template files behind a `--self-improve` flag). Every change is a
git commit on a `meta-agent` branch; `git revert` undoes anything.

Usage
-----
    from maestro_meta import MetaAgent
    meta = MetaAgent(llm=router, checkpoints=store, ledger=ledger)
    recommendations = await meta.analyze_recent_runs(limit=20)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class RecommendationKind(str, Enum):
    ADJUST_LLM_HINT = "adjust_llm_hint"
    TIGHTEN_LOOP_BUDGET = "tighten_loop_budget"
    LOOSEN_LOOP_BUDGET = "loosen_loop_budget"
    PROMOTE_MEMORY = "promote_memory"
    ADJUST_SUPERVISOR_PROMPT = "adjust_supervisor_prompt"
    ADD_FALLBACK_PROVIDER = "add_fallback_provider"
    QUARANTINE_AGENT = "quarantine_agent"


class Severity(str, Enum):
    INFO = "info"
    WARN = "warn"
    CRITICAL = "critical"


@dataclass
class Recommendation:
    kind: RecommendationKind
    severity: Severity
    title: str
    description: str
    target: str
    proposed_change: dict[str, Any] = field(default_factory=dict)
    expected_savings_usd: float = 0.0
    expected_success_rate_delta: float = 0.0
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)


@dataclass
class MetaAgent:
    """Self-improving meta-agent that analyzes runs + proposes optimizations."""

    llm: Any
    checkpoints: Any
    ledger: Any
    memory: Any = None

    async def analyze_recent_runs(self, limit: int = 20) -> list[Recommendation]:
        cost_data = await self._gather_cost_data(limit)
        audit_data = await self._gather_audit_data(limit)
        recs: list[Recommendation] = []
        recs.extend(self._detect_cost_outliers(cost_data))
        recs.extend(self._detect_failure_patterns(audit_data))
        recs.extend(self._detect_loop_stagnation(audit_data))
        if cost_data and len(cost_data) >= 3:
            recs.extend(await self._llm_analyze(cost_data, audit_data))
        recs.sort(key=lambda r: (r.severity.value, -r.expected_savings_usd), reverse=True)
        return recs

    async def _gather_cost_data(self, limit: int) -> list[dict[str, Any]]:
        if self.ledger is None:
            return []
        import sqlite3
        conn = sqlite3.connect(self.ledger.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT run_id, provider, model, "
                "SUM(prompt_tokens) AS prompt_tokens, "
                "SUM(completion_tokens) AS completion_tokens, "
                "SUM(cost_usd) AS cost_usd, COUNT(*) AS calls "
                "FROM cost_entries GROUP BY run_id, provider, model "
                "ORDER BY run_id DESC LIMIT ?",
                (limit * 5,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    async def _gather_audit_data(self, limit: int) -> list[dict[str, Any]]:
        if self.checkpoints is None:
            return []
        import sqlite3
        conn = sqlite3.connect(self.checkpoints.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT run_id, ts, kind, payload_json FROM audit "
                "WHERE kind IN ('run.complete', 'run.fatal', 'loop.created') "
                "ORDER BY ts DESC LIMIT ?",
                (limit * 3,),
            ).fetchall()
            return [
                {"run_id": r["run_id"], "ts": r["ts"], "kind": r["kind"],
                 "payload": json.loads(r["payload_json"])}
                for r in rows
            ]
        finally:
            conn.close()

    def _detect_cost_outliers(self, cost_data: list[dict[str, Any]]) -> list[Recommendation]:
        if not cost_data:
            return []
        by_model: dict[tuple[str, str], list[float]] = {}
        for row in cost_data:
            key = (row["provider"], row["model"])
            by_model.setdefault(key, []).append(row["cost_usd"])
        recs: list[Recommendation] = []
        for (provider, model), costs in by_model.items():
            if len(costs) < 3:
                continue
            avg = sum(costs) / len(costs)
            max_cost = max(costs)
            if max_cost > avg * 2 and max_cost > 1.0:
                recs.append(Recommendation(
                    kind=RecommendationKind.ADJUST_LLM_HINT,
                    severity=Severity.WARN,
                    title=f"{provider}/{model} costs {max_cost:.2f} USD in one run (avg {avg:.2f})",
                    description=(
                        f"This model cost {max_cost:.2f} USD in a single run, "
                        f"which is {max_cost/avg:.1f}x the average. Consider routing "
                        f"low-stakes calls to a cheaper model."
                    ),
                    target=f"{provider}/{model}",
                    proposed_change={"suggested_model": "gpt-4o-mini" if provider != "ollama" else "llama3.1:8b"},
                    expected_savings_usd=max_cost - avg,
                    confidence=0.7,
                    evidence=[f"avg={avg:.4f}", f"max={max_cost:.4f}", f"calls={len(costs)}"],
                ))
        return recs

    def _detect_failure_patterns(self, audit_data: list[dict[str, Any]]) -> list[Recommendation]:
        if not audit_data:
            return []
        failures: dict[str, int] = {}
        successes: dict[str, int] = {}
        for entry in audit_data:
            run_id = entry["run_id"]
            if entry["kind"] == "run.fatal":
                failures[run_id] = failures.get(run_id, 0) + 1
            elif entry["kind"] == "run.complete":
                payload = entry["payload"]
                if payload.get("status") == "failed":
                    failures[run_id] = failures.get(run_id, 0) + 1
                else:
                    successes[run_id] = successes.get(run_id, 0) + 1
        recs: list[Recommendation] = []
        total_runs = len(set(list(failures.keys()) + list(successes.keys())))
        if total_runs >= 5 and len(failures) / total_runs > 0.4:
            recs.append(Recommendation(
                kind=RecommendationKind.ADJUST_SUPERVISOR_PROMPT,
                severity=Severity.CRITICAL,
                title=f"{len(failures)}/{total_runs} recent runs failed",
                description=(
                    f"The failure rate is {len(failures)/total_runs:.0%}. "
                    f"Review the supervisor's decomposition prompt."
                ),
                target="supervisor",
                expected_success_rate_delta=-(len(failures) / total_runs),
                confidence=0.6,
                evidence=[f"failures={len(failures)}", f"successes={len(successes)}"],
            ))
        return recs

    def _detect_loop_stagnation(self, audit_data: list[dict[str, Any]]) -> list[Recommendation]:
        loop_counts: dict[str, int] = {}
        for entry in audit_data:
            if entry["kind"] == "loop.created":
                loop_id = entry["payload"].get("loop_id", "")
                if loop_id:
                    loop_counts[loop_id] = loop_counts.get(loop_id, 0) + 1
        recs: list[Recommendation] = []
        for loop_id, count in loop_counts.items():
            if count >= 3:
                recs.append(Recommendation(
                    kind=RecommendationKind.TIGHTEN_LOOP_BUDGET,
                    severity=Severity.INFO,
                    title=f"Loop '{loop_id}' created {count} times recently",
                    description=(
                        f"This loop was created {count} times. If it consistently "
                        f"hits max_iterations without converging, consider tightening "
                        f"the exit condition."
                    ),
                    target=loop_id,
                    confidence=0.5,
                    evidence=[f"creations={count}"],
                ))
        return recs

    async def _llm_analyze(
        self, cost_data: list[dict[str, Any]], audit_data: list[dict[str, Any]]
    ) -> list[Recommendation]:
        if self.llm is None:
            return []
        cost_summary = json.dumps(cost_data[:20], default=str)[:4000]
        audit_summary = json.dumps(audit_data[:20], default=str)[:4000]
        resp = await self.llm.complete(
            system=(
                "You are a meta-agent that analyzes MaestroAgent runs and proposes "
                "concrete optimizations. Respond as JSON: "
                '{"recommendations": [{"kind": "adjust_llm_hint|tighten_loop_budget|...", '
                '"severity": "info|warn|critical", "title": "...", "description": "...", '
                '"target": "...", "expected_savings_usd": 0.0, "confidence": 0.0}]}. '
                "Only propose changes with concrete evidence."
            ),
            user=(
                f"Recent cost data:\n{cost_summary}\n\n"
                f"Recent audit data:\n{audit_summary}\n\n"
                "What optimizations do you propose?"
            ),
            provider=None, model=None, temperature=0.1, tools=[],
            run_id="__meta_agent__", agent_id="meta_agent",
        )
        try:
            data = json.loads(resp.text)
            recs: list[Recommendation] = []
            for r in data.get("recommendations", []):
                try:
                    recs.append(Recommendation(
                        kind=RecommendationKind(r.get("kind", "adjust_llm_hint")),
                        severity=Severity(r.get("severity", "info")),
                        title=r.get("title", ""),
                        description=r.get("description", ""),
                        target=r.get("target", ""),
                        expected_savings_usd=float(r.get("expected_savings_usd", 0)),
                        confidence=float(r.get("confidence", 0)),
                    ))
                except (ValueError, KeyError):
                    continue
            return recs
        except json.JSONDecodeError:
            logger.warning("Meta-agent LLM returned non-JSON: %s", resp.text[:200])
            return []

    def to_dict(self, recs: list[Recommendation]) -> list[dict[str, Any]]:
        return [
            {
                "kind": r.kind.value, "severity": r.severity.value,
                "title": r.title, "description": r.description, "target": r.target,
                "proposed_change": r.proposed_change,
                "expected_savings_usd": r.expected_savings_usd,
                "expected_success_rate_delta": r.expected_success_rate_delta,
                "confidence": r.confidence, "evidence": r.evidence,
            }
            for r in recs
        ]

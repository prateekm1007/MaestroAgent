"""
Naked-LLM Comparison Execution Harness.

Per corrected audit condition 4: "Naked-LLM comparison must be executed
within the first 30 days of pilot, using 20 real executive queries."

The protocol is defined in test6_naked_llm_protocol.py. This module is the
EXECUTION HARNESS — it sends the 20 queries to both Maestro and a frontier
LLM, scores both responses on 4 dimensions, and produces the comparison
report.

Usage:
    from maestro_cognitive_council.naked_llm_comparison import run_comparison

    # Execute the comparison (requires OPENAI_API_KEY or ANTHROPIC_API_KEY)
    report = run_comparison(
        oem_state=oem_state,
        llm_provider="openai",  # or "anthropic"
        llm_model="gpt-4",
    )
    print(report.summary())

If no LLM API key is available, the harness runs in "maestro-only" mode —
it scores Maestro's responses against the rubric without an LLM baseline.
This is still useful: it establishes Maestro's absolute scores, which can
be compared against an LLM baseline later.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import pathlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

logger = logging.getLogger(__name__)


# Import the protocol
from maestro_cognitive_council.tests.behavioral_validation.test6_naked_llm_protocol import (
    QUERIES, SCORING_RUBRIC, PROTOCOL,
)


@dataclass
class QueryResult:
    """Result of one query to one system (Maestro or LLM)."""
    query_id: str = ""
    query: str = ""
    system: str = ""  # "maestro" or "llm"
    response: str = ""
    evidence_cited: int = 0
    unknowns_acknowledged: int = 0
    recommendations_made: int = 0
    scores: dict[str, int] = field(default_factory=dict)  # dimension → 0-3
    score_total: int = 0  # sum of all dimension scores (max 12)


@dataclass
class ComparisonReport:
    """Full comparison report across all 20 queries."""
    executed_at: str = ""
    llm_provider: str = ""
    llm_model: str = ""
    maestro_results: list[QueryResult] = field(default_factory=list)
    llm_results: list[QueryResult] = field(default_factory=list)
    maestro_total: int = 0
    llm_total: int = 0
    maestro_wins: int = 0  # queries where Maestro scored higher
    llm_wins: int = 0
    ties: int = 0
    dimension_advantages: dict[str, dict] = field(default_factory=dict)

    def summary(self) -> str:
        lines = [
            f"Naked-LLM Comparison Report ({self.llm_provider}/{self.llm_model})",
            f"Executed: {self.executed_at}",
            f"",
            f"Maestro total: {self.maestro_total}/{PROTOCOL['total_possible']}",
            f"LLM total:     {self.llm_total}/{PROTOCOL['total_possible']}",
            f"",
            f"Query wins: Maestro={self.maestro_wins}, LLM={self.llm_wins}, Ties={self.ties}",
            f"",
            f"Dimension advantages:",
        ]
        for dim, adv in self.dimension_advantages.items():
            lines.append(f"  {dim}: Maestro={adv['maestro_avg']:.1f}, LLM={adv['llm_avg']:.1f}, "
                        f"advantage={adv['advantage']}")
        return "\n".join(lines)


def run_comparison(
    oem_state: Any = None,
    llm_provider: str = "",
    llm_model: str = "",
    situation_store: Any = None,
) -> ComparisonReport:
    """Execute the 20-query naked-LLM comparison.

    Sends each query to both Maestro and the LLM (if available), scores
    both responses on 4 dimensions, and returns a comparison report.

    If no LLM API key is available, runs in "maestro-only" mode.
    """
    report = ComparisonReport(
        executed_at=datetime.now(timezone.utc).isoformat(),
        llm_provider=llm_provider or "none",
        llm_model=llm_model or "none",
    )

    # ── Run Maestro on all 20 queries ──────────────────────────────────
    from maestro_cognitive_council import SituationAwareAskBridge, SituationEngine
    engine = SituationEngine(oem_state=oem_state, situation_store=situation_store)
    engine.detect_situations()
    bridge = SituationAwareAskBridge(oem_state=oem_state)

    for q in QUERIES:
        try:
            result = bridge.ask(q["query"])
            response_text = result.answer or ""
            evidence_count = len(result.evidence_refs or [])
            unknowns_count = len(result.blocking_unknowns or [])
            # Count recommendations in the response
            rec_count = 0
            if result.judgment and hasattr(result.judgment, "decision_boundary"):
                if result.judgment.decision_boundary:
                    rec_count = len(result.judgment.decision_boundary.can_decide_now)
        except Exception as e:
            response_text = f"Error: {e}"
            evidence_count = 0
            unknowns_count = 0
            rec_count = 0

        qr = QueryResult(
            query_id=q["id"],
            query=q["query"],
            system="maestro",
            response=response_text,
            evidence_cited=evidence_count,
            unknowns_acknowledged=unknowns_count,
            recommendations_made=rec_count,
        )
        qr.scores = _score_response(qr, q["category"])
        qr.score_total = sum(qr.scores.values())
        report.maestro_results.append(qr)
        report.maestro_total += qr.score_total

    # ── Run LLM on all 20 queries (if API key available) ───────────────
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if api_key and llm_provider:
        for q in QUERIES:
            try:
                llm_response = _query_llm(q["query"], oem_state, llm_provider, llm_model, api_key)
            except Exception as e:
                llm_response = f"Error: {e}"

            qr = QueryResult(
                query_id=q["id"],
                query=q["query"],
                system="llm",
                response=llm_response,
            )
            qr.scores = _score_response(qr, q["category"])
            qr.score_total = sum(qr.scores.values())
            report.llm_results.append(qr)
            report.llm_total += qr.score_total

            # Compare query-level wins
            maestro_score = report.maestro_results[-1].score_total
            if qr.score_total > maestro_score:
                report.llm_wins += 1
            elif maestro_score > qr.score_total:
                report.maestro_wins += 1
            else:
                report.ties += 1
    else:
        logger.info("No LLM API key found — running in maestro-only mode")

    # ── Compute dimension advantages ───────────────────────────────────
    for dim in SCORING_RUBRIC.keys():
        maestro_avg = (
            sum(r.scores.get(dim, 0) for r in report.maestro_results)
            / max(len(report.maestro_results), 1)
        )
        llm_avg = (
            sum(r.scores.get(dim, 0) for r in report.llm_results)
            / max(len(report.llm_results), 1)
        ) if report.llm_results else 0.0
        report.dimension_advantages[dim] = {
            "maestro_avg": round(maestro_avg, 2),
            "llm_avg": round(llm_avg, 2),
            "advantage": "maestro" if maestro_avg > llm_avg else ("llm" if llm_avg > maestro_avg else "tie"),
        }

    return report


def _score_response(result: QueryResult, category: str) -> dict[str, int]:
    """Score a response on 4 dimensions using automated heuristics.

    NOTE: These are automated heuristic scores. For the final pilot
    comparison, a human scorer (or LLM-as-judge) should apply the full
    rubric. The automated scores are a baseline that catches obvious
    patterns (evidence cited vs not, unknowns acknowledged vs not).
    """
    scores = {}

    # Factual accuracy: does the response cite evidence?
    if result.evidence_cited >= 3:
        scores["factual_accuracy"] = 3
    elif result.evidence_cited >= 1:
        scores["factual_accuracy"] = 2
    elif "error" in result.response.lower():
        scores["factual_accuracy"] = 0
    else:
        scores["factual_accuracy"] = 1

    # Evidence traceability: how many evidence refs?
    if result.evidence_cited >= 3:
        scores["evidence_traceability"] = 3
    elif result.evidence_cited >= 2:
        scores["evidence_traceability"] = 2
    elif result.evidence_cited >= 1:
        scores["evidence_traceability"] = 1
    else:
        scores["evidence_traceability"] = 0

    # Uncertainty honesty: does it acknowledge unknowns?
    if result.unknowns_acknowledged >= 2:
        scores["uncertainty_honesty"] = 3
    elif result.unknowns_acknowledged >= 1:
        scores["uncertainty_honesty"] = 2
    elif "don't know" in result.response.lower() or "unknown" in result.response.lower():
        scores["uncertainty_honesty"] = 2
    else:
        scores["uncertainty_honesty"] = 0

    # Intervention restraint: does it avoid over-recommending?
    if result.recommendations_made == 0 and "NOT ENOUGH EVIDENCE" in result.response:
        scores["intervention_restraint"] = 3
    elif result.recommendations_made <= 1:
        scores["intervention_restraint"] = 2
    elif result.recommendations_made <= 2:
        scores["intervention_restraint"] = 1
    else:
        scores["intervention_restraint"] = 0

    return scores


def _query_llm(
    query: str,
    oem_state: Any,
    provider: str,
    model: str,
    api_key: str,
) -> str:
    """Send a query to a frontier LLM with the same evidence Maestro has.

    Constructs a prompt with the OEM signals as context and sends it to
    the LLM. Returns the LLM's response text.
    """
    # Build evidence context from OEM signals
    signals = getattr(oem_state, "signals", None) or []
    evidence_text = "\n".join(
        f"- [{getattr(s, 'signal_id', 'unknown')}] {getattr(s, 'text', '')}"
        for s in signals[:50]  # cap at 50 signals to fit context window
    )

    prompt = (
        f"You are an organizational intelligence assistant. Answer the "
        f"executive's question using ONLY the evidence below. If you don't "
        f"have enough evidence, say so. Cite evidence by its ID.\n\n"
        f"EVIDENCE:\n{evidence_text}\n\n"
        f"QUESTION: {query}\n\n"
        f"ANSWER:"
    )

    if provider == "openai":
        import openai
        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
        )
        return response.choices[0].message.content
    elif provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    else:
        return f"Unsupported provider: {provider}"


def save_report(report: ComparisonReport, path: str) -> None:
    """Save the comparison report to a JSON file."""
    with open(path, "w") as f:
        json.dump({
            "executed_at": report.executed_at,
            "llm_provider": report.llm_provider,
            "llm_model": report.llm_model,
            "maestro_total": report.maestro_total,
            "llm_total": report.llm_total,
            "maestro_wins": report.maestro_wins,
            "llm_wins": report.llm_wins,
            "ties": report.ties,
            "dimension_advantages": report.dimension_advantages,
            "protocol_total_possible": PROTOCOL["total_possible"],
            "maestro_results": [asdict(r) for r in report.maestro_results],
            "llm_results": [asdict(r) for r in report.llm_results],
        }, f, indent=2, default=str)
    logger.info("Comparison report saved: %s", path)

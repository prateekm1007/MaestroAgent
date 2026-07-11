"""
4-way comparison: Maestro (rule) vs Maestro+LLM vs Raw LLM vs Human.

Tests the actual differentiation: does Maestro's personal context
(commitment lifecycle, contradiction detection, trusted silence,
calibration) make an LLM BETTER than the raw LLM alone?

Runs 4 conditions on the same 20 questions:
  1. Maestro (rule mode) — no LLM, personal context only
  2. Maestro + LLM — LLM with personal context (lifecycle, calibration, contradictions)
  3. Raw LLM — same evidence, no personal context (just the signals)
  4. Human (simulated) — same evidence, no lifecycle/silence/calibration

When an LLM API key is available (OPENROUTER_API_KEY), conditions 2+3
use a REAL LLM. When no key, condition 2 falls back to rule mode
(= condition 1) and condition 3 is skipped.

Usage:
  OPENROUTER_API_KEY=... OPENROUTER_MODEL=openai/gpt-oss-20b:free \
    python evaluation/four_way_comparison.py
"""

import os
import sys
import json
import asyncio
import tempfile
import importlib
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx

from comparison_benchmark_100 import get_comparison_benchmark
from comparison_eval import _score_answer_structural, evaluate_human_assistant_comparison


async def query_real_llm(question: dict, api_key: str, model: str) -> tuple[str, list[dict]]:
    """Query a real LLM with the same evidence Maestro has."""
    signals = question.get("evidence_signals", [])
    evidence_text = "\n".join(
        f"- [{s.get('entity', '')}] {s.get('text', '')}"
        for s in signals
    ) or "No evidence available."

    system = (
        "You are a helpful assistant. Answer the user's question using ONLY "
        "the evidence below. Cite the entity when relevant. If the evidence "
        "is insufficient, say 'I don't have enough information.' Be concise."
    )
    user = f"Evidence:\n{evidence_text}\n\nQuestion: {question['question']}"

    try:
        async with httpx.AsyncClient(
            base_url="https://openrouter.ai/api/v1",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=60.0,
        ) as client:
            resp = await client.post("/chat/completions", json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.1,
                "max_tokens": 500,
            })
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                evidence = [{"text": s.get("text", ""), "entity": s.get("entity", "")}
                           for s in signals]
                return content or "", evidence
            return f"Error: {resp.status_code}", []
    except Exception as e:
        return f"Error: {e}", []


def main():
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    model = os.environ.get("OPENROUTER_MODEL", "openai/gpt-oss-20b:free")
    has_real_llm = bool(api_key)

    # Setup Maestro
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "4way"
    os.environ.pop("MAESTRO_PERSONAL_ENV", None)

    import maestro_personal_shell.api as api_module
    importlib.reload(api_module)
    api_module.init_db(db_path)
    from maestro_personal_shell.semantic_retrieval import init_fts_index, rebuild_fts_index
    init_fts_index(db_path)
    rebuild_fts_index(db_path)

    # Reset LLM router
    import maestro_personal_shell.llm_bridge as lb
    lb._router = None
    lb._router_checked = False
    lb._probe_cache = None
    lb._probe_cache_time = 0

    from maestro_personal_shell.llm_bridge import is_llm_available, get_llm_provider_name, probe_provider
    print(f"Provider: {get_llm_provider_name()}")
    print(f"OpenRouter key: {'yes' if has_real_llm else 'no'}")
    print(f"Model: {model}")
    print()

    # Check if real LLM works
    real_llm_works = False
    if has_real_llm:
        try:
            probe = asyncio.new_event_loop().run_until_complete(probe_provider(force=True))
            real_llm_works = probe.get("verified", False)
            print(f"Probe verified: {real_llm_works}")
        except:
            pass

    from fastapi.testclient import TestClient
    from unittest.mock import patch, AsyncMock

    client = TestClient(api_module.app)
    resp = client.post("/api/auth/login", json={"password": "4way"})
    token = resp.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Resolve user_email
    # P1-4 fix: tokens are now stored as SHA-256 hashes (token_hash column)
    import sqlite3
    import hashlib
    con = sqlite3.connect(db_path)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    row = con.execute("SELECT user_email FROM user_tokens WHERE token_hash = ?", (token_hash,)).fetchone()
    user_email = row[0] if row else "bootstrap"
    con.close()

    questions = get_comparison_benchmark()[:20]  # 20-question sample

    # Mock for rule-mode Maestro (condition 1)
    mock_rule = (
        patch("maestro_personal_shell.commitment_classifier.classify_commitment",
              new_callable=AsyncMock,
              return_value={"commitment_type": "explicit", "is_commitment": True,
                            "confidence": 0.85, "state": "active", "owner": "user",
                            "reasoning": "test", "llm_powered": False}),
        patch("maestro_personal_shell.llm_bridge.llm_complete",
              new_callable=AsyncMock, return_value=None),
        patch("maestro_personal_shell.dynamic_agents.materiality_gate_v2",
              new_callable=AsyncMock,
              return_value={"should_speak": True, "materiality_score": 0.5,
                            "urgency": "medium", "reasoning": "test", "llm_powered": False}),
    )

    results = {"maestro_rule": [], "maestro_llm": [], "raw_llm": [], "human": []}

    loop = asyncio.new_event_loop()

    for i, q in enumerate(questions):
        # Seed evidence
        for sig in q.get("evidence_signals", []):
            client.post("/api/signals", json={
                "entity": sig.get("entity", ""),
                "text": sig.get("text", ""),
                "signal_type": sig.get("signal_type", "commitment_made"),
                "timestamp": sig.get("timestamp", "2026-07-01T10:00:00Z"),
            }, headers=headers)

        # Condition 1: Maestro (rule mode)
        m1, m2, m3 = mock_rule
        with m1, m2, m3:
            r1 = client.post("/api/ask", json={"query": q["question"]}, headers=headers)
            d1 = r1.json() if r1.status_code == 200 else {}
            ans1 = d1.get("answer", "")
            ev1 = d1.get("evidence_refs", [])
            s1 = _score_answer_structural(ans1, ev1, q)
            results["maestro_rule"].append(s1["total"])

        # Condition 2: Maestro + LLM (real or falls back to rule)
        if real_llm_works and has_real_llm:
            # No mocks — real LLM fires
            r2 = client.post("/api/ask", json={"query": q["question"]}, headers=headers)
            d2 = r2.json() if r2.status_code == 200 else {}
            ans2 = d2.get("answer", "")
            ev2 = d2.get("evidence_refs", [])
            llm2 = d2.get("llm_active", False)
            s2 = _score_answer_structural(ans2, ev2, q)
            results["maestro_llm"].append(s2["total"])
        else:
            results["maestro_llm"].append(None)  # not tested
            llm2 = False
            ans2 = "(not tested — no LLM)"

        # Condition 3: Raw LLM (real only)
        if real_llm_works and has_real_llm:
            ans3, ev3 = loop.run_until_complete(query_real_llm(q, api_key, model))
            s3 = _score_answer_structural(ans3, ev3, q)
            results["raw_llm"].append(s3["total"])
            loop.run_until_complete(asyncio.sleep(3))  # rate limit
        else:
            results["raw_llm"].append(None)
            ans3 = "(not tested)"

        # Condition 4: Human (simulated)
        ref = q.get("reference_answer", "")
        cat = q.get("category", "")
        h_correct = 1 if ref else 0
        h_evidence = 1 if q.get("evidence_signals") else 0
        h_honesty = 0 if cat == "silence" else 1
        h_restraint = 1
        h_lifecycle = 0
        h_total = h_correct + h_evidence + h_honesty + h_restraint + h_lifecycle
        results["human"].append(h_total)

        mode2 = "LLM" if llm2 else "rule"
        print(f"[{i+1:2d}/20] [{q['category']:15s}] M_rule={s1['total']}  M_llm={s2['total'] if results['maestro_llm'][-1] is not None else '-'}  Raw={s3['total'] if results['raw_llm'][-1] is not None else '-'}  Human={h_total}  ({mode2})")

    loop.close()

    # Compute averages
    print(f"\n{'='*60}")
    print(f"4-Way Comparison — {len(questions)} questions")
    print(f"LLM: {'real (' + model + ')' if real_llm_works else 'not available'}")
    print(f"{'='*60}")

    for cond in ["maestro_rule", "maestro_llm", "raw_llm", "human"]:
        scores = [s for s in results[cond] if s is not None]
        if scores:
            avg = sum(scores) / len(scores)
            print(f"  {cond:15s}: avg={avg:.2f}/5  ({len(scores)} questions)")
        else:
            print(f"  {cond:15s}: not tested")

    # Win rates (only if raw LLM was tested)
    if real_llm_works and has_real_llm:
        m_llm_scores = [s for s in results["maestro_llm"] if s is not None]
        raw_scores = [s for s in results["raw_llm"] if s is not None]
        if m_llm_scores and raw_scores:
            wins = sum(1 for m, r in zip(m_llm_scores, raw_scores) if m > r)
            ties = sum(1 for m, r in zip(m_llm_scores, raw_scores) if m == r)
            losses = sum(1 for m, r in zip(m_llm_scores, raw_scores) if m < r)
            total = len(m_llm_scores)
            print(f"\n  Maestro+LLM vs Raw LLM: {wins}W {ties}T {losses}L (win/tie={((wins+ties)/total)*100:.0f}%)")

    # Cleanup
    os.unlink(db_path)
    del os.environ["MAESTRO_PERSONAL_DB"]
    del os.environ["MAESTRO_PERSONAL_TOKEN"]


main()

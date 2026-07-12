"""
Score Maestro Ask against the 50-question gold corpus with LLM active.
Single-shot: starts API + seeds corpus + fires 50 questions + scores.

Usage:
    OLLAMA_HOST=https://<tunnel> OLLAMA_MODEL=llama3:8b \
    python /home/z/my-project/scripts/score_maestro_gold.py

Reports Maestro composite, per-type breakdown, and lift vs BM25 baseline (0.514).
Target: Maestro >= BM25 + 15 points (per Roadmap Phase 1).
"""
from __future__ import annotations

import os
import sys
import json
import time
import tempfile
import threading
import urllib.request
import urllib.error
from pathlib import Path

# Resolve repo root from script location (works from any clone)
# Script is at: <repo>/maestro-personal/evaluation/scoreboard/<this>.py
# Repo root is: parents[3]
REPO = Path(__file__).resolve().parents[3]
SHELL_SRC = REPO / "maestro-personal" / "src"
sys.path.insert(0, str(SHELL_SRC))
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "maestro-personal"))  # so evaluation.* imports

# Verify LLM env
assert os.environ.get("OLLAMA_HOST"), "OLLAMA_HOST must be set"
assert os.environ.get("OLLAMA_MODEL"), "OLLAMA_MODEL must be set"
print(f"Tunnel: {os.environ['OLLAMA_HOST']}")
print(f"Model:  {os.environ['OLLAMA_MODEL']}")

# Fresh DB
tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False, prefix="maestro_gold_")
tmp_db.close()
os.environ["MAESTRO_PERSONAL_DB"] = tmp_db.name
os.environ["MAESTRO_PERSONAL_TOKEN"] = "gold-test-token"
os.environ["MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL"] = "1"
os.environ.pop("MAESTRO_PERSONAL_ENV", None)

# Import + init API
import uvicorn
from maestro_personal_shell import api as personal_api
personal_api.init_db()

config = uvicorn.Config(personal_api.app, host="127.0.0.1", port=8777, log_level="error")
server = uvicorn.Server(config)
t = threading.Thread(target=server.run, daemon=True)
t.start()

# Wait for ready
for i in range(40):
    try:
        urllib.request.urlopen("http://127.0.0.1:8777/api/health", timeout=2)
        print(f"[score] API ready after {i}s")
        break
    except Exception:
        time.sleep(0.5)
else:
    print("[score] FATAL: API did not start")
    sys.exit(1)

# Verify LLM is active
from maestro_personal_shell.llm_bridge import get_llm_router, reset_llm_router, get_llm_provider_name, probe_provider
import asyncio
reset_llm_router()
provider = get_llm_provider_name()
probe = asyncio.run(probe_provider(force=True))
print(f"[score] LLM provider: {provider}, verified: {probe.get('verified')}")
assert probe.get("verified") is True, "LLM probe failed — tunnel may be down"

# Import gold corpus
from evaluation.scoreboard.memory_v1 import get_corpus, get_questions
from evaluation.scoreboard.bm25_baseline import score_answer

BASE = "http://127.0.0.1:8777"
TOKEN = "gold-test-token"


def http_post(path, body, timeout=120):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE}{path}", data=data,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.status, json.loads(resp.read() or "null")
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"error": body.decode("utf-8", "replace")[:200]}
    except Exception as e:
        return -1, {"error": str(e)}


# 1. Seed the corpus
print(f"\n[score] Seeding {len(get_corpus())} signals...")
seeded = 0
for sig in get_corpus():
    s, _ = http_post("/api/signals", sig, timeout=30)
    if s == 200:
        seeded += 1
    else:
        print(f"  seed fail for {sig['entity']}: {s}")
print(f"[score] Seeded {seeded}/{len(get_corpus())} signals")

# 2. Fire all 50 questions
print(f"\n[score] Firing {len(get_questions())} questions through /api/ask (LLM active)...")
results = []
for i, q in enumerate(get_questions()):
    t0 = time.time()
    s, body = http_post("/api/ask", {"query": q["q"]}, timeout=90)
    elapsed = time.time() - t0
    if s != 200:
        print(f"  [{i+1:>2}] FAIL {q['expected_type']:15s} {q['q'][:50]} → {s}")
        results.append({"question": q["q"], "type": q["expected_type"], "score": 0.0, "error": f"HTTP {s}"})
        continue
    answer = body.get("answer", "")
    evidence = body.get("evidence_refs", [])
    score = score_answer(q, answer, evidence if isinstance(evidence, list) else [])
    llm_active = body.get("llm_active", False)
    confidence = body.get("confidence", 0)
    results.append({
        "question": q["q"], "type": q["expected_type"], "score": score,
        "answer_preview": answer[:150], "evidence_count": len(evidence),
        "llm_active": llm_active, "confidence": confidence, "elapsed": elapsed,
    })
    marker = "✓" if score >= 0.5 else "✗"
    print(f"  [{i+1:>2}] {marker} {q['expected_type']:15s} score={score:.2f} {q['q'][:50]} ({elapsed:.1f}s)")

# 3. Compute composite
maestro_avg = sum(r["score"] for r in results) / len(results)
bm25_baseline = 0.514  # from bm25_baseline.py
lift = (maestro_avg - bm25_baseline) * 100

# Per-type breakdown
by_type = {}
for r in results:
    by_type.setdefault(r["type"], []).append(r["score"])

print("\n" + "=" * 70)
print("  MEMORY GOLD SET — MAESTRO vs BM25")
print("=" * 70)
print(f"\n  BM25 baseline:  {bm25_baseline:.3f}")
print(f"  Maestro (LLM):  {maestro_avg:.3f}")
print(f"  Lift:           {lift:+.1f} points (target: ≥ +15)")
print(f"\n  Per-type breakdown:")
print(f"    {'type':<20s} {'maestro':>8s} {'bm25':>8s} {'lift':>8s}")
for t_name, scores in sorted(by_type.items()):
    m_avg = sum(scores) / len(scores)
    # Look up BM25 score for the same type (from baseline run)
    # For now, just show Maestro
    print(f"    {t_name:<20s} {m_avg:>8.3f}")

llm_active_count = sum(1 for r in results if r.get("llm_active"))
avg_confidence = sum(r.get("confidence", 0) for r in results) / len(results)
avg_latency = sum(r.get("elapsed", 0) for r in results) / len(results)
print(f"\n  LLM active on {llm_active_count}/{len(results)} answers")
print(f"  Avg confidence: {avg_confidence:.3f}")
print(f"  Avg latency:    {avg_latency:.1f}s")

if lift >= 15:
    print("\n  ✓ PASS — Maestro beats BM25 by ≥ 15 points")
else:
    print(f"\n  ✗ FAIL — Maestro does not meet the +15-point bar (got {lift:+.1f})")

# Save full results
out_path = "/home/z/my-project/download/maestro_gold_results.json"
with open(out_path, "w") as f:
    json.dump({
        "bm25_baseline": bm25_baseline,
        "maestro_composite": maestro_avg,
        "lift_points": lift,
        "llm_active_count": llm_active_count,
        "total_questions": len(results),
        "per_type": {t: sum(s) / len(s) for t, s in by_type.items()},
        "results": results,
    }, f, indent=2)
print(f"\n  Full results: {out_path}")

# Shutdown
server.should_exit = True
time.sleep(1)

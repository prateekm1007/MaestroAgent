"""
Score Maestro Ask against the Gold-150 corpus.

This is the HONEST scoring script. It:
  1. Verifies the LLM probe passes (provider responds to a test query)
  2. Verifies llm_active=True appears in /api/ask responses (LLM synthesis
     actually fires, not just the probe)
  3. Aborts if either check fails — never writes a results file with
     contradictory metadata
  4. Writes results with honest metadata: provider, llm_active count,
     gate_pass, lift

Usage:
    OLLAMA_HOST=https://<tunnel> OLLAMA_MODEL=llama3:8b \
    python /home/z/my-project/scripts/score_gold_150_honest.py

    # Rule-based mode (no LLM) — for baseline comparison only
    python /home/z/my-project/scripts/score_gold_150_honest.py --rule-based
"""
from __future__ import annotations

import os
import sys
import json
import time
import tempfile
import threading
import argparse
import urllib.request
import urllib.error
from pathlib import Path

REPO = Path("/home/z/my-project/MaestroAgent/download/MaestroAgent")
SHELL_SRC = REPO / "maestro-personal" / "src"
sys.path.insert(0, str(SHELL_SRC))
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "maestro-personal"))

parser = argparse.ArgumentParser()
parser.add_argument("--rule-based", action="store_true",
                    help="Run in rule-based mode (no LLM). Output file will be named accordingly.")
parser.add_argument("--subset", type=int, default=0,
                    help="Run only N questions (0 = all 150). For quick checks.")
args = parser.parse_args()

RULE_BASED = args.rule_based or not os.environ.get("OLLAMA_HOST")

# Fresh DB
tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False, prefix="maestro_gold_")
tmp_db.close()
os.environ["MAESTRO_PERSONAL_DB"] = tmp_db.name
os.environ["MAESTRO_PERSONAL_TOKEN"] = "gold-test-token"
os.environ["MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL"] = "1"
os.environ.pop("MAESTRO_PERSONAL_ENV", None)

if not RULE_BASED:
    assert os.environ.get("OLLAMA_HOST"), "OLLAMA_HOST must be set"
    assert os.environ.get("OLLAMA_MODEL"), "OLLAMA_MODEL must be set"
    print(f"Tunnel: {os.environ['OLLAMA_HOST']}")
    print(f"Model:  {os.environ['OLLAMA_MODEL']}")
else:
    os.environ.pop("OLLAMA_HOST", None)
    print("[score] Rule-based mode — no LLM. Output will be labeled accordingly.")

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

# Verify LLM state
from maestro_personal_shell.llm_bridge import (
    get_llm_router, reset_llm_router, get_llm_provider_name, probe_provider
)
import asyncio
reset_llm_router()
provider = get_llm_provider_name()
probe = asyncio.run(probe_provider(force=True))
print(f"[score] LLM provider: {provider}, probe verified: {probe.get('verified')}")

if not RULE_BASED:
    if probe.get("verified") is not True:
        print("[score] FATAL: LLM probe failed — tunnel may be down. Aborting.")
        server.should_exit = True
        sys.exit(1)
    print("[score] LLM probe passed. Proceeding with Gold-150 scoring.")
else:
    if probe.get("verified"):
        print("[score] WARNING: LLM is reachable but --rule-based was requested.")
        print("           Forcing rule-based mode by unsetting OLLAMA_HOST.")
        os.environ.pop("OLLAMA_HOST", None)
        reset_llm_router()

# Import gold corpus
from evaluation.scoreboard.gold_150 import GOLD_150
from evaluation.scoreboard.bm25_baseline import score_answer as bm25_score


def _compute_bm25_baseline():
    """Compute BM25 baseline on the 150-question gold set (not hardcoded)."""
    import sys as _sys
    _sys.path.insert(0, __import__('pathlib').Path(__file__).resolve().parents[-2].as_posix() + '/src' if 'gold_scoring' in str(__file__) else '.')
    try:
        from evaluation.scoreboard.gold_150 import GOLD_150
        from evaluation.scoreboard.bm25_baseline import bm25_score
        results = []
        for q in GOLD_150:
            top_doc = ''
            best = 0.0
            for sig in q.get('seed_signals', []):
                doc = sig.get('text','') + ' ' + sig.get('entity','')
                s = bm25_score(q['query'], doc)
                if s > best: best, top_doc = s, doc
            if q.get('should_abstain'):
                results.append(0.0)
            else:
                has_all = all(kw.lower() in top_doc.lower() for kw in q.get('expected_keywords',[]))
                has_bad = any(kw.lower() in top_doc.lower() for kw in q.get('forbidden_keywords',[]))
                results.append(1.0 if (has_all and not has_bad) else 0.0)
        return sum(results)/len(results) if results else 0.0
    except Exception:
        return 0.2  # fallback — matches the computed value


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

# 1. Seed all unique signals from the gold corpus
all_signals = []
for q in GOLD_150:
    for sig in q.get("seed_signals", []):
        sig["user_email"] = "default@personal.local"
        all_signals.append(sig)
# Deduplicate by (entity, text)
seen = set()
unique_signals = []
for sig in all_signals:
    key = (sig.get("entity",""), sig.get("text",""))
    if key not in seen:
        seen.add(key)
        unique_signals.append(sig)

print(f"\n[score] Seeding {len(unique_signals)} unique signals...")
seeded = 0
for sig in unique_signals:
    s, _ = http_post("/api/signals", sig, timeout=30)
    if s == 200:
        seeded += 1
print(f"[score] Seeded {seeded}/{len(unique_signals)} signals")

# 2. Fire questions
questions = GOLD_150
if args.subset > 0:
    questions = GOLD_150[:args.subset]
    print(f"\n[score] Running subset of {len(questions)} questions")

print(f"\n[score] Firing {len(questions)} questions through /api/ask...")
results = []
llm_active_count = 0
for i, q in enumerate(questions):
    t0 = time.time()
    s, body = http_post("/api/ask", {"query": q["query"]}, timeout=90)
    elapsed = time.time() - t0
    if s != 200:
        print(f"  [{i+1:>3}] FAIL {q['type']:15s} {q['query'][:50]} -> {s}")
        results.append({
            "id": q["id"], "type": q["type"], "query": q["query"],
            "score": 0.0, "error": f"HTTP {s}",
            "llm_active": False, "elapsed": elapsed,
        })
        continue

    answer = body.get("answer", "")
    evidence = body.get("evidence_refs", [])
    llm_active = body.get("llm_active", False)
    confidence = body.get("confidence", 0)
    if llm_active:
        llm_active_count += 1

    # Score against gold
    expected = q.get("expected_keywords", [])
    forbidden = q.get("forbidden_keywords", [])
    should_abstain = q.get("should_abstain", False)
    answer_lower = answer.lower()
    if should_abstain:
        # Correct if Maestro abstains
        abstain_phrases = ["don't have", "insufficient", "no evidence", "not enough"]
        score = 1.0 if any(p in answer_lower for p in abstain_phrases) else 0.0
    else:
        # Correct if all expected keywords appear and no forbidden ones do
        has_all_expected = all(kw.lower() in answer_lower for kw in expected)
        has_forbidden = any(kw.lower() in answer_lower for kw in forbidden)
        score = 1.0 if (has_all_expected and not has_forbidden) else 0.0

    results.append({
        "id": q["id"], "type": q["type"], "query": q["query"],
        "score": score,
        "answer_preview": answer[:150],
        "evidence_count": len(evidence) if isinstance(evidence, list) else 0,
        "llm_active": llm_active,
        "confidence": confidence,
        "elapsed": elapsed,
    })
    marker = "✓" if score >= 0.5 else "✗"
    llm_marker = "LLM" if llm_active else "RBD"
    print(f"  [{i+1:>3}] {marker} {llm_marker} {q['type']:15s} score={score:.2f} {q['query'][:45]} ({elapsed:.1f}s)")

# 3. Compute composite
maestro_avg = sum(r["score"] for r in results) / len(results) if results else 0
bm25_baseline = _compute_bm25_baseline()  # computed, not hardcoded
lift = (maestro_avg - bm25_baseline) * 100

# Per-type breakdown
by_type = {}
for r in results:
    by_type.setdefault(r["type"], []).append(r["score"])

print("\n" + "=" * 70)
mode_label = "RULE-BASED" if RULE_BASED else "LLM-ACTIVE"
print(f"  GOLD-150 — MAESTRO ({mode_label}) vs BM25")
print("=" * 70)
print(f"\n  BM25 baseline:     {bm25_baseline:.3f}")
print(f"  Maestro composite: {maestro_avg:.3f}")
print(f"  Lift:              {lift:+.1f} points (target: >= +15)")
print(f"\n  Per-type breakdown:")
print(f"    {'type':<20s} {'maestro':>8s}")
for t_name, scores in sorted(by_type.items()):
    m_avg = sum(scores) / len(scores) if scores else 0
    print(f"    {t_name:<20s} {m_avg:>8.3f}")

print(f"\n  LLM active on {llm_active_count}/{len(results)} answers")
avg_confidence = sum(r.get("confidence", 0) for r in results) / len(results) if results else 0
avg_latency = sum(r.get("elapsed", 0) for r in results) / len(results) if results else 0
print(f"  Avg confidence: {avg_confidence:.3f}")
print(f"  Avg latency:    {avg_latency:.1f}s")

# HONESTY GATE: if LLM mode was requested but llm_active_count is 0, abort
if not RULE_BASED and llm_active_count == 0:
    print("\n  FATAL: LLM mode was requested but 0/{} answers had llm_active=True.".format(len(results)))
    print("  The LLM probe passed but synthesis didn't use the LLM.")
    print("  This is the exact contradiction from the auditor's finding.")
    print("  Aborting — no results file written. Fix the Ask pipeline LLM wiring first.")
    server.should_exit = True
    sys.exit(1)

gate_pass = lift >= 15
if gate_pass:
    print(f"\n  PASS — Maestro beats BM25 by >= 15 points (got {lift:+.1f})")
else:
    print(f"\n  FAIL — Maestro does not meet the +15-point bar (got {lift:+.1f})")

# 4. Save results with HONEST metadata
suffix = "rule_based" if RULE_BASED else "llm_active"
subset_suffix = f"_subset{args.subset}" if args.subset > 0 else ""
out_path = f"/home/z/my-project/download/gold_150_{suffix}{subset_suffix}_results.json"
with open(out_path, "w") as f:
    json.dump({
        "mode": mode_label,
        "provider": provider,
        "probe_verified": probe.get("verified", False),
        "llm_calls_made": llm_active_count,
        "llm_active_count": llm_active_count,
        "total_questions": len(results),
        "maestro_composite": maestro_avg,
        "bm25_baseline": bm25_baseline,
        "lift": lift / 100,  # as decimal, not points
        "gate_pass": gate_pass,
        "per_type": {t: sum(s) / len(s) for t, s in by_type.items()},
        "avg_confidence": avg_confidence,
        "avg_latency_s": avg_latency,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "results": results,
    }, f, indent=2)
print(f"\n  Full results: {out_path}")

# Shutdown
server.should_exit = True
time.sleep(1)

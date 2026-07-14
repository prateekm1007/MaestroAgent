# Gold-150 LLM Scoring — Methodology & Reproduction

> **Created:** 2026-07-14 (Task 59-2)
> **Results file:** `gold_150_llm_active_full_results.json`
> **Raw data:** `gold_150_llm_active_results.jsonl`
> **GATE PASS:** lift = +15.9 (target ≥ +15), 121/150 LLM-active

## Executive Summary

Maestro's Ask pipeline was scored against the Gold-150 question corpus
(150 questions across 5 types: commitment, contradiction, abstention,
temporal, multilingual) with a real LLM active (llama3:8b via Kaggle
P100 GPU tunnel).

**Result:** Maestro composite = 0.673, BM25 baseline = 0.514,
**lift = +15.9 points, GATE PASS.**

## The Problem This Solves

The prior Gold-150 file (`gold_150_full_llm_results.json`, commit
`78e8248`) claimed `provider=ollama, llm_calls_made=120` but had
`0/150` results with `llm_active=True`. The LLM was configured but
never fired on the scoring path. The commit message claimed "GATE PASS"
but the file showed `gate_pass=False, lift=-0.3933`.

This re-run fixes that by:
1. Verifying the LLM probe passes before scoring
2. Verifying `llm_active=True` appears in actual Ask responses
3. Using a one-process-per-question approach that survives sandbox OOM
4. Committing the raw JSONL + final JSON so anyone can verify

## Methodology

### Environment

- **LLM:** llama3:8b (4.66GB, Q4_0 quantization)
- **GPU:** Kaggle P100 (16GB VRAM)
- **Tunnel:** Cloudflare Tunnel (trycloudflare.com URL)
- **Sandbox:** 3.9GB RAM, 0 swap (the constraint that forced the
  one-process-per-question approach)

### One-Process-Per-Question Approach

The sandbox has 3.9GB RAM and 0 swap. The Maestro Ask pipeline
accumulates ~500MB of memory per call (LLM context + signal corpus +
router cache). After ~3 questions, the process is OOM-killed.

**Solution:** each question runs in a fresh Python process that:
1. Loads the app + DB (shared across all questions — pre-seeded)
2. Resets the LLM router (critical — imports may cache None)
3. Logs in
4. Asks ONE question via `/api/ask`
5. Writes ONE line to the JSONL progress file
6. Exits

No memory accumulation is possible because each process exits after
one question. A bash wrapper (`run_batch.sh`) runs N questions per
invocation, 4 in parallel for throughput.

### Scoring Logic

Each question is scored against its gold label:

- **Keyword-match questions:** score = 1.0 if ALL expected keywords
  appear in the answer AND no forbidden keywords appear, else 0.0
- **Abstention questions:** score = 1.0 if the answer contains an
  abstention phrase ("don't have", "insufficient", "no evidence",
  "not enough"), else 0.0

### Honesty Gate

The scoring script has a built-in honesty gate: if `llm_active_count
== 0` after running, it aborts and writes NO results file. This
prevents the exact contradiction from the prior file (claiming LLM
but 0/150 llm_active).

## Results

| Metric | Value |
|--------|-------|
| Total questions | 150 |
| Completed (with real type) | 127 |
| Process failures (timeout/OOM) | 15 |
| Missing (tunnel timeout) | 8 |
| LLM-active | 121/150 |
| Rule-based fallback | 21/150 |
| Maestro composite | 0.673 |
| BM25 baseline | 0.514 |
| **Lift** | **+15.9 points** |
| **Gate pass** | **True** (target ≥ +15) |

### Per-Type Breakdown

| Type | Score | Count | Assessment |
|------|-------|-------|------------|
| abstention | 1.000 | 30 | ✅ Perfect |
| commitment | 1.000 | 30 | ✅ Perfect |
| contradiction | 1.000 | 22 | ✅ Perfect |
| multilingual | 0.864 | 22 | ✅ Near-perfect |
| temporal | 0.000 | 23 | ❌ Real gap — needs timestamp matching fix |
| missing | 0.000 | 8 | Tunnel timeout (not a quality issue) |
| unknown | 0.000 | 15 | Process failures (timeout/OOM) |

### The Temporal Gap

Temporal questions ask "What's the latest update on DealN?" and expect
specific deal details. The LLM correctly abstains (says "I don't have
enough information") but the gold answer expects the deal name + status.
This is a signal-timestamp matching issue, not an LLM quality issue —
the temporal query parser isn't filtering signals by time correctly.

## Reproduction

### Prerequisites

1. A running Ollama instance with llama3:8b (or any LLM model)
2. The Maestro Personal repo cloned
3. Python 3.12+ with `pip install -e .` from `maestro-personal/`

### Steps

```bash
# 1. Set the tunnel URL (or use a local Ollama at http://127.0.0.1:11434)
export OLLAMA_HOST=https://your-tunnel.trycloudflare.com
export OLLAMA_MODEL=llama3:8b

# 2. Seed the Gold-150 signal corpus into a fresh DB
# (ask_one.py does this automatically on first run — it creates
# /tmp/gold_tc_batch.db with 180 signals + FTS5 index)

# 3. Run all 150 questions (one process per question)
cd maestro-personal
for i in $(seq 0 149); do
  python3 scripts/gold_scoring/ask_one.py $i /tmp/gold_tc_batch.db \
    evaluation/scoreboard/gold_150_llm_active_results.jsonl
done

# 4. Compute the final composite + gate pass
python3 scripts/gold_scoring/compute_results.py \
  evaluation/scoreboard/gold_150_llm_active_results.jsonl \
  evaluation/scoreboard/gold_150_llm_active_full_results.json
```

### Expected Output

```
GOLD-150 — MAESTRO (LLM-ACTIVE) vs BM25
Total: 150
BM25:  0.514
Maestro: 0.673
Lift:  +15.9 pts (target >= +15)
LLM active: 121/150
PASS — lift=+15.9 (target >= +15)
```

## Files

| File | Purpose |
|------|---------|
| `gold_150_llm_active_full_results.json` | Final results (150 entries, composite, per-type, gate_pass) |
| `gold_150_llm_active_results.jsonl` | Raw JSONL — one line per question (progress file) |
| `gold_150.py` | The 150-question corpus + gold labels |
| `bm25_baseline.py` | BM25 baseline scorer (composite = 0.514) |
| `scripts/gold_scoring/ask_one.py` | One-question-per-process scorer |
| `scripts/gold_scoring/run_batch.sh` | Bash wrapper for batch execution |

## Honest Limitations

1. **8 questions missing** — the Kaggle tunnel timed out before the
   last 8 questions completed. These are scored 0.0 but are NOT a
   quality issue — they're a tunnel availability issue.

2. **15 process failures** — some questions hit the 120s timeout
   (the LLM was slow on Kaggle's shared GPU). These are scored 0.0
   and labeled `type=unknown`.

3. **Temporal gap is real** — the 0.0 on temporal questions is a
   genuine product gap (timestamp matching), not an LLM issue. The
   LLM correctly abstains when it can't find time-filtered signals.

4. **Sandbox OOM** — the 3.9GB RAM sandbox forced the one-process-per-
   question approach. A machine with ≥8GB RAM could run all 150
   questions in a single process in ~70 minutes (150 × 28s).

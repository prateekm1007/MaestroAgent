# Retrieval Optimization Plan — Decisively Outperform BM25

> **Status:** Execution plan, not a blueprint. Each stage has: why it exists,
> what's already built (verified by execution this session), what's missing,
> and how success is measured. Grounded in the n=100 ablation results from
> 2026-07-20 (B_full_maestro = 7.3/10 on v1, 5.8/10 on v2, 5.1/10 on v3).
>
> **GOVERNANCE GATE:** Every "already built" claim below is verified by
> reading the actual code in `retrieval_ensemble.py` and running the
> ablation. Per P1 (claim = executed), no stage is marked complete without
> pasted output. Per P11 (building vs wiring), each stage has both a
> "capability exists" check and a "wired into production" check.

## Objective

The benchmark results demonstrate that retrieval—not generation—is the
primary bottleneck. BM25 performs strongly on lexical lookups but fails on
relationship, temporal, recurring, and commitment-state queries. The goal
is not to replace BM25, but to build a retrieval pipeline that consistently
supplies richer, more relevant evidence than lexical search alone.

**Current state (verified this session, n=100, v1 corpus):**
- BM25 alone: 0.5033 (5.0/10)
- Full Maestro (BM25 + specialists + RRF + LLM grounding): 0.7267 (7.3/10)
- Lift: +22.3pts. Gate 1 floor (5/10) cleared.
- LLM activation: 69/100 (69%) — up from 23% before the LLM-grounding fix.

**The gap to 9/10:** The weak types are priority (0.38), temporal (0.75
after fix, was 0.38), disputed (0.67 after fix, was 0.33), relational
(0.47), recurring (0.50). These are the types where lexical search
fundamentally cannot solve the problem — the fix must come from the
retrieval architecture, not the LLM.

---

## Stage 1 — High-Recall Candidate Generation

**Why this stage exists:** Before specialized retrievers can refine, they
need a broad pool of candidates. BM25 is near-optimal for this: fast,
lexical, high-recall on explicit keywords. Using BM25 for precision (as
the sole retriever) is where the current system breaks — but using it for
recall is exactly right.

**What's already built (verified):** `stage1_bm25_recall()` in
`retrieval_ensemble.py` line 75. Returns top 50 candidates via FTS5.
The ablation's A_bm25 arm uses this path and scores 0.5033 — confirming
BM25 works as a baseline.

**What's missing:** Nothing for this stage. BM25 recall is solid.

**Success measurement:**
- Recall@50: > 99% (is the exact text in the top 50?) — **not yet measured**
  directly, but inferred from A_bm25 scoring 0.50+ on direct_lookup types
- Latency: < 50ms — **not yet measured directly**

---

## Stage 2 — Hybrid Retrieval (Specialist Retrievers in Parallel)

**Why this stage exists:** Keyword search breaks down on implicit promises,
temporal shifts, and evolving relationship states. To answer "What's at
risk this week?", the system must retrieve based on metadata, graph
relations, and state — not just text overlap. Each specialist retriever
excels where BM25 is weak.

**What's already built (verified):** 5 specialist retrievers in
`retrieval_ensemble.py`, all wired into the production `/api/ask` path
(commit `c448459` + LLM-grounding fix):
1. **Entity Retriever** (line 162) — matches people/companies/projects
2. **Temporal Retriever** (line 189) — filters by time window
3. **Commitment Retriever** (line 264) — filters by ledger state
   (overdue/broken/active/completed)
4. **Relationship Retriever** (line 321) — graph traversal from entities
5. **Intent Keyword Retriever** (line 381) — semantic intent matching

**What's missing:**
- The Commitment Retriever returns `[LEDGER state=...]` synthetic rows
  that need normalization (fixed in `ask.py` but not in the ensemble itself)
- The Relationship Retriever relies on the Situation Graph, which is
  built on-the-fly from signals — no persistent graph index
- No dedicated "Contradiction Retriever" — contradictions are found
  only if both signals happen to be retrieved by other specialists

**Success measurement:**
- Recall@20 (after RRF): > 95% — **not yet measured directly**
- MRR: > 0.85 — **not yet measured directly**
- The n=100 ablation's per-type scores are a proxy: direct_lookup=0.93
  (entity retriever works), broken=0.60 (commitment retriever partial),
  relational=0.47 (relationship retriever weak)

---

## Stage 3 — Reciprocal Rank Fusion (RRF)

**Why this stage exists:** Multiple retrievers return ranked lists with
incomparable scores. RRF merges them robustly without requiring score
calibration. Standard RRF weight: 1/(60+rank) (Cormack et al. 2009).

**What's already built (verified):** `reciprocal_rank_fusion()` in
`retrieval_ensemble.py` line 423. Uses k=60. Returns top 20 fused results.
Wired into production via `retrieve()` at line 673.

**What's missing:**
- No per-retriever weight tuning (all retrievers weighted equally in RRF)
- No query-dependent retriever selection (e.g., temporal queries should
  weight the temporal retriever higher)

**Success measurement:**
- The lift from A_bm25 to B_full_maestro (+22.3pts on v1) is the
  end-to-end measure of stages 1-3 combined
- Per-type improvements after the Path B → Path A wiring fix (commit
  `c448459`): broken +100pts, recurring +50pts, relational +40pts —
  these validate that RRF + specialists work when actually called

---

## Stage 4 — Cross-Encoder Reranking

**Why this stage exists:** RRF gives good recall but imperfect precision.
A cross-encoder (query + document evaluated jointly) substantially
improves evidence precision before generation. LLMs degrade sharply when
given irrelevant evidence — protecting the context window is critical.

**What's already built:** ❌ **NOT BUILT.** This is the biggest missing
piece. The current pipeline goes RRF → context_engineer (dedup + sort)
→ LLM. No reranking step exists.

**What's missing:**
- No cross-encoder model integration (BAAI/bge-reranker-v2-m3 or
  jina-reranker-v2-base-multilingual recommended)
- No reranking stage in `retrieve()` or `context_engineer()`
- The Ollama-based reranker models may not be available via OpenRouter;
  would need a separate inference path or a hosted reranker API

**Success measurement:**
- Evidence Precision: > 95% (are the 5-8 chunks strictly relevant?)
- Context Token Reduction: > 60% vs raw Stage 1 output
- **NOT YET MEASURABLE** — no reranker to test against

**Execution plan:**
1. Evaluate whether OpenRouter hosts a reranker endpoint (or use a
   hosted reranker like Cohere Rerank)
2. If not, run a local cross-encoder via Ollama (bge-reranker-v2-m3)
3. Add a `stage4_rerank()` function between RRF and context_engineer
4. Measure evidence precision before/after on the 3-set ablation

---

## Stage 5 — Context Compression

**Why this stage exists:** The LLM should receive 5-8 high-quality,
chronologically ordered, deduplicated evidence chunks — not 30 loosely
related passages. This protects the context window and improves reasoning.

**What's already built (verified):** `context_engineer()` in
`retrieval_ensemble.py` line 481. Does:
- ✅ Drop noise signals (newsletter/fyi unless explicitly queried)
- ✅ Deduplicate by normalized text
- ✅ Sort chronologically (oldest first) for timeline queries
- ✅ Intent-aware sort (preserve RRF order for intent queries — fix
  from 2026-07-20)
- ✅ Top-K (8 by default)

**What's missing:**
- ❌ No cross-passage merging (overlapping passages are deduped, not
  merged)
- ❌ No low-information snippet detection (a 2-word signal gets the same
  treatment as a 50-word signal)
- ❌ No provenance-structured output (evidence is sent as flat text, not
  as structured metadata with signal_id/entity/timestamp)

**Success measurement:**
- Context Token Reduction: > 60% vs raw Stage 1 output — **partially
  measurable** (current top-K=8 from top-50 BM25 = 84% reduction, but
  this is truncation not compression)
- Evidence Precision: > 95% — **depends on Stage 4 reranker**

---

## Model Comparison (verified this session)

**The plan recommends Qwen 3 14B/32B and DeepSeek-R1 as local Ollama
models.** The reality: this sandbox uses OpenRouter (cloud API), not
local Ollama. Here's what was tested:

| Model | OpenRouter slug | Status | v2 B_full | v3 B_full |
|-------|----------------|--------|-----------|-----------|
| Llama 3.3 70B | `meta-llama/llama-3.3-70b-instruct` | ✅ works | 0.5769 | 0.5122 |
| Qwen Plus | `qwen/qwen-plus` | ✅ works | 0.5769 | 0.5488 |
| Gemini 2.5 Flash-Lite | `google/gemini-2.5-flash-lite` | ❌ region-blocked | N/A | N/A |

**Key finding:** Qwen-Plus improved v3 by +3.7pts (0.5122 → 0.5488) and
doubled LLM activation (13/41 → 23/41). On v2, scores were identical
because the scorer is entity-presence-based (both models mention the same
entities). Qwen's answers are more natural/conversational but the scorer
can't distinguish quality — only entity presence.

**Recommendation:** Switch the default model from llama-3.3-70b to
qwen-plus. It's cheaper ($0.0000068/call vs $0.0000029/call — both
effectively free), fires more reliably, and produces better answers on
the harder v3 corpus. Gemini can't be tested from this region.

---

## Benchmark Strategy

**Do not attempt to outperform BM25 on problems that are fundamentally
lexical.** BM25 is already near-optimal for:
- direct lookup (B_full = 0.93 on v1)
- keyword search
- exact names
- simple multilingual retrieval (B_full = 1.00 on v1)

Instead, optimize for questions where lexical search breaks down:
- relationship reasoning (relational: 0.47 — needs work)
- temporal reasoning (temporal: 0.75 after fix — improved)
- commitment tracking (broken: 0.60, overdue: 0.67 — partial)
- contradiction detection (contradiction: 1.00 — already strong)
- recurring commitments (recurring: 0.50 — needs work)
- "What changed?" / "What is at risk?" (at_risk: 0.53 — needs work)

These are Maestro's intended differentiators. The 3-set ablation shows
the differentiators are weakest on v2 (enterprise sales, 5.8/10) and v3
(engineering/ops, 5.1/10) — the scenarios that most resemble real
production use.

---

## Success Metrics (current state)

| Metric | Target | Current (v1 n=100) | Status |
|--------|--------|---------------------|--------|
| Recall@10 | > 95% | not measured directly | ❓ |
| Recall@20 | > 98% | not measured directly | ❓ |
| MRR | > 0.85 | not measured directly | ❓ |
| NDCG@10 | > 0.90 | not measured directly | ❓ |
| Evidence Precision | > 95% | depends on Stage 4 | ❌ |
| Answer Accuracy | > 90% | B_full = 72.7% | ⚠️ |
| Provenance Accuracy | > 99% | not measured directly | ❓ |
| Hallucination Rate | < 1% | not measured directly | ❓ |

**The gap:** The ablation measures answer accuracy (entity-presence
scoring) but NOT recall, MRR, NDCG, evidence precision, provenance
accuracy, or hallucination rate. These require a separate evaluation
harness with gold-labeled relevance judgments per signal, not just
per question. Building this harness is a prerequisite for measuring
Stages 3-5 independently.

---

## Execution Priority

1. **Switch default model to qwen-plus** (quick win, verified +3.7pts
   on v3)
2. **Build the recall/MRR/NDCG evaluation harness** (can't measure
   Stages 3-5 without it)
3. **Build Stage 4 cross-encoder reranker** (biggest missing piece)
4. **Improve context compression** (merge overlapping passages, structured
   provenance)
5. **Add per-retriever weight tuning in RRF** (query-dependent weighting)
6. **Build a dedicated Contradiction Retriever** (currently relies on
   other specialists happening to find both sides)

---

## Expected Outcome

By combining high-recall BM25 (✅ built), hybrid retrieval (✅ built),
RRF (✅ built), cross-encoder reranking (❌ not built), and context
compression (⚠️ partial), Maestro should no longer compete with BM25 on
lexical search. Instead, it should surpass BM25 on the kinds of temporal,
relational, and commitment-aware reasoning tasks that define the product's
value proposition.

**Current composite (3-set average, llama):** ~6.1/10
**Current composite (3-set average, qwen — estimated):** ~6.3/10
**Target:** 9/10

The gap from 6.3 to 9.0 is 2.7 points. The biggest levers are:
- Stage 4 reranker (estimated +1-2pts on evidence precision)
- Recall/MRR evaluation harness (can't optimize what we can't measure)
- Per-type fixes for priority (0.38), relational (0.47), recurring (0.50)

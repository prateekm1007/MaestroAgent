# MAESTRO RETRIEVAL EXECUTION PLAN: Decisively Outperforming BM25

> **Status:** Tactical execution plan for the retrieval sub-system. Committed
> 2026-07-20 by the new coder session, sourced from the user's directive.
> Supports Phase 1 + Phase 2 of `ROADMAP_TO_WORLD_CLASS.md`. The 4 stages
> below are the concrete engineering work that turns "Agentic Ask Engine"
> (roadmap Phase 2.1) and "Hybrid BM25+embedding retrieval" (forensic audit
> P2 item #10) from prose into shipped code.
>
> **GOVERNANCE GATE:** Each stage has a "Success Measurement" gate. Per P1
> (a claim is not true until it has been executed), no stage is marked
> complete without pasted benchmark output from THIS session hitting the
> stated Recall@k / MRR / precision / latency / accuracy numbers.

This is a rewritten version of the architectural blueprint — a **tactical execution plan**.

It shifts the tone from "what to build" to "how to execute, why it matters, and how to prove it works."

***

## The Objective
The current benchmark results show that retrieval—not generation—is Maestro's primary bottleneck. BM25 performs strongly on simple lexical lookups (e.g., "Find the email from Maria") but fails entirely on Maestro's core value propositions: relationship tracking, temporal shifts, and commitment lifecycle states.

This execution plan outlines the phased deployment of a hybrid retrieval pipeline. **The goal is not to deprecate BM25, but to relegate it to a baseline recall engine**, allowing specialized vector and graph retrievers to supply the contextual evidence required for world-class AI reasoning.

---

## Stage 1: High-Recall Candidate Generation (The Safety Net)
**The Why:** Before we can reason about complex relationships, we must guarantee that the raw source material is caught in the initial net. BM25 is highly efficient and near-perfect for exact entity lookups and keyword matching.
**The Execution:**
* Do not attempt to use BM25 for precision.
* Configure BM25 to cast a wide net, extracting the top 30–50 candidate passages.
* Treat this stage strictly as a coarse filter to ensure zero data loss on explicit keyword queries.

**Success Measurement (Stage 1 Gate):**
* **Recall@50:** > 99% (Did the exact text exist anywhere in the top 50 chunks?)
* **Latency:** < 50ms per query.

---

## Stage 2: Parallel Hybrid Retrieval (The Differentiator)
**The Why:** Keyword search breaks down on implicit promises, temporal shifts, and evolving relationship states. To answer questions like *"What's at risk this week?"*, the system must retrieve based on metadata, graph relations, and state—not just text overlap.
**The Execution:**
Run multiple specialized retrievers concurrently alongside BM25, merging their outputs via **Reciprocal Rank Fusion (RRF)** to prevent over-reliance on any single method.
1. **Entity Retriever:** Indexes people, companies, and projects. (Solves: *"What did I promise Maria?"* without needing the word "promise" in the text).
2. **Temporal Retriever:** Indexes deadlines, recency, and recurring events. (Solves: *"What changed since Tuesday?"*).
3. **Graph Retriever:** Traverses the Maestro Situation Graph (Entity → Emails → Meetings → Commitments). (Solves multi-hop relational questions).
4. **Commitment Retriever:** Indexes by strict commitment state, owner, and confidence. (Solves: *"What is overdue or blocked?"*).

**Success Measurement (Stage 2 Gate):**
* **Recall@20:** > 95% (Are the correct contextual passages in the unified top 20?)
* **MRR (Mean Reciprocal Rank):** > 0.85 (Are the best passages floating to the top of the RRF pile?)

---

## Stage 3: Cross-Encoder Reranking & Compression (The Noise Filter)
**The Why:** LLMs degrade in reasoning quality and hallucinate when flooded with 30–50 loosely related, overlapping passages. We must protect the context window.
**The Execution:**
* Pass the top 20 candidates through a dedicated Cross-Encoder Reranker (e.g., `BAAI/bge-reranker-v2-m3` or `jina-reranker-v2-base-multilingual`). These models evaluate query-document relevance jointly, massively increasing precision.
* **Compress:** Deduplicate, merge overlapping passages, and order them chronologically.
* **Output:** Supply the LLM with exactly 5–8 high-signal, chronologically ordered evidence chunks enriched with strict provenance metadata.

**Success Measurement (Stage 3 Gate):**
* **Evidence Precision:** > 95% (Are the 5-8 chunks sent to the LLM strictly relevant to the query?)
* **Context Token Reduction:** > 60% reduction in tokens sent to the LLM compared to raw Stage 1 output.

---

## Stage 4: Reasoning Engine Upgrade (The Brain)
**The Why:** Passing perfect evidence to a weak model yields poor synthesis. Benchmarks indicate that Llama 3 (8B) lacks the logical rigor required for conditional reasoning, multi-hop inference, and contradiction detection.
**The Execution:**
Migrate the local inference engine to models proven to excel at structured logic and synthesis.
* **Primary Target:** `Qwen 3 14B` (Exceptional instruction following, multilingual, highly efficient).
* **High-Compute Target:** `Qwen 3 32B` (For complex planning and nuanced conditional workflows).
* **Judgment/Validation Layer:** `DeepSeek-R1 Distill Qwen 14B` (Best-in-class for contradiction detection and logical verification).
* **Lightweight Alternatives:** `Gemma 3 12B` or `Mistral Small 3.2`.

**Success Measurement (Stage 4 Gate):**
* **Answer Accuracy:** > 90%
* **Provenance Accuracy:** > 99% (Does every claim trace back to an exact chunk ID?)
* **Hallucination Rate:** < 1% (Zero manufactured commitments).

---

## Executive Benchmark Strategy
To prove this pipeline works, **stop benchmarking Maestro against simple lookups.** BM25 is already near-optimal for finding exact names or direct keywords.

Future testing must exclusively evaluate Maestro on the problems lexical search fundamentally cannot solve:
1. **Contradiction Detection** (e.g., Signal A says "Will do X", Signal B says "X is done").
2. **Temporal Reasoning** (e.g., "What changed specifically regarding the Titan project since yesterday?").
3. **Commitment Lifecycle** (e.g., "What promises have I neglected the longest?").

**Expected ROI:** By executing this pipeline, Maestro will decisively abandon the limitations of semantic search bars and transition into a state-aware, relational intelligence engine.

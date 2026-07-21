# MAESTRO PERSONAL: ROADMAP TO WORLD-CLASS (9/10 ACROSS ALL BENCHMARKS)

> **Status:** Strategic north star. Committed 2026-07-20 by the new coder
> session, sourced from the user's directive. This document is the multi-month
> product direction; the 4-stage `RETRIEVAL_EXECUTION_PLAN.md` is the tactical
> retrieval sub-plan that supports Phase 1+2 of this roadmap.
>
> **GOVERNANCE GATE:** This roadmap does NOT override the forensic audit's P0
> items (mobile login bypass, test isolation). Those must close first — see
> STATE.md for the unified priority order. Building new product on top of
> unresolved security debt violates P6 (fail closed, not silent).
>
> **⚠️ CORRECTIONS (2026-07-20, second coder session):** A senior auditor
> reviewed this roadmap against the repo's scoring discipline and flagged
> three issues. They are documented inline below at the affected sections.
> The roadmap is NOT discarded — its good engineering ideas (intent
> classification, commitment lifecycle, agentic Ask with tool-calling) are
> retained. But it must NOT be executed as-written because:
> 1. The benchmark score table (below) has target numbers with NO gate, NO
>    command, NO falsifiable check. Per direction #1: "Do not report a
>    score, percentage, or 'impact' without the command that produced it."
>    Every target in that table is an assertion, not an earned score.
> 2. "AI Quality" as used here is a FOURTH definition. The repo already has
>    two: Gate 1 (BM25 ablation, currently 2/10) and the Ask-correctness
>    one from a parallel auditor thread. `SCORING_SYSTEM_v2.md` was
>    supposed to be the Rosetta Stone but **does not exist in the repo**
>    (verified this session — `find . -iname 'scoring_system*'` returns
>    nothing; `verify_benchmark.sh` references "SCORING_SYSTEM.md" in a
>    comment but that file also doesn't exist). This is a governance gap
>    to flag to Prateek.
> 3. The Phase 1.1 "Hardened Ambient Intelligence" diagnosis is factually
>    wrong. `ambient_notifications.py` ALREADY has DND/in-call suppression
>    (verified by code read this session). The actual open question is a
>    PRODUCT DECISION: should "commitment overdue" be CRITICAL (breaks
>    through DND, current behavior) or HIGH (suppressed in DND)? That's
>    one line of severity reclassification pending Prateek's call, not a
>    phase of engineering.

This roadmap outlines the precise engineering and product phases required to elevate Maestro Personal from a "Promising Prototype" to a genuinely **World-Class (9/10)** category leader across all 16 audit benchmarks.

It directly addresses the critical flaws identified in the external audit: the rigid Ask engine, the naive commitment extraction (susceptible to jokes), and the noisy Ambient Intelligence logic.

---

## Phase 1: Foundation & "Stop the Bleeding" (Months 1–2)
**Goal:** Fix trust-breaking behaviors, silence the noise, and implement true intent parsing.

### 1. Hardened Ambient Intelligence (The "Zero Noise" Policy)

> **⚠️ CORRECTION (2026-07-20):** This item is misdiagnosed. The DND/in-call
> suppression state-machine the roadmap proposes to build ALREADY EXISTS in
> `ambient_notifications.py` (verified by code read this session — see
> `RESPONSE_TO_STALE_REVIEW.md` and three other places that document the
> "DND active: only CRITICAL shows" rule). The roadmap's Phase 1.1 is
> proposing to build something that's already built. The ACTUAL open
> question is a product decision, not engineering: should "commitment
> overdue" be classified CRITICAL (breaks through DND — current behavior)
> or HIGH (suppressed in DND, shown in focus mode)? That's one line of
> severity reclassification pending a Prateek decision. Do NOT execute
> this item as a multi-month engineering phase. Take it to Prateek as a
> product question per the auditor's direction #4.

* **The Fix:** Completely decouple notification generation from notification *delivery*. Implement a strict state-machine that respects `is_in_call` and `is_dnd_active`. If DND is active, high-priority notifications must be queued into a "Digest" delivered only when the user's state changes to available.
* **Impact:** Ambient Intelligence reaches **9/10**. UX reaches **9/10**.

### 2. Intent-Aware Commitment Extraction
* **The Fix:** Move away from naive keyword matching (e.g., triggering on the word "promise"). Implement a secondary LLM classifier step to evaluate the *intent* and *context* of a statement. It must reliably discard sarcasm, jokes (e.g., "Why did the chicken cross the road?"), hyperbole, and hypotheticals.
* **Impact:** AI Quality jumps from 3 to **6/10**. Trust jumps from 6 to **8/10**.

### 3. State Lifecycle Tracking for Commitments
* **The Fix:** Commitments cannot just be "Active" or "Stale." Implement a full lifecycle graph: `Candidate -> Active -> Completed -> Canceled -> Superseded`. Allow users to easily update these states via the UI or natural language ("I already sent the email to Maria").
* **Impact:** Commitment Intelligence jumps from 5 to **8/10**.

---

## Phase 2: Synthesis & Advanced Intelligence (Months 3–4)
**Goal:** Transform the Ask engine from a "semantic search bar" into a true reasoning engine capable of multi-hop logic and state aggregation.

### 1. Agentic "Ask" Engine
* **The Fix:** The Ask endpoint must stop performing flat vector searches. Implement a multi-agent orchestration layer. When a user asks "What commitments are completed?", the LLM must map this to an internal tool call (`get_commitments(state="completed")`), synthesize the JSON response, and return a conversational answer.
* **Impact:** Ask reaches **9/10**. AI Quality reaches **8/10**.

### 2. Contradiction & Resolution Memory
* **The Fix:** Expand the "Prepare" logic globally. When a new signal contradicts an old commitment (e.g., *Signal A: "I will do X"*, *Signal B: "X is done"*), the system must automatically propose a resolution or prompt the user: "Did this complete your commitment?".
* **Impact:** Memory reaches **9/10**. Meeting Preparation reaches **9/10**.

### 3. Nuanced Edge-Case Handling & Conversational Fallbacks
* **The Fix:** Eliminate canned error responses ("I don't have enough information..."). If the system doesn't know what was promised to Elon Musk, it should intelligently contextualize: "You have no recorded commitments with Elon Musk. Would you like me to check your broader signal history?"
* **Impact:** Consumer Readiness reaches **8/10**.

---

## Phase 3: Enterprise Polish & World-Class Standards (Months 5–6)
**Goal:** Bulletproof the system for institutional investors and Fortune 100 enterprise adoption.

### 1. Enterprise-Grade Security & Prompt Defense
* **The Fix:** Implement robust defenses against adversarial prompt injection via the Ask engine. Ensure strict multi-tenant data siloing, end-to-end encryption for all stored signals, and an export/delete mechanism to comply with GDPR/CCPA.
* **Impact:** Security reaches **9/10**. Enterprise Readiness jumps from 3 to **9/10**.

### 2. Micro-Latency & Performance Budgets
* **The Fix:** Institute a strict <100ms latency budget for all UI interactions (dashboard loading, navigating) and a <1.5s latency budget for LLM-powered Ask responses (utilizing streaming SSE and semantic caching for frequent queries).
* **Impact:** Performance reaches **9/10**. Reliability reaches **9/10**.

### 3. Ecosystem Connectors & Auto-Healing
* **The Fix:** Robust integrations with Slack, Gmail, and Calendar that can gracefully handle partial syncs, broken credentials, and API rate limits without silently failing. Add an "Integration Health" UI to transparently explain connection statuses to the user.
* **Impact:** Product-Market Fit reaches **9/10**. Consumer Readiness reaches **9/10**.

---

## Benchmark Score Tracking

| Benchmark | Audit Score | Phase 1 Target | Phase 2 Target | Phase 3 Target | Core Action Needed |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Product Vision** | 9 | 9 | 9 | 9 | Maintain strict opinionated design. |
| **Evidence** | 9 | 9 | 9 | 9 | Maintain strict provenance tagging. |
| **Meeting Prep** | 8 | 8 | 9 | 9 | Add global contradiction resolution. |
| **Performance** | 8 | 8 | 8 | 9 | Sub-1.5s Ask streaming, edge caching. |
| **UX** | 8 | 9 | 9 | 9 | UI polish for state management. |
| **World-Class Potential** | 8 | 8 | 9 | 9 | Agentic Ask and Zero-Noise. |
| **Differentiation** | 8 | 8 | 9 | 9 | Lifecycle graphs separate it from basic LLMs. |
| **Reliability** | 7 | 8 | 8 | 9 | Graceful connector error handling. |
| **Memory** | 7 | 8 | 9 | 9 | Relational memory graph. |
| **Security** | 7 | 7 | 8 | 9 | Prompt injection defense & SOC2 prep. |
| **Trust** | 6 | 8 | 9 | 9 | Eradicate false positive commitments (jokes). |
| **Product-Market Fit** | 6 | 7 | 8 | 9 | Flawless third-party integrations. |
| **Commitment Intel.** | 5 | 8 | 9 | 9 | Intent-classifier & state lifecycle. |
| **Consumer Readiness** | 4 | 6 | 8 | 9 | Graceful conversational fallbacks. |
| **Enterprise Readiness** | 3 | 4 | 6 | 9 | GDPR/CCPA, RBAC, Data siloing. |
| **AI Quality** | 3 | 6 | 8 | 9 | LLM orchestration layer for aggregations. |
| **Ambient Intel.** | 2 | 9 | 9 | 9 | Strict Context/DND rule enforcement. |
| **Ask Engine** | 3 | 6 | 9 | 9 | Multi-hop reasoning and tool calling. |

---

## Conclusion
To reach **9/10**, Maestro must stop trying to be a database that *looks* like an AI, and become an AI that *reasons over* a database.

By upgrading the extraction pipeline to understand intent, completely overhauling the Ask engine to support tool-calling and aggregations, and enforcing a strict "zero noise" policy for ambient notifications, Maestro will transition from a brittle prototype to an indispensable, world-class professional workflow tool.

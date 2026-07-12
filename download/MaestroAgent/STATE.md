# Maestro State Log

> ⛔ **GOVERNANCE GATE: Read [GOVERNANCE.md](./GOVERNANCE.md) and [ENTROPY_RECOVERY.md](./GOVERNANCE.md) BEFORE doing any work or trusting any claim in this file.**

## Last Updated
2026-07-12 — LLM-active test run with Kaggle P100 Ollama tunnel. Both baseline failures CLOSED.

## Current Status: ~5.3/10 → audit-fix pass complete + LLM proven. Controlled single-user beta. Not multi-user safe.

> **HEAD:** `11342e4` on `main` (was `daeb88e`, was `2133cb5`, was `f32a751` at audit time).
>
> **Test counts (executed with LLM active, P4 reconciliation):**
> - 824 tests collected (was 807 — 17 new tests added in 2133cb5+daeb88e)
> - Security + lifecycle + LLM subset (206 tests): **206/206 PASSED** in 74s
> - LLM-specific tests (test_llm_via_ollama + test_llm_wiring + test_llm_latency_hypothesis): **35 passed, 3 skipped** in 31s
> - Both baseline failures now CLOSED:
>   1. test_graph_completion_rate_accuracy → FIXED in 2133cb5 (F3 graph wiring)
>   2. test_llm_complete_works_when_api_responds → FIXED in 11342e4 (test isolation)
> - End-to-end Ask with LLM: **PASSED** — llm_active=True, provider=ollama,
>   confidence=0.3 (honestly capped by single-evidence), answer correctly
>   mentions Maria + Friday + pricing/proposal, 27.6s latency
>
> **LLM runtime (proven this session):**
> - Provider: Ollama (llama3:8b, Q4_0, 4.66GB)
> - Hosted on: Kaggle P100 GPU via Cloudflare tunnel
> - Eval speed: 0.06s per token
> - llm_active=True verified in /api/ask response
> - probe_provider() returns verified=True, latency_ms=744
>
> **Audit findings addressed (3 commits: 2133cb5, daeb88e, 11342e4):**
> - F1 (ask ranking noise): FIXED ✓ — select_top_evidence now filters by min_score
> - F2 (label honesty): FIXED ✓ — llm_active=true with LLM; confidence caps in rules mode
> - F3 (graph completion_rate): FIXED ✓ — wired resolve_completion_signal into ingest
> - F4 (staleness consistency): FIXED ✓ — aligned threshold; closure-only reset
> - F6 (silence false CRITICAL): FIXED ✓ — removed bare 'fine' from legal keywords
> - F8/S1 (auth fail-closed): FIXED ✓ — dev mode no longer mints arbitrary emails
> - F9 (Prepare corrections): FIXED ✓ — _filter_corrected_signals applied
> - F10 (STATE.md stale): FIXED ✓ — reconciled with HEAD
> - HIGH-1 (XSS in entity): FIXED ✓ — 3-layer sanitization applied to entity
> - MEDIUM-2 (length cap): FIXED ✓ — Field(max_length=200/10000)
> - MEDIUM-3 (docs exposure): FIXED ✓ — /docs disabled in production
> - P25 (confidence cap): FIXED ✓ — three caps: rules 0.6, <3 evidence 0.5, noise 0.3
> - Test isolation (Phase 0.3): FIXED ✓ — both baseline failures closed
>
> **Audit findings still OPEN (require external deps or multi-week work):**
> - F5 (live learning A/B): PARTIALLY ADDRESSED — dismissal recorded; live divergence weak
> - F7 (copilot WS fusion): OPEN — REST copilot works; WS fused whispers not demonstrated
> - F8/S2 (OIDC): OPEN — shared-secret with fail-closed default; real IdP needed for SaaS
> - F10 (api.py god-module): OPEN — 5,289 lines; splitting is Phase 8 P2 work
> - Phase 1 (memory gold set + BM25 comparison): NOT STARTED — needs 50-question gold corpus
> - Phase 2 (commitment lifecycle gold set): NOT STARTED — needs 50-item lifecycle corpus
> - Phase 3 (100-moment silence benchmark): NOT STARTED — needs production whisper path scoring
> - Phase 4 (copilot 10-meeting eval): NOT STARTED — needs WS + LLM + meeting scripts
> - Phase 5 (ablation table): NOT STARTED — needs all above first
>
> **What's verified by execution this session:**
> - 206/206 security + lifecycle + LLM tests PASSED with LLM active
> - 35/35 LLM-specific tests PASSED (3 skipped — provider-specific)
> - End-to-end Ask: llm_active=True, provider=ollama, confidence=0.3 (honestly capped)
> - Both baseline test failures CLOSED
> - XSS, auth, staleness, silence, Prepare — all regression tests green
>
> **What's NOT verified:**
> - Full 824-test suite (ran 206-test subset + 35 LLM tests; full suite needs >5min)
> - Multi-user calibration isolation in production
> - OIDC/real auth (shared-secret only, fail-closed default)
> - Phase 1-5 gold-set evaluations (not yet built)
>
> **CTO recommendation (updated):**
> - Multi-user SaaS: DO NOT SHIP
> - Single-user local dogfood: SHIP TO CONTROLLED BETA (LLM now proven)
> - "9/10 / world-class": NOT JUSTIFIED — needs Phase 1-5 gold-set proof per roadmap

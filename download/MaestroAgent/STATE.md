# Maestro State Log

> ⛔ **GOVERNANCE GATE: Read [GOVERNANCE.md](./GOVERNANCE.md) and [ENTROPY_RECOVERY.md](./GOVERNANCE.md) BEFORE doing any work or trusting any claim in this file.**

## Last Updated
2026-07-12 — Independent audit fixes at `2133cb5` (P0/P1 findings from MaestroPersonal_Independent_Audit_Report.md).

## Current Status: ~5.3/10 → audit-fix pass complete. Controlled single-user beta. Not multi-user safe.

> **HEAD:** `2133cb5` on `main` (was `f32a751` at audit time, was `eb80a91` in prior STATE.md).
>
> **Test counts (executed this session, P4 reconciliation):**
> - 807 tests collected (was claimed as "622" in prior STATE.md — stale, P4 violation)
> - 785 passed, 2 failed, 20 skipped at baseline `f32a751`
> - After fixes at `2133cb5`: 124/124 security + lifecycle subset PASSED
> - The 2 baseline failures (test_graph_completion_rate_accuracy,
>   test_llm_complete_works_when_api_responds) — first is now FIXED,
>   second requires an LLM provider not available in this env.
>
> **Audit findings addressed this session (commit 2133cb5):**
> - F3 (graph completion_rate stays None): FIXED ✓ — wired
>   resolve_completion_signal into create_signal ingest path (P11 fix)
> - F4 (days_stale inconsistency + closure reset): FIXED ✓ — aligned
>   threshold to 2 in both endpoints; only closure signals reset staleness
> - F6 ('velocity is fine' → CRITICAL legal): FIXED ✓ — removed bare
>   'fine' from legal keywords; replaced with specific phrases
> - F8/S1 (dev mode mints arbitrary emails): FIXED ✓ — fail-closed
>   default; opt-in via MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL=1
> - F1 (ask ranking noise dominance): FIXED ✓ — select_top_evidence
>   now actually filters by min_score (was P11 wiring gap)
> - F2 + P25 (label honesty + confidence cap): FIXED ✓ — three caps:
>   rules-only max 0.6, <3 evidence max 0.5, noise evidence max 0.3
> - F9 (Prepare lists dismissed signals): FIXED ✓ — apply
>   _filter_corrected_signals to entity_signals in /api/prepare
> - HIGH-1 (XSS in entity field): FIXED ✓ — apply 3-layer sanitization
>   stack to entity (was only applied to text)
> - MEDIUM-2 (no input length cap): FIXED ✓ — Field(max_length=200)
>   on entity, Field(max_length=10_000) on text
> - MEDIUM-3 (docs exposed in prod): FIXED ✓ — /docs, /openapi.json,
>   /redoc disabled when _is_production()
>
> **Audit findings still OPEN:**
> - F2 (no LLM in env): OPEN — needs Ollama or cloud provider. The
>   product now caps confidence at 0.6 in rules-only mode (F2 fix above)
>   so it no longer claims high confidence without an LLM, but the
>   "intelligence" path itself is still rule-based until a provider is wired.
> - F5 (live learning changes whisper delivery): PARTIALLY ADDRESSED —
>   dismissal behaviors are recorded; whisper ranking consumption of
>   per-entity dismissal rates is still weak. Unit test
>   test_alice_suppressed_bob_not_suppressed passes; live A/B divergence
>   is partial.
> - F7 (copilot WS intelligence): OPEN — REST copilot returns state
>   transitions; WS auth works; fused historical whispers not demonstrated.
> - F8/S2 (no OIDC): OPEN — shared-secret auth with fail-closed default
>   is the current state. Real IdP required for multi-user SaaS.
> - F10 (api.py god-module): OPEN — 5,289 lines. Splitting is P2 work.
>
> **What's verified by execution this session:**
> - 124/124 security + lifecycle tests PASSED (cross_user_isolation,
>   p0_audit_fixes, audit_f4_f10_remaining, directive5_security_trust,
>   22_new_tests, ask_ranker_integration, + 4 new test files:
>   test_f8_auth_fail_closed, test_high1_xss_and_length_cap,
>   test_f6_silence_false_critical, test_f4_staleness_consistency)
> - test_graph_completion_rate_accuracy: PASSED (was FAILING at baseline)
> - XSS in entity field: verified blocked (6/6 test cases)
> - Dev-mode arbitrary email minting: verified blocked (2/2 test cases)
> - 'velocity is fine' no longer triggers CRITICAL (4/4 test cases)
> - Stale-commitment consistency between /api/commitments and /the-one
>   verified (3/3 test cases)
>
> **What's NOT verified:**
> - Real LLM comparison (no working API key in environment)
> - Multi-user calibration isolation in production (code fix applied, not runtime-tested)
> - OIDC/real auth (shared-secret only, fail-closed default)
> - Full 807-test suite (subset of 124 security/lifecycle tests run this session)
>
> **CTO recommendation (unchanged from audit):**
> - Multi-user SaaS: DO NOT SHIP
> - Single-user local dogfood: SHIP TO CONTROLLED BETA
> - "9/10 / world-class": NOT JUSTIFIED — needs LLM, live learning proof, copilot WS proof

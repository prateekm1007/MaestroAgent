# Road to 9/10 — Status Log

**Last updated:** 2026-07-12 (after commit 6d1148d)
**Governance gate:** GOVERNANCE.md + ENTROPY_RECOVERY.md read from disk this session.

## Environment baseline

| Item | Value |
|------|-------|
| Commit SHA | `6d1148d` on `main` |
| Branch | `main` |
| Python | 3.12.13 |
| Product path | `download/MaestroAgent/maestro-personal/` |
| Core dependency | `download/MaestroAgent/backend/` (installed editable) |
| API port | 8766 |
| LLM provider | Ollama (llama3:8b on Kaggle P100 GPU via Cloudflare tunnel) |
| LLM verified | `true` (probe_provider returns verified=True, latency_ms=744) |
| Privacy mode | `local_rules` (with LLM: `local_ollama`) |

## Test suite status

### Maestro Personal

```
824 tests collected
Security + lifecycle + LLM subset (206 tests): 206/206 PASSED in 74s
Both baseline failures CLOSED:
  1. test_graph_completion_rate_accuracy → FIXED in 2133cb5 (F3 graph wiring)
  2. test_llm_complete_works_when_api_responds → FIXED in 11342e4 (test isolation)
```

### Backend

Not re-run this session. Known to have legacy failures per prior audits. Phase 1.2 of the Roadmap to 9/10 requires fixing or explicitly retiring these.

## Scorecard (current vs target)

| Category | Audit Score | Target | Gap | Status |
|----------|-------------|--------|-----|--------|
| Core product usefulness | 4.5 | 9.0 | -4.5 | Phase 2-3 work pending |
| Memory & retrieval | 4.0 | 9.0 | -5.0 | BM25 baseline=0.514; Maestro scoring pending |
| Real-time copilot | 2.5 | 9.0 | -6.5 | Phase 4 work pending |
| Learning & personalization | 3.5 | 9.0 | -5.5 | F5 wiring fixed; causal A/B pending |
| Reasoning quality | 2.5 | 9.0 | -6.5 | LLM now active; gold-set scoring pending |
| Trusted silence | 4.0 | 9.0 | -5.0 | F6 fixed; 100-moment benchmark pending |
| Reliability & resilience | 5.5 | 9.0 | -3.5 | Phase 7 work pending |
| Security & privacy | 5.5 | 9.0 | -3.5 | F8/HIGH-1/MEDIUM fixed; OIDC pending |
| Performance & scalability | 7.0 | 9.0 | -2.0 | 10K SLO tests pass; 100K pending |
| Product coherence | 5.0 | 9.0 | -4.0 | F4/F9 fixed; cross-surface test pending |
| Observability & auditability | 5.5 | 9.0 | -3.5 | Traces exist; whisper-decisions pending |
| Engineering quality | 4.5 | 9.0 | -4.5 | api.py split plan written; execution pending |
| **Weighted overall** | **4.4** | **≥9.0** | | **PROMISING BUT UNPROVEN** |

## Findings addressed (commits on origin/main)

| Finding | Severity | Commit | Status |
|---------|----------|--------|--------|
| F1 (ask ranking noise) | CRITICAL | 2133cb5 | FIXED ✓ |
| F2 (label honesty) | HIGH | 2133cb5 + 7dab549 | FIXED ✓ (LLM now active) |
| F3 (graph completion_rate) | HIGH | 2133cb5 | FIXED ✓ |
| F4 (staleness consistency) | HIGH | 2133cb5 + 6d1148d | FIXED ✓ |
| F6 (silence false CRITICAL) | HIGH | 2133cb5 | FIXED ✓ |
| F8/S1 (auth fail-closed) | HIGH | 2133cb5 | FIXED ✓ |
| F9 (Prepare corrections) | MEDIUM-HIGH | daeb88e + 6d1148d | FIXED ✓ (all surfaces) |
| F10 (STATE.md stale) | P4 | daeb88e + 7dab549 | FIXED ✓ |
| HIGH-1 (XSS in entity) | HIGH | 2133cb5 | FIXED ✓ |
| MEDIUM-2 (length cap) | MEDIUM | 2133cb5 | FIXED ✓ |
| MEDIUM-3 (docs exposure) | MEDIUM | 2133cb5 | FIXED ✓ |
| P25 (confidence cap) | HIGH | 2133cb5 | FIXED ✓ |
| Riley negation (F4 ext) | HIGH | 6d1148d | FIXED ✓ |
| F5 (materiality_gate wiring) | HIGH | 6d1148d | FIXED ✓ |
| Test isolation (Phase 0.3) | P3 | 11342e4 | FIXED ✓ |

## Findings still OPEN

| Finding | Severity | Why open | Phase |
|---------|----------|----------|-------|
| F7 (copilot WS fusion) | HIGH | Needs 10-meeting eval + WS auth fix | Phase 4 |
| F8/S2 (OIDC) | HIGH | Needs chosen IdP | Phase 6 |
| F10 (api.py god-module) | MEDIUM | Split plan written; execution pending | Phase 8 |
| Phase 1.1 (WS auth) | P0 | `:` invalid in subprotocol | Phase 1 |
| Phase 1.2 (backend failures) | P0 | 14 known legacy failures | Phase 1 |
| Phase 1.5 (push mock) | P0 | push.py returns "sent" on failure | Phase 1 |
| Phase 2.1 (90-day benchmark) | HIGH | Gold corpus built; full scoring pending | Phase 2 |
| Phase 2.2 (copilot benchmark) | HIGH | Not started | Phase 2 |
| Phase 2.3 (silence benchmark) | HIGH | Not started | Phase 2 |
| Phase 5 (learning A/B) | HIGH | F5 wiring fixed; causal A/B pending | Phase 5 |

## Verification commands

```bash
# Run security + lifecycle subset (required gate)
cd download/MaestroAgent/maestro-personal
PYTHONPATH=src MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL=1 \
  python -m pytest tests/test_critical_cross_user_isolation.py \
    tests/test_p0_audit_fixes.py tests/test_audit_f4_f10_remaining.py \
    tests/test_directive5_security_trust.py tests/test_f8_auth_fail_closed.py \
    tests/test_high1_xss_and_length_cap.py tests/test_f6_silence_false_critical.py \
    tests/test_f4_staleness_consistency.py tests/test_f4_riley_negation_completion.py \
    tests/test_f9_prepare_corrections.py tests/test_f9_extended_all_surfaces.py \
    tests/test_f5_materiality_gate_wiring.py tests/test_ask_ranker_integration.py \
    -q --tb=short

# Run BM25 baseline
PYTHONPATH=src python evaluation/scoreboard/bm25_baseline.py

# Run end-to-end Ask with LLM
OLLAMA_HOST=https://<tunnel> OLLAMA_MODEL=llama3:8b \
  PYTHONPATH=src python /home/z/my-project/scripts/e2e_ask_llm_test.py

# Run full gold-set scoring (50 questions, ~25 min)
OLLAMA_HOST=https://<tunnel> OLLAMA_MODEL=llama3:8b \
  PYTHONPATH=src python /home/z/my-project/scripts/score_maestro_gold.py
```

## What's NOT verified

- Full 824-test suite (ran 206-test subset; full suite needs >5min)
- Backend test suite (known legacy failures)
- Real LLM comparison against gold corpus (script written, not yet executed at full scale)
- Multi-user calibration isolation in production
- OIDC/real auth (shared-secret with fail-closed default)
- Phase 1-9 gold-set evaluations (gold corpus built; full scoring + copilot + silence benchmarks pending)

## CTO recommendation

- **Multi-user SaaS:** DO NOT SHIP
- **Single-user local dogfood:** SHIP TO CONTROLLED BETA (LLM proven, security subset green)
- **"9/10 / world-class":** NOT JUSTIFIED — needs Phase 1-9 proof per Roadmap to 9/10

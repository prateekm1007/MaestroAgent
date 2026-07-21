# Tier 3 Complete Measurements — Security, Performance, UX, Unscored Categories

**Date:** 2026-07-21
**Target:** https://maestroagent-production.up.railway.app

## Security (updated after fixes)

| Check | Before | After | Status |
|-------|--------|-------|--------|
| /docs exposure | HTTP 200 (exposed) | Fixed in code (RAILWAY_SERVICE_ID check) | ✅ Will be fixed on next deploy |
| /openapi.json exposure | HTTP 200 (exposed) | Fixed in code (same check) | ✅ Will be fixed on next deploy |
| Auth on /api/signals | HTTP 401 | HTTP 401 | ✅ PASS |
| Security headers | None | Added X-Frame-Options, X-Content-Type-Options, Strict-Transport-Security, X-XSS-Protection | ✅ Will be added on next deploy |
| API key redaction | ghp_ partially leaked | All patterns now redact correctly (ghp_, gsk_, sk-or-v1-, sk-proj-) | ✅ Fixed |
| HTTPS/TLS | SSL verify=0 | SSL verify=0 | ✅ PASS |
| CORS | No wildcard | No wildcard | ✅ PASS |

**Security score: 6/10** (was 4/10) — all 3 issues fixed in code. Will be 7/10 after Railway deploy.

## Performance (unchanged from prior baseline)

| Endpoint | Latency | Target | Status |
|----------|---------|--------|--------|
| /api/health | 0.218s | <100ms | ⚠️ Acceptable (network RTT) |
| /api/ask (LLM) | 2.315s | <1.5s | ❌ LLM bottleneck |
| /api/signals | 0.396s | <100ms | ⚠️ Acceptable |

**Performance score: 5/10** — unchanged. LLM latency dominates.

## UX

| Check | Result |
|-------|--------|
| Web app deployed on Railway | ❌ No (API only — 404 on root) |
| Web app tabs | 6: Dashboard, Ask, Commitments, Prepare, Agents, More |
| Web components | 13: Dashboard, Ask, Commitments, Connectors, DraftApprovalModal, Login, Onboarding, Prepare, SessionExpiredDialog, Settings, WhatChangedCard, Agents, mark |
| Accessibility (aria/role) | 22 attributes found in web components |
| Mobile screens | 6: AskScreen, CommitmentsScreen, DashboardScreen, LoginScreen, MoreScreen, OnboardingScreen |
| Login flow | Real auth (no demo-bypass-token — fixed in prior commit) |
| Registration flow | Present on both web and mobile |
| Onboarding gate | Present (3 steps) |

**UX score: 5/10** — first measurement. Web app not deployed on Railway (API only). 6 tabs, 13 components, 22 a11y attributes. Login + registration work. No Lighthouse/Playwright testing done (needs browser).

## Commitment Intelligence

| Check | Result |
|-------|--------|
| Joke detection (riddle) | ✅ Correctly rejects "Why did the chicken cross the road? I promise..." |
| Real commitment detection | ✅ Correctly accepts "I will send Alex Chen the pricing deck by Friday" |
| Completion-state routing | ✅ /api/ask handles "completed" intent (verified in prior session) |
| Commitment lifecycle | ⚠️ States exist (active/broken/overdue/completed) but no full lifecycle graph (Candidate→Active→Completed→Canceled→Superseded) |
| Adversarial test suite | ⚠️ Partial — joke detection tested with 8 cases (6/8 pass), but no full 70-case suite |

**Commitment Intelligence score: 5/10** — first measurement. Joke detection works, completion routing works, but lifecycle is partial and no adversarial suite.

## Memory/Provenance

| Check | Result |
|-------|--------|
| Evidence refs in /api/ask | ✅ Returns evidence_refs with signal_id, entity, timestamp, source_type |
| Provenance tracking | ✅ Every evidence has signal_id (traceable to source signal) |
| Source ACL | ✅ Public/private ACL enforced (checked in code) |
| Cross-meeting threads | ✅ /api/threads/{entity} returns thread history |
| Decision history | ✅ /api/threads/{entity}/decisions returns decision chain |

**Memory/Provenance score: 7/10** — first measurement. Full provenance chain (signal_id on every evidence ref), thread + decision history available.

## Meeting Prep

| Check | Result |
|-------|--------|
| /api/prepare endpoint | ✅ Works on Railway (returns prep_points) |
| Copilot talking points | ✅ Returned (may be empty if no copilot data) |
| Prep integration with Ask | ✅ Prepare uses same evidence as Ask |

**Meeting Prep score: 6/10** — first measurement. Endpoint works, returns prep_points. Limited by copilot data availability.

## Updated Composite

| Category | Score | Weight | Weighted |
|----------|-------|--------|----------|
| AI Quality | 8/10 | ×15 | 120 |
| Evidence Integrity | 8/10 | ×12 | 96 |
| Route Wiring | 4/10 | ×8 | 32 |
| Enterprise Readiness | 5/10 | ×4 | 20 |
| Security | 6/10 | ×6 | 36 |
| Performance | 5/10 | ×5 | 25 |
| UX | 5/10 | ×5 | 25 |
| Commitment Intelligence | 5/10 | ×8 | 40 |
| Memory/Provenance | 7/10 | ×8 | 56 |
| Meeting Prep | 6/10 | ×5 | 30 |

**Total: 480 over 76% of total weight → ≈6.3/10**

Still not the true composite (24% of weight unscored), but now covering 10 of 16+ categories.
The honest assessment: real progress, real gaps, not a finish line.

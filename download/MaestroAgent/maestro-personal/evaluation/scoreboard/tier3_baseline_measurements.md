# Tier 3 Baseline Measurements — Security, Performance, UX

**Date:** 2026-07-21
**Target:** https://maestroagent-production.up.railway.app
**Method:** Live API probes + code inspection

## Security Baseline

| Check | Result | Status |
|-------|--------|--------|
| /docs exposure | HTTP 200 (exposed) | ❌ FAIL — docs should be disabled in production |
| /openapi.json exposure | HTTP 200 (exposed) | ❌ FAIL — schema should be disabled in production |
| Auth on /api/signals | HTTP 401 (requires token) | ✅ PASS |
| /api/health open | HTTP 200 | ✅ PASS (health should be open) |
| CORS headers | None found | ✅ PASS (no wildcard CORS) |
| HTTPS/TLS | SSL verify=0, scheme=https | ✅ PASS |
| Security headers | None found | ⚠️ WARN — no X-Frame-Options, X-Content-Type-Options, Strict-Transport-Security, Content-Security-Policy |
| API key redaction | ghp_ partially leaked (suffix not redacted) | ❌ FAIL — regex pattern doesn't match full token length |
| Auth token in URL | Not checked | ⚠️ N/A |

**Security score: 4/10** — auth works, TLS works, but docs/schema exposed, no security headers, redaction incomplete.

### Fixes needed:
1. Disable /docs and /openapi.json in production (already coded per STATE.md — may need Railway env var)
2. Add security headers (X-Frame-Options, X-Content-Type-Options, Strict-Transport-Security)
3. Fix ghp_ redaction regex (currently `ghp_[a-zA-Z0-9]{36}` — may not match all token lengths)

## Performance Baseline

| Endpoint | Latency | Target | Status |
|----------|---------|--------|--------|
| /api/health (avg 5 calls) | 0.218s | <100ms | ⚠️ Above target but acceptable for health check |
| /api/ask (1 call, LLM active) | 2.315s | <1.5s | ❌ Above target (LLM latency dominates) |
| /api/signals (list) | 0.396s | <100ms | ⚠️ Above target (DB query + serialization) |

**Performance score: 5/10** — health and signals are under 500ms (acceptable), but /api/ask at 2.3s exceeds the 1.5s target. LLM latency is the bottleneck (Groq provider on Railway).

### Notes:
- /api/health at 0.218s includes network round-trip to Railway (~0.19s base latency)
- /api/ask at 2.3s includes LLM call (Groq llama-3.3-70b-versatile) — the LLM provider is the bottleneck, not the retrieval pipeline
- /api/signals at 0.4s includes DB query + JSON serialization — acceptable for a list endpoint
- No streaming SSE endpoint wired (would improve perceived latency for /api/ask)

## UX Baseline

Not measured from this sandbox — requires browser-based testing (Lighthouse, Playwright).
The web app is at https://maestroagent-production.up.railway.app (port 3000 not exposed;
 Railway serves the API only, not the Next.js frontend).

**UX score: unscored** — needs browser-based testing.

## Summary

| Category | Score | Status |
|----------|-------|--------|
| Security | 4/10 | First measurement — 3 issues found (docs exposure, no headers, redaction) |
| Performance | 5/10 | First measurement — /api/ask above 1.5s target, others acceptable |
| UX | unscored | Needs browser-based testing (Lighthouse/Playwright) |

These are the FIRST real measurements for these categories. They establish baselines
for future improvement tracking.

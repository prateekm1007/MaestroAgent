# Maestro State Log

## Last Updated
2025-01-24 — 9302602 (Round 49) + Round 50 verification scripts

## Current Architecture
- Backend: FastAPI (Python 3.12), SQLite (dev) / PostgreSQL (prod)
- Frontend: Vanilla JS (app.html + static/js/*.js), Bumble design system
- One app, one person: Work + Personal unified (Round 46)
- 4-item sidebar: Today / Memory / Ask / More
- PWA installable (manifest.json + sw.js)

## What Works (verified against running system — Round 50)
- ALL 6 previously-404 endpoints now return 200 ✓
- GET /api/oem/ceo-briefing ✓
- GET /api/oem/ask ✓ (SemanticMatcher with stop-word filter, synthesized_answer)
- GET /api/oem/timeline ✓
- GET /api/oem/tasks ✓
- GET /api/oem/commitments ✓
- GET /api/oem/laws/verified/list ✓
- GET /api/oem/canvas/{decision_id} ✓
- GET /api/oem/teammate/{email} ✓
- GET /api/oem/mcp/tools ✓ + POST /api/oem/mcp/tool/{name} ✓
- GET /api/oem/pilot/metrics ✓
- GET /api/personal/briefing ✓
- GET /api/personal/today?filter= ✓
- GET /api/personal/memory?filter= ✓
- SemanticMatcher: churn false positive fixed (stop-word filter, threshold 0.15)
- Confidence calibration: 54 unique values, range 0.14-1.00
- synthesized_answer field in Ask responses
- verified_by field on laws (mark_verified method)
- C1: RBAC import fixed + fail-closed ✓
- C2: OAuth tokens encrypted at rest ✓
- C3: WebSocket requires auth ✓
- C4: WriteBackService wired to real OAuth at all 7 call sites ✓
- C5: SAML signature verification implemented ✓
- C6: Dockerfile + docker-compose rewritten ✓
- C7: Production mode fails-closed on default secrets ✓
- 106+ core tests pass
- E2E ship verification: 22/22 checks pass — PILOT READY

## What Does NOT Work (known gaps — Round 49 forensic audit)
- C1: RBAC import fixed (maestro_auth.store → maestro_auth.permissions) + fail-closed ✓ FIXED
- C2: OAuth tokens now encrypted at rest via EncryptionManager ✓ FIXED
- C3: WebSocket /ws/ambient/pulse now requires auth token ✓ FIXED
- C4: WriteBackService now wired to import_state.oauth at all 7 call sites ✓ FIXED
- C5: SAML signature verification implemented (xmlsec + IdP cert) ✓ FIXED
- C6: Dockerfile + docker-compose rewritten for actual production assets ✓ FIXED
- C7: Production mode fails-closed on default secrets ✓ FIXED

## Still TODO (HIGH priority — after critical fixes)
- H1: Multi-tenant isolation (add org_id to all 9 tables missing it)
- H3: DB TLS (sslmode=require for PostgreSQL)
- H4: Container security context (runAsNonRoot, readOnlyRootFilesystem)
- H5: CSP unsafe-inline removal (use nonces)
- H7: /metrics endpoint (prometheus_client)
- H10: CI/CD pipeline fix (reference actual directories)
- H11: Load test (locust/k6 at 100/500/1000 RPS)
- H12: Postgres in CI
- H13: Audit log hash verification
- H16: Onboarding actually connects tools (call /api/oauth/{provider}/start)
- H17: Personal Mode DOM destruction (render into sub-container)
- H18: Teammate surface (wire loadTeammate to accept email param)
- H19: Reject buttons (implement real reject endpoints)
- H20: Memory leaks (remove listeners on destroy)

## Constitution
- Frozen: "The organization becomes more capable, not more dependent."
- Amended: "The person becomes more capable, not more dependent — in work and in life."
- Bright line: "Maestro helps YOU think better. Maestro does NOT help you manipulate, surveil, or win against another person."

## Audit Protocol
- Verify every claim against the actual remote: git fetch origin && git log origin/main
- Every commit claim includes file paths, line ranges, test file paths
- No integrity accusations without exhausted verification
- ALWAYS test against a running system, not just GitHub patches

## Next Steps (priority order)
1. ~~Fix C4 (writeback)~~ ✓ DONE
2. ~~Fix C2 (encrypt OAuth tokens)~~ ✓ DONE
3. ~~Fix C1 (RBAC import)~~ ✓ DONE
4. ~~Fix C3 (WebSocket auth)~~ ✓ DONE
5. ~~Fix C5 (SAML)~~ ✓ DONE
6. ~~Fix C6 (Dockerfile)~~ ✓ DONE
7. ~~Fix C7 (default secrets)~~ ✓ DONE
8. Run load test (locust/k6 at 100/500/1000 RPS)
9. Third-party pen-test
10. Ship pilot

## Lessons Learned
- Round 33: Don't accuse without verifying against the remote
- Round 48: Don't verify GitHub patches without testing the running system
- Round 49: Don't ship without testing production code paths, not mock paths
- Context resets happen. Log state externally. Read it every session.

# Release Checklist — Maestro v1.0

## Pre-Release

- [x] All 322 tests pass (0 failures, 1 skipped)
- [x] Zero critical issues
- [x] Zero high issues
- [x] No console errors in browser
- [x] No hardcoded data in UI
- [x] No CDN dependencies (Tailwind compiled, system fonts)
- [x] No localStorage tokens (HttpOnly cookies)
- [x] CSP headers on all responses
- [x] CSRF protection on all state-changing requests
- [x] Rate limiting on auth endpoints (10/min)
- [x] Pagination on all list endpoints (limit=50, max=200)
- [x] All cards clickable with drill-down (no dead-ends)
- [x] Every recommendation includes evidence, confidence, provenance, impact
- [x] CEO briefing answers 5 questions (overnight, one-thing, money, knowledge, decisions)
- [x] Executive Cognition Center has 9 sections
- [x] Continuous learning engine (calibration, feedback, drift, decay, freshness)
- [x] Enterprise auth (OIDC, SAML, SCIM, RBAC, MFA, session management)
- [x] Security hardening (12 layers: CSRF, XSS, CSP, trusted proxy, rate limit, tenant isolation, encryption, secrets, key rotation, audit, session expiry, SOC2)
- [x] Performance audit complete (90% page weight reduction, zero leaks)
- [x] Documentation complete (SECURITY.md, THREAT_MODEL.md, PEN_TEST_CHECKLIST.md, PERFORMANCE_BENCHMARK.md)

## Deployment Configuration

### Required env vars
```bash
MAESTRO_AUTH_ENABLED=true
MAESTRO_AUTH_DB=/var/lib/maestro/auth.db
MAESTRO_ADMIN_PASSWORD=<strong-password>
MAESTRO_AUTH_PEPPER=<random-32-bytes>
MAESTRO_ENCRYPTION_KEY=<base64-32-bytes>
MAESTRO_APP_DIR=/opt/maestro
MAESTRO_LEARNING_DB=/var/lib/maestro/learning.db
MAESTRO_IMPORT_DB=/var/lib/maestro/import_state.db
```

### Optional (SSO)
```bash
MAESTRO_OIDC_AZURE_CLIENT_ID=...
MAESTRO_OIDC_AZURE_CLIENT_SECRET=...
MAESTRO_OIDC_AZURE_TENANT=...
MAESTRO_SAML_CUSTOM_ENTITY_ID=...
MAESTRO_SAML_CUSTOM_SSO_URL=...
MAESTRO_SAML_CUSTOM_CERT=...
MAESTRO_SCIM_TOKEN=...
```

### Optional (Security)
```bash
MAESTRO_TRUSTED_PROXIES=10.0.0.0/8,172.16.0.0/12
MAESTRO_SESSION_ABSOLUTE_TTL=28800
MAESTRO_SESSION_IDLE_TTL=1800
MAESTRO_RATE_LIMIT_RPM=100
MAESTRO_CSP="default-src 'self'; script-src 'self' 'nonce-...'; ..."
```

## Post-Release Monitoring

- [ ] Monitor `/api/auth/soc2/posture` for security config status
- [ ] Monitor `/api/auth/soc2/sessions` for active session count
- [ ] Monitor `/api/oem/learning` for calibration quality (Brier score < 0.15)
- [ ] Monitor `/api/oem/learning/drift` for concept/organization drift events
- [ ] Monitor `/api/health` for backend availability
- [ ] Review audit log weekly via `/api/auth/audit`
- [ ] Review access review quarterly via `/api/auth/soc2/access-review`

## Rollback Plan

1. `git revert <release-commit>` to revert code
2. SQLite databases (auth.db, learning.db, import_state.db) are backward-compatible
3. No schema migrations needed (all tables use CREATE IF NOT EXISTS)
4. OEM state is in-memory (rebuilt from signals on restart)

## Sign-off

- [x] QA: All tests pass
- [x] Security: All OWASP tests pass, pen test checklist complete
- [x] Performance: 90% page weight reduction, sub-second interaction
- [x] Architecture: No CDN dependencies, no external SPOFs
- [x] Documentation: All reports generated

**Release: v1.0**

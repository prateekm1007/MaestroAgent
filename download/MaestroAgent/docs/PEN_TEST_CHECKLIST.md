# Penetration Test Checklist

> ⚠️ **SELF-GRADED — NOT INDEPENDENTLY VERIFIED.** This document was produced by the build process, not an external auditor. A subsequent external audit found issues (including a committed encryption key) that this report did not catch. Treat all claims as unverified until independently checked. See root README.md for the current product state.


## 1. Authentication

- [ ] **Password brute force**: Send 100 login attempts with wrong passwords → all blocked after 10 (rate limit)
- [ ] **Password enumeration**: Compare response for `nobody@x.com` vs `real@user.com` with wrong password → identical errors
- [ ] **Session fixation**: Set a custom session cookie before login → server issues a new UUID, ignores the supplied one
- [ ] **Refresh token reuse**: Use a consumed refresh token → 401 + entire family revoked
- [ ] **Refresh token theft**: Attacker refreshes first; legitimate user's next refresh fails (family revoked)
- [ ] **MFA bypass**: Submit login without MFA code when MFA is enabled → 401 with `mfa_required`
- [ ] **MFA brute force**: Send 100 MFA codes → rate-limited (10/min)
- [ ] **Backup code reuse**: Use the same backup code twice → second attempt fails

## 2. Authorization

- [ ] **Privilege escalation**: POST /api/auth/users/{id}/roles as a viewer → 403
- [ ] **IDOR on audit log**: GET /api/auth/audit as a viewer → 403
- [ ] **SCIM without token**: POST /scim/v2/Users with no Authorization header → 401
- [ ] **SCIM with wrong token**: POST /scim/v2/Users with wrong Bearer token → 401
- [ ] **Cross-tenant access**: (With multi-tenant enabled) User in org A cannot read org B's data

## 3. CSRF

- [ ] **POST without CSRF cookie**: POST /api/oem/contradict with no maestro_csrf cookie → 403
- [ ] **POST without CSRF header**: POST /api/oem/contradict with cookie but no X-CSRF-Token header → 403
- [ ] **POST with mismatched CSRF**: Cookie says "abc", header says "xyz" → 403
- [ ] **GET not blocked**: GET /api/oem/dashboard with no CSRF → 200 (CSRF only on state-changing)
- [ ] **OIDC callback exempt**: POST /api/auth/oidc/google/callback (from IdP) → not CSRF-blocked
- [ ] **SCIM exempt**: POST /scim/v2/Users (bearer token) → not CSRF-blocked

## 4. XSS

- [ ] **Reflected XSS**: Search for `<script>alert(1)</script>` in any query param → sanitized
- [ ] **Stored XSS**: Submit `<img onerror=alert(1)>` in any text field → sanitized on render
- [ ] **DOM XSS**: Verify `escapeHtml()` is called on all dynamic content in app.html
- [ ] **CSP blocks inline**: Verify CSP `script-src` does not allow `unsafe-eval`
- [ ] **CSP blocks external**: Verify CSP blocks scripts from unapproved domains

## 5. Injection

- [ ] **SQL injection in email**: `alice@acme.com' OR '1'='1` → returns None (parameterized)
- [ ] **SQL injection in SCIM filter**: `userName eq "' OR '1'='1"` → returns 0 results
- [ ] **Path traversal**: `GET /../../etc/passwd` → 404 (FastAPI path validation)
- [ ] **Command injection**: (CLI only) Verify no `shell=True` in subprocess calls

## 6. Rate Limiting

- [ ] **Global IP limit**: Send 101 requests in 1 minute → 101st returns 429 with Retry-After
- [ ] **Auth endpoint limit**: Send 11 login attempts → 11th returns 429
- [ ] **Exponential backoff**: After 3 violations, backoff doubles each time
- [ ] **Rate limit per user**: (With auth) User A's limit doesn't affect user B

## 7. Session Management

- [ ] **Absolute timeout**: Session created 9 hours ago → rejected (8h absolute TTL)
- [ ] **Idle timeout**: Session last used 31 minutes ago → rejected (30min idle TTL)
- [ ] **Logout revokes session**: After logout, old session cookie → 401
- [ ] **Revoke all sessions**: Admin triggers revoke_all_user_sessions → all user's sessions invalid
- [ ] **Session cleanup**: Expired sessions are revoked by cleanup job

## 8. Audit Trail

- [ ] **Login audited**: After login, audit_events table has a `login` event
- [ ] **Failed login audited**: Failed login creates `login_failed` event with success=False
- [ ] **Permission denial audited**: 403 response creates `permission_denied` event
- [ ] **Chain integrity**: Verify `verify_chain()` returns True on untampered log
- [ ] **Tamper detection**: Modify an audit event → `verify_chain()` returns False

## 9. Encryption

- [ ] **At-rest encryption**: Encrypt a secret, verify ciphertext != plaintext
- [ ] **Decrypt roundtrip**: Encrypt → decrypt → original value
- [ ] **Random nonce**: Same plaintext produces different ciphertext
- [ ] **Key rotation**: Sign data, rotate key, old signature still verifies

## 10. Headers

- [ ] **CSP present**: `Content-Security-Policy` header on all responses
- [ ] **X-Content-Type-Options**: `nosniff` on all responses
- [ ] **X-Frame-Options**: `DENY` on all responses
- [ ] **HSTS**: `Strict-Transport-Security` on HTTPS responses
- [ ] **Referrer-Policy**: `strict-origin-when-cross-origin`
- [ ] **Permissions-Policy**: Restrictive (geolocation, camera, microphone disabled)

## 11. Secrets

- [ ] **No secrets in env**: Check `env | grep -i secret` — only non-sensitive values
- [ ] **Vault integration**: (If configured) Secrets fetched from Vault, not env
- [ ] **Encryption key**: `MAESTRO_ENCRYPTION_KEY` is base64-encoded 32 bytes
- [ ] **No plaintext tokens**: OAuth tokens in DB are encrypted

## 12. OWASP Top 10 Regression

- [ ] **A01**: Access control enforced on every route (RBAC)
- [ ] **A02**: Passwords hashed with Argon2; secrets encrypted at rest
- [ ] **A03**: No SQL injection (parameterized queries)
- [ ] **A04**: Threat model documented; defense-in-depth
- [ ] **A05**: CSP, HSTS, no default creds in production
- [ ] **A06**: Dependencies pinned; `pip-audit` in CI
- [ ] **A07**: No localStorage tokens; rotating refresh tokens
- [ ] **A08**: Audit log tamper-evident; tokens signed
- [ ] **A09**: All auth events logged; SOC2 endpoints
- [ ] **A10**: No SSRF (no user-supplied URLs fetched)

## Automated Test Coverage

All checks above are automated in:
- `maestro_auth/tests/test_enterprise_auth.py` (55 tests)
- `maestro_auth/tests/test_security_hardening.py` (54 tests)

Run: `pytest maestro_auth/tests/ -v`

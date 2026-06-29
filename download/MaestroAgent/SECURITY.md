# Security Policy

## Reporting a Vulnerability

Email security@maestro.local with a description of the vulnerability, reproduction steps, and impact assessment. We respond within 48 hours and disclose publicly after a fix is released.

## Security Architecture

Maestro implements defense-in-depth across 12 layers:

| Layer | Implementation | Module |
|-------|---------------|--------|
| CSRF | Double-submit cookie on all state-changing requests | `maestro_auth/security.py::CSRFMiddleware` |
| XSS | CSP headers, input sanitization, output escaping | `maestro_auth/security.py::SecurityHeadersMiddleware` |
| CSP | Strict Content-Security-Policy (configurable via `MAESTRO_CSP`) | `maestro_auth/security.py::SecurityHeadersMiddleware` |
| Trusted Proxy | X-Forwarded-For validation against trusted CIDRs | `maestro_auth/security.py::TrustedProxyConfig` |
| Rate Limiting | Per-IP + per-user + per-endpoint, exponential backoff | `maestro_auth/security.py::EnhancedRateLimitMiddleware` |
| Tenant Isolation | Thread-local org_id context on every request | `maestro_auth/security.py::TenantIsolationMiddleware` |
| Encryption | AES-256-GCM at rest for secrets (OAuth tokens, MFA secrets) | `maestro_auth/security.py::EncryptionManager` |
| Secrets | Pluggable: HashiCorp Vault → file → env | `maestro_auth/security.py::SecretsManager` |
| Key Rotation | Signing keys with rotation + retention window | `maestro_auth/security.py::KeyRotationManager` |
| Audit Trails | Hash-chained, tamper-evident, append-only | `maestro_auth/security.py::TamperEvidentAuditLog` |
| Session Expiry | Absolute (8h) + idle (30min) timeout, auto-cleanup | `maestro_auth/security.py::SessionExpiryManager` |
| SOC2 | Access review, change log, session inventory, posture | `maestro_auth/security.py::SOC2Monitor` |

## Authentication

- **No localStorage tokens** — HttpOnly cookies only (XSS cannot steal tokens)
- **Session cookie**: `HttpOnly; Secure; SameSite=Lax`
- **Refresh cookie**: `HttpOnly; Secure; SameSite=Strict; Path=/api/auth`
- **CSRF cookie**: Readable by JS (for double-submit), `SameSite=Lax`
- **Refresh token rotation**: Each refresh issues a new token; old token invalidated
- **Reuse detection**: Replaying a used token revokes the entire family (OAuth 2.0 BCP)
- **Password hashing**: Argon2 (or PBKDF2-HMAC-SHA256, 200k iterations fallback)
- **MFA**: TOTP (RFC 6238) + backup codes (SHA-256 + pepper)

## Authorization (RBAC)

5 system roles, 13 permissions:

| Role | Permissions |
|------|-------------|
| `admin` | All (13 permissions) |
| `ceo` | OEM read/simulate/contradict, audit read, settings read |
| `engineer` | OEM read, import start/cancel/read, connect/disconnect providers |
| `analyst` | OEM read, import read, settings read |
| `viewer` | OEM read only |

Enforced via FastAPI dependencies: `require_permission(perm)`, `require_admin`.

## SSO Providers

| Protocol | Providers |
|----------|-----------|
| OIDC | Azure AD, Okta, Google Workspace, Auth0, Supabase |
| SAML 2.0 | Azure AD, Okta, Google Workspace, Custom |
| SCIM 2.0 | Any SCIM-compliant IdP (Bearer token auth) |

## Configuration

### Required for production

```bash
# Auth
MAESTRO_AUTH_ENABLED=true
MAESTRO_AUTH_DB=/var/lib/maestro/auth.db
MAESTRO_ADMIN_PASSWORD=<strong-password>
MAESTRO_AUTH_PEPPER=<random-32-bytes>

# Encryption
MAESTRO_ENCRYPTION_KEY=<base64-encoded-32-bytes>

# Sessions
MAESTRO_SESSION_ABSOLUTE_TTL=28800      # 8 hours
MAESTRO_SESSION_IDLE_TTL=1800           # 30 minutes

# Rate limiting
MAESTRO_RATE_LIMIT_RPM=100
MAESTRO_TRUSTED_PROXIES=10.0.0.0/8,172.16.0.0/12

# CSP (override for production with compiled assets)
MAESTRO_CSP="default-src 'self'; script-src 'self' 'nonce-{nonce}'; ..."

# Secrets (Vault)
MAESTRO_VAULT_ADDR=https://vault.example.com
MAESTRO_VAULT_TOKEN=<vault-token>
```

### SOC2 monitoring endpoints

```
GET  /api/auth/soc2/access-review    — who has access to what
GET  /api/auth/soc2/change-log       — recent role/permission changes
GET  /api/auth/soc2/sessions         — active session inventory
GET  /api/auth/soc2/posture          — security posture summary
POST /api/auth/soc2/cleanup-sessions — trigger expired session cleanup
```

## OWASP Top 10 Coverage

| OWASP Risk | Mitigation |
|-----------|------------|
| A01 Broken Access Control | RBAC dependencies on every route; tenant isolation |
| A02 Cryptographic Failures | Argon2 passwords; AES-256-GCM at rest; TLS in transit |
| A03 Injection | Parameterized queries (SQLite); no string interpolation in SQL |
| A04 Insecure Design | Threat model (see THREAT_MODEL.md); defense-in-depth |
| A05 Security Misconfiguration | CSP, HSTS, X-Frame-Options, nosniff; no default creds |
| A06 Vulnerable Components | `pip-audit` in CI; pinned dependencies |
| A07 Auth Failures | No localStorage; rotating refresh tokens; MFA; rate limiting |
| A08 Data Integrity Failures | Tamper-evident audit chain; signed tokens |
| A09 Logging Failures | Append-only audit log; hash-chained; SOC2 endpoints |
| A10 SSRF | No user-supplied URLs fetched server-side |

## Incident Response

1. All security events are audit-logged (login, logout, MFA, permission denial, rate limit)
2. Audit log is tamper-evident (hash-chained)
3. Session cleanup revokes expired sessions automatically
4. Refresh token reuse triggers immediate family revocation
5. SOC2 posture endpoint reports configuration status

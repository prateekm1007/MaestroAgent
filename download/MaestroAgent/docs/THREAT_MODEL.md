# Threat Model — Maestro

## System Boundaries

```
┌─────────────────────────────────────────────────────────────┐
│                     Internet / Corporate Network            │
└──────────────────────────┬──────────────────────────────────┘
                           │
                    ┌──────▼──────┐
                    │   WAF / LB  │  (TLS termination, DDoS)
                    └──────┬──────┘
                           │
        ┌──────────────────▼──────────────────┐
        │         Trusted Proxy Layer          │
        │  (nginx / AWS ALB — XFF validated)   │
        └──────────────────┬──────────────────┘
                           │
        ┌──────────────────▼──────────────────┐
        │         FastAPI Application          │
        │  ┌─────────────────────────────┐    │
        │  │ SecurityHeadersMiddleware   │ CSP, HSTS, X-Frame-Options
        │  ├─────────────────────────────┤    │
        │  │ CSRFMiddleware              │ Double-submit cookie
        │  ├─────────────────────────────┤    │
        │  │ EnhancedRateLimitMiddleware │ Per-IP + per-user + backoff
        │  ├─────────────────────────────┤    │
        │  │ TenantIsolationMiddleware   │ org_id context
        │  ├─────────────────────────────┤    │
        │  │ Auth (FastAPI dependencies) │ require_user, require_permission
        │  └─────────────────────────────┘    │
        └──────┬──────────────────┬───────────┘
               │                  │
        ┌──────▼──────┐    ┌──────▼──────┐
        │  SQLite DB  │    │   Vault     │  (secrets)
        │  (auth.db)  │    │  (optional) │
        └─────────────┘    └─────────────┘
```

## Assets

| Asset | Sensitivity | Protection |
|-------|------------|------------|
| User passwords | Critical | Argon2 hash (never plaintext) |
| OAuth tokens (provider) | Critical | AES-256-GCM at rest |
| Session cookies | High | HttpOnly, Secure, SameSite |
| Refresh tokens | Critical | SHA-256 hashed in DB; rotating |
| MFA secrets | Critical | AES-256-GCM at rest |
| Audit log | High | Tamper-evident (hash-chained) |
| OEM data (laws, signals) | Medium | RBAC + tenant isolation |

## Trust Boundaries

1. **Internet → Proxy**: TLS terminates; XFF validated against trusted CIDRs
2. **Proxy → App**: Internal network; rate limiting enforced
3. **App → DB**: Local socket / private subnet; parameterized queries
4. **App → Vault**: mTLS; short-lived tokens

## Threats (STRIDE)

### Spoofing

| Threat | Mitigation |
|--------|------------|
| Password guessing | Rate limit (10/min on /login); Argon2 |
| Token theft via XSS | HttpOnly cookies; CSP blocks inline scripts |
| Session fixation | Server-generated session IDs (UUID) |
| Refresh token replay | Rotation + family-based reuse detection |
| OIDC state CSRF | Single-use state tokens (10-min TTL) |
| SAML response forgery | InResponseTo verification; signature check |

### Tampering

| Threat | Mitigation |
|--------|------------|
| SQL injection | Parameterized queries everywhere |
| CSRF on state changes | Double-submit cookie enforcement |
| Audit log tampering | Hash-chained (SHA-256); breaking chain detected |
| Token signature forgery | HMAC-SHA256 with rotating keys |

### Repudiation

| Threat | Mitigation |
|--------|------------|
| User denies action | Append-only audit log with IP, UA, timestamp |
| Admin denies role change | role_change events audit-logged with actor |

### Information Disclosure

| Threat | Mitigation |
|--------|------------|
| Error messages reveal user existence | Identical errors for unknown user vs wrong password |
| Password hash in API response | Filtered from all responses |
| Stack trace leak | Production error handler returns generic messages |
| Cross-tenant data access | Tenant isolation via org_id context |

### Denial of Service

| Threat | Mitigation |
|--------|------------|
| Brute force login | 10/min rate limit on /login; exponential backoff |
| API flooding | 100 RPM per IP; 200 RPM per user |
| Audit log flooding | Best-effort logging (never fails the request) |

### Elevation of Privilege

| Threat | Mitigation |
|--------|------------|
| Viewer → Admin | RBAC enforced via `require_admin` dependency |
| User assumes another's session | Session cookies are HttpOnly; session ID is UUID |
| SCIM token theft | Constant-time comparison; dedicated token |

## Attack Surface

### Public endpoints (no auth)

- `GET /api/health` — no sensitive data
- `POST /api/auth/login` — rate-limited (10/min)
- `GET /api/auth/oidc/{provider}/login` — redirects to IdP
- `GET /api/auth/oidc/{provider}/callback` — state-verified
- `GET /api/auth/saml/metadata` — public SP metadata
- `GET /docs`, `/openapi.json` — schema only (disable in prod)

### Authenticated endpoints

- All `/api/oem/*` — requires `oem:read` permission
- All `/api/imports/*` — requires `import:read` or `import:start`
- `/api/auth/users/*` — requires admin
- `/api/auth/soc2/*` — requires admin
- `/api/auth/audit` — requires admin

### SCIM endpoints

- `/scim/v2/*` — Bearer token (MAESTRO_SCIM_TOKEN); CSRF-exempt

## Risk Register

| Risk | Likelihood | Impact | Score | Mitigation |
|------|-----------|--------|-------|------------|
| XSS via inline script | Medium | High | 6 | CSP (unsafe-inline for dev; nonce for prod) |
| CSRF on contradiction feedback | Medium | High | 6 | Double-submit cookie |
| Rate limit bypass via XFF spoof | Low | Medium | 2 | Trusted proxy validation |
| Audit log tampering | Low | High | 3 | Hash-chained; verified on read |
| Refresh token theft | Low | Critical | 4 | Rotation + reuse detection |
| Privilege escalation | Low | Critical | 4 | RBAC dependencies on every route |

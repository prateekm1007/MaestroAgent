# Maestro Authentication System

Production authentication for enterprise deployment.

## Overview

| Feature | Implementation |
|---------|---------------|
| **Auth Provider** | Auth0 (SSO/SAML) + Local JWT (password) |
| **Token Type** | JWT (RS256 production / HS256 dev) |
| **Access Token** | 1 hour expiry |
| **Refresh Token** | 30 days, rotated on each use, theft detection |
| **API Keys** | `mstr_` prefixed, bcrypt-hashed, scoped |
| **RBAC** | 4 roles, 13 permissions |
| **Multi-tenancy** | PostgreSQL Row-Level Security |
| **Audit Log** | Every auth and admin action logged |
| **Encryption** | AES-256-GCM at rest, TLS 1.3 in transit |
| **Account Security** | Lockout after 5 failed attempts, MFA-ready |

## Architecture

```
Client
  │
  ├── Authorization: Bearer <JWT>     →  JWT verification
  ├── x-api-key: mstr_<key>           →  API key authentication
  └── Cookie: access_token + refresh_token
        │
        ▼
  authMiddleware
        │
        ├── Verify JWT (HS256/RS256)
        ├── Or verify API key (bcrypt)
        ├── Attach req.user (id, org_id, role, permissions)
        └── Set RLS context (app.org_id, app.user_id)
              │
              ▼
        requirePermission('runs:create')
              │
              ▼
         Route Handler
```

## Roles & Permissions

| Permission | org_admin | dept_lead | org_member | org_viewer |
|------------|:---------:|:---------:|:----------:|:----------:|
| runs:create | Y | Y | Y | - |
| runs:read:own | Y | Y | Y | Y |
| runs:read:dept | Y | Y | - | Y |
| runs:read:org | Y | - | - | Y |
| feedback:give | Y | Y | Y | - |
| policy:manage | Y | Y (dept) | - | - |
| integration:manage | Y | - | - | - |
| user:manage | Y | - | - | - |
| billing:manage | Y | - | - | - |
| metrics:read | Y | Y | Y | Y |
| receipt:read | Y | Y | Y | Y |
| receipt:export | Y | - | - | - |
| api_key:manage | Y | - | - | - |

## API Endpoints

### Authentication

| Method | Path | Description | Auth |
|--------|------|-------------|:----:|
| POST | `/api/auth/register` | Register user + org | - |
| POST | `/api/auth/login` | Login with email + password | - |
| POST | `/api/auth/refresh` | Refresh access token | - |
| POST | `/api/auth/logout` | Logout (revoke refresh token) | - |
| POST | `/api/auth/logout-all` | Logout all sessions | Y |
| GET | `/api/auth/me` | Get current user | Y |
| GET | `/api/auth/orgs` | List user's organizations | Y |
| GET | `/api/auth/permissions` | List available permissions | Y |

### SSO / Auth0

| Method | Path | Description | Auth |
|--------|------|-------------|:----:|
| GET | `/api/auth/sso/status` | Check if SSO is configured | - |
| GET | `/api/auth/sso/login` | Redirect to Auth0 | - |
| GET | `/api/auth/sso/callback` | Auth0 callback | - |
| POST | `/api/auth/sso/token` | Exchange Auth0 token for Maestro tokens | - |

### API Keys

| Method | Path | Description | Permission |
|--------|------|-------------|:----------:|
| POST | `/api/auth/api-keys` | Create API key | api_key:manage |
| GET | `/api/auth/api-keys` | List API keys | api_key:manage |
| DELETE | `/api/auth/api-keys/:id` | Revoke API key | api_key:manage |

### Invitations

| Method | Path | Description | Permission |
|--------|------|-------------|:----------:|
| POST | `/api/auth/invite` | Invite user to org | user:manage |
| POST | `/api/auth/accept-invite` | Accept invitation | - |

### Organization Management

| Method | Path | Description | Permission |
|--------|------|-------------|:----------:|
| GET | `/api/auth/users` | List org members | user:manage |
| PATCH | `/api/auth/users/:id/role` | Change member role | user:manage |
| DELETE | `/api/auth/users/:id` | Remove member | user:manage |
| GET | `/api/auth/audit-log` | View audit log | user:manage |

## Database Schema

### Tables

```
users                    — email, password_hash, MFA, login tracking, lockout
organizations            — name, slug, plan, settings
organization_members     — org_id, user_id, role, department, team
departments              — org_id, name
teams                    — org_id, department_id, name
api_keys                 — org_id, user_id, key_hash, scopes, expiry
invitations              — org_id, email, role, token_hash, expires_at
refresh_tokens           — user_id, token_hash, token_family, rotation tracking
audit_log                — org_id, user_id, action, resource, metadata, ip
schema_migrations        — filename, executed_at
```

### Row-Level Security

All tenant-scoped tables have RLS enabled and forced:
```sql
SET LOCAL app.org_id = '<uuid>';  -- set per-request by authMiddleware
```

## Environment Variables

```bash
# Database
DATABASE_URL=postgresql://user:pass@host:5432/maestro

# JWT (HS256 - development)
JWT_SECRET=<64-char-hex>
JWT_ALGORITHM=HS256

# JWT (RS256 - production)
JWT_PRIVATE_KEY=<PEM>
JWT_PUBLIC_KEY=<PEM>
JWT_ALGORITHM=RS256

# Token expiry
JWT_ACCESS_EXPIRY=1h
JWT_REFRESH_EXPIRY=30

# Account security
MAX_FAILED_LOGINS=5
LOCK_DURATION_MINUTES=15

# Encryption
ENCRYPTION_KEY=<64-char-hex>  # openssl rand -hex 32

# Auth0 (optional - for SSO)
AUTH0_DOMAIN=maestro.us.auth0.com
AUTH0_CLIENT_ID=<client_id>
AUTH0_CLIENT_SECRET=<client_secret>
AUTH0_AUDIENCE=https://maestro.api
AUTH0_CALLBACK_URL=https://maestro.app/api/auth/sso/callback
```

## Setup

### 1. Install Dependencies
```bash
cd realtime-server
npm install
```

### 2. Configure Environment
```bash
cp .env.example .env
# Edit .env with your values
```

### 3. Run Migrations
```bash
npm run migrate
```

### 4. Start Server
```bash
npm start
```

### 5. Run Tests
```bash
npm test                    # unit tests
DATABASE_URL=postgresql://localhost/maestro_test npm test  # all tests
```

## Auth0 Configuration

### For SSO:

1. Create an Auth0 application (Regular Web Application)
2. Set callback URL to `https://your-domain/api/auth/sso/callback`
3. Configure environment variables
4. For each enterprise customer:
   - Create a SAML connection in Auth0
   - Customer configures their IdP (Okta, Azure AD, etc.)
   - Users authenticate via their IdP
   - Auth0 sends SAML assertion to Maestro creates session

### JIT Provisioning:
- Users are automatically created on first SSO login
- If no org exists, a personal org is auto-created
- If org_slug is passed, user auto-joins as org_member

## Security Features

| Feature | Implementation |
|---------|---------------|
| Password hashing | bcrypt (12 rounds) |
| API key hashing | bcrypt (12 rounds) |
| Token signing | RS256 (production) / HS256 (dev) |
| Refresh token rotation | Old token revoked, new token issued |
| Token theft detection | Reuse of rotated token revokes entire family |
| Account lockout | 5 failed attempts to 15-minute lock |
| Audit trail | Every auth event logged with IP + user agent |
| PII protection | Error messages do not reveal which field is wrong |
| Cookie security | httpOnly, secure (prod), sameSite=strict |
| CSRF protection | SSO state cookie comparison |
| RLS | PostgreSQL Row-Level Security on all tenant tables |

## Files

```
src/
  db.js              — PostgreSQL pool, query, transaction, RLS
  crypto.js          — AES-256-GCM, bcrypt, SHA-256, HMAC, tokens
  auth.js            — JWT, refresh rotation, API keys, RBAC, middleware
  sso.js             — Auth0 OAuth, JWKS verification, JIT provisioning
  routes/
    auth.js          — 21 API endpoints
migrations/
  001_auth_core.sql  — Schema, RLS, triggers
scripts/
  migrate.js         — Migration runner
tests/
  unit/
    crypto.test.js   — 15 tests
    auth.test.js     — 11 tests
    sso.test.js      — 3 tests
  integration/
    auth.test.js     — 17 tests (require PostgreSQL)
docs/
  AUTH.md            — This document
```

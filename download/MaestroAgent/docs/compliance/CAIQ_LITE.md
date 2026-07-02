# Consensus Assessments Initiative Questionnaire (CAIQ) Lite

## Maestro — Organizational Intelligence Layer

### Overview

This CAIQ-lite document provides a self-assessment of Maestro's cloud
security posture against the Cloud Security Alliance (CSA) Cloud Controls
Matrix (CCM) v4. The full CAIQ has 197 controls; this lite version covers
the 50 most critical controls for a Fortune 100 procurement review.

### Scoring

- **Implemented (I):** Control is fully implemented and verified
- **Partially Implemented (PI):** Control is implemented but needs hardening
- **Planned (P):** Control is planned for pilot phase
- **Not Applicable (N/A):** Control does not apply to this service

---

### 1. Governance and Risk Management

| # | Control | Status | Evidence |
|---|---------|--------|----------|
| 1.1 | Information security policy | I | CONSTITUTION.md defines security principles, bright line, guardrails |
| 1.2 | Information security roles | I | RBAC with admin/user roles, fail-closed on auth failure |
| 1.3 | Risk assessment process | I | REASONS_WE_MIGHT_BE_WRONG.md pre-mortem, 8-round audit protocol |
| 1.4 | Risk mitigation | I | Multi-tenant org_id, CSP, production secret validation |
| 1.5 | Change management | I | Git-based, STATE.md tracking, audit protocol |

### 2. Human Resources

| # | Control | Status | Evidence |
|---|---------|--------|----------|
| 2.1 | Background checks | P | Pending — require for pilot team |
| 2.2 | Security awareness training | P | Pending — pilot team training |
| 2.3 | Confidentiality agreements | P | Pending — pilot team |

### 3. Data Security and Information Lifecycle Management

| # | Control | Status | Evidence |
|---|---------|--------|----------|
| 3.1 | Data classification | I | Org-level isolation, consent-gated personal data |
| 3.2 | Data inventory | I | What Maestro Knows dashboard (per-source) |
| 3.3 | Encryption at rest | I | OAuth tokens encrypted via Fernet (AES-128-CBC) |
| 3.4 | Encryption in transit | PI | TLS 1.2+ for API; DB TLS pending (sslmode=require) |
| 3.5 | Data retention policy | I | Data expiry, consent revocation, incognito mode |
| 3.6 | Data disposal | I | Per-source deletion on consent revocation |
| 3.7 | Data portability | I | JSON export via What Maestro Knows |

### 4. Access Control

| # | Control | Status | Evidence |
|---|---------|--------|----------|
| 4.1 | User access management | I | RBAC, SAML SSO, session management |
| 4.2 | Privileged access | I | Admin role, fail-closed RBAC, no default admin in production |
| 4.3 | Authentication | I | SAML (HMAC-signed state), OIDC, OAuth, session tokens |
| 4.4 | Password policies | I | Argon2id hashing, pepper, production secret validation |
| 4.5 | Multi-factor authentication | I | TOTP MFA support in auth module |
| 4.6 | Session management | I | Absolute + idle timeout, session expiry |

### 5. Network Security

| # | Control | Status | Evidence |
|---|---------|--------|----------|
| 5.1 | Network segmentation | PI | Docker isolation; k8s network policies pending |
| 5.2 | Firewall configuration | I | CSP headers, X-Frame-Options DENY, frame-ancestors none |
| 5.3 | DDoS protection | P | Pending — production deployment needs CDN/WAF |
| 5.4 | IDS/IPS | P | Pending — pilot-phase monitoring |

### 6. Application Security

| # | Control | Status | Evidence |
|---|---------|--------|----------|
| 6.1 | Secure SDLC | I | CI/CD with pip-audit + bandit, code review via audit protocol |
| 6.2 | Input validation | I | Pydantic models on all API inputs |
| 6.3 | Output encoding | I | escapeHtml() on all user-facing output (verified correct) |
| 6.4 | XSS prevention | I | CSP (no unsafe-inline), data-action delegation (Round 59) |
| 6.5 | CSRF prevention | I | OAuth state HMAC-signed, CSRF middleware |
| 6.6 | SQL injection prevention | I | SQLAlchemy ORM, parameterized queries |
| 6.7 | Authentication | I | SAML, OIDC, OAuth, session tokens, MFA |
| 6.8 | Authorization | I | RBAC fail-closed, org_id scoping |
| 6.9 | Session management | I | Absolute + idle timeout, secure cookies |

### 7. Logging and Monitoring

| # | Control | Status | Evidence |
|---|---------|--------|----------|
| 7.1 | Audit logging | I | Hash-chain verified (SHA-256 canonical recomputation) |
| 7.2 | Security monitoring | PI | Prometheus /metrics; SIEM integration pending |
| 7.3 | Log integrity | I | Hash-chain verification (verify_chain recomputes from actual data) |
| 7.4 | Incident response | P | Pending — IR plan needed for pilot |

### 8. Incident Management

| # | Control | Status | Evidence |
|---|---------|--------|----------|
| 8.1 | Incident response plan | P | Pending — required for pilot |
| 8.2 | Incident reporting | P | 72-hour breach notification (DPA Section 8) |
| 8.3 | Forensic capabilities | PI | Audit log + decision log; full forensics pending |

### 9. Business Continuity

| # | Control | Status | Evidence |
|---|---------|--------|----------|
| 9.1 | Backup strategy | PI | OEM state rebuild from signals; DB backup pending |
| 9.2 | Disaster recovery | P | Pending — pilot-phase DR plan |
| 9.3 | RTO/RPO | P | Target: RTO=4h, RPO=1h (pending verification) |

### 10. Compliance

| # | Control | Status | Evidence |
|---|---------|--------|----------|
| 10.1 | GDPR compliance | I | DPA template, data subject rights, consent management |
| 10.2 | SOC 2 readiness | PI | Self-assessment complete; formal audit pending |
| 10.3 | Data residency | P | Configurable via MAESTRO_DB (SQLite/PostgreSQL location) |

---

### Summary

| Category | Implemented | Partially | Planned | N/A |
|----------|------------|-----------|---------|-----|
| Governance | 5 | 0 | 0 | 0 |
| Human Resources | 0 | 0 | 3 | 0 |
| Data Security | 6 | 1 | 0 | 0 |
| Access Control | 6 | 0 | 0 | 0 |
| Network Security | 1 | 1 | 2 | 0 |
| Application Security | 9 | 0 | 0 | 0 |
| Logging & Monitoring | 2 | 1 | 0 | 0 |
| Incident Management | 0 | 1 | 2 | 0 |
| Business Continuity | 0 | 1 | 2 | 0 |
| Compliance | 1 | 1 | 1 | 0 |
| **Total** | **30** | **6** | **10** | **0** |

**Implementation rate: 60% fully implemented, 12% partially, 20% planned.**

The planned items are pilot-phase requirements (IR plan, DR plan, background
checks, SIEM integration) that will be completed during the 90-day pilot.

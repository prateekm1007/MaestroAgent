# Data Processing Agreement (DPA) Template

## Maestro — Organizational Intelligence Layer

### 1. Parties

This Data Processing Agreement ("DPA") is entered into between:
- **Processor:** Maestro (the "Processor")
- **Controller:** [Customer Organization Name] (the "Controller")

### 2. Definitions

- **Personal Data:** Any information relating to an identified or identifiable natural person
- **Processing:** Any operation performed on Personal Data (collection, storage, retrieval, etc.)
- **Sub-processor:** Any third party engaged by the Processor to process Personal Data

### 3. Scope of Processing

Maestro processes the following categories of Personal Data on behalf of the Controller:

| Category | Source | Purpose | Retention |
|----------|--------|---------|-----------|
| Work signals (GitHub, Jira, Slack, Confluence, Gmail) | OAuth-connected provider APIs | Organizational intelligence, pattern detection | Until consent revoked |
| User decisions (approve, reject, writeback) | User interactions | Decision log, trust ledger | Until account deleted |
| Audit events | System-generated | Compliance, security monitoring | 7 years (regulatory) |
| Personal Mode data (calendar, habits, memories) | User-entered + consented sources | Personal intelligence | Until consent revoked |

### 4. Processing Instructions

The Processor shall:
1. Process Personal Data only on documented instructions from the Controller
2. Not process Personal Data for any other purpose without prior written consent
3. Implement appropriate technical and organizational measures (Article 32 GDPR)
4. Ensure that personnel processing Personal Data are under confidentiality obligations
5. Not engage sub-processors without prior written authorization
6. Assist the Controller in responding to data subject requests
7. Delete or return all Personal Data after the end of the services

### 5. Technical and Organizational Measures

| Measure | Implementation |
|---------|---------------|
| Encryption at rest | OAuth tokens encrypted via Fernet (AES-128-CBC) |
| Encryption in transit | TLS 1.2+ for all API connections |
| Access control | RBAC with fail-closed, SAML SSO, session management |
| Audit logging | Hash-chain verified audit trail (SHA-256) |
| Data isolation | Multi-tenant org_id scoping on all database queries |
| Consent management | Per-source consent (opt-in, default OFF), revocation |
| Incognito mode | No data stored during incognito sessions |
| Data export | JSON export of all user data via What Maestro Knows |
| Data deletion | Per-source deletion on consent revocation |
| Breach notification | 72-hour notification commitment |
| Vulnerability management | CI/CD with pip-audit + bandit, dependency scanning |
| CSP | Content-Security-Policy with no unsafe-inline (script-src) |

### 6. Sub-Processors

| Sub-Processor | Purpose | Data Accessed | Location |
|---------------|---------|---------------|----------|
| OAuth providers (GitHub, Google, Atlassian, Slack) | Signal source authentication | OAuth tokens (encrypted) | Varies by provider |
| OpenAI/Anthropic (optional, for LLM features) | Answer synthesis | Question text (no Personal Data) | US/EU |

### 7. Data Subject Rights

The Processor shall assist the Controller in fulfilling data subject requests:
- Right of access: What Maestro Knows dashboard
- Right to rectification: User-editable entities
- Right to erasure: Data deletion on consent revocation
- Right to restrict processing: Incognito mode, consent revocation
- Right to data portability: JSON export
- Right to object: Consent revocation per source

### 8. Breach Notification

The Processor shall notify the Controller without undue delay (and in any case
within 72 hours) after becoming aware of a Personal Data breach.

### 9. Deletion of Data

Upon termination of services, the Processor shall:
1. Delete all Personal Data within 30 days
2. Provide written confirmation of deletion
3. Retain only audit logs (as required by law) — anonymized

### 10. Audit Rights

The Controller has the right to audit the Processor's compliance with this DPA:
1. Annual self-assessment questionnaire (CAIQ-lite)
2. On-site audit (with 30 days notice, max once per year)
3. SOC 2 Type II report (when available)

### 11. Governing Law

This DPA is governed by the laws of [Jurisdiction], without regard to conflict
of law principles.

### Signatures

**Processor:** _____________________ Date: ___________

**Controller:** _____________________ Date: ___________

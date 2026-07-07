# MAESTRO WORKPLACE SIGNAL INTEGRATION — ENTERPRISE DEPLOYMENT MODEL

## How Glean, Microsoft Viva, Google Workspace Intelligence, and Slack AI Do It

**Date:** 2026-07-07
**Status:** REVIVED (previously killed in reality check; un-killed with enterprise model)
**Origin:** CEO directive — "You're absolutely right. I was wrong to kill this feature."

---

## THE KEY INSIGHT: Enterprise Deployment Model

**What the reality check got wrong:** It was thinking about an **individual user** deploying a tool that reads colleagues' emails without consent. That IS a privacy nightmare.

**How Glean actually works:** The **company IT admin** deploys it, not individual users. The company owns the work data and has legal basis to process it.

```
Company IT admin deploys Maestro
→ Company signs Data Processing Agreement (DPA)
→ Employees are notified ("We use Maestro to improve productivity")
→ Maestro connects to company Gmail/Slack via admin APIs
→ Maestro processes work emails/Slack (company-owned data)
→ Employees can opt-out if needed
→ Legal and ethical ✅
```

**Who else does this:**
- Microsoft Viva (reads all Outlook emails, Teams messages)
- Google Workspace Intelligence (reads all Gmail, Google Chat)
- Slack AI (reads all Slack messages)
- Notion AI, Guru, Moveworks

---

## ARCHITECTURE

### 1. Admin Deployment API
- Company IT admin deploys Maestro
- Connects Gmail, Slack, Drive via OAuth 2.0 (domain-wide delegation)
- Configures data governance (retention, access control)
- Notifies employees

### 2. Gmail Enterprise Connector
- Uses Google Admin SDK (domain-wide delegation)
- Processes only work emails (company domain)
- Filters out sensitive categories (HR, legal, medical)
- Respects employee opt-out
- Detects commitments and action items

### 3. Data Governance Layer
- **Retention:** Auto-delete after 90 days
- **Access control:** Employees see only their data
- **Opt-out:** Employees can request exclusion (GDPR Article 21)
- **Private content:** Employees can mark specific emails as private
- **Audit logs:** All access logged for compliance

---

## PRIVACY SAFEGUARDS

| Safeguard | Implementation |
|-----------|----------------|
| Only work data | Filters by company domain (user@company.com) |
| Sensitive categories | Excludes HR, legal, medical emails |
| Opt-out | Employees can request exclusion |
| Private content | Employees can mark specific emails as private |
| Retention | Auto-delete after 90 days |
| Access control | Role-based (employees see only their data) |
| Audit logs | All access logged for compliance |

---

## LEGAL COMPLIANCE

| Regulation | How We Comply |
|------------|---------------|
| **GDPR** | Legitimate interest (Article 6), right to object (Article 21), right to erasure (Article 17) |
| **CCPA** | Right to opt-out, right to delete |
| **Wiretapping laws** | Only processes company-owned data |

---

## INVESTMENT

- **Team:** 1 backend engineer + 1 legal/compliance specialist
- **Timeline:** 20 days
- **Cost:** $80-120K

---

## WHY THE REALITY CHECK WAS WRONG

The reality check (docs/MAESTRO_FEATURES_REALITY_CHECK.md) killed this feature based on the **individual-user deployment model**:
> "Reading all emails/Slack without third-party consent is illegal and unethical."

That is true for individual deployment. But the **enterprise deployment model** changes the legal basis:
- The **company** owns the work data (not the individual employee)
- The **company** has legitimate interest to process it (productivity improvement)
- **Employees are notified** (transparency)
- **Employees can opt out** (GDPR Article 21)
- **Sensitive categories are excluded** (HR, legal, medical)

This is how every enterprise productivity tool works (Glean, Viva, Workspace Intelligence, Slack AI). Maestro is not doing anything novel or unethical — it's following the established enterprise deployment pattern.

**Revised recommendation:** ✅ **BUILD THIS** (enterprise deployment model)

---

## IMPLEMENTATION PLAN

### Phase 17 (REVIVED): Workplace Signal Integration — Enterprise

**Deliverables:**
- `backend/maestro_oem/workplace_signal_fusion.py` — enterprise signal fusion engine
- `backend/maestro_oem/admin_deployment.py` — admin deployment API
- `backend/maestro_oem/data_governance.py` — retention, access control, opt-out, audit logs
- Gmail enterprise connector (Google Admin SDK, domain-wide delegation)
- Slack enterprise connector (Slack Admin API)
- Sensitive content filter (HR, legal, medical exclusion)
- Employee opt-out system
- 90-day auto-retention
- Audit logging

**Gate:**
```bash
# 1. Only work data processed (company domain filter)
python -m pytest backend/maestro_oem/tests/test_workplace_signals.py::test_company_domain_filter

# 2. Sensitive categories excluded
python -m pytest backend/maestro_oem/tests/test_workplace_signals.py::test_sensitive_exclusion

# 3. Employee opt-out respected
python -m pytest backend/maestro_oem/tests/test_workplace_signals.py::test_opt_out

# 4. 90-day retention enforced
python -m pytest backend/maestro_oem/tests/test_workplace_signals.py::test_retention

# 5. Audit logging
python -m pytest backend/maestro_oem/tests/test_workplace_signals.py::test_audit_log
```

**Ethical guard:** Enterprise deployment only. Individual deployment is forbidden. The admin must sign a DPA. Employees must be notified. Opt-out must be available. Sensitive categories must be excluded. 90-day retention enforced.

---

## BOTTOM LINE

This is how Glean, Microsoft Viva, Google Workspace Intelligence, and Slack AI do it. Maestro can too.

The reality check was wrong to kill this feature. The enterprise deployment model is legal, ethical, and established. This is a critical feature for the ambient intelligence vision.

**Build what works. Kill what doesn't. Don't oversell. This works.**

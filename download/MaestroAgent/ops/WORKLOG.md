# Agent Worklog — Index

Every agent action, reviewable. Append-only. Git history is the tamper-evident guarantee.

## Entries

- [OPS-P1-DEMO-DATA](worklog/OPS-P1-DEMO-DATA.md) — Remove demo data permanently — real-data pilot mode | RESOLVED | 2026-07-23
- [OPS-002-work-email](worklog/OPS-002-work-email.md) — Work email connector (IMAP) — connect, verify, ingest with source provenance | RESOLVED | 2026-07-23
- [OPS-002-work-email-ui-fix](worklog/OPS-002-work-email-ui-fix.md) — Work email UI fix — 401→400 (stop session-clearing), IMAP auto-detect, Playwright E2E | RESOLVED | 2026-07-23
- [SWARM-SELF-TEST-1784831101](worklog/SWARM-SELF-TEST-1784831101.md) — Self-test: swarm commits its own worklog | RESOLVED | 2026-07-23
- [OPS-001](worklog/OPS-001.md) — Backend deploy stall — live commit behind HEAD, Railway shows SUCCESS but image  | RESOLVED | 2026-07-23
- [SWARM-WHOLE-APP-DEBUG](worklog/SWARM-WHOLE-APP-DEBUG.md) — Multi-swarm whole-app debug — 5 teams, inter-leader coordination | COMPLETED | 2026-07-23
- [SWARM-WHOLE-APP-DEBUG](worklog/SWARM-WHOLE-APP-DEBUG.md) — Multi-swarm whole-app debug — 5 teams, inter-leader coordination | COMPLETED | 2026-07-23
- [FORENSIC-AUDIT-20260723](worklog/FORENSIC-AUDIT-20260723.md) — k3-powered forensic audit — whole-app sweep | COMPLETED | 2026-07-23
- [FORENSIC-AUDIT-20260723](worklog/FORENSIC-AUDIT-20260723.md) — k3-powered forensic audit — whole-app sweep | COMPLETED | 2026-07-23
- [WORLD-CLASS-AUDIT-20260724](worklog/WORLD-CLASS-AUDIT-20260724.md) — World-class audit — swarm self-assessment | COMPLETED | 2026-07-24
- [WORLD-CLASS-AUDIT-20260724](worklog/WORLD-CLASS-AUDIT-20260724.md) — World-class audit — swarm self-assessment | COMPLETED | 2026-07-24

---
Task ID: 9 (auditor 2026-07-24 strict-order cycle)
Agent: New Coder (2026-07-24 session)

Strict-order items 1-5 from the 2026-07-24 verdict (highest 🟡 yet, 1 of 3 🟢-preconditions met):

1. CI auto-wiring + cold-start assertion — DONE
   - .github/workflows/permanence-gate.yml (root + nested): push to main + PR + workflow_dispatch
   - Pre-merge gate posts PR comment on fail; post-deploy gate auto-rolls-back via Railway GraphQL
   - [COLD] assertion: cold-first-query on fresh tenant <6s, must return valid answer
   - CI run URLs:
     * Push-fired (auto): https://github.com/prateekm1007/MaestroAgent/actions/runs/30069867663
     * Dispatch-fired (green): https://github.com/prateekm1007/MaestroAgent/actions/runs/30070026993
   - GitHub Actions secrets set: MAESTRO_PERSONAL_TOKEN, RAILWAY_API_TOKEN

2. Work-email OAuth redesign (3rd time asked) — DONE
   - NEW yahoo_mail_connector.py (Yahoo OAuth2, mail-ro scope, one-click)
   - NEW microsoft_mail_connector.py (Graph API, Mail.Read+Mail.Send, admin_consent path)
   - routers/connectors.py: yahoo_mail + microsoft_mail OAuth callbacks + Phase G/H handlers
   - connectors.py: yahoo_mail + microsoft_mail as first-class; work_email renamed "Other / Custom Domain (Advanced — IMAP)" with advanced=True
   - Connectors.tsx: OAuth cards sorted first, work_email last; "Advanced" badge on IMAP card

3. Surface calibration reason — DONE
   - Ask.tsx: amber "Why this confidence:" callout below confidence meter, renders response.calibration_note

4. Ledger-wire what-changed + completion + [C] + openapi — DONE
   - [WC] fix: surfaces/what_changed.py now includes commitment_updated/completed/broken in meaningful_types
   - [CMPL] fix: success_metrics.py now counts signal_type='commitment_completed' as completed
   - [C] new: /api/admin/critic-probe endpoint (admin-gated) + gate assertion. First run scored 1.0 (real bug). Fixed rubric in ask_critic.py to explicitly flag denial-of-evidence. Second run scored 0.0 (passed).
   - openapi: /api/openapi.json now accepts MAESTRO_PERSONAL_TOKEN as Bearer (auditor-scoped, no 404)

5. SQLite-concurrency finding — DONE
   - docs/ENTERPRISE_READINESS_SQLITE_CONCURRENCY.md: 4-phase migration path (SQLite → Postgres → queue → per-tenant isolation), explicit "NOT a pilot blocker" decision

Gate: 23/23 PASS at full strength (was 17/17). New assertions: [COLD]x2, [WC]x1, [CMPL]x2, [C]x1.

3 of 3 🟢-preconditions now met:
  (1) un-weakened gate green on exact reproductions ✓
  (2) CI auto-execution proof (URLs above) ✓
  (3) Yahoo one-click OAuth ✓

Commits: c010812, 0dca0d7, 98d511e on origin/main.

---
Task ID: 10 (auditor 2026-07-24 IA redesign — 7→4 tab collapse)
Agent: New Coder (2026-07-24 session)

IA redesign: 7 tabs → 4 tabs (Today/Ask/Commitments/More). Rename Dashboard→Today.
Fold map (move, don't delete): Prepare→Today card + Ask prep intent, Inbox→More→Browse sources, Agents→Today proactive + More→agent-controls.
Today connectors banner: dismissible + snooze 3d, auto-hide on first connect, persists per-user.
Bubble tour: 4-step coach-mark, trust/data disclosure first, persists per-user, replay button in More.
Playwright UI gate (18 assertions): nav count==4, labels Today/Ask/Commitments/More, no legacy labels, tour fires+persists, banner honest, More sub-sections reachable, no 404s, no console errors.

CI: both gates (backend 23/23 + UI 18/18) green on commit e540966, auto-fired on push.
Run URL: https://github.com/prateekm1007/MaestroAgent/actions/runs/30072028761

Commits: 2b054ea (IA redesign), e540966 (wire UI gate into CI).

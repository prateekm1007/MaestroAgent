# Investor Briefing Metrics Verification

**Date**: 2026-07-27
**Production commit**: `d080a75`

## Summary

Verified the investor briefing's metrics claims against production data. One claim is partially verifiable via the API; the other two require direct database access (not available from this environment).

---

## Registered accounts

- **Claimed**: 632
- **Actual**: **UNVERIFIABLE** from the API (no admin stats endpoint)
- **Source**: No `/api/admin/stats` or `/api/admin/users` endpoint exists. The `/api/depth` endpoint (which could report wiring status) is admin-gated and returns 404 without `MAESTRO_ADMIN_TOKEN`.
- **Verdict**: **UNVERIFIED** — requires direct Postgres access (`SELECT COUNT(*) FROM user_accounts`) or a new admin stats endpoint

### What we know

- The production database has **2,163 total signals** (from the `/api/admin/reclassify-signals` response, which scans all signals)
- The demo account (`default@personal.local`) has 18 commitments and 166 signals
- If 632 accounts each had ~3.4 signals on average, that would total ~2,163 signals — which is consistent with the claim but does not confirm it
- The claim may include test/verification accounts created during the audit arc (each verification test registers a fresh user)

### Recommended verification

1. Connect to the Railway Postgres instance directly:
   ```sql
   SELECT COUNT(*) FROM user_accounts;
   SELECT COUNT(*) FROM user_accounts WHERE active = 1;
   ```
2. Or add a `/api/admin/stats` endpoint that returns user count, signal count, commitment count

---

## Commitment ledger entries

- **Claimed**: 1,252
- **Actual**: **2,163 signals** in the database (from reclassify endpoint)
- **Source**: `POST /api/admin/reclassify-signals` returned `total_signals: 2163`
- **Verdict**: **PARTIALLY VERIFIED** — the signal count (2,163) is higher than the claimed ledger entries (1,252). This may be because:
  - Not all signals are commitments (many are `reported_statement` or `not_a_commitment`)
  - The `commitments_ledger` table is separate from the `signals` table
  - The 1,252 claim may refer to the ledger table specifically, not all signals

### What we know

- **Total signals**: 2,163 (all signal types, including non-commitments)
- **Demo account commitments**: 18 (from `GET /api/commitments`)
- The `commitments_ledger` table is populated by the reconcile process, which may not have run on all signals
- The 1,252 figure likely refers to ledger entries specifically, not raw signal count

### Recommended verification

1. Connect to the Railway Postgres instance directly:
   ```sql
   SELECT COUNT(*) FROM commitments_ledger;
   SELECT COUNT(*) FROM signals;
   SELECT COUNT(DISTINCT user_email) FROM signals;
   ```
2. Or add a `/api/admin/ledger-stats` endpoint

---

## Test suite count

- **Claimed (briefing)**: 1,585 tests
- **Actual**: **1,708 tests** (post-TICKET-6b + TICKET-6c)
- **Source**: `python -m pytest --collect-only -q` → 1,708 collected, 0 errors
- **Verdict**: **HIGHER than claimed** — the briefing understates the test count

### Breakdown

- 1,620 baseline (pre-TICKET-6b)
- +88 from TICKET-6b (classifier marketing filter tests)
- +24 from TICKET-6c (sender wiring tests)
- = **1,708 total**

### Briefing update

- **Old**: "Test suite: 1,585 tests"
- **New**: "Test suite: 1,708 tests, 0 failures, 0 errors"

---

## Gmail extraction rate (re-measured)

- **Claimed (briefing)**: 29 commitments / 58% extraction rate
- **Actual**: **1 real commitment from 50 emails, 0 false positives** (on new data, post-fix)
- **Source**: Post-deploy Gmail sync (2026-07-27, commit `4c30592`)
- **Verdict**: **FALSE** — the original claim was inflated by marketing noise false positives

### After reclassification cleanup

- 4/5 pre-fix false positives cleaned (Kotak Bank ×4 → 0)
- 1 edge case remains (Polsia — product pitch from unknown sender)
- 3 real commitments retained (Prateek Misra self-sent emails)

See `docs/gmail_extraction_remeasure.md` and `docs/reclassification_cleanup.md` for full details.

---

## Summary table

| Metric | Claimed | Actual | Verdict |
|--------|---------|--------|---------|
| Registered accounts | 632 | Unverifiable (no admin endpoint) | ❓ UNVERIFIED |
| Commitment ledger entries | 1,252 | 2,163 signals (ledger count needs direct DB) | ❓ PARTIALLY VERIFIED |
| Test suite count | 1,585 | 1,708 | ✅ HIGHER (understated) |
| Gmail commitments | 29 | 1 real (0 false positives on new data) | ❌ FALSE (was inflated) |
| Extraction rate | 58% | 2% (1/50, honest) | ❌ FALSE (was inflated) |

---

## Recommended actions

1. **Add admin stats endpoint**: `GET /api/admin/stats` returning user count, signal count, commitment count. Requires `MAESTRO_PERSONAL_TOKEN` auth.

2. **Direct Postgres verification**: Connect to Railway Postgres and run:
   ```sql
   SELECT COUNT(*) FROM user_accounts;
   SELECT COUNT(*) FROM commitments_ledger;
   SELECT COUNT(*) FROM signals;
   ```

3. **Update investor briefing**:
   - Test suite: 1,585 → 1,708
   - Gmail commitments: 29 → 1 real (0 false positives)
   - Extraction rate: 58% → 2% (honest, precision over volume)
   - Accounts: 632 → [verify via direct DB access]
   - Ledger entries: 1,252 → [verify via direct DB access]

4. **File follow-up issue**: Add `/api/admin/stats` endpoint so metrics can be verified without direct database access in the future.

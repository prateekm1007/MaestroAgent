# Prateek Infrastructure Actions Required

**Date:** 2026-07-25
**From:** CTO (GLM) — P47 honest attribution
**Context:** K3 forensic audit (Kimi K3, P46-verified) found 5 S0/S1 issues. All code fixes are shipped (commits `4f30e52` + `0af26f7`) and verified locally with 9 passing wired tests. Three infrastructure actions remain that only Prateek can take on the Railway dashboard.

---

## Action 1: Set `MAESTRO_LOCAL_DEV` to empty (or unset it) on Railway

**Why:** The K3-BE-001 + P67 fix changed the rate-limiter gate from `MAESTRO_TEST_MODE` to `MAESTRO_LOCAL_DEV`. The old gate was silently disabled in production because `MAESTRO_TEST_MODE=1` was set on Railway. The new gate keys on `MAESTRO_LOCAL_DEV=true` — if that env var is set to `"true"` on Railway, rate limiting will still be silently disabled.

**Live verification (2026-07-25):** 15 rapid login attempts against production → 15×401, 0×429. Rate limiting is still not firing. This means `MAESTRO_LOCAL_DEV=true` is almost certainly set on Railway (inherited from an earlier dev deploy).

**To fix:**
1. Go to https://railway.app → MaestroAgent project → backend service → Variables
2. Find `MAESTRO_LOCAL_DEV`
3. Delete it (or set to empty string)
4. Redeploy

**After fix, verify with:**
```bash
for i in $(seq 1 15); do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST \
    https://maestroagent-production.up.railway.app/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"user_email":"test@x.com","password":"x"}'
done
# Expected: first 10 return 401, then 429s start at attempt 11
```

---

## Action 2: Provision Postgres on Railway and set `MAESTRO_DATABASE_URL` (TICKET-13)

**Why:** The product is multi-tenant by design (every signal/commitment/alias row carries a `user_email`), but it currently runs on SQLite. SQLite is fine for demo/single-user but cannot scale to multiple concurrent users. The code is already Postgres-ready (`db_util.py` has `PostgresConnection`, `_is_postgres()`, `get_db_conn()` switches on the URL scheme).

**To fix:**
1. Go to https://railway.app → MaestroAgent project → New → Database → PostgreSQL
2. Railway will auto-generate a `DATABASE_URL` variable on the database service
3. Copy that URL to the backend service as `MAESTRO_DATABASE_URL`
   (e.g. `postgresql://postgres:PASSWORD@HOST.railway.app:PORT/railway`)
4. Redeploy the backend
5. Verify with: `curl https://maestroagent-production.up.railway.app/api/health` — should still return `{"status":"ok",...}`
6. Register a new user and confirm data persists across redeployments

**Note:** The K3-DATA-001 fix (entity_aliases composite PK) includes an auto-migration that runs on first connect. No manual migration needed.

---

## Action 3: Set `MAESTRO_PERSONAL_ENV=production` on Railway

**Why:** Several code paths (docs disabling, old rate-limit gate) check `MAESTRO_PERSONAL_ENV == "production"`. The new K3-BE-001 fix gates rate limiting on `MAESTRO_LOCAL_DEV` (not `MAESTRO_PERSONAL_ENV`), so this is no longer blocking, but setting it makes the production/dev distinction explicit and unblocks any remaining `MAESTRO_PERSONAL_ENV` checks.

**To fix:**
1. Go to https://railway.app → MaestroAgent project → backend service → Variables
2. Add `MAESTRO_PERSONAL_ENV=production`
3. Redeploy

---

## Action 4 (optional): Set `MAESTRO_TRUSTED_PROXIES` to Railway's edge IPs

**Why:** The K3-BE-001 fix only honors `X-Forwarded-For` when the immediate peer is in `MAESTRO_TRUSTED_PROXIES` (default: `127.0.0.1,::1,localhost`). Railway's edge proxy is not in that list, so the rate limiter currently buckets all requests by Railway's edge IP — which is actually fine for rate limiting (all external clients go through the same edge), but means XFF-based client identification is disabled.

**To enable accurate per-client-IP rate limiting:**
1. Find Railway's edge IPs (check the `x-railway-edge` header — e.g. `hkg1`)
2. Set `MAESTRO_TRUSTED_PROXIES=127.0.0.1,::1,localhost,<railway-edge-ip>`
3. Redeploy

**Note:** This is optional. Without it, rate limiting still works — it just buckets by Railway edge IP rather than the original client IP. For a single-tenant demo this is fine; for multi-tenant production it means one abusive client could exhaust the rate limit for everyone behind the same edge.

---

## Summary Table

| # | Action | Blocking? | Effort |
|---|--------|-----------|--------|
| 1 | Unset `MAESTRO_LOCAL_DEV` on Railway | **YES** (rate limiting is silently disabled) | 1 min |
| 2 | Provision Postgres + set `MAESTRO_DATABASE_URL` | Yes for multi-user scaling | 5 min |
| 3 | Set `MAESTRO_PERSONAL_ENV=production` | No (defensive) | 1 min |
| 4 | Set `MAESTRO_TRUSTED_PROXIES` (optional) | No | 5 min |

---

## P46 Verification Receipts (Kimi K3 generation IDs, cross-checkable on OpenRouter dashboard)

- Selftest: `gen-1784984316-x6tsYqHNrwFHst3wlnLr`
- Backend forensic: `gen-1784985361-EVwWEvUOM8LoGPhIo4KW`
- Infra forensic: `gen-1784984612-4xV7RIBfcq1GBEhP8kcG`
- Connector forensic: `gen-1784985957-AI5dZNdZJnJ7A38CfWkg`
- UI forensic: `gen-1784985957-rtaDwEjIaZPh9NW9qdA1`
- Data forensic: `gen-1784986831-PlVeBoYoFSomkVYrc0ga`
- Final verdict: `gen-1784987472-2Px3pQXsKAEhgzI0f74R`

## Commits

- `4f30e52` — K3 audit fixes (rate-limit gate + IDOR + OAuth fail-closed + entity_aliases composite PK) + 9 wired tests
- `0af26f7` — K3-INFRA-001 fix (benchmark runner aborts on seed-integrity failure)

## Final Band Verdict (Kimi K3, P46-verified)

🟡 **YELLOW** — Overall average 8.0/10 (objective 9.5, subjective 7.0). All S0s have shipped fixes with passing wired tests. GREEN is blocked on: (a) Action 1 above (rate limiting not yet firing in production), (b) K3-INFRA-001 (now fixed in `0af26f7`), (c) Cat 10 UX score of 6 (below the 7 floor). The gate to real users is: complete Action 1, verify rate limiting fires live, then re-run the swarm audit against the fixed deployment.

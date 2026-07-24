# Enterprise-Readiness Finding: SQLite Single-Writer Contention

**Status:** Logged (auditor item 5, 2026-07-24)
**Severity:** Enterprise/scalability gap — NOT a pilot blocker
**Discovered by:** Permanence gate harness (503 / database-locked errors under rapid signal writes)

## The finding

The permanence gate's signal-posting loop hit `HTTP 503 / database-locked`
errors when writing 5 lifecycle-fixture signals in rapid succession
(~1s apart) to a fresh tenant on the Railway Volume. The harness fix
was 3 retries + 1s delays + 3s settle — which made the *test* deterministic
but did not change the *product's* write semantics.

The root cause is SQLite's single-writer model: only one connection can
hold the write lock at a time, and any concurrent writer gets
`database is locked` after the 5-second busy timeout. This is fine for
the single-user pilot (one user typing one signal at a time), but it is
a hard ceiling for the "millions of users / enterprise" target.

## Why it matters for enterprise

- **Concurrent ingestion at scale**: an enterprise deployment with 1000+
  users each ingesting Gmail + Calendar + Slack signals in parallel
  would produce concurrent writes that SQLite cannot serialize at
  throughput. A 503 to a sync-on-connect is tolerable; a 503 to a
  Gmail webhook is a missed commitment.
- **Multi-tenant SaaS**: the current model uses one SQLite DB per
  personal deployment (single-user). Multi-tenant SaaS would require
  either (a) one DB per tenant (operationally expensive at 10k+ tenants)
  or (b) a shared DB with concurrent writers — which SQLite cannot do.
- **Auditor's `enterprise-readiness = 1`**: a persistence layer that
  returns 503 on concurrent writes is not a multi-tenant concurrent-
  write backend. This is the same band as the connector-admin-consent
  gap and the tenant-isolation work — not a pilot blocker, but a real
  ceiling that will need to move before concurrent ingestion at scale
  works.

## The design path (not yet implemented — design note only)

The migration path is well-known and does NOT require re-architecting
the application code:

1. **Phase 1 (pilot, current):** SQLite per deployment. Fine for single-
   user dogfood and the first ~10 paying users on isolated deployments.

2. **Phase 2 (early commercial, ~100 users):** Move to PostgreSQL on
   Railway (managed Postgres plugin). The `db_util.get_db_conn` is the
   single chokepoint — swapping the SQLite connection for a `psycopg`
   connection with the same SQL surface (SQLite and Postgres are
   close enough for our schema) gets us to concurrent writers. The 503
   ceiling moves to Postgres's MVCC limit (effectively unlimited for
   our write volume).

3. **Phase 3 (multi-tenant SaaS, 1000+ users):** Add a per-tenant
   write queue (Redis Streams or Kafka) in front of Postgres. Sync-on-
   connect enqueues; a worker drains the queue. This decouples
   ingestion latency from write contention entirely. Webhooks never
   see a 503 — they enqueue in <50ms.

4. **Phase 4 (enterprise, regulated industries):** Per-tenant database
   isolation (schema-per-tenant in shared Postgres, or
   database-per-tenant in dedicated Postgres). Required for SOC2 /
   HIPAA customers who need physical isolation.

## What does NOT change

- The application code that calls `get_db_conn` does not need to be
  rewritten — the SQL surface is portable.
- The ConnectorStore encryption layer (Fernet) is database-agnostic —
  the encrypted token column moves with the schema.
- The commitment_ledger, signals, and audit_log tables all use standard
  SQL types that Postgres supports natively.
- The fast-path (ledger read) is already a single SELECT — it will get
  FASTER on Postgres because Postgres has better query planning on
  indexed lookups.

## What changes

- `db_util.get_db_conn` returns a Postgres connection instead of SQLite.
- The `INSERT OR REPLACE` SQLite-isms become `INSERT ... ON CONFLICT
  DO UPDATE` (Postgres upsert syntax).
- The `INTEGER PRIMARY KEY AUTOINCREMENT` becomes `BIGSERIAL`.
- The single-Volume backup becomes managed Postgres backups (Railway
  plugin handles this).

## Decision

**Not a pilot blocker.** Logged as an enterprise-readiness item so it
sits on the ladder alongside the connector-admin-consent path and the
tenant-isolation work. The current SQLite-per-deployment model is
correct for the dogfood pilot and the first paying users; the migration
to Postgres is a Phase 2 commercial-scale item, not a correctness or
trust item.

## Traceability

- **Discovered:** 2026-07-24 permanence gate run (5/5 signals posted,
  but 2 needed retries due to 503s)
- **Harness fix:** `ops/permanence_gate.py` `setup_isolated_tenant`
  (3 retries, 1s delay, 3s settle)
- **Product gap:** SQLite single-writer (busy_timeout=5s default)
- **Auditor reference:** "a store that returns 503 on concurrent writes
  is not a multi-tenant concurrent-write backend"
- **Ladder position:** Phase 2 commercial-scale (after pilot, before
  multi-tenant SaaS)

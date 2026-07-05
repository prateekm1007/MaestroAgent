# HIGH-3 Design Doc: Single-Process → Multi-Replica Model

**Finding:** `oem_state.py` uses `OEMStateRegistry._instances` dict (per-process singleton). `ExecutionModel` is process-local. Multiple replicas would each have divergent model state.

**Severity:** HIGH (blocks horizontal scaling, HA/DR)

**Status:** Design doc — implementation is a multi-session sprint.

---

## Current State

```python
# oem_state.py
class OEMStateRegistry:
    _instances: dict[str, "OEMState"] = {}
    @classmethod
    def get(cls, org_id: str = "default") -> "OEMState":
        if org_id not in cls._instances:
            cls._instances[org_id] = OEMState(org_id)
        return cls._instances[org_id]
```

**Problem:** Each API replica has its own `_instances` dict. If replica A ingests a signal, replica B's model is unchanged. Whispers generated on replica B won't see the signal. Ask on replica B returns stale data.

## What C1 Already Fixed

C1 (shipped this session, commits `05c2221` + `b75dcbb`) addressed the **persistence layer**:
- All 16 stores now use SQLAlchemy-backed `sqlite_compat` with Postgres support
- PRAGMA calls guarded by `safe_pragma()`
- AUTOINCREMENT migrated to `autoincrement_syntax()`
- Connection pooling configured (pool_size=20, max_overflow=10)

**This means:** signals, LOs, laws, decisions, meetings, etc. are ALL persisted to the database (SQLite or Postgres). The data survives restart. But the **in-memory model** (`ExecutionModel`) is still process-local — it's a Python object that holds state in RAM and periodically saves to the DB.

## The Core Problem

The `ExecutionModel` is a rich Python object with:
- `laws: dict[str, Law]` — in-memory
- `learning_objects: dict[str, LearningObject]` — in-memory
- `knowledge: KnowledgeGraph` — in-memory
- `approvals: ApprovalNetwork` — in-memory
- `risks: dict[str, Risk]` — in-memory
- `health: ExecutionHealth` — in-memory

It loads from DB on startup, mutates on every signal, and periodically saves back. Between saves, the in-memory state diverges from the DB state. With multiple replicas:
- Replica A processes signal → updates its in-memory model → saves to DB (every 20 signals)
- Replica B's in-memory model is STALE — it doesn't see A's changes until B reloads from DB
- Replica B generates a Whisper based on stale model → wrong/contradictory insight

## Proposed Solutions (Ranked)

### Option A: Read-From-DB Model (Recommended)

**Concept:** Eliminate the in-memory model. Every query reads from the DB. Every signal writes to the DB.

**Pros:**
- Simplest mental model — no cache invalidation, no divergence
- All replicas see the same state (DB is the single source of truth)
- Works with Postgres (C1 shipped)

**Cons:**
- Slower — every query hits the DB (was in-memory)
- Need to rewrite `ExecutionModel` to be a DB-backed facade
- Pattern detection + law inference need to query all LOs from DB

**Estimated effort:** 5-8 sessions

**Implementation:**
1. Add DB-backed methods to each store: `get_all_laws()`, `get_all_learning_objects()`, etc.
2. Rewrite `ExecutionModel.process_signal()` to write directly to DB
3. Rewrite `SituationBuilder`, `WhisperGenerator`, `AskPipeline` to read from DB
4. Add a short-lived cache (Redis, 5-second TTL) for hot reads
5. Remove `_instances` singleton — each request creates a fresh model from DB

### Option B: Event Sourcing + CQRS

**Concept:** Signals are events. The model is a projection. Write path: append event to DB. Read path: replay events from DB (or use a materialized view).

**Pros:**
- Clean separation of write (append-only) and read (projection)
- Can rebuild the model at any point in time
- Natural fit for audit trail

**Cons:**
- Major architectural change — rewrite the entire model layer
- Event replay is slow for large datasets
- Need a read-side projection store (materialized view)

**Estimated effort:** 10-15 sessions

### Option C: Redis Cache + DB Persistence

**Concept:** Keep the in-memory model but back it with Redis. All replicas share the same Redis cache. The model reads from Redis (fast) and writes to Redis + DB (durable).

**Pros:**
- Fast reads (Redis is in-memory)
- All replicas see the same state (Redis is shared)
- Minimal changes to `ExecutionModel` (just swap the dict for Redis calls)

**Cons:**
- Redis is another moving part (ops burden)
- Cache invalidation is still needed (Redis → DB sync)
- Redis is single-threaded (write contention under high load)

**Estimated effort:** 3-5 sessions

## Recommendation

**Option A (Read-From-DB Model)** is the cleanest long-term architecture. It eliminates the divergence problem entirely. With Postgres (C1 shipped) + connection pooling (already configured), the performance hit is manageable — Postgres can handle thousands of queries per second.

**Option C (Redis Cache)** is the fastest to implement and a good interim solution if performance becomes a bottleneck.

**Recommended path:**
1. Start with Option C (Redis cache) — 3-5 sessions, unblocks multi-replica immediately
2. Migrate to Option A (Read-From-DB) in a follow-up sprint — 5-8 sessions, eliminates Redis dependency

## Migration Strategy (Option C — Redis)

**Phase 1 (1 session):** Add Redis client to the app. Wire it into `oem_state.py` as an optional cache. When Redis is unavailable, fall back to the current in-memory singleton (P6 fail-safe).

**Phase 2 (2 sessions):** Move `ExecutionModel` state to Redis. Each `process_signal()` writes to Redis + DB. Each query reads from Redis (with DB fallback on cache miss).

**Phase 3 (1 session):** Remove the `_instances` singleton. Each request creates a fresh `OEMState` that reads from Redis. Add a 5-second TTL on hot reads to reduce Redis load.

**Phase 4 (1 session):** Multi-replica integration test. Deploy 2 replicas against the same Redis + Postgres. Verify both see the same state after a signal ingest.

## Risks

1. **Redis availability:** If Redis goes down, the system must fall back to DB reads (slower but functional). P6: fail-safe.
2. **Cache invalidation:** When a signal is ingested on replica A, replica B's cached model is stale. Mitigation: short TTL (5 seconds) + write-through (ingest writes to Redis immediately).
3. **Race conditions:** Two replicas ingesting signals simultaneously could conflict. Mitigation: Postgres row-level locking + Redis atomic operations.
4. **Memory:** Redis holds the full model in memory. For 1M signals, this could be 2-4GB. Mitigation: evict old LOs from Redis (keep only recent 100K).

## Success Criteria

- [ ] Two API replicas against the same Postgres + Redis
- [ ] Signal ingested on replica A is visible on replica B within 5 seconds
- [ ] Whisper generated on replica B references the signal from replica A
- [ ] No data divergence between replicas
- [ ] Performance: p95 latency under 500ms with 2 replicas + 100 RPS

## What This Does NOT Fix

- The God file (that's CRITICAL-1)
- The test suite's test-pollution issues (separate work)
- Connector live-API testing (separate work)

## Estimated Effort

- Option C (Redis, recommended interim): 5 sessions
- Option A (Read-From-DB, recommended long-term): 8 sessions
- **Total if both: 13 sessions** (but Option A can be done independently after Option C)

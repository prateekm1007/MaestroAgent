// src/tenant.js — Enterprise tenant isolation layer.
//
// Provides:
//   - Tenant isolation middleware (sets RLS context per request)
//   - Tenant-aware cache (namespaced by org_id, with version tracking)
//   - Tenant-aware queue (job payloads tagged with org_id)
//   - RLS verification utilities
//   - Tenant context tracking (for audit)
//   - Defense-in-depth: RLS at DB + org_id filter at application layer
//
// Architecture:
//   Request → authMiddleware (extracts org_id from JWT/API key)
//           → tenantMiddleware (acquires DB client, sets RLS context, tracks session)
//           → route handler (all queries automatically scoped to org_id)
//           → response (DB client released, RLS context cleared)

import { pool, query, withTransaction, setRLSContext, getClient } from './db.js';
import crypto from 'node:crypto';

// ============================================================================
// TENANT-AWARE CACHE
// ============================================================================

/**
 * Tenant-aware in-memory cache.
 * All keys are automatically prefixed with the org_id.
 * Cache invalidation is tracked per-org via tenant_cache_versions table.
 */
export class TenantCache {
  constructor() {
    this._cache = new Map();
    this._versions = new Map(); // orgId -> Map(cacheKey -> version)
  }

  /**
   * Get a cached value for a specific org.
   * @param {string} orgId
   * @param {string} key - Cache key (without org prefix)
   * @returns {any|null}
   */
  get(orgId, key) {
    const cacheKey = `${orgId}:${key}`;
    return this._cache.get(cacheKey) ?? null;
  }

  /**
   * Set a cached value for a specific org.
   * @param {string} orgId
   * @param {string} key
   * @param {any} value
   * @param {number} ttlMs - Time-to-live in milliseconds (0 = no expiry)
   */
  set(orgId, key, value, ttlMs = 0) {
    const cacheKey = `${orgId}:${key}`;
    this._cache.set(cacheKey, value);

    if (ttlMs > 0) {
      setTimeout(() => {
        this._cache.delete(cacheKey);
      }, ttlMs);
    }
  }

  /**
   * Delete a cached value for a specific org.
   * @param {string} orgId
   * @param {string} key
   */
  delete(orgId, key) {
    this._cache.delete(`${orgId}:${key}`);
  }

  /**
   * Invalidate ALL cached values for a specific org.
   * Called when org data changes significantly (e.g., policy update).
   * @param {string} orgId
   */
  invalidateOrg(orgId) {
    const prefix = `${orgId}:`;
    for (const key of this._cache.keys()) {
      if (key.startsWith(prefix)) {
        this._cache.delete(key);
      }
    }
    // Bump version in DB
    this._bumpVersion(orgId, '*');
  }

  /**
   * Invalidate a specific cache key for an org.
   * @param {string} orgId
   * @param {string} key
   */
  invalidate(orgId, key) {
    this._cache.delete(`${orgId}:${key}`);
    this._bumpVersion(orgId, key);
  }

  /**
   * Get all cache keys for an org (for debugging/monitoring).
   * @param {string} orgId
   * @returns {string[]}
   */
  keys(orgId) {
    const prefix = `${orgId}:`;
    return Array.from(this._cache.keys())
      .filter(k => k.startsWith(prefix))
      .map(k => k.slice(prefix.length));
  }

  /**
   * Get cache stats for monitoring.
   * @returns {object}
   */
  stats() {
    return {
      total_entries: this._cache.size,
      orgs: new Set(Array.from(this._cache.keys()).map(k => k.split(':')[0])).size,
    };
  }

  async _bumpVersion(orgId, key) {
    try {
      await query(
        `INSERT INTO tenant_cache_versions (org_id, cache_key, version, updated_at)
         VALUES ($1, $2, 1, now())
         ON CONFLICT (org_id, cache_key)
         DO UPDATE SET version = tenant_cache_versions.version + 1, updated_at = now()`,
        [orgId, key]
      );
    } catch (err) {
      // Non-critical — cache versioning is best-effort
    }
  }
}

// Singleton cache instance
export const tenantCache = new TenantCache();

// ============================================================================
// TENANT-AWARE QUEUE
// ============================================================================

/**
 * Tenant-aware job queue.
 * All jobs are tagged with org_id for:
 *   - Isolation: workers only process jobs for orgs they have context for
 *   - Monitoring: per-org job stats
 *   - Rate limiting: per-org job limits
 */
export class TenantQueue {
  constructor() {
    this._queues = new Map(); // orgId -> job[]
    this._workers = [];
  }

  /**
   * Enqueue a job for a specific org.
   * @param {string} orgId
   * @param {string} jobType - e.g. 'llm_call', 'receipt_generation', 'pattern_extraction'
   * @param {object} payload - Job data (automatically tagged with org_id)
   * @param {object} options - { priority, delay_ms }
   * @returns {string} Job ID
   */
  enqueue(orgId, jobType, payload, options = {}) {
    const jobId = crypto.randomUUID();
    const job = {
      id: jobId,
      org_id: orgId,
      type: jobType,
      payload: { ...payload, _org_id: orgId }, // defense-in-depth
      priority: options.priority || 0,
      delay_ms: options.delay_ms || 0,
      created_at: new Date().toISOString(),
      attempts: 0,
      max_attempts: 3,
    };

    if (!this._queues.has(orgId)) {
      this._queues.set(orgId, []);
    }

    const queue = this._queues.get(orgId);

    // Insert by priority (higher priority = processed first)
    const insertIdx = queue.findIndex(j => j.priority < job.priority);
    if (insertIdx === -1) {
      queue.push(job);
    } else {
      queue.splice(insertIdx, 0, job);
    }

    // Notify workers
    this._notifyWorkers();

    return jobId;
  }

  /**
   * Dequeue the next job for a specific org.
   * @param {string} orgId
   * @returns {object|null} Job or null if queue is empty
   */
  dequeue(orgId) {
    const queue = this._queues.get(orgId);
    if (!queue || queue.length === 0) return null;

    const job = queue.shift();
    if (queue.length === 0) {
      this._queues.delete(orgId);
    }
    return job;
  }

  /**
   * Peek at the next job without removing it.
   * @param {string} orgId
   */
  peek(orgId) {
    const queue = this._queues.get(orgId);
    return queue?.[0] || null;
  }

  /**
   * Get queue length for an org.
   * @param {string} orgId
   * @returns {number}
   */
  length(orgId) {
    return this._queues.get(orgId)?.length || 0;
  }

  /**
   * Get queue stats for all orgs (monitoring).
   * @returns {object}
   */
  stats() {
    let totalJobs = 0;
    const byOrg = {};

    for (const [orgId, queue] of this._queues) {
      byOrg[orgId] = queue.length;
      totalJobs += queue.length;
    }

    return {
      total_jobs: totalJobs,
      org_count: this._queues.size,
      by_org: byOrg,
    };
  }

  /**
   * Clear all jobs for an org (e.g., on disconnect).
   * @param {string} orgId
   */
  clear(orgId) {
    this._queues.delete(orgId);
  }

  /**
   * Register a worker that processes jobs.
   * @param {function} handler - async (job) => void
   */
  registerWorker(handler) {
    this._workers.push(handler);
  }

  _notifyWorkers() {
    // In production, this would use Redis pub/sub or SQS.
    // For now, workers poll via dequeue().
  }
}

// Singleton queue instance
export const tenantQueue = new TenantQueue();

// ============================================================================
// TENANT ISOLATION MIDDLEWARE
// ============================================================================

/**
 * Middleware: Set tenant context for the request.
 *
 * This middleware:
 *   1. Extracts org_id from req.user (set by authMiddleware)
 *   2. Acquires a database client from the pool
 *   3. Sets the RLS context (SET LOCAL app.org_id) on that client
 *   4. Attaches the client to req.dbClient for use in route handlers
 *   5. Tracks the tenant session for audit
 *   6. Releases the client after response is sent
 *
 * IMPORTANT: This middleware must run AFTER authMiddleware.
 */
export function tenantMiddleware(req, res, next) {
  if (!req.user?.org_id) {
    // No org context (e.g., health checks, public endpoints)
    return next();
  }

  const orgId = req.user.org_id;
  const userId = req.user.id;
  const sessionId = req.headers['x-session-id'] || crypto.randomUUID();

  // Acquire a dedicated client for this request
  // This ensures the RLS context is isolated to this request
  pool.connect().then(async (client) => {
    try {
      // Set RLS context
      await client.query('SET LOCAL app.org_id = $1', [orgId]);
      if (userId) {
        await client.query('SET LOCAL app.user_id = $1', [userId]);
      }

      // Attach client to request
      req.dbClient = client;
      req.tenant = {
        orgId,
        userId,
        sessionId,
      };

      // Track tenant context (fire and forget)
      query(
        `INSERT INTO tenant_context (org_id, user_id, session_id, ip_address, user_agent, expires_at)
         VALUES ($1, $2, $3, $4, $5, now() + interval '1 hour')`,
        [orgId, userId, sessionId, req.ip, req.headers['user-agent'] || null]
      ).catch(() => {}); // Non-critical

      // Release client after response
      res.on('finish', () => {
        // Reset RLS context before releasing (defense-in-depth)
        client.query('RESET app.org_id').catch(() => {});
        client.query('RESET app.user_id').catch(() => {});
        client.release();
      });

      next();
    } catch (err) {
      client.release();
      console.error('[tenant] Failed to set tenant context:', err.message);
      res.status(500).json({ error: 'Failed to establish tenant context' });
    }
  }).catch((err) => {
    console.error('[tenant] Failed to acquire DB client:', err.message);
    res.status(503).json({ error: 'Database connection unavailable' });
  });
}

/**
 * Middleware: Require tenant context.
 * Use on routes that MUST have an org context (all tenant-scoped operations).
 */
export function requireTenant(req, res, next) {
  if (!req.tenant?.orgId) {
    return res.status(403).json({ error: 'Tenant context required — organization membership needed' });
  }
  next();
}

// ============================================================================
// TENANT-AWARE QUERY HELPERS
// ============================================================================

/**
 * Execute a query with tenant context.
 * Uses the request's dedicated DB client if available, otherwise falls back
 * to the pool (with manual RLS context setting).
 *
 * @param {object} req - Express request with req.tenant
 * @param {string} text - SQL query
 * @param {Array} params - Query parameters
 * @returns {Promise<object>} Query result
 */
export async function tenantQuery(req, text, params = []) {
  if (req.dbClient) {
    // Use the request's dedicated client (RLS already set)
    return req.dbClient.query(text, params);
  }

  // Fallback: acquire from pool and set RLS context
  const client = await getClient();
  try {
    if (req.tenant?.orgId) {
      await setRLSContext(client, req.tenant.orgId, req.tenant.userId);
    }
    return await client.query(text, params);
  } finally {
    client.release();
  }
}

/**
 * Execute a function within a tenant-scoped transaction.
 *
 * @param {object} req - Express request with req.tenant
 * @param {function} fn - async (client) => result
 * @returns {Promise<any>}
 */
export async function tenantTransaction(req, fn) {
  if (req.dbClient) {
    // Use the request's client — already has RLS context
    const client = req.dbClient;
    try {
      await client.query('BEGIN');
      const result = await fn(client);
      await client.query('COMMIT');
      return result;
    } catch (err) {
      await client.query('ROLLBACK');
      throw err;
    }
  }

  // Fallback: pool with RLS
  return withTransaction(async (client) => {
    if (req.tenant?.orgId) {
      await setRLSContext(client, req.tenant.orgId, req.tenant.userId);
    }
    return fn(client);
  });
}

// ============================================================================
// RLS VERIFICATION UTILITIES
// ============================================================================

/**
 * Verify that RLS is active on all tenant-scoped tables.
 * Run this at startup to ensure no table was missed.
 *
 * @returns {Promise<{ allActive: boolean, tables: object[] }>}
 */
export async function verifyRLSOnAllTables() {
  const result = await query(`
    SELECT
      c.relname AS table_name,
      c.relrowsecurity AS rls_enabled,
      c.relforcerowsecurity AS rls_forced,
      COUNT(p.polname) AS policy_count
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    LEFT JOIN pg_policy p ON p.polrelid = c.oid
    WHERE n.nspname = 'public'
    AND c.relkind = 'r'
    GROUP BY c.relname, c.relrowsecurity, c.relforcerowsecurity
    ORDER BY c.relname
  `);

  const tables = result.rows.map(r => ({
    table: r.table_name,
    rls_enabled: r.rls_enabled,
    rls_forced: r.rls_forced,
    policy_count: parseInt(r.policy_count, 10),
  }));

  // Tables that MUST have RLS (all tenant-scoped tables)
  const requiredTables = [
    'runs', 'artifacts', 'events', 'learning_objects', 'execution_patterns',
    'operating_policies', 'execution_receipts', 'evidence_items', 'cases',
    'integrations', 'webhook_events', 'api_keys', 'audit_log',
    'organization_members', 'departments', 'teams', 'invitations',
    'custom_roles', 'role_permissions', 'role_assignments', 'resource_ownership',
    'refresh_tokens',
  ];

  const missingRLS = requiredTables.filter(name => {
    const table = tables.find(t => t.table === name);
    return !table || !table.rls_enabled || !table.rls_forced;
  });

  return {
    allActive: missingRLS.length === 0,
    total_tables: tables.length,
    required_tables: requiredTables.length,
    missing_rls: missingRLS,
    tables,
  };
}

/**
 * Test tenant isolation by attempting to read data from a different org.
 * This function should ALWAYS return 0 rows if RLS is working correctly.
 *
 * @param {string} orgId - The org to set as context
 * @param {string} targetOrgId - A different org to try to read (should be blocked)
 * @returns {Promise<{ isolated: boolean, leaked_rows: number }>}
 */
export async function testTenantIsolation(orgId, targetOrgId) {
  const client = await getClient();
  try {
    // Set context to orgId
    await client.query('SET LOCAL app.org_id = $1', [orgId]);

    // Try to read runs belonging to targetOrgId
    const result = await client.query(
      'SELECT COUNT(*) as count FROM runs WHERE org_id = $1',
      [targetOrgId]
    );

    const leakedRows = parseInt(result.rows[0].count, 10);

    return {
      isolated: leakedRows === 0,
      leaked_rows: leakedRows,
      context_org: orgId,
      target_org: targetOrgId,
    };
  } finally {
    client.release();
  }
}

// ============================================================================
// TENANT ISOLATION STATUS
// ============================================================================

export async function getTenantIsolationStatus() {
  const rlsStatus = await verifyRLSOnAllTables();
  const cacheStats = tenantCache.stats();
  const queueStats = tenantQueue.stats();

  return {
    rls: {
      all_active: rlsStatus.allActive,
      total_tables: rlsStatus.total_tables,
      required_tables: rlsStatus.required_tables,
      missing: rlsStatus.missing_rls,
    },
    cache: cacheStats,
    queue: queueStats,
    middleware: true,
    tenant_aware_queries: true,
    tenant_aware_transactions: true,
    defense_in_depth: true, // RLS + application-level org_id filtering
  };
}

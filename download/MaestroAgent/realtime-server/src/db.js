// src/db.js — PostgreSQL connection pool.
//
// Production database layer. Replaces JSONL file storage with
// PostgreSQL 16. Provides:
//   - Connection pooling (pg.Pool)
//   - Query helper with slow-query logging
//   - Transaction helper (BEGIN/COMMIT/ROLLBACK)
//   - Row-Level Security context setter (per-request org isolation)
//
// Environment variables:
//   DATABASE_URL — postgresql://user:pass@host:5432/dbname
//   DB_POOL_MAX  — max connections (default: 20)
//   DB_STATEMENT_TIMEOUT — query timeout in ms (default: 30000)

import pg from 'pg';

const { Pool } = pg;

const pool = new Pool({
  connectionString: process.env.DATABASE_URL || 'postgresql://localhost:5432/maestro',
  max: parseInt(process.env.DB_POOL_MAX || '20', 10),
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 5000,
  statement_timeout: parseInt(process.env.DB_STATEMENT_TIMEOUT || '30000', 10),
});

pool.on('error', (err, client) => {
  console.error('[db] unexpected error on idle client', err);
  process.exit(-1);
});

/**
 * Execute a query with parameters.
 * @param {string} text - SQL query
 * @param {Array} params - Query parameters
 * @returns {Promise<pg.QueryResult>}
 */
export async function query(text, params) {
  const start = Date.now();
  try {
    const result = await pool.query(text, params);
    const duration = Date.now() - start;
    if (duration > 200) {
      console.warn('[db] slow query', {
        text: text.slice(0, 100),
        duration: `${duration}ms`,
        rows: result.rowCount,
      });
    }
    return result;
  } catch (err) {
    const duration = Date.now() - start;
    console.error('[db] query error', {
      text: text.slice(0, 100),
      duration: `${duration}ms`,
      error: err.message,
    });
    throw err;
  }
}

/**
 * Execute a function within a database transaction.
 * Automatically commits on success, rolls back on error.
 * @param {(client: pg.PoolClient) => Promise<T>} fn
 * @returns {Promise<T>}
 */
export async function withTransaction(fn) {
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const result = await fn(client);
    await client.query('COMMIT');
    return result;
  } catch (err) {
    await client.query('ROLLBACK');
    throw err;
  } finally {
    client.release();
  }
}

/**
 * Get a client from the pool (for multi-query sequences).
 * Remember to call client.release().
 * @returns {Promise<pg.PoolClient>}
 */
export async function getClient() {
  return pool.connect();
}

/**
 * Set the RLS (Row-Level Security) context for the current connection.
 * Must be called within a transaction or session.
 * @param {pg.PoolClient} client
 * @param {string} orgId - Organization UUID
 * @param {string|null} userId - User UUID (optional, for audit)
 */
export async function setRLSContext(client, orgId, userId = null) {
  await client.query('SET LOCAL app.org_id = $1', [orgId]);
  if (userId) {
    await client.query('SET LOCAL app.user_id = $1', [userId]);
  }
}

/**
 * Check database connectivity.
 * @returns {Promise<boolean>}
 */
export async function healthCheck() {
  try {
    const result = await query('SELECT 1 as ok');
    return result.rows[0].ok === 1;
  } catch {
    return false;
  }
}

/**
 * Close the pool (for testing / shutdown).
 */
export async function closePool() {
  await pool.end();
}

export { pool };

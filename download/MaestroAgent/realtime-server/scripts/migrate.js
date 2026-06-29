// scripts/migrate.js — Database migration runner.
//
// Usage:
//   node scripts/migrate.js                    # Run all pending migrations
//   node scripts/migrate.js --status           # Show migration status
//
// Migrations are SQL files in the migrations/ directory, numbered sequentially.
// They are tracked in a `schema_migrations` table.

import { promises as fs } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { query, withTransaction, closePool } from '../src/db.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const MIGRATIONS_DIR = path.join(__dirname, '..', 'migrations');

async function ensureMigrationsTable() {
  await query(`
    CREATE TABLE IF NOT EXISTS schema_migrations (
      filename    TEXT PRIMARY KEY,
      executed_at TIMESTAMPTZ DEFAULT now()
    )
  `);
}

async function getExecutedMigrations() {
  const result = await query('SELECT filename FROM schema_migrations ORDER BY filename');
  return result.rows.map(r => r.filename);
}

async function getPendingMigrations() {
  const files = await fs.readdir(MIGRATIONS_DIR);
  const sqlFiles = files.filter(f => f.endsWith('.sql')).sort();
  const executed = await getExecutedMigrations();
  return sqlFiles.filter(f => !executed.includes(f));
}

async function runMigration(filename) {
  const filepath = path.join(MIGRATIONS_DIR, filename);
  const sql = await fs.readFile(filepath, 'utf8');

  await withTransaction(async (client) => {
    await client.query(sql);
    await client.query('INSERT INTO schema_migrations (filename) VALUES ($1)', [filename]);
  });

  console.log(`[migrate] done: ${filename}`);
}

async function runAll() {
  await ensureMigrationsTable();
  const pending = await getPendingMigrations();

  if (pending.length === 0) {
    console.log('[migrate] No pending migrations.');
    return;
  }

  console.log(`[migrate] ${pending.length} pending migration(s):`);
  for (const file of pending) {
    await runMigration(file);
  }
  console.log(`[migrate] All migrations complete.`);
}

async function showStatus() {
  await ensureMigrationsTable();
  const pending = await getPendingMigrations();
  const executed = await getExecutedMigrations();

  console.log('\nExecuted migrations:');
  for (const f of executed) console.log(`  done: ${f}`);

  console.log('\nPending migrations:');
  for (const f of pending) console.log(`  pending: ${f}`);
}

async function main() {
  const args = process.argv.slice(2);

  try {
    if (args.includes('--status')) {
      await showStatus();
    } else {
      await runAll();
    }
  } catch (err) {
    console.error('[migrate] Error:', err.message);
    process.exit(1);
  } finally {
    await closePool();
  }
}

main();

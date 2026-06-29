// scripts/restore.js — PostgreSQL restore from backup.
//
// Usage:
//   node scripts/restore.js ./backups/maestro-2026-06-27.sql
//
// Requires psql to be installed and on PATH.
// WARNING: This overwrites all data in the target database.
// Requires confirmation unless --force flag is passed.

import { execSync } from 'node:child_process';
import readline from 'node:readline';
import { promises as fs } from 'node:fs';

async function confirm(message) {
  if (process.argv.includes('--force')) return true;
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise(resolve => {
    rl.question(message, answer => {
      rl.close();
      resolve(answer.toLowerCase() === 'yes' || answer.toLowerCase() === 'y');
    });
  });
}

async function restore() {
  const backupPath = process.argv[2];
  if (!backupPath) {
    console.error('[restore] Usage: node scripts/restore.js <backup-file.sql> [--force]');
    process.exit(1);
  }

  try {
    await fs.access(backupPath);
  } catch {
    console.error(`[restore] File not found: ${backupPath}`);
    process.exit(1);
  }

  const dbUrl = process.env.DATABASE_URL;
  if (!dbUrl) {
    console.error('[restore] DATABASE_URL not set');
    process.exit(1);
  }

  const ok = await confirm(`[restore] This will OVERWRITE all data in ${dbUrl}. Continue? (yes/no): `);
  if (!ok) {
    console.log('[restore] Cancelled.');
    process.exit(0);
  }

  console.log(`[restore] Restoring from ${backupPath}...`);

  const url = new URL(dbUrl);
  const env = { ...process.env, PGPASSWORD: url.password };

  try {
    // Drop and recreate schema (clean slate)
    const dropCmd = `psql --host=${url.hostname} --port=${url.port || 5432} --username=${url.username} --dbname=${url.pathname.slice(1)} -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"`;
    execSync(dropCmd, { env, stdio: 'inherit' });

    // Restore from backup
    const restoreCmd = `psql --host=${url.hostname} --port=${url.port || 5432} --username=${url.username} --dbname=${url.pathname.slice(1)} --file="${backupPath}"`;
    execSync(restoreCmd, { env, stdio: 'inherit' });

    console.log('[restore] Complete.');
  } catch (err) {
    console.error('[restore] Failed:', err.message);
    process.exit(1);
  }
}

restore();

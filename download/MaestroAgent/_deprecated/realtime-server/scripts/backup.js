// scripts/backup.js — PostgreSQL backup using pg_dump.
//
// Usage:
//   node scripts/backup.js                    # Backup to ./backups/maestro-YYYY-MM-DD.sql
//   node scripts/backup.js /custom/path.sql   # Backup to custom path
//
// Requires pg_dump to be installed and on PATH.
// Uses DATABASE_URL for connection.

import { execSync } from 'node:child_process';
import { promises as fs } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

async function backup() {
  const dbUrl = process.env.DATABASE_URL;
  if (!dbUrl) {
    console.error('[backup] DATABASE_URL not set');
    process.exit(1);
  }

  const backupDir = path.join(__dirname, '..', 'backups');
  await fs.mkdir(backupDir, { recursive: true });

  const date = new Date().toISOString().split('T')[0];
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-').split('T')[1];
  const backupPath = process.argv[2] || path.join(backupDir, `maestro-${date}-${timestamp.slice(0, 8)}.sql`);

  console.log(`[backup] Starting backup to ${backupPath}...`);

  try {
    // Parse DATABASE_URL for pg_dump
    const url = new URL(dbUrl);
    const env = {
      ...process.env,
      PGPASSWORD: url.password,
    };

    const cmd = `pg_dump --host=${url.hostname} --port=${url.port || 5432} --username=${url.username} --dbname=${url.pathname.slice(1)} --format=plain --no-owner --no-privileges --file="${backupPath}"`;

    execSync(cmd, { env, stdio: 'inherit' });

    const stats = await fs.stat(backupPath);
    const sizeMB = (stats.size / 1024 / 1024).toFixed(2);

    console.log(`[backup] Complete: ${backupPath} (${sizeMB} MB)`);

    // Keep only last 30 backups
    const files = await fs.readdir(backupDir);
    const sqlFiles = files.filter(f => f.endsWith('.sql')).sort();
    if (sqlFiles.length > 30) {
      const toDelete = sqlFiles.slice(0, sqlFiles.length - 30);
      for (const f of toDelete) {
        await fs.unlink(path.join(backupDir, f));
        console.log(`[backup] Deleted old backup: ${f}`);
      }
    }
  } catch (err) {
    console.error('[backup] Failed:', err.message);
    process.exit(1);
  }
}

backup();

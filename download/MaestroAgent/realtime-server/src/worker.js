// src/worker.js — Background worker process.
//
// Consumes jobs from the tenant queue (or Redis queue in production).
// Handles: LLM calls, receipt generation, pattern extraction,
// integration sync, backup jobs.
//
// In production, run multiple worker instances for horizontal scaling.
// Each worker polls the queue, processes jobs, and acks on completion.

import { tenantQueue } from './tenant.js';

const WORKER_ID = `worker-${process.pid}`;
const POLL_INTERVAL_MS = 1000;
const MAX_CONCURRENT_JOBS = parseInt(process.env.WORKER_MAX_CONCURRENT || '5', 10);

console.log(`[worker] Starting ${WORKER_ID} (max concurrent: ${MAX_CONCURRENT_JOBS})`);

// Track active jobs for graceful shutdown
const activeJobs = new Set();
let shuttingDown = false;

async function processJob(job) {
  const { id, org_id, type, payload } = job;
  console.log(`[worker] Processing ${type} job ${id} for org ${org_id}`);

  try {
    switch (type) {
      case 'llm_call':
        // LLM calls are handled inline by the API server (streaming).
        // Worker handles non-streaming LLM calls (e.g., conductor learn phase).
        break;

      case 'receipt_generation':
        // Generate execution receipt after run completes
        break;

      case 'pattern_extraction':
        // Extract patterns from completed learning objects
        break;

      case 'integration_sync':
        // Sync data from external integrations (Jira, GitHub, Slack)
        break;

      case 'backup':
        // Create database backup
        break;

      case 'cleanup':
        // Clean up old data (expired tokens, old audit logs, etc.)
        break;

      default:
        console.warn(`[worker] Unknown job type: ${type}`);
    }
  } catch (err) {
    console.error(`[worker] Job ${id} failed:`, err.message);
    // Re-queue with exponential backoff (in production, use Redis RPOPLPUSH)
  }
}

async function pollLoop() {
  while (!shuttingDown) {
    if (activeJobs.size >= MAX_CONCURRENT_JOBS) {
      await sleep(100);
      continue;
    }

    // Check all orgs for jobs (in production, use Redis BLPOP)
    // For now, this is a placeholder that would integrate with the tenant queue
    await sleep(POLL_INTERVAL_MS);
  }
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// Graceful shutdown
async function shutdown(signal) {
  console.log(`[worker] ${signal} received, shutting down gracefully...`);
  shuttingDown = true;

  // Wait for active jobs to complete (max 60 seconds)
  const start = Date.now();
  while (activeJobs.size > 0 && Date.now() - start < 60000) {
    console.log(`[worker] Waiting for ${activeJobs.size} active jobs...`);
    await sleep(1000);
  }

  console.log('[worker] Shutdown complete');
  process.exit(0);
}

process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));

// Start polling
pollLoop().catch(err => {
  console.error('[worker] Fatal error:', err);
  process.exit(1);
});

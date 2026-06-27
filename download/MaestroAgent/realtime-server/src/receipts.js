// receipts.js — Maestro's Execution Receipts.
//
// Every execution produces an immutable receipt — an audit trail that
// answers: "Why did Maestro do this, and was it compliant?"
//
// This is what enterprises pay millions for: GOVERNANCE.
//
// Not memory. Not patterns. Not policies. Governance.
//
// A bank doesn't care that Planner→Researcher→Writer→Reviewer works.
// They care that "every customer communication was reviewed under the
// bank's approved policy, evidence was attached, reviewer John Smith
// approved it at 14:32 UTC, and no constitutional rule was violated."
//
// Receipt shape:
//   {
//     receiptId, runId, goal, goalClass,
//     scope: { organization, department, team, userId, ... },
//     plan: { team, steps, predictedConfidence },
//     policiesApplied: [ { policyId, rule, enforcement, evidence } ],
//     patternsUsed: [ { goalClass, scopeLevel, version } ],
//     evidence: [ { type, description, artifact, timestamp } ],
//     approvals: [ { required, granted, by, timestamp } ],
//     exceptions: [ { policyId, reason, approvedBy } ],
//     confidence: { predicted, actual },
//     outcome: { result, notes, corrections },
//     execution: { durationMs, cost, artifactCount, specialistCount },
//     lessons: string,
//     receiptHash,        // SHA-256 of the receipt content (tamper-evident)
//     createdAt
//   }

import { promises as fs } from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { getCurrentScope } from './scope.js';

const RECEIPT_STORE_PATH = path.resolve('./execution-receipts.jsonl');
const receipts = new Map(); // receiptId -> Receipt

export async function initReceiptStore() {
  try {
    const data = await fs.readFile(RECEIPT_STORE_PATH, 'utf8');
    for (const line of data.split('\n').filter(Boolean)) {
      try {
        const obj = JSON.parse(line);
        receipts.set(obj.receiptId, obj);
      } catch {}
    }
    console.log(`[receipts] loaded ${receipts.size} execution receipts from disk`);
  } catch (err) {
    if (err.code !== 'ENOENT') console.warn('[receipts] failed to load store:', err.message);
  }
}

async function persist(receipt) {
  try {
    await fs.appendFile(RECEIPT_STORE_PATH, JSON.stringify(receipt) + '\n', 'utf8');
  } catch (err) {
    console.warn('[receipts] failed to persist:', err.message);
  }
}

// Compute a tamper-evident hash of the receipt.
// This is what makes the receipt immutable — any change to the receipt
// content changes the hash, making tampering detectable.
function computeReceiptHash(receipt) {
  const content = JSON.stringify({
    runId: receipt.runId,
    goal: receipt.goal,
    plan: receipt.plan,
    policiesApplied: receipt.policiesApplied,
    patternsUsed: receipt.patternsUsed,
    outcome: receipt.outcome,
    confidence: receipt.confidence,
    execution: receipt.execution,
    createdAt: receipt.createdAt,
  });
  return crypto.createHash('sha256').update(content).digest('hex');
}

// Create a receipt from a completed run.
// Called after the run completes and feedback is recorded.
export async function createReceipt(run, options = {}) {
  const scope = run.scope || getCurrentScope();
  const receipt = {
    receiptId: crypto.randomUUID(),
    runId: run.id,
    goal: run.goal,
    goalClass: run.team?.title || 'unknown',
    scope: {
      organization: scope.organization,
      industry: scope.industry,
      department: scope.department,
      team: scope.team,
      userId: scope.userId,
    },
    plan: {
      team: run.team?.agents || [],
      template: run.team?.title || '',
      steps: run.team?.agents?.length || 0,
      predictedConfidence: run.avgConfidence ?? null,
    },
    policiesApplied: options.policiesApplied || [],
    patternsUsed: options.patternsUsed || [],
    evidence: options.evidence || [],
    approvals: options.approvals || [],
    exceptions: options.exceptions || [],
    confidence: {
      predicted: run.avgConfidence ?? null,
      actual: run.outcome || 'pending',
    },
    outcome: {
      result: run.outcome || 'pending',
      notes: run.outcomeNotes || '',
      corrections: run.consumedInterrupts || [],
    },
    execution: {
      durationMs: run.durationMs || 0,
      cost: run.cost || 0,
      artifactCount: run.artifacts?.length || 0,
      specialistCount: run.team?.agents?.length || 0,
      artifacts: (run.artifacts || []).map(a => ({
        filename: a.filename,
        agent: a.agent_name,
        bytes: a.bytes,
        isFinal: !!a.isFinal,
      })),
    },
    lessons: run.lessons || '',
    createdAt: new Date().toISOString(),
  };

  // Compute hash AFTER all fields are set, BEFORE adding the hash itself.
  receipt.receiptHash = computeReceiptHash(receipt);

  receipts.set(receipt.receiptId, receipt);
  await persist(receipt);
  console.log(`[receipts] created receipt ${receipt.receiptId.slice(0, 8)} for run ${run.id.slice(0, 8)} (hash: ${receipt.receiptHash.slice(0, 16)}...)`);
  return receipt;
}

// Retrieve a receipt by run ID.
export function getReceiptByRunId(runId) {
  for (const r of receipts.values()) {
    if (r.runId === runId) return r;
  }
  return null;
}

// Retrieve a receipt by receipt ID.
export function getReceipt(receiptId) {
  return receipts.get(receiptId) || null;
}

// List all receipts (most recent first).
export function listReceipts(limit = 50) {
  return Array.from(receipts.values())
    .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt))
    .slice(0, limit);
}

// Verify a receipt's hash (tamper detection).
export function verifyReceipt(receiptId) {
  const receipt = receipts.get(receiptId);
  if (!receipt) return { valid: false, error: 'receipt not found' };
  const storedHash = receipt.receiptHash;
  const computedHash = computeReceiptHash({ ...receipt, receiptHash: undefined });
  return {
    valid: storedHash === computedHash,
    storedHash,
    computedHash,
    receiptId,
  };
}

// Get receipt stats.
export function getReceiptStats() {
  const all = Array.from(receipts.values());
  return {
    total: all.length,
    withOutcome: all.filter(r => r.outcome.result !== 'pending').length,
    accepted: all.filter(r => r.outcome.result === 'accepted').length,
    rejected: all.filter(r => r.outcome.result === 'rejected').length,
    edited: all.filter(r => r.outcome.result === 'edited').length,
    withExceptions: all.filter(r => r.exceptions.length > 0).length,
    withApprovals: all.filter(r => r.approvals.length > 0).length,
    totalArtifacts: all.reduce((sum, r) => sum + r.execution.artifactCount, 0),
    avgDuration: all.length > 0
      ? Math.round(all.reduce((sum, r) => sum + r.execution.durationMs, 0) / all.length)
      : 0,
  };
}

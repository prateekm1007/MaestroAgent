// evidence.js — Maestro's Evidence, Cases & Precedents layer.
//
// This is the layer above Execution Receipts.
//
// A Receipt is an audit trail — it records WHAT happened.
// Evidence is EXTRACTED from receipts — it's the reusable proof.
// A Case is a collection of evidence around a specific governance decision.
// A Precedent is what emerges when similar cases recur — the planner
// reasons about precedents before executing.
//
// This is how legal systems work:
//   Receipt (what happened) → Evidence (the proof) → Case (the decision) →
//   Precedent (future reasoning)
//
// ACTIVE GOVERNANCE:
//   Instead of: Policy says X → planner reads X → hopefully follows X
//   We do:      Planner asks "what evidence do similar past cases have?" →
//               reasons about whether this execution will satisfy governance →
//               executes with evidence-aware confidence
//
// Evidence shape:
//   {
//     id, receiptId, runId,
//     type: 'review' | 'approval' | 'test' | 'artifact' | 'signoff' | 'exception',
//     description,           // "Security review completed"
//     reviewer,              // who/what provided this evidence
//     artifacts: [...],      // linked artifact filenames
//     policyAddressed,       // which policy this evidence satisfies
//     timestamp,
//     hash,                  // links back to receipt hash (tamper-evident)
//   }
//
// Case shape:
//   {
//     id,
//     goal, goalClass,
//     evidence: [evidenceIds],
//     policiesAddressed: [...],
//     outcome: 'approved' | 'blocked' | 'exception_granted',
//     precedentStrength: 0-1,  // grows when similar cases recur
//     createdAt
//   }
//
// Precedent shape (emerges from cases):
//   {
//     id,
//     goalClass,
//     pattern: "For [goal class], [evidence type] is typically required",
//     caseCount,              // how many cases contributed
//     successRate,            // % of cases with outcome='approved'
//     typicalEvidence: [...], // most common evidence types
//     scope, scopeKey, scopeLevel
//   }

import { promises as fs } from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { getCurrentScope, getScopeHierarchy, scopeKey } from './scope.js';

const EVIDENCE_STORE_PATH = path.resolve('./evidence.jsonl');
const CASE_STORE_PATH = path.resolve('./cases.jsonl');
const PRECEDENT_STORE_PATH = path.resolve('./precedents.jsonl');

const evidence = new Map();   // id -> Evidence
const cases = new Map();      // id -> Case
const precedents = new Map(); // id -> Precedent

export async function initEvidenceStore() {
  try {
    const data = await fs.readFile(EVIDENCE_STORE_PATH, 'utf8');
    for (const line of data.split('\n').filter(Boolean)) {
      try {
        const obj = JSON.parse(line);
        evidence.set(obj.id, obj);
      } catch {}
    }
    console.log(`[evidence] loaded ${evidence.size} evidence items from disk`);
  } catch (err) {
    if (err.code !== 'ENOENT') console.warn('[evidence] failed to load:', err.message);
  }

  try {
    const data = await fs.readFile(CASE_STORE_PATH, 'utf8');
    for (const line of data.split('\n').filter(Boolean)) {
      try {
        const obj = JSON.parse(line);
        cases.set(obj.id, obj);
      } catch {}
    }
    console.log(`[evidence] loaded ${cases.size} cases from disk`);
  } catch (err) {
    if (err.code !== 'ENOENT') console.warn('[evidence] failed to load cases:', err.message);
  }

  try {
    const data = await fs.readFile(PRECEDENT_STORE_PATH, 'utf8');
    for (const line of data.split('\n').filter(Boolean)) {
      try {
        const obj = JSON.parse(line);
        precedents.set(obj.id, obj);
      } catch {}
    }
    console.log(`[evidence] loaded ${precedents.size} precedents from disk`);
  } catch (err) {
    if (err.code !== 'ENOENT') console.warn('[evidence] failed to load precedents:', err.message);
  }
}

async function persistEvidence(ev) {
  try { await fs.appendFile(EVIDENCE_STORE_PATH, JSON.stringify(ev) + '\n', 'utf8'); }
  catch (err) { console.warn('[evidence] persist failed:', err.message); }
}

async function persistCase(c) {
  try { await fs.appendFile(CASE_STORE_PATH, JSON.stringify(c) + '\n', 'utf8'); }
  catch (err) { console.warn('[evidence] case persist failed:', err.message); }
}

async function persistPrecedent(p) {
  try { await fs.appendFile(PRECEDENT_STORE_PATH, JSON.stringify(p) + '\n', 'utf8'); }
  catch (err) { console.warn('[evidence] precedent persist failed:', err.message); }
}

// Extract evidence from a completed receipt.
// Each artifact, each policy addressed, each approval becomes an evidence item.
export async function extractEvidenceFromReceipt(receipt) {
  if (!receipt) return [];
  const extracted = [];

  // Evidence from artifacts — each deliverable is evidence of work done.
  for (const artifact of receipt.execution?.artifacts || []) {
    const ev = {
      id: crypto.randomUUID(),
      receiptId: receipt.receiptId,
      runId: receipt.runId,
      type: 'artifact',
      description: `${artifact.agent} produced ${artifact.filename}`,
      reviewer: artifact.agent,
      artifacts: [artifact.filename],
      policyAddressed: null,
      timestamp: receipt.createdAt,
      hash: receipt.receiptHash,
      scope: receipt.scope,
    };
    evidence.set(ev.id, ev);
    await persistEvidence(ev);
    extracted.push(ev);
  }

  // Evidence from policies applied — each policy that was satisfied.
  for (const policy of receipt.policiesApplied || []) {
    const ev = {
      id: crypto.randomUUID(),
      receiptId: receipt.receiptId,
      runId: receipt.runId,
      type: 'review',
      description: `Policy addressed: ${policy.rule}`,
      reviewer: 'Maestro Governance Engine',
      artifacts: [],
      policyAddressed: policy.rule,
      policyEnforcement: policy.enforcement,
      timestamp: receipt.createdAt,
      hash: receipt.receiptHash,
      scope: receipt.scope,
    };
    evidence.set(ev.id, ev);
    await persistEvidence(ev);
    extracted.push(ev);
  }

  // Evidence from approvals (or lack thereof).
  for (const approval of receipt.approvals || []) {
    const ev = {
      id: crypto.randomUUID(),
      receiptId: receipt.receiptId,
      runId: receipt.runId,
      type: approval.granted ? 'approval' : 'pending_approval',
      description: `Approval ${approval.granted ? 'granted' : 'pending'}: ${approval.control}`,
      reviewer: approval.reviewer,
      artifacts: [],
      policyAddressed: approval.control,
      timestamp: approval.timestamp || receipt.createdAt,
      hash: receipt.receiptHash,
      scope: receipt.scope,
    };
    evidence.set(ev.id, ev);
    await persistEvidence(ev);
    extracted.push(ev);
  }

  // Evidence from exceptions.
  for (const exception of receipt.exceptions || []) {
    const ev = {
      id: crypto.randomUUID(),
      receiptId: receipt.receiptId,
      runId: receipt.runId,
      type: 'exception',
      description: `Exception: ${exception.policyId} — ${exception.reason}`,
      reviewer: exception.approvedBy || 'unauthorized',
      artifacts: [],
      policyAddressed: exception.policyId,
      timestamp: receipt.createdAt,
      hash: receipt.receiptHash,
      scope: receipt.scope,
    };
    evidence.set(ev.id, ev);
    await persistEvidence(ev);
    extracted.push(ev);
  }

  return extracted;
}

// Create a Case from a receipt + its evidence.
// A case represents "here's a governance decision that was made, with evidence."
export async function createCase(receipt, evidenceItems) {
  const goalClass = receipt.goalClass || 'unknown';
  const c = {
    id: crypto.randomUUID(),
    receiptId: receipt.receiptId,
    runId: receipt.runId,
    goal: receipt.goal,
    goalClass,
    evidence: (evidenceItems || []).map(e => e.id),
    evidenceTypes: (evidenceItems || []).map(e => e.type),
    policiesAddressed: (receipt.policiesApplied || []).map(p => p.rule),
    outcome: receipt.outcome?.result || 'pending',
    scope: receipt.scope,
    scopeKey: receipt.scope ? scopeKey({ level: 'company', ...receipt.scope }) : 'global',
    createdAt: new Date().toISOString(),
    precedentStrength: 0, // will be updated when precedents are recalculated
  };
  cases.set(c.id, c);
  await persistCase(c);

  // Update precedents based on this new case.
  await updatePrecedents(c);

  return c;
}

// Update precedents based on accumulated cases.
// When similar cases recur, a precedent emerges.
async function updatePrecedents(newCase) {
  const goalClass = newCase.goalClass;
  const scope = newCase.scope || {};
  const hierarchy = getScopeHierarchy({ ...scope, level: 'individual' });

  // Find or create a precedent for this goal class at each scope level.
  for (const scopeLvl of hierarchy) {
    const sKey = scopeKey(scopeLvl);
    let precedent = null;
    for (const p of precedents.values()) {
      if (p.goalClass === goalClass && p.scopeKey === sKey) {
        precedent = p;
        break;
      }
    }

    // Find all cases at this scope level for this goal class.
    const relevantCases = Array.from(cases.values()).filter(c => {
      if (c.goalClass !== goalClass) return false;
      const caseScope = { ...c.scope, level: 'individual' };
      const caseHierarchy = getScopeHierarchy(caseScope);
      return caseHierarchy.some(l => scopeKey(l) === sKey);
    });

    if (relevantCases.length === 0) continue;

    if (!precedent) {
      precedent = {
        id: crypto.randomUUID(),
        goalClass,
        scopeKey: sKey,
        scopeLevel: scopeLvl.level,
        caseIds: [],
        caseCount: 0,
        successRate: null,
        typicalEvidence: [],
        pattern: '',
        createdAt: new Date().toISOString(),
        lastUpdated: new Date().toISOString(),
      };
      precedents.set(precedent.id, precedent);
    }

    // Update precedent with aggregated case data.
    precedent.caseIds = relevantCases.map(c => c.id);
    precedent.caseCount = relevantCases.length;

    const approved = relevantCases.filter(c => c.outcome === 'accepted' || c.outcome === 'approved').length;
    precedent.successRate = precedent.caseCount > 0 ? approved / precedent.caseCount : null;

    // Find most common evidence types.
    const evidenceTypeCounts = {};
    for (const c of relevantCases) {
      for (const et of c.evidenceTypes || []) {
        evidenceTypeCounts[et] = (evidenceTypeCounts[et] || 0) + 1;
      }
    }
    precedent.typicalEvidence = Object.entries(evidenceTypeCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([type, count]) => ({ type, count }));

    // Generate pattern description.
    const evidenceStr = precedent.typicalEvidence.length > 0
      ? precedent.typicalEvidence.map(e => e.type).join(', ')
      : 'no typical evidence yet';
    precedent.pattern = `For ${goalClass} at ${scopeLvl.level} scope, typical evidence includes: ${evidenceStr}. Success rate: ${precedent.successRate !== null ? Math.round(precedent.successRate * 100) + '%' : 'unknown'} across ${precedent.caseCount} case${precedent.caseCount > 1 ? 's' : ''}.`;

    precedent.lastUpdated = new Date().toISOString();
    await persistPrecedent(precedent);
  }
}

// Retrieve precedents for a goal — cascades through scope hierarchy.
// This is ACTIVE GOVERNANCE — the planner reasons about past cases
// before executing.
export function retrievePrecedents(goal, goalClass, scope = null) {
  const useScope = scope || getCurrentScope();
  const hierarchy = getScopeHierarchy(useScope);
  const results = [];

  for (const scopeLvl of hierarchy) {
    const sKey = scopeKey(scopeLvl);
    for (const p of precedents.values()) {
      if (p.goalClass === goalClass && p.scopeKey === sKey && p.caseCount > 0) {
        results.push(p);
        break;
      }
    }
  }
  return results;
}

// Format precedents as context for the conductor.
// This is what makes governance ACTIVE — the planner reasons:
// "Similar past cases typically required X evidence and had Y% success rate."
export function formatPrecedentContext(precedentsArr) {
  if (!precedentsArr || precedentsArr.length === 0) return '';
  const blocks = precedentsArr.map(p => {
    const evidenceStr = p.typicalEvidence.length > 0
      ? p.typicalEvidence.map(e => `${e.type} (${e.count}×)`).join(', ')
      : 'none yet';
    return `--- Precedent [${p.scopeLevel}] for ${p.goalClass} ---
${p.pattern}
Typical evidence: ${evidenceStr}
Cases: ${p.caseCount}
---`;
  });
  return blocks.join('\n\n');
}

// Get stats.
export function getEvidenceStats() {
  return {
    evidence: {
      total: evidence.size,
      byType: Array.from(evidence.values()).reduce((acc, e) => {
        acc[e.type] = (acc[e.type] || 0) + 1;
        return acc;
      }, {}),
    },
    cases: {
      total: cases.size,
      approved: Array.from(cases.values()).filter(c => c.outcome === 'accepted' || c.outcome === 'approved').length,
      blocked: Array.from(cases.values()).filter(c => c.outcome === 'blocked').length,
    },
    precedents: {
      total: precedents.size,
      byScope: Array.from(precedents.values()).reduce((acc, p) => {
        acc[p.scopeLevel] = (acc[p.scopeLevel] || 0) + 1;
        return acc;
      }, {}),
    },
  };
}

export function listEvidence(limit = 50) {
  return Array.from(evidence.values())
    .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
    .slice(0, limit);
}

export function listCases(limit = 50) {
  return Array.from(cases.values())
    .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt))
    .slice(0, limit);
}

export function listPrecedents() {
  return Array.from(precedents.values())
    .sort((a, b) => b.caseCount - a.caseCount);
}

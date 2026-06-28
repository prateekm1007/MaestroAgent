// cpr.js — Customer Proof Rate.
//
// The ONE external metric. Everything else feeds into this.
//
// > Percentage of design partners that achieve their promised outcome
//   within 90 days.
//
// Example:
//   5 partners
//   4 achieve ≥15% cycle time reduction
//   CPR = 80%
//
// Investors understand it. Customers understand it. Employees understand it.
//
// CPR is the only metric that matters externally. OED, TTV, COI, EII —
// they're all useful internally, but CPR is what goes in the pitch deck,
// the board update, and the homepage.

import { listReceipts } from './receipts.js';
import { computeMetrics } from './metrics.js';

// Promised outcomes per design partner.
// Each design partner has a promised outcome (e.g., "15% cycle time reduction").
// CPR measures what % of partners achieved their promised outcome.
const partnerPromises = new Map(); // orgId -> { promisedOutcome, baseline, startDate }

export function setPartnerPromise(orgId, promise) {
  partnerPromises.set(orgId, {
    orgId,
    promisedOutcome: promise.promisedOutcome || '15% cycle time reduction',
    targetReduction: promise.targetReduction || 15, // percentage
    baseline: promise.baseline || null,
    startDate: promise.startDate || new Date().toISOString(),
    daysToProve: promise.daysToProve || 90,
  });
}

// Compute CPR across all design partners.
export function computeCPR() {
  if (partnerPromises.size === 0) {
    return {
      available: false,
      message: 'No design partner promises set. Call setPartnerPromise for each partner.',
      cpr: null,
    };
  }

  const partners = Array.from(partnerPromises.values());
  const results = partners.map(p => evaluatePartnerPromise(p));

  const achieved = results.filter(r => r.achieved).length;
  const total = results.length;
  const cpr = total > 0 ? Math.round((achieved / total) * 100) : 0;

  return {
    available: true,
    cpr,
    achieved,
    total,
    rating: cpr >= 80 ? 'excellent' : cpr >= 60 ? 'good' : cpr >= 40 ? 'at risk' : 'critical',
    partners: results,
    interpretation: interpretCPR(cpr, achieved, total),
    target: '≥ 80% (4 of 5 partners achieve their promised outcome)',
    generatedAt: new Date().toISOString(),
  };
}

// Evaluate whether a single partner achieved their promised outcome.
function evaluatePartnerPromise(promise) {
  const metrics = computeMetrics({ organization: promise.orgId });
  const receipts = listReceipts(1000).filter(r => r.scope?.organization === promise.orgId);

  if (receipts.length === 0) {
    return {
      orgId: promise.orgId,
      promisedOutcome: promise.promisedOutcome,
      targetReduction: promise.targetReduction,
      achieved: false,
      status: 'not_started',
      message: 'No executions yet.',
      daysSinceStart: null,
    };
  }

  // Check if 90 days have passed.
  const startDate = new Date(promise.startDate);
  const daysSinceStart = Math.floor((Date.now() - startDate.getTime()) / (1000 * 60 * 60 * 24));

  if (daysSinceStart < 90) {
    return {
      orgId: promise.orgId,
      promisedOutcome: promise.promisedOutcome,
      targetReduction: promise.targetReduction,
      achieved: false,
      status: 'in_progress',
      daysSinceStart,
      daysRemaining: 90 - daysSinceStart,
      currentCycleTime: metrics.headline?.cycleTimeHours || null,
      baselineCycleTime: promise.baseline?.cycleTimeHours || null,
      currentReduction: promise.baseline?.cycleTimeHours
        ? Math.round(((promise.baseline.cycleTimeHours - (metrics.headline?.cycleTimeHours || 0)) / promise.baseline.cycleTimeHours) * 100)
        : null,
      message: `In progress: ${daysSinceStart}/90 days. Current reduction: ${promise.baseline?.cycleTimeHours ? Math.round(((promise.baseline.cycleTimeHours - (metrics.headline?.cycleTimeHours || 0)) / promise.baseline.cycleTimeHours) * 100) + '%' : 'measuring...'}`,
    };
  }

  // 90 days passed — evaluate.
  const currentCycleTime = metrics.headline?.cycleTimeHours || 0;
  const baselineCycleTime = promise.baseline?.cycleTimeHours || 0;
  const reduction = baselineCycleTime > 0
    ? Math.round(((baselineCycleTime - currentCycleTime) / baselineCycleTime) * 100)
    : 0;

  const achieved = reduction >= promise.targetReduction;

  return {
    orgId: promise.orgId,
    promisedOutcome: promise.promisedOutcome,
    targetReduction: promise.targetReduction,
    achieved,
    status: achieved ? 'achieved' : 'missed',
    daysSinceStart,
    baselineCycleTime,
    currentCycleTime,
    reduction,
    message: achieved
      ? `Achieved: ${reduction}% cycle time reduction (target: ${promise.targetReduction}%).`
      : `Missed: ${reduction}% reduction vs ${promise.targetReduction}% target.`,
  };
}

function interpretCPR(cpr, achieved, total) {
  if (cpr >= 80) return `${achieved} of ${total} design partners achieved their promised outcome. Strong product-market fit signal.`;
  if (cpr >= 60) return `${achieved} of ${total} partners achieved outcomes. Promising but needs consistency.`;
  if (cpr >= 40) return `${achieved} of ${total} partners achieved outcomes. At risk — investigate why others missed.`;
  return `${achieved} of ${total} partners achieved outcomes. Critical — the thesis may not be working.`;
}

// Get CPR for a specific partner.
export function getPartnerProof(orgId) {
  const promise = partnerPromises.get(orgId);
  if (!promise) {
    return { available: false, message: 'No promise set for this partner.' };
  }
  return evaluatePartnerPromise(promise);
}

// List all partner promises.
export function listPartnerPromises() {
  return Array.from(partnerPromises.values());
}

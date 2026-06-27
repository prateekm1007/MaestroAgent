// customer-metrics.js — Time-to-Value (TTV) + Cognitive Overhead Index (COI)
//
// TTV: How many days until the customer experiences their first measurable
// improvement? If 90 days — too slow. If 14 — now you're onto something.
//
// COI: The anti-metric. Every release should REDUCE it. Measures clicks,
// configuration time, manual policy creation, approvals configured, prompts
// written. The system should become smarter without demanding more effort.

import { listReceipts } from './receipts.js';
import { getGovernanceStats } from './governance.js';
import { getPolicyStats } from './policies.js';
import { getIntegrationStats } from './integrations.js';

// === TIME-TO-VALUE (TTV) ===
// Measures days from first execution to first measurable improvement.
//
// "Measurable improvement" = the first execution that:
//   - Was accepted by the user (outcome = 'accepted')
//   - Referenced a past pattern or learning object (knowledge reuse)
//   - Had confidence > 0 (specialist was confident)
//   - Produced a deliverable artifact
//
// TTV is the customer-facing metric. Lower is better.
export function computeTTV(orgId) {
  const receipts = listReceipts(1000);
  const orgReceipts = orgId
    ? receipts.filter(r => r.scope?.organization === orgId)
    : receipts;

  if (orgReceipts.length === 0) {
    return {
      available: false,
      message: 'No executions yet. TTV is measured from first execution to first measurable improvement.',
      ttvDays: null,
    };
  }

  // Sort by creation time.
  const sorted = orgReceipts.sort((a, b) => new Date(a.createdAt) - new Date(b.createdAt));
  const firstExecution = new Date(sorted[0].createdAt);

  // Find the first execution that shows "measurable improvement."
  const improvementReceipt = sorted.find(r =>
    r.outcome?.result === 'accepted' &&
    (r.patternsUsed?.length > 0 || r.evidence?.length > 0) &&
    r.execution?.artifactCount > 0
  );

  if (!improvementReceipt) {
    return {
      available: true,
      ttvDays: null,
      status: 'pending',
      message: 'No measurable improvement yet. Waiting for first accepted execution with knowledge reuse.',
      firstExecutionAt: firstExecution.toISOString(),
      totalExecutions: orgReceipts.length,
      target: '< 14 days',
    };
  }

  const improvementDate = new Date(improvementReceipt.createdAt);
  const ttvMs = improvementDate - firstExecution;
  const ttvDays = ttvMs / (1000 * 60 * 60 * 24);

  // Rate the TTV.
  let rating;
  if (ttvDays <= 7) rating = 'excellent';
  else if (ttvDays <= 14) rating = 'good';
  else if (ttvDays <= 30) rating = 'acceptable';
  else if (ttvDays <= 60) rating = 'slow';
  else rating = 'too slow';

  return {
    available: true,
    ttvDays: Math.round(ttvDays * 10) / 10,
    rating,
    status: 'achieved',
    firstExecutionAt: firstExecution.toISOString(),
    firstImprovementAt: improvementDate.toISOString(),
    improvementRunId: improvementReceipt.runId,
    totalExecutions: orgReceipts.length,
    target: '< 14 days',
    interpretation: interpretTTV(ttvDays),
  };
}

function interpretTTV(days) {
  if (days <= 7) return 'Customer experienced value within the first week. Excellent onboarding.';
  if (days <= 14) return 'Customer saw improvement within 2 weeks. Strong TTV.';
  if (days <= 30) return 'Customer saw improvement within a month. Acceptable, but optimize onboarding.';
  if (days <= 60) return 'TTV is over a month. Customers may churn before seeing value. Reduce friction.';
  return 'TTV is too slow. Customers are not experiencing value quickly enough. Immediate intervention required.';
}

// === COGNITIVE OVERHEAD INDEX (COI) ===
// The anti-metric. Every release should REDUCE this.
//
// Measures the effort a customer expends to use Maestro:
//   - Number of manual policy creations
//   - Number of approval chains configured manually
//   - Average configuration time (estimated from setup actions)
//   - Number of clicks to complete an execution (estimated)
//   - Number of prompts/interrupts per execution
//   - Number of manual feedback submissions
//
// Lower is better. The system should become smarter without demanding more effort.
export function computeCOI(orgId) {
  const receipts = listReceipts(1000);
  const orgReceipts = orgId
    ? receipts.filter(r => r.scope?.organization === orgId)
    : receipts;

  const governance = getGovernanceStats();
  const policies = getPolicyStats();
  const integrations = getIntegrationStats(orgId || 'default');

  // Count manual configuration actions.
  const manualPolicies = policies.total || 0;
  const manualControls = governance.total || 0;
  const manualApprovals = governance.approvalRequired || 0;

  // Count user effort per execution.
  const totalInterrupts = orgReceipts.reduce((sum, r) =>
    sum + (r.outcome?.corrections?.length || 0), 0);
  const totalFeedback = orgReceipts.filter(r =>
    r.outcome?.result !== 'pending').length;

  // Estimate clicks per execution (rough proxy):
  // - Submit goal: 1 click
  // - Each interrupt: 3 clicks (type, send, confirm)
  // - Each feedback: 2 clicks (select, submit)
  const estimatedClicksPerExecution = 1 + (totalInterrupts / Math.max(orgReceipts.length, 1)) * 3 + (totalFeedback / Math.max(orgReceipts.length, 1)) * 2;

  // Estimate configuration overhead (from setup actions).
  const configActions = manualPolicies + manualControls + manualApprovals;
  const estimatedConfigMinutes = configActions * 5; // ~5 min per config action

  // Compute COI (0-100, lower is better).
  const overheadScore =
    (manualPolicies * 2) +
    (manualControls * 1.5) +
    (manualApprovals * 1) +
    (estimatedClicksPerExecution * 5) +
    (totalInterrupts / Math.max(orgReceipts.length, 1) * 10);

  const coi = Math.min(100, Math.round(overheadScore));

  return {
    available: orgReceipts.length > 0,
    coi,
    rating: coi <= 20 ? 'excellent' : coi <= 40 ? 'good' : coi <= 60 ? 'acceptable' : coi <= 80 ? 'high' : 'too high',
    components: {
      manualPolicies,
      manualControls,
      manualApprovals,
      estimatedClicksPerExecution: Math.round(estimatedClicksPerExecution * 10) / 10,
      totalInterrupts,
      totalFeedback,
      estimatedConfigMinutes,
    },
    interpretation: interpretCOI(coi),
    target: 'Decrease every release',
    generatedAt: new Date().toISOString(),
  };
}

function interpretCOI(coi) {
  if (coi <= 20) return 'Low cognitive overhead. Customers can use Maestro with minimal configuration.';
  if (coi <= 40) return 'Moderate overhead. Some manual configuration required, but manageable.';
  if (coi <= 60) return 'Significant overhead. Customers are spending time configuring rather than executing.';
  if (coi <= 80) return 'High overhead. Configuration burden may be blocking adoption.';
  return 'Too high. Cognitive overhead is likely preventing customer success. Simplify immediately.';
}

// Combined customer health score using TTV + COI + OED.
export function computeCustomerHealth(orgId, baselineMetrics = null) {
  const ttv = computeTTV(orgId);
  const coi = computeCOI(orgId);
  const oed = computeOED(orgId, baselineMetrics);

  // Normalize each to 0-100 (higher = healthier).
  const ttvScore = ttv.ttvDays !== null
    ? Math.max(0, 100 - (ttv.ttvDays * 2)) // 0 days = 100, 50 days = 0
    : ttv.status === 'pending' ? 30 : 0;

  const coiScore = coi.available ? Math.max(0, 100 - coi.coi) : 50;

  const oedScore = oed.available ? Math.max(0, Math.min(100, 50 + oed.oed * 2)) : 50;

  const healthScore = Math.round((ttvScore * 0.3) + (coiScore * 0.3) + (oedScore * 0.4));

  return {
    available: true,
    orgId: orgId || 'global',
    healthScore,
    rating: healthScore >= 75 ? 'healthy' : healthScore >= 50 ? 'at risk' : 'critical',
    components: {
      ttv: { score: Math.round(ttvScore), ...ttv },
      coi: { score: Math.round(coiScore), ...coi },
      oed: { score: Math.round(oedScore), ...oed },
    },
    interpretation: interpretHealth(healthScore),
    generatedAt: new Date().toISOString(),
  };
}

function interpretHealth(score) {
  if (score >= 75) return 'Customer is healthy. Fast time-to-value, low overhead, positive OED.';
  if (score >= 50) return 'Customer is at risk. Identify which component is dragging the score down.';
  return 'Customer is critical. Immediate intervention needed — slow TTV, high overhead, or negative OED.';
}

// Import OED for the combined health score.
import { computeOED } from './observatory.js';

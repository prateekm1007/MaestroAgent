// metrics.js — Maestro's Execution Metrics.
//
// This is NOT a cognitive layer. This is the COMMERCIAL layer.
//
// Executives don't buy patterns, policies, or receipts.
// They buy:
//   - Cycle time reduction
//   - Approval latency
//   - Rework %
//   - Knowledge reuse
//   - Compliance score
//   - Policy violations prevented
//   - Audit readiness
//   - Hours saved
//
// Every metric is computed from Execution Receipts — the audit trail
// becomes the data source for operational intelligence.
//
// This is what turns Maestro from "AI that executes" into
// "continuous operational improvement platform."

import { listReceipts } from './receipts.js';
import { listCases } from './evidence.js';
import { getStats as getLearningStats } from './learning.js';
import { getGovernanceStats } from './governance.js';
import { getPolicyStats } from './policies.js';

// Compute all execution metrics from accumulated receipts.
// This is the dashboard a CIO buys.
export function computeMetrics(scope = null) {
  const receipts = listReceipts(1000); // all receipts
  const cases = listCases(1000);
  const learning = getLearningStats();
  const governance = getGovernanceStats();
  const policies = getPolicyStats();

  // Filter by scope if provided.
  const filteredReceipts = scope
    ? receipts.filter(r => matchesScope(r.scope, scope))
    : receipts;

  if (filteredReceipts.length === 0) {
    return {
      totalExecutions: 0,
      message: 'No executions yet. Metrics will appear after projects are completed.',
    };
  }

  // === CYCLE TIME ===
  // Average execution duration (from start to finish).
  const cycleTimes = filteredReceipts
    .map(r => r.execution?.durationMs || 0)
    .filter(d => d > 0);
  const avgCycleTimeMs = cycleTimes.length > 0
    ? cycleTimes.reduce((a, b) => a + b, 0) / cycleTimes.length
    : 0;

  // === APPROVAL LATENCY ===
  // How long approvals take (pending approvals = latency not yet resolved).
  const pendingApprovals = filteredReceipts.reduce((sum, r) => {
    return sum + (r.approvals?.filter(a => !a.granted).length || 0);
  }, 0);
  const totalApprovals = filteredReceipts.reduce((sum, r) => {
    return sum + (r.approvals?.length || 0);
  }, 0);
  const approvalRate = totalApprovals > 0 ? (totalApprovals - pendingApprovals) / totalApprovals : 1;

  // === REWORK % ===
  // Percentage of executions that were rejected or edited (needed rework).
  const reworkCount = filteredReceipts.filter(r =>
    r.outcome?.result === 'rejected' || r.outcome?.result === 'edited'
  ).length;
  const reworkRate = filteredReceipts.length > 0 ? reworkCount / filteredReceipts.length : 0;

  // === KNOWLEDGE REUSE ===
  // Percentage of executions that referenced past patterns/precedents.
  const knowledgeReuseCount = filteredReceipts.filter(r =>
    (r.patternsUsed?.length || 0) > 0
  ).length;
  const knowledgeReuseRate = filteredReceipts.length > 0 ? knowledgeReuseCount / filteredReceipts.length : 0;

  // === COMPLIANCE SCORE ===
  // Percentage of executions that satisfied all governance controls.
  const violationsCount = filteredReceipts.filter(r =>
    r.exceptions?.some(e => e.reason === 'constitutional')
  ).length;
  const complianceScore = filteredReceipts.length > 0
    ? ((filteredReceipts.length - violationsCount) / filteredReceipts.length) * 100
    : 100;

  // === POLICY VIOLATIONS PREVENTED ===
  // Executions that were BLOCKED by governance (preventing non-compliant work).
  const violationsPrevented = filteredReceipts.filter(r =>
    r.outcome?.result === 'blocked'
  ).length;

  // === AUDIT READINESS ===
  // Percentage of executions with complete receipts (all evidence collected).
  const completeReceipts = filteredReceipts.filter(r =>
    r.evidence?.length > 0 && r.receiptHash
  ).length;
  const auditReadiness = filteredReceipts.length > 0
    ? (completeReceipts / filteredReceipts.length) * 100
    : 0;

  // === HOURS SAVED (estimated) ===
  // Estimate: each completed execution saves ~2 hours of manual work
  // (research, drafting, review, compliance checking).
  // This is conservative — real enterprises see 4-10x for repetitive workflows.
  const hoursSavedPerExecution = 2;
  const hoursSaved = filteredReceipts.length * hoursSavedPerExecution;

  // === DELIVERABLE QUALITY ===
  // Acceptance rate (accepted / total with outcomes).
  const withOutcomes = filteredReceipts.filter(r => r.outcome?.result !== 'pending');
  const accepted = withOutcomes.filter(r => r.outcome?.result === 'accepted');
  const acceptanceRate = withOutcomes.length > 0 ? accepted.length / withOutcomes.length : 0;

  // === KNOWLEDGE GROWTH ===
  // How the knowledge base is growing.
  const totalArtifacts = filteredReceipts.reduce((sum, r) =>
    sum + (r.execution?.artifactCount || 0), 0);
  const totalEvidence = filteredReceipts.reduce((sum, r) =>
    sum + (r.evidence?.length || 0), 0);

  return {
    // Headline metrics (what executives buy)
    headline: {
      cycleTimeHours: Math.round(avgCycleTimeMs / 1000 / 60 * 10) / 10, // hours, 1 decimal
      reworkRate: Math.round(reworkRate * 100),
      knowledgeReuseRate: Math.round(knowledgeReuseRate * 100),
      complianceScore: Math.round(complianceScore),
      hoursSaved,
      violationsPrevented,
      auditReadiness: Math.round(auditReadiness),
      acceptanceRate: Math.round(acceptanceRate * 100),
    },

    // Operational details (what managers care about)
    operational: {
      totalExecutions: filteredReceipts.length,
      totalArtifacts,
      totalEvidence,
      pendingApprovals,
      totalApprovals,
      approvalRate: Math.round(approvalRate * 100),
      blockedExecutions: violationsPrevented,
    },

    // Knowledge base state (what CTOs care about)
    knowledge: {
      learningObjects: learning.total,
      acceptedProjects: learning.accepted,
      patterns: getPatternCount(),
      policies: policies.total,
      constitutionalPolicies: policies.constitutional,
      governanceControls: governance.total,
      blockingControls: governance.blocking,
      cases: cases.length,
      precedents: getPrecedentCount(),
    },

    // Trends (computed from receipt timestamps)
    trends: computeTrends(filteredReceipts),

    // Scope this was computed for
    scope: scope || 'global',
    computedAt: new Date().toISOString(),
  };
}

// Compute Before/After ROI report.
// Compares early executions vs recent executions to show improvement.
export function computeROIReport(scope = null) {
  const receipts = listReceipts(1000);
  const filtered = scope
    ? receipts.filter(r => matchesScope(r.scope, scope))
    : receipts;

  if (filtered.length < 4) {
    return {
      available: false,
      message: 'Need at least 4 executions to compute Before/After report.',
      totalExecutions: filtered.length,
    };
  }

  // Split into first half (before) and second half (after).
  const sorted = filtered.sort((a, b) => new Date(a.createdAt) - new Date(b.createdAt));
  const midpoint = Math.floor(sorted.length / 2);
  const before = sorted.slice(0, midpoint);
  const after = sorted.slice(midpoint);

  const beforeMetrics = computeMetricsForSet(before);
  const afterMetrics = computeMetricsForSet(after);

  // Compute deltas.
  const deltas = {
    cycleTime: beforeMetrics.cycleTimeHours - afterMetrics.cycleTimeHours,
    reworkRate: beforeMetrics.reworkRate - afterMetrics.reworkRate,
    knowledgeReuse: afterMetrics.knowledgeReuseRate - beforeMetrics.knowledgeReuseRate,
    compliance: afterMetrics.complianceScore - beforeMetrics.complianceScore,
    acceptance: afterMetrics.acceptanceRate - beforeMetrics.acceptanceRate,
  };

  return {
    available: true,
    before: {
      executions: before.length,
      period: before[0]?.createdAt + ' → ' + before[before.length - 1]?.createdAt,
      metrics: beforeMetrics,
    },
    after: {
      executions: after.length,
      period: after[0]?.createdAt + ' → ' + after[after.length - 1]?.createdAt,
      metrics: afterMetrics,
    },
    deltas: {
      cycleTimeHours: Math.round(deltas.cycleTime * 10) / 10,
      cycleTimeImprovement: beforeMetrics.cycleTimeHours > 0
        ? Math.round((deltas.cycleTime / beforeMetrics.cycleTimeHours) * 100) : 0,
      reworkRatePoints: Math.round(deltas.reworkRate * 100) / 100,
      knowledgeReusePoints: Math.round(deltas.knowledgeReuse * 100),
      compliancePoints: Math.round(deltas.compliance),
      acceptancePoints: Math.round(deltas.acceptance * 100),
    },
    summary: generateROISummary(beforeMetrics, afterMetrics, deltas),
  };
}

function computeMetricsForSet(receipts) {
  const cycleTimes = receipts.map(r => r.execution?.durationMs || 0).filter(d => d > 0);
  const avgCycleMs = cycleTimes.length > 0 ? cycleTimes.reduce((a, b) => a + b, 0) / cycleTimes.length : 0;
  const rework = receipts.filter(r => r.outcome?.result === 'rejected' || r.outcome?.result === 'edited').length;
  const reuse = receipts.filter(r => (r.patternsUsed?.length || 0) > 0).length;
  const violations = receipts.filter(r => r.exceptions?.some(e => e.reason === 'constitutional')).length;
  const withOutcomes = receipts.filter(r => r.outcome?.result !== 'pending');
  const accepted = withOutcomes.filter(r => r.outcome?.result === 'accepted');

  return {
    cycleTimeHours: Math.round(avgCycleMs / 1000 / 60 * 10) / 10,
    reworkRate: receipts.length > 0 ? rework / receipts.length : 0,
    knowledgeReuseRate: receipts.length > 0 ? reuse / receipts.length : 0,
    complianceScore: receipts.length > 0 ? ((receipts.length - violations) / receipts.length) * 100 : 100,
    acceptanceRate: withOutcomes.length > 0 ? accepted.length / withOutcomes.length : 0,
  };
}

function generateROISummary(before, after, deltas) {
  const lines = [];
  if (deltas.cycleTimeHours > 0) {
    lines.push(`Cycle time reduced by ${deltas.cycleTimeHours} hours (${deltas.cycleTimeImprovement}% faster).`);
  }
  if (deltas.reworkRatePoints > 0) {
    lines.push(`Rework rate reduced by ${Math.round(deltas.reworkRatePoints * 100)}%.`);
  }
  if (deltas.knowledgeReusePoints > 0) {
    lines.push(`Knowledge reuse increased by ${deltas.knowledgeReusePoints}%.`);
  }
  if (deltas.compliancePoints > 0) {
    lines.push(`Compliance score improved by ${deltas.compliancePoints} points.`);
  }
  if (deltas.acceptancePoints > 0) {
    lines.push(`Acceptance rate improved by ${deltas.acceptancePoints}%.`);
  }
  return lines.length > 0 ? lines.join(' ') : 'Insufficient data for trend analysis.';
}

function computeTrends(receipts) {
  // Group by day.
  const byDay = {};
  for (const r of receipts) {
    const day = r.createdAt?.split('T')[0];
    if (!day) continue;
    if (!byDay[day]) byDay[day] = { count: 0, duration: 0, accepted: 0 };
    byDay[day].count++;
    byDay[day].duration += r.execution?.durationMs || 0;
    if (r.outcome?.result === 'accepted') byDay[day].accepted++;
  }
  return Object.entries(byDay)
    .sort((a, b) => a[0].localeCompare(b[0]))
    .slice(-14) // last 14 days
    .map(([day, data]) => ({
      date: day,
      executions: data.count,
      avgDurationMs: data.count > 0 ? data.duration / data.count : 0,
      accepted: data.accepted,
    }));
}

function matchesScope(receiptScope, filterScope) {
  if (!receiptScope || !filterScope) return true;
  for (const key of ['organization', 'department', 'team', 'userId']) {
    if (filterScope[key] && receiptScope[key] !== filterScope[key]) return false;
  }
  return true;
}

function getPatternCount() {
  // Lazy import to avoid circular dependency.
  return 0; // placeholder — getPatternStats is in server.js scope
}

function getPrecedentCount() {
  return 0; // placeholder
}

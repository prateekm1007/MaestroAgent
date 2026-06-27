// benchmarks.js — Operational Benchmark Network.
//
// "Top 10% engineering teams review code in 4 hours. Median is 26 hours."
//
// This is the network effect. Once 500 companies use Maestro, each one
// can see how they compare to peers — anonymously.
//
// Benchmarks are computed from the aggregated, anonymized execution data
// across all organizations. No company sees another company's raw data.
// They only see aggregate statistics:
//   - Percentiles (top 10%, median, bottom 10%)
//   - Industry averages
//   - Best practices derived from top performers
//
// This is what companies pay for: not just "how are we doing?" but
// "how are we doing relative to everyone else?"

import { listReceipts } from './receipts.js';

// Compute benchmarks across all organizations.
// Returns percentile rankings for key metrics.
export function computeBenchmarks(scope = null) {
  const receipts = listReceipts(10000);

  if (receipts.length < 5) {
    return {
      available: false,
      message: 'Need at least 5 total executions across the network to compute benchmarks.',
      totalExecutions: receipts.length,
    };
  }

  // Group by organization.
  const byOrg = {};
  for (const r of receipts) {
    const org = r.scope?.organization || 'unknown';
    if (!byOrg[org]) byOrg[org] = [];
    byOrg[org].push(r);
  }

  const orgCount = Object.keys(byOrg).length;

  if (orgCount < 2) {
    return {
      available: false,
      message: 'Need at least 2 organizations for benchmarking. Currently: ' + orgCount,
      totalOrganizations: orgCount,
      totalExecutions: receipts.length,
    };
  }

  // Compute per-org metrics.
  const orgMetrics = [];
  for (const [org, orgReceipts] of Object.entries(byOrg)) {
    const metrics = computeOrgMetrics(orgReceipts);
    orgMetrics.push({ org, ...metrics, executionCount: orgReceipts.length });
  }

  // Compute percentiles for each metric.
  const benchmarkMetrics = ['cycleTimeHours', 'complianceScore', 'acceptanceRate', 'reworkRate', 'knowledgeReuseRate'];
  const percentiles = {};

  for (const metric of benchmarkMetrics) {
    const values = orgMetrics.map(m => m[metric]).filter(v => v !== null && v !== undefined);
    if (values.length === 0) continue;

    values.sort((a, b) => {
      // For cycleTime and reworkRate, lower is better.
      // For compliance and acceptance, higher is better.
      if (metric === 'cycleTimeHours' || metric === 'reworkRate') return a - b;
      return a - b;
    });

    percentiles[metric] = {
      p10: percentile(values, 0.10),
      p25: percentile(values, 0.25),
      p50: percentile(values, 0.50), // median
      p75: percentile(values, 0.75),
      p90: percentile(values, 0.90),
      min: values[0],
      max: values[values.length - 1],
      // For cycle time and rework: lower is better, so p10 = top performers.
      // For compliance and acceptance: higher is better, so p90 = top performers.
      topPerformers: (metric === 'cycleTimeHours' || metric === 'reworkRate')
        ? percentile(values, 0.10)
        : percentile(values, 0.90),
      direction: (metric === 'cycleTimeHours' || metric === 'reworkRate') ? 'lower_better' : 'higher_better',
    };
  }

  // Generate insights.
  const insights = generateInsights(percentiles, orgMetrics);

  return {
    available: true,
    totalOrganizations: orgCount,
    totalExecutions: receipts.length,
    percentiles,
    insights,
    yourOrg: scope?.organization
      ? orgMetrics.find(m => m.org === scope.organization) || null
      : null,
    generatedAt: new Date().toISOString(),
  };
}

// Compute metrics for a single organization.
function computeOrgMetrics(receipts) {
  const cycleTimes = receipts.map(r => r.execution?.durationMs || 0).filter(d => d > 0);
  const avgCycleMs = cycleTimes.length > 0 ? cycleTimes.reduce((a, b) => a + b, 0) / cycleTimes.length : 0;

  const violations = receipts.filter(r => r.exceptions?.some(e => e.reason === 'constitutional')).length;
  const rework = receipts.filter(r => r.outcome?.result === 'rejected' || r.outcome?.result === 'edited').length;
  const reuse = receipts.filter(r => (r.patternsUsed?.length || 0) > 0).length;
  const withOutcomes = receipts.filter(r => r.outcome?.result !== 'pending');
  const accepted = withOutcomes.filter(r => r.outcome?.result === 'accepted');

  return {
    cycleTimeHours: Math.round(avgCycleMs / 1000 / 60 * 10) / 10,
    complianceScore: Math.round(((receipts.length - violations) / receipts.length) * 100),
    acceptanceRate: withOutcomes.length > 0 ? Math.round((accepted.length / withOutcomes.length) * 100) : 0,
    reworkRate: Math.round((rework / receipts.length) * 100),
    knowledgeReuseRate: Math.round((reuse / receipts.length) * 100),
  };
}

// Generate insights from benchmark data.
function generateInsights(percentiles, orgMetrics) {
  const insights = [];

  if (percentiles.cycleTimeHours) {
    const topCycle = percentiles.cycleTimeHours.topPerformers;
    const medianCycle = percentiles.cycleTimeHours.p50;
    insights.push({
      metric: 'cycleTimeHours',
      insight: `Top 10% of organizations complete executions in ${topCycle} hours. Median is ${medianCycle} hours.`,
      recommendation: `If you're above median, focus on approval chain optimization and parallelizing reviews.`,
    });
  }

  if (percentiles.complianceScore) {
    const topCompliance = percentiles.complianceScore.topPerformers;
    insights.push({
      metric: 'complianceScore',
      insight: `Top 10% of organizations achieve ${topCompliance}% compliance. Median is ${percentiles.complianceScore.p50}%.`,
      recommendation: `Organizations with >90% compliance typically automate policy enforcement rather than relying on manual review.`,
    });
  }

  if (percentiles.knowledgeReuseRate) {
    const topReuse = percentiles.knowledgeReuseRate.topPerformers;
    insights.push({
      metric: 'knowledgeReuseRate',
      insight: `Top 10% of organizations reuse past execution knowledge in ${topReuse}% of new projects. Median is ${percentiles.knowledgeReuseRate.p50}%.`,
      recommendation: `Knowledge reuse is the leading indicator of compounding improvement. Focus on pattern extraction and feedback loops.`,
    });
  }

  if (percentiles.reworkRate) {
    const topRework = percentiles.reworkRate.topPerformers;
    insights.push({
      metric: 'reworkRate',
      insight: `Top 10% of organizations have a rework rate of only ${topRework}%. Median is ${percentiles.reworkRate.p50}%.`,
      recommendation: `High rework rates indicate planning gaps. Invest in the conductor's examine phase and pattern retrieval.`,
    });
  }

  return insights;
}

// Compute percentile value from sorted array.
function percentile(sortedValues, p) {
  if (sortedValues.length === 0) return 0;
  const idx = Math.ceil(p * sortedValues.length) - 1;
  return sortedValues[Math.max(0, Math.min(idx, sortedValues.length - 1))];
}

// Get benchmark stats.
export function getBenchmarkStats() {
  const receipts = listReceipts(10000);
  const byOrg = {};
  for (const r of receipts) {
    const org = r.scope?.organization || 'unknown';
    if (!byOrg[org]) byOrg[org] = 0;
    byOrg[org]++;
  }
  return {
    totalOrganizations: Object.keys(byOrg).length,
    totalExecutions: receipts.length,
    organizations: Object.entries(byOrg).map(([org, count]) => ({ org, executions: count })),
  };
}

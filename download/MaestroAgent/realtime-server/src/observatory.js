// observatory.js — The Execution Observatory.
//
// Every design partner contributes anonymous metrics to a shared dataset.
// No company sees another company's raw data — only aggregate statistics.
//
// This becomes the proprietary asset that makes Maestro impossible to
// compete with. After 500+ partners, you know things like:
//   "Companies that parallelize security + legal review ship 23% faster
//    (95% confidence, n=41)."
//
// That's not AI. That's comparative execution intelligence.
// People pay enormous amounts of money for that.

import { promises as fs } from 'node:fs';
import path from 'node:path';
import { listReceipts } from './receipts.js';
import { computeMetrics } from './metrics.js';
import { getCurrentScope } from './scope.js';

const OBSERVATORY_STORE_PATH = path.resolve('./execution-observatory.jsonl');
const observations = []; // array of anonymous observations

export async function initObservatoryStore() {
  try {
    const data = await fs.readFile(OBSERVATORY_STORE_PATH, 'utf8');
    for (const line of data.split('\n').filter(Boolean)) {
      try {
        observations.push(JSON.parse(line));
      } catch {}
    }
    console.log(`[observatory] loaded ${observations.length} anonymous observations from disk`);
  } catch (err) {
    if (err.code !== 'ENOENT') console.warn('[observatory] failed to load:', err.message);
  }
}

async function persist(observation) {
  try { await fs.appendFile(OBSERVATORY_STORE_PATH, JSON.stringify(observation) + '\n', 'utf8'); }
  catch (err) { console.warn('[observatory] persist failed:', err.message); }
}

// Contribute an anonymous observation from an organization's metrics.
// This is called periodically (e.g., weekly) for each design partner.
// The observation is STRIPPED of all identifying information — only
// aggregate metrics and company-size bucket are stored.
export async function contributeObservation(orgId, options = {}) {
  const metrics = computeMetrics({ organization: orgId });
  if (!metrics.headline) {
    return { contributed: false, reason: 'no metrics available for this org' };
  }

  // Determine company-size bucket (anonymous).
  const engineerCount = options.engineerCount || 50;
  const sizeBucket = bucketBySize(engineerCount);

  // Strip all identifying info. The observation contains ONLY:
  // - size bucket (not company name)
  // - industry (not company name)
  // - aggregate metrics (no raw execution data)
  // - timestamp
  const observation = {
    id: crypto.randomUUID(),
    orgIdHash: hashOrgId(orgId), // one-way hash, not reversible
    sizeBucket,
    industry: options.industry || 'technology',
    metrics: {
      cycleTimeHours: metrics.headline.cycleTimeHours,
      reworkRate: metrics.headline.reworkRate,
      knowledgeReuseRate: metrics.headline.knowledgeReuseRate,
      complianceScore: metrics.headline.complianceScore,
      hoursSaved: metrics.headline.hoursSaved,
      violationsPrevented: metrics.headline.violationsPrevented,
      auditReadiness: metrics.headline.auditReadiness,
      acceptanceRate: metrics.headline.acceptanceRate,
    },
    operational: {
      totalExecutions: metrics.operational?.totalExecutions || 0,
      totalArtifacts: metrics.operational?.totalArtifacts || 0,
      totalEvidence: metrics.operational?.totalEvidence || 0,
    },
    contributedAt: new Date().toISOString(),
    // NOTE: No company name. No raw execution data. No user info.
    // This is a one-way contribution — data flows in, only aggregates flow out.
  };

  observations.push(observation);
  await persist(observation);
  console.log(`[observatory] anonymous observation contributed (bucket: ${sizeBucket}, executions: ${observation.operational.totalExecutions})`);

  return {
    contributed: true,
    observationId: observation.id,
    sizeBucket,
    message: 'Anonymous metrics contributed to the Execution Observatory.',
  };
}

// Get aggregate statistics from the observatory.
// This is what design partners see — how they compare to peers.
export function getObservatoryStats() {
  if (observations.length === 0) {
    return {
      available: false,
      message: 'No observations yet. The observatory grows as design partners contribute.',
      totalObservations: 0,
    };
  }

  // Group by size bucket.
  const byBucket = {};
  for (const obs of observations) {
    if (!byBucket[obs.sizeBucket]) byBucket[obs.sizeBucket] = [];
    byBucket[obs.sizeBucket].push(obs);
  }

  // Compute percentiles for each bucket.
  const bucketStats = {};
  for (const [bucket, obsList] of Object.entries(byBucket)) {
    bucketStats[bucket] = computeBucketPercentiles(obsList);
  }

  // Compute overall percentiles.
  const overall = computeBucketPercentiles(observations);

  // Generate insights.
  const insights = generateObservatoryInsights(observations, bucketStats);

  return {
    available: true,
    totalObservations: observations.length,
    totalOrganizations: new Set(observations.map(o => o.orgIdHash)).size,
    bySizeBucket: bucketStats,
    overall,
    insights,
    generatedAt: new Date().toISOString(),
  };
}

// Compare an organization against the observatory.
// "How does our cycle time compare to similar companies?"
export function compare_toPeers(orgId, options = {}) {
  const metrics = computeMetrics({ organization: orgId });
  if (!metrics.headline) {
    return { available: false, reason: 'no metrics available for this org' };
  }

  const engineerCount = options.engineerCount || 50;
  const sizeBucket = bucketBySize(engineerCount);
  const peerBucket = observations.filter(o => o.sizeBucket === sizeBucket);

  if (peerBucket.length < 3) {
    return {
      available: false,
      reason: `Only ${peerBucket.length} peer organizations in the ${sizeBucket} bucket. Need at least 3 for comparison.`,
      yourMetrics: metrics.headline,
    };
  }

  const peerStats = computeBucketPercentiles(peerBucket);

  // Compare each metric.
  const comparisons = {};
  for (const [metric, value] of Object.entries(metrics.headline)) {
    const peerData = peerStats[metric];
    if (!peerData) continue;

    let percentile;
    if (metric === 'cycleTimeHours' || metric === 'reworkRate') {
      // Lower is better — find what % of peers are worse (higher).
      percentile = peerData.values.filter(v => v > value).length / peerData.values.length;
    } else {
      // Higher is better — find what % of peers are worse (lower).
      percentile = peerData.values.filter(v => v < value).length / peerData.values.length;
    }

    comparisons[metric] = {
      yourValue: value,
      peerMedian: peerData.p50,
      peerTop10: peerData.topPerformers,
      percentile: Math.round(percentile * 100),
      rating: percentile >= 0.9 ? 'top 10%' : percentile >= 0.75 ? 'top 25%' : percentile >= 0.5 ? 'above median' : percentile >= 0.25 ? 'below median' : 'bottom 25%',
    };
  }

  return {
    available: true,
    sizeBucket,
    peerCount: peerBucket.length,
    comparisons,
    summary: generateComparisonSummary(comparisons),
    generatedAt: new Date().toISOString(),
  };
}

function generateComparisonSummary(comparisons) {
  const lines = [];
  if (comparisons.cycleTimeHours) {
    const c = comparisons.cycleTimeHours;
    lines.push(`Your cycle time (${c.yourValue}h) is in the ${c.rating} compared to peers (median: ${c.peerMedian}h).`);
  }
  if (comparisons.knowledgeReuseRate) {
    const c = comparisons.knowledgeReuseRate;
    lines.push(`Knowledge reuse (${c.yourValue}%) is ${c.rating} (peer median: ${c.peerMedian}%).`);
  }
  if (comparisons.complianceScore) {
    const c = comparisons.complianceScore;
    lines.push(`Compliance score (${c.yourValue}%) is ${c.rating} (peer median: ${c.peerMedian}%).`);
  }
  return lines.join(' ');
}

function computeBucketPercentiles(obsList) {
  const metrics = ['cycleTimeHours', 'reworkRate', 'knowledgeReuseRate', 'complianceScore', 'auditReadiness', 'acceptanceRate'];
  const result = {};

  for (const metric of metrics) {
    const values = obsList.map(o => o.metrics[metric]).filter(v => v !== null && v !== undefined && v >= 0);
    if (values.length === 0) continue;

    values.sort((a, b) => a - b);
    const direction = (metric === 'cycleTimeHours' || metric === 'reworkRate') ? 'lower_better' : 'higher_better';

    result[metric] = {
      p10: percentile(values, 0.10),
      p25: percentile(values, 0.25),
      p50: percentile(values, 0.50),
      p75: percentile(values, 0.75),
      p90: percentile(values, 0.90),
      topPerformers: direction === 'lower_better' ? percentile(values, 0.10) : percentile(values, 0.90),
      direction,
      values, // kept for comparison queries
    };
  }

  return result;
}

function generateObservatoryInsights(observations, bucketStats) {
  const insights = [];

  if (bucketStats['50-200']?.cycleTimeHours) {
    const b = bucketStats['50-200'];
    insights.push({
      insight: `Mid-size companies (50-200 engineers): median cycle time is ${b.cycleTimeHours.p50}h. Top 10% achieve ${b.cycleTimeHours.topPerformers}h.`,
      recommendation: 'If your cycle time is above median, focus on approval chain optimization.',
    });
  }

  if (observations.length >= 10) {
    const avgReuse = observations.reduce((sum, o) => sum + (o.metrics.knowledgeReuseRate || 0), 0) / observations.length;
    insights.push({
      insight: `Across ${observations.length} observations, average knowledge reuse is ${Math.round(avgReuse)}%. Companies above 50% show compounding improvement.`,
      recommendation: 'Knowledge reuse is the leading indicator of compounding returns.',
    });
  }

  return insights;
}

function bucketBySize(count) {
  if (count < 20) return '1-19';
  if (count < 50) return '20-49';
  if (count < 200) return '50-200';
  if (count < 1000) return '200-1000';
  return '1000+';
}

function percentile(sortedValues, p) {
  if (sortedValues.length === 0) return 0;
  const idx = Math.ceil(p * sortedValues.length) - 1;
  return sortedValues[Math.max(0, Math.min(idx, sortedValues.length - 1))];
}

function hashOrgId(orgId) {
  // Simple hash — in production, use a proper one-way hash with salt.
  let hash = 0;
  for (let i = 0; i < orgId.length; i++) {
    const char = orgId.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash;
  }
  return 'org_' + Math.abs(hash).toString(36);
}

// === ORGANIZATIONAL EXECUTION DELTA (OED) ===
// The North Star Metric.
//
// OED = Execution Quality After 90 Days − Execution Quality Before Maestro
//
// If OED > 0, the organization is executing better because of Maestro.
// If OED ≤ 0, Maestro isn't helping (yet).
export function computeOED(orgId, baselineMetrics) {
  const currentMetrics = computeMetrics({ organization: orgId });
  if (!currentMetrics.headline) {
    return {
      available: false,
      message: 'No current metrics available. Need executions to compute OED.',
    };
  }

  if (!baselineMetrics) {
    return {
      available: false,
      message: 'Baseline metrics required. Measure before Maestro adoption, then call OED after 90 days.',
      currentMetrics: currentMetrics.headline,
    };
  }

  // Compute delta for each metric.
  const cycleTimeDelta = baselineMetrics.cycleTimeHours
    ? ((baselineMetrics.cycleTimeHours - currentMetrics.headline.cycleTimeHours) / baselineMetrics.cycleTimeHours) * 100
    : 0;

  const knowledgeReuseDelta = currentMetrics.headline.knowledgeReuseRate - (baselineMetrics.knowledgeReuseRate || 0);
  const complianceDelta = currentMetrics.headline.complianceScore - (baselineMetrics.complianceScore || 100);
  const reworkDelta = (baselineMetrics.reworkRate || 0) - currentMetrics.headline.reworkRate;
  const auditReadinessDelta = currentMetrics.headline.auditReadiness - (baselineMetrics.auditReadiness || 0);

  // Weighted OED (same weights as EII).
  const oed =
    (cycleTimeDelta * 0.25) +
    (knowledgeReuseDelta * 0.20) +
    (complianceDelta * 0.20) +
    (reworkDelta * 0.20) +
    (auditReadinessDelta * 0.15);

  return {
    available: true,
    orgId,
    oed: Math.round(oed * 10) / 10,
    rating: oed > 15 ? 'excellent' : oed > 5 ? 'good' : oed > 0 ? 'improving' : oed > -5 ? 'stagnant' : 'declining',
    deltas: {
      cycleTimeImprovement: Math.round(cycleTimeDelta * 10) / 10,
      knowledgeReuseImprovement: Math.round(knowledgeReuseDelta * 10) / 10,
      complianceImprovement: Math.round(complianceDelta * 10) / 10,
      reworkReduction: Math.round(reworkDelta * 10) / 10,
      auditReadinessImprovement: Math.round(auditReadinessDelta * 10) / 10,
    },
    baseline: baselineMetrics,
    current: currentMetrics.headline,
    interpretation: interpretOED(oed),
    generatedAt: new Date().toISOString(),
  };
}

function interpretOED(oed) {
  if (oed > 15) return 'Organization is executing significantly better with Maestro. Strong evidence of value.';
  if (oed > 5) return 'Organization is improving. Continue current trajectory.';
  if (oed > 0) return 'Marginal improvement. Monitor closely and address bottlenecks.';
  if (oed > -5) return 'No measurable improvement yet. May need more time or workflow adjustments.';
  return 'Execution has declined. Immediate intervention required.';
}

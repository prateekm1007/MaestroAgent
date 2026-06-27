// explanation.js — Maestro's Explanation Engine.
//
// Every recommendation must answer "Why?"
//
// Not: "Parallelize legal review."
// But: "Based on 18,247 similar product launches: median cycle time
//       improved 14%, compliance unchanged, confidence 92%."
//
// This is the trust layer. Enterprises don't buy black-box AI.
// They buy explainable, evidence-backed recommendations.
//
// The Explanation Engine is NOT a new cognitive layer. It's an
// interface over existing cognition — it exposes evidence, patterns,
// policies, precedents, and receipts as human-readable reasoning.
//
// Every explanation has:
//   - The recommendation
//   - The evidence (what data supports this)
//   - The reasoning (how the data leads to the recommendation)
//   - The confidence (how sure we are)
//   - The caveats (what could be wrong)
//   - The sources (which receipts/cases/patterns were used)

import { listReceipts } from './receipts.js';
import { listCases, listPrecedents } from './evidence.js';
import { listControls } from './governance.js';
import { listPolicies } from './policies.js';
import { computeMetrics } from './metrics.js';

// Generate an explanation for a recommendation.
//
// recommendation: { type, text, data }
//   e.g. { type: 'simulation', text: 'Parallelize legal and security review', data: {...simulationResult} }
//   e.g. { type: 'metric', text: 'Cycle time is 23% above median', data: {...metrics} }
//   e.g. { type: 'governance', text: 'This execution was blocked', data: {...violation} }
export function explainRecommendation(recommendation, scope = null) {
  if (!recommendation || !recommendation.text) {
    return { available: false, error: 'recommendation.text is required' };
  }

  const receipts = listReceipts(10000);
  const filtered = scope
    ? receipts.filter(r => matchesScope(r.scope, scope))
    : receipts;

  const type = recommendation.type || 'general';

  let explanation;
  switch (type) {
    case 'simulation':
      explanation = explainSimulation(recommendation, filtered);
      break;
    case 'metric':
      explanation = explainMetric(recommendation, filtered);
      break;
    case 'governance':
      explanation = explainGovernance(recommendation, filtered);
      break;
    case 'benchmark':
      explanation = explainBenchmark(recommendation, filtered);
      break;
    default:
      explanation = explainGeneral(recommendation, filtered);
  }

  return {
    available: true,
    recommendation: recommendation.text,
    type,
    ...explanation,
    generatedAt: new Date().toISOString(),
  };
}

// Explain a simulation recommendation.
function explainSimulation(rec, receipts) {
  const data = rec.data || {};
  const dataPoints = data.dataPoints?.total || receipts.length;

  return {
    evidence: [
      {
        type: 'historical_executions',
        count: dataPoints,
        description: `Based on ${dataPoints} historical execution${dataPoints !== 1 ? 's' : ''} in your organization.`,
      },
      ...(data.dataPoints?.withStep ? [{
        type: 'comparison',
        count: data.dataPoints.withStep,
        description: `${data.dataPoints.withStep} executions included the step being analyzed.`,
      }] : []),
      ...(data.dataPoints?.withoutStep ? [{
        type: 'comparison',
        count: data.dataPoints.withoutStep,
        description: `${data.dataPoints.withoutStep} executions did not include the step (control group).`,
      }] : []),
    ],
    reasoning: buildSimulationReasoning(data),
    confidence: data.confidence || 0.5,
    confidenceExplanation: explainConfidence(data.confidence || 0.5, dataPoints),
    caveats: buildSimulationCaveats(data),
    sources: {
      receiptsAnalyzed: dataPoints,
      timeRange: receipts.length > 0 ? {
        from: receipts[receipts.length - 1]?.createdAt,
        to: receipts[0]?.createdAt,
      } : null,
    },
  };
}

function buildSimulationReasoning(data) {
  const reasoning = [];
  if (data.deltas) {
    if (data.deltas.cycleTimeHours !== undefined) {
      const direction = data.deltas.cycleTimeHours > 0 ? 'increase' : 'decrease';
      reasoning.push(`Cycle time would ${direction} by ${Math.abs(data.deltas.cycleTimeHours)} hours.`);
    }
    if (data.deltas.complianceScore !== undefined) {
      const direction = data.deltas.complianceScore > 0 ? 'improve' : 'decrease';
      reasoning.push(`Compliance score would ${direction} by ${Math.abs(data.deltas.complianceScore)} points.`);
    }
    if (data.deltas.acceptanceRate !== undefined) {
      reasoning.push(`Acceptance rate would change by ${data.deltas.acceptanceRate} percentage points.`);
    }
  }
  if (data.riskLevel) {
    reasoning.push(`Risk level: ${data.riskLevel}.`);
  }
  if (data.isConstitutional) {
    reasoning.push(`This step is protected by a constitutional rule — it cannot be removed without governance approval.`);
  }
  return reasoning;
}

function buildSimulationCaveats(data) {
  const caveats = [];
  if ((data.confidence || 0) < 0.5) {
    caveats.push('Confidence is low — more execution data is needed for a stronger prediction.');
  }
  if ((data.dataPoints?.total || 0) < 20) {
    caveats.push(`Only ${data.dataPoints?.total || 0} data points were used. Recommendations strengthen with more history.`);
  }
  if (data.isConstitutional) {
    caveats.push('This is a constitutional rule. The simulation is advisory only — removal requires formal governance review.');
  }
  return caveats;
}

// Explain a metric recommendation.
function explainMetric(rec, receipts) {
  const metrics = rec.data?.headline || {};
  const total = receipts.length;

  return {
    evidence: [
      {
        type: 'execution_data',
        count: total,
        description: `Computed from ${total} execution${total !== 1 ? 's' : ''}.`,
      },
      {
        type: 'receipts',
        count: total,
        description: `Each metric is derived from tamper-evident execution receipts.`,
      },
    ],
    reasoning: [
      `Current cycle time: ${metrics.cycleTimeHours || 0} hours.`,
      `Current compliance score: ${metrics.complianceScore || 0}%.`,
      `Current knowledge reuse: ${metrics.knowledgeReuseRate || 0}%.`,
      `Current rework rate: ${metrics.reworkRate || 0}%.`,
      `Hours saved (estimated): ${metrics.hoursSaved || 0}.`,
    ],
    confidence: total >= 10 ? 0.9 : total >= 5 ? 0.7 : 0.4,
    confidenceExplanation: explainConfidence(total >= 10 ? 0.9 : 0.7, total),
    caveats: total < 10 ? ['Metrics will stabilize with more execution data.'] : [],
    sources: { receiptsAnalyzed: total },
  };
}

// Explain a governance decision (why was this blocked?).
function explainGovernance(rec, receipts) {
  const data = rec.data || {};
  const violations = data.violations || [];

  return {
    evidence: violations.map(v => ({
      type: 'policy_violation',
      description: `Policy: "${v.control}"`,
      scope: v.scope,
      evidence: v.evidence,
      severity: v.severity,
    })),
    reasoning: violations.map(v =>
      `Execution blocked because "${v.control}" (${v.scope} scope) was not addressed in the plan. ` +
      `Required evidence: ${v.evidence}.`
    ),
    confidence: 1.0, // governance blocks are deterministic
    confidenceExplanation: 'Governance violations are deterministic — confidence is 100%.',
    caveats: [],
    sources: {
      policiesChecked: violations.length,
      controlsActive: listControls().length,
    },
  };
}

// Explain a benchmark comparison.
function explainBenchmark(rec, receipts) {
  const data = rec.data || {};

  return {
    evidence: [
      {
        type: 'cross_org_data',
        count: data.totalOrganizations || 0,
        description: `Compared against ${data.totalOrganizations || 0} organization${(data.totalOrganizations || 0) !== 1 ? 's' : ''}.`,
      },
      {
        type: 'execution_data',
        count: data.totalExecutions || 0,
        description: `Based on ${data.totalExecutions || 0} total executions across the network.`,
      },
    ],
    reasoning: (data.insights || []).map(i => i.insight),
    confidence: (data.totalOrganizations || 0) >= 10 ? 0.9 : (data.totalOrganizations || 0) >= 5 ? 0.7 : 0.3,
    confidenceExplanation: explainConfidence(
      (data.totalOrganizations || 0) >= 10 ? 0.9 : 0.7,
      data.totalOrganizations || 0
    ),
    caveats: (data.totalOrganizations || 0) < 10
      ? ['Benchmark confidence increases as more organizations join the network.']
      : [],
    sources: {
      organizations: data.totalOrganizations,
      executions: data.totalExecutions,
    },
  };
}

// General explanation for any recommendation.
function explainGeneral(rec, receipts) {
  return {
    evidence: [{
      type: 'historical_data',
      count: receipts.length,
      description: `Based on ${receipts.length} historical execution${receipts.length !== 1 ? 's' : ''}.`,
    }],
    reasoning: [rec.text],
    confidence: 0.5,
    confidenceExplanation: 'Default confidence — no specific evidence type provided.',
    caveats: ['Provide a recommendation type (simulation/metric/governance/benchmark) for a richer explanation.'],
    sources: { receiptsAnalyzed: receipts.length },
  };
}

// Explain what a confidence score means in plain English.
function explainConfidence(confidence, dataPoints) {
  const pct = Math.round(confidence * 100);
  if (confidence >= 0.9) {
    return `${pct}% confidence — based on ${dataPoints} data points. High statistical reliability.`;
  } else if (confidence >= 0.7) {
    return `${pct}% confidence — based on ${dataPoints} data points. Directionally reliable, monitor for changes.`;
  } else if (confidence >= 0.5) {
    return `${pct}% confidence — based on ${dataPoints} data points. Indicative only; collect more data.`;
  } else {
    return `${pct}% confidence — based on ${dataPoints} data points. Low reliability; treat as hypothesis.`;
  }
}

function matchesScope(receiptScope, filterScope) {
  if (!receiptScope || !filterScope) return true;
  for (const key of ['organization', 'department', 'team', 'userId']) {
    if (filterScope[key] && receiptScope[key] !== filterScope[key]) return false;
  }
  return true;
}

// === EXECUTION IMPROVEMENT INDEX (EII) ===
// The one metric to obsess over.
//
// EII = Cycle Time Improvement + Knowledge Reuse Improvement +
//       Policy Compliance Improvement + Rework Reduction +
//       Audit Readiness Improvement
//
// If this number consistently improves, you have a business.
// If it doesn't, none of the architecture matters.
export function computeEII(orgId) {
  const receipts = listReceipts(10000);
  const filtered = orgId
    ? receipts.filter(r => r.scope?.organization === orgId)
    : receipts;

  if (filtered.length < 4) {
    return {
      available: false,
      message: 'Need at least 4 executions to compute EII. The index measures improvement over time.',
      totalExecutions: filtered.length,
    };
  }

  // Split into first half (before) and second half (after).
  const sorted = filtered.sort((a, b) => new Date(a.createdAt) - new Date(b.createdAt));
  const midpoint = Math.floor(sorted.length / 2);
  const before = sorted.slice(0, midpoint);
  const after = sorted.slice(midpoint);

  const beforeMetrics = computeSetMetrics(before);
  const afterMetrics = computeSetMetrics(after);

  // Compute improvements (positive = improvement).
  const cycleTimeImprovement = beforeMetrics.cycleTimeHours > 0
    ? ((beforeMetrics.cycleTimeHours - afterMetrics.cycleTimeHours) / beforeMetrics.cycleTimeHours) * 100
    : 0;

  const knowledgeReuseImprovement = afterMetrics.knowledgeReuseRate - beforeMetrics.knowledgeReuseRate;

  const complianceImprovement = afterMetrics.complianceScore - beforeMetrics.complianceScore;

  const reworkReduction = beforeMetrics.reworkRate - afterMetrics.reworkRate;

  const auditReadinessImprovement = afterMetrics.auditReadiness - beforeMetrics.auditReadiness;

  // Weighted EII (cycle time and compliance weighted highest).
  const eii =
    (cycleTimeImprovement * 0.25) +
    (knowledgeReuseImprovement * 0.20) +
    (complianceImprovement * 0.20) +
    (reworkReduction * 0.20) +
    (auditReadinessImprovement * 0.15);

  return {
    available: true,
    orgId: orgId || 'global',
    eii: Math.round(eii * 10) / 10,
    rating: eii > 10 ? 'excellent' : eii > 5 ? 'good' : eii > 0 ? 'improving' : eii > -5 ? 'stagnant' : 'declining',
    components: {
      cycleTimeImprovement: Math.round(cycleTimeImprovement * 10) / 10,
      knowledgeReuseImprovement: Math.round(knowledgeReuseImprovement * 10) / 10,
      complianceImprovement: Math.round(complianceImprovement * 10) / 10,
      reworkReduction: Math.round(reworkReduction * 10) / 10,
      auditReadinessImprovement: Math.round(auditReadinessImprovement * 10) / 10,
    },
    before: { period: before.length + ' executions', metrics: beforeMetrics },
    after: { period: after.length + ' executions', metrics: afterMetrics },
    interpretation: interpretEII(eii),
    generatedAt: new Date().toISOString(),
  };
}

function interpretEII(eii) {
  if (eii > 15) return 'Organization is executing significantly better over time. The system is working.';
  if (eii > 5) return 'Organization is improving. Continue current trajectory and focus on weakest component.';
  if (eii > 0) return 'Marginal improvement. Identify bottlenecks using the simulation engine.';
  if (eii > -5) return 'Stagnant. No measurable improvement. Review feedback loops and pattern extraction.';
  return 'Declining. Execution is getting worse. Immediate intervention required — check governance violations and rework rate.';
}

function computeSetMetrics(receipts) {
  if (receipts.length === 0) {
    return { cycleTimeHours: 0, complianceScore: 0, knowledgeReuseRate: 0, reworkRate: 0, auditReadiness: 0 };
  }
  const cycleTimes = receipts.map(r => r.execution?.durationMs || 0).filter(d => d > 0);
  const avgCycleMs = cycleTimes.length > 0 ? cycleTimes.reduce((a, b) => a + b, 0) / cycleTimes.length : 0;
  const violations = receipts.filter(r => r.exceptions?.some(e => e.reason === 'constitutional')).length;
  const rework = receipts.filter(r => r.outcome?.result === 'rejected' || r.outcome?.result === 'edited').length;
  const reuse = receipts.filter(r => (r.patternsUsed?.length || 0) > 0).length;
  const completeReceipts = receipts.filter(r => r.evidence?.length > 0 && r.receiptHash).length;

  return {
    cycleTimeHours: Math.round(avgCycleMs / 1000 / 60 * 10) / 10,
    complianceScore: Math.round(((receipts.length - violations) / receipts.length) * 100),
    knowledgeReuseRate: Math.round((reuse / receipts.length) * 100),
    reworkRate: Math.round((rework / receipts.length) * 100),
    auditReadiness: Math.round((completeReceipts / receipts.length) * 100),
  };
}

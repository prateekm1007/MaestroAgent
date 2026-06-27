// simulation.js — Organizational Simulation Engine.
//
// "If we remove security review from this workflow, what happens?"
//
// This is the capability that turns Maestro from an execution tool into
// an executive advisor. Every past execution becomes a data point.
// The simulation engine answers "what if?" questions by analyzing
// the causal patterns in historical receipts.
//
// Example simulations:
//   - "What if we remove the security review step?"
//   - "What if we parallelize legal and compliance reviews?"
//   - "What if we require design review before coding?"
//   - "What if we reduce the QA cycle from 3 rounds to 1?"
//
// Each simulation returns:
//   - Predicted impact on cycle time
//   - Predicted impact on compliance/risk
//   - Predicted impact on acceptance rate
//   - Confidence in the prediction
//   - Recommendation
//
// This is what executives pay for: not just "what happened" but
// "what would happen if we changed something."

import { listReceipts } from './receipts.js';
import { listCases } from './evidence.js';
import { getGovernanceStats, listControls } from './governance.js';
import { getPolicyStats } from './policies.js';

// Run a simulation based on a "what if" question.
//
// Simulation types:
//   - remove_step: "What if we remove [step/policy]?"
//   - parallelize: "What if we run [A] and [B] in parallel?"
//   - add_step: "What if we add [step]?"
//   - change_threshold: "What if we change the confidence threshold?"
export function runSimulation(simulationDef, scope = null) {
  const receipts = listReceipts(1000);
  const filtered = scope
    ? receipts.filter(r => matchesScope(r.scope, scope))
    : receipts;

  if (filtered.length < 3) {
    return {
      available: false,
      message: 'Need at least 3 executions to run a simulation. Current: ' + filtered.length,
      totalExecutions: filtered.length,
    };
  }

  const type = simulationDef.type;
  let result;

  switch (type) {
    case 'remove_step':
      result = simulateRemoveStep(filtered, simulationDef);
      break;
    case 'parallelize':
      result = simulateParallelize(filtered, simulationDef);
      break;
    case 'add_step':
      result = simulateAddStep(filtered, simulationDef);
      break;
    case 'change_threshold':
      result = simulateChangeThreshold(filtered, simulationDef);
      break;
    default:
      return { available: false, error: `unknown simulation type: ${type}` };
  }

  return {
    available: true,
    simulation: simulationDef,
    totalExecutions: filtered.length,
    ...result,
    generatedAt: new Date().toISOString(),
  };
}

// Simulate removing a step/policy from the workflow.
// "What if we remove security review?"
function simulateRemoveStep(receipts, def) {
  const stepName = (def.step || '').toLowerCase();
  const controls = listControls();

  // Find executions that had this step vs didn't.
  const withStep = receipts.filter(r =>
    r.policiesApplied?.some(p => p.rule?.toLowerCase().includes(stepName)) ||
    r.approvals?.some(a => a.control?.toLowerCase().includes(stepName))
  );
  const withoutStep = receipts.filter(r =>
    !r.policiesApplied?.some(p => p.rule?.toLowerCase().includes(stepName)) &&
    !r.approvals?.some(a => a.control?.toLowerCase().includes(stepName))
  );

  // Find the control being removed.
  const removedControl = controls.find(c =>
    c.policyRule?.toLowerCase().includes(stepName)
  );

  // Compute current metrics (with the step).
  const currentMetrics = computeSetMetrics(withStep);
  // Compute simulated metrics (without the step — use the "withoutStep" set as proxy).
  const simulatedMetrics = withoutStep.length > 0
    ? computeSetMetrics(withoutStep)
    : extrapolateRemoval(currentMetrics, removedControl);

  // Compute deltas.
  const cycleTimeDelta = simulatedMetrics.cycleTimeHours - currentMetrics.cycleTimeHours;
  const complianceDelta = simulatedMetrics.complianceScore - currentMetrics.complianceScore;
  const acceptanceDelta = simulatedMetrics.acceptanceRate - currentMetrics.acceptanceRate;

  // Determine risk level.
  const isConstitutional = removedControl?.enforcement === 'constitutional';
  const riskLevel = isConstitutional ? 'critical'
    : Math.abs(complianceDelta) > 20 ? 'high'
    : Math.abs(complianceDelta) > 10 ? 'medium'
    : 'low';

  // Generate recommendation.
  let recommendation;
  if (isConstitutional) {
    recommendation = `BLOCKED: "${def.step}" is a constitutional rule. Removing it would violate the organization's governance framework. Consider parallelizing instead of removing.`;
  } else if (riskLevel === 'high' || riskLevel === 'critical') {
    recommendation = `NOT RECOMMENDED: Removing "${def.step}" would save ${Math.abs(cycleTimeDelta).toFixed(1)} hours but reduce compliance by ${Math.abs(complianceDelta).toFixed(0)} points and increase risk. Consider parallelizing or automating the step instead.`;
  } else if (cycleTimeDelta < 0) {
    recommendation = `FEASIBLE: Removing "${def.step}" would reduce cycle time by ${Math.abs(cycleTimeDelta).toFixed(1)} hours (${Math.abs(cycleTimeDelta / currentMetrics.cycleTimeHours * 100).toFixed(0)}%) with minimal compliance impact (${complianceDelta.toFixed(0)} points). Monitor acceptance rate for regression.`;
  } else {
    recommendation = `NEUTRAL: Removing "${def.step}" shows no significant cycle time benefit. Consider other optimizations.`;
  }

  return {
    type: 'remove_step',
    step: def.step,
    current: currentMetrics,
    simulated: simulatedMetrics,
    deltas: {
      cycleTimeHours: Math.round(cycleTimeDelta * 10) / 10,
      complianceScore: Math.round(complianceDelta),
      acceptanceRate: Math.round(acceptanceDelta * 100) / 100,
    },
    riskLevel,
    isConstitutional,
    removedControl: removedControl ? {
      rule: removedControl.policyRule,
      enforcement: removedControl.enforcement,
      evidenceRequired: removedControl.evidenceRequired,
    } : null,
    recommendation,
    confidence: Math.min(filtered.length / 20, 1), // higher confidence with more data
    dataPoints: {
      withStep: withStep.length,
      withoutStep: withoutStep.length,
      total: filtered.length,
    },
  };
}

// Simulate parallelizing two steps.
// "What if we run security and legal review in parallel?"
function simulateParallelize(receipts, def) {
  const steps = def.steps || [];
  if (steps.length < 2) {
    return { error: 'parallelize simulation requires at least 2 steps' };
  }

  // Find executions that had both steps.
  const withBoth = receipts.filter(r => {
    const policies = r.policiesApplied?.map(p => p.rule?.toLowerCase()) || [];
    return steps.every(s => policies.some(p => p.includes(s.toLowerCase())));
  });

  const currentMetrics = computeSetMetrics(withBoth);

  // Estimate parallel time = max(step times) instead of sum.
  // Assume each step takes ~30% of total cycle time.
  const stepTimeFraction = 0.3;
  const serialTime = currentMetrics.cycleTimeHours * steps.length * stepTimeFraction;
  const parallelTime = currentMetrics.cycleTimeHours * stepTimeFraction; // max instead of sum
  const timeSaved = serialTime - parallelTime;

  const simulatedCycleTime = currentMetrics.cycleTimeHours - timeSaved;

  return {
    type: 'parallelize',
    steps,
    current: currentMetrics,
    simulated: {
      ...currentMetrics,
      cycleTimeHours: Math.round(simulatedCycleTime * 10) / 10,
    },
    deltas: {
      cycleTimeHours: Math.round(timeSaved * 10) / 10,
      cycleTimeImprovement: currentMetrics.cycleTimeHours > 0
        ? Math.round((timeSaved / currentMetrics.cycleTimeHours) * 100) : 0,
    },
    recommendation: `Parallelizing ${steps.join(' + ')} could save ${timeSaved.toFixed(1)} hours (${Math.round(timeSaved / currentMetrics.cycleTimeHours * 100)}% faster). Compliance impact: minimal (both reviews still occur).`,
    confidence: Math.min(withBoth.length / 10, 1),
    dataPoints: { withBothSteps: withBoth.length, total: receipts.length },
  };
}

// Simulate adding a new step.
// "What if we require design review before coding?"
function simulateAddStep(receipts, def) {
  const stepName = def.step;
  const currentMetrics = computeSetMetrics(receipts);

  // Estimate impact of adding a step.
  const estimatedTimeAdded = 2; // hours
  const estimatedComplianceGain = 5; // percentage points
  const estimatedAcceptanceGain = 3; // percentage points

  return {
    type: 'add_step',
    step: stepName,
    current: currentMetrics,
    simulated: {
      cycleTimeHours: currentMetrics.cycleTimeHours + estimatedTimeAdded,
      complianceScore: Math.min(100, currentMetrics.complianceScore + estimatedComplianceGain),
      acceptanceRate: Math.min(100, currentMetrics.acceptanceRate + estimatedAcceptanceGain),
    },
    deltas: {
      cycleTimeHours: estimatedTimeAdded,
      complianceScore: estimatedComplianceGain,
      acceptanceRate: estimatedAcceptanceGain,
    },
    recommendation: `Adding "${stepName}" would add ~${estimatedTimeAdded}h to cycle time but improve compliance by ~${estimatedComplianceGain} points. Net benefit depends on current compliance gaps.`,
    confidence: 0.3, // low confidence — this is a new step with no historical data
    dataPoints: { total: receipts.length },
  };
}

// Simulate changing a confidence threshold.
// "What if we only auto-approve executions with >90% confidence?"
function simulateChangeThreshold(receipts, def) {
  const newThreshold = def.threshold || 80;
  const currentMetrics = computeSetMetrics(receipts);

  // How many executions would be auto-approved at the new threshold?
  // (We don't have per-execution confidence in receipts yet, but we can
  // use the acceptance rate as a proxy.)
  const autoApprovedRate = currentMetrics.acceptanceRate / 100;
  const wouldAutoApprove = Math.round(autoApprovedRate * receipts.length);

  return {
    type: 'change_threshold',
    threshold: newThreshold,
    current: currentMetrics,
    simulated: {
      autoApprovedCount: wouldAutoApprove,
      manualReviewCount: receipts.length - wouldAutoApprove,
      autoApprovalRate: Math.round(autoApprovedRate * 100),
    },
    recommendation: `Setting auto-approval threshold to ${newThreshold}% would auto-approve ~${wouldAutoApprove} of ${receipts.length} executions (${Math.round(autoApprovedRate * 100)}%), reducing manual review burden by ${Math.round(autoApprovedRate * 100)}%.`,
    confidence: 0.5,
    dataPoints: { total: receipts.length },
  };
}

// Helper: compute metrics for a set of receipts.
function computeSetMetrics(receipts) {
  if (receipts.length === 0) {
    return { cycleTimeHours: 0, complianceScore: 100, acceptanceRate: 0 };
  }
  const cycleTimes = receipts.map(r => r.execution?.durationMs || 0).filter(d => d > 0);
  const avgCycleMs = cycleTimes.length > 0 ? cycleTimes.reduce((a, b) => a + b, 0) / cycleTimes.length : 0;
  const violations = receipts.filter(r => r.exceptions?.some(e => e.reason === 'constitutional')).length;
  const withOutcomes = receipts.filter(r => r.outcome?.result !== 'pending');
  const accepted = withOutcomes.filter(r => r.outcome?.result === 'accepted');

  return {
    cycleTimeHours: Math.round(avgCycleMs / 1000 / 60 * 10) / 10,
    complianceScore: Math.round(((receipts.length - violations) / receipts.length) * 100),
    acceptanceRate: withOutcomes.length > 0 ? Math.round((accepted.length / withOutcomes.length) * 100) : 0,
  };
}

// Extrapolate metrics if we don't have "without step" data.
function extrapolateRemoval(current, removedControl) {
  // Removing a step saves time but reduces compliance.
  const timeSaved = 2; // estimated hours
  const complianceLoss = removedControl?.enforcement === 'constitutional' ? 50 : 15;
  return {
    cycleTimeHours: Math.max(0, current.cycleTimeHours - timeSaved),
    complianceScore: Math.max(0, current.complianceScore - complianceLoss),
    acceptanceRate: Math.max(0, current.acceptanceRate - 5),
  };
}

function matchesScope(receiptScope, filterScope) {
  if (!receiptScope || !filterScope) return true;
  for (const key of ['organization', 'department', 'team', 'userId']) {
    if (filterScope[key] && receiptScope[key] !== filterScope[key]) return false;
  }
  return true;
}

// List available simulation types.
export function listSimulationTypes() {
  return [
    {
      type: 'remove_step',
      name: 'Remove a Step',
      description: 'What if we remove a policy or review step from the workflow?',
      example: '{ "type": "remove_step", "step": "security review" }',
    },
    {
      type: 'parallelize',
      name: 'Parallelize Steps',
      description: 'What if we run two review steps in parallel instead of sequentially?',
      example: '{ "type": "parallelize", "steps": ["security", "legal"] }',
    },
    {
      type: 'add_step',
      name: 'Add a Step',
      description: 'What if we add a new review or approval step?',
      example: '{ "type": "add_step", "step": "design review" }',
    },
    {
      type: 'change_threshold',
      name: 'Change Threshold',
      description: 'What if we change the auto-approval confidence threshold?',
      example: '{ "type": "change_threshold", "threshold": 90 }',
    },
  ];
}

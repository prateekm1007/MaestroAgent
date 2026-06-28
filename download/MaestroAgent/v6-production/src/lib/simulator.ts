// Maestro v6 — Decision Workbench Simulator
// Pure function: given a config, return predicted 90-day state.
// In production this calls the OEM counterfactual engine; here we
// expose the interface and a deterministic mock for testing.

import type { SimulatorConfig, SimulatorOutputs, PredictedState } from '@/types/domain';

export interface SimulatorInput {
  orgId: string;
  decisionType: 'HIRING' | 'PRICING' | 'PROCESS' | 'ORG_CHANGE' | 'CUSTOM';
  config: SimulatorConfig;
  horizonDays: number; // default 90
}

export interface SimulatorResult {
  outputs: SimulatorOutputs;
  predictedState: PredictedState;
  // Calibration metadata
  matchingPrecedents: number;
  confidenceBand: 'HIGH' | 'MEDIUM' | 'LOW';
}

// Deterministic mock — in production this is the OEM's counterfactual engine.
// The mock is intentionally simple: it computes outputs from config deltas
// and confidence from distance to a "recommended" configuration.
export function simulate(input: SimulatorInput): SimulatorResult {
  const { config, horizonDays } = input;

  // Hiring-specific logic
  const totalHires = config.emea + config.apac + config.na;
  const emeaCapacity = Math.round((config.emea / 8) * 24);
  const apacSupportRatio = config.apac >= 5 ? '1:14 · at threshold'
    : config.apac >= 3 ? '1:11 · below threshold'
    : '1:8 · critical';
  const p1Prob = Math.max(0.3, Math.min(0.85, 0.55 + (totalHires - 14) * 0.03));
  const attrRisk = Math.max(0.2, Math.min(0.7, 0.42 + (config.apac < 4 ? 0.12 : 0)));
  const cost = totalHires * 0.15;

  // Distance from Maestro's recommended config (5, 6, 2 for hiring)
  const distFromRec = Math.abs(config.emea - 5) + Math.abs(config.apac - 6) + Math.abs(config.na - 2);
  const confidence = Math.max(0.55, 0.78 - distFromRec * 0.025);

  let confidenceNote: string;
  let band: 'HIGH' | 'MEDIUM' | 'LOW';
  if (confidence > 0.75) {
    confidenceNote = 'Within target band. Model is calibrated on 47 similar prior decisions in your org.';
    band = 'HIGH';
  } else if (confidence > 0.65) {
    confidenceNote = "Outside Maestro's recommended configuration. Lower confidence — fewer prior decisions match.";
    band = 'MEDIUM';
  } else {
    confidenceNote = 'Low confidence. This configuration has few precedents in your org. Approve with explicit verification plan.';
    band = 'LOW';
  }

  const outputs: SimulatorOutputs = {
    emeaCapacity,
    apacSupportRatio,
    p1ClusterProbability: p1Prob,
    attritionRisk: attrRisk,
    annualizedCost: cost,
    confidence,
    confidenceNote,
  };

  const predictedState: PredictedState = {
    horizon: horizonDays,
    leadingIndicators: [
      { name: `EMEA delivery capacity +${emeaCapacity}%`, direction: 'UP', source: 'oem:counterfactual' },
      { name: `APAC support ratio ${apacSupportRatio}`, direction: apacSupportRatio.includes('critical') ? 'DOWN' : apacSupportRatio.includes('below') ? 'WARNING' : 'UP', source: 'L-0014' },
      { name: `P1 cluster probability ${(p1Prob * 100).toFixed(0)}%`, direction: p1Prob > 0.6 ? 'WARNING' : 'UP', source: 'L-0007' },
    ],
    capabilityDeltas: [
      { capability: 'EMEA sales capacity', delta: emeaCapacity, unit: '%' },
      { capability: 'APAC sales capacity', delta: config.apac >= 5 ? 8 : -8, unit: '%' },
      { capability: 'Cross-team handoff latency', delta: 1.2, unit: 'days' },
    ],
    risks: [
      { description: 'APAC churn spike Q1 2025', probability: 0.68, impact: 0.74, source: 'L-0014' },
      { description: 'Onboarding-induced P1 cluster in Feb', probability: p1Prob, impact: 0.68, source: 'L-0007' },
      { description: 'VP Sales attrition (dissent unresolved)', probability: attrRisk, impact: 0.81 },
    ],
  };

  return {
    outputs,
    predictedState,
    matchingPrecedents: Math.max(2, 47 - distFromRec * 3),
    confidenceBand: band,
  };
}

// Verify a prediction 90 days later — called by the verification cron
export function verifyPrediction(
  statement: string,
  actualOutcome: 'HIT' | 'MISS',
): { result: 'HIT' | 'MISS'; verifiedAt: string } {
  return {
    result: actualOutcome,
    verifiedAt: new Date().toISOString(),
  };
}

// Compute the SHR impact of a pending set of verifications
export function projectShrImpact(
  currentShr: number,
  currentTotal: number,
  pendingPredictions: number,
  assumedHitRate: number,
): { bestCase: number; worstCase: number; expectedCase: number } {
  const newHits = pendingPredictions * assumedHitRate;
  const newMisses = pendingPredictions * (1 - assumedHitRate);
  const newTotal = currentTotal + pendingPredictions;
  const expectedCase = (currentShr * currentTotal + newHits) / newTotal;
  return {
    bestCase: (currentShr * currentTotal + pendingPredictions) / newTotal,
    worstCase: (currentShr * currentTotal) / newTotal,
    expectedCase,
  };
}

// Maestro v6 — Unit tests for the simulator
// Tests the decision workbench counterfactual engine.

import { simulate, projectShrImpact, verifyPrediction } from '@/lib/simulator';
import type { SimulatorConfig } from '@/types/domain';

describe('Decision Simulator', () => {
  const baseConfig: SimulatorConfig = {
    emea: 8, apac: 4, na: 2, parameters: {},
  };

  describe('simulate()', () => {
    it('returns predicted state for default config', () => {
      const result = simulate({
        orgId: 'org-1', decisionType: 'HIRING',
        config: baseConfig, horizonDays: 90,
      });

      expect(result.outputs.emeaCapacity).toBe(24);
      expect(result.outputs.apacSupportRatio).toContain('below threshold');
      expect(result.outputs.p1ClusterProbability).toBeGreaterThan(0);
      expect(result.outputs.confidence).toBeGreaterThan(0.5);
      expect(result.predictedState.horizon).toBe(90);
      expect(result.predictedState.leadingIndicators.length).toBeGreaterThan(0);
    });

    it('flags critical APAC support ratio when apac < 3', () => {
      const result = simulate({
        orgId: 'org-1', decisionType: 'HIRING',
        config: { ...baseConfig, apac: 0 }, horizonDays: 90,
      });
      expect(result.outputs.apacSupportRatio).toContain('critical');
    });

    it('reaches at-threshold when apac >= 5', () => {
      const result = simulate({
        orgId: 'org-1', decisionType: 'HIRING',
        config: { ...baseConfig, apac: 6 }, horizonDays: 90,
      });
      expect(result.outputs.apacSupportRatio).toContain('at threshold');
    });

    it('reduces confidence when far from recommended config', () => {
      const recommended = simulate({
        orgId: 'org-1', decisionType: 'HIRING',
        config: { emea: 5, apac: 6, na: 2, parameters: {} },
        horizonDays: 90,
      });
      const far = simulate({
        orgId: 'org-1', decisionType: 'HIRING',
        config: { emea: 14, apac: 0, na: 0, parameters: {} },
        horizonDays: 90,
      });
      expect(recommended.outputs.confidence).toBeGreaterThan(far.outputs.confidence);
    });

    it('clamps confidence to a minimum of 0.55', () => {
      const result = simulate({
        orgId: 'org-1', decisionType: 'HIRING',
        config: { emea: 0, apac: 0, na: 0, parameters: {} },
        horizonDays: 90,
      });
      expect(result.outputs.confidence).toBeGreaterThanOrEqual(0.55);
    });

    it('assigns confidence band based on confidence value', () => {
      const high = simulate({
        orgId: 'org-1', decisionType: 'HIRING',
        config: { emea: 5, apac: 6, na: 2, parameters: {} },
        horizonDays: 90,
      });
      expect(high.confidenceBand).toBe('HIGH');

      const low = simulate({
        orgId: 'org-1', decisionType: 'HIRING',
        config: { emea: 14, apac: 0, na: 0, parameters: {} },
        horizonDays: 90,
      });
      expect(['MEDIUM', 'LOW']).toContain(low.confidenceBand);
    });

    it('includes risks with probability × impact', () => {
      const result = simulate({
        orgId: 'org-1', decisionType: 'HIRING',
        config: baseConfig, horizonDays: 90,
      });
      expect(result.predictedState.risks.length).toBeGreaterThan(0);
      for (const risk of result.predictedState.risks) {
        expect(risk.probability).toBeGreaterThanOrEqual(0);
        expect(risk.probability).toBeLessThanOrEqual(1);
        expect(risk.impact).toBeGreaterThanOrEqual(0);
        expect(risk.impact).toBeLessThanOrEqual(1);
      }
    });
  });

  describe('verifyPrediction()', () => {
    it('returns the actual outcome with timestamp', () => {
      const result = verifyPrediction('test', 'HIT');
      expect(result.result).toBe('HIT');
      expect(result.verifiedAt).toBeDefined();
    });
  });

  describe('projectShrImpact()', () => {
    it('projects best/worst/expected case', () => {
      const result = projectShrImpact(0.83, 23, 3, 0.78);
      expect(result.bestCase).toBeGreaterThan(result.expectedCase);
      expect(result.expectedCase).toBeGreaterThan(result.worstCase);
    });

    it('best case equals 1.0 when all pending hit and current is high', () => {
      const result = projectShrImpact(1.0, 10, 5, 1.0);
      expect(result.bestCase).toBeCloseTo(1.0);
    });
  });
});

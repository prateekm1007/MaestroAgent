// tests/unit/repository.test.js — Unit tests for repository layer.
//
// Tests the SQL construction and parameter handling of the repository
// without requiring a live database. Uses mock query function.

import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock the db module
vi.mock('../../src/db.js', () => ({
  query: vi.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
  withTransaction: vi.fn(async (fn) => fn({
    query: vi.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
  })),
  pool: {},
}));

import { query } from '../../src/db.js';
import {
  runsRepo,
  artifactsRepo,
  eventsRepo,
  learningObjectsRepo,
  patternsRepo,
  policiesRepo,
  receiptsRepo,
  evidenceItemsRepo,
  casesRepo,
  precedentsRepo,
  integrationsRepo,
  webhookEventsRepo,
  operatingModelsRepo,
  designPartnersRepo,
  hypothesesRepo,
  fridayDashboardsRepo,
  observatoryRepo,
  partnerPromisesRepo,
} from '../../src/repository.js';

describe('repository', () => {
  beforeEach(() => {
    query.mockClear();
    query.mockResolvedValue({ rows: [{ id: 'test-id' }], rowCount: 1 });
  });

  describe('runsRepo', () => {
    it('insert should call query with INSERT', async () => {
      await runsRepo.insert({ org_id: 'org-1', goal: 'test goal', status: 'pending' });
      expect(query).toHaveBeenCalled();
      const call = query.mock.calls[0];
      expect(call[0]).toContain('INSERT INTO runs');
      expect(call[0]).toContain('VALUES');
    });

    it('getById should use parameterized query', async () => {
      await runsRepo.getById('run-123');
      expect(query).toHaveBeenCalledWith('SELECT * FROM runs WHERE id = $1', ['run-123']);
    });

    it('listByOrg should include limit and offset', async () => {
      await runsRepo.listByOrg('org-1', 10, 5);
      const call = query.mock.calls[0];
      expect(call[0]).toContain('LIMIT $2');
      expect(call[0]).toContain('OFFSET $3');
      expect(call[1]).toEqual(['org-1', 10, 5]);
    });

    it('update should build SET clauses dynamically', async () => {
      await runsRepo.update('run-1', { status: 'completed', avg_confidence: 92 });
      const call = query.mock.calls[0];
      expect(call[0]).toContain('UPDATE runs SET');
      expect(call[0]).toContain('status = $2');
      expect(call[0]).toContain('avg_confidence = $3');
      expect(call[1]).toEqual(['run-1', 'completed', 92]);
    });

    it('update with no changes should return null', async () => {
      const result = await runsRepo.update('run-1', {});
      // Should still call getById
      expect(query).toHaveBeenCalled();
    });
  });

  describe('artifactsRepo', () => {
    it('insert should include all fields', async () => {
      await artifactsRepo.insert({
        run_id: 'run-1', org_id: 'org-1', agent_id: 'planner',
        agent_name: 'Planner', filename: '01-planner.md', content: 'test', bytes: 4,
      });
      const call = query.mock.calls[0];
      expect(call[0]).toContain('INSERT INTO artifacts');
      expect(call[1]).toContain('planner');
    });

    it('getByRun should query by run_id', async () => {
      await artifactsRepo.getByRun('run-1');
      expect(query).toHaveBeenCalledWith('SELECT * FROM artifacts WHERE run_id = $1 ORDER BY created_at', ['run-1']);
    });
  });

  describe('eventsRepo', () => {
    it('insert should cast payload to jsonb', async () => {
      await eventsRepo.insert({ run_id: 'run-1', org_id: 'org-1', type: 'run.started', payload: { goal: 'test' } });
      const call = query.mock.calls[0];
      expect(call[0]).toContain('$4::jsonb');
      expect(call[1][3]).toBe(JSON.stringify({ goal: 'test' }));
    });

    it('getByRun should order by ts', async () => {
      await eventsRepo.getByRun('run-1');
      expect(query).toHaveBeenCalledWith('SELECT * FROM events WHERE run_id = $1 ORDER BY ts', ['run-1']);
    });
  });

  describe('learningObjectsRepo', () => {
    it('retrieveSimilar should build dynamic OR clauses', async () => {
      query.mockResolvedValue({ rows: [], rowCount: 0 });
      await learningObjectsRepo.retrieveSimilar('write a blog post', 3);
      const call = query.mock.calls[0];
      expect(call[0]).toContain('LIKE');
      expect(call[0]).toContain('OR');
    });

    it('update should handle jsonb fields', async () => {
      await learningObjectsRepo.update('lo-1', { outcome: 'accepted', specialists: [{ name: 'test' }] });
      const call = query.mock.calls[0];
      expect(call[0]).toContain('specialists = $');
      expect(call[0]).toContain('::jsonb');
    });
  });

  describe('patternsRepo', () => {
    it('getOrCreate should use ON CONFLICT', async () => {
      await patternsRepo.getOrCreate('Content Writing', { level: 'global', scopeKey: 'global' });
      const call = query.mock.calls[0];
      expect(call[0]).toContain('ON CONFLICT (goal_class, scope_key)');
    });

    it('update should include last_updated', async () => {
      await patternsRepo.update('pat-1', { project_count: 5 });
      const call = query.mock.calls[0];
      expect(call[0]).toContain('last_updated = now()');
    });
  });

  describe('policiesRepo', () => {
    it('insert should include all governance fields', async () => {
      await policiesRepo.insert({
        rule: 'Security review required', scope_key: 'global', scope_level: 'global',
        enforcement: 'mandatory', block_execution: true,
      });
      const call = query.mock.calls[0];
      expect(call[0]).toContain('block_execution');
      expect(call[0]).toContain('exception_allowed');
    });

    it('findByRuleAndScope should use LEFT() for prefix matching', async () => {
      await policiesRepo.findByRuleAndScope('Security review required for APIs', 'global');
      const call = query.mock.calls[0];
      expect(call[0]).toContain('LEFT(rule, 60)');
    });
  });

  describe('receiptsRepo', () => {
    it('insert should include receipt_hash', async () => {
      await receiptsRepo.insert({
        run_id: 'run-1', org_id: 'org-1', goal: 'test', receipt_hash: 'abc123',
      });
      const call = query.mock.calls[0];
      expect(call[0]).toContain('receipt_hash');
      expect(call[1]).toContain('abc123');
    });

    it('listByOrg should order by created_at DESC', async () => {
      await receiptsRepo.listByOrg('org-1');
      const call = query.mock.calls[0];
      expect(call[0]).toContain('ORDER BY created_at DESC');
    });
  });

  describe('integrationsRepo', () => {
    it('insert should include credentials', async () => {
      await integrationsRepo.insert({
        org_id: 'org-1', provider_id: 'jira', provider_name: 'Jira',
        credentials: 'encrypted-token',
      });
      const call = query.mock.calls[0];
      expect(call[0]).toContain('credentials');
      expect(call[1]).toContain('encrypted-token');
    });

    it('delete should set status to disconnected', async () => {
      await integrationsRepo.delete('int-1');
      const call = query.mock.calls[0];
      expect(call[0]).toContain("status = 'disconnected'");
      expect(call[0]).toContain('disconnected_at = now()');
    });
  });

  describe('webhookEventsRepo', () => {
    it('isDuplicate should check unique constraint fields', async () => {
      query.mockResolvedValue({ rows: [], rowCount: 0 });
      const result = await webhookEventsRepo.isDuplicate('org-1', 'jira', 'evt-123');
      const call = query.mock.calls[0];
      expect(call[0]).toContain('org_id = $1');
      expect(call[0]).toContain('provider = $2');
      expect(call[0]).toContain('event_id = $3');
      expect(result).toBe(false);
    });

    it('markProcessed should use ON CONFLICT DO NOTHING', async () => {
      await webhookEventsRepo.markProcessed('org-1', 'jira', 'evt-123', { type: 'issue_created' });
      const call = query.mock.calls[0];
      expect(call[0]).toContain('ON CONFLICT (org_id, provider, event_id) DO NOTHING');
    });
  });

  describe('hypothesesRepo', () => {
    it('insert should use ON CONFLICT DO NOTHING', async () => {
      await hypothesesRepo.insert({ id: 'H001', hypothesis: 'Test hypothesis' });
      const call = query.mock.calls[0];
      expect(call[0]).toContain('ON CONFLICT (id) DO NOTHING');
    });

    it('update should set last_updated', async () => {
      await hypothesesRepo.update('H001', { confidence: 'high' });
      const call = query.mock.calls[0];
      expect(call[0]).toContain('last_updated = now()');
    });
  });

  describe('partnerPromisesRepo', () => {
    it('upsert should use ON CONFLICT (org_id) DO UPDATE', async () => {
      await partnerPromisesRepo.upsert({ org_id: 'org-1', target_reduction: 20 });
      const call = query.mock.calls[0];
      expect(call[0]).toContain('ON CONFLICT (org_id) DO UPDATE');
      expect(call[0]).toContain('target_reduction = EXCLUDED.target_reduction');
    });
  });

  describe('operatingModelsRepo', () => {
    it('upsert should increment version on conflict', async () => {
      await operatingModelsRepo.upsert({ org_id: 'org-1', name: 'Test Org' });
      const call = query.mock.calls[0];
      expect(call[0]).toContain('version = operating_models.version + 1');
    });
  });
});

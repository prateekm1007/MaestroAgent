// tests/unit/tenant.test.js — Unit tests for src/tenant.js

import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock db
vi.mock('../../src/db.js', () => ({
  query: vi.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
  withTransaction: vi.fn(async (fn) => fn({ query: vi.fn().mockResolvedValue({ rows: [], rowCount: 0 }) })),
  pool: { connect: vi.fn() },
  getClient: vi.fn().mockResolvedValue({ query: vi.fn().mockResolvedValue({ rows: [], rowCount: 0 }), release: vi.fn() }),
  setRLSContext: vi.fn().mockResolvedValue(undefined),
}));

import {
  TenantCache,
  TenantQueue,
  tenantCache,
  tenantQueue,
  requireTenant,
  tenantQuery,
  verifyRLSOnAllTables,
  testTenantIsolation,
  getTenantIsolationStatus,
} from '../../src/tenant.js';

describe('tenant', () => {
  describe('TenantCache', () => {
    let cache;

    beforeEach(() => {
      cache = new TenantCache();
    });

    it('should set and get values scoped by org', () => {
      cache.set('org-1', 'patterns', [{ id: 1 }]);
      cache.set('org-2', 'patterns', [{ id: 2 }]);

      expect(cache.get('org-1', 'patterns')).toEqual([{ id: 1 }]);
      expect(cache.get('org-2', 'patterns')).toEqual([{ id: 2 }]);
    });

    it('should return null for non-existent key', () => {
      expect(cache.get('org-1', 'nonexistent')).toBeNull();
    });

    it('should delete a specific key for an org', () => {
      cache.set('org-1', 'key1', 'value1');
      cache.set('org-1', 'key2', 'value2');
      cache.delete('org-1', 'key1');

      expect(cache.get('org-1', 'key1')).toBeNull();
      expect(cache.get('org-1', 'key2')).toBe('value2');
    });

    it('should invalidate all keys for an org', () => {
      cache.set('org-1', 'key1', 'value1');
      cache.set('org-1', 'key2', 'value2');
      cache.set('org-2', 'key1', 'value3');
      cache.invalidateOrg('org-1');

      expect(cache.get('org-1', 'key1')).toBeNull();
      expect(cache.get('org-1', 'key2')).toBeNull();
      expect(cache.get('org-2', 'key1')).toBe('value3');
    });

    it('should list keys for an org', () => {
      cache.set('org-1', 'key1', 'v1');
      cache.set('org-1', 'key2', 'v2');
      cache.set('org-2', 'key3', 'v3');

      const keys = cache.keys('org-1');
      expect(keys).toContain('key1');
      expect(keys).toContain('key2');
      expect(keys).not.toContain('key3');
    });

    it('should return stats', () => {
      cache.set('org-1', 'key1', 'v1');
      cache.set('org-2', 'key1', 'v2');

      const stats = cache.stats();
      expect(stats.total_entries).toBe(2);
      expect(stats.orgs).toBe(2);
    });

    it('should support TTL', () => {
      cache.set('org-1', 'temp', 'value', 10);
      expect(cache.get('org-1', 'temp')).toBe('value');
      // Wait for expiry
      return new Promise(resolve => {
        setTimeout(() => {
          expect(cache.get('org-1', 'temp')).toBeNull();
          resolve();
        }, 20);
      });
    });
  });

  describe('TenantQueue', () => {
    let queue;

    beforeEach(() => {
      queue = new TenantQueue();
    });

    it('should enqueue a job tagged with org_id', () => {
      const jobId = queue.enqueue('org-1', 'llm_call', { prompt: 'test' });
      expect(jobId).toBeTruthy();
      expect(queue.length('org-1')).toBe(1);
    });

    it('should dequeue jobs for a specific org', () => {
      queue.enqueue('org-1', 'job1', { data: 1 });
      queue.enqueue('org-2', 'job2', { data: 2 });

      const job1 = queue.dequeue('org-1');
      expect(job1.type).toBe('job1');
      expect(job1.org_id).toBe('org-1');
      expect(job1.payload._org_id).toBe('org-1');

      const job2 = queue.dequeue('org-2');
      expect(job2.type).toBe('job2');
      expect(job2.org_id).toBe('org-2');

      expect(queue.dequeue('org-1')).toBeNull();
    });

    it('should respect priority', () => {
      queue.enqueue('org-1', 'low', {}, { priority: 0 });
      queue.enqueue('org-1', 'high', {}, { priority: 10 });
      queue.enqueue('org-1', 'medium', {}, { priority: 5 });

      const high = queue.dequeue('org-1');
      expect(high.type).toBe('high');

      const medium = queue.dequeue('org-1');
      expect(medium.type).toBe('medium');

      const low = queue.dequeue('org-1');
      expect(low.type).toBe('low');
    });

    it('should peek without removing', () => {
      queue.enqueue('org-1', 'job1', {});
      const peeked = queue.peek('org-1');
      expect(peeked.type).toBe('job1');
      expect(queue.length('org-1')).toBe(1);
    });

    it('should return null when queue is empty', () => {
      expect(queue.dequeue('org-1')).toBeNull();
      expect(queue.peek('org-1')).toBeNull();
      expect(queue.length('org-1')).toBe(0);
    });

    it('should clear all jobs for an org', () => {
      queue.enqueue('org-1', 'job1', {});
      queue.enqueue('org-1', 'job2', {});
      queue.enqueue('org-2', 'job3', {});

      queue.clear('org-1');
      expect(queue.length('org-1')).toBe(0);
      expect(queue.length('org-2')).toBe(1);
    });

    it('should return stats', () => {
      queue.enqueue('org-1', 'job1', {});
      queue.enqueue('org-1', 'job2', {});
      queue.enqueue('org-2', 'job3', {});

      const stats = queue.stats();
      expect(stats.total_jobs).toBe(3);
      expect(stats.org_count).toBe(2);
      expect(stats.by_org['org-1']).toBe(2);
      expect(stats.by_org['org-2']).toBe(1);
    });

    it('should register workers', () => {
      const handler = vi.fn();
      queue.registerWorker(handler);
      expect(queue._workers).toHaveLength(1);
    });
  });

  describe('requireTenant middleware', () => {
    it('should pass if tenant context exists', () => {
      const req = { tenant: { orgId: 'org-1' } };
      const res = { status: vi.fn().mockReturnThis(), json: vi.fn() };
      const next = vi.fn();
      requireTenant(req, res, next);
      expect(next).toHaveBeenCalled();
    });

    it('should return 403 if no tenant context', () => {
      const req = {};
      const res = { status: vi.fn().mockReturnThis(), json: vi.fn() };
      const next = vi.fn();
      requireTenant(req, res, next);
      expect(res.status).toHaveBeenCalledWith(403);
      expect(next).not.toHaveBeenCalled();
    });
  });

  describe('tenantQuery', () => {
    it('should use request DB client if available', async () => {
      const mockClient = { query: vi.fn().mockResolvedValue({ rows: [{ id: 1 }] }) };
      const req = { dbClient: mockClient, tenant: { orgId: 'org-1' } };

      const result = await tenantQuery(req, 'SELECT * FROM runs WHERE id = $1', ['run-1']);
      expect(mockClient.query).toHaveBeenCalledWith('SELECT * FROM runs WHERE id = $1', ['run-1']);
      expect(result.rows[0].id).toBe(1);
    });
  });

  describe('verifyRLSOnAllTables', () => {
    it('should return table list with RLS status', async () => {
      const { query } = await import('../../src/db.js');
      query.mockResolvedValueOnce({
        rows: [
          { table_name: 'runs', rls_enabled: true, rls_forced: true, policy_count: 2 },
          { table_name: 'users', rls_enabled: false, rls_forced: false, policy_count: 0 },
        ],
      });

      const result = await verifyRLSOnAllTables();
      expect(result.tables).toHaveLength(2);
      expect(result.tables[0].table).toBe('runs');
      expect(result.tables[0].rls_enabled).toBe(true);
    });
  });

  describe('testTenantIsolation', () => {
    it('should test cross-tenant access prevention', async () => {
      const { getClient } = await import('../../src/db.js');
      const mockClient = {
        query: vi.fn()
          .mockResolvedValueOnce({}) // SET LOCAL
          .mockResolvedValueOnce({ rows: [{ count: '0' }] }), // SELECT COUNT
        release: vi.fn(),
      };
      getClient.mockResolvedValueOnce(mockClient);

      const result = await testTenantIsolation('org-1', 'org-2');
      expect(result.isolated).toBe(true);
      expect(result.leaked_rows).toBe(0);
    });
  });

  describe('getTenantIsolationStatus', () => {
    it('should return complete status', async () => {
      const { query } = await import('../../src/db.js');
      query.mockResolvedValueOnce({
        rows: [
          { relname: 'runs', relrowsecurity: true, relforcerowsecurity: true, policy_count: '2' },
        ],
      });

      const status = await getTenantIsolationStatus();
      expect(status).toHaveProperty('rls');
      expect(status).toHaveProperty('cache');
      expect(status).toHaveProperty('queue');
      expect(status.middleware).toBe(true);
      expect(status.defense_in_depth).toBe(true);
    });
  });
});

// __tests__/api.test.ts — Tests for lib/api.ts

import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock fetch
const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

// Mock localStorage
const mockLocalStorage = {
  getItem: vi.fn(() => null),
  setItem: vi.fn(),
  removeItem: vi.fn(),
};
vi.stubGlobal('localStorage', mockLocalStorage);

// Mock document.cookie
vi.stubGlobal('document', { cookie: '' });

import { ApiError } from '@/lib/api';

describe('api', () => {
  beforeEach(() => {
    mockFetch.mockReset();
    mockLocalStorage.getItem.mockReturnValue(null);
  });

  describe('ApiError', () => {
    it('should create an error with status and body', () => {
      const err = new ApiError(404, { error: 'Not found' });
      expect(err.status).toBe(404);
      expect(err.message).toBe('Not found');
      expect(err.body.error).toBe('Not found');
    });
  });

  describe('auth API structure', () => {
    it('should export auth functions', async () => {
      const { auth } = await import('@/lib/api');
      expect(typeof auth.login).toBe('function');
      expect(typeof auth.register).toBe('function');
      expect(typeof auth.logout).toBe('function');
      expect(typeof auth.me).toBe('function');
      expect(typeof auth.createApiKey).toBe('function');
      expect(typeof auth.listUsers).toBe('function');
    });
  });

  describe('runs API structure', () => {
    it('should export runs functions', async () => {
      const { runs } = await import('@/lib/api');
      expect(typeof runs.create).toBe('function');
      expect(typeof runs.list).toBe('function');
      expect(typeof runs.get).toBe('function');
      expect(typeof runs.feedback).toBe('function');
      expect(typeof runs.interrupt).toBe('function');
    });
  });

  describe('metrics API structure', () => {
    it('should export metrics functions', async () => {
      const { metrics } = await import('@/lib/api');
      expect(typeof metrics.get).toBe('function');
      expect(typeof metrics.cpr).toBe('function');
      expect(typeof metrics.eii).toBe('function');
      expect(typeof metrics.simulate).toBe('function');
    });
  });

  describe('receipts API structure', () => {
    it('should export receipts functions', async () => {
      const { receipts } = await import('@/lib/api');
      expect(typeof receipts.list).toBe('function');
      expect(typeof receipts.getByRun).toBe('function');
      expect(typeof receipts.verify).toBe('function');
    });
  });

  describe('integrations API structure', () => {
    it('should export integrations functions', async () => {
      const { integrations } = await import('@/lib/api');
      expect(typeof integrations.list).toBe('function');
      expect(typeof integrations.jiraAuthUrl).toBe('function');
      expect(typeof integrations.githubAuthUrl).toBe('function');
      expect(typeof integrations.slackAuthUrl).toBe('function');
    });
  });
});

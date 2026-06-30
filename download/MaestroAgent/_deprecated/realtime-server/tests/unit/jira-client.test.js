// tests/unit/jira-client.test.js — Unit tests for Jira API client.
//
// Tests the JiraClient class without making real HTTP calls.
// Uses undici's MockAgent to intercept requests.

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { MockAgent, setGlobalDispatcher } from 'undici';
import { JiraClient, JiraApiError, getAuthorizationUrl } from '../../src/integrations/jira-client.js';

describe('jira-client', () => {
  let mockAgent;
  let mockPool;

  beforeEach(() => {
    mockAgent = new MockAgent();
    mockAgent.disableNetConnect();
    setGlobalDispatcher(mockAgent);
    mockPool = mockAgent.get('https://api.atlassian.com');
  });

  afterEach(() => {
    mockAgent.enableNetConnect();
  });

  function createClient(overrides = {}) {
    return new JiraClient({
      cloudId: 'test-cloud-id',
      accessToken: 'test-access-token',
      refreshToken: 'test-refresh-token',
      onTokenRefresh: vi.fn(),
      logger: { warn: vi.fn(), error: vi.fn(), log: vi.fn() },
      ...overrides,
    });
  }

  describe('constructor', () => {
    it('should set base URLs with cloud ID', () => {
      const client = createClient();
      expect(client.cloudId).toBe('test-cloud-id');
      expect(client.accessToken).toBe('test-access-token');
    });
  });

  function mockReply(method, path, statusCode, body, headers = {}) {
    mockPool.intercept({ method, path }).reply(statusCode, body, {
      headers: { 'content-type': 'application/json', ...headers },
    });
  }

  describe('createIssue', () => {
    it('should POST to /issue with correct fields', async () => {
      mockReply('POST', '/ex/jira/test-cloud-id/rest/api/3/issue', 201, {
        id: '10001', key: 'ENG-123', self: 'https://api.atlassian.com/ex/jira/test-cloud-id/rest/api/3/issue/10001',
      });

      const client = createClient();
      const result = await client.createIssue({
        projectKey: 'ENG',
        summary: 'Test issue',
        description: 'Test description',
        issueType: 'Task',
      });

      expect(result.key).toBe('ENG-123');
      expect(result.id).toBe('10001');
    });

    it('should handle API error (400)', async () => {
      mockReply('POST', '/ex/jira/test-cloud-id/rest/api/3/issue', 400, { errorMessages: ['Project does not exist'] });

      const client = createClient();
      await expect(client.createIssue({
        projectKey: 'INVALID',
        summary: 'Test',
      })).rejects.toThrow('Project does not exist');
    });
  });

  describe('getIssue', () => {
    it('should GET issue by key', async () => {
      mockReply('GET', '/ex/jira/test-cloud-id/rest/api/3/issue/ENG-123', 200, {
        id: '10001', key: 'ENG-123', fields: { summary: 'Test' },
      });

      const client = createClient();
      const result = await client.getIssue('ENG-123');
      expect(result.key).toBe('ENG-123');
    });

    it('should pass fields parameter', async () => {
      mockReply('GET', '/ex/jira/test-cloud-id/rest/api/3/issue/ENG-123?fields=summary%2Cstatus', 200, {
        id: '10001', key: 'ENG-123', fields: { summary: 'Test', status: {} },
      });

      const client = createClient();
      const result = await client.getIssue('ENG-123', ['summary', 'status']);
      expect(result.key).toBe('ENG-123');
    });
  });

  describe('updateIssue', () => {
    it('should PUT to /issue/:key', async () => {
      mockPool.intercept({
        method: 'PUT',
        path: '/ex/jira/test-cloud-id/rest/api/3/issue/ENG-123',
      }).reply(204, '', { headers: { 'content-type': 'text/plain' } });

      const client = createClient();
      await client.updateIssue('ENG-123', { summary: 'Updated' });
    });
  });

  describe('addComment', () => {
    it('should POST comment to issue', async () => {
      mockReply('POST', '/ex/jira/test-cloud-id/rest/api/3/issue/ENG-123/comment', 201, {
        id: '100', body: { type: 'doc' }, created: '2026-01-01T00:00:00.000Z',
      });

      const client = createClient();
      const result = await client.addComment('ENG-123', 'Test comment');
      expect(result.id).toBe('100');
    });
  });

  describe('searchIssues', () => {
    it('should POST to /search with JQL', async () => {
      mockReply('POST', '/ex/jira/test-cloud-id/rest/api/3/search', 200, {
        issues: [{ id: '1', key: 'ENG-1' }, { id: '2', key: 'ENG-2' }],
        total: 2, startAt: 0, maxResults: 50,
      });

      const client = createClient();
      const result = await client.searchIssues('project = ENG ORDER BY created DESC');
      expect(result.issues).toHaveLength(2);
      expect(result.total).toBe(2);
    });
  });

  describe('getTransitions', () => {
    it('should GET transitions for issue', async () => {
      mockReply('GET', '/ex/jira/test-cloud-id/rest/api/3/issue/ENG-123/transitions', 200, {
        transitions: [
          { id: '11', name: 'To Do' },
          { id: '21', name: 'In Progress' },
          { id: '31', name: 'Done' },
        ],
      });

      const client = createClient();
      const result = await client.getTransitions('ENG-123');
      expect(result.transitions).toHaveLength(3);
      expect(result.transitions[1].name).toBe('In Progress');
    });
  });

  describe('transitionIssue', () => {
    it('should POST transition', async () => {
      mockPool.intercept({
        method: 'POST',
        path: '/ex/jira/test-cloud-id/rest/api/3/issue/ENG-123/transitions',
      }).reply(204, '', { headers: { 'content-type': 'text/plain' } });

      const client = createClient();
      await client.transitionIssue('ENG-123', '21');
    });
  });

  describe('addRemoteLink', () => {
    it('should POST remote link', async () => {
      mockReply('POST', '/ex/jira/test-cloud-id/rest/api/3/issue/ENG-123/remotelink', 201, { id: '100' });

      const client = createClient();
      const result = await client.addRemoteLink('ENG-123', {
        url: 'https://maestro.app/runs/123',
        title: 'Maestro Run',
      });
      expect(result.id).toBe('100');
    });
  });

  describe('error handling', () => {
    it('should throw JiraApiError on 403', async () => {
      mockReply('GET', '/ex/jira/test-cloud-id/rest/api/3/issue/ENG-999', 403, { errorMessages: ['Permission denied'] });

      const client = createClient();
      try {
        await client.getIssue('ENG-999');
        expect.fail('Should have thrown');
      } catch (err) {
        expect(err).toBeInstanceOf(JiraApiError);
        expect(err.statusCode).toBe(403);
        expect(err.message).toContain('Permission denied');
      }
    });

    it('should retry on 500 errors', async () => {
      // First attempt: 500
      mockPool.intercept({
        method: 'GET',
        path: '/ex/jira/test-cloud-id/rest/api/3/issue/ENG-123',
      }).reply(500, 'Internal Server Error', { headers: { 'content-type': 'text/plain' } });

      // Second attempt: 200
      mockReply('GET', '/ex/jira/test-cloud-id/rest/api/3/issue/ENG-123', 200, {
        id: '10001', key: 'ENG-123', fields: { summary: 'Test' },
      });

      const client = createClient();
      const result = await client.getIssue('ENG-123');
      expect(result.key).toBe('ENG-123');
    });

    it('should handle 429 rate limit with retry', async () => {
      // First attempt: 429
      mockPool.intercept({
        method: 'GET',
        path: '/ex/jira/test-cloud-id/rest/api/3/issue/ENG-123',
      }).reply(429, '{}', { headers: { 'Retry-After': '0', 'content-type': 'application/json' } });

      // Second attempt: 200
      mockReply('GET', '/ex/jira/test-cloud-id/rest/api/3/issue/ENG-123', 200, {
        id: '10001', key: 'ENG-123', fields: { summary: 'Test' },
      });

      const client = createClient();
      const result = await client.getIssue('ENG-123');
      expect(result.key).toBe('ENG-123');
    });
  });

  describe('getAuthorizationUrl', () => {
    it('should generate correct OAuth URL', () => {
      process.env.ATLASSIAN_CLIENT_ID = 'test-client-id';
      process.env.ATLASSIAN_REDIRECT_URI = 'https://maestro.app/api/integrations/jira/callback';

      const url = getAuthorizationUrl('test-state');
      expect(url).toContain('auth.atlassian.com/authorize');
      expect(url).toContain('client_id=test-client-id');
      expect(url).toContain('state=test-state');
      expect(url).toContain('response_type=code');
    });
  });
});

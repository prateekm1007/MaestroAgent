// tests/unit/github-client.test.js — Unit tests for GitHub API client.
//
// Uses undici MockAgent to intercept HTTP requests.

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { MockAgent, setGlobalDispatcher } from 'undici';
import { GitHubClient, GitHubApiError, getGitHubAuthUrl } from '../../src/integrations/github-client.js';

describe('github-client', () => {
  let mockAgent;
  let mockPool;

  beforeEach(() => {
    mockAgent = new MockAgent();
    mockAgent.disableNetConnect();
    setGlobalDispatcher(mockAgent);
    mockPool = mockAgent.get('https://api.github.com');
  });

  afterEach(() => {
    mockAgent.enableNetConnect();
  });

  function createClient(overrides = {}) {
    return new GitHubClient({
      token: 'test-token',
      tokenType: 'oauth',
      logger: { warn: vi.fn(), error: vi.fn(), log: vi.fn() },
      ...overrides,
    });
  }

  function mockReply(method, path, statusCode, body, headers = {}) {
    mockPool.intercept({ method, path }).reply(statusCode, body, {
      headers: { 'content-type': 'application/json', ...headers },
    });
  }

  describe('constructor', () => {
    it('should set token and type', () => {
      const client = createClient();
      expect(client.token).toBe('test-token');
      expect(client.tokenType).toBe('oauth');
    });

    it('should initialize cache', () => {
      const client = createClient();
      expect(client.cache).toBeInstanceOf(Map);
    });
  });

  describe('getPullRequest', () => {
    it('should GET /repos/:repo/pulls/:num', async () => {
      mockReply('GET', '/repos/owner/repo/pulls/123', 200, {
        id: 1, number: 123, title: 'Test PR', state: 'open',
        head: { ref: 'feature', sha: 'abc123' },
        base: { ref: 'main', sha: 'def456' },
      });

      const client = createClient();
      const result = await client.getPullRequest('owner/repo', 123);
      expect(result.number).toBe(123);
      expect(result.title).toBe('Test PR');
    });
  });

  describe('listPullRequests', () => {
    it('should GET /repos/:repo/pulls with query params', async () => {
      mockReply('GET', '/repos/owner/repo/pulls?state=open&sort=created&direction=desc&per_page=30&page=1', 200, [
        { number: 1, title: 'PR 1' },
        { number: 2, title: 'PR 2' },
      ]);

      const client = createClient();
      const result = await client.listPullRequests('owner/repo');
      expect(result).toHaveLength(2);
    });
  });

  describe('createPullRequest', () => {
    it('should POST to /repos/:repo/pulls', async () => {
      mockReply('POST', '/repos/owner/repo/pulls', 201, {
        number: 42, title: 'New PR', html_url: 'https://github.com/owner/repo/pull/42',
      });

      const client = createClient();
      const result = await client.createPullRequest('owner/repo', {
        title: 'New PR', head: 'feature', base: 'main',
      });
      expect(result.number).toBe(42);
    });
  });

  describe('createReview', () => {
    it('should POST review to PR', async () => {
      mockReply('POST', '/repos/owner/repo/pulls/123/reviews', 200, {
        id: 1, state: 'COMMENT', body: 'Looks good',
      });

      const client = createClient();
      const result = await client.createReview('owner/repo', 123, {
        body: 'Looks good', event: 'COMMENT',
      });
      expect(result.state).toBe('COMMENT');
    });
  });

  describe('addIssueComment', () => {
    it('should POST comment to issue/PR', async () => {
      mockReply('POST', '/repos/owner/repo/issues/123/comments', 201, {
        id: 1, body: 'Test comment',
      });

      const client = createClient();
      const result = await client.addIssueComment('owner/repo', 123, 'Test comment');
      expect(result.body).toBe('Test comment');
    });
  });

  describe('createCheckRun', () => {
    it('should POST check run', async () => {
      mockReply('POST', '/repos/owner/repo/check-runs', 201, {
        id: 1, name: 'Maestro Review', status: 'in_progress',
      });

      const client = createClient();
      const result = await client.createCheckRun('owner/repo', {
        name: 'Maestro Review', head_sha: 'abc123',
      });
      expect(result.name).toBe('Maestro Review');
    });
  });

  describe('triggerWorkflow', () => {
    it('should POST workflow dispatch', async () => {
      mockPool.intercept({
        method: 'POST',
        path: '/repos/owner/repo/actions/workflows/ci.yml/dispatches',
      }).reply(204, '', { headers: { 'content-type': 'text/plain' } });

      const client = createClient();
      await client.triggerWorkflow('owner/repo', 'ci.yml', 'main', { env: 'staging' });
    });
  });

  describe('listWorkflowRuns', () => {
    it('should GET /actions/runs', async () => {
      mockReply('GET', '/repos/owner/repo/actions/runs?per_page=30&page=1', 200, {
        workflow_runs: [
          { id: 1, name: 'CI', status: 'completed', conclusion: 'success' },
          { id: 2, name: 'CI', status: 'in_progress', conclusion: null },
        ],
        total_count: 2,
      });

      const client = createClient();
      const result = await client.listWorkflowRuns('owner/repo');
      expect(result.workflow_runs).toHaveLength(2);
      expect(result.total_count).toBe(2);
    });
  });

  describe('getRateLimit', () => {
    it('should GET /rate_limit', async () => {
      mockReply('GET', '/rate_limit', 200, {
        resources: {
          core: { limit: 5000, remaining: 4999, reset: 1700000000 },
        },
      });

      const client = createClient();
      const result = await client.getRateLimit();
      expect(result.resources.core.remaining).toBe(4999);
    });
  });

  describe('getRepository', () => {
    it('should GET /repos/:repo', async () => {
      mockReply('GET', '/repos/owner/repo', 200, {
        id: 1, full_name: 'owner/repo', private: false,
      });

      const client = createClient();
      const result = await client.getRepository('owner/repo');
      expect(result.full_name).toBe('owner/repo');
    });
  });

  describe('error handling', () => {
    it('should throw GitHubApiError on 404', async () => {
      mockReply('GET', '/repos/owner/repo/pulls/999', 404, {
        message: 'Not Found',
      });

      const client = createClient();
      try {
        await client.getPullRequest('owner/repo', 999);
        expect.fail('Should have thrown');
      } catch (err) {
        expect(err).toBeInstanceOf(GitHubApiError);
        expect(err.statusCode).toBe(404);
      }
    });

    it('should retry on 500 errors', async () => {
      mockPool.intercept({
        method: 'GET',
        path: '/repos/owner/repo',
      }).reply(500, 'Internal Server Error', { headers: { 'content-type': 'text/plain' } });

      mockReply('GET', '/repos/owner/repo', 200, {
        id: 1, full_name: 'owner/repo',
      });

      const client = createClient();
      const result = await client.getRepository('owner/repo');
      expect(result.full_name).toBe('owner/repo');
    });

    it('should handle 403 rate limit with retry', async () => {
      // First: rate limited
      mockPool.intercept({
        method: 'GET',
        path: '/repos/owner/repo',
      }).reply(403, { message: 'Rate limit' }, {
        headers: {
          'content-type': 'application/json',
          'x-ratelimit-remaining': '0',
          'x-ratelimit-reset': String(Math.floor(Date.now() / 1000) + 1),
        },
      });

      // Second: success
      mockReply('GET', '/repos/owner/repo', 200, {
        id: 1, full_name: 'owner/repo',
      });

      const client = createClient();
      const result = await client.getRepository('owner/repo');
      expect(result.full_name).toBe('owner/repo');
    });

    it('should handle 403 secondary rate limit with retry-after', async () => {
      mockPool.intercept({
        method: 'GET',
        path: '/repos/owner/repo',
      }).reply(403, { message: 'Secondary rate limit' }, {
        headers: {
          'content-type': 'application/json',
          'x-ratelimit-remaining': '4000',
          'retry-after': '0',
        },
      });

      mockReply('GET', '/repos/owner/repo', 200, {
        id: 1, full_name: 'owner/repo',
      });

      const client = createClient();
      const result = await client.getRepository('owner/repo');
      expect(result.full_name).toBe('owner/repo');
    });
  });

  describe('ETag caching', () => {
    it('should cache GET responses with ETag', async () => {
      // First request: 200 with ETag
      mockPool.intercept({
        method: 'GET',
        path: '/repos/owner/repo',
      }).reply(200, { id: 1, full_name: 'owner/repo' }, {
        headers: {
          'content-type': 'application/json',
          'etag': '"abc123"',
        },
      });

      const client = createClient();
      const result1 = await client.getRepository('owner/repo');
      expect(result1.full_name).toBe('owner/repo');
      expect(client.cache.size).toBe(1);

      // Second request: 304 Not Modified
      mockPool.intercept({
        method: 'GET',
        path: '/repos/owner/repo',
      }).reply(304, '', {
        headers: { 'content-type': 'text/plain' },
      });

      const result2 = await client.getRepository('owner/repo');
      expect(result2.full_name).toBe('owner/repo'); // Returns cached data
    });
  });

  describe('getGitHubAuthUrl', () => {
    it('should generate correct OAuth URL', () => {
      process.env.GITHUB_CLIENT_ID = 'test-client-id';
      process.env.GITHUB_REDIRECT_URI = 'https://maestro.app/api/integrations/github/callback';

      const url = getGitHubAuthUrl('test-state');
      expect(url).toContain('github.com/login/oauth/authorize');
      expect(url).toContain('client_id=test-client-id');
      expect(url).toContain('state=test-state');
    });
  });
});

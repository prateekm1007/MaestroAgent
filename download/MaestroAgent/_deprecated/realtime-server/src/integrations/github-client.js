// src/integrations/github-client.js — GitHub REST API v2022.11.28 client.
//
// Provides authenticated API calls to GitHub using OAuth tokens (user-to-server)
// or installation tokens (GitHub App, server-to-server).
//
// Features:
//   - Rate limit handling (primary + secondary, X-RateLimit headers)
//   - Retry on 5xx (3 attempts, exponential backoff)
//   - Conditional requests (ETag / If-None-Match for caching)
//   - All GitHub REST API operations used by Maestro
//
// API reference: https://docs.github.com/en/rest

import { fetch } from 'undici';

const GITHUB_API_BASE = 'https://api.github.com';
const MAX_RETRIES = 3;

/**
 * GitHub API client.
 * Each instance is scoped to a specific org's integration (token + config).
 */
export class GitHubClient {
  /**
   * @param {object} options
   * @param {string} options.token - OAuth access token or installation token
   * @param {string} [options.tokenType] - 'oauth' | 'installation'
   * @param {function} [options.onTokenRefresh] - Called when installation token is refreshed
   * @param {object} [options.logger]
   * @param {Map<string, {etag: string, data: any, ts: number}>} [options.cache] - ETag cache
   */
  constructor(options) {
    this.token = options.token;
    this.tokenType = options.tokenType || 'oauth';
    this.onTokenRefresh = options.onTokenRefresh || (() => {});
    this.logger = options.logger || console;
    this.cache = options.cache || new Map();
  }

  // ===========================================================================
  // HTTP CORE
  // ===========================================================================

  /**
   * Make an authenticated GitHub API request.
   * Handles rate limits, retries, and conditional requests (ETag caching).
   *
   * @param {string} method - HTTP method
   * @param {string} path - API path (e.g. '/repos/owner/repo/pulls/123')
   * @param {object} options - { body, query, headers, cacheKey, raw }
   * @returns {Promise<object>} Parsed JSON response
   */
  async _request(method, path, options = {}) {
    const url = new URL(`${GITHUB_API_BASE}${path}`);

    if (options.query) {
      for (const [key, value] of Object.entries(options.query)) {
        if (value !== undefined && value !== null) {
          url.searchParams.set(key, String(value));
        }
      }
    }

    // ETag caching for GET requests
    const cacheKey = options.cacheKey || (method === 'GET' ? path : null);
    const cached = cacheKey ? this.cache.get(cacheKey) : null;

    const headers = {
      'Authorization': `Bearer ${this.token}`,
      'Accept': 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      ...options.headers,
    };

    if (cached?.etag) {
      headers['If-None-Match'] = cached.etag;
    }

    let lastError;

    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      try {
        const response = await fetch(url.toString(), {
          method,
          headers,
          body: options.body ? JSON.stringify(options.body) : undefined,
        });

        // Handle rate limiting (403 with X-RateLimit-Remaining: 0)
        if (response.status === 403) {
          const remaining = response.headers.get('x-ratelimit-remaining');
          const resetAt = response.headers.get('x-ratelimit-reset');

          if (remaining === '0') {
            const waitSeconds = resetAt
              ? Math.max(1, parseInt(resetAt, 10) - Math.floor(Date.now() / 1000))
              : 60;
            if (attempt < MAX_RETRIES) {
              this.logger.warn(`[github] Rate limited, waiting ${waitSeconds}s (attempt ${attempt + 1}/${MAX_RETRIES})`);
              await sleep(Math.min(waitSeconds, 60) * 1000); // Cap at 60s for tests
              continue;
            }
            throw new GitHubApiError('Rate limit exceeded', 403, 'RATE_LIMITED', {
              reset_at: resetAt,
            });
          }

          // Secondary rate limit (abuse detection)
          const retryAfter = response.headers.get('retry-after');
          if (retryAfter) {
            if (attempt < MAX_RETRIES) {
              this.logger.warn(`[github] Secondary rate limit, waiting ${retryAfter}s (attempt ${attempt + 1}/${MAX_RETRIES})`);
              await sleep(parseInt(retryAfter, 10) * 1000);
              continue;
            }
            throw new GitHubApiError('Secondary rate limit exceeded', 403, 'SECONDARY_RATE_LIMIT', {
              retry_after: retryAfter,
            });
          }
        }

        // Handle 401 — try token refresh for installation tokens
        if (response.status === 401 && attempt === 0 && this.tokenType === 'installation') {
          this.logger.warn('[github] Token expired, attempting refresh');
          const refreshed = await this.onTokenRefresh();
          if (refreshed) {
            headers.Authorization = `Bearer ${this.token}`;
            continue;
          }
          throw new GitHubApiError('Token expired and refresh failed', 401, 'AUTH_EXPIRED');
        }

        // Handle 5xx with retry
        if (response.status >= 500 && attempt < MAX_RETRIES) {
          const backoff = Math.pow(2, attempt) * 1000;
          this.logger.warn(`[github] Server error ${response.status}, retrying in ${backoff}ms (attempt ${attempt + 1}/${MAX_RETRIES})`);
          await sleep(backoff);
          continue;
        }

        // 304 Not Modified — return cached data
        if (response.status === 304 && cached) {
          return cached.data;
        }

        // Parse response
        const contentType = response.headers.get('content-type') || '';
        if (contentType.includes('application/json')) {
          const json = await response.json();

          if (!response.ok) {
            const errorMsg = json.message || `HTTP ${response.status}`;
            throw new GitHubApiError(errorMsg, response.status, json.code || 'API_ERROR', json);
          }

          // Cache GET responses with ETag
          if (cacheKey && method === 'GET') {
            const etag = response.headers.get('etag');
            if (etag) {
              this.cache.set(cacheKey, { etag, data: json, ts: Date.now() });
            }
          }

          return json;
        }

        // Raw response (e.g. file content, patch)
        if (options.raw) {
          const text = await response.text();
          if (!response.ok) {
            throw new GitHubApiError(text || `HTTP ${response.status}`, response.status);
          }
          return text;
        }

        if (!response.ok) {
          const text = await response.text();
          throw new GitHubApiError(text || `HTTP ${response.status}`, response.status);
        }

        return { status: response.status };
      } catch (err) {
        if (err instanceof GitHubApiError) throw err;
        lastError = err;
        if (attempt < MAX_RETRIES) {
          const backoff = Math.pow(2, attempt) * 1000;
          this.logger.warn(`[github] Request error: ${err.message}, retrying in ${backoff}ms (attempt ${attempt + 1}/${MAX_RETRIES})`);
          await sleep(backoff);
          continue;
        }
      }
    }

    throw lastError || new GitHubApiError('Max retries exceeded', 500, 'MAX_RETRIES');
  }

  // ===========================================================================
  // PULL REQUESTS
  // ===========================================================================

  /**
   * Get a pull request.
   * @param {string} repo - "owner/repo" format
   * @param {number} prNumber
   */
  async getPullRequest(repo, prNumber) {
    return this._request('GET', `/repos/${repo}/pulls/${prNumber}`, {
      cacheKey: `pr:${repo}:${prNumber}`,
    });
  }

  /**
   * List pull requests.
   * @param {string} repo
   * @param {object} options - { state, sort, direction, per_page, page }
   */
  async listPullRequests(repo, options = {}) {
    return this._request('GET', `/repos/${repo}/pulls`, {
      query: {
        state: options.state || 'open',
        sort: options.sort || 'created',
        direction: options.direction || 'desc',
        per_page: options.per_page || 30,
        page: options.page || 1,
      },
    });
  }

  /**
   * Create a pull request.
   * @param {string} repo
   * @param {object} params - { title, head, base, body, draft }
   */
  async createPullRequest(repo, params) {
    return this._request('POST', `/repos/${repo}/pulls`, {
      body: {
        title: params.title,
        head: params.head,
        base: params.base || 'main',
        body: params.body,
        draft: params.draft || false,
      },
    });
  }

  /**
   * Update a pull request.
   * @param {string} repo
   * @param {number} prNumber
   * @param {object} params - { title, body, state }
   */
  async updatePullRequest(repo, prNumber, params) {
    return this._request('PATCH', `/repos/${repo}/pulls/${prNumber}`, {
      body: params,
    });
  }

  /**
   * Merge a pull request.
   * @param {string} repo
   * @param {number} prNumber
   * @param {object} params - { commit_title, merge_method }
   */
  async mergePullRequest(repo, prNumber, params = {}) {
    return this._request('PUT', `/repos/${repo}/pulls/${prNumber}/merge`, {
      body: {
        commit_title: params.commit_title,
        commit_message: params.commit_message,
        merge_method: params.merge_method || 'merge', // merge | squash | rebase
      },
    });
  }

  /**
   * Request reviewers.
   * @param {string} repo
   * @param {number} prNumber
   * @param {string[]} reviewers - GitHub usernames
   */
  async requestReviewers(repo, prNumber, reviewers) {
    return this._request('POST', `/repos/${repo}/pulls/${prNumber}/requested_reviewers`, {
      body: { reviewers },
    });
  }

  // ===========================================================================
  // REVIEWS
  // ===========================================================================

  /**
   * List reviews on a PR.
   * @param {string} repo
   * @param {number} prNumber
   */
  async listReviews(repo, prNumber) {
    return this._request('GET', `/repos/${repo}/pulls/${prNumber}/reviews`, {
      cacheKey: `reviews:${repo}:${prNumber}`,
    });
  }

  /**
   * Create a review on a PR.
   * @param {string} repo
   * @param {number} prNumber
   * @param {object} params - { body, event, commit_id }
   *   event: 'APPROVE' | 'REQUEST_CHANGES' | 'COMMENT'
   */
  async createReview(repo, prNumber, params) {
    return this._request('POST', `/repos/${repo}/pulls/${prNumber}/reviews`, {
      body: {
        body: params.body,
        event: params.event || 'COMMENT',
        commit_id: params.commit_id,
      },
    });
  }

  /**
   * Submit a pending review.
   * @param {string} repo
   * @param {number} prNumber
   * @param {number} reviewId
   * @param {object} params - { body, event }
   */
  async submitReview(repo, prNumber, reviewId, params) {
    return this._request('POST', `/repos/${repo}/pulls/${prNumber}/reviews/${reviewId}/events`, {
      body: {
        body: params.body,
        event: params.event || 'COMMENT',
      },
    });
  }

  /**
   * Get review comments (inline code comments).
   * @param {string} repo
   * @param {number} prNumber
   */
  async getReviewComments(repo, prNumber) {
    return this._request('GET', `/repos/${repo}/pulls/${prNumber}/comments`, {
      cacheKey: `review_comments:${repo}:${prNumber}`,
    });
  }

  /**
   * Create a review comment (inline code comment).
   * @param {string} repo
   * @param {number} prNumber
   * @param {object} params - { body, commit_id, path, line, side, start_line, start_side }
   */
  async createReviewComment(repo, prNumber, params) {
    return this._request('POST', `/repos/${repo}/pulls/${prNumber}/comments`, {
      body: params,
    });
  }

  // ===========================================================================
  // ISSUES
  // ===========================================================================

  /**
   * Get an issue.
   * @param {string} repo
   * @param {number} issueNumber
   */
  async getIssue(repo, issueNumber) {
    return this._request('GET', `/repos/${repo}/issues/${issueNumber}`, {
      cacheKey: `issue:${repo}:${issueNumber}`,
    });
  }

  /**
   * List issues.
   * @param {string} repo
   * @param {object} options - { state, labels, sort, direction, since, per_page, page }
   */
  async listIssues(repo, options = {}) {
    return this._request('GET', `/repos/${repo}/issues`, {
      query: {
        state: options.state || 'open',
        labels: options.labels?.join(','),
        sort: options.sort || 'created',
        direction: options.direction || 'desc',
        since: options.since,
        per_page: options.per_page || 30,
        page: options.page || 1,
      },
    });
  }

  /**
   * Create an issue.
   * @param {string} repo
   * @param {object} params - { title, body, labels, assignees, milestone }
   */
  async createIssue(repo, params) {
    return this._request('POST', `/repos/${repo}/issues`, {
      body: params,
    });
  }

  /**
   * Update an issue.
   * @param {string} repo
   * @param {number} issueNumber
   * @param {object} params
   */
  async updateIssue(repo, issueNumber, params) {
    return this._request('PATCH', `/repos/${repo}/issues/${issueNumber}`, {
      body: params,
    });
  }

  /**
   * Add a comment to an issue or PR.
   * @param {string} repo
   * @param {number} issueOrPrNumber
   * @param {string} body
   */
  async addIssueComment(repo, issueOrPrNumber, body) {
    return this._request('POST', `/repos/${repo}/issues/${issueOrPrNumber}/comments`, {
      body: { body },
    });
  }

  /**
   * List comments on an issue or PR.
   * @param {string} repo
   * @param {number} issueOrPrNumber
   */
  async listIssueComments(repo, issueOrPrNumber) {
    return this._request('GET', `/repos/${repo}/issues/${issueOrPrNumber}/comments`, {
      cacheKey: `issue_comments:${repo}:${issueOrPrNumber}`,
    });
  }

  // ===========================================================================
  // STATUS CHECKS / CHECK RUNS
  // ===========================================================================

  /**
   * Get combined status for a ref.
   * @param {string} repo
   * @param {string} ref - SHA or branch name
   */
  async getCombinedStatusForRef(repo, ref) {
    return this._request('GET', `/repos/${repo}/commits/${ref}/check-runs`, {
      query: { per_page: 100 },
      cacheKey: `check_runs:${repo}:${ref}`,
    });
  }

  /**
   * List check runs for a specific ref.
   * @param {string} repo
   * @param {string} ref
   */
  async listCheckRunsForRef(repo, ref) {
    return this._request('GET', `/repos/${repo}/commits/${ref}/check-suites`, {
      query: { per_page: 100 },
      cacheKey: `check_suites:${repo}:${ref}`,
    });
  }

  /**
   * Create a check run (GitHub Actions / CI status).
   * @param {string} repo
   * @param {object} params - { name, head_sha, status, conclusion, output, actions }
   */
  async createCheckRun(repo, params) {
    return this._request('POST', `/repos/${repo}/check-runs`, {
      body: params,
    });
  }

  /**
   * Update a check run.
   * @param {string} repo
   * @param {number} checkRunId
   * @param {object} params
   */
  async updateCheckRun(repo, checkRunId, params) {
    return this._request('PATCH', `/repos/${repo}/check-runs/${checkRunId}`, {
      body: params,
    });
  }

  // ===========================================================================
  // GITHUB ACTIONS
  // ===========================================================================

  /**
   * List workflow runs for a repository.
   * @param {string} repo
   * @param {object} options - { actor, branch, event, status, per_page, page }
   */
  async listWorkflowRuns(repo, options = {}) {
    return this._request('GET', `/repos/${repo}/actions/runs`, {
      query: {
        actor: options.actor,
        branch: options.branch,
        event: options.event,
        status: options.status,
        per_page: options.per_page || 30,
        page: options.page || 1,
      },
    });
  }

  /**
   * Get a workflow run.
   * @param {string} repo
   * @param {number} runId
   */
  async getWorkflowRun(repo, runId) {
    return this._request('GET', `/repos/${repo}/actions/runs/${runId}`, {
      cacheKey: `workflow_run:${repo}:${runId}`,
    });
  }

  /**
   * Cancel a workflow run.
   * @param {string} repo
   * @param {number} runId
   */
  async cancelWorkflowRun(repo, runId) {
    return this._request('POST', `/repos/${repo}/actions/runs/${runId}/cancel`);
  }

  /**
   * Re-run a failed workflow.
   * @param {string} repo
   * @param {number} runId
   */
  async rerunWorkflowRun(repo, runId) {
    return this._request('POST', `/repos/${repo}/actions/runs/${runId}/rerun`);
  }

  /**
   * List workflow run logs (download URL).
   * @param {string} repo
   * @param {number} runId
   */
  async getWorkflowRunLogs(repo, runId) {
    const result = await this._request('GET', `/repos/${repo}/actions/runs/${runId}/logs`);
    return result;
  }

  /**
   * Get a job log from a workflow run.
   * @param {string} repo
   * @param {number} jobId
   */
  async getJobLogs(repo, jobId) {
    return this._request('GET', `/repos/${repo}/actions/jobs/${jobId}/logs`, { raw: true });
  }

  /**
   * Trigger a workflow dispatch.
   * @param {string} repo
   * @param {string} workflowId - Workflow filename (e.g. "ci.yml") or ID
   * @param {string} ref - Branch or tag name
   * @param {object} inputs - Workflow inputs
   */
  async triggerWorkflow(repo, workflowId, ref, inputs = {}) {
    return this._request('POST', `/repos/${repo}/actions/workflows/${workflowId}/dispatches`, {
      body: { ref, inputs },
    });
  }

  // ===========================================================================
  // REPOSITORIES
  // ===========================================================================

  /**
   * Get repository info.
   * @param {string} repo - "owner/repo"
   */
  async getRepository(repo) {
    return this._request('GET', `/repos/${repo}`, {
      cacheKey: `repo:${repo}`,
    });
  }

  /**
   * List repositories for the authenticated user.
   * @param {object} options - { visibility, affiliation, per_page, page }
   */
  async listReposForAuthenticatedUser(options = {}) {
    return this._request('GET', '/user/repos', {
      query: {
        visibility: options.visibility || 'all',
        affiliation: options.affiliation || 'owner,collaborator,organization_member',
        per_page: options.per_page || 100,
        page: options.page || 1,
      },
    });
  }

  /**
   * Get file content from a repo.
   * @param {string} repo
   * @param {string} path - File path
   * @param {string} [ref] - Branch/commit
   * @returns {Promise<string>} File content (decoded from base64)
   */
  async getFileContent(repo, path, ref) {
    const query = ref ? { ref } : {};
    const result = await this._request('GET', `/repos/${repo}/contents/${path}`, {
      query,
      cacheKey: `file:${repo}:${path}:${ref || 'default'}`,
    });

    if (result.encoding === 'base64') {
      return Buffer.from(result.content, 'base64').toString('utf8');
    }
    return result.content;
  }

  /**
   * List branches.
   * @param {string} repo
   */
  async listBranches(repo) {
    return this._request('GET', `/repos/${repo}/branches`, {
      query: { per_page: 100 },
    });
  }

  // ===========================================================================
  // COMMITS
  // ===========================================================================

  /**
   * List commits on a repo.
   * @param {string} repo
   * @param {object} options - { sha, path, since, until, per_page, page }
   */
  async listCommits(repo, options = {}) {
    return this._request('GET', `/repos/${repo}/commits`, {
      query: {
        sha: options.sha,
        path: options.path,
        since: options.since,
        until: options.until,
        per_page: options.per_page || 30,
        page: options.page || 1,
      },
    });
  }

  /**
   * Get a commit.
   * @param {string} repo
   * @param {string} ref - SHA
   */
  async getCommit(repo, ref) {
    return this._request('GET', `/repos/${repo}/commits/${ref}`, {
      cacheKey: `commit:${repo}:${ref}`,
    });
  }

  /**
   * Compare two commits.
   * @param {string} repo
   * @param {string} base
   * @param {string} head
   */
  async compareCommits(repo, base, head) {
    return this._request('GET', `/repos/${repo}/compare/${base}...${head}`, {
      cacheKey: `compare:${repo}:${base}:${head}`,
    });
  }

  // ===========================================================================
  // WEBHOOKS
  // ===========================================================================

  /**
   * List webhook deliveries for a repository.
   * @param {string} repo
   */
  async listWebhookDeliveries(repo) {
    return this._request('GET', `/repos/${repo}/hooks/deliveries`);
  }

  /**
   * Redeliver a webhook delivery.
   * @param {string} repo
   * @param {number} deliveryId
   */
  async redeliverWebhook(repo, deliveryId) {
    return this._request('POST', `/repos/${repo}/hooks/deliveries/${deliveryId}/attempts`);
  }

  // ===========================================================================
  // RATE LIMIT INFO
  // ===========================================================================

  /**
   * Get current rate limit status.
   */
  async getRateLimit() {
    return this._request('GET', '/rate_limit');
  }
}

// ===========================================================================
// HELPERS
// ===========================================================================

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Custom error for GitHub API errors.
 */
export class GitHubApiError extends Error {
  constructor(message, statusCode, code = 'API_ERROR', details = null) {
    super(message);
    this.name = 'GitHubApiError';
    this.statusCode = statusCode;
    this.code = code;
    this.details = details;
  }
}

// ============================================================================
// OAUTH FLOW
// ============================================================================

/**
 * Generate the GitHub OAuth authorization URL.
 * @param {string} state - CSRF state token
 * @param {string[]} scopes - OAuth scopes
 * @returns {string} Authorization URL
 */
export function getGitHubAuthUrl(state, scopes = ['repo', 'read:org', 'workflow']) {
  const params = new URLSearchParams({
    client_id: process.env.GITHUB_CLIENT_ID,
    redirect_uri: process.env.GITHUB_REDIRECT_URI,
    scope: scopes.join(' '),
    state,
  });

  return `https://github.com/login/oauth/authorize?${params.toString()}`;
}

/**
 * Exchange an OAuth code for an access token.
 * @param {string} code - Authorization code from GitHub callback
 * @returns {Promise<{ access_token: string, token_type: string, scope: string }>}
 */
export async function exchangeGitHubCodeForToken(code) {
  const response = await fetch('https://github.com/login/oauth/access_token', {
    method: 'POST',
    headers: {
      'Accept': 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      client_id: process.env.GITHUB_CLIENT_ID,
      client_secret: process.env.GITHUB_CLIENT_SECRET,
      code,
      redirect_uri: process.env.GITHUB_REDIRECT_URI,
    }),
  });

  if (!response.ok) {
    throw new GitHubApiError('Token exchange failed', response.status);
  }

  const tokens = await response.json();

  if (tokens.error) {
    throw new GitHubApiError(tokens.error_description || tokens.error, 400, 'AUTH_ERROR', tokens);
  }

  return tokens;
}

/**
 * Get the authenticated user's info.
 * @param {string} accessToken
 */
export async function getAuthenticatedUser(accessToken) {
  const response = await fetch(`${GITHUB_API_BASE}/user`, {
    headers: {
      'Authorization': `Bearer ${accessToken}`,
      'Accept': 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
    },
  });

  if (!response.ok) {
    throw new GitHubApiError('Failed to get user info', response.status);
  }

  return response.json();
}

// src/integrations/jira-client.js — Atlassian Jira Cloud REST API v3 client.
//
// Provides authenticated API calls to Jira Cloud using OAuth 2.0 access tokens
// obtained via the Atlassian 3LO (three-legged OAuth) flow.
//
// Features:
//   - Automatic token refresh on 401
//   - Rate limit handling (429 → exponential backoff)
//   - Retry on 5xx (3 attempts, exponential backoff)
//   - All Jira REST API v3 operations used by Maestro
//   - Typed responses
//
// API reference: https://developer.atlassian.com/cloud/jira/platform/rest/v3/

import { fetch } from 'undici';

const JIRA_API_BASE = 'https://api.atlassian.com';
const MAX_RETRIES = 3;
const RATE_LIMIT_RETRY_AFTER = 60; // seconds, if no Retry-After header

/**
 * Jira API client.
 * Each instance is scoped to a specific org's integration (cloud ID + tokens).
 */
export class JiraClient {
  /**
   * @param {object} options
   * @param {string} options.cloudId - Atlassian cloud ID (from accessible resources)
   * @param {string} options.accessToken - OAuth 2.0 access token
   * @param {string} options.refreshToken - OAuth 2.0 refresh token
   * @param {function} options.onTokenRefresh - Called when tokens are refreshed (newTokens)
   * @param {object} options.logger - Logger with .warn/.error methods
   */
  constructor(options) {
    this.cloudId = options.cloudId;
    this.accessToken = options.accessToken;
    this.refreshToken = options.refreshToken;
    this.onTokenRefresh = options.onTokenRefresh || (() => {});
    this.logger = options.logger || console;
    this._baseUrl = `${JIRA_API_BASE}/ex/jira/${options.cloudId}/rest/api/3`;
    this._agileBaseUrl = `${JIRA_API_BASE}/ex/jira/${options.cloudId}/rest/agile/1.0`;
  }

  // ===========================================================================
  // HTTP CORE
  // ===========================================================================

  /**
   * Make an authenticated Jira API request with retry and rate-limit handling.
   * @param {string} method - HTTP method
   * @param {string} path - API path (without base URL)
   * @param {object} options - { body, query, headers, isAgile }
   * @returns {Promise<object>} Parsed JSON response
   */
  async _request(method, path, options = {}) {
    const baseUrl = options.isAgile ? this._agileBaseUrl : this._baseUrl;
    const url = new URL(`${baseUrl}${path}`);

    if (options.query) {
      for (const [key, value] of Object.entries(options.query)) {
        if (value !== undefined && value !== null) {
          url.searchParams.set(key, String(value));
        }
      }
    }

    let lastError;

    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      try {
        const response = await fetch(url.toString(), {
          method,
          headers: {
            'Authorization': `Bearer ${this.accessToken}`,
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            ...options.headers,
          },
          body: options.body ? JSON.stringify(options.body) : undefined,
        });

        // Handle rate limiting (429)
        if (response.status === 429) {
          const retryAfter = parseInt(response.headers.get('Retry-After') || RATE_LIMIT_RETRY_AFTER, 10);
          if (attempt < MAX_RETRIES) {
            this.logger.warn(`[jira] Rate limited, retrying after ${retryAfter}s (attempt ${attempt + 1}/${MAX_RETRIES})`);
            await sleep(retryAfter * 1000);
            continue;
          }
          throw new JiraApiError('Rate limit exceeded after max retries', 429, 'RATE_LIMITED');
        }

        // Handle 401 — try token refresh
        if (response.status === 401 && attempt === 0 && this.refreshToken) {
          this.logger.warn('[jira] Access token expired, attempting refresh');
          const refreshed = await this._refreshToken();
          if (refreshed) {
            // Retry with new token
            continue;
          }
          throw new JiraApiError('Token refresh failed', 401, 'AUTH_EXPIRED');
        }

        // Handle 5xx with retry
        if (response.status >= 500 && attempt < MAX_RETRIES) {
          const backoff = Math.pow(2, attempt) * 1000;
          this.logger.warn(`[jira] Server error ${response.status}, retrying in ${backoff}ms (attempt ${attempt + 1}/${MAX_RETRIES})`);
          await sleep(backoff);
          continue;
        }

        // Parse response
        const contentType = response.headers.get('content-type') || '';
        if (contentType.includes('application/json')) {
          const json = await response.json();

          if (!response.ok) {
            const errorMsg = json.errorMessages?.join('; ') || json.message || `HTTP ${response.status}`;
            throw new JiraApiError(errorMsg, response.status, json.errorKey || 'API_ERROR', json);
          }

          return json;
        }

        if (!response.ok) {
          const text = await response.text();
          throw new JiraApiError(text || `HTTP ${response.status}`, response.status, 'HTTP_ERROR');
        }

        return { status: response.status };
      } catch (err) {
        if (err instanceof JiraApiError) throw err;
        lastError = err;
        if (attempt < MAX_RETRIES) {
          const backoff = Math.pow(2, attempt) * 1000;
          this.logger.warn(`[jira] Request error: ${err.message}, retrying in ${backoff}ms (attempt ${attempt + 1}/${MAX_RETRIES})`);
          await sleep(backoff);
          continue;
        }
      }
    }

    throw lastError || new JiraApiError('Max retries exceeded', 500, 'MAX_RETRIES');
  }

  /**
   * Refresh the OAuth access token using the refresh token.
   * Calls onTokenRefresh callback with new tokens.
   * @returns {Promise<boolean>} True if refresh succeeded
   */
  async _refreshToken() {
    try {
      const response = await fetch('https://auth.atlassian.com/oauth/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          grant_type: 'refresh_token',
          client_id: process.env.ATLASSIAN_CLIENT_ID,
          client_secret: process.env.ATLASSIAN_CLIENT_SECRET,
          refresh_token: this.refreshToken,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        this.logger.error('[jira] Token refresh failed:', error);
        return false;
      }

      const tokens = await response.json();
      this.accessToken = tokens.access_token;
      this.refreshToken = tokens.refresh_token; // Atlassian rotates refresh tokens

      // Notify the caller to persist new tokens
      await this.onTokenRefresh({
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token,
        expiresIn: tokens.expires_in,
      });

      return true;
    } catch (err) {
      this.logger.error('[jira] Token refresh error:', err.message);
      return false;
    }
  }

  // ===========================================================================
  // ISSUES
  // ===========================================================================

  /**
   * Create an issue.
   * @param {object} params
   * @param {string} params.projectKey - Jira project key (e.g. "ENG")
   * @param {string} params.summary - Issue summary
   * @param {string} params.description - Issue description (plain text)
   * @param {string} params.issueType - Issue type name (e.g. "Task", "Bug", "Story")
   * @param {string} [params.assigneeAccountId] - Atlassian account ID
   * @param {string[]} [params.labels] - Labels
   * @param {object} [params.customFields] - Custom field values { fieldId: value }
   * @returns {Promise<object>} Created issue { id, key, self }
   */
  async createIssue(params) {
    const fields = {
      project: { key: params.projectKey },
      summary: params.summary,
      issuetype: { name: params.issueType || 'Task' },
    };

    if (params.description) {
      fields.description = {
        type: 'doc',
        version: 1,
        content: [
          {
            type: 'paragraph',
            content: [{ type: 'text', text: params.description }],
          },
        ],
      };
    }

    if (params.assigneeAccountId) {
      fields.assignee = { accountId: params.assigneeAccountId };
    }

    if (params.labels) {
      fields.labels = params.labels;
    }

    if (params.customFields) {
      Object.assign(fields, params.customFields);
    }

    return this._request('POST', '/issue', { body: { fields } });
  }

  /**
   * Get an issue by key or ID.
   * @param {string} issueKeyOrId - e.g. "ENG-123"
   * @param {string[]} [fields] - Specific fields to retrieve
   * @returns {Promise<object>} Issue object
   */
  async getIssue(issueKeyOrId, fields = null) {
    const query = {};
    if (fields) query.fields = fields.join(',');
    return this._request('GET', `/issue/${issueKeyOrId}`, { query });
  }

  /**
   * Update an issue.
   * @param {string} issueKeyOrId
   * @param {object} fields - Fields to update
   * @returns {Promise<object>}
   */
  async updateIssue(issueKeyOrId, fields) {
    return this._request('PUT', `/issue/${issueKeyOrId}`, { body: { fields } });
  }

  /**
   * Update issue status via transition.
   * @param {string} issueKeyOrId
   * @param {string} transitionId - Transition ID (get available via getTransitions)
   * @param {object} [fields] - Additional fields to update during transition
   * @returns {Promise<object>}
   */
  async transitionIssue(issueKeyOrId, transitionId, fields = null) {
    const body = { transition: { id: transitionId } };
    if (fields) body.fields = fields;
    return this._request('POST', `/issue/${issueKeyOrId}/transitions`, { body });
  }

  /**
   * Get available transitions for an issue.
   * @param {string} issueKeyOrId
   * @returns {Promise<object>} { transitions: [{ id, name, to: { id, name } }] }
   */
  async getTransitions(issueKeyOrId) {
    return this._request('GET', `/issue/${issueKeyOrId}/transitions`);
  }

  /**
   * Search for issues using JQL.
   * @param {string} jql - JQL query
   * @param {object} options - { fields, maxResults, startAt, expand }
   * @returns {Promise<object>} { issues, total, startAt, maxResults }
   */
  async searchIssues(jql, options = {}) {
    return this._request('POST', '/search', {
      body: {
        jql,
        fields: options.fields || ['summary', 'status', 'assignee', 'priority', 'issuetype'],
        maxResults: options.maxResults || 50,
        startAt: options.startAt || 0,
        expand: options.expand,
      },
    });
  }

  /**
   * Delete an issue.
   * @param {string} issueKeyOrId
   */
  async deleteIssue(issueKeyOrId) {
    return this._request('DELETE', `/issue/${issueKeyOrId}`);
  }

  // ===========================================================================
  // COMMENTS
  // ===========================================================================

  /**
   * Add a comment to an issue.
   * @param {string} issueKeyOrId
   * @param {string} body - Comment text (plain text, will be wrapped in ADF)
   * @param {string} [visibility] - Visibility restriction (role or group)
   * @returns {Promise<object>} Created comment { id, body, created, author }
   */
  async addComment(issueKeyOrId, body, visibility = null) {
    const commentBody = {
      body: {
        type: 'doc',
        version: 1,
        content: [
          {
            type: 'paragraph',
            content: [{ type: 'text', text: body }],
          },
        ],
      },
    };

    if (visibility) {
      commentBody.visibility = visibility;
    }

    return this._request('POST', `/issue/${issueKeyOrId}/comment`, { body: commentBody });
  }

  /**
   * Get all comments on an issue.
   * @param {string} issueKeyOrId
   * @returns {Promise<object[]>} Comments
   */
  async getComments(issueKeyOrId) {
    const result = await this._request('GET', `/issue/${issueKeyOrId}/comment`);
    return result.comments || [];
  }

  /**
   * Update a comment.
   * @param {string} issueKeyOrId
   * @param {string} commentId
   * @param {string} body - New comment text
   */
  async updateComment(issueKeyOrId, commentId, body) {
    return this._request('PUT', `/issue/${issueKeyOrId}/comment/${commentId}`, {
      body: {
        body: {
          type: 'doc',
          version: 1,
          content: [{ type: 'paragraph', content: [{ type: 'text', text: body }] }],
        },
      },
    });
  }

  /**
   * Delete a comment.
   * @param {string} issueKeyOrId
   * @param {string} commentId
   */
  async deleteComment(issueKeyOrId, commentId) {
    return this._request('DELETE', `/issue/${issueKeyOrId}/comment/${commentId}`);
  }

  // ===========================================================================
  // ATTACHMENTS
  // ===========================================================================

  /**
   * Add an attachment to an issue.
   * Uses multipart/form-data upload.
   * @param {string} issueKeyOrId
   * @param {Buffer} fileContent - File content as Buffer
   * @param {string} filename - Name of the file
   * @returns {Promise<object[]>} Array of created attachment metadata
   */
  async addAttachment(issueKeyOrId, fileContent, filename) {
    const FormData = (await import('undici')).FormData;
    const { Blob } = globalThis;

    const formData = new FormData();
    formData.append('file', new Blob([fileContent]), filename);

    return this._request('POST', `/issue/${issueKeyOrId}/attachments`, {
      body: formData,
      headers: {
        'Content-Type': undefined, // Let undici set the multipart boundary
        'X-Atlassian-Token': 'no-check', // Required for attachment uploads
      },
    });
  }

  /**
   * Get attachments for an issue.
   * @param {string} issueKeyOrId
   * @returns {Promise<object[]>} Attachment metadata
   */
  async getAttachments(issueKeyOrId) {
    const issue = await this.getIssue(issueKeyOrId, ['attachment']);
    return issue.fields?.attachment || [];
  }

  /**
   * Download an attachment.
   * @param {string} attachmentId
   * @returns {Promise<Buffer>} Attachment content
   */
  async downloadAttachment(attachmentId) {
    const response = await fetch(`${this._baseUrl}/attachment/content/${attachmentId}`, {
      headers: { 'Authorization': `Bearer ${this.accessToken}` },
    });
    if (!response.ok) {
      throw new JiraApiError(`Failed to download attachment: HTTP ${response.status}`, response.status);
    }
    return Buffer.from(await response.arrayBuffer());
  }

  /**
   * Delete an attachment.
   * @param {string} attachmentId
   */
  async deleteAttachment(attachmentId) {
    return this._request('DELETE', `/attachment/${attachmentId}`);
  }

  // ===========================================================================
  // PROJECTS
  // ===========================================================================

  /**
   * List all accessible projects.
   * @returns {Promise<object[]>} Projects
   */
  async listProjects() {
    return this._request('GET', '/project/search', { query: { maxResults: 100 } });
  }

  /**
   * Get project details.
   * @param {string} projectKeyOrId
   */
  async getProject(projectKeyOrId) {
    return this._request('GET', `/project/${projectKeyOrId}`);
  }

  /**
   * Get issue types for a project.
   * @param {string} projectId
   */
  async getIssueTypes(projectId) {
    return this._request('GET', `/project/${projectId}/statuses`);
  }

  // ===========================================================================
  // USERS
  // ===========================================================================

  /**
   * Search for users.
   * @param {string} query - Search query (name or email)
   * @returns {Promise<object[]>} Users
   */
  async searchUsers(query) {
    return this._request('GET', '/user/search', { query: { query, maxResults: 10 } });
  }

  /**
   * Get current user.
   */
  async getMyself() {
    return this._request('GET', '/myself');
  }

  // ===========================================================================
  // WORKLOGS
  // ===========================================================================

  /**
   * Add a worklog entry to an issue.
   * @param {string} issueKeyOrId
   * @param {object} params - { timeSpent, timeSpentSeconds, started, comment }
   */
  async addWorklog(issueKeyOrId, params) {
    const body = {};
    if (params.timeSpent) body.timeSpent = params.timeSpent;
    if (params.timeSpentSeconds) body.timeSpentSeconds = params.timeSpentSeconds;
    if (params.started) body.started = params.started;
    if (params.comment) {
      body.comment = {
        type: 'doc', version: 1,
        content: [{ type: 'paragraph', content: [{ type: 'text', text: params.comment }] }],
      };
    }
    return this._request('POST', `/issue/${issueKeyOrId}/worklog`, { body });
  }

  // ===========================================================================
  // LINKS (remote issue links — connect Jira issues to Maestro runs)
  // ===========================================================================

  /**
   * Create a remote issue link (links a Jira issue to an external URL).
   * Used to link Jira issues to Maestro execution receipts.
   * @param {string} issueKeyOrId
   * @param {object} params - { url, title, relationship, iconUrl }
   * @returns {Promise<object>} { id }
   */
  async addRemoteLink(issueKeyOrId, params) {
    return this._request('POST', `/issue/${issueKeyOrId}/remotelink`, {
      body: {
        object: {
          url: params.url,
          title: params.title,
          icon: params.iconUrl ? { url16x16: params.iconUrl } : undefined,
          status: { iconUrl: undefined, resolved: false },
        },
        relationship: params.relationship || 'executed by',
      },
    });
  }

  /**
   * Get remote issue links.
   * @param {string} issueKeyOrId
   */
  async getRemoteLinks(issueKeyOrId) {
    return this._request('GET', `/issue/${issueKeyOrId}/remotelink`);
  }

  /**
   * Delete a remote issue link.
   * @param {string} issueKeyOrId
   * @param {string} linkId
   */
  async deleteRemoteLink(issueKeyOrId, linkId) {
    return this._request('DELETE', `/issue/${issueKeyOrId}/remotelink/${linkId}`);
  }

  // ===========================================================================
  // WEBHOOKS (server-side webhook registration)
  // ===========================================================================

  /**
   * Register a webhook in Jira.
   * @param {object} params - { name, url, events, jqlFilter }
   * @returns {Promise<object>} { webhookId }
   */
  async registerWebhook(params) {
    return this._request('POST', '/webhook', {
      body: {
        name: params.name,
        url: params.url,
        events: params.events || ['jira:issue_created', 'jira:issue_updated', 'jira:issue_deleted'],
        jqlFilter: params.jqlFilter || '',
        excludeBody: false,
      },
    });
  }

  /**
   * Delete a registered webhook.
   * @param {string} webhookId
   */
  async deleteWebhook(webhookId) {
    return this._request('DELETE', `/webhook/${webhookId}`);
  }
}

// ===========================================================================
// HELPERS
// ===========================================================================

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Custom error for Jira API errors.
 */
export class JiraApiError extends Error {
  constructor(message, statusCode, code = 'API_ERROR', details = null) {
    super(message);
    this.name = 'JiraApiError';
    this.statusCode = statusCode;
    this.code = code;
    this.details = details;
  }
}

/**
 * Get the Atlassian cloud ID for the user's Jira instance.
 * Called after OAuth to determine which Jira Cloud instance to use.
 * @param {string} accessToken
 * @returns {Promise<{ cloudId: string, url: string, name: string }>}
 */
export async function getAccessibleResource(accessToken) {
  const response = await fetch('https://api.atlassian.com/oauth/token/accessible-resources', {
    headers: { 'Authorization': `Bearer ${accessToken}`, 'Accept': 'application/json' },
  });

  if (!response.ok) {
    throw new JiraApiError('Failed to get accessible resources', response.status);
  }

  const resources = await response.json();
  if (resources.length === 0) {
    throw new JiraApiError('No accessible Jira instances. Ensure the app is installed on your Jira site.', 403);
  }

  // Return first resource (user can have multiple Jira instances)
  const resource = resources[0];
  return {
    cloudId: resource.id,
    url: resource.url,
    name: resource.name,
    scopes: resource.scopes,
  };
}

/**
 * Exchange authorization code for OAuth tokens.
 * @param {string} code - Authorization code from Atlassian
 * @returns {Promise<{ access_token: string, refresh_token: string, expires_in: number, scope: string }>}
 */
export async function exchangeCodeForTokens(code) {
  const response = await fetch('https://auth.atlassian.com/oauth/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      grant_type: 'authorization_code',
      client_id: process.env.ATLASSIAN_CLIENT_ID,
      client_secret: process.env.ATLASSIAN_CLIENT_SECRET,
      code,
      redirect_uri: process.env.ATLASSIAN_REDIRECT_URI,
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new JiraApiError(error.error_description || 'Token exchange failed', response.status, 'AUTH_ERROR', error);
  }

  return response.json();
}

/**
 * Generate the Atlassian OAuth authorization URL.
 * @param {string} state - CSRF state token
 * @returns {string} Authorization URL
 */
export function getAuthorizationUrl(state) {
  const params = new URLSearchParams({
    audience: 'api.atlassian.com',
    client_id: process.env.ATLASSIAN_CLIENT_ID,
    scope: 'read:jira-work write:jira-work read:jira-user write:jira-user offline_access',
    redirect_uri: process.env.ATLASSIAN_REDIRECT_URI,
    state,
    response_type: 'code',
    prompt: 'consent',
  });

  return `https://auth.atlassian.com/authorize?${params.toString()}`;
}

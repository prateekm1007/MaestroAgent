// src/integrations/github.js — GitHub integration service.
//
// Connects Maestro to GitHub.
// Handles: OAuth flow, webhook signature verification, event routing,
// PR creation from runs, review posting, issue sync, Actions integration,
// status checks, caching via ETag, monitoring.
//
// Environment variables:
//   GITHUB_CLIENT_ID      — OAuth App client ID
//   GITHUB_CLIENT_SECRET  — OAuth App client secret
//   GITHUB_REDIRECT_URI   — OAuth callback URL
//   GITHUB_WEBHOOK_SECRET — Webhook signing secret

import crypto from 'node:crypto';
import { query } from '../db.js';
import { encrypt, decrypt } from '../crypto.js';
import { webhookEventsRepo, integrationsRepo } from '../repository.js';
import { auditLog } from '../auth.js';
import { GitHubClient, GitHubApiError, getGitHubAuthUrl, exchangeGitHubCodeForToken, getAuthenticatedUser } from './github-client.js';

// ============================================================================
// OAUTH FLOW
// ============================================================================

/**
 * Get the GitHub OAuth authorization URL.
 * @param {string} state - CSRF token
 * @returns {string} URL to redirect user to
 */
export function getGitHubOAuthUrl(state) {
  return getGitHubAuthUrl(state);
}

/**
 * Handle OAuth callback — exchange code for token, store integration.
 * @param {string} orgId
 * @param {string} code - Authorization code
 * @returns {Promise<object>} Integration record
 */
export async function handleGitHubCallback(orgId, code) {
  const tokens = await exchangeGitHubCodeForToken(code);
  const user = await getAuthenticatedUser(tokens.access_token);

  const credentials = encrypt(JSON.stringify({
    accessToken: tokens.access_token,
    tokenType: 'oauth',
    scope: tokens.scope,
    githubUser: user.login,
    githubUserId: user.id,
    avatarUrl: user.avatar_url,
    tokenObtainedAt: new Date().toISOString(),
  }));

  // Remove existing GitHub integration
  await query(
    "UPDATE integrations SET status = 'disconnected', disconnected_at = now() WHERE org_id = $1 AND provider_id = 'github'",
    [orgId]
  );

  const integration = await integrationsRepo.insert({
    org_id: orgId,
    provider_id: 'github',
    provider_name: 'GitHub',
    capabilities: ['create_pr', 'review_pr', 'create_issue', 'trigger_workflow', 'read_repo', 'add_comment', 'create_check_run'],
    config: {
      githubUser: user.login,
      avatarUrl: user.avatar_url,
      repos: [], // populated during sync
    },
    credentials,
    status: 'connected',
  });

  await auditLog(orgId, null, 'integration.connect', { provider: 'github', github_user: user.login });

  return integration;
}

// ============================================================================
// CLIENT FACTORY
// ============================================================================

/**
 * Get an authenticated GitHubClient for an org's GitHub integration.
 * @param {string} orgId
 * @returns {Promise<GitHubClient>}
 */
export async function getGitHubClient(orgId) {
  const integration = await integrationsRepo.findByOrgAndProvider(orgId, 'github');
  if (!integration) {
    throw new Error('GitHub is not connected for this organization');
  }

  const creds = JSON.parse(decrypt(integration.credentials));

  const client = new GitHubClient({
    token: creds.accessToken,
    tokenType: creds.tokenType || 'oauth',
    onTokenRefresh: async () => {
      // GitHub OAuth tokens don't expire by default, but can be revoked
      // For GitHub App installations, this would refresh the installation token
      return false;
    },
    logger: console,
  });

  return client;
}

// ============================================================================
// WEBHOOK VERIFICATION
// ============================================================================

/**
 * Verify a GitHub webhook signature using HMAC-SHA256.
 * GitHub sends: x-hub-signature-256: sha256=<hex>
 *
 * @param {string} secret - Webhook secret
 * @param {string|Buffer} rawBody - Raw request body
 * @param {string} signature - Signature from x-hub-signature-256 header
 * @returns {boolean}
 */
export function verifyGitHubWebhookSignature(secret, rawBody, signature) {
  if (!secret || !rawBody || !signature) return false;

  const expected = 'sha256=' + crypto
    .createHmac('sha256', secret)
    .update(rawBody)
    .digest('hex');

  const bufA = Buffer.from(signature);
  const bufB = Buffer.from(expected);
  if (bufA.length !== bufB.length) return false;
  return crypto.timingSafeEqual(bufA, bufB);
}

/**
 * Verify a GitHub webhook request.
 * @param {object} req - Express request (must have rawBody)
 * @returns {boolean}
 */
export function verifyGitHubWebhook(req) {
  const secret = process.env.GITHUB_WEBHOOK_SECRET;
  if (!secret) {
    console.warn('[github] GITHUB_WEBHOOK_SECRET not set — skipping verification');
    return true; // Allow in dev
  }

  const signature = req.headers['x-hub-signature-256'];
  if (!signature) return false;

  const rawBody = req.rawBody || JSON.stringify(req.body);
  return verifyGitHubWebhookSignature(secret, rawBody, signature);
}

// ============================================================================
// WEBHOOK EVENT HANDLING
// ============================================================================

/**
 * Handle an incoming GitHub webhook event.
 * Implements idempotency via webhook_events table.
 *
 * @param {string} orgId
 * @param {object} payload - GitHub webhook payload
 * @param {object} headers - Request headers
 * @returns {Promise<object>} Processing result
 */
export async function handleGitHubWebhookEvent(orgId, payload, headers = {}) {
  const eventType = headers['x-github-event'];
  const deliveryId = headers['x-github-delivery'];

  if (!eventType || !deliveryId) {
    return { processed: false, reason: 'missing event type or delivery ID' };
  }

  // Idempotency check
  const isDuplicate = await webhookEventsRepo.isDuplicate(orgId, 'github', deliveryId);
  if (isDuplicate) {
    return { processed: false, reason: 'duplicate event' };
  }

  await webhookEventsRepo.markProcessed(orgId, 'github', deliveryId, payload);

  // Update integration stats
  await query(
    'UPDATE integrations SET events_received = events_received + 1, last_sync_at = now() WHERE org_id = $1 AND provider_id = $2',
    [orgId, 'github']
  );

  const action = payload.action;

  switch (eventType) {
    case 'pull_request':
      return handlePullRequestEvent(orgId, payload, action);
    case 'issues':
      return handleIssueEvent(orgId, payload, action);
    case 'push':
      return handlePushEvent(orgId, payload);
    case 'check_run':
      return handleCheckRunEvent(orgId, payload, action);
    case 'workflow_run':
      return handleWorkflowRunEvent(orgId, payload, action);
    case 'issue_comment':
      return handleIssueCommentEvent(orgId, payload, action);
    default:
      return { processed: true, action: 'ignored', eventType };
  }
}

async function handlePullRequestEvent(orgId, payload, action) {
  const pr = payload.pull_request;
  const repo = payload.repository;

  switch (action) {
    case 'opened':
    case 'reopened':
      return {
        processed: true,
        action: 'pr_opened',
        repo: repo.full_name,
        prNumber: pr.number,
        prTitle: pr.title,
        prUrl: pr.html_url,
        branch: pr.head.ref,
        sha: pr.head.sha,
      };

    case 'closed':
      return {
        processed: true,
        action: 'pr_closed',
        repo: repo.full_name,
        prNumber: pr.number,
        merged: pr.merged,
      };

    case 'ready_for_review':
      return {
        processed: true,
        action: 'pr_ready_for_review',
        repo: repo.full_name,
        prNumber: pr.number,
      };

    default:
      return { processed: true, action: 'pr_event_ignored', eventType: action };
  }
}

async function handleIssueEvent(orgId, payload, action) {
  const issue = payload.issue;
  const repo = payload.repository;

  return {
    processed: true,
    action: `issue_${action}`,
    repo: repo.full_name,
    issueNumber: issue.number,
    issueTitle: issue.title,
    state: issue.state,
  };
}

async function handlePushEvent(orgId, payload) {
  const repo = payload.repository;
  const commits = payload.commits || [];

  return {
    processed: true,
    action: 'push',
    repo: repo.full_name,
    ref: payload.ref,
    commitCount: commits.length,
    headCommit: payload.after,
  };
}

async function handleCheckRunEvent(orgId, payload, action) {
  const checkRun = payload.check_run;

  return {
    processed: true,
    action: `check_run_${action}`,
    repo: payload.repository?.full_name,
    checkRunId: checkRun?.id,
    name: checkRun?.name,
    status: checkRun?.status,
    conclusion: checkRun?.conclusion,
    sha: checkRun?.head_sha,
  };
}

async function handleWorkflowRunEvent(orgId, payload, action) {
  const workflowRun = payload.workflow_run;

  return {
    processed: true,
    action: `workflow_run_${action}`,
    repo: payload.repository?.full_name,
    runId: workflowRun?.id,
    name: workflowRun?.name,
    status: workflowRun?.status,
    conclusion: workflowRun?.conclusion,
    branch: workflowRun?.head_branch,
  };
}

async function handleIssueCommentEvent(orgId, payload, action) {
  if (action !== 'created') return { processed: true, action: 'comment_event_ignored' };

  const comment = payload.comment;
  const issue = payload.issue;
  const repo = payload.repository;

  // Check for Maestro commands in comments (e.g. "/maestro review")
  const body = comment.body || '';
  if (body.toLowerCase().startsWith('/maestro ')) {
    const command = body.slice('/maestro '.length).trim();
    return {
      processed: true,
      action: 'maestro_command',
      repo: repo.full_name,
      issueNumber: issue.number,
      command,
      commenter: comment.user?.login,
    };
  }

  return { processed: true, action: 'comment_ignored' };
}

// ============================================================================
// GITHUB ACTIONS (called by Maestro engine)
// ============================================================================

/**
 * Create a PR review from a Maestro execution.
 * @param {string} orgId
 * @param {string} repo - "owner/repo"
 * @param {number} prNumber
 * @param {string} body - Review body (markdown)
 * @param {string} event - 'APPROVE' | 'REQUEST_CHANGES' | 'COMMENT'
 */
export async function createPRReview(orgId, repo, prNumber, body, event = 'COMMENT') {
  const client = await getGitHubClient(orgId);
  const result = await client.createReview(repo, prNumber, { body, event });

  await auditLog(orgId, null, 'integration.github.review_created', {
    repo, prNumber, event,
  });

  return result;
}

/**
 * Create an inline review comment on a specific line.
 * @param {string} orgId
 * @param {string} repo
 * @param {number} prNumber
 * @param {object} params - { body, commit_id, path, line, side }
 */
export async function createReviewComment(orgId, repo, prNumber, params) {
  const client = await getGitHubClient(orgId);
  return client.createReviewComment(repo, prNumber, params);
}

/**
 * Comment on an issue or PR.
 * @param {string} orgId
 * @param {string} repo
 * @param {number} issueOrPrNumber
 * @param {string} body
 */
export async function addGitHubComment(orgId, repo, issueOrPrNumber, body) {
  const client = await getGitHubClient(orgId);
  return client.addIssueComment(repo, issueOrPrNumber, body);
}

/**
 * Create a check run (e.g. "Maestro Review" status check).
 * @param {string} orgId
 * @param {string} repo
 * @param {object} params - { name, head_sha, status, conclusion, output }
 */
export async function createCheckRun(orgId, repo, params) {
  const client = await getGitHubClient(orgId);
  return client.createCheckRun(repo, params);
}

/**
 * Trigger a GitHub Actions workflow.
 * @param {string} orgId
 * @param {string} repo
 * @param {string} workflowId - e.g. "ci.yml"
 * @param {string} ref - Branch name
 * @param {object} inputs - Workflow inputs
 */
export async function triggerWorkflow(orgId, repo, workflowId, ref, inputs = {}) {
  const client = await getGitHubClient(orgId);
  return client.triggerWorkflow(repo, workflowId, ref, inputs);
}

/**
 * Get PR details.
 * @param {string} orgId
 * @param {string} repo
 * @param {number} prNumber
 */
export async function getPullRequest(orgId, repo, prNumber) {
  const client = await getGitHubClient(orgId);
  return client.getPullRequest(repo, prNumber);
}

/**
 * Get PR diff/changes.
 * @param {string} orgId
 * @param {string} repo
 * @param {number} prNumber
 */
export async function getPRDiff(orgId, repo, prNumber) {
  const client = await getGitHubClient(orgId);
  const pr = await client.getPullRequest(repo, prNumber);
  const base = pr.base?.sha;
  const head = pr.head?.sha;

  if (base && head) {
    const comparison = await client.compareCommits(repo, base, head);
    return {
      files: comparison.files || [],
      commits: comparison.commits || [],
      additions: comparison.total_commits,
      deletions: comparison.behind_by,
    };
  }

  return { files: [], commits: [] };
}

/**
 * Search issues in a repo.
 * @param {string} orgId
 * @param {string} repo
 * @param {object} options - { state, labels }
 */
export async function listIssues(orgId, repo, options = {}) {
  const client = await getGitHubClient(orgId);
  return client.listIssues(repo, options);
}

/**
 * Get repository info.
 * @param {string} orgId
 * @param {string} repo
 */
export async function getRepository(orgId, repo) {
  const client = await getGitHubClient(orgId);
  return client.getRepository(repo);
}

/**
 * List workflow runs (GitHub Actions CI/CD).
 * @param {string} orgId
 * @param {string} repo
 * @param {object} options
 */
export async function listWorkflowRuns(orgId, repo, options = {}) {
  const client = await getGitHubClient(orgId);
  return client.listWorkflowRuns(repo, options);
}

// ============================================================================
// SYNC ENGINE
// ============================================================================

/**
 * Sync GitHub repositories and recent activity.
 * @param {string} orgId
 */
export async function syncGitHubRepos(orgId) {
  const client = await getGitHubClient(orgId);
  const integration = await integrationsRepo.findByOrgAndProvider(orgId, 'github');

  if (!integration) return { synced: 0, reason: 'GitHub not connected' };

  let synced = 0;
  let errors = 0;

  try {
    // List repos for the authenticated user
    const repos = await client.listReposForAuthenticatedUser({ per_page: 100 });

    const repoNames = repos.map?.(r => r.full_name) || [];

    // Update integration config with repo list
    await query(
      'UPDATE integrations SET config = config || $1::jsonb WHERE id = $2',
      [JSON.stringify({ repos: repoNames }), integration.id]
    );

    synced = repoNames.length;
  } catch (err) {
    console.error('[github-sync] Error:', err.message);
    errors++;
  }

  await query(
    'UPDATE integrations SET last_sync_at = now() WHERE org_id = $1 AND provider_id = $2',
    [orgId, 'github']
  );

  return { synced, errors };
}

// ============================================================================
// MONITORING
// ============================================================================

/**
 * Get GitHub integration health.
 * @param {string} orgId
 */
export async function getGitHubHealth(orgId) {
  const integration = await integrationsRepo.findByOrgAndProvider(orgId, 'github');

  if (!integration) {
    return { connected: false };
  }

  let apiHealthy = false;
  let apiError = null;
  let rateLimit = null;

  try {
    const client = await getGitHubClient(orgId);
    const limitInfo = await client.getRateLimit();
    apiHealthy = true;
    rateLimit = {
      limit: limitInfo.resources?.core?.limit,
      remaining: limitInfo.resources?.core?.remaining,
      reset: limitInfo.resources?.core?.reset,
    };
  } catch (err) {
    apiError = err.message;
  }

  return {
    connected: integration.status === 'connected',
    api_healthy: apiHealthy,
    api_error: apiError,
    github_user: integration.config?.githubUser,
    repo_count: integration.config?.repos?.length || 0,
    last_sync_at: integration.last_sync_at,
    events_received: integration.events_received,
    events_sent: integration.events_sent,
    rate_limit: rateLimit,
  };
}

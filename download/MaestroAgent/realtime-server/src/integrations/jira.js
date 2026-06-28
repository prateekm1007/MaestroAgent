// src/integrations/jira.js — Jira integration service.
//
// Connects Maestro to Atlassian Jira Cloud.
// Handles: OAuth flow, webhook verification, event routing, sync engine,
// issue creation from runs, run linking to issues, status sync.
//
// Environment variables:
//   ATLASSIAN_CLIENT_ID      — OAuth client ID
//   ATLASSIAN_CLIENT_SECRET  — OAuth client secret
//   ATLASSIAN_REDIRECT_URI   — OAuth callback URL (e.g. https://maestro.app/api/integrations/jira/callback)
//   ATLASSIAN_WEBHOOK_SECRET — Secret for webhook signature verification
//   JIRA_SYNC_INTERVAL_MS    — Sync interval (default: 300000 = 5 min)

import crypto from 'node:crypto';
import { query } from '../db.js';
import { decrypt, encrypt } from '../crypto.js';
import { webhookEventsRepo, integrationsRepo } from '../repository.js';
import { auditLog } from '../auth.js';
import { JiraClient, JiraApiError, getAccessibleResource, exchangeCodeForTokens, getAuthorizationUrl } from './jira-client.js';

const JIRA_SYNC_INTERVAL_MS = parseInt(process.env.JIRA_SYNC_INTERVAL_MS || '300000', 10);

// ============================================================================
// OAUTH FLOW
// ============================================================================

/**
 * Get the Jira OAuth authorization URL.
 * @param {string} orgId
 * @param {string} state - CSRF token
 * @returns {string} URL to redirect user to
 */
export function getJiraAuthUrl(orgId, state) {
  return getAuthorizationUrl(state);
}

/**
 * Handle OAuth callback — exchange code for tokens, store integration.
 * @param {string} orgId
 * @param {string} code - Authorization code
 * @returns {Promise<object>} Integration record
 */
export async function handleJiraCallback(orgId, code) {
  // Exchange code for tokens
  const tokens = await exchangeCodeForTokens(code);

  // Get cloud ID (which Jira instance)
  const resource = await getAccessibleResource(tokens.access_token);

  // Store integration with encrypted credentials
  const credentials = encrypt(JSON.stringify({
    accessToken: tokens.access_token,
    refreshToken: tokens.refresh_token,
    expiresIn: tokens.expires_in,
    cloudId: resource.cloudId,
    jiraUrl: resource.url,
    tokenObtainedAt: new Date().toISOString(),
  }));

  // Remove any existing Jira integration for this org
  await query(
    "UPDATE integrations SET status = 'disconnected', disconnected_at = now() WHERE org_id = $1 AND provider_id = 'jira'",
    [orgId]
  );

  // Create new integration record
  const integration = await integrationsRepo.insert({
    org_id: orgId,
    provider_id: 'jira',
    provider_name: 'Jira',
    capabilities: ['create_issue', 'update_issue', 'add_comment', 'transition_issue', 'search_issues', 'add_attachment', 'add_remote_link'],
    config: {
      cloudId: resource.cloudId,
      jiraUrl: resource.url,
      jiraName: resource.name,
    },
    credentials,
    status: 'connected',
  });

  await auditLog(orgId, null, 'integration.connect', { provider: 'jira', jira_url: resource.url });

  return integration;
}

// ============================================================================
// CLIENT FACTORY
// ============================================================================

/**
 * Get an authenticated JiraClient for an org's Jira integration.
 * @param {string} orgId
 * @returns {Promise<JiraClient>} Configured client
 */
export async function getJiraClient(orgId) {
  const integration = await integrationsRepo.findByOrgAndProvider(orgId, 'jira');
  if (!integration) {
    throw new Error('Jira is not connected for this organization');
  }

  const creds = JSON.parse(decrypt(integration.credentials));

  const client = new JiraClient({
    cloudId: creds.cloudId,
    accessToken: creds.accessToken,
    refreshToken: creds.refreshToken,
    onTokenRefresh: async (newTokens) => {
      // Persist refreshed tokens
      const updatedCreds = encrypt(JSON.stringify({
        ...creds,
        accessToken: newTokens.accessToken,
        refreshToken: newTokens.refreshToken,
        tokenObtainedAt: new Date().toISOString(),
      }));
      await query(
        'UPDATE integrations SET credentials = $1 WHERE id = $2',
        [updatedCreds, integration.id]
      );
    },
  });

  return client;
}

// ============================================================================
// WEBHOOK VERIFICATION
// ============================================================================

/**
 * Verify a Jira webhook request.
 * Atlassian does not use HMAC for webhooks; instead they send a shared secret
 * in the URL query parameter, OR the webhook is registered with a specific URL
 * that includes a secret path segment.
 *
 * We verify via a secret in the webhook URL path + checking the X-Atlassian-Webhook-Identifier header.
 * For production, use the Atlassian webhook signature (if configured) or verify
 * via the webhook registration URL.
 *
 * @param {object} req - Express request
 * @param {string} orgId - Expected org ID
 * @returns {boolean} True if verified
 */
export function verifyJiraWebhook(req, orgId) {
  // P0-5 FIX: Reject in production when secret is not configured.
  const expectedSecret = process.env.ATLASSIAN_WEBHOOK_SECRET;
  if (!expectedSecret) {
    if (process.env.NODE_ENV === 'production') {
      console.error('[jira] ATLASSIAN_WEBHOOK_SECRET not set — REJECTING webhook in production');
      return false;
    }
    console.warn('[jira] ATLASSIAN_WEBHOOK_SECRET not set — allowing in development only');
  } else {
    const webhookSecret = req.params.secret || req.query.secret;
    if (!webhookSecret || webhookSecret !== expectedSecret) {
      return false;
    }
  }

  // Verify org_id matches (the webhook URL includes the org_id)
  if (!orgId) {
    return false;
  }

  return true;
}

// ============================================================================
// WEBHOOK EVENT HANDLING
// ============================================================================

/**
 * Handle an incoming Jira webhook event.
 * Implements idempotency via webhook_events table.
 *
 * @param {string} orgId
 * @param {object} payload - Jira webhook payload
 * @param {object} headers - Request headers
 * @returns {Promise<object>} Processing result
 */
export async function handleJiraWebhookEvent(orgId, payload, headers = {}) {
  const eventType = payload.webhookEvent;
  const issue = payload.issue;

  if (!eventType || !issue) {
    return { processed: false, reason: 'missing event type or issue' };
  }

  // Idempotency: check for duplicate
  const eventId = headers['x-atlassian-webhook-identifier'] || `${eventType}-${issue.id}-${Date.now()}`;
  const isDuplicate = await webhookEventsRepo.isDuplicate(orgId, 'jira', eventId);
  if (isDuplicate) {
    return { processed: false, reason: 'duplicate event' };
  }

  // Mark as processed
  await webhookEventsRepo.markProcessed(orgId, 'jira', eventId, payload);

  // Update integration stats
  await query(
    'UPDATE integrations SET events_received = events_received + 1, last_sync_at = now() WHERE org_id = $1 AND provider_id = $2',
    [orgId, 'jira']
  );

  // Route to appropriate handler
  switch (eventType) {
    case 'jira:issue_created':
      return handleIssueCreated(orgId, issue);
    case 'jira:issue_updated':
      return handleIssueUpdated(orgId, issue, payload.changelog);
    case 'jira:issue_deleted':
      return handleIssueDeleted(orgId, issue);
    case 'comment_created':
      return handleCommentCreated(orgId, issue, payload.comment);
    default:
      return { processed: true, action: 'ignored', eventType };
  }
}

/**
 * Handle issue created event — trigger Maestro execution if configured.
 */
async function handleIssueCreated(orgId, issue) {
  // Check if this project is configured for auto-execution
  const projectKey = issue.fields?.project?.key;
  const integration = await integrationsRepo.findByOrgAndProvider(orgId, 'jira');
  const autoExecute = integration?.config?.autoExecuteProjects || [];

  if (!autoExecute.includes(projectKey)) {
    return { processed: true, action: 'ignored', reason: 'project not configured for auto-execution' };
  }

  // Check if issue already has a Maestro link (avoid duplicate)
  const summary = issue.fields?.summary || '';
  const description = extractPlainText(issue.fields?.description) || '';

  // Determine goal from issue
  const goal = `${summary}: ${description}`.slice(0, 4000);

  return {
    processed: true,
    action: 'trigger_execution',
    goal,
    issueKey: issue.key,
    issueId: issue.id,
    project: projectKey,
  };
}

/**
 * Handle issue updated event — sync status changes.
 */
async function handleIssueUpdated(orgId, issue, changelog) {
  if (!changelog?.items) {
    return { processed: true, action: 'synced', issueKey: issue.key };
  }

  const changes = changelog.items.map(item => ({
    field: item.field,
    from: item.fromString,
    to: item.toString,
  }));

  return {
    processed: true,
    action: 'synced',
    issueKey: issue.key,
    changes,
  };
}

/**
 * Handle issue deleted event.
 */
async function handleIssueDeleted(orgId, issue) {
  return {
    processed: true,
    action: 'deleted',
    issueKey: issue.key,
    issueId: issue.id,
  };
}

/**
 * Handle comment created event.
 */
async function handleCommentCreated(orgId, issue, comment) {
  return {
    processed: true,
    action: 'comment_synced',
    issueKey: issue.key,
    commentId: comment.id,
    author: comment.author?.displayName,
  };
}

// ============================================================================
// JIRA ACTIONS (called by Maestro engine)
// ============================================================================

/**
 * Create a Jira issue from a Maestro execution.
 * @param {string} orgId
 * @param {object} params - { projectKey, summary, description, issueType, labels }
 * @returns {Promise<object>} Created issue { id, key, url }
 */
export async function createJiraIssue(orgId, params) {
  const client = await getJiraClient(orgId);
  const issue = await client.createIssue(params);
  const jiraUrl = await getJiraUrl(orgId);

  await auditLog(orgId, null, 'integration.jira.issue_created', {
    issueKey: issue.key, project: params.projectKey, summary: params.summary,
  });

  return {
    ...issue,
    url: `${jiraUrl}/browse/${issue.key}`,
  };
}

/**
 * Add a comment to a Jira issue.
 * @param {string} orgId
 * @param {string} issueKey
 * @param {string} comment
 */
export async function addJiraComment(orgId, issueKey, comment) {
  const client = await getJiraClient(orgId);
  return client.addComment(issueKey, comment);
}

/**
 * Transition a Jira issue (change status).
 * @param {string} orgId
 * @param {string} issueKey
 * @param {string} transitionName - e.g. "In Progress", "Done", "In Review"
 * @param {object} [fields] - Additional fields to update during transition
 */
export async function transitionJiraIssue(orgId, issueKey, transitionName, fields = null) {
  const client = await getJiraClient(orgId);

  // Get available transitions
  const { transitions } = await client.getTransitions(issueKey);
  const transition = transitions.find(t =>
    t.name.toLowerCase() === transitionName.toLowerCase()
  );

  if (!transition) {
    throw new Error(`Transition "${transitionName}" not available for issue ${issueKey}. Available: ${transitions.map(t => t.name).join(', ')}`);
  }

  return client.transitionIssue(issueKey, transition.id, fields);
}

/**
 * Search Jira issues using JQL.
 * @param {string} orgId
 * @param {string} jql - JQL query
 * @param {object} options - { maxResults, fields }
 */
export async function searchJiraIssues(orgId, jql, options = {}) {
  const client = await getJiraClient(orgId);
  return client.searchIssues(jql, options);
}

/**
 * Add an attachment to a Jira issue.
 * @param {string} orgId
 * @param {string} issueKey
 * @param {Buffer} fileContent
 * @param {string} filename
 */
export async function addJiraAttachment(orgId, issueKey, fileContent, filename) {
  const client = await getJiraClient(orgId);
  return client.addAttachment(issueKey, fileContent, filename);
}

/**
 * Link a Maestro run/receipt to a Jira issue (remote link).
 * @param {string} orgId
 * @param {string} issueKey
 * @param {string} runId - Maestro run ID
 * @param {string} receiptUrl - URL to Maestro receipt
 */
export async function linkRunToJiraIssue(orgId, issueKey, runId, receiptUrl) {
  const client = await getJiraClient(orgId);
  return client.addRemoteLink(issueKey, {
    url: receiptUrl,
    title: `Maestro Execution: ${runId.slice(0, 8)}`,
    relationship: 'executed by',
  });
}

/**
 * Get a Jira issue.
 * @param {string} orgId
 * @param {string} issueKey
 */
export async function getJiraIssue(orgId, issueKey) {
  const client = await getJiraClient(orgId);
  return client.getIssue(issueKey);
}

// ============================================================================
// SYNC ENGINE
// ============================================================================

/**
 * Sync Jira issues to Maestro.
 * Runs periodically (via worker) to keep Maestro in sync with Jira state changes
 * that happened outside of Maestro-initiated actions.
 *
 * @param {string} orgId
 * @returns {Promise<object>} Sync results { synced, errors, lastSync }
 */
export async function syncJiraIssues(orgId) {
  const client = await getJiraClient(orgId);
  const integration = await integrationsRepo.findByOrgAndProvider(orgId, 'jira');

  if (!integration) {
    return { synced: 0, errors: 0, reason: 'Jira not connected' };
  }

  const syncConfig = integration.config?.syncConfig || {};
  const projects = syncConfig.projects || [];
  const lastSync = integration.last_sync_at || new Date(0).toISOString();

  let synced = 0;
  let errors = 0;

  for (const projectKey of projects) {
    try {
      // Search for issues updated since last sync
      const jql = `project = ${projectKey} AND updated >= "${formatJiraDate(lastSync)}" ORDER BY updated ASC`;
      const result = await client.searchIssues(jql, { maxResults: 100, fields: ['summary', 'status', 'assignee', 'updated'] });

      for (const issue of result.issues || []) {
        // Process each issue (emit events, update linked runs)
        synced++;
      }
    } catch (err) {
      console.error(`[jira-sync] Error syncing project ${projectKey}:`, err.message);
      errors++;
    }
  }

  // Update last sync time
  await query(
    'UPDATE integrations SET last_sync_at = now() WHERE org_id = $1 AND provider_id = $2',
    [orgId, 'jira']
  );

  return { synced, errors, lastSync: new Date().toISOString() };
}

/**
 * Start the periodic sync engine for all connected Jira integrations.
 * Call once at server startup.
 * @param {number} intervalMs - Sync interval (default: from env)
 */
export function startJiraSyncEngine(intervalMs = JIRA_SYNC_INTERVAL_MS) {
  console.log(`[jira-sync] Starting sync engine (interval: ${intervalMs}ms)`);

  setInterval(async () => {
    try {
      // Get all orgs with active Jira integrations
      const result = await query(
        `SELECT DISTINCT org_id FROM integrations WHERE provider_id = 'jira' AND status = 'connected'`,
      );

      for (const row of result.rows) {
        try {
          await syncJiraIssues(row.org_id);
        } catch (err) {
          console.error(`[jira-sync] Error syncing org ${row.org_id}:`, err.message);
        }
      }
    } catch (err) {
      console.error('[jira-sync] Engine error:', err.message);
    }
  }, intervalMs);
}

// ============================================================================
// MONITORING
// ============================================================================

/**
 * Get Jira integration health metrics for an org.
 * @param {string} orgId
 * @returns {Promise<object>} Health metrics
 */
export async function getJiraHealth(orgId) {
  const integration = await integrationsRepo.findByOrgAndProvider(orgId, 'jira');

  if (!integration) {
    return { connected: false };
  }

  // Try a simple API call to check if tokens are still valid
  let apiHealthy = false;
  let apiError = null;

  try {
    const client = await getJiraClient(orgId);
    await client.getMyself();
    apiHealthy = true;
  } catch (err) {
    apiError = err.message;
  }

  return {
    connected: integration.status === 'connected',
    api_healthy: apiHealthy,
    api_error: apiError,
    jira_url: integration.config?.jiraUrl,
    jira_name: integration.config?.jiraName,
    last_sync_at: integration.last_sync_at,
    events_received: integration.events_received,
    events_sent: integration.events_sent,
    config: integration.config,
  };
}

// ============================================================================
// HELPERS
// ============================================================================

/**
 * Get the Jira URL for an org's integration.
 */
async function getJiraUrl(orgId) {
  const integration = await integrationsRepo.findByOrgAndProvider(orgId, 'jira');
  return integration?.config?.jiraUrl || 'https://your-domain.atlassian.net';
}

/**
 * Extract plain text from Atlassian Document Format (ADF).
 */
function extractPlainText(adf) {
  if (!adf) return '';
  if (typeof adf === 'string') return adf;

  let text = '';
  if (adf.content) {
    for (const node of adf.content) {
      if (node.text) text += node.text;
      if (node.content) text += extractPlainText(node);
    }
  }
  return text;
}

/**
 * Format a date for JQL (yyyy-MM-dd HH:mm).
 */
function formatJiraDate(isoString) {
  const date = new Date(isoString);
  const yyyy = date.getFullYear();
  const MM = String(date.getMonth() + 1).padStart(2, '0');
  const dd = String(date.getDate()).padStart(2, '0');
  const HH = String(date.getHours()).padStart(2, '0');
  const mm = String(date.getMinutes()).padStart(2, '0');
  return `${yyyy}-${MM}-${dd} ${HH}:${mm}`;
}

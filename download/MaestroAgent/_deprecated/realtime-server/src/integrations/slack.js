// src/integrations/slack.js — Slack integration service.
//
// Handles: OAuth, webhook verification, slash commands, interactive buttons,
// approval workflows, notifications, workflow triggers, monitoring.
//
// Environment variables:
//   SLACK_CLIENT_ID       — Slack app client ID
//   SLACK_CLIENT_SECRET   — Slack app client secret
//   SLACK_SIGNING_SECRET  — Slack app signing secret (for webhook verification)
//   SLACK_REDIRECT_URI    — OAuth callback URL

import crypto from 'node:crypto';
import { query } from '../db.js';
import { encrypt, decrypt } from '../crypto.js';
import { webhookEventsRepo, integrationsRepo } from '../repository.js';
import { auditLog } from '../auth.js';
import {
  SlackClient,
  SlackApiError,
  getSlackAuthUrl,
  exchangeSlackCodeForToken,
  verifySlackSignature,
  Blocks,
} from './slack-client.js';

// ============================================================================
// OAUTH FLOW
// ============================================================================

export function getSlackOAuthUrl(state) {
  return getSlackAuthUrl(state);
}

export async function handleSlackCallback(orgId, code) {
  const tokens = await exchangeSlackCodeForToken(code);

  const credentials = encrypt(JSON.stringify({
    botToken: tokens.access_token,
    botUserId: tokens.bot_user_id,
    teamId: tokens.team?.id,
    teamName: tokens.team?.name,
    webhookUrl: tokens.incoming_webhook?.url,
    webhookChannel: tokens.incoming_webhook?.channel,
    webhookChannelId: tokens.incoming_webhook?.channel_id,
    scopes: tokens.scope,
    tokenObtainedAt: new Date().toISOString(),
  }));

  await query(
    "UPDATE integrations SET status = 'disconnected', disconnected_at = now() WHERE org_id = $1 AND provider_id = 'slack'",
    [orgId]
  );

  const integration = await integrationsRepo.insert({
    org_id: orgId,
    provider_id: 'slack',
    provider_name: 'Slack',
    capabilities: ['send_message', 'request_approval', 'notify_channel', 'create_thread', 'upload_file', 'schedule_message'],
    config: {
      teamId: tokens.team?.id,
      teamName: tokens.team?.name,
      botUserId: tokens.bot_user_id,
      defaultChannel: tokens.incoming_webhook?.channel,
      defaultChannelId: tokens.incoming_webhook?.channel_id,
      webhookUrl: tokens.incoming_webhook?.url,
    },
    credentials,
    status: 'connected',
  });

  await auditLog(orgId, null, 'integration.connect', {
    provider: 'slack',
    team: tokens.team?.name,
  });

  return integration;
}

// ============================================================================
// CLIENT FACTORY
// ============================================================================

export async function getSlackClient(orgId) {
  const integration = await integrationsRepo.findByOrgAndProvider(orgId, 'slack');
  if (!integration) {
    throw new Error('Slack is not connected for this organization');
  }

  const creds = JSON.parse(decrypt(integration.credentials));

  return new SlackClient({
    botToken: creds.botToken,
    logger: console,
  });
}

// ============================================================================
// WEBHOOK VERIFICATION
// ============================================================================

// P0-5 FIX: Reject webhooks in production when secret is not configured.
export function verifySlackWebhook(req) {
  const secret = process.env.SLACK_SIGNING_SECRET;
  if (!secret) {
    if (process.env.NODE_ENV === 'production') {
      console.error('[slack] SLACK_SIGNING_SECRET not set — REJECTING webhook in production');
      return false;
    }
    console.warn('[slack] SLACK_SIGNING_SECRET not set — allowing in development only');
    return true;
  }

  const signature = req.headers['x-slack-signature'];
  const timestamp = req.headers['x-slack-request-timestamp'];
  const rawBody = req.rawBody || JSON.stringify(req.body);

  return verifySlackSignature(secret, rawBody, signature, timestamp);
}

// ============================================================================
// NOTIFICATIONS
// ============================================================================

/**
 * Send a notification to a Slack channel.
 * @param {string} orgId
 * @param {string} channel - Channel ID or name
 * @param {string} text - Message text (fallback for notifications)
 * @param {array|null} blocks - Block Kit blocks for rich formatting
 * @param {object} options - { thread_ts, icon_emoji }
 */
export async function sendNotification(orgId, channel, text, blocks = null, options = {}) {
  const client = await getSlackClient(orgId);
  return client.postMessage(channel, text, blocks, options);
}

/**
 * Notify about a new Maestro execution.
 */
export async function notifyExecutionStarted(orgId, run) {
  const integration = await integrationsRepo.findByOrgAndProvider(orgId, 'slack');
  const channel = integration?.config?.defaultChannelId;
  if (!channel) return null;

  const blocks = [
    Blocks.header('Maestro Execution Started'),
    Blocks.section(`*Goal:* ${run.goal}`),
    Blocks.sectionWithFields([
      `*Run ID:* ${run.id.slice(0, 8)}`,
      `*Status:* ${run.status}`,
    ]),
    Blocks.actions([
      Blocks.linkButton('View in Maestro', `${process.env.FRONTEND_URL || ''}/runs/${run.id}`),
    ]),
  ];

  return sendNotification(orgId, channel, `Maestro execution started: ${run.goal}`, blocks);
}

/**
 * Notify about execution completion.
 */
export async function notifyExecutionCompleted(orgId, run, result) {
  const integration = await integrationsRepo.findByOrgAndProvider(orgId, 'slack');
  const channel = integration?.config?.defaultChannelId;
  if (!channel) return null;

  const icon = result.status === 'completed' ? 'white_check_mark' : 'x';
  const blocks = [
    Blocks.header(`:${icon}: Maestro Execution ${result.status}`),
    Blocks.section(`*Goal:* ${run.goal}`),
    Blocks.sectionWithFields([
      `*Duration:* ${(result.duration_ms / 1000).toFixed(1)}s`,
      `*Artifacts:* ${result.artifacts?.length || 0}`,
      `*Confidence:* ${result.avg_confidence || 'N/A'}%`,
    ]),
    Blocks.actions([
      Blocks.linkButton('View Receipt', `${process.env.FRONTEND_URL || ''}/runs/${run.id}`),
      Blocks.linkButton('Download Deliverable', `${process.env.FRONTEND_URL || ''}/api/runs/${run.id}/artifacts/${result.final_artifact}`),
    ]),
  ];

  return sendNotification(orgId, channel, `Maestro execution ${result.status}: ${run.goal}`, blocks);
}

/**
 * Notify about a governance violation (blocked execution).
 */
export async function notifyGovernanceViolation(orgId, run, violations) {
  const integration = await integrationsRepo.findByOrgAndProvider(orgId, 'slack');
  const channel = integration?.config?.defaultChannelId;
  if (!channel) return null;

  const violationText = violations.map(v => `• ${v.control} (${v.scope})`).join('\n');
  const blocks = [
    Blocks.header(':warning: Maestro Execution Blocked'),
    Blocks.section(`*Goal:* ${run.goal}`),
    Blocks.section(`*Violations:*\n${violationText}`),
    Blocks.context(['An execution was blocked by governance controls. Review the policy or adjust the plan.']),
  ];

  return sendNotification(orgId, channel, 'Maestro execution blocked by governance', blocks);
}

// ============================================================================
// APPROVALS
// ============================================================================

/**
 * Send an approval request to a Slack channel.
 * The message includes Approve/Reject buttons.
 *
 * @param {string} orgId
 * @param {object} approval - { id, control, description, reviewer, channel, runId }
 * @returns {Promise<object>} Slack message response { ts, channel }
 */
export async function sendApprovalRequest(orgId, approval) {
  const client = await getSlackClient(orgId);
  const channel = approval.channel;

  const value = JSON.stringify({
    approval_id: approval.id,
    run_id: approval.runId,
    control: approval.control,
  });

  const blocks = [
    Blocks.header(':mag: Maestro Approval Required'),
    Blocks.section(`*Policy:* ${approval.control}`),
    Blocks.section(`*Description:* ${approval.description || 'No description provided'}`),
    approval.reviewer ? Blocks.sectionWithFields([`*Reviewer:* ${approval.reviewer}`]) : null,
    Blocks.divider(),
    Blocks.actions([
      Blocks.approveButton(value),
      Blocks.rejectButton(value),
    ]),
  ].filter(Boolean);

  const result = await client.postMessage(
    channel,
    `Approval required: ${approval.control}`,
    blocks
  );

  // Store the message ts for later updates
  await query(
    `INSERT INTO audit_log (org_id, action, resource_type, resource_id, metadata)
     VALUES ($1, 'integration.slack.approval_sent', 'approval', $2, $3)`,
    [orgId, approval.id, JSON.stringify({ channel, ts: result.ts, control: approval.control })]
  );

  return result;
}

/**
 * Handle an approval button click (interactive component).
 * Updates the Slack message and records the decision.
 *
 * @param {string} orgId
 * @param {object} payload - Slack interactive payload
 * @returns {Promise<object>} Response to send back to Slack
 */
export async function handleApprovalAction(orgId, payload) {
  const action = payload.actions?.[0];
  if (!action) return { text: 'No action found' };

  const isApprove = action.action_id === 'maestro_approve';
  const decision = isApprove ? 'approved' : 'rejected';
  const user = payload.user;
  const data = JSON.parse(action.value);

  // Update the Slack message
  const client = await getSlackClient(orgId);
  const updatedBlocks = [
    Blocks.header(isApprove ? ':white_check_mark: Approved' : ':x: Rejected'),
    Blocks.section(`*Policy:* ${data.control}`),
    Blocks.section(`*Decision:* ${decision} by <@${user.id}>`),
    Blocks.context([`Run ID: ${data.run_id?.slice(0, 8) || 'N/A'}`]),
  ];

  await client.updateMessage(
    payload.channel?.id,
    payload.message?.ts,
    `Approval ${decision}: ${data.control} by <@${user.id}>`,
    updatedBlocks
  );

  // Audit log
  await auditLog(orgId, user.id, 'integration.slack.approval_decision', {
    approval_id: data.approval_id,
    run_id: data.run_id,
    control: data.control,
    decision,
    slack_user: user.id,
    slack_user_name: user.name,
  });

  return {
    text: `Approval ${decision} by <@${user.id}>`,
  };
}

// ============================================================================
// SLASH COMMANDS
// ============================================================================

/**
 * Handle a /maestro slash command.
 * Supported commands:
 *   /maestro run <goal>          — Start a new execution
 *   /maestro status              — Show execution metrics
 *   /maestro approve <run_id>    — Approve a pending execution
 *   /maestro help                — Show help
 *
 * @param {string} orgId
 * @param {object} command - Slack command payload
 * @returns {Promise<object>} Slack response
 */
export async function handleSlashCommand(orgId, command) {
  const text = command.text || '';
  const parts = text.split(/\s+/);
  const subcommand = parts[0]?.toLowerCase();

  switch (subcommand) {
    case 'run':
      return handleSlashRun(orgId, parts.slice(1).join(' '), command);

    case 'status':
      return handleSlashStatus(orgId, command);

    case 'help':
      return {
        response_type: 'ephemeral',
        text: '*Maestro Commands:*\n• `/maestro run <goal>` — Start an execution\n• `/maestro status` — Show metrics\n• `/maestro help` — Show this help',
      };

    default:
      return {
        response_type: 'ephemeral',
        text: 'Unknown command. Use `/maestro help` for available commands.',
      };
  }
}

async function handleSlashRun(orgId, goal, command) {
  if (!goal) {
    return {
      response_type: 'ephemeral',
      text: 'Please provide a goal. Usage: `/maestro run <goal>`',
    };
  }

  return {
    response_type: 'in_channel',
    blocks: [
      Blocks.header(':rocket: Maestro Execution Started'),
      Blocks.section(`*Goal:* ${goal}`),
      Blocks.context([`Triggered by <@${command.user_id}> via slash command`]),
    ],
    // The actual run creation is handled by the route handler which calls createRun()
    _maestro_action: 'create_run',
    _maestro_goal: goal,
  };
}

async function handleSlashStatus(orgId, command) {
  // Return a placeholder — the route handler fills in real metrics
  return {
    response_type: 'ephemeral',
    text: 'Fetching your Maestro metrics...',
    _maestro_action: 'show_status',
  };
}

// ============================================================================
// WORKFLOW TRIGGERS (Slack Workflow Builder integration)
// ============================================================================

/**
 * Trigger a Slack Workflow Builder webhook.
 * This allows Maestro to start Slack workflows (e.g., approval chains, notifications).
 *
 * @param {string} webhookUrl - Slack workflow webhook URL
 * @param {object} payload - Workflow inputs
 */
export async function triggerSlackWorkflow(webhookUrl, payload) {
  const response = await fetch(webhookUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new SlackApiError(`Workflow trigger failed: HTTP ${response.status}`, response.status);
  }

  return { ok: true };
}

/**
 * Send a notification to a Slack incoming webhook.
 * Simpler than the Web API — just POST JSON to the webhook URL.
 *
 * @param {string} orgId
 * @param {string} text
 * @param {array|null} blocks
 */
export async function sendWebhookNotification(orgId, text, blocks = null) {
  const integration = await integrationsRepo.findByOrgAndProvider(orgId, 'slack');
  const webhookUrl = integration?.config?.webhookUrl;

  if (!webhookUrl) {
    throw new Error('No incoming webhook URL configured for this Slack integration');
  }

  const client = await getSlackClient(orgId);
  return client.postToWebhook(webhookUrl, { text, blocks });
}

// ============================================================================
// MONITORING
// ============================================================================

export async function getSlackHealth(orgId) {
  const integration = await integrationsRepo.findByOrgAndProvider(orgId, 'slack');

  if (!integration) {
    return { connected: false };
  }

  let apiHealthy = false;
  let apiError = null;
  let teamInfo = null;

  try {
    const client = await getSlackClient(orgId);
    const teamResult = await client.getTeamInfo();
    apiHealthy = true;
    teamInfo = {
      id: teamResult.team?.id,
      name: teamResult.team?.name,
      domain: teamResult.team?.domain,
    };
  } catch (err) {
    apiError = err.message;
  }

  return {
    connected: integration.status === 'connected',
    api_healthy: apiHealthy,
    api_error: apiError,
    team: teamInfo,
    default_channel: integration.config?.defaultChannel,
    bot_user_id: integration.config?.botUserId,
    last_sync_at: integration.last_sync_at,
    events_received: integration.events_received,
    events_sent: integration.events_sent,
  };
}

// ============================================================================
// INTERACTIVE PAYLOAD HANDLING
// ============================================================================

/**
 * Handle any Slack interactive payload (button clicks, modal submissions).
 * Routes to the appropriate handler based on the interaction type.
 *
 * @param {string} orgId
 * @param {object} payload - Slack interactive payload
 * @returns {Promise<object>} Response to send back to Slack
 */
export async function handleInteractivePayload(orgId, payload) {
  const type = payload.type;

  switch (type) {
    case 'block_actions':
      // Button click
      const actionId = payload.actions?.[0]?.action_id;

      if (actionId === 'maestro_approve' || actionId === 'maestro_reject') {
        return handleApprovalAction(orgId, payload);
      }

      return { text: 'Action received' };

    case 'view_submission':
      // Modal form submission
      return { response_action: 'clear' };

    case 'view_closed':
      return {};

    default:
      return { text: 'Payload type not handled' };
  }
}

// integrations.js — Enterprise Integration Framework.
//
// Connects Maestro to the tools enterprises already use:
//   - Jira (issue tracking, project management)
//   - GitHub (code execution, PR reviews)
//   - Slack (notifications, approvals)
//   - ServiceNow (IT service management)
//   - Confluence (documentation)
//   - Microsoft 365 (general productivity)
//   - Google Workspace (docs, sheets)
//
// Each integration is a CONNECTOR that:
//   1. Receives events from the external tool (webhooks)
//   2. Sends commands to the external tool (API calls)
//   3. Translates between Maestro's execution model and the tool's model
//
// Integrations are what make Maestro EMBEDDED rather than a standalone
// tool. Once integrated, Maestro becomes part of the workflow —
// Jira tickets trigger executions, PRs get reviewed by Maestro,
// approvals happen in Slack.

import { promises as fs } from 'node:fs';
import path from 'node:path';

const INTEGRATION_STORE_PATH = path.resolve('./integrations.jsonl');
const integrations = new Map(); // id -> Integration

// Integration provider definitions.
// Each provider has: name, capabilities, authType, eventTypes, apiDoc URL.
export const PROVIDERS = {
  jira: {
    id: 'jira',
    name: 'Jira',
    description: 'Issue tracking and project management',
    capabilities: ['create_issue', 'update_issue', 'link_execution', 'sync_status'],
    authType: 'api_token',
    eventTypes: ['issue_created', 'issue_updated', 'sprint_started'],
    apiBase: 'https://api.atlassian.com',
    icon: '🎯',
  },
  github: {
    id: 'github',
    name: 'GitHub',
    description: 'Code execution, PR reviews, and repository management',
    capabilities: ['create_pr', 'review_pr', 'create_issue', 'trigger_workflow', 'read_repo'],
    authType: 'oauth',
    eventTypes: ['pr_opened', 'pr_reviewed', 'issue_opened', 'push'],
    apiBase: 'https://api.github.com',
    icon: '🐙',
  },
  slack: {
    id: 'slack',
    name: 'Slack',
    description: 'Notifications, approvals, and team communication',
    capabilities: ['send_message', 'request_approval', 'notify_channel', 'create_thread'],
    authType: 'oauth',
    eventTypes: ['message', 'approval_response', 'command'],
    apiBase: 'https://slack.com/api',
    icon: '💬',
  },
  servicenow: {
    id: 'servicenow',
    name: 'ServiceNow',
    description: 'IT service management and operations',
    capabilities: ['create_ticket', 'update_ticket', 'sync_incident', 'link_change'],
    authType: 'basic',
    eventTypes: ['incident_created', 'change_requested', 'ticket_updated'],
    apiBase: 'https://api.service-now.com',
    icon: '🎫',
  },
  confluence: {
    id: 'confluence',
    name: 'Confluence',
    description: 'Documentation and knowledge base',
    capabilities: ['create_page', 'update_page', 'search_docs', 'attach_evidence'],
    authType: 'api_token',
    eventTypes: ['page_created', 'page_updated'],
    apiBase: 'https://api.atlassian.com',
    icon: '📚',
  },
  m365: {
    id: 'm365',
    name: 'Microsoft 365',
    description: 'General productivity suite',
    capabilities: ['send_email', 'create_event', 'read_sharepoint', 'teams_message'],
    authType: 'oauth',
    eventTypes: ['email_received', 'event_created'],
    apiBase: 'https://graph.microsoft.com',
    icon: '🔵',
  },
  gworkspace: {
    id: 'gworkspace',
    name: 'Google Workspace',
    description: 'Docs, Sheets, and Drive integration',
    capabilities: ['create_doc', 'update_sheet', 'share_file', 'read_folder'],
    authType: 'oauth',
    eventTypes: ['doc_created', 'file_shared'],
    apiBase: 'https://www.googleapis.com',
    icon: '📎',
  },
};

export async function initIntegrationStore() {
  try {
    const data = await fs.readFile(INTEGRATION_STORE_PATH, 'utf8');
    for (const line of data.split('\n').filter(Boolean)) {
      try {
        const obj = JSON.parse(line);
        integrations.set(obj.id, obj);
      } catch {}
    }
    console.log(`[integrations] loaded ${integrations.size} integrations from disk`);
  } catch (err) {
    if (err.code !== 'ENOENT') console.warn('[integrations] failed to load:', err.message);
  }
}

async function persist(integration) {
  try { await fs.appendFile(INTEGRATION_STORE_PATH, JSON.stringify(integration) + '\n', 'utf8'); }
  catch (err) { console.warn('[integrations] persist failed:', err.message); }
}

// Connect an integration for an organization.
// In production, this would trigger an OAuth flow or API key validation.
// For now, we register the binding and mark it as 'connected'.
export async function connectIntegration(orgId, providerId, config = {}) {
  const provider = PROVIDERS[providerId];
  if (!provider) throw new Error(`unknown provider: ${providerId}`);

  const integration = {
    id: crypto.randomUUID(),
    orgId,
    providerId,
    providerName: provider.name,
    capabilities: provider.capabilities,
    config: {
      // In production, these would be real OAuth tokens / API keys.
      // For the SDK, we store the binding configuration.
      workspace: config.workspace || null,
      defaultChannel: config.defaultChannel || null,
      defaultProject: config.defaultProject || null,
      autoSync: config.autoSync !== false,
      eventFilter: config.eventFilter || null,
    },
    status: 'connected',
    connectedAt: new Date().toISOString(),
    lastSyncAt: null,
    eventsReceived: 0,
    eventsSent: 0,
  };

  integrations.set(integration.id, integration);
  await persist(integration);
  console.log(`[integrations] connected ${provider.name} for org ${orgId}`);
  return integration;
}

// List all integrations for an organization.
export function listIntegrations(orgId) {
  return Array.from(integrations.values())
    .filter(i => i.orgId === orgId)
    .map(i => ({
      id: i.id,
      providerId: i.providerId,
      providerName: i.providerName,
      status: i.status,
      capabilities: i.capabilities,
      connectedAt: i.connectedAt,
      lastSyncAt: i.lastSyncAt,
      eventsReceived: i.eventsReceived,
      eventsSent: i.eventsSent,
    }));
}

// Disconnect an integration.
export async function disconnectIntegration(integrationId) {
  const integration = integrations.get(integrationId);
  if (!integration) return false;
  integration.status = 'disconnected';
  integration.disconnectedAt = new Date().toISOString();
  await persist(integration);
  return true;
}

// Handle an incoming webhook event from an external tool.
// This is how Maestro receives events from Jira, GitHub, Slack, etc.
export async function handleWebhookEvent(providerId, event, orgId) {
  const provider = PROVIDERS[providerId];
  if (!provider) throw new Error(`unknown provider: ${providerId}`);

  // Find the integration for this org + provider.
  const integration = Array.from(integrations.values()).find(
    i => i.orgId === orgId && i.providerId === providerId && i.status === 'connected'
  );
  if (!integration) {
    return { processed: false, reason: 'no active integration for this org+provider' };
  }

  // Increment event count.
  integration.eventsReceived++;
  integration.lastSyncAt = new Date().toISOString();
  await persist(integration);

  // Process the event based on provider type.
  // In production, each provider would have its own event handler.
  const processed = {
    integrationId: integration.id,
    provider: provider.name,
    eventType: event.type || 'unknown',
    receivedAt: new Date().toISOString(),
    action: determineAction(providerId, event),
  };

  console.log(`[integrations] webhook from ${provider.name}: ${event.type || 'unknown'} → action: ${processed.action}`);
  return { processed: true, result: processed };
}

// Determine what Maestro should do based on an incoming event.
function determineAction(providerId, event) {
  switch (providerId) {
    case 'jira':
      if (event.type === 'issue_created') return 'trigger_execution';
      if (event.type === 'issue_updated') return 'sync_status';
      return 'ignore';
    case 'github':
      if (event.type === 'pr_opened') return 'trigger_review';
      if (event.type === 'issue_opened') return 'trigger_execution';
      return 'ignore';
    case 'slack':
      if (event.type === 'approval_response') return 'update_approval';
      if (event.type === 'command') return 'execute_command';
      return 'ignore';
    case 'servicenow':
      if (event.type === 'change_requested') return 'trigger_governance_review';
      if (event.type === 'incident_created') return 'trigger_investigation';
      return 'ignore';
    case 'confluence':
      if (event.type === 'page_created') return 'index_document';
      return 'ignore';
    default:
      return 'ignore';
  }
}

// Get integration stats for an org.
export function getIntegrationStats(orgId) {
  const orgIntegrations = listIntegrations(orgId);
  return {
    total: orgIntegrations.length,
    connected: orgIntegrations.filter(i => i.status === 'connected').length,
    byProvider: orgIntegrations.reduce((acc, i) => {
      acc[i.providerId] = (acc[i.providerId] || 0) + 1;
      return acc;
    }, {}),
    totalEventsReceived: orgIntegrations.reduce((sum, i) => sum + i.eventsReceived, 0),
    totalEventsSent: orgIntegrations.reduce((sum, i) => sum + i.eventsSent, 0),
    availableProviders: Object.keys(PROVIDERS),
  };
}

// List available providers.
export function listProviders() {
  return Object.values(PROVIDERS);
}

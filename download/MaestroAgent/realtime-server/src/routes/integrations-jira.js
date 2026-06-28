// src/routes/integrations-jira.js — Jira integration API routes.
//
// Endpoints:
//   GET    /api/integrations/jira/auth           — Get OAuth URL
//   GET    /api/integrations/jira/callback       — OAuth callback
//   GET    /api/integrations/jira/health         — Health check
//   POST   /api/integrations/jira/issues         — Create issue
//   GET    /api/integrations/jira/issues/:key    — Get issue
//   POST   /api/integrations/jira/issues/:key/comment  — Add comment
//   POST   /api/integrations/jira/issues/:key/transition — Transition issue
//   POST   /api/integrations/jira/issues/:key/attachment — Add attachment
//   POST   /api/integrations/jira/issues/:key/link      — Link run to issue
//   POST   /api/integrations/jira/search         — Search issues (JQL)
//   POST   /api/integrations/jira/webhook/:orgId — Webhook receiver
//   POST   /api/integrations/jira/sync           — Trigger manual sync

import express from 'express';
import { authMiddleware, requirePerm, PERMISSIONS } from '../auth.js';
import { generateToken } from '../crypto.js';
import {
  getJiraAuthUrl,
  handleJiraCallback,
  getJiraHealth,
  createJiraIssue,
  getJiraIssue,
  addJiraComment,
  transitionJiraIssue,
  addJiraAttachment,
  linkRunToJiraIssue,
  searchJiraIssues,
  verifyJiraWebhook,
  handleJiraWebhookEvent,
  syncJiraIssues,
} from '../integrations/jira.js';

const router = express.Router();

// All routes require auth except webhook and OAuth callback
router.use((req, res, next) => {
  // Skip auth for webhook and OAuth callback
  if (req.path.startsWith('/webhook/') || req.path === '/callback') {
    return next();
  }
  return authMiddleware(req, res, next);
});

// ============================================================================
// OAUTH FLOW
// ============================================================================

router.get('/auth', (req, res) => {
  const state = generateToken(16);
  const url = getJiraAuthUrl(req.user.org_id, state);
  res.json({ auth_url: url, state });
});

router.get('/callback', async (req, res) => {
  const { code, error, error_description } = req.query;

  if (error) {
    const frontendUrl = process.env.FRONTEND_URL || '/';
    return res.redirect(`${frontendUrl}?jira_error=${encodeURIComponent(error_description || error)}`);
  }

  if (!code) {
    return res.status(400).json({ error: 'Missing authorization code' });
  }

  // Use default org or pass via state
  const orgId = req.user?.org_id || req.query.org_id;
  if (!orgId) {
    return res.status(400).json({ error: 'Organization ID required' });
  }

  try {
    await handleJiraCallback(orgId, code);
    const frontendUrl = process.env.FRONTEND_URL || '/';
    return res.redirect(`${frontendUrl}?jira_connected=1`);
  } catch (err) {
    console.error('[jira] OAuth callback error:', err);
    const frontendUrl = process.env.FRONTEND_URL || '/';
    return res.redirect(`${frontendUrl}?jira_error=${encodeURIComponent(err.message)}`);
  }
});

// ============================================================================
// HEALTH
// ============================================================================

router.get('/health', async (req, res) => {
  try {
    const health = await getJiraHealth(req.user.org_id);
    res.json(health);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ============================================================================
// ISSUES
// ============================================================================

router.post('/issues', requirePerm(PERMISSIONS.INTEGRATION_MANAGE), async (req, res) => {
  const { projectKey, summary, description, issueType, labels } = req.body;
  if (!projectKey || !summary) {
    return res.status(400).json({ error: 'projectKey and summary are required' });
  }
  try {
    const issue = await createJiraIssue(req.user.org_id, {
      projectKey, summary, description, issueType, labels,
    });
    res.status(201).json(issue);
  } catch (err) {
    console.error('[jira] Create issue error:', err);
    res.status(err.statusCode || 500).json({ error: err.message });
  }
});

router.get('/issues/:key', async (req, res) => {
  try {
    const issue = await getJiraIssue(req.user.org_id, req.params.key);
    res.json(issue);
  } catch (err) {
    res.status(err.statusCode || 500).json({ error: err.message });
  }
});

router.post('/issues/:key/comment', async (req, res) => {
  const { comment } = req.body;
  if (!comment) return res.status(400).json({ error: 'comment is required' });
  try {
    const result = await addJiraComment(req.user.org_id, req.params.key, comment);
    res.status(201).json(result);
  } catch (err) {
    res.status(err.statusCode || 500).json({ error: err.message });
  }
});

router.post('/issues/:key/transition', async (req, res) => {
  const { transition_name, fields } = req.body;
  if (!transition_name) return res.status(400).json({ error: 'transition_name is required' });
  try {
    await transitionJiraIssue(req.user.org_id, req.params.key, transition_name, fields);
    res.json({ ok: true });
  } catch (err) {
    res.status(err.statusCode || 500).json({ error: err.message });
  }
});

router.post('/issues/:key/attachment', async (req, res) => {
  const { content, filename } = req.body;
  if (!content || !filename) return res.status(400).json({ error: 'content (base64) and filename are required' });
  try {
    const fileBuffer = Buffer.from(content, 'base64');
    const result = await addJiraAttachment(req.user.org_id, req.params.key, fileBuffer, filename);
    res.status(201).json(result);
  } catch (err) {
    res.status(err.statusCode || 500).json({ error: err.message });
  }
});

router.post('/issues/:key/link', async (req, res) => {
  const { run_id, receipt_url } = req.body;
  if (!run_id || !receipt_url) return res.status(400).json({ error: 'run_id and receipt_url are required' });
  try {
    const result = await linkRunToJiraIssue(req.user.org_id, req.params.key, run_id, receipt_url);
    res.status(201).json(result);
  } catch (err) {
    res.status(err.statusCode || 500).json({ error: err.message });
  }
});

// ============================================================================
// SEARCH
// ============================================================================

router.post('/search', async (req, res) => {
  const { jql, max_results, fields } = req.body;
  if (!jql) return res.status(400).json({ error: 'jql is required' });
  try {
    const result = await searchJiraIssues(req.user.org_id, jql, {
      maxResults: max_results || 50,
      fields: fields,
    });
    res.json(result);
  } catch (err) {
    res.status(err.statusCode || 500).json({ error: err.message });
  }
});

// ============================================================================
// WEBHOOK (no auth — verified by secret)
// ============================================================================

router.post('/webhook/:orgId/:secret', async (req, res) => {
  const { orgId, secret } = req.params;

  // Verify webhook
  if (!verifyJiraWebhook(req, orgId)) {
    return res.status(401).json({ error: 'Webhook verification failed' });
  }

  try {
    const result = await handleJiraWebhookEvent(orgId, req.body, req.headers);
    res.json(result);
  } catch (err) {
    console.error('[jira] Webhook error:', err);
    res.status(500).json({ error: 'Webhook processing failed' });
  }
});

// ============================================================================
// MANUAL SYNC
// ============================================================================

router.post('/sync', requirePerm(PERMISSIONS.INTEGRATION_MANAGE), async (req, res) => {
  try {
    const result = await syncJiraIssues(req.user.org_id);
    res.json(result);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

export default router;

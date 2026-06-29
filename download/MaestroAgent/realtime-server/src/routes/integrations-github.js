// src/routes/integrations-github.js — GitHub integration API routes.
//
// Endpoints:
//   GET    /api/integrations/github/auth           — Get OAuth URL
//   GET    /api/integrations/github/callback       — OAuth callback
//   GET    /api/integrations/github/health         — Health check
//   GET    /api/integrations/github/repos          — List synced repos
//   GET    /api/integrations/github/repos/:repo    — Get repo info
//   GET    /api/integrations/github/prs/:repo/:num — Get PR
//   POST   /api/integrations/github/prs/:repo/:num/review — Create review
//   POST   /api/integrations/github/prs/:repo/:num/comment — Add comment
//   POST   /api/integrations/github/issues/:repo   — Create issue
//   GET    /api/integrations/github/issues/:repo   — List issues
//   POST   /api/integrations/github/check-runs/:repo — Create check run
//   POST   /api/integrations/github/workflows/:repo/:id/trigger — Trigger workflow
//   GET    /api/integrations/github/workflows/:repo/runs — List workflow runs
//   POST   /api/integrations/github/webhook/:orgId — Webhook receiver
//   POST   /api/integrations/github/sync           — Trigger manual sync

import express from 'express';
import { authMiddleware, requirePerm, PERMISSIONS } from '../auth.js';
import { generateToken } from '../crypto.js';
import {
  getGitHubOAuthUrl,
  handleGitHubCallback,
  getGitHubHealth,
  getRepository,
  getPullRequest,
  createPRReview,
  addGitHubComment,
  listIssues,
  createCheckRun,
  triggerWorkflow,
  listWorkflowRuns,
  verifyGitHubWebhook,
  handleGitHubWebhookEvent,
  syncGitHubRepos,
  getGitHubClient,
} from '../integrations/github.js';

const router = express.Router();

// Skip auth for webhook and OAuth callback
router.use((req, res, next) => {
  if (req.path.startsWith('/webhook/') || req.path === '/callback') {
    return next();
  }
  return authMiddleware(req, res, next);
});

// Capture raw body for webhook verification
router.use('/webhook/:orgId', express.raw({ type: 'application/json' }), (req, res, next) => {
  if (req.body && Buffer.isBuffer(req.body)) {
    req.rawBody = req.body;
    try { req.body = JSON.parse(req.body.toString()); } catch {}
  }
  next();
});

// ============================================================================
// OAUTH
// ============================================================================

router.get('/auth', (req, res) => {
  const state = generateToken(16);
  const url = getGitHubOAuthUrl(state);
  res.json({ auth_url: url, state });
});

router.get('/callback', async (req, res) => {
  const { code, error, error_description } = req.query;

  if (error) {
    const frontendUrl = process.env.FRONTEND_URL || '/';
    return res.redirect(`${frontendUrl}?github_error=${encodeURIComponent(error_description || error)}`);
  }

  if (!code) return res.status(400).json({ error: 'Missing authorization code' });

  const orgId = req.user?.org_id || req.query.org_id;
  if (!orgId) return res.status(400).json({ error: 'Organization ID required' });

  try {
    await handleGitHubCallback(orgId, code);
    const frontendUrl = process.env.FRONTEND_URL || '/';
    return res.redirect(`${frontendUrl}?github_connected=1`);
  } catch (err) {
    console.error('[github] OAuth callback error:', err);
    const frontendUrl = process.env.FRONTEND_URL || '/';
    return res.redirect(`${frontendUrl}?github_error=${encodeURIComponent(err.message)}`);
  }
});

// ============================================================================
// HEALTH
// ============================================================================

router.get('/health', async (req, res) => {
  try {
    const health = await getGitHubHealth(req.user.org_id);
    res.json(health);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ============================================================================
// REPOSITORIES
// ============================================================================

router.get('/repos', async (req, res) => {
  try {
    const client = await getGitHubClient(req.user.org_id);
    const repos = await client.listReposForAuthenticatedUser({ per_page: 100 });
    res.json({ repos });
  } catch (err) {
    res.status(err.statusCode || 500).json({ error: err.message });
  }
});

router.get('/repos/:repo', async (req, res) => {
  try {
    const repo = await getRepository(req.user.org_id, req.params.repo);
    res.json(repo);
  } catch (err) {
    res.status(err.statusCode || 500).json({ error: err.message });
  }
});

// ============================================================================
// PULL REQUESTS
// ============================================================================

router.get('/prs/:repo/:num', async (req, res) => {
  try {
    const pr = await getPullRequest(req.user.org_id, req.params.repo, parseInt(req.params.num, 10));
    res.json(pr);
  } catch (err) {
    res.status(err.statusCode || 500).json({ error: err.message });
  }
});

router.post('/prs/:repo/:num/review', async (req, res) => {
  const { body, event } = req.body;
  if (!body) return res.status(400).json({ error: 'body is required' });
  try {
    const result = await createPRReview(
      req.user.org_id, req.params.repo, parseInt(req.params.num, 10),
      body, event || 'COMMENT'
    );
    res.status(201).json(result);
  } catch (err) {
    res.status(err.statusCode || 500).json({ error: err.message });
  }
});

router.post('/prs/:repo/:num/comment', async (req, res) => {
  const { body } = req.body;
  if (!body) return res.status(400).json({ error: 'body is required' });
  try {
    const result = await addGitHubComment(
      req.user.org_id, req.params.repo, parseInt(req.params.num, 10), body
    );
    res.status(201).json(result);
  } catch (err) {
    res.status(err.statusCode || 500).json({ error: err.message });
  }
});

// ============================================================================
// ISSUES
// ============================================================================

router.get('/issues/:repo', async (req, res) => {
  try {
    const issues = await listIssues(req.user.org_id, req.params.repo, {
      state: req.query.state || 'open',
    });
    res.json({ issues });
  } catch (err) {
    res.status(err.statusCode || 500).json({ error: err.message });
  }
});

// ============================================================================
// CHECK RUNS (status checks)
// ============================================================================

router.post('/check-runs/:repo', requirePerm(PERMISSIONS.INTEGRATION_MANAGE), async (req, res) => {
  const { name, head_sha, status, conclusion, output } = req.body;
  if (!name || !head_sha) return res.status(400).json({ error: 'name and head_sha are required' });
  try {
    const result = await createCheckRun(req.user.org_id, req.params.repo, {
      name, head_sha, status: status || 'in_progress', conclusion, output,
    });
    res.status(201).json(result);
  } catch (err) {
    res.status(err.statusCode || 500).json({ error: err.message });
  }
});

// ============================================================================
// GITHUB ACTIONS
// ============================================================================

router.post('/workflows/:repo/:id/trigger', requirePerm(PERMISSIONS.INTEGRATION_MANAGE), async (req, res) => {
  const { ref, inputs } = req.body;
  if (!ref) return res.status(400).json({ error: 'ref (branch/tag) is required' });
  try {
    await triggerWorkflow(req.user.org_id, req.params.repo, req.params.id, ref, inputs || {});
    res.status(204).json({ ok: true });
  } catch (err) {
    res.status(err.statusCode || 500).json({ error: err.message });
  }
});

router.get('/workflows/:repo/runs', async (req, res) => {
  try {
    const runs = await listWorkflowRuns(req.user.org_id, req.params.repo, {
      status: req.query.status,
      branch: req.query.branch,
      per_page: parseInt(req.query.per_page) || 30,
    });
    res.json(runs);
  } catch (err) {
    res.status(err.statusCode || 500).json({ error: err.message });
  }
});

// ============================================================================
// WEBHOOK
// ============================================================================

router.post('/webhook/:orgId', async (req, res) => {
  // Verify signature
  if (!verifyGitHubWebhook(req)) {
    return res.status(401).json({ error: 'Webhook signature verification failed' });
  }

  try {
    const result = await handleGitHubWebhookEvent(req.params.orgId, req.body, req.headers);
    res.json(result);
  } catch (err) {
    console.error('[github] Webhook error:', err);
    res.status(500).json({ error: 'Webhook processing failed' });
  }
});

// ============================================================================
// SYNC
// ============================================================================

router.post('/sync', requirePerm(PERMISSIONS.INTEGRATION_MANAGE), async (req, res) => {
  try {
    const result = await syncGitHubRepos(req.user.org_id);
    res.json(result);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

export default router;

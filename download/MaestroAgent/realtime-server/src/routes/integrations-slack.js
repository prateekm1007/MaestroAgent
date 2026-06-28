// src/routes/integrations-slack.js — Slack integration API routes.
//
// Endpoints:
//   GET    /api/integrations/slack/auth           — Get OAuth URL
//   GET    /api/integrations/slack/callback       — OAuth callback
//   GET    /api/integrations/slack/health         — Health check
//   POST   /api/integrations/slack/notify         — Send notification
//   POST   /api/integrations/slack/approval       — Send approval request
//   POST   /api/integrations/slack/webhook/:orgId — Webhook (slash commands + interactive)
//   POST   /api/integrations/slack/workflow       — Trigger Slack workflow
//   POST   /api/integrations/slack/sync           — Manual sync

import express from 'express';
import { authMiddleware, requirePerm, PERMISSIONS } from '../auth.js';
import { generateToken } from '../crypto.js';
import {
  getSlackOAuthUrl,
  handleSlackCallback,
  getSlackHealth,
  sendNotification,
  sendApprovalRequest,
  handleSlashCommand,
  handleInteractivePayload,
  triggerSlackWorkflow,
  sendWebhookNotification,
  verifySlackWebhook,
} from '../integrations/slack.js';

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
    req.rawBody = req.body.toString();
    try { req.body = JSON.parse(req.rawBody); } catch {}
  }
  next();
});

// ============================================================================
// OAUTH
// ============================================================================

router.get('/auth', (req, res) => {
  const state = generateToken(16);
  const url = getSlackOAuthUrl(state);
  res.json({ auth_url: url, state });
});

router.get('/callback', async (req, res) => {
  const { code, error, error_description } = req.query;

  if (error) {
    const frontendUrl = process.env.FRONTEND_URL || '/';
    return res.redirect(`${frontendUrl}?slack_error=${encodeURIComponent(error_description || error)}`);
  }

  if (!code) return res.status(400).json({ error: 'Missing authorization code' });

  const orgId = req.user?.org_id || req.query.org_id;
  if (!orgId) return res.status(400).json({ error: 'Organization ID required' });

  try {
    await handleSlackCallback(orgId, code);
    const frontendUrl = process.env.FRONTEND_URL || '/';
    return res.redirect(`${frontendUrl}?slack_connected=1`);
  } catch (err) {
    console.error('[slack] OAuth callback error:', err);
    const frontendUrl = process.env.FRONTEND_URL || '/';
    return res.redirect(`${frontendUrl}?slack_error=${encodeURIComponent(err.message)}`);
  }
});

// ============================================================================
// HEALTH
// ============================================================================

router.get('/health', async (req, res) => {
  try {
    const health = await getSlackHealth(req.user.org_id);
    res.json(health);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ============================================================================
// NOTIFICATIONS
// ============================================================================

router.post('/notify', async (req, res) => {
  const { channel, text, blocks } = req.body;
  if (!channel || !text) return res.status(400).json({ error: 'channel and text are required' });
  try {
    const result = await sendNotification(req.user.org_id, channel, text, blocks || null);
    res.json(result);
  } catch (err) {
    res.status(err.statusCode || 500).json({ error: err.message });
  }
});

// ============================================================================
// APPROVALS
// ============================================================================

router.post('/approval', async (req, res) => {
  const { id, control, description, reviewer, channel, run_id } = req.body;
  if (!id || !control || !channel) {
    return res.status(400).json({ error: 'id, control, and channel are required' });
  }
  try {
    const result = await sendApprovalRequest(req.user.org_id, {
      id, control, description, reviewer, channel, runId: run_id,
    });
    res.json(result);
  } catch (err) {
    res.status(err.statusCode || 500).json({ error: err.message });
  }
});

// ============================================================================
// WEBHOOK (slash commands + interactive components)
// ============================================================================

router.post('/webhook/:orgId', async (req, res) => {
  // Verify Slack signature
  if (!verifySlackWebhook(req)) {
    return res.status(401).json({ error: 'Slack signature verification failed' });
  }

  const orgId = req.params.orgId;
  const body = req.body;

  // Slash command (form-encoded)
  if (body.command) {
    try {
      const result = await handleSlashCommand(orgId, body);

      // If the command triggers a run creation, handle it here
      if (result._maestro_action === 'create_run') {
        // Return immediate response, then create run async
        res.json({
          response_type: result.response_type,
          text: result.text,
          blocks: result.blocks,
        });

        // The actual run creation would be triggered here
        // via the engine — emit an event or call createRun()
        return;
      }

      if (result._maestro_action === 'show_status') {
        // Fetch metrics and update message
        // For now, return placeholder
        res.json({
          response_type: 'ephemeral',
          text: 'Maestro metrics: Use the Maestro dashboard for full details.',
        });
        return;
      }

      res.json(result);
    } catch (err) {
      console.error('[slack] Slash command error:', err);
      res.json({ response_type: 'ephemeral', text: `Error: ${err.message}` });
    }
    return;
  }

  // Interactive payload (JSON)
  if (body.payload) {
    const payload = typeof body.payload === 'string' ? JSON.parse(body.payload) : body.payload;

    try {
      const result = await handleInteractivePayload(orgId, payload);
      res.json(result);
    } catch (err) {
      console.error('[slack] Interactive payload error:', err);
      res.json({ text: `Error: ${err.message}` });
    }
    return;
  }

  // URL verification (Slack challenge)
  if (body.type === 'url_verification' && body.challenge) {
    return res.json({ challenge: body.challenge });
  }

  res.status(400).json({ error: 'Unknown Slack webhook payload' });
});

// ============================================================================
// WORKFLOW TRIGGER
// ============================================================================

router.post('/workflow', async (req, res) => {
  const { webhook_url, payload } = req.body;
  if (!webhook_url || !payload) {
    return res.status(400).json({ error: 'webhook_url and payload are required' });
  }
  try {
    const result = await triggerSlackWorkflow(webhook_url, payload);
    res.json(result);
  } catch (err) {
    res.status(err.statusCode || 500).json({ error: err.message });
  }
});

// ============================================================================
// WEBHOOK NOTIFICATION (incoming webhook)
// ============================================================================

router.post('/webhook-notify', async (req, res) => {
  const { text, blocks } = req.body;
  if (!text) return res.status(400).json({ error: 'text is required' });
  try {
    const result = await sendWebhookNotification(req.user.org_id, text, blocks || null);
    res.json(result);
  } catch (err) {
    res.status(err.statusCode || 500).json({ error: err.message });
  }
});

export default router;

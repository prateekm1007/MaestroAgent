// src/integrations/slack-client.js — Slack Web API client.
//
// Provides authenticated API calls to Slack using OAuth bot tokens (xoxb-).
//
// Features:
//   - Rate limit handling (429 → Retry-After)
//   - Retry on 5xx (3 attempts, exponential backoff)
//   - All Slack Web API methods used by Maestro
//   - Block Kit builder helpers for rich messages
//
// API reference: https://api.slack.com/methods

import { fetch } from 'undici';
import crypto from 'node:crypto';

const SLACK_API_BASE = 'https://slack.com/api';
const MAX_RETRIES = 3;

export class SlackClient {
  constructor(options) {
    this.botToken = options.botToken;
    this.logger = options.logger || console;
  }

  // ===========================================================================
  // HTTP CORE
  // ===========================================================================

  async _request(method, data = {}) {
    const url = `${SLACK_API_BASE}/${method}`;
    let lastError;

    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      try {
        const formData = new URLSearchParams();
        for (const [key, value] of Object.entries(data)) {
          if (value !== undefined && value !== null) {
            formData.set(key, typeof value === 'object' ? JSON.stringify(value) : String(value));
          }
        }

        const response = await fetch(url, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${this.botToken}`,
            'Content-Type': 'application/x-www-form-urlencoded',
          },
          body: formData.toString(),
        });

        if (response.status === 429) {
          const retryAfter = parseInt(response.headers.get('retry-after') || '60', 10);
          if (attempt < MAX_RETRIES) {
            this.logger.warn(`[slack] Rate limited, retrying after ${retryAfter}s (attempt ${attempt + 1}/${MAX_RETRIES})`);
            await sleep(Math.min(retryAfter, 60) * 1000);
            continue;
          }
          throw new SlackApiError('Rate limit exceeded', 429, 'RATE_LIMITED');
        }

        if (response.status >= 500 && attempt < MAX_RETRIES) {
          const backoff = Math.pow(2, attempt) * 1000;
          this.logger.warn(`[slack] Server error ${response.status}, retrying in ${backoff}ms`);
          await sleep(backoff);
          continue;
        }

        const json = await response.json();

        if (!json.ok) {
          throw new SlackApiError(json.error || 'Slack API error', response.status, json.error, json);
        }

        return json;
      } catch (err) {
        if (err instanceof SlackApiError) throw err;
        lastError = err;
        if (attempt < MAX_RETRIES) {
          const backoff = Math.pow(2, attempt) * 1000;
          this.logger.warn(`[slack] Request error: ${err.message}, retrying in ${backoff}ms`);
          await sleep(backoff);
          continue;
        }
      }
    }

    throw lastError || new SlackApiError('Max retries exceeded', 500, 'MAX_RETRIES');
  }

  // ===========================================================================
  // MESSAGING
  // ===========================================================================

  async postMessage(channel, text, blocks = null, options = {}) {
    return this._request('chat.postMessage', {
      channel,
      text,
      blocks: blocks || undefined,
      mrkdwn: true,
      unfurl_links: options.unfurl_links ?? true,
      unfurl_media: options.unfurl_media ?? false,
      thread_ts: options.thread_ts,
      reply_broadcast: options.reply_broadcast,
      icon_emoji: options.icon_emoji,
      username: options.username || 'Maestro',
    });
  }

  async updateMessage(channel, ts, text, blocks = null) {
    return this._request('chat.update', {
      channel, ts, text, blocks: blocks || undefined,
    });
  }

  async deleteMessage(channel, ts) {
    return this._request('chat.delete', { channel, ts });
  }

  async getPermalink(channel, messageTs) {
    return this._request('chat.getPermalink', { channel, message_ts: messageTs });
  }

  // ===========================================================================
  // VIEWS (Modals)
  // ===========================================================================

  async openView(triggerId, view) {
    return this._request('views.open', { trigger_id: triggerId, view });
  }

  async updateView(viewId, view) {
    return this._request('views.update', { view_id: viewId, view });
  }

  async pushView(triggerId, view) {
    return this._request('views.push', { trigger_id: triggerId, view });
  }

  // ===========================================================================
  // DIALOGS (legacy, for simple interactions)
  // ===========================================================================

  async openDialog(triggerId, dialog) {
    return this._request('dialog.open', { trigger_id: triggerId, dialog });
  }

  // ===========================================================================
  // CHANNELS
  // ===========================================================================

  async createChannel(name, isPrivate = false) {
    return this._request('conversations.create', { name, is_private: isPrivate });
  }

  async listChannels(types = 'public_channel,private_channel', limit = 200) {
    return this._request('conversations.list', { types, limit });
  }

  async getChannelInfo(channel) {
    return this._request('conversations.info', { channel });
  }

  async joinChannel(channel) {
    return this._request('conversations.join', { channel });
  }

  async inviteToChannel(channel, users) {
    return this._request('conversations.invite', {
      channel,
      users: Array.isArray(users) ? users.join(',') : users,
    });
  }

  async setChannelTopic(channel, topic) {
    return this._request('conversations.setTopic', { channel, topic });
  }

  // ===========================================================================
  // USERS
  // ===========================================================================

  async getUserInfo(userId) {
    return this._request('users.info', { user: userId });
  }

  async listUsers(limit = 200) {
    return this._request('users.list', { limit });
  }

  async getUserByEmail(email) {
    return this._request('users.lookupByEmail', { email });
  }

  // ===========================================================================
  // TEAM
  // ===========================================================================

  async getTeamInfo() {
    return this._request('team.info');
  }

  // ===========================================================================
  // INCOMING WEBHOOKS
  // ===========================================================================

  async postToWebhook(webhookUrl, payload) {
    const response = await fetch(webhookUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const text = await response.text();
      throw new SlackApiError(text || `HTTP ${response.status}`, response.status);
    }

    return { ok: true };
  }

  // ===========================================================================
  // REMINDERS / SCHEDULED MESSAGES
  // ===========================================================================

  async scheduleMessage(channel, postAt, text, blocks = null) {
    return this._request('chat.scheduleMessage', {
      channel, post_at: postAt, text, blocks: blocks || undefined,
    });
  }

  // ===========================================================================
  // FILES
  // ===========================================================================

  async uploadFile(channels, filename, content, title = null, fileType = null) {
    return this._request('files.upload', {
      channels: Array.isArray(channels) ? channels.join(',') : channels,
      filename,
      content,
      title,
      filetype: fileType,
    });
  }
}

// ===========================================================================
// HELPERS
// ===========================================================================

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

export class SlackApiError extends Error {
  constructor(message, statusCode, code = 'API_ERROR', details = null) {
    super(message);
    this.name = 'SlackApiError';
    this.statusCode = statusCode;
    this.code = code;
    this.details = details;
  }
}

// ============================================================================
// OAUTH FLOW
// ============================================================================

export function getSlackAuthUrl(state, scopes) {
  const defaultScopes = [
    'chat:write',
    'commands',
    'incoming-webhook',
    'channels:read',
    'groups:read',
    'users:read',
    'users:read.email',
    'team:read',
    'files:write',
  ];

  const params = new URLSearchParams({
    client_id: process.env.SLACK_CLIENT_ID,
    scope: (scopes || defaultScopes).join(','),
    redirect_uri: process.env.SLACK_REDIRECT_URI,
    state,
  });

  return `https://slack.com/oauth/v2/authorize?${params.toString()}`;
}

export async function exchangeSlackCodeForToken(code) {
  const response = await fetch('https://slack.com/api/oauth.v2.access', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      client_id: process.env.SLACK_CLIENT_ID,
      client_secret: process.env.SLACK_CLIENT_SECRET,
      code,
      redirect_uri: process.env.SLACK_REDIRECT_URI,
    }).toString(),
  });

  if (!response.ok) {
    throw new SlackApiError('Token exchange failed', response.status);
  }

  const tokens = await response.json();
  if (!tokens.ok) {
    throw new SlackApiError(tokens.error || 'OAuth failed', 400, 'AUTH_ERROR', tokens);
  }

  return tokens;
}

// ============================================================================
// WEBHOOK SIGNATURE VERIFICATION
// ============================================================================

/**
 * Verify a Slack request signature.
 * Slack sends: X-Slack-Signature: v0=<hex>, X-Slack-Request-Timestamp: <epoch>
 *
 * @param {string} signingSecret - Slack app signing secret
 * @param {string} rawBody - Raw request body as string
 * @param {string} signature - X-Slack-Signature header value
 * @param {string} timestamp - X-Slack-Request-Timestamp header value
 * @param {number} maxAgeSeconds - Max age of request (default: 300 = 5 min)
 * @returns {boolean}
 */
export function verifySlackSignature(signingSecret, rawBody, signature, timestamp, maxAgeSeconds = 300) {
  if (!signingSecret || !rawBody || !signature || !timestamp) return false;

  // Reject requests older than maxAgeSeconds
  const now = Math.floor(Date.now() / 1000);
  if (Math.abs(now - parseInt(timestamp, 10)) > maxAgeSeconds) {
    return false;
  }

  const sigBase = `v0:${timestamp}:${rawBody}`;
  const expected = 'v0=' + crypto
    .createHmac('sha256', signingSecret)
    .update(sigBase)
    .digest('hex');

  const bufA = Buffer.from(signature);
  const bufB = Buffer.from(expected);
  if (bufA.length !== bufB.length) return false;
  return crypto.timingSafeEqual(bufA, bufB);
}

// ============================================================================
// BLOCK KIT HELPERS
// ============================================================================

export const Blocks = {
  header(text) {
    return { type: 'header', text: { type: 'plain_text', text } };
  },

  section(text) {
    return { type: 'section', text: { type: 'mrkdwn', text } };
  },

  sectionWithFields(fields) {
    return { type: 'section', fields: fields.map(f => ({ type: 'mrkdwn', text: f })) };
  },

  divider() {
    return { type: 'divider' };
  },

  context(items) {
    return { type: 'context', elements: items.map(i => ({ type: 'mrkdwn', text: i })) };
  },

  actions(elements) {
    return { type: 'actions', elements };
  },

  button(text, value, style = null, actionId = null) {
    const btn = {
      type: 'button',
      text: { type: 'plain_text', text },
      value,
    };
    if (style) btn.style = style;
    if (actionId) btn.action_id = actionId;
    return btn;
  },

  approveButton(value) {
    return Blocks.button('Approve', value, 'primary', 'maestro_approve');
  },

  rejectButton(value) {
    return Blocks.button('Reject', value, 'danger', 'maestro_reject');
  },

  linkButton(text, url) {
    return { type: 'button', text: { type: 'plain_text', text }, url };
  },
};

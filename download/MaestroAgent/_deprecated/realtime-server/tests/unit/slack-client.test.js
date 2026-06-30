// tests/unit/slack-client.test.js — Unit tests for Slack API client.

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { MockAgent, setGlobalDispatcher } from 'undici';
import {
  SlackClient,
  SlackApiError,
  getSlackAuthUrl,
  verifySlackSignature,
  Blocks,
} from '../../src/integrations/slack-client.js';
import crypto from 'node:crypto';

describe('slack-client', () => {
  let mockAgent;
  let mockPool;

  beforeEach(() => {
    mockAgent = new MockAgent();
    mockAgent.disableNetConnect();
    setGlobalDispatcher(mockAgent);
    mockPool = mockAgent.get('https://slack.com');
  });

  afterEach(() => {
    mockAgent.enableNetConnect();
  });

  function createClient(overrides = {}) {
    return new SlackClient({
      botToken: 'xoxb-test-token',
      logger: { warn: vi.fn(), error: vi.fn(), log: vi.fn() },
      ...overrides,
    });
  }

  function mockReply(method, statusCode, body, headers = {}) {
    mockPool.intercept({
      method: 'POST',
      path: `/api/${method}`,
    }).reply(statusCode, body, {
      headers: { 'content-type': 'application/json', ...headers },
    });
  }

  describe('constructor', () => {
    it('should set bot token', () => {
      const client = createClient();
      expect(client.botToken).toBe('xoxb-test-token');
    });
  });

  describe('postMessage', () => {
    it('should POST to chat.postMessage', async () => {
      mockReply('chat.postMessage', 200, {
        ok: true, channel: 'C123', ts: '1234567890.123',
      });

      const client = createClient();
      const result = await client.postMessage('C123', 'Hello world');
      expect(result.ok).toBe(true);
      expect(result.channel).toBe('C123');
    });

    it('should include blocks when provided', async () => {
      mockReply('chat.postMessage', 200, { ok: true, ts: '123.456' });

      const client = createClient();
      const blocks = [Blocks.header('Test'), Blocks.section('Hello')];
      await client.postMessage('C123', 'fallback', blocks);
    });
  });

  describe('updateMessage', () => {
    it('should POST to chat.update', async () => {
      mockReply('chat.update', 200, { ok: true, channel: 'C123', ts: '123.456' });

      const client = createClient();
      await client.updateMessage('C123', '123.456', 'Updated text');
    });
  });

  describe('deleteMessage', () => {
    it('should POST to chat.delete', async () => {
      mockReply('chat.delete', 200, { ok: true });

      const client = createClient();
      await client.deleteMessage('C123', '123.456');
    });
  });

  describe('openView', () => {
    it('should POST to views.open', async () => {
      mockReply('views.open', 200, { ok: true, view: { id: 'V123' } });

      const client = createClient();
      const result = await client.openView('trigger-123', { type: 'modal', blocks: [] });
      expect(result.view.id).toBe('V123');
    });
  });

  describe('createChannel', () => {
    it('should POST to conversations.create', async () => {
      mockReply('conversations.create', 200, {
        ok: true, channel: { id: 'C456', name: 'test-channel' },
      });

      const client = createClient();
      const result = await client.createChannel('test-channel');
      expect(result.channel.id).toBe('C456');
    });
  });

  describe('listChannels', () => {
    it('should POST to conversations.list', async () => {
      mockReply('conversations.list', 200, {
        ok: true, channels: [{ id: 'C1', name: 'general' }, { id: 'C2', name: 'random' }],
      });

      const client = createClient();
      const result = await client.listChannels();
      expect(result.channels).toHaveLength(2);
    });
  });

  describe('getUserInfo', () => {
    it('should POST to users.info', async () => {
      mockReply('users.info', 200, {
        ok: true, user: { id: 'U123', name: 'testuser', real_name: 'Test User' },
      });

      const client = createClient();
      const result = await client.getUserInfo('U123');
      expect(result.user.name).toBe('testuser');
    });
  });

  describe('getTeamInfo', () => {
    it('should POST to team.info', async () => {
      mockReply('team.info', 200, {
        ok: true, team: { id: 'T123', name: 'Test Team', domain: 'testteam' },
      });

      const client = createClient();
      const result = await client.getTeamInfo();
      expect(result.team.name).toBe('Test Team');
    });
  });

  describe('scheduleMessage', () => {
    it('should POST to chat.scheduleMessage', async () => {
      mockReply('chat.scheduleMessage', 200, {
        ok: true, scheduled_message_id: 'Q123', post_at: '1700000000',
      });

      const client = createClient();
      const result = await client.scheduleMessage('C123', 1700000000, 'Scheduled message');
      expect(result.scheduled_message_id).toBe('Q123');
    });
  });

  describe('uploadFile', () => {
    it('should POST to files.upload', async () => {
      mockReply('files.upload', 200, {
        ok: true, file: { id: 'F123', name: 'test.txt' },
      });

      const client = createClient();
      const result = await client.uploadFile('C123', 'test.txt', 'file content');
      expect(result.file.id).toBe('F123');
    });
  });

  describe('error handling', () => {
    it('should throw SlackApiError on API error', async () => {
      mockReply('chat.postMessage', 200, {
        ok: false, error: 'channel_not_found',
      });

      const client = createClient();
      try {
        await client.postMessage('INVALID', 'test');
        expect.fail('Should have thrown');
      } catch (err) {
        expect(err).toBeInstanceOf(SlackApiError);
        expect(err.code).toBe('channel_not_found');
      }
    });

    it('should retry on 429 rate limit', async () => {
      // First: 429
      mockPool.intercept({
        method: 'POST',
        path: '/api/chat.postMessage',
      }).reply(429, { ok: false, error: 'ratelimited' }, {
        headers: { 'retry-after': '0', 'content-type': 'application/json' },
      });

      // Second: success
      mockReply('chat.postMessage', 200, { ok: true, ts: '123.456' });

      const client = createClient();
      const result = await client.postMessage('C123', 'test');
      expect(result.ok).toBe(true);
    });

    it('should retry on 500 errors', async () => {
      mockPool.intercept({
        method: 'POST',
        path: '/api/chat.postMessage',
      }).reply(500, 'Internal Server Error', {
        headers: { 'content-type': 'text/plain' },
      });

      mockReply('chat.postMessage', 200, { ok: true, ts: '123.456' });

      const client = createClient();
      const result = await client.postMessage('C123', 'test');
      expect(result.ok).toBe(true);
    });
  });

  describe('getSlackAuthUrl', () => {
    it('should generate correct OAuth URL', () => {
      process.env.SLACK_CLIENT_ID = 'test-client-id';
      process.env.SLACK_REDIRECT_URI = 'https://maestro.app/api/integrations/slack/callback';

      const url = getSlackAuthUrl('test-state');
      expect(url).toContain('slack.com/oauth/v2/authorize');
      expect(url).toContain('client_id=test-client-id');
      expect(url).toContain('state=test-state');
    });
  });

  describe('verifySlackSignature', () => {
    it('should verify a valid signature', () => {
      const secret = 'test-signing-secret';
      const rawBody = '{"type\":\"block_actions\"}';
      const timestamp = String(Math.floor(Date.now() / 1000));

      const sigBase = `v0:${timestamp}:${rawBody}`;
      const signature = 'v0=' + crypto.createHmac('sha256', secret).update(sigBase).digest('hex');

      expect(verifySlackSignature(secret, rawBody, signature, timestamp)).toBe(true);
    });

    it('should reject invalid signature', () => {
      const timestamp = String(Math.floor(Date.now() / 1000));
      expect(verifySlackSignature('secret', 'body', 'v0=invalid', timestamp)).toBe(false);
    });

    it('should reject expired timestamps', () => {
      const oldTimestamp = String(Math.floor(Date.now() / 1000) - 600); // 10 min ago
      expect(verifySlackSignature('secret', 'body', 'v0=anything', oldTimestamp)).toBe(false);
    });

    it('should reject missing parameters', () => {
      expect(verifySlackSignature(null, 'body', 'sig', '123')).toBe(false);
      expect(verifySlackSignature('secret', null, 'sig', '123')).toBe(false);
    });
  });

  describe('Blocks helpers', () => {
    it('should create header block', () => {
      const block = Blocks.header('Test Header');
      expect(block.type).toBe('header');
      expect(block.text.text).toBe('Test Header');
    });

    it('should create section block', () => {
      const block = Blocks.section('*Bold text*');
      expect(block.type).toBe('section');
      expect(block.text.type).toBe('mrkdwn');
    });

    it('should create divider block', () => {
      expect(Blocks.divider().type).toBe('divider');
    });

    it('should create context block', () => {
      const block = Blocks.context(['Line 1', 'Line 2']);
      expect(block.type).toBe('context');
      expect(block.elements).toHaveLength(2);
    });

    it('should create actions block', () => {
      const block = Blocks.actions([Blocks.button('Click', 'value')]);
      expect(block.type).toBe('actions');
      expect(block.elements).toHaveLength(1);
    });

    it('should create button', () => {
      const btn = Blocks.button('Approve', 'approval-123', 'primary', 'maestro_approve');
      expect(btn.type).toBe('button');
      expect(btn.text.text).toBe('Approve');
      expect(btn.style).toBe('primary');
      expect(btn.action_id).toBe('maestro_approve');
    });

    it('should create approve button', () => {
      const btn = Blocks.approveButton('{"id":"123"}');
      expect(btn.action_id).toBe('maestro_approve');
      expect(btn.style).toBe('primary');
    });

    it('should create reject button', () => {
      const btn = Blocks.rejectButton('{"id":"123"}');
      expect(btn.action_id).toBe('maestro_reject');
      expect(btn.style).toBe('danger');
    });

    it('should create link button', () => {
      const btn = Blocks.linkButton('View', 'https://example.com');
      expect(btn.url).toBe('https://example.com');
    });
  });
});

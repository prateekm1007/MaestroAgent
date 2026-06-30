// src/llm/providers/anthropic.js — Anthropic Claude provider.

import { LLMProvider, LLMError, parseSSEStream } from '../provider.js';

const ANTHROPIC_API_BASE = 'https://api.anthropic.com/v1';

const PRICING = {
  'claude-3-5-sonnet-20241022': { input: 3.00, output: 15.00 },
  'claude-3-5-haiku-20241022': { input: 0.80, output: 4.00 },
  'claude-3-opus-20240229': { input: 15.00, output: 75.00 },
  'claude-3-sonnet-20240229': { input: 3.00, output: 15.00 },
  'claude-3-haiku-20240307': { input: 0.25, output: 1.25 },
};

export class AnthropicProvider extends LLMProvider {
  name = 'anthropic';
  defaultModel = 'claude-3-5-sonnet-20241022';

  constructor(options) {
    super(options);
    this.baseUrl = options.baseUrl || ANTHROPIC_API_BASE;
    this.apiVersion = options.apiVersion || '2023-06-01';
  }

  async complete(request) {
    const model = request.model || this.defaultModel;
    const body = {
      model,
      max_tokens: request.maxTokens || 4096,
      system: request.system,
      messages: [{ role: 'user', content: request.user }],
      temperature: request.temperature ?? 0.2,
      stream: request.stream ?? true,
    };

    const headers = {
      'x-api-key': this.apiKey,
      'anthropic-version': this.apiVersion,
      'Content-Type': 'application/json',
    };

    const response = await fetch(`${this.baseUrl}/messages`, { method: 'POST', headers, body: JSON.stringify(body) });

    if (response.status === 429) throw new LLMError('Rate limited', 429, 'RATE_LIMITED', this.name, { retry_after: response.headers.get('retry-after') });
    if (response.status === 401 || response.status === 403) throw new LLMError('Auth failed', response.status, 'AUTH_ERROR', this.name);
    if (!response.ok) { const err = await response.json().catch(() => ({})); throw new LLMError(err.error?.message || `HTTP ${response.status}`, response.status, 'API_ERROR', this.name, err); }

    if (request.stream && request.onToken) {
      let fullText = '', pt = 0, ct = 0;
      await parseSSEStream(response, (data) => {
        if (data.type === 'content_block_delta' && data.delta?.text) {
          fullText += data.delta.text;
          request.onToken(data.delta.text);
        }
        if (data.type === 'message_delta' && data.usage) {
          ct = data.usage.output_tokens || ct;
        }
        if (data.type === 'message_start' && data.message?.usage) {
          pt = data.message.usage.input_tokens || pt;
        }
      });
      if (!ct) ct = Math.ceil(fullText.length / 4);
      if (!pt) pt = Math.ceil((request.system + request.user).length / 4);
      return { text: fullText, provider: this.name, model, promptTokens: pt, completionTokens: ct, costUsd: this.estimateCost(model, pt, ct) };
    }

    const data = await response.json();
    let text = '';
    for (const block of data.content || []) {
      if (block.type === 'text') text += block.text;
    }
    const usage = data.usage || {};
    return { text, provider: this.name, model, promptTokens: usage.input_tokens || 0, completionTokens: usage.output_tokens || 0, costUsd: this.estimateCost(model, usage.input_tokens || 0, usage.output_tokens || 0), raw: data };
  }

  async health() { try { const r = await fetch(`${this.baseUrl}/models`, { headers: { 'x-api-key': this.apiKey, 'anthropic-version': this.apiVersion } }); return r.ok; } catch { return false; } }
  async listModels() { try { const r = await fetch(`${this.baseUrl}/models`, { headers: { 'x-api-key': this.apiKey, 'anthropic-version': this.apiVersion } }); if (!r.ok) return []; const d = await r.json(); return (d.data || []).map(m => m.id); } catch { return []; } }
  estimateCost(model, pt, ct) { const p = PRICING[model] || PRICING['claude-3-5-haiku-20241022']; return (pt / 1e6 * p.input) + (ct / 1e6 * p.output); }
}

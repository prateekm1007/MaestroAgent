// src/llm/providers/openai.js — OpenAI provider (also used by Azure and OpenRouter).

import { LLMProvider, LLMError, parseSSEStream, sleep } from '../provider.js';

const OPENAI_API_BASE = 'https://api.openai.com/v1';

const PRICING = {
  'gpt-4o': { input: 2.50, output: 10.00 },
  'gpt-4o-mini': { input: 0.15, output: 0.60 },
  'gpt-4-turbo': { input: 10.00, output: 30.00 },
  'gpt-4': { input: 30.00, output: 60.00 },
  'gpt-3.5-turbo': { input: 0.50, output: 1.50 },
  'o1': { input: 15.00, output: 60.00 },
  'o1-mini': { input: 3.00, output: 12.00 },
  'o3-mini': { input: 3.00, output: 12.00 },
};

export class OpenAIProvider extends LLMProvider {
  name = 'openai';
  defaultModel = 'gpt-4o-mini';

  constructor(options) {
    super(options);
    this.baseUrl = options.baseUrl || OPENAI_API_BASE;
    this.orgId = options.orgId;
  }

  async complete(request) {
    const model = request.model || this.defaultModel;
    const body = {
      model,
      messages: [
        { role: 'system', content: request.system },
        { role: 'user', content: request.user },
      ],
      temperature: request.temperature ?? 0.2,
      stream: request.stream ?? true,
    };
    if (request.maxTokens) body.max_tokens = request.maxTokens;

    const headers = {
      'Authorization': `Bearer ${this.apiKey}`,
      'Content-Type': 'application/json',
    };
    if (this.orgId) headers['OpenAI-Organization'] = this.orgId;

    const response = await fetch(`${this.baseUrl}/chat/completions`, {
      method: 'POST', headers, body: JSON.stringify(body),
    });

    if (response.status === 429) throw new LLMError('Rate limited', 429, 'RATE_LIMITED', this.name, { retry_after: response.headers.get('retry-after') });
    if (response.status === 401 || response.status === 403) throw new LLMError('Auth failed', response.status, 'AUTH_ERROR', this.name);
    if (!response.ok) { const err = await response.json().catch(() => ({})); throw new LLMError(err.error?.message || `HTTP ${response.status}`, response.status, 'API_ERROR', this.name, err); }

    if (request.stream && request.onToken) {
      let fullText = '', promptTokens = 0, completionTokens = 0;
      await parseSSEStream(response, (data) => {
        const delta = data.choices?.[0]?.delta?.content || '';
        if (delta) { fullText += delta; request.onToken(delta); }
        if (data.usage) { promptTokens = data.usage.prompt_tokens || 0; completionTokens = data.usage.completion_tokens || 0; }
      });
      if (!completionTokens) completionTokens = Math.ceil(fullText.length / 4);
      if (!promptTokens) promptTokens = Math.ceil((request.system + request.user).length / 4);
      return { text: fullText, provider: this.name, model, promptTokens, completionTokens, costUsd: this.estimateCost(model, promptTokens, completionTokens) };
    }

    const data = await response.json();
    const usage = data.usage || {};
    return { text: data.choices?.[0]?.message?.content || '', provider: this.name, model, promptTokens: usage.prompt_tokens || 0, completionTokens: usage.completion_tokens || 0, costUsd: this.estimateCost(model, usage.prompt_tokens || 0, usage.completion_tokens || 0), raw: data };
  }

  async health() { try { const r = await fetch(`${this.baseUrl}/models`, { headers: { 'Authorization': `Bearer ${this.apiKey}` } }); return r.ok; } catch { return false; } }
  async listModels() { const r = await fetch(`${this.baseUrl}/models`, { headers: { 'Authorization': `Bearer ${this.apiKey}` } }); if (!r.ok) return []; const d = await r.json(); return (d.data || []).map(m => m.id).sort(); }
  estimateCost(model, pt, ct) { const p = PRICING[model] || PRICING['gpt-4o-mini']; return (pt / 1e6 * p.input) + (ct / 1e6 * p.output); }
}

export class AzureOpenAIProvider extends LLMProvider {
  name = 'azure';
  defaultModel = 'gpt-4o-mini';

  constructor(options) {
    super(options);
    this.baseUrl = options.baseUrl;
    this.deployment = options.deployment;
    this.apiVersion = options.apiVersion || '2024-10-21';
  }

  async complete(request) {
    const model = request.model || this.deployment;
    const body = {
      messages: [{ role: 'system', content: request.system }, { role: 'user', content: request.user }],
      temperature: request.temperature ?? 0.2,
      stream: request.stream ?? true,
      stream_options: request.stream ? { include_usage: true } : undefined,
    };
    if (request.maxTokens) body.max_tokens = request.maxTokens;

    const response = await fetch(`${this.baseUrl}/deployments/${this.deployment}/chat/completions?api-version=${this.apiVersion}`, {
      method: 'POST', headers: { 'api-key': this.apiKey, 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });

    if (response.status === 429) throw new LLMError('Rate limited', 429, 'RATE_LIMITED', this.name);
    if (!response.ok) { const err = await response.json().catch(() => ({})); throw new LLMError(err.error?.message || `HTTP ${response.status}`, response.status, 'API_ERROR', this.name, err); }

    if (request.stream && request.onToken) {
      let fullText = '', pt = 0, ct = 0;
      await parseSSEStream(response, (data) => {
        const delta = data.choices?.[0]?.delta?.content || '';
        if (delta) { fullText += delta; request.onToken(delta); }
        if (data.usage) { pt = data.usage.prompt_tokens || 0; ct = data.usage.completion_tokens || 0; }
      });
      if (!ct) ct = Math.ceil(fullText.length / 4);
      if (!pt) pt = Math.ceil((request.system + request.user).length / 4);
      return { text: fullText, provider: this.name, model, promptTokens: pt, completionTokens: ct, costUsd: this.estimateCost(model, pt, ct) };
    }

    const data = await response.json();
    const usage = data.usage || {};
    return { text: data.choices?.[0]?.message?.content || '', provider: this.name, model, promptTokens: usage.prompt_tokens || 0, completionTokens: usage.completion_tokens || 0, costUsd: this.estimateCost(model, usage.prompt_tokens || 0, usage.completion_tokens || 0), raw: data };
  }

  estimateCost(model, pt, ct) { const p = PRICING[model] || PRICING['gpt-4o-mini']; return (pt / 1e6 * p.input) + (ct / 1e6 * p.output); }
}

export class OpenRouterProvider extends OpenAIProvider {
  name = 'openrouter';
  defaultModel = 'openai/gpt-4o-mini';

  constructor(options) {
    super(options);
    this.baseUrl = options.baseUrl || 'https://openrouter.ai/api/v1';
    this.referer = options.referer || process.env.OPENROUTER_REFERER;
    this.title = options.title || 'Maestro';
  }

  async complete(request) {
    const model = request.model || this.defaultModel;
    const body = {
      model,
      messages: [{ role: 'system', content: request.system }, { role: 'user', content: request.user }],
      temperature: request.temperature ?? 0.2,
      stream: request.stream ?? true,
    };
    if (request.maxTokens) body.max_tokens = request.maxTokens;

    const headers = { 'Authorization': `Bearer ${this.apiKey}`, 'Content-Type': 'application/json' };
    if (this.referer) headers['HTTP-Referer'] = this.referer;
    if (this.title) headers['X-Title'] = this.title;

    const response = await fetch(`${this.baseUrl}/chat/completions`, { method: 'POST', headers, body: JSON.stringify(body) });
    if (response.status === 429) throw new LLMError('Rate limited', 429, 'RATE_LIMITED', this.name);
    if (!response.ok) { const err = await response.json().catch(() => ({})); throw new LLMError(err.error?.message || `HTTP ${response.status}`, response.status, 'API_ERROR', this.name, err); }

    if (request.stream && request.onToken) {
      let fullText = '', pt = 0, ct = 0;
      await parseSSEStream(response, (data) => {
        const delta = data.choices?.[0]?.delta?.content || '';
        if (delta) { fullText += delta; request.onToken(delta); }
        if (data.usage) { pt = data.usage.prompt_tokens || 0; ct = data.usage.completion_tokens || 0; }
      });
      if (!ct) ct = Math.ceil(fullText.length / 4);
      if (!pt) pt = Math.ceil((request.system + request.user).length / 4);
      return { text: fullText, provider: this.name, model, promptTokens: pt, completionTokens: ct, costUsd: this.estimateCost(model, pt, ct) };
    }

    const data = await response.json();
    const usage = data.usage || {};
    return { text: data.choices?.[0]?.message?.content || '', provider: this.name, model, promptTokens: usage.prompt_tokens || 0, completionTokens: usage.completion_tokens || 0, costUsd: this.estimateCost(model, usage.prompt_tokens || 0, usage.completion_tokens || 0), raw: data };
  }
}

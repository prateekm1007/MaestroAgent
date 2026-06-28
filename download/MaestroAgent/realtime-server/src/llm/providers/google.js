// src/llm/providers/google.js — Google Gemini provider.

import { LLMProvider, LLMError, parseSSEStream } from '../provider.js';

const GOOGLE_API_BASE = 'https://generativelanguage.googleapis.com/v1beta';

const PRICING = {
  'gemini-2.0-flash': { input: 0.10, output: 0.40 },
  'gemini-1.5-pro': { input: 1.25, output: 5.00 },
  'gemini-1.5-flash': { input: 0.075, output: 0.30 },
  'gemini-1.5-flash-8b': { input: 0.0375, output: 0.15 },
};

export class GoogleProvider extends LLMProvider {
  name = 'google';
  defaultModel = 'gemini-2.0-flash';

  constructor(options) {
    super(options);
    this.baseUrl = options.baseUrl || GOOGLE_API_BASE;
  }

  async complete(request) {
    const model = request.model || this.defaultModel;
    const stream = request.stream ?? true;
    const action = stream ? 'streamGenerateContent' : 'generateContent';

    const body = {
      systemInstruction: { parts: [{ text: request.system }] },
      contents: [{ role: 'user', parts: [{ text: request.user }] }],
      generationConfig: {
        temperature: request.temperature ?? 0.2,
        maxOutputTokens: request.maxTokens || 8192,
      },
    };

    const url = `${this.baseUrl}/models/${model}:${action}?key=${this.apiKey}${stream ? '&alt=sse' : ''}`;
    const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

    if (response.status === 429) throw new LLMError('Rate limited', 429, 'RATE_LIMITED', this.name);
    if (response.status === 401 || response.status === 403) throw new LLMError('Auth failed', response.status, 'AUTH_ERROR', this.name);
    if (!response.ok) { const err = await response.json().catch(() => ({})); throw new LLMError(err.error?.message || `HTTP ${response.status}`, response.status, 'API_ERROR', this.name, err); }

    if (stream && request.onToken) {
      let fullText = '', pt = 0, ct = 0;
      await parseSSEStream(response, (data) => {
        const text = data.candidates?.[0]?.content?.parts?.[0]?.text || '';
        if (text) { fullText += text; request.onToken(text); }
        if (data.usageMetadata) { pt = data.usageMetadata.promptTokenCount || pt; ct = data.usageMetadata.candidatesTokenCount || ct; }
      });
      if (!ct) ct = Math.ceil(fullText.length / 4);
      if (!pt) pt = Math.ceil((request.system + request.user).length / 4);
      return { text: fullText, provider: this.name, model, promptTokens: pt, completionTokens: ct, costUsd: this.estimateCost(model, pt, ct) };
    }

    const data = await response.json();
    const text = data.candidates?.[0]?.content?.parts?.map(p => p.text).join('') || '';
    const usage = data.usageMetadata || {};
    return { text, provider: this.name, model, promptTokens: usage.promptTokenCount || 0, completionTokens: usage.candidatesTokenCount || 0, costUsd: this.estimateCost(model, usage.promptTokenCount || 0, usage.candidatesTokenCount || 0), raw: data };
  }

  async health() { try { const r = await fetch(`${this.baseUrl}/models?key=${this.apiKey}`); return r.ok; } catch { return false; } }
  async listModels() { try { const r = await fetch(`${this.baseUrl}/models?key=${this.apiKey}`); if (!r.ok) return []; const d = await r.json(); return (d.models || []).map(m => m.name.replace('models/', '')); } catch { return []; } }
  estimateCost(model, pt, ct) { const p = PRICING[model] || PRICING['gemini-2.0-flash']; return (pt / 1e6 * p.input) + (ct / 1e6 * p.output); }
}

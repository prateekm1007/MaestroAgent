// src/llm/providers/glm.js — GLM (ZhiPu AI) provider.
// Also wraps z-ai-web-dev-sdk for backward compatibility.

import { LLMProvider, LLMError } from '../provider.js';
import { promises as fs } from 'node:fs';

const PRICING = {
  'glm-4-plus': { input: 0.50, output: 0.50 },
  'glm-4': { input: 0.35, output: 0.35 },
  'glm-4-flash': { input: 0.00, output: 0.00 },
  'glm-4-air': { input: 0.10, output: 0.10 },
};

export class GLMProvider extends LLMProvider {
  name = 'glm';
  defaultModel = 'glm-4-plus';

  constructor(options) {
    super(options);
    this._zai = null;
  }

  async _getZAI() {
    if (!this._zai) {
      const ZAI = (await import('z-ai-web-dev-sdk')).default;
      this._zai = await ZAI.create();
    }
    return this._zai;
  }

  async complete(request) {
    const model = request.model || this.defaultModel;
    const zai = await this._getZAI();

    try {
      if (request.stream && request.onToken) {
        const stream = await zai.chat.completions.create({
          messages: [
            { role: 'assistant', content: request.system },
            { role: 'user', content: request.user },
          ],
          stream: true,
          thinking: { type: 'disabled' },
        });

        let fullText = '';
        for await (const rawChunk of stream) {
          let text;
          if (rawChunk instanceof Uint8Array || ArrayBuffer.isView(rawChunk)) {
            text = Buffer.from(rawChunk).toString('utf8');
          } else if (typeof rawChunk === 'string') {
            text = rawChunk;
          } else if (rawChunk?.choices?.[0]?.delta?.content) {
            const delta = rawChunk.choices[0].delta.content;
            fullText += delta; request.onToken(delta); continue;
          } else continue;

          // Parse SSE
          const lines = text.split('\n');
          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed.startsWith('data:')) continue;
            const payload = trimmed.slice(5).trim();
            if (payload === '[DONE]') continue;
            try {
              const obj = JSON.parse(payload);
              const delta = obj?.choices?.[0]?.delta?.content || '';
              if (delta) { fullText += delta; request.onToken(delta); }
            } catch {}
          }
        }

        const pt = Math.ceil((request.system + request.user).length / 4);
        const ct = Math.ceil(fullText.length / 4);
        return { text: fullText, provider: this.name, model, promptTokens: pt, completionTokens: ct, costUsd: this.estimateCost(model, pt, ct) };
      }

      // Non-streaming
      const response = await zai.chat.completions.create({
        messages: [
          { role: 'assistant', content: request.system },
          { role: 'user', content: request.user },
        ],
        stream: false,
        thinking: { type: 'disabled' },
      });

      const text = response.choices?.[0]?.message?.content || '';
      return { text, provider: this.name, model, promptTokens: 0, completionTokens: Math.ceil(text.length / 4), costUsd: 0, raw: response };
    } catch (err) {
      if (err.message?.includes('429')) throw new LLMError('Rate limited', 429, 'RATE_LIMITED', this.name);
      throw new LLMError(err.message, 500, 'API_ERROR', this.name);
    }
  }

  async health() { try { await this._getZAI(); return true; } catch { return false; } }
  estimateCost(model, pt, ct) { const p = PRICING[model] || PRICING['glm-4-plus']; return (pt / 1e6 * p.input) + (ct / 1e6 * p.output); }
}

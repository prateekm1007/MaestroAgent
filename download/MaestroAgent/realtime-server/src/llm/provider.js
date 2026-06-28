// src/llm/provider.js — Abstract LLM provider interface.
//
// All providers implement this interface. The router (router.js) uses
// providers interchangeably, selecting based on org config, cost,
// rate limits, and fallback chains.
//
// Provider responsibilities:
//   - Translate Maestro's LLMRequest into the provider's API format
//   - Parse the provider's SSE stream into token deltas
//   - Return an LLMResponse with text + usage + cost
//   - Handle provider-specific auth (API key, OAuth, etc.)
//
// The router handles: retries, fallbacks, rate limits, cost tracking.

/**
 * LLM request — provider-agnostic.
 * @typedef {Object} LLMRequest
 * @property {string} system - System prompt
 * @property {string} user - User prompt
 * @property {string} model - Model identifier (provider-specific)
 * @property {number} temperature - 0-2 (default 0.2)
 * @property {number|null} maxTokens - Max output tokens
 * @property {boolean} stream - Whether to stream tokens
 * @property {function(string): void} [onToken] - Called per token delta (streaming)
 */

/**
 * LLM response — provider-agnostic.
 * @typedef {Object} LLMResponse
 * @property {string} text - Full response text
 * @property {string} provider - Provider name
 * @property {string} model - Model used
 * @property {number} promptTokens - Input token count
 * @property {number} completionTokens - Output token count
 * @property {number} costUsd - Estimated cost in USD
 * @property {Object|null} raw - Raw provider response (optional)
 */

/**
 * Abstract LLM provider.
 * Every provider (OpenAI, Anthropic, Google, GLM, OpenRouter, Azure)
 * extends this class.
 */
export class LLMProvider {
  /** @type {string} */
  name = 'abstract';

  /**
   * @param {Object} options
   * @param {string} options.apiKey
   * @param {string} [options.baseUrl]
   * @param {Object} [options.logger]
   */
  constructor(options) {
    this.apiKey = options.apiKey;
    this.baseUrl = options.baseUrl;
    this.logger = options.logger || console;
  }

  /**
   * Execute a chat completion.
   * @param {LLMRequest} request
   * @returns {Promise<LLMResponse>}
   */
  async complete(request) {
    throw new Error(`${this.name}.complete() not implemented`);
  }

  /**
   * Check if the provider is healthy (reachable).
   * @returns {Promise<boolean>}
   */
  async health() {
    return true;
  }

  /**
   * List available models for this provider.
   * @returns {Promise<string[]>}
   */
  async listModels() {
    return [];
  }

  /**
   * Get the default model for this provider.
   * @returns {string}
   */
  getDefaultModel() {
    return '';
  }

  /**
   * Estimate cost in USD for a completion.
   * @param {string} model
   * @param {number} promptTokens
   * @param {number} completionTokens
   * @returns {number}
   */
  estimateCost(model, promptTokens, completionTokens) {
    return 0;
  }
}

/**
 * Parse an SSE (Server-Sent Events) stream from a fetch Response.
 * Calls onData(jsonObj) for each `data: {...}` line.
 * Calls onDone() when stream ends or [DONE] is received.
 *
 * @param {Response} response - fetch Response with a ReadableStream body
 * @param {function(Object): void} onData - Called per SSE data payload (parsed JSON)
 * @param {function(): void} [onDone] - Called when stream completes
 * @returns {Promise<void>}
 */
export async function parseSSEStream(response, onData, onDone) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || !trimmed.startsWith('data:')) continue;
        const payload = trimmed.slice(5).trim();
        if (payload === '[DONE]') {
          if (onDone) onDone();
          return;
        }
        try {
          const obj = JSON.parse(payload);
          onData(obj);
        } catch {
          // Partial JSON — skip, will be completed in next chunk
        }
      }
    }

    // Flush remaining buffer
    if (buffer.trim().startsWith('data:')) {
      const payload = buffer.trim().slice(5).trim();
      if (payload && payload !== '[DONE]') {
        try {
          onData(JSON.parse(payload));
        } catch {}
      }
    }

    if (onDone) onDone();
  } finally {
    reader.releaseLock();
  }
}

/**
 * Sleep for N milliseconds.
 */
export function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * LLM provider error.
 */
export class LLMError extends Error {
  constructor(message, statusCode, code = 'LLM_ERROR', provider = 'unknown', details = null) {
    super(message);
    this.name = 'LLMError';
    this.statusCode = statusCode;
    this.code = code;
    this.provider = provider;
    this.details = details;
  }

  get isRetryable() {
    return (
      this.statusCode === 429 ||
      this.statusCode >= 500 ||
      this.code === 'RATE_LIMITED' ||
      this.code === 'SERVER_ERROR' ||
      this.code === 'TIMEOUT'
    );
  }

  get isAuthError() {
    return this.statusCode === 401 || this.statusCode === 403;
  }
}

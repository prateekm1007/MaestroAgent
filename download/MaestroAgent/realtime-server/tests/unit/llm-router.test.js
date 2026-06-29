// tests/unit/llm-router.test.js — Tests for the LLM router.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { LLMError, LLMProvider, parseSSEStream, sleep } from '../../src/llm/provider.js';
import {
  getOrgLLMConfig,
  setOrgLLMConfig,
  getCostStats,
  availableProviders,
  complete,
  streamLLM,
} from '../../src/llm/router.js';

describe('llm-router', () => {
  describe('LLMError', () => {
    it('should create error with status, code, and provider', () => {
      const err = new LLMError('Rate limited', 429, 'RATE_LIMITED', 'openai');
      expect(err.message).toBe('Rate limited');
      expect(err.statusCode).toBe(429);
      expect(err.code).toBe('RATE_LIMITED');
      expect(err.provider).toBe('openai');
    });

    it('should identify retryable errors', () => {
      expect(new LLMError('Server error', 500, 'SERVER_ERROR').isRetryable).toBe(true);
      expect(new LLMError('Rate limited', 429, 'RATE_LIMITED').isRetryable).toBe(true);
      expect(new LLMError('Bad request', 400, 'BAD_REQUEST').isRetryable).toBe(false);
    });

    it('should identify auth errors', () => {
      expect(new LLMError('Unauthorized', 401).isAuthError).toBe(true);
      expect(new LLMError('Forbidden', 403).isAuthError).toBe(true);
      expect(new LLMError('Server error', 500).isAuthError).toBe(false);
    });
  });

  describe('LLMProvider (abstract)', () => {
    it('should throw on complete()', async () => {
      const provider = new LLMProvider({ apiKey: 'test' });
      await expect(provider.complete({})).rejects.toThrow('not implemented');
    });

    it('should return true for health() by default', async () => {
      const provider = new LLMProvider({ apiKey: 'test' });
      expect(await provider.health()).toBe(true);
    });

    it('should return empty array for listModels()', async () => {
      const provider = new LLMProvider({ apiKey: 'test' });
      expect(await provider.listModels()).toEqual([]);
    });

    it('should return 0 for estimateCost()', () => {
      const provider = new LLMProvider({ apiKey: 'test' });
      expect(provider.estimateCost('model', 100, 50)).toBe(0);
    });
  });

  describe('parseSSEStream', () => {
    it('should parse SSE data lines', async () => {
      const events = [];
      const mockResponse = {
        body: {
          getReader: () => {
            const chunks = [
              'data: {"choices":[{"delta":{"content":"Hello"}}]}\n',
              'data: {"choices":[{"delta":{"content":" World"}}]}\n',
              'data: [DONE]\n',
            ];
            let idx = 0;
            return {
              read: async () => idx < chunks.length ? { done: false, value: new TextEncoder().encode(chunks[idx++]) } : { done: true },
              releaseLock: () => {},
            };
          },
        },
      };

      await parseSSEStream(mockResponse, (data) => events.push(data));
      expect(events).toHaveLength(2);
      expect(events[0].choices[0].delta.content).toBe('Hello');
      expect(events[1].choices[0].delta.content).toBe(' World');
    });

    it('should handle partial JSON across chunks', async () => {
      const events = [];
      const mockResponse = {
        body: {
          getReader: () => {
            const chunks = [
              'data: {"choices":[{"del',
              'ta":{"content":"Hi"}}]}\n',
              'data: [DONE]\n',
            ];
            let idx = 0;
            return {
              read: async () => idx < chunks.length ? { done: false, value: new TextEncoder().encode(chunks[idx++]) } : { done: true },
              releaseLock: () => {},
            };
          },
        },
      };

      await parseSSEStream(mockResponse, (data) => events.push(data));
      expect(events).toHaveLength(1);
      expect(events[0].choices[0].delta.content).toBe('Hi');
    });
  });

  describe('Org configuration', () => {
    it('should return default config when not set', () => {
      const config = getOrgLLMConfig(null);
      expect(config.provider).toBe('glm');
      expect(config.model).toBe('glm-4-plus');
      expect(config.fallbackChain).toContain('glm');
    });

    it('should set and get org-specific config', () => {
      setOrgLLMConfig('org-1', {
        provider: 'openai',
        model: 'gpt-4o',
        fallbackChain: ['openai', 'anthropic'],
        maxCostPerRun: 1.0,
        temperature: 0.5,
      });
      const config = getOrgLLMConfig('org-1');
      expect(config.provider).toBe('openai');
      expect(config.model).toBe('gpt-4o');
      expect(config.fallbackChain).toEqual(['openai', 'anthropic']);
      expect(config.maxCostPerRun).toBe(1.0);
      expect(config.temperature).toBe(0.5);
    });

    it('should return default for unconfigured org', () => {
      const config = getOrgLLMConfig('unknown-org');
      expect(config.provider).toBe('glm');
    });
  });

  describe('Cost tracking', () => {
    it('should return empty stats for unknown org', () => {
      const stats = getCostStats('unknown');
      expect(stats.totalUsd).toBe(0);
      expect(stats.calls).toBe(0);
    });
  });

  describe('availableProviders', () => {
    it('should return a list of provider names', () => {
      const providers = availableProviders();
      expect(Array.isArray(providers)).toBe(true);
      expect(providers).toContain('glm'); // GLM is always available
    });
  });

  describe('complete() with fallback', () => {
    it('should throw when no providers are available', async () => {
      // This test verifies the error path when the router can't find any providers
      // In the test environment, GLM should be available, so we test a different path:
      // passing an orgId with a fallback chain that doesn't match available providers
      setOrgLLMConfig('test-no-providers', {
        provider: 'nonexistent',
        fallbackChain: ['nonexistent'],
      });

      await expect(complete({
        system: 'test', user: 'test',
        orgId: 'test-no-providers',
      })).rejects.toThrow();
    });
  });

  describe('streamLLM (legacy compatibility)', () => {
    it('should be a function', () => {
      expect(typeof streamLLM).toBe('function');
    });
  });
});

// src/llm/router.js — LLM router with fallback chains, retries, rate limits,
// cost tracking, and per-organization configuration.
//
// This is the single entry point for all LLM calls. The engine and conductor
// call router.complete() instead of a specific provider. The router handles:
//   - Provider selection (based on org config)
//   - Fallback chains (try provider A, if fails try B, then C)
//   - Retries (exponential backoff on 429/5xx)
//   - Rate limit tracking (per-provider)
//   - Cost tracking (per-org, per-run)
//   - Per-org model configuration
//
// Environment variables:
//   OPENAI_API_KEY          — OpenAI API key
//   ANTHROPIC_API_KEY       — Anthropic API key
//   GOOGLE_API_KEY          — Google Gemini API key
//   ZAI_API_KEY             — ZhiPu GLM API key (optional — z-ai SDK may auto-auth)
//   OPENROUTER_API_KEY      — OpenRouter API key
//   AZURE_OPENAI_API_KEY    — Azure OpenAI API key
//   AZURE_OPENAI_BASE_URL   — Azure endpoint
//   AZURE_OPENAI_DEPLOYMENT — Azure deployment name
//
// Per-org configuration (stored in organizations.settings JSONB):
//   {
//     "llm": {
//       "provider": "openai",
//       "model": "gpt-4o-mini",
//       "fallback_chain": ["openai", "anthropic", "glm"],
//       "max_cost_per_run_usd": 0.50,
//       "temperature": 0.2
//     }
//   }

import { LLMError, sleep } from './provider.js';
import { OpenAIProvider, AzureOpenAIProvider, OpenRouterProvider } from './providers/openai.js';
import { AnthropicProvider } from './providers/anthropic.js';
import { GoogleProvider } from './providers/google.js';
import { GLMProvider } from './providers/glm.js';
import { query } from '../db.js';

const MAX_RETRIES = 3;
const RETRY_BASE_DELAY_MS = 1000;
const DEFAULT_FALLBACK_CHAIN = ['glm', 'openai', 'anthropic'];
const DEFAULT_MODEL = 'glm-4-plus';
const DEFAULT_PROVIDER = 'glm';
const DEFAULT_MAX_COST_PER_RUN = 0.50;

// ============================================================================
// PROVIDER REGISTRY
// ============================================================================

let _providers = null;

function createProviders() {
  const providers = {};

  // GLM (always available via z-ai-web-dev-sdk)
  try { providers['glm'] = new GLMProvider({ apiKey: process.env.ZAI_API_KEY || 'auto' }); } catch (e) { console.warn('[llm] GLM provider init failed:', e.message); }

  // OpenAI
  if (process.env.OPENAI_API_KEY) {
    try { providers['openai'] = new OpenAIProvider({ apiKey: process.env.OPENAI_API_KEY, orgId: process.env.OPENAI_ORG_ID }); } catch (e) { console.warn('[llm] OpenAI provider init failed:', e.message); }
  }

  // Anthropic
  if (process.env.ANTHROPIC_API_KEY) {
    try { providers['anthropic'] = new AnthropicProvider({ apiKey: process.env.ANTHROPIC_API_KEY }); } catch (e) { console.warn('[llm] Anthropic provider init failed:', e.message); }
  }

  // Google
  if (process.env.GOOGLE_API_KEY) {
    try { providers['google'] = new GoogleProvider({ apiKey: process.env.GOOGLE_API_KEY }); } catch (e) { console.warn('[llm] Google provider init failed:', e.message); }
  }

  // OpenRouter
  if (process.env.OPENROUTER_API_KEY) {
    try { providers['openrouter'] = new OpenRouterProvider({ apiKey: process.env.OPENROUTER_API_KEY }); } catch (e) { console.warn('[llm] OpenRouter provider init failed:', e.message); }
  }

  // Azure OpenAI
  if (process.env.AZURE_OPENAI_API_KEY && process.env.AZURE_OPENAI_BASE_URL) {
    try {
      providers['azure'] = new AzureOpenAIProvider({
        apiKey: process.env.AZURE_OPENAI_API_KEY,
        baseUrl: process.env.AZURE_OPENAI_BASE_URL,
        deployment: process.env.AZURE_OPENAI_DEPLOYMENT,
      });
    } catch (e) { console.warn('[llm] Azure provider init failed:', e.message); }
  }

  console.log(`[llm] Router initialized with ${Object.keys(providers).length} providers: ${Object.keys(providers).join(', ')}`);
  return providers;
}

function getProviders() {
  if (!_providers) _providers = createProviders();
  return _providers;
}

// ============================================================================
// ORG CONFIGURATION
// ============================================================================

const orgConfigs = new Map(); // orgId -> LLMConfig

/**
 * Get LLM configuration for an organization.
 * Falls back to defaults if not configured.
 * @param {string|null} orgId
 * @returns {Object} { provider, model, fallbackChain, maxCostPerRun, temperature }
 */
export function getOrgLLMConfig(orgId) {
  if (orgId && orgConfigs.has(orgId)) return orgConfigs.get(orgId);
  return {
    provider: DEFAULT_PROVIDER,
    model: DEFAULT_MODEL,
    fallbackChain: DEFAULT_FALLBACK_CHAIN,
    maxCostPerRun: DEFAULT_MAX_COST_PER_RUN,
    temperature: 0.2,
  };
}

/**
 * Set LLM configuration for an organization.
 * @param {string} orgId
 * @param {Object} config
 */
export function setOrgLLMConfig(orgId, config) {
  orgConfigs.set(orgId, {
    provider: config.provider || DEFAULT_PROVIDER,
    model: config.model || DEFAULT_MODEL,
    fallbackChain: config.fallbackChain || DEFAULT_FALLBACK_CHAIN,
    maxCostPerRun: config.maxCostPerRun || DEFAULT_MAX_COST_PER_RUN,
    temperature: config.temperature ?? 0.2,
  });
}

/**
 * Load org LLM config from database.
 * @param {string} orgId
 */
export async function loadOrgLLMConfig(orgId) {
  try {
    const result = await query('SELECT settings FROM organizations WHERE id = $1', [orgId]);
    const settings = result.rows[0]?.settings || {};
    if (settings.llm) {
      setOrgLLMConfig(orgId, settings.llm);
    }
  } catch {}
}

// ============================================================================
// COST TRACKING
// ============================================================================

const costLedger = new Map(); // orgId -> { totalUsd, calls, byProvider }

/**
 * Record a cost for an org.
 */
function recordCost(orgId, provider, model, costUsd, promptTokens, completionTokens) {
  if (!orgId) return;
  if (!costLedger.has(orgId)) {
    costLedger.set(orgId, { totalUsd: 0, calls: 0, byProvider: {} });
  }
  const ledger = costLedger.get(orgId);
  ledger.totalUsd += costUsd;
  ledger.calls += 1;
  if (!ledger.byProvider[provider]) {
    ledger.byProvider[provider] = { totalUsd: 0, calls: 0, tokens: 0 };
  }
  ledger.byProvider[provider].totalUsd += costUsd;
  ledger.byProvider[provider].calls += 1;
  ledger.byProvider[provider].tokens += promptTokens + completionTokens;
}

/**
 * Get cost stats for an org.
 */
export function getCostStats(orgId) {
  return costLedger.get(orgId) || { totalUsd: 0, calls: 0, byProvider: {} };
}

/**
 * Get all org cost stats.
 */
export function getAllCostStats() {
  const result = {};
  for (const [orgId, stats] of costLedger) {
    result[orgId] = stats;
  }
  return result;
}

// ============================================================================
// RATE LIMIT TRACKING
// ============================================================================

const rateLimits = new Map(); // provider -> { lastLimited, retryAfter }

function isRateLimited(provider) {
  const rl = rateLimits.get(provider);
  if (!rl) return false;
  if (rl.retryAfter && Date.now() < rl.retryAfter) return true;
  rateLimits.delete(provider);
  return false;
}

function markRateLimited(provider, retryAfterSeconds = 60) {
  rateLimits.set(provider, {
    lastLimited: Date.now(),
    retryAfter: Date.now() + retryAfterSeconds * 1000,
  });
}

// ============================================================================
// MAIN ROUTING LOGIC
// ============================================================================

/**
 * Execute an LLM completion with full routing, fallback, retry, and cost tracking.
 *
 * @param {Object} params
 * @param {string} params.system - System prompt
 * @param {string} params.user - User prompt
 * @param {string} [params.model] - Override model
 * @param {number} [params.temperature] - Override temperature
 * @param {number} [params.maxTokens] - Max output tokens
 * @param {boolean} [params.stream] - Stream tokens (default true)
 * @param {function(string): void} [params.onToken] - Token callback
 * @param {string|null} [params.orgId] - Org ID for config/cost tracking
 * @param {string} [params.runId] - Run ID for cost tracking
 * @param {string} [params.agentId] - Agent ID for cost tracking
 * @returns {Promise<Object>} LLMResponse
 */
export async function complete(params) {
  const { system, user, model, temperature, maxTokens, stream = true, onToken, orgId = null, runId = null, agentId = null } = params;

  const config = getOrgLLMConfig(orgId);
  const chain = config.fallbackChain.filter(p => getProviders()[p]); // only available providers
  if (chain.length === 0) throw new LLMError('No LLM providers available', 503, 'NO_PROVIDERS');

  const useModel = model || config.model;
  const useTemp = temperature ?? config.temperature;

  let lastError = null;

  for (const providerName of chain) {
    if (isRateLimited(providerName)) {
      console.warn(`[llm] Provider ${providerName} is rate-limited, skipping`);
      continue;
    }

    const provider = getProviders()[providerName];
    const actualModel = providerName === config.provider ? useModel : provider.getDefaultModel();

    // Retry loop
    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      try {
        const response = await provider.complete({
          system, user,
          model: actualModel,
          temperature: useTemp,
          maxTokens,
          stream,
          onToken,
        });

        // Record cost
        recordCost(orgId, response.provider, response.model, response.costUsd, response.promptTokens, response.completionTokens);

        // Log cost to audit
        if (orgId) {
          query(
            `INSERT INTO audit_log (org_id, action, metadata) VALUES ($1, 'llm.call', $2)`,
            [orgId, JSON.stringify({ provider: response.provider, model: response.model, promptTokens: response.promptTokens, completionTokens: response.completionTokens, costUsd: response.costUsd, runId, agentId })]
          ).catch(() => {});
        }

        return response;
      } catch (err) {
        lastError = err;

        if (err instanceof LLMError) {
          // Rate limited — mark and try next provider
          if (err.code === 'RATE_LIMITED') {
            const retryAfter = err.details?.retry_after;
            markRateLimited(providerName, retryAfter ? parseInt(retryAfter, 10) : 60);
            console.warn(`[llm] Provider ${providerName} rate limited, trying next in chain`);
            break; // Skip remaining retries for this provider, go to next in chain
          }

          // Auth error — don't retry, try next provider
          if (err.isAuthError) {
            console.warn(`[llm] Provider ${providerName} auth failed: ${err.message}, trying next`);
            break;
          }

          // Retryable error (5xx) — retry with backoff
          if (err.isRetryable && attempt < MAX_RETRIES) {
            const delay = RETRY_BASE_DELAY_MS * Math.pow(2, attempt);
            console.warn(`[llm] Provider ${providerName} error (${err.statusCode}), retrying in ${delay}ms (attempt ${attempt + 1}/${MAX_RETRIES})`);
            await sleep(delay);
            continue;
          }
        }

        // Non-retryable error — try next provider
        console.warn(`[llm] Provider ${providerName} failed: ${err.message}, trying next in chain`);
        break;
      }
    }
  }

  throw lastError || new LLMError('All providers failed', 503, 'ALL_PROVIDERS_FAILED');
}

// ============================================================================
// HEALTH CHECK
// ============================================================================

export async function healthCheckAll() {
  const providers = getProviders();
  const results = {};

  for (const [name, provider] of Object.entries(providers)) {
    try {
      results[name] = await provider.health();
    } catch {
      results[name] = false;
    }
  }

  return results;
}

export function availableProviders() {
  return Object.keys(getProviders());
}

export async function listAllModels() {
  const providers = getProviders();
  const results = {};

  for (const [name, provider] of Object.entries(providers)) {
    try {
      const models = await provider.listModels();
      if (models.length > 0) results[name] = models;
    } catch {}
  }

  return results;
}

// ============================================================================
// LEGACY COMPATIBILITY (for engine.js and conductor.js)
// ============================================================================

/**
 * Stream an LLM call — backward-compatible with the old streamLLM interface.
 * Uses the router with default config.
 */
export async function streamLLM({ system, user, onToken, orgId = null }) {
  const response = await complete({
    system, user, stream: true, onToken, orgId,
  });
  return response.text;
}

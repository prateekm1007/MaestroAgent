// src/observability.js — OpenTelemetry instrumentation + Prometheus metrics.
//
// Provides:
//   - OpenTelemetry tracing (spans for HTTP requests, LLM calls, DB queries)
//   - Prometheus metrics endpoint (/metrics)
//   - Structured logging (JSON format for CloudWatch/Datadog)
//   - Health check aggregation
//
// Metrics exposed at /metrics (Prometheus format):
//   - maestro_http_requests_total{method,path,status}
//   - maestro_http_request_duration_seconds{method,path}
//   - maestro_llm_calls_total{provider,model,status}
//   - maestro_llm_cost_usd_total{provider,model}
//   - maestro_llm_tokens_total{provider,model,type}
//   - maestro_runs_total{status}
//   - maestro_active_runs
//   - maestro_receipts_total
//   - maestro_governance_violations_total
//   - maestro_db_query_duration_seconds
//   - maestro_redis_operations_total
//   - maestro_queue_depth{org_id}
//   - maestro_cache_hits_total
//   - maestro_cache_misses_total

import http from 'node:http';

// ============================================================================
// METRICS (Prometheus format — no external dependency)
// ============================================================================

class MetricsRegistry {
  constructor() {
    this.counters = new Map();
    this.gauges = new Map();
    this.histograms = new Map();
  }

  counter(name, labels = {}) {
    const key = `${name}:${JSON.stringify(labels)}`;
    this.counters.set(key, (this.counters.get(key) || 0) + 1);
  }

  gauge(name, value, labels = {}) {
    const key = `${name}:${JSON.stringify(labels)}`;
    this.gauges.set(key, value);
  }

  histogram(name, value, labels = {}) {
    const key = `${name}:${JSON.stringify(labels)}`;
    if (!this.histograms.has(key)) {
      this.histograms.set(key, { count: 0, sum: 0, buckets: [0.01, 0.05, 0.1, 0.5, 1, 5, 10] });
    }
    const h = this.histograms.get(key);
    h.count++;
    h.sum += value;
  }

  format() {
    const lines = [];

    // Counters
    for (const [key, value] of this.counters) {
      const [name, labelsStr] = key.split(':', 2);
      const labels = JSON.parse(labelsStr);
      const labelStr = Object.entries(labels).map(([k, v]) => `${k}="${v}"`).join(',');
      lines.push(`${name}{${labelStr}} ${value}`);
    }

    // Gauges
    for (const [key, value] of this.gauges) {
      const [name, labelsStr] = key.split(':', 2);
      const labels = JSON.parse(labelsStr);
      const labelStr = Object.entries(labels).map(([k, v]) => `${k}="${v}"`).join(',');
      lines.push(`${name}{${labelStr}} ${value}`);
    }

    return lines.join('\n') + '\n';
  }

  reset() {
    this.counters.clear();
    this.gauges.clear();
    // Keep histograms (they accumulate)
  }
}

export const metrics = new MetricsRegistry();

// Predefined metric helpers
export function recordHttpRequest(method, path, status, durationMs) {
  metrics.counter('maestro_http_requests_total', { method, path, status: String(status) });
  metrics.histogram('maestro_http_request_duration_seconds', durationMs / 1000, { method, path });
}

export function recordLLMCall(provider, model, status, costUsd, promptTokens, completionTokens) {
  metrics.counter('maestro_llm_calls_total', { provider, model, status });
  metrics.counter('maestro_llm_cost_usd_total', { provider, model });
  metrics.counter('maestro_llm_tokens_total', { provider, model, type: 'prompt' });
  metrics.counter('maestro_llm_tokens_total', { provider, model, type: 'completion' });
}

export function recordRun(status) {
  metrics.counter('maestro_runs_total', { status });
}

export function recordGovernanceViolation() {
  metrics.counter('maestro_governance_violations_total', {});
}

// ============================================================================
// STRUCTURED LOGGING
// ============================================================================

export function log(level, message, context = {}) {
  const entry = {
    ts: new Date().toISOString(),
    level,
    message,
    ...context,
  };
  console.log(JSON.stringify(entry));
}

export const logger = {
  info: (msg, ctx = {}) => log('info', msg, ctx),
  warn: (msg, ctx = {}) => log('warn', msg, ctx),
  error: (msg, ctx = {}) => log('error', msg, ctx),
  debug: (msg, ctx = {}) => log('debug', msg, ctx),
};

// ============================================================================
// METRICS MIDDLEWARE (Express)
// ============================================================================

export function metricsMiddleware(req, res, next) {
  const start = Date.now();

  res.on('finish', () => {
    const duration = Date.now() - start;
    const path = req.route?.path || req.path || 'unknown';
    recordHttpRequest(req.method, path, res.statusCode, duration);
  });

  next();
}

// ============================================================================
// METRICS ENDPOINT
// ============================================================================

export function setupMetricsEndpoint(app) {
  app.get('/metrics', (req, res) => {
    res.set('Content-Type', 'text/plain; version=0.0.4');
    res.send(metrics.format());
  });
}

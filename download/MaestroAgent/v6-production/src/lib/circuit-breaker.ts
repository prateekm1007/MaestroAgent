// Circuit breaker for external API calls.
// Opens after `failureThreshold` consecutive failures; stays open for `resetTimeoutMs`;
// half-open state allows 1 probe request; closes if probe succeeds.

import { baseLogger } from './logger';

type CircuitState = 'closed' | 'open' | 'half-open';

interface CircuitBreakerOptions {
  name: string;
  failureThreshold: number;       // consecutive failures before opening
  resetTimeoutMs: number;         // how long to stay open before half-open
  successThreshold: number;       // successes in half-open before closing
  timeoutMs: number;              // per-call timeout
}

interface CircuitBreakerState {
  state: CircuitState;
  failureCount: number;
  successCount: number;
  lastFailureAt: number | null;
  openedAt: number | null;
}

const breakers = new Map<string, CircuitBreakerState>();

function getBreaker(name: string): CircuitBreakerState {
  if (!breakers.has(name)) {
    breakers.set(name, {
      state: 'closed',
      failureCount: 0,
      successCount: 0,
      lastFailureAt: null,
      openedAt: null,
    });
  }
  return breakers.get(name)!;
}

export class CircuitOpenError extends Error {
  constructor(public breakerName: string) {
    super(`Circuit breaker "${breakerName}" is open`);
    this.name = 'CircuitOpenError';
  }
}

export async function withCircuitBreaker<T>(
  options: CircuitBreakerOptions,
  fn: () => Promise<T>,
): Promise<T> {
  const breaker = getBreaker(options.name);

  // Check if circuit is open
  if (breaker.state === 'open') {
    const elapsed = Date.now() - (breaker.openedAt || 0);
    if (elapsed >= options.resetTimeoutMs) {
      // Transition to half-open
      breaker.state = 'half-open';
      breaker.successCount = 0;
      baseLogger.warn({ breaker: options.name }, 'Circuit breaker → half-open');
    } else {
      throw new CircuitOpenError(options.name);
    }
  }

  // Execute the function with timeout
  try {
    const result = await withTimeout(fn(), options.timeoutMs);
    onSuccess(breaker, options);
    return result;
  } catch (err) {
    onFailure(breaker, options, err);
    throw err;
  }
}

function onSuccess(breaker: CircuitBreakerState, options: CircuitBreakerOptions): void {
  if (breaker.state === 'half-open') {
    breaker.successCount++;
    if (breaker.successCount >= options.successThreshold) {
      breaker.state = 'closed';
      breaker.failureCount = 0;
      baseLogger.info({ breaker: options.name }, 'Circuit breaker → closed (recovered)');
    }
  } else {
    breaker.failureCount = 0;
  }
}

function onFailure(breaker: CircuitBreakerState, options: CircuitBreakerOptions, err: unknown): void {
  breaker.failureCount++;
  breaker.lastFailureAt = Date.now();

  if (breaker.state === 'half-open') {
    // Half-open failure → reopen
    breaker.state = 'open';
    breaker.openedAt = Date.now();
    baseLogger.error({ breaker: options.name, err }, 'Circuit breaker → open (half-open probe failed)');
    return;
  }

  if (breaker.failureCount >= options.failureThreshold) {
    breaker.state = 'open';
    breaker.openedAt = Date.now();
    baseLogger.error(
      { breaker: options.name, failures: breaker.failureCount },
      'Circuit breaker → open (failure threshold reached)',
    );
  }
}

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new Error(`Operation timed out after ${ms}ms`));
    }, ms);
    promise.then(
      (val) => { clearTimeout(timer); resolve(val); },
      (err) => { clearTimeout(timer); reject(err); },
    );
  });
}

// Health check — for /api/health
export function getCircuitBreakerHealth(): Record<string, { state: CircuitState; failureCount: number }> {
  const result: Record<string, { state: CircuitState; failureCount: number }> = {};
  for (const [name, state] of breakers.entries()) {
    result[name] = { state: state.state, failureCount: state.failureCount };
  }
  return result;
}

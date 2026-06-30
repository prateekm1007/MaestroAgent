// Pino logger with request ID context (AsyncLocalStorage).
// Every log line within a request shares the same requestId — grep-able in production.

import pino from 'pino';
import { AsyncLocalStorage } from 'async_hooks';
import { env } from './env';

const baseLogger = pino({
  name: 'maestro-v6',
  level: env.LOG_LEVEL,
  base: { service: 'maestro-api', version: '0.1.0' },
  redact: {
    paths: [
      'req.headers.authorization',
      'req.headers.cookie',
      '*.password',
      '*.token',
      '*.accessToken',
      '*.refreshToken',
      '*.ENCRYPTION_KEY',
      '*.NEXTAUTH_SECRET',
    ],
    censor: '[REDACTED]',
  },
  formatters: {
    level: (label) => ({ level: label }),
  },
  serializers: {
    req: (req) => ({
      method: req.method,
      url: req.url,
      requestId: req.requestId,
    }),
    err: pino.stdSerializers.err,
  },
});

// AsyncLocalStorage carries requestId across async boundaries
const requestContext = new AsyncLocalStorage<{ requestId: string; userId?: string; orgId?: string }>();

export function withRequestContext<T>(requestId: string, fn: () => T, metadata?: { userId?: string; orgId?: string }): T {
  return requestContext.run({ requestId, ...metadata }, fn);
}

export function log(): pino.Logger {
  const ctx = requestContext.getStore();
  if (ctx) {
    return baseLogger.child({ requestId: ctx.requestId, userId: ctx.userId, orgId: ctx.orgId });
  }
  return baseLogger;
}

export { baseLogger };

// Centralized error types and HTTP error mapper.
// Every error in the system is an ApiError with status, code, message, and optional details.
// The error boundary in Next.js catches thrown ApiErrors and returns structured JSON.

import { NextResponse } from 'next/server';
import { baseLogger } from './logger';
import { ZodError } from 'zod';

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
    // Maintain proper stack trace (V8 only)
    if (Error.captureStackTrace) {
      Error.captureStackTrace(this, ApiError);
    }
  }
}

// ─── Common error factories ───
export const Errors = {
  unauthorized: (message = 'Authentication required') => new ApiError(401, 'UNAUTHORIZED', message),
  forbidden: (message = 'Insufficient permissions') => new ApiError(403, 'FORBIDDEN', message),
  notFound: (entity: string, id: string) => new ApiError(404, 'NOT_FOUND', `${entity} not found: ${id}`),
  conflict: (message: string) => new ApiError(409, 'CONFLICT', message),
  unprocessableEntity: (message: string, details?: unknown) => new ApiError(422, 'UNPROCESSABLE_ENTITY', message, details),
  rateLimited: (retryAfterMs: number) => new ApiError(429, 'RATE_LIMITED', 'Too many requests', { retryAfterMs }),
  internal: (message = 'Internal server error') => new ApiError(500, 'INTERNAL', message),
  badRequest: (message: string, details?: unknown) => new ApiError(400, 'BAD_REQUEST', message, details),
  consentRequired: () => new ApiError(403, 'CONSENT_REQUIRED', 'All participants must consent before recording begins'),
  idempotencyConflict: () => new ApiError(409, 'IDEMPOTENCY_CONFLICT', 'Idempotency-Key already in use for a different request body'),
};

// ─── Error → HTTP response mapper ───
export function errorToResponse(err: unknown, requestId?: string): NextResponse {
  // Known ApiError
  if (err instanceof ApiError) {
    const body: Record<string, unknown> = {
      error: err.message,
      code: err.code,
    };
    if (err.details) body.details = err.details;
    if (requestId) body.requestId = requestId;

    // Don't log 4xx as errors (they're client mistakes, not server bugs)
    if (err.status >= 500) {
      baseLogger.error({ err, requestId }, 'API error');
    } else if (err.status >= 400) {
      baseLogger.warn({ err: { code: err.code, message: err.message }, requestId }, 'Client error');
    }

    return NextResponse.json(body, { status: err.status });
  }

  // Zod validation error
  if (err instanceof ZodError) {
    baseLogger.warn({ err: err.issues, requestId }, 'Validation error');
    return NextResponse.json({
      error: 'Validation failed',
      code: 'VALIDATION_ERROR',
      details: err.issues,
      requestId,
    }, { status: 400 });
  }

  // Unknown error — log full stack, return generic message
  baseLogger.error({ err, requestId }, 'Unhandled error');
  return NextResponse.json({
    error: 'Internal server error',
    code: 'INTERNAL',
    requestId,
  }, { status: 500 });
}

// ─── Async handler wrapper ───
// Catches all errors and converts to NextResponse. Eliminates try/catch in every route.
type Handler = (req: Request, ctx?: any) => Promise<NextResponse | Response>;

export function asyncHandler(handler: Handler): Handler {
  return async (req, ctx) => {
    try {
      return await handler(req, ctx);
    } catch (err) {
      const requestId = req.headers.get('x-request-id') || undefined;
      return errorToResponse(err, requestId);
    }
  };
}

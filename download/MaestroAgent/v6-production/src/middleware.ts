// Next.js middleware — centralized auth, request ID, rate limiting.
// Runs on every /api/* request except /api/health and /api/auth/*.

import { NextRequest, NextResponse } from 'next/server';
import { randomUUID } from 'crypto';
import { getServerSession } from 'next-auth';
import { authOptions } from '@/app/api/auth/[...nextauth]/route';
import { rateLimit } from '@/lib/rate-limit';
import { env } from '@/lib/env';
import { baseLogger, withRequestContext } from '@/lib/logger';

// Paths that don't require auth
const PUBLIC_PATHS = ['/api/health', '/api/auth'];

export async function middleware(req: NextRequest): Promise<NextResponse> {
  const { pathname } = req.nextUrl;

  // Skip auth for public paths
  if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) {
    return NextResponse.next();
  }

  // Generate request ID (or use incoming header for distributed tracing)
  const requestId = req.headers.get('x-request-id') || randomUUID();

  // ─── Auth ───
  // Note: getServerSession requires the full Next.js context, which middleware doesn't have.
  // In production, we verify the JWT directly from the cookie.
  // This is a simplified version — production uses jose library to verify JWT.
  const session = await getSessionFromCookie(req);

  if (!session) {
    return NextResponse.json(
      { error: 'Authentication required', code: 'UNAUTHORIZED', requestId },
      { status: 401 },
    );
  }

  // ─── Rate limiting ───
  // Per-user, per-endpoint-class
  const endpointClass = getEndpointClass(pathname);
  const rateLimitKey = `${session.orgId}:${session.userId}:${endpointClass}`;
  const limits = getRateLimits(endpointClass);
  const rl = await rateLimit(rateLimitKey, limits.max, limits.windowMs);

  if (!rl.allowed) {
    return NextResponse.json(
      { error: 'Too many requests', code: 'RATE_LIMITED', requestId, retryAfterMs: rl.retryAfterMs },
      {
        status: 429,
        headers: {
          'X-Request-Id': requestId,
          'Retry-After': String(Math.ceil(rl.retryAfterMs / 1000)),
          'X-RateLimit-Remaining': '0',
        },
      },
    );
  }

  // ─── Attach context to request headers ───
  const requestHeaders = new Headers(req.headers);
  requestHeaders.set('x-request-id', requestId);
  requestHeaders.set('x-user-id', session.userId);
  requestHeaders.set('x-org-id', session.orgId);
  requestHeaders.set('x-user-role', session.role);

  const response = NextResponse.next({
    request: { headers: requestHeaders },
  });

  // ─── Response headers ───
  response.headers.set('X-Request-Id', requestId);
  response.headers.set('X-RateLimit-Remaining', String(rl.remaining));

  // Log request
  withRequestContext(requestId, () => {
    baseLogger.info({
      req: {
        method: req.method,
        url: pathname,
        requestId,
      },
      userId: session.userId,
      orgId: session.orgId,
    }, 'request');
  });

  return response;
}

// ─── Helpers ───

interface SessionData {
  userId: string;
  orgId: string;
  role: string;
}

async function getSessionFromCookie(req: NextRequest): Promise<SessionData | null> {
  // In production: verify JWT from cookie using jose library
  // For scaffold: read from next-auth session cookie
  // This is a placeholder — real implementation depends on auth provider
  try {
    // Production would use: import { jwtVerify } from 'jose';
    // const token = req.cookies.get('next-auth.session-token')?.value;
    // const verified = await jwtVerify(token, secret);
    // return { userId: verified.payload.sub, orgId: verified.payload.orgId, role: verified.payload.role };
    return null; // Real implementation goes here
  } catch {
    return null;
  }
}

function getEndpointClass(pathname: string): string {
  if (pathname.startsWith('/api/decisions')) return 'decisions';
  if (pathname.startsWith('/api/meetings')) return 'meetings';
  if (pathname.startsWith('/api/predictions')) return 'predictions';
  if (pathname.startsWith('/api/laws')) return 'laws';
  if (pathname.startsWith('/api/debates')) return 'debates';
  return 'default';
}

function getRateLimits(endpointClass: string): { max: number; windowMs: number } {
  switch (endpointClass) {
    case 'decisions':
      return { max: 30, windowMs: 60_000 }; // 30 req/min
    case 'meetings':
      return { max: 100, windowMs: 60_000 }; // Higher — transcript chunks
    case 'predictions':
      return { max: 20, windowMs: 60_000 };
    default:
      return { max: env.RATE_LIMIT_MAX_REQUESTS, windowMs: env.RATE_LIMIT_WINDOW_MS };
  }
}

export const config = {
  matcher: ['/api/:path*'],
};

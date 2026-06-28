// Maestro v6 — Server-side utilities
// Auth, encryption, audit, OEM access, calibration

import { PrismaClient } from '@prisma/client';
import { getServerSession } from 'next-auth';
import { authOptions } from '@/app/api/auth/[...nextauth]/route';
import pino from 'pino';
import { createCipheriv, createDecipheriv, randomBytes } from 'crypto';

export const prisma = new PrismaClient();
export const log = pino({ name: 'maestro-v6' });

// ============================================================
// AUTH — every API route must call requireUser()
// ============================================================

export interface AuthContext {
  userId: string;
  orgId: string;
  role: 'MEMBER' | 'ADMIN' | 'CEO' | 'EXECUTIVE';
}

export async function requireUser(): Promise<AuthContext> {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    throw new ApiError(401, 'UNAUTHORIZED', 'Authentication required');
  }
  const ctx: AuthContext = {
    userId: session.user.id,
    orgId: session.user.orgId,
    role: session.user.role,
  };
  return ctx;
}

export function requireRole(ctx: AuthContext, ...roles: AuthContext['role'][]) {
  if (!roles.includes(ctx.role)) {
    throw new ApiError(403, 'FORBIDDEN', `Requires role: ${roles.join(' | ')}`);
  }
}

// ============================================================
// ERROR TYPES
// ============================================================

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
  }
}

// ============================================================
// ENCRYPTION — for OAuth tokens and PII at rest
// ============================================================

const ENCRYPTION_KEY = process.env.ENCRYPTION_KEY!; // 32-byte hex string
const ALGORITHM = 'aes-256-gcm';

export function encrypt(plaintext: string): { ciphertext: Buffer; iv: Buffer; tag: Buffer } {
  const iv = randomBytes(12);
  const cipher = createCipheriv(ALGORITHM, Buffer.from(ENCRYPTION_KEY, 'hex'), iv);
  const ciphertext = Buffer.concat([cipher.update(plaintext, 'utf8'), cipher.final()]);
  const tag = cipher.getAuthTag();
  return { ciphertext, iv, tag };
}

export function decrypt(encrypted: { ciphertext: Buffer; iv: Buffer; tag: Buffer }): string {
  const decipher = createDecipheriv(ALGORITHM, Buffer.from(ENCRYPTION_KEY, 'hex'), encrypted.iv);
  decipher.setAuthTag(encrypted.tag);
  return Buffer.concat([decipher.update(encrypted.ciphertext), decipher.final()]).toString('utf8');
}

// ============================================================
// AUDIT — every state-changing operation is logged
// ============================================================

export async function audit(
  ctx: AuthContext,
  action: string,
  entityType: string,
  entityId: string,
  before?: unknown,
  after?: unknown,
  request?: { ip?: string; userAgent?: string },
) {
  await prisma.auditEvent.create({
    data: {
      orgId: ctx.orgId,
      actorId: ctx.userId,
      action,
      entityType,
      entityId,
      before: before as any,
      after: after as any,
      ip: request?.ip,
      userAgent: request?.userAgent,
    },
  });
  log.info({ action, entityType, entityId, orgId: ctx.orgId, actorId: ctx.userId }, 'audit');
}

// ============================================================
// RATE LIMITING — simple in-memory, replace with Redis in prod
// ============================================================

const rateLimitMap = new Map<string, { count: number; resetAt: number }>();

export function rateLimit(key: string, max: number, windowMs: number): boolean {
  const now = Date.now();
  const entry = rateLimitMap.get(key);
  if (!entry || entry.resetAt < now) {
    rateLimitMap.set(key, { count: 1, resetAt: now + windowMs });
    return true;
  }
  if (entry.count >= max) return false;
  entry.count++;
  return true;
}

// ============================================================
// CALIBRATION — bucket computation for SHR
// ============================================================

export function confidenceBucket(confidence: number): number {
  return Math.min(9, Math.floor(confidence * 10));
}

export function computeShr(hits: number, misses: number): number {
  const total = hits + misses;
  return total === 0 ? 0 : hits / total;
}

export function isWithinShrBand(shr: number): boolean {
  // Target band: 0.80–0.88
  return shr >= 0.80 && shr <= 0.88;
}

// ============================================================
// DECISION QUESTION ENFORCEMENT
// Every screen must declare a decision question.
// This is v6's design rule — surfaces without a DQ are forbidden.
// ============================================================

export function validateDecisionQuestion(dq: string): void {
  if (!dq || dq.trim().length < 10) {
    throw new ApiError(400, 'INVALID_DECISION_QUESTION',
      'Every surface must declare a decision question (min 10 chars)');
  }
  if (!dq.endsWith('?')) {
    throw new ApiError(400, 'INVALID_DECISION_QUESTION',
      'Decision question must end with "?"');
  }
}

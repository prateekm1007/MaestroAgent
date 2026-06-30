// Maestro v6 — Server-side utilities (hardened)
// Auth, audit, SHR, calibration. Refactored to use new env, logger, errors, rate-limit modules.

import { prisma } from './db';
import { ApiError, Errors } from './errors';
import { log } from './logger';
import { env } from './env';
import { createCipheriv, createDecipheriv, randomBytes } from 'crypto';

// ============================================================
// AUTH CONTEXT — reads from headers set by middleware
// ============================================================

export interface AuthContext {
  userId: string;
  orgId: string;
  role: 'MEMBER' | 'ADMIN' | 'CEO' | 'EXECUTIVE';
  requestId: string;
}

export function getAuthContext(req: Request): AuthContext {
  const userId = req.headers.get('x-user-id');
  const orgId = req.headers.get('x-org-id');
  const role = req.headers.get('x-user-role') as AuthContext['role'];
  const requestId = req.headers.get('x-request-id') || 'unknown';

  if (!userId || !orgId || !role) {
    throw Errors.unauthorized('Missing auth context headers (middleware did not run?)');
  }

  return { userId, orgId, role, requestId };
}

export function requireRole(ctx: AuthContext, ...roles: AuthContext['role'][]): void {
  if (!roles.includes(ctx.role)) {
    throw Errors.forbidden(`Requires role: ${roles.join(' | ')}`);
  }
}

// ============================================================
// ENCRYPTION — AES-256-GCM with KMS-backed key (production)
// In dev: use ENCRYPTION_KEY env var directly
// In prod: key is fetched from KMS and cached
// ============================================================

const ALGORITHM = 'aes-256-gcm';

let _keyCache: Buffer | null = null;

async function getEncryptionKey(): Promise<Buffer> {
  if (_keyCache) return _keyCache;

  if (env.KMS_KEY_ID && env.AWS_REGION) {
    // Production: fetch from KMS
    // const { KMSClient, DecryptCommand } = await import('@aws-sdk/client-kms');
    // const kms = new KMSClient({ region: env.AWS_REGION });
    // ... fetch and decrypt data key
    // For scaffold: fall through to env
    throw new Error('KMS not implemented in scaffold — use ENCRYPTION_KEY env var');
  }

  // Dev/staging: use env var directly
  _keyCache = Buffer.from(env.ENCRYPTION_KEY, 'hex');
  return _keyCache;
}

export async function encrypt(plaintext: string): Promise<{ ciphertext: Buffer; iv: Buffer; tag: Buffer }> {
  const key = await getEncryptionKey();
  const iv = randomBytes(12);
  const cipher = createCipheriv(ALGORITHM, key, iv);
  const ciphertext = Buffer.concat([cipher.update(plaintext, 'utf8'), cipher.final()]);
  const tag = cipher.getAuthTag();
  return { ciphertext, iv, tag };
}

export async function decrypt(encrypted: { ciphertext: Buffer; iv: Buffer; tag: Buffer }): Promise<string> {
  const key = await getEncryptionKey();
  const decipher = createDecipheriv(ALGORITHM, key, encrypted.iv);
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
): Promise<void> {
  try {
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
    log().info({ action, entityType, entityId, orgId: ctx.orgId, actorId: ctx.userId }, 'audit');
  } catch (err) {
    // Audit failure must not break the request — but must be logged
    log().error({ err, action, entityType, entityId }, 'AUDIT LOG FAILED — this is a security incident');
    // In production: alert PagerDuty
  }
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
  return shr >= 0.80 && shr <= 0.88;
}

// ============================================================
// DECISION QUESTION ENFORCEMENT
// ============================================================

export function validateDecisionQuestion(dq: string): void {
  if (!dq || dq.trim().length < 10) {
    throw Errors.badRequest('Every surface must declare a decision question (min 10 chars)');
  }
  if (!dq.trim().endsWith('?')) {
    throw Errors.badRequest('Decision question must end with "?"');
  }
}

// ============================================================
// GRACEFUL SHUTDOWN
// ============================================================

export async function gracefulShutdown(signal: string): Promise<void> {
  log().info({ signal }, 'Graceful shutdown initiated');
  // Stop accepting new requests (Next.js handles this)
  // Wait for in-flight requests (up to 30s)
  // Disconnect DB and Redis
  const { disconnectPrisma } = await import('./db');
  const { disconnectRedis } = await import('./redis');
  await Promise.all([disconnectPrisma(), disconnectRedis()]);
  log().info('Graceful shutdown complete');
  process.exit(0);
}

process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));
process.on('SIGINT', () => gracefulShutdown('SIGINT'));

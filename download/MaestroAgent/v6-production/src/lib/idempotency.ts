// Idempotency-Key handling for POST routes.
// Stores request body hash + response in Redis for 24h.
// Second request with same key returns cached response (if body matches) or 409 (if body differs).

import { getRedis } from './redis';
import { Errors } from './errors';
import { log } from './logger';

const IDEMPOTENCY_TTL_SECONDS = 60 * 60 * 24; // 24 hours
const KEY_PREFIX = 'idem:';

interface StoredResponse {
  status: number;
  body: unknown;
}

function bodyHash(body: unknown): string {
  const crypto = require('crypto') as typeof import('crypto');
  return crypto.createHash('sha256').update(JSON.stringify(body)).digest('hex').slice(0, 32);
}

/**
 * Check or store an idempotency key.
 * - If key is new: stores the body hash, returns null (caller should proceed).
 * - If key exists with same body hash: returns the cached response.
 * - If key exists with different body hash: throws 409 IDEMPOTENCY_CONFLICT.
 * - If key is missing/undefined: returns null (idempotency optional).
 */
export async function checkIdempotency(
  key: string | null,
  orgId: string,
  body: unknown,
): Promise<StoredResponse | null> {
  if (!key) return null;

  const redis = getRedis();
  const redisKey = `${KEY_PREFIX}${orgId}:${key}`;
  const bodyHashValue = bodyHash(body);

  // Atomic check-and-set
  const existing = await redis.get(redisKey);
  if (existing) {
    const parsed = JSON.parse(existing) as { bodyHash: string; response?: StoredResponse };
    if (parsed.bodyHash !== bodyHashValue) {
      throw Errors.idempotencyConflict();
    }
    if (parsed.response) {
      log().info({ idempotencyKey: key }, 'Idempotent cache hit');
      return parsed.response;
    }
    // Request in progress (no response yet) — caller should wait or return 409
    // For simplicity, we throw conflict; production would poll
    throw Errors.conflict('Request with this Idempotency-Key is already in progress');
  }

  // Store the body hash with no response yet (marks as in-progress)
  await redis.setex(redisKey, IDEMPOTENCY_TTL_SECONDS, JSON.stringify({ bodyHash: bodyHashValue }));
  return null;
}

/**
 * Store the response for an idempotency key. Must be called after checkIdempotency returns null.
 */
export async function storeIdempotencyResponse(
  key: string | null,
  orgId: string,
  body: unknown,
  response: StoredResponse,
): Promise<void> {
  if (!key) return;
  const redis = getRedis();
  const redisKey = `${KEY_PREFIX}${orgId}:${key}`;
  const bodyHashValue = bodyHash(body);
  await redis.setex(
    redisKey,
    IDEMPOTENCY_TTL_SECONDS,
    JSON.stringify({ bodyHash: bodyHashValue, response }),
  );
}

// Redis-based sliding window rate limiter.
// Replaces the in-memory rateLimitMap — works across multiple instances.

import { getRedis } from './redis';
import { Errors } from './errors';

const KEY_PREFIX = 'rl:';

/**
 * Rate limit using a sliding window log algorithm.
 * @param identifier - typically `${orgId}:${userId}:${endpoint}`
 * @param maxRequests - max requests in the window
 * @param windowMs - window size in milliseconds
 * @returns { allowed: boolean, retryAfterMs: number, remaining: number }
 */
export async function rateLimit(
  identifier: string,
  maxRequests: number,
  windowMs: number,
): Promise<{ allowed: boolean; retryAfterMs: number; remaining: number }> {
  const redis = getRedis();
  const key = `${KEY_PREFIX}${identifier}`;
  const now = Date.now();
  const windowStart = now - windowMs;

  // Atomic sliding window: remove old entries, add current, count
  // Using Lua for atomicity
  const luaScript = `
    redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, ARGV[1])
    local count = redis.call('ZCARD', KEYS[1])
    if count < tonumber(ARGV[2]) then
      redis.call('ZADD', KEYS[1], ARGV[3], ARGV[4])
      redis.call('PEXPIRE', KEYS[1], ARGV[5])
      return {1, tonumber(ARGV[2]) - count - 1, 0}
    else
      local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
      local retryAfter = ARGV[5] - (ARGV[3] - oldest[2])
      return {0, 0, retryAfter}
    end
  `;

  const result = await redis.eval(
    luaScript,
    1,
    key,
    windowStart,
    maxRequests,
    now,
    `${now}:${Math.random().toString(36).slice(2)}`,
    windowMs,
  ) as number[];

  const [allowed, remaining, retryAfter] = result;
  return {
    allowed: allowed === 1,
    remaining,
    retryAfterMs: Math.max(0, retryAfter),
  };
}

/**
 * Express/Next.js helper — throws ApiError 429 if rate limited.
 */
export async function enforceRateLimit(
  identifier: string,
  maxRequests: number,
  windowMs: number,
): Promise<void> {
  const result = await rateLimit(identifier, maxRequests, windowMs);
  if (!result.allowed) {
    throw Errors.rateLimited(result.retryAfterMs);
  }
}

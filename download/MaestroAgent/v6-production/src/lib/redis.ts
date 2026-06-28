// Redis client — single connection reused across the app.
// Used for: rate limiting, idempotency keys, WebSocket pub/sub, BullMQ queues.

import Redis, { type RedisOptions } from 'ioredis';
import { env } from './env';
import { baseLogger } from './logger';

const options: RedisOptions = {
  // Retry strategy: exponential backoff, max 3s
  retryStrategy: (times) => Math.min(times * 100, 3000),
  maxRetriesPerRequest: 3,
  enableOfflineQueue: true,
  lazyConnect: false,
  // Keep alive — critical for long-running processes
  keepAlive: 30000,
  // Connection timeout — fail fast if Redis is down
  connectTimeout: 5000,
  // Disconnect on error, let retry strategy handle reconnect
  reconnectOnError: (err) => {
    const targetErrors = ['READONLY', 'NOAUTH', 'WRONGPASS'];
    return targetErrors.some((e) => err.message.includes(e));
  },
};

let _client: Redis | null = null;
let _subscriber: Redis | null = null;

export function getRedis(): Redis {
  if (!_client) {
    _client = new Redis(env.REDIS_URL, options);
    _client.on('error', (err) => {
      baseLogger.error({ err }, 'Redis client error');
    });
    _client.on('connect', () => {
      baseLogger.info('Redis connected');
    });
    _client.on('reconnecting', (delay) => {
      baseLogger.warn({ delay }, 'Redis reconnecting');
    });
  }
  return _client;
}

export function getSubscriber(): Redis {
  if (!_subscriber) {
    _subscriber = new Redis(env.REDIS_URL, options);
    _subscriber.on('error', (err) => {
      baseLogger.error({ err }, 'Redis subscriber error');
    });
  }
  return _subscriber;
}

export async function disconnectRedis(): Promise<void> {
  const promises: Promise<void>[] = [];
  if (_client) {
    promises.push(_client.quit().then(() => { _client = null; }));
  }
  if (_subscriber) {
    promises.push(_subscriber.quit().then(() => { _subscriber = null; }));
  }
  await Promise.all(promises);
}

// ─── Pub/Sub helpers ───
export async function publish(channel: string, message: unknown): Promise<void> {
  const redis = getRedis();
  await redis.publish(channel, JSON.stringify(message));
}

export async function subscribe(channel: string, handler: (message: unknown) => void): Promise<void> {
  const subscriber = getSubscriber();
  await subscriber.subscribe(channel);
  subscriber.on('message', (chan, msg) => {
    if (chan === channel) {
      try {
        handler(JSON.parse(msg));
      } catch (err) {
        baseLogger.error({ err, channel: chan }, 'Failed to parse pub/sub message');
      }
    }
  });
}

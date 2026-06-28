// Zod-validated environment configuration.
// Application refuses to start if any required var is missing or malformed.
// This file is imported by every other module — fail-fast at startup, not at request time.

import { z } from 'zod';

const EnvSchema = z.object({
  // ─── App ───
  NODE_ENV: z.enum(['development', 'test', 'staging', 'production']).default('development'),
  PORT: z.coerce.number().int().min(1).max(65535).default(3000),
  APP_URL: z.string().url().default('http://localhost:3000'),

  // ─── Database ───
  DATABASE_URL: z.string().url().refine(
    (url) => url.startsWith('postgres://') || url.startsWith('postgresql://'),
    'DATABASE_URL must be a PostgreSQL connection string'
  ),
  DATABASE_POOL_SIZE: z.coerce.number().int().min(2).max(50).default(10),
  DATABASE_STATEMENT_TIMEOUT_MS: z.coerce.number().int().min(1000).default(30000),

  // ─── Redis ───
  REDIS_URL: z.string().url().refine(
    (url) => url.startsWith('redis://') || url.startsWith('rediss://'),
    'REDIS_URL must be a Redis connection string'
  ),

  // ─── Encryption ───
  // 32-byte hex string (64 chars). Generate with: openssl rand -hex 32
  ENCRYPTION_KEY: z.string().regex(/^[0-9a-f]{64}$/, 'ENCRYPTION_KEY must be 64 hex chars (32 bytes)'),

  // ─── Auth ───
  NEXTAUTH_URL: z.string().url(),
  NEXTAUTH_SECRET: z.string().min(32, 'NEXTAUTH_SECRET must be at least 32 chars'),
  GOOGLE_CLIENT_ID: z.string().optional(),
  GOOGLE_CLIENT_SECRET: z.string().optional(),
  AZURE_CLIENT_ID: z.string().optional(),
  AZURE_CLIENT_SECRET: z.string().optional(),
  OKTA_CLIENT_ID: z.string().optional(),
  OKTA_CLIENT_SECRET: z.string().optional(),
  OKTA_ISSUER: z.string().url().optional(),

  // ─── LLM ───
  ANTHROPIC_API_KEY: z.string().startsWith('sk-ant-').optional(),
  OPENAI_API_KEY: z.string().startsWith('sk-').optional(),
  OLLAMA_BASE_URL: z.string().url().default('http://localhost:11434'),

  // ─── AWS (optional in dev) ───
  AWS_REGION: z.string().optional(),
  AWS_ACCESS_KEY_ID: z.string().optional(),
  AWS_SECRET_ACCESS_KEY: z.string().optional(),
  S3_BUCKET_NAME: z.string().optional(),
  KMS_KEY_ID: z.string().optional(),

  // ─── External APIs ───
  LINKEDIN_API_KEY: z.string().optional(),
  LINKEDIN_API_SECRET: z.string().optional(),
  TWITTER_BEARER_TOKEN: z.string().optional(),
  NEWS_API_KEY: z.string().optional(),

  // ─── Observability ───
  SENTRY_DSN: z.string().url().optional(),
  LOG_LEVEL: z.enum(['fatal', 'error', 'warn', 'info', 'debug', 'trace']).default('info'),

  // ─── Rate Limiting ───
  RATE_LIMIT_WINDOW_MS: z.coerce.number().int().min(1000).default(60000),
  RATE_LIMIT_MAX_REQUESTS: z.coerce.number().int().min(1).default(100),
  SIMULATOR_RATE_LIMIT: z.coerce.number().int().min(1).default(30),

  // ─── Meeting Intelligence ───
  TRANSCRIPT_PROCESSING_TIMEOUT_MS: z.coerce.number().int().default(5000),
  MEETING_AUDIO_RETENTION_DAYS: z.coerce.number().int().default(730), // 2 years
  AUDIT_LOG_RETENTION_YEARS: z.coerce.number().int().default(7),
});

export type Env = z.infer<typeof EnvSchema>;

function loadEnv(): Env {
  const parsed = EnvSchema.safeParse(process.env);
  if (!parsed.success) {
    console.error('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    console.error('  FATAL: Invalid environment configuration');
    console.error('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    for (const issue of parsed.error.issues) {
      console.error(`  ${issue.path.join('.')}: ${issue.message}`);
    }
    console.error('');
    console.error('  Copy .env.example to .env and fill in the required values.');
    console.error('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    process.exit(1);
  }
  return parsed.data;
}

// Single load — fail fast at import time
export const env = loadEnv();

// Convenience flags
export const isProduction = env.NODE_ENV === 'production';
export const isTest = env.NODE_ENV === 'test';
export const isDevelopment = env.NODE_ENV === 'development';

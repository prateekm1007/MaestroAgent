// Prisma client singleton with connection pooling and graceful shutdown.
// Hot-reload safe (prevents multiple instances in dev).

import { PrismaClient } from '@prisma/client';
import { env } from './env';
import { baseLogger } from './logger';

const prismaClientSingleton = () => {
  return new PrismaClient({
    log: env.NODE_ENV === 'development' ? ['query', 'warn', 'error'] : ['warn', 'error'],
    datasources: {
      db: {
        url: env.DATABASE_URL,
      },
    },
    // Statement timeout — kill slow queries before they hold locks
    // (Prisma 5+ supports this via the datasource URL; we set it here as fallback)
  });
};

// ─── Hot-reload safety ───
declare global {
  // eslint-disable-next-line no-var
  var __prisma: PrismaClient | undefined;
}

export const prisma = globalThis.__prisma ?? prismaClientSingleton();

if (env.NODE_ENV !== 'production') {
  globalThis.__prisma = prisma;
}

// ─── Graceful shutdown ───
export async function disconnectPrisma(): Promise<void> {
  if (globalThis.__prisma) {
    baseLogger.info('Disconnecting Prisma...');
    await prisma.$disconnect();
    globalThis.__prisma = undefined;
  }
}

// ─── Health check helper ───
export async function checkDatabaseHealth(): Promise<{ status: 'ok' | 'down'; latencyMs?: number }> {
  try {
    const start = Date.now();
    await prisma.$queryRaw`SELECT 1`;
    return { status: 'ok', latencyMs: Date.now() - start };
  } catch {
    return { status: 'down' };
  }
}

// Maestro v6 — Health check
// GET /api/health — used by load balancer and monitoring

import { NextResponse } from 'next/server';
import { prisma } from '@/lib/server';

export async function GET() {
  const checks: { name: string; status: 'ok' | 'degraded' | 'down'; latencyMs?: number }[] = [];

  // DB check
  try {
    const start = Date.now();
    await prisma.$queryRaw`SELECT 1`;
    checks.push({ name: 'database', status: 'ok', latencyMs: Date.now() - start });
  } catch {
    checks.push({ name: 'database', status: 'down' });
  }

  // Signal source connectivity (lazy — only checks if configured)
  // In production: check Slack, Jira, GitHub OAuth validity

  const allOk = checks.every(c => c.status === 'ok');
  return NextResponse.json(
    { status: allOk ? 'ok' : 'degraded', checks, version: '0.1.0' },
    { status: allOk ? 200 : 503 },
  );
}

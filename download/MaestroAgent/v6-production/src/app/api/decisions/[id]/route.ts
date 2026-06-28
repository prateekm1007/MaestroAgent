// Maestro v6 — Decision Workbench API
// POST /api/decisions/[id]/simulate
// PATCH /api/decisions/[id] (approve/reject/defer)

import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';
import { requireUser, requireRole, audit, ApiError, prisma, log } from '@/lib/server';
import { simulate } from '@/lib/simulator';
import type { SimulatorConfig } from '@/types/domain';

const SimulateRequestSchema = z.object({
  config: z.object({
    emea: z.number().int().min(0).max(50),
    apac: z.number().int().min(0).max(50),
    na: z.number().int().min(0).max(50),
    parameters: z.record(z.string(), z.number()).optional().default({}),
  }),
  horizonDays: z.number().int().min(7).max(365).default(90),
});

export async function POST(
  req: NextRequest,
  { params }: { params: { id: string } },
) {
  try {
    const ctx = await requireUser();
    requireRole(ctx, 'CEO', 'EXECUTIVE', 'ADMIN');

    const body = await req.json();
    const parsed = SimulateRequestSchema.safeParse(body);
    if (!parsed.success) {
      throw new ApiError(400, 'INVALID_REQUEST', 'Invalid simulator config', parsed.error.issues);
    }

    const decision = await prisma.decision.findFirst({
      where: { id: params.id, orgId: ctx.orgId },
      select: { id: true, title: true, decisionQuestion: true },
    });
    if (!decision) throw new ApiError(404, 'NOT_FOUND', 'Decision not found');

    const result = simulate({
      orgId: ctx.orgId,
      decisionType: 'HIRING',
      config: parsed.data.config as SimulatorConfig,
      horizonDays: parsed.data.horizonDays,
    });

    await prisma.decision.update({
      where: { id: decision.id },
      data: {
        simulatorConfig: parsed.data.config as any,
        simulatorOutputs: result.outputs as any,
      },
    });

    await audit(ctx, 'decision.simulate', 'decision', decision.id, undefined, {
      config: parsed.data.config, confidence: result.outputs.confidence,
    });

    return NextResponse.json(result);
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json({ error: err.message, code: err.code }, { status: err.status });
    }
    log.error({ err }, 'simulate failed');
    return NextResponse.json({ error: 'Internal error', code: 'INTERNAL' }, { status: 500 });
  }
}

const ApproveRequestSchema = z.object({
  action: z.enum(['APPROVE', 'REJECT', 'DEFER']),
  notes: z.string().optional(),
});

export async function PATCH(
  req: NextRequest,
  { params }: { params: { id: string } },
) {
  try {
    const ctx = await requireUser();
    requireRole(ctx, 'CEO', 'EXECUTIVE');

    const body = await req.json();
    const parsed = ApproveRequestSchema.safeParse(body);
    if (!parsed.success) throw new ApiError(400, 'INVALID_REQUEST', 'Invalid action');

    const decision = await prisma.decision.findFirst({
      where: { id: params.id, orgId: ctx.orgId },
    });
    if (!decision) throw new ApiError(404, 'NOT_FOUND', 'Decision not found');

    const now = new Date();
    const verifyDate = new Date(now.getTime() + 90 * 24 * 60 * 60 * 1000);

    const updated = await prisma.decision.update({
      where: { id: decision.id },
      data: {
        status: parsed.data.action === 'APPROVE' ? 'APPROVED'
          : parsed.data.action === 'REJECT' ? 'REJECTED' : 'DEFERRED',
        approvedAt: parsed.data.action === 'APPROVE' ? now : null,
        approvedBy: parsed.data.action === 'APPROVE' ? ctx.userId : null,
        verifyDate: parsed.data.action === 'APPROVE' ? verifyDate : null,
      },
    });

    if (parsed.data.action === 'APPROVE') {
      await prisma.prediction.create({
        data: {
          orgId: ctx.orgId,
          statement: `Decision "${decision.title}" outcome will match predicted state`,
          confidence: decision.confidence,
          madeAt: now,
          verifyDate,
          bucket: Math.min(9, Math.floor(decision.confidence * 10)),
          decisionId: decision.id,
        },
      });
    }

    await audit(ctx, `decision.${parsed.data.action.toLowerCase()}`, 'decision', decision.id,
      decision, updated, {
        ip: req.headers.get('x-forwarded-for') || undefined,
        userAgent: req.headers.get('user-agent') || undefined,
      });

    return NextResponse.json(updated);
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json({ error: err.message, code: err.code }, { status: err.status });
    }
    log.error({ err }, 'decision action failed');
    return NextResponse.json({ error: 'Internal error', code: 'INTERNAL' }, { status: 500 });
  }
}

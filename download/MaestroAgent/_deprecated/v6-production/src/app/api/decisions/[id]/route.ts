// Maestro v6 — Decision Workbench API (hardened)
// POST /api/decisions/[id]/simulate — Run OEM counterfactual (idempotent)
// PATCH /api/decisions/[id] — Approve / reject / defer (atomic, audited)

import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';
import {
  getAuthContext, requireRole, audit, validateDecisionQuestion,
} from '@/lib/server';
import { Errors, errorToResponse, asyncHandler } from '@/lib/errors';
import { prisma } from '@/lib/db';
import { simulate } from '@/lib/simulator';
import { enforceRateLimit } from '@/lib/rate-limit';
import { checkIdempotency, storeIdempotencyResponse } from '@/lib/idempotency';
import { sanitizeText } from '@/lib/sanitize';
import { log } from '@/lib/logger';
import type { SimulatorConfig } from '@/types/domain';

// ============================================================
// POST /api/decisions/[id]/simulate
// ============================================================

const SimulateRequestSchema = z.object({
  config: z.object({
    emea: z.number().int().min(0).max(50),
    apac: z.number().int().min(0).max(50),
    na: z.number().int().min(0).max(50),
    parameters: z.record(z.string(), z.number()).optional().default({}),
  }),
  horizonDays: z.number().int().min(7).max(365).default(90),
});

export const POST = asyncHandler(async (req: NextRequest, { params }: { params: { id: string } }) => {
  const ctx = getAuthContext(req);
  requireRole(ctx, 'CEO', 'EXECUTIVE', 'ADMIN');

  // Rate limit: simulator is expensive
  await enforceRateLimit(`${ctx.orgId}:${ctx.userId}:simulate`, 30, 60_000);

  const body = await req.json();
  const parsed = SimulateRequestSchema.safeParse(body);
  if (!parsed.success) {
    throw Errors.badRequest('Invalid simulator config', parsed.error.issues);
  }

  // Idempotency check
  const idempotencyKey = req.headers.get('idempotency-key');
  const cached = await checkIdempotency(idempotencyKey, ctx.orgId, body);
  if (cached) {
    return NextResponse.json(cached.body, { status: cached.status });
  }

  // Verify decision belongs to org (scoped query — IDOR protection)
  const decision = await prisma.decision.findFirst({
    where: { id: params.id, orgId: ctx.orgId },
    select: { id: true, title: true, decisionQuestion: true },
  });
  if (!decision) throw Errors.notFound('Decision', params.id);

  // Validate DQ still passes (defensive — should have been validated at creation)
  try {
    validateDecisionQuestion(decision.decisionQuestion);
  } catch {
    throw Errors.badRequest('Decision has invalid decision question — cannot simulate');
  }

  const result = simulate({
    orgId: ctx.orgId,
    decisionType: 'HIRING',
    config: parsed.data.config as SimulatorConfig,
    horizonDays: parsed.data.horizonDays,
  });

  // Persist simulator state (atomic update)
  await prisma.decision.update({
    where: { id: decision.id },
    data: {
      simulatorConfig: parsed.data.config as any,
      simulatorOutputs: result.outputs as any,
    },
  });

  await audit(ctx, 'decision.simulate', 'decision', decision.id, undefined, {
    config: parsed.data.config,
    confidence: result.outputs.confidence,
  });

  const response = { status: 200, body: result };
  await storeIdempotencyResponse(idempotencyKey, ctx.orgId, body, response);

  return NextResponse.json(result);
});

// ============================================================
// PATCH /api/decisions/[id] — approve / reject / defer
// ATOMIC: Decision update + Prediction create + AuditEvent create in one transaction
// ============================================================

const ApproveRequestSchema = z.object({
  action: z.enum(['APPROVE', 'REJECT', 'DEFER']),
  notes: z.string().max(2000).optional(),
});

export const PATCH = asyncHandler(async (req: NextRequest, { params }: { params: { id: string } }) => {
  const ctx = getAuthContext(req);
  requireRole(ctx, 'CEO', 'EXECUTIVE');

  const body = await req.json();
  const parsed = ApproveRequestSchema.safeParse(body);
  if (!parsed.success) throw Errors.badRequest('Invalid action');

  // Idempotency
  const idempotencyKey = req.headers.get('idempotency-key');
  const cached = await checkIdempotency(idempotencyKey, ctx.orgId, body);
  if (cached) return NextResponse.json(cached.body, { status: cached.status });

  // Fetch decision (scoped)
  const decision = await prisma.decision.findFirst({
    where: { id: params.id, orgId: ctx.orgId },
  });
  if (!decision) throw Errors.notFound('Decision', params.id);

  // State machine validation
  if (decision.status !== 'PROPOSED' && decision.status !== 'IN_DEBATE') {
    throw Errors.conflict(`Decision is in status ${decision.status} — cannot ${parsed.data.action.toLowerCase()}`);
  }

  const now = new Date();
  const verifyDate = new Date(now.getTime() + 90 * 24 * 60 * 60 * 1000);
  const sanitizedNotes = parsed.data.notes ? sanitizeText(parsed.data.notes, { maxLength: 2000 }) : null;

  // ATOMIC: Decision update + Prediction create + AuditEvent create
  const [updated, newPrediction] = await prisma.$transaction(async (tx) => {
    const updated = await tx.decision.update({
      where: { id: decision.id },
      data: {
        status: parsed.data.action === 'APPROVE' ? 'APPROVED'
          : parsed.data.action === 'REJECT' ? 'REJECTED' : 'DEFERRED',
        approvedAt: parsed.data.action === 'APPROVE' ? now : null,
        approvedBy: parsed.data.action === 'APPROVE' ? ctx.userId : null,
        verifyDate: parsed.data.action === 'APPROVE' ? verifyDate : null,
      },
    });

    // If approved, log prediction to Ledger (same transaction — no orphans)
    let newPrediction = null;
    if (parsed.data.action === 'APPROVE') {
      newPrediction = await tx.prediction.create({
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

    // Audit (same transaction — if audit fails, decision doesn't commit)
    await tx.auditEvent.create({
      data: {
        orgId: ctx.orgId,
        actorId: ctx.userId,
        action: `decision.${parsed.data.action.toLowerCase()}`,
        entityType: 'decision',
        entityId: decision.id,
        before: decision as any,
        after: updated as any,
        ip: req.headers.get('x-forwarded-for') || undefined,
        userAgent: req.headers.get('user-agent') || undefined,
      },
    });

    return [updated, newPrediction] as const;
  });

  log().info({
    decisionId: decision.id,
    action: parsed.data.action,
    predictionId: newPrediction?.id,
  }, 'Decision action completed');

  const response = { status: 200, body: { decision: updated, prediction: newPrediction } };
  await storeIdempotencyResponse(idempotencyKey, ctx.orgId, body, response);

  return NextResponse.json(response.body);
});

// Maestro v6 — Live Meeting API (hardened)
// POST /api/meetings/[id] — Submit transcript chunk (consent-gated, idempotent, sanitized)
// GET  /api/meetings/[id] — Get meeting state

import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';
import { getAuthContext, audit } from '@/lib/server';
import { Errors, asyncHandler } from '@/lib/errors';
import { prisma } from '@/lib/db';
import { enforceRateLimit } from '@/lib/rate-limit';
import { checkIdempotency, storeIdempotencyResponse } from '@/lib/idempotency';
import { sanitizeTranscript } from '@/lib/sanitize';
import { processTranscriptChunk, verifyConsent, logConsent, type TranscriptChunk } from '@/lib/meeting-engine';
import { publish } from '@/lib/redis';
import { log } from '@/lib/logger';

// ============================================================
// POST /api/meetings/[id] — transcript chunk
// ============================================================

const TranscriptChunkSchema = z.object({
  ts: z.string().regex(/^\d{2}:\d{2}(:\d{2})?$/, 'ts must be HH:MM or HH:MM:SS'),
  speakerId: z.string().min(1).max(100),
  speakerName: z.string().min(1).max(200),
  text: z.string().min(1).max(5000),
});

const TranscriptRequestBodySchema = z.object({
  meetingId: z.string().cuid(),
  chunk: TranscriptChunkSchema,
});

export const POST = asyncHandler(async (req: NextRequest, { params }: { params: { id: string } }) => {
  const ctx = getAuthContext(req);

  // Rate limit: 100 chunks/min/user
  await enforceRateLimit(`${ctx.orgId}:${ctx.userId}:meetings`, 100, 60_000);

  const body = await req.json();
  const parsed = TranscriptRequestBodySchema.safeParse(body);
  if (!parsed.success) {
    throw Errors.badRequest('Invalid transcript chunk', parsed.error.issues);
  }

  // Idempotency
  const idempotencyKey = req.headers.get('idempotency-key');
  const cached = await checkIdempotency(idempotencyKey, ctx.orgId, body);
  if (cached) return NextResponse.json(cached.body, { status: cached.status });

  // Sanitize the chunk text BEFORE any processing
  const sanitizedChunk: TranscriptChunk = {
    ts: parsed.data.chunk.ts,
    speakerId: parsed.data.chunk.speakerId,
    speakerName: sanitizeTranscript(parsed.data.chunk.speakerName),
    text: sanitizeTranscript(parsed.data.chunk.text),
  };

  // Verify meeting exists and belongs to org
  const meeting = await prisma.meeting.findFirst({
    where: { id: params.id, orgId: ctx.orgId },
  });
  if (!meeting) throw Errors.notFound('Meeting', params.id);

  // Verify participant is in the meeting (authorization)
  const participants = meeting.participants as any[];
  const isParticipant = participants.some((p) => p.entityId === ctx.userId);
  if (!isParticipant) {
    throw Errors.forbidden('You are not a participant in this meeting');
  }

  // CONSENT GATE — hard server-side check, cannot be bypassed by client
  if (!verifyConsent(participants)) {
    throw Errors.consentRequired();
  }

  // Fetch org laws for trigger matching
  const laws = await prisma.orgLaw.findMany({
    where: {
      orgId: ctx.orgId,
      status: { in: ['VALIDATED', 'STRESSED', 'UNKNOWN_TO_LEADERSHIP'] },
    },
  });

  // Process the chunk
  const result = processTranscriptChunk(sanitizedChunk, laws as any);

  // ATOMIC: persist transcript line + action items + audit
  await prisma.$transaction(async (tx) => {
    // Append transcript line
    const currentTranscript = (meeting.transcript as any[]) || [];
    await tx.meeting.update({
      where: { id: meeting.id },
      data: {
        transcript: [...currentTranscript, {
          ts: sanitizedChunk.ts,
          speakerId: sanitizedChunk.speakerId,
          speakerName: sanitizedChunk.speakerName,
          text: sanitizedChunk.text,
          highlights: result.highlights,
        }],
      },
    });

    // Create action items
    for (const ai of result.actionItems) {
      await tx.actionItem.create({
        data: {
          orgId: ctx.orgId,
          meetingId: meeting.id,
          text: sanitizeTranscript(ai.text),
          source: ai.source,
        },
      });
    }

    // Audit
    await tx.auditEvent.create({
      data: {
        orgId: ctx.orgId,
        actorId: ctx.userId,
        action: 'meeting.transcript_chunk',
        entityType: 'meeting',
        entityId: meeting.id,
        after: { ts: sanitizedChunk.ts, objections: result.objections.length, actionItems: result.actionItems.length },
      },
    });
  });

  // Broadcast to other participants via Redis pub/sub
  await publish(`meeting:${meeting.id}`, {
    type: 'transcript_chunk',
    chunk: sanitizedChunk,
    processing: result,
  });

  log().info({
    meetingId: meeting.id,
    objections: result.objections.length,
    actionItems: result.actionItems.length,
    invokedLaws: result.invokedLaws.length,
  }, 'Transcript chunk processed');

  const response = { status: 200, body: result };
  await storeIdempotencyResponse(idempotencyKey, ctx.orgId, body, response);

  return NextResponse.json(result);
});

// ============================================================
// POST /api/meetings/[id]/consent — participant consents
// ============================================================

const ConsentSchema = z.object({
  participantId: z.string().cuid(),
});

export async function POST_CONSENT(req: NextRequest, { params }: { params: { id: string } }) {
  return asyncHandler(async () => {
    const ctx = getAuthContext(req);
    const body = await req.json();
    const parsed = ConsentSchema.safeParse(body);
    if (!parsed.success) throw Errors.badRequest('Invalid consent body');

    const meeting = await prisma.meeting.findFirst({
      where: { id: params.id, orgId: ctx.orgId },
    });
    if (!meeting) throw Errors.notFound('Meeting', params.id);

    // Update participant consent
    const participants = (meeting.participants as any[]).map((p) => {
      if (p.entityId === parsed.data.participantId) {
        return { ...p, consentedAt: new Date().toISOString(), consentMethod: 'EXPLICIT' };
      }
      return p;
    });

    const consentState = logConsent(meeting.id, participants as any);

    await prisma.meeting.update({
      where: { id: meeting.id },
      data: {
        participants: participants as any,
        consentLoggedAt: consentState.consentLoggedAt,
      },
    });

    await audit(ctx, 'meeting.consent_logged', 'meeting', meeting.id, undefined, {
      participantId: parsed.data.participantId,
      allConsented: consentState.allConsented,
    });

    // Broadcast consent update
    await publish(`meeting:${meeting.id}`, {
      type: 'consent_update',
      consentState,
    });

    return NextResponse.json(consentState);
  })(req);
}

// ============================================================
// GET /api/meetings/[id] — get meeting state
// ============================================================

export const GET = asyncHandler(async (req: NextRequest, { params }: { params: { id: string } }) => {
  const ctx = getAuthContext(req);

  const meeting = await prisma.meeting.findFirst({
    where: { id: params.id, orgId: ctx.orgId },
    include: {
      actionItems: true,
      predictions: true,
    },
  });
  if (!meeting) throw Errors.notFound('Meeting', params.id);

  // Verify participant
  const participants = meeting.participants as any[];
  const isParticipant = participants.some((p) => p.entityId === ctx.userId);
  if (!isParticipant) {
    throw Errors.forbidden('You are not a participant in this meeting');
  }

  return NextResponse.json(meeting);
});

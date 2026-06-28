// Maestro v6 — Live Meeting WebSocket
// Handles real-time transcript streaming, objection detection, action item extraction.
// Critical: consent must be verified before any recording begins.

import { NextRequest } from 'next/server';
import { WebSocket, WebSocketServer } from 'ws';
import { requireUser, audit, ApiError, prisma, log } from '@/lib/server';
import { processTranscriptChunk, verifyConsent, logConsent, type TranscriptChunk } from '@/lib/meeting-engine';

// In-memory state for active meetings (production: Redis)
const activeMeetings = new Map<string, { ws: Set<WebSocket>; consentVerified: boolean }>();

export async function GET(req: NextRequest) {
  // Upgrade to WebSocket — Next.js 16 custom server pattern
  // In production this is handled by a separate ws server
  return new Response('WebSocket endpoint — use ws:// protocol', {
    status: 426,
    headers: { 'Upgrade': 'websocket' },
  });
}

export async function POST(req: NextRequest) {
  // REST fallback for transcript chunks (if WS unavailable)
  try {
    const ctx = await requireUser();
    const body = await req.json();

    const { meetingId, chunk } = body as { meetingId: string; chunk: TranscriptChunk };
    if (!meetingId || !chunk) {
      throw new ApiError(400, 'INVALID_REQUEST', 'meetingId and chunk required');
    }

    const meeting = await prisma.meeting.findFirst({
      where: { id: meetingId, orgId: ctx.orgId },
      include: { participants: true },
    });
    if (!meeting) throw new ApiError(404, 'NOT_FOUND', 'Meeting not found');

    // CRITICAL: Verify consent before processing any audio
    if (!verifyConsent(meeting.participants as any)) {
      throw new ApiError(403, 'CONSENT_REQUIRED',
        'All participants must consent before recording begins');
    }

    // Fetch org laws for trigger matching
    const laws = await prisma.orgLaw.findMany({
      where: { orgId: ctx.orgId, status: { in: ['VALIDATED', 'STRESSED', 'UNKNOWN_TO_LEADERSHIP'] } },
    });

    const result = processTranscriptChunk(chunk, laws as any);

    // Persist transcript line
    await prisma.meeting.update({
      where: { id: meetingId },
      data: {
        transcript: [...(meeting.transcript as any[]), {
          ts: chunk.ts, speakerId: chunk.speakerId,
          speakerName: chunk.speakerName, text: chunk.text,
          highlights: result.highlights,
        }],
      },
    });

    // Log action items as they're detected
    for (const ai of result.actionItems) {
      await prisma.actionItem.create({
        data: {
          orgId: ctx.orgId, meetingId,
          text: ai.text, source: ai.source,
        },
      });
    }

    return NextResponse.json(result);
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json({ error: err.message, code: err.code }, { status: err.status });
    }
    log.error({ err }, 'meeting transcript failed');
    return NextResponse.json({ error: 'Internal error', code: 'INTERNAL' }, { status: 500 });
  }
}

// Helper exported for the ws server (separate process in production)
export function handleMeetingMessage(meetingId: string, message: any, ws: WebSocket) {
  // Broadcast transcript to all participants in the meeting
  const active = activeMeetings.get(meetingId);
  if (!active) return;
  active.ws.forEach(client => {
    if (client !== ws && client.readyState === WebSocket.OPEN) {
      client.send(JSON.stringify(message));
    }
  });
}

// Cron: verify predictions whose verifyDate has passed
export async function verifyDuePredictions() {
  const due = await prisma.prediction.findMany({
    where: { result: 'PENDING', verifyDate: { lte: new Date() } },
  });
  for (const pred of due) {
    // In production: call the OEM verification engine
    // For scaffold: mark as PENDING — verification logic is org-specific
    log.info({ predictionId: pred.id }, 'prediction due for verification');
  }
}

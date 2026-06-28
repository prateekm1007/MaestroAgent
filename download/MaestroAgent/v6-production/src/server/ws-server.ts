// Maestro v6 — WebSocket server with authentication.
// Runs as a separate Node.js process (port 3001) in production.
// Each connection requires a valid JWT and verifies meeting membership.

import { WebSocketServer, WebSocket } from 'ws';
import { randomUUID } from 'crypto';
import http from 'http';
import { env } from '@/lib/env';
import { getRedis, subscribe, publish, disconnectRedis } from '@/lib/redis';
import { prisma, disconnectPrisma } from '@/lib/db';
import { baseLogger } from '@/lib/logger';
import jwt from 'jsonwebtoken';

interface WSClient {
  ws: WebSocket;
  userId: string;
  orgId: string;
  meetingId: string | null;
  isAlive: boolean;
}

const clients = new Map<WebSocket, WSClient>();

export function startWsServer(server?: http.Server): WebSocketServer {
  const wss = server
    ? new WebSocketServer({ server })
    : new WebSocketServer({ port: 3001 });

  wss.on('connection', async (ws: WebSocket, req: http.IncomingMessage) => {
    const connectionId = randomUUID();
    baseLogger.info({ connectionId, url: req.url }, 'WS connection attempt');

    // ─── Auth: verify JWT from query param or header ───
    const url = new URL(req.url || '', `http://${req.headers.host}`);
    const token = url.searchParams.get('token') || extractBearerToken(req.headers.authorization);

    if (!token) {
      baseLogger.warn({ connectionId }, 'WS connection rejected: no token');
      ws.close(4001, 'Authentication required');
      return;
    }

    let payload: { userId: string; orgId: string; role: string };
    try {
      payload = jwt.verify(token, env.NEXTAUTH_SECRET) as any;
    } catch (err) {
      baseLogger.warn({ connectionId, err }, 'WS connection rejected: invalid token');
      ws.close(4001, 'Invalid authentication');
      return;
    }

    const client: WSClient = {
      ws,
      userId: payload.userId,
      orgId: payload.orgId,
      meetingId: null,
      isAlive: true,
    };
    clients.set(ws, client);

    // ─── Heartbeat ───
    ws.on('pong', () => {
      const c = clients.get(ws);
      if (c) c.isAlive = true;
    });

    // ─── Message handling ───
    ws.on('message', async (data: Buffer) => {
      try {
        const message = JSON.parse(data.toString());
        await handleWsMessage(ws, client, message);
      } catch (err) {
        baseLogger.error({ err, connectionId }, 'WS message handling error');
      }
    });

    ws.on('close', () => {
      clients.delete(ws);
      baseLogger.info({ connectionId, userId: payload.userId }, 'WS disconnected');
    });

    ws.on('error', (err) => {
      baseLogger.error({ err, connectionId }, 'WS error');
    });

    baseLogger.info({ connectionId, userId: payload.userId, orgId: payload.orgId }, 'WS authenticated');
  });

  // ─── Heartbeat interval — kill dead connections ───
  const heartbeatInterval = setInterval(() => {
    for (const [ws, client] of clients.entries()) {
      if (!client.isAlive) {
        baseLogger.warn({ userId: client.userId }, 'WS terminating dead connection');
        ws.terminate();
        clients.delete(ws);
        continue;
      }
      client.isAlive = false;
      ws.ping();
    }
  }, 30_000);

  // ─── Subscribe to Redis pub/sub for meeting broadcasts ───
  subscribe('meeting:*', (message: any) => {
    // Broadcast to all clients in the meeting
    for (const [ws, client] of clients.entries()) {
      if (client.meetingId === message.meetingId && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(message));
      }
    }
  });

  // ─── Graceful shutdown ───
  process.on('SIGTERM', async () => {
    baseLogger.info('WS server shutting down');
    clearInterval(heartbeatInterval);
    for (const [ws] of clients) {
      ws.close(1001, 'Server shutting down');
    }
    wss.close();
    await disconnectRedis();
    await disconnectPrisma();
    process.exit(0);
  });

  baseLogger.info({ port: 3001 }, 'WebSocket server started');
  return wss;
}

async function handleWsMessage(ws: WebSocket, client: WSClient, message: any): Promise<void> {
  switch (message.type) {
    case 'join_meeting': {
      const meetingId = message.meetingId;
      if (!meetingId || typeof meetingId !== 'string') {
        ws.send(JSON.stringify({ type: 'error', error: 'meetingId required' }));
        return;
      }

      // Verify meeting exists, belongs to org, and user is a participant
      const meeting = await prisma.meeting.findFirst({
        where: { id: meetingId, orgId: client.orgId },
      });
      if (!meeting) {
        ws.send(JSON.stringify({ type: 'error', error: 'Meeting not found' }));
        return;
      }

      const participants = meeting.participants as any[];
      const isParticipant = participants.some((p) => p.entityId === client.userId);
      if (!isParticipant) {
        ws.send(JSON.stringify({ type: 'error', error: 'Not a participant' }));
        return;
      }

      client.meetingId = meetingId;
      ws.send(JSON.stringify({ type: 'joined', meetingId }));
      baseLogger.info({ userId: client.userId, meetingId }, 'WS joined meeting');
      break;
    }

    case 'leave_meeting': {
      client.meetingId = null;
      ws.send(JSON.stringify({ type: 'left' }));
      break;
    }

    default:
      ws.send(JSON.stringify({ type: 'error', error: `Unknown message type: ${message.type}` }));
  }
}

function extractBearerToken(authHeader?: string): string | null {
  if (!authHeader || !authHeader.startsWith('Bearer ')) return null;
  return authHeader.slice(7);
}

// ─── Start if run directly ───
if (require.main === module) {
  startWsServer();
}

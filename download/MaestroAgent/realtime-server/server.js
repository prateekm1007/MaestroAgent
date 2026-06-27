// server.js — MaestroAgent realtime backend.
//
// Provides:
//   POST /api/runs              { goal } -> { run_id, status }
//   GET  /api/runs              -> [{ id, goal, status, ... }]
//   GET  /api/runs/:id          -> { id, goal, status, artifacts, ... }
//   GET  /api/runs/:id/events   -> [event, event, ...]   (replay)
//   GET  /api/runs/:id/artifacts/:filename -> file download
//   GET  /api/health            -> { ok, providers }
//   WS   /ws/:run_id            -> live event stream
//
// Serves app.html (and assets) from ../  as the default UI.
//
// Port defaults to 8765 — the same port the mock app used, so existing
// bookmarks keep working.

import express from 'express';
import cors from 'cors';
import { WebSocketServer } from 'ws';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { promises as fs } from 'node:fs';

import {
  createRun,
  runGoal,
  getRun,
  listRuns,
  subscribe,
} from './src/engine.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const PROJECT_ROOT = path.resolve(__dirname, '..'); // /home/z/my-project/download/MaestroAgent

const PORT = parseInt(process.env.PORT || '8765', 10);
const app = express();
app.use(cors());
app.use(express.json({ limit: '1mb' }));

// --- Static UI ---
// Serve the new app.html at /, and the mock backup at /mock.
app.get('/', async (req, res) => {
  res.sendFile(path.join(PROJECT_ROOT, 'app.html'));
});
app.get('/app.html', async (req, res) => {
  res.sendFile(path.join(PROJECT_ROOT, 'app.html'));
});
app.get('/mock', async (req, res) => {
  res.sendFile(path.join(PROJECT_ROOT, 'app-mock.html'));
});

// --- API ---
app.get('/api/health', (req, res) => {
  res.json({
    ok: true,
    version: '1.0.0-realtime',
    providers: ['zai'],
    uptime: process.uptime(),
    runs: listRuns().length,
  });
});

app.post('/api/runs', async (req, res) => {
  const goal = (req.body?.goal || '').trim();
  if (!goal) return res.status(400).json({ error: 'goal is required' });
  if (goal.length > 4000) return res.status(400).json({ error: 'goal too long (max 4000 chars)' });

  const run = createRun(goal);
  // Fire and forget — the run streams events to subscribers.
  runGoal(run.id, goal).catch(err => console.error(`[run ${run.id}] failed:`, err));

  res.json({
    run_id: run.id,
    status: run.status,
    goal: run.goal,
    startedAt: run.startedAt,
  });
});

app.get('/api/runs', (req, res) => {
  res.json(listRuns());
});

app.get('/api/runs/:id', (req, res) => {
  const run = getRun(req.params.id);
  if (!run) return res.status(404).json({ error: 'run not found' });
  res.json({
    id: run.id,
    goal: run.goal,
    status: run.status,
    startedAt: run.startedAt,
    endedAt: run.endedAt,
    durationMs: run.durationMs,
    team: run.team,
    artifacts: run.artifacts.map(a => ({
      agent_id: a.agent_id,
      agent_name: a.agent_name,
      filename: a.filename,
      bytes: a.bytes,
      isFinal: !!a.isFinal,
      preview: a.preview,
    })),
    error: run.error,
  });
});

app.get('/api/runs/:id/events', (req, res) => {
  const run = getRun(req.params.id);
  if (!run) return res.status(404).json({ error: 'run not found' });
  res.json(run.events);
});

app.get('/api/runs/:id/artifacts/:filename', async (req, res) => {
  const run = getRun(req.params.id);
  if (!run) return res.status(404).json({ error: 'run not found' });
  const artifact = run.artifacts.find(a => a.filename === req.params.filename);
  if (!artifact) return res.status(404).json({ error: 'artifact not found' });

  try {
    const data = await fs.readFile(artifact.path);
    res.setHeader('Content-Type', 'text/markdown; charset=utf-8');
    res.setHeader('Content-Disposition', `attachment; filename="${artifact.filename}"`);
    res.send(data);
  } catch (err) {
    res.status(500).json({ error: 'failed to read artifact', detail: err.message });
  }
});

// --- HTTP + WS server on the same port ---
const server = http.createServer(app);
// Use noServer mode so we can match any /ws/* path (default `path`
// option only accepts an exact string match).
const wss = new WebSocketServer({ noServer: true });

server.on('upgrade', (req, socket, head) => {
  const match = req.url?.match(/^\/ws\/([^/?]+)/);
  if (!match) {
    socket.write('HTTP/1.1 400 Bad Request\r\n\r\n');
    socket.destroy();
    return;
  }
  wss.handleUpgrade(req, socket, head, (ws) => {
    wss.emit('connection', ws, req);
  });
});

wss.on('connection', async (ws, req) => {
  // Extract run_id from /ws/:run_id
  const match = req.url?.match(/^\/ws\/([^/?]+)/);
  const runId = match?.[1];
  if (!runId) {
    ws.close(4400, 'missing run_id');
    return;
  }
  const run = getRun(runId);
  if (!run) {
    ws.close(4404, 'run not found');
    return;
  }

  // Ack — also tell client how many events we already have (for replay).
  ws.send(JSON.stringify({
    type: 'connected',
    run_id: runId,
    status: run.status,
    event_count: run.events.length,
  }));

  // Replay past events (in case the client connects late).
  for (const ev of run.events) {
    ws.send(JSON.stringify(ev));
  }

  // Subscribe to future events.
  const unsub = subscribe(runId, (event) => {
    if (ws.readyState === ws.OPEN) {
      ws.send(JSON.stringify(event));
    }
  });

  ws.on('close', () => unsub());
  ws.on('error', () => unsub());
});

server.listen(PORT, () => {
  console.log(`\n  MaestroAgent realtime server`);
  console.log(`  ============================`);
  console.log(`  UI:        http://localhost:${PORT}/`);
  console.log(`  Mock UI:   http://localhost:${PORT}/mock`);
  console.log(`  Health:    http://localhost:${PORT}/api/health`);
  console.log(`  WebSocket: ws://localhost:${PORT}/ws/{run_id}`);
  console.log(`  Deliverables: ${path.resolve(__dirname, 'deliverables')}/`);
  console.log();
});

// engine.js — MaestroAgent orchestration engine.
//
// This is the REAL runtime. Given a goal, it:
//   1. Picks a specialist team based on the goal text.
//   2. Runs each agent in sequence via z-ai-web-dev-sdk.
//   3. Streams every LLM token to the run's event bus.
//   4. Saves each agent's output as a real deliverable file on disk.
//   5. Produces a final "deliverable.zip"-style index + the main artifact.
//
// The engine is intentionally simple — no graph DSL, no parallel branches.
// Real Maestro has all that; this is the minimum viable engine that
// produces real streaming + real artifacts. The point is: this is not
// mock. Every byte of LLM output you see in the UI came from a real
// model call.

import ZAI from 'z-ai-web-dev-sdk';
import { promises as fs } from 'node:fs';
import path from 'node:path';
import { AGENTS, pickTeam } from './agents.js';

// In-memory run registry. Keyed by run_id.
// Each entry: { id, goal, status, team, startedAt, endedAt, events: [], subscribers: Set }
export const runs = new Map();

// Each run has its own emitter. Subscribers are async callbacks.
export function subscribe(runId, callback) {
  const run = runs.get(runId);
  if (!run) return () => {};
  run.subscribers.add(callback);
  return () => run.subscribers.delete(callback);
}

export function getRun(runId) {
  return runs.get(runId) || null;
}

export function listRuns() {
  return Array.from(runs.values()).map(r => ({
    id: r.id,
    goal: r.goal,
    status: r.status,
    startedAt: r.startedAt,
    endedAt: r.endedAt,
    teamSize: r.team.length,
    artifacts: r.artifacts.length,
  }));
}

// Emit an event to all subscribers of a run.
async function emit(run, type, payload = {}) {
  const event = {
    type,
    run_id: run.id,
    ts: new Date().toISOString(),
    event_id: crypto.randomUUID(),
    payload,
  };
  run.events.push(event);
  // Fan out — copy the set so a subscriber removing itself mid-emit is safe.
  // Wrap each call in Promise.resolve() so subscribers that return undefined
  // (e.g. ws.send) don't blow up .catch().
  const subs = Array.from(run.subscribers);
  await Promise.all(
    subs.map(fn => Promise.resolve(fn(event)).catch(() => {}))
  );
}

// Stream a single LLM call. Returns the full text once complete.
// Calls onToken(chunk) for every delta.
//
// The z-ai-web-dev-sdk streaming API returns raw SSE byte chunks
// (Uint8Array). Each chunk may contain multiple `data:` lines, each
// holding a JSON object with choices[0].delta.content. We parse them
// manually so we get REAL token-by-token streaming from the model.
async function streamLLM({ system, user, onToken }) {
  const zai = await ZAI.create();
  const messages = [
    { role: 'assistant', content: system },
    { role: 'user', content: user },
  ];

  const stream = await zai.chat.completions.create({
    messages,
    stream: true,
    thinking: { type: 'disabled' },
  });

  let full = '';
  let buffer = ''; // accumulate partial SSE lines across chunks

  for await (const rawChunk of stream) {
    // Coerce to string — chunk may be Uint8Array, Buffer, or already a string.
    let text;
    if (rawChunk instanceof Uint8Array || ArrayBuffer.isView(rawChunk)) {
      text = Buffer.from(rawChunk).toString('utf8');
    } else if (typeof rawChunk === 'string') {
      text = rawChunk;
    } else if (rawChunk?.choices?.[0]?.delta?.content) {
      // Already-parsed object (future SDK versions may do this).
      const delta = rawChunk.choices[0].delta.content;
      full += delta;
      if (onToken) onToken(delta);
      continue;
    } else {
      // Unknown shape — skip.
      continue;
    }

    buffer += text;
    // SSE messages are separated by \n\n; lines start with `data: `.
    const lines = buffer.split('\n');
    // Keep the last (possibly partial) line in the buffer.
    buffer = lines.pop() || '';

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith('data:')) continue;
      const payload = trimmed.slice(5).trim();
      if (payload === '[DONE]') continue;
      try {
        const obj = JSON.parse(payload);
        const delta = obj?.choices?.[0]?.delta?.content || '';
        if (delta) {
          full += delta;
          if (onToken) onToken(delta);
        }
      } catch {
        // Partial JSON in the middle of a chunk — skip, will retry next chunk.
      }
    }
  }

  // Flush any remaining buffer.
  if (buffer.trim().startsWith('data:')) {
    const payload = buffer.trim().slice(5).trim();
    if (payload && payload !== '[DONE]') {
      try {
        const obj = JSON.parse(payload);
        const delta = obj?.choices?.[0]?.delta?.content || '';
        if (delta) {
          full += delta;
          if (onToken) onToken(delta);
        }
      } catch { /* ignore */ }
    }
  }

  return full;
}

// Sanitize a string into a safe filename.
function slugify(s) {
  return s.toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60) || 'output';
}

// Save an artifact to disk. Returns { filename, path, bytes }.
async function saveArtifact(run, agentId, content, ext = 'md') {
  const dir = path.resolve('./deliverables', run.id);
  await fs.mkdir(dir, { recursive: true });
  const filename = `${String(run.artifacts.length + 1).padStart(2, '0')}-${agentId}.${ext}`;
  const full = path.join(dir, filename);
  await fs.writeFile(full, content, 'utf8');
  const stat = await fs.stat(full);
  return { filename, path: full, bytes: stat.size };
}

// Run the full orchestration for a goal. This is the entry point.
export async function runGoal(runId, goal) {
  const run = runs.get(runId);
  if (!run) throw new Error(`Run ${runId} not found`);

  const team = pickTeam(goal);
  run.team = team;
  run.status = 'running';

  await emit(run, 'run.started', {
    goal,
    team: team.agents.map(id => ({ id, ...AGENTS[id] })),
    template: team.title,
  });

  // Brief "thinking" pause so the UI can render the team-joining animation.
  await sleep(400);

  // Announce each specialist joining the team.
  for (const agentId of team.agents) {
    const agent = AGENTS[agentId];
    await emit(run, 'agent.joined', { agent_id: agentId, name: agent.name, icon: agent.icon, role: agent.role });
    await sleep(300);
  }

  // Run each agent in sequence. The context accumulates so later agents
  // can build on earlier agents' output.
  let context = '';
  const startedAt = Date.now();

  try {
    for (let i = 0; i < team.agents.length; i++) {
      const agentId = team.agents[i];
      const agent = AGENTS[agentId];

      await emit(run, 'agent.thinking', {
        agent_id: agentId,
        name: agent.name,
        icon: agent.icon,
        step: i + 1,
        total_steps: team.agents.length,
      });

      // Build the user prompt with accumulated context.
      const userPrompt = agent.buildUserPrompt(goal, context.slice(-4000)); // cap context window

      // Stream the LLM call. Each token gets emitted.
      let buffer = '';
      const fullText = await streamLLM({
        system: agent.systemPrompt,
        user: userPrompt,
        onToken: (delta) => {
          buffer += delta;
          // Emit ~every 8 chars to avoid flooding the WS.
          if (buffer.length >= 8) {
            emit(run, 'agent.token', { agent_id: agentId, delta: buffer });
            buffer = '';
          }
        },
      });
      // Flush any remainder.
      if (buffer) {
        await emit(run, 'agent.token', { agent_id: agentId, delta: buffer });
        buffer = '';
      }

      // Save the artifact.
      const artifact = await saveArtifact(run, agentId, fullText, team.deliverableExt);
      run.artifacts.push({
        agent_id: agentId,
        agent_name: agent.name,
        filename: artifact.filename,
        path: artifact.path,
        bytes: artifact.bytes,
        preview: fullText.slice(0, 200) + (fullText.length > 200 ? '...' : ''),
      });

      await emit(run, 'agent.completed', {
        agent_id: agentId,
        name: agent.name,
        text: fullText,
        artifact: artifact.filename,
        bytes: artifact.bytes,
        step: i + 1,
        total_steps: team.agents.length,
      });

      // Accumulate context for the next agent.
      context += `\n\n### ${agent.name} output\n${fullText}`;
    }

    // Save the final combined deliverable.
    const finalDoc = buildFinalDeliverable(run, goal, context);
    const finalArtifact = await saveArtifact(run, 'final-deliverable', finalDoc, team.deliverableExt);
    run.artifacts.push({
      agent_id: 'final',
      agent_name: 'Final Deliverable',
      filename: finalArtifact.filename,
      path: finalArtifact.path,
      bytes: finalArtifact.bytes,
      preview: finalDoc.slice(0, 200) + '...',
      isFinal: true,
    });

    run.status = 'completed';
    run.endedAt = new Date().toISOString();
    run.durationMs = Date.now() - startedAt;

    await emit(run, 'run.completed', {
      status: 'completed',
      artifacts: run.artifacts.map(a => ({ filename: a.filename, bytes: a.bytes, agent: a.agent_name, isFinal: !!a.isFinal })),
      duration_ms: run.durationMs,
      final_artifact: finalArtifact.filename,
    });
  } catch (err) {
    run.status = 'failed';
    run.endedAt = new Date().toISOString();
    run.error = err.message;
    await emit(run, 'run.failed', { error: err.message, stack: err.stack });
  }
}

// Build the final combined deliverable markdown.
function buildFinalDeliverable(run, goal, context) {
  const lines = [
    `# Deliverable: ${goal}`,
    '',
    `**Produced by:** MaestroAgent`,
    `**Run ID:** ${run.id}`,
    `**Generated:** ${new Date().toISOString()}`,
    `**Team:** ${run.team.agents.map(id => AGENTS[id].name).join(' → ')}`,
    '',
    '---',
    '',
    context.trim(),
    '',
    '---',
    '',
    '## Artifacts Produced',
    '',
    ...run.artifacts.map(a => `- **${a.filename}** (${a.bytes} bytes) — by ${a.agent_name}`),
    '',
  ];
  return lines.join('\n');
}

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

export function createRun(goal) {
  const id = crypto.randomUUID();
  const run = {
    id,
    goal,
    status: 'pending',
    team: null,
    startedAt: new Date().toISOString(),
    endedAt: null,
    durationMs: 0,
    events: [],
    artifacts: [],
    subscribers: new Set(),
    error: null,
  };
  runs.set(id, run);
  return run;
}

// engine.js — MaestroAgent orchestration engine (Phase 4).
//
// Phase 4 architecture:
//
//   1. Conductor examines goal → streams real reasoning to user
//   2. Conductor assembles team → explains WHY each specialist
//   3. For each specialist:
//      a. Conductor hands off (1-2 sentences, streamed)
//      b. Specialist runs (real LLM call, tokens streamed)
//      c. Confidence + disagreements parsed from output
//      d. Evidence added to checklist
//      e. If disagreements exist, queued for resolution
//   4. Conductor resolves all disagreements (debate phase)
//   5. Conductor summarizes with overall confidence
//   6. Final deliverable saved
//
// Interruptions: user messages arrive via /api/runs/:id/interrupt and
// are queued. Before each specialist runs, the queue is drained and
// the message is prepended to that specialist's user prompt. The
// currently-running specialist is NOT cancelled — the interrupt takes
// effect at the next handoff. This is intentional: it preserves the
// work already done while letting the user steer.

import ZAI from 'z-ai-web-dev-sdk';
import { promises as fs } from 'node:fs';
import path from 'node:path';
import { AGENTS, pickTeam, parseConfidence, parseDisagreements, stripStructuredBlocks } from './agents.js';
import {
  conductorExamine,
  conductorAssemble,
  conductorHandoff,
  conductorResolve,
  conductorSummarize,
} from './conductor.js';

// In-memory run registry. Keyed by run_id.
export const runs = new Map();

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
    teamSize: r.team?.agents?.length || 0,
    artifacts: r.artifacts.length,
    avgConfidence: r.avgConfidence || null,
  }));
}

// Push a user interruption into the run's queue.
export function interruptRun(runId, message) {
  const run = runs.get(runId);
  if (!run) return false;
  run.interruptQueue.push(message);
  return true;
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
  const subs = Array.from(run.subscribers);
  await Promise.all(
    subs.map(fn => Promise.resolve(fn(event)).catch(() => {}))
  );
}

// Stream a specialist LLM call. Same SSE parser as before.
// Retries on 429 (rate limit) with exponential backoff.
async function streamLLM({ system, user, onToken }) {
  const zai = await ZAI.create();
  const messages = [
    { role: 'assistant', content: system },
    { role: 'user', content: user },
  ];

  let lastErr = null;
  for (let attempt = 0; attempt < 4; attempt++) {
    try {
      const stream = await zai.chat.completions.create({
        messages,
        stream: true,
        thinking: { type: 'disabled' },
      });
      let full = '';
      let buffer = '';
      for await (const rawChunk of stream) {
        let text;
        if (rawChunk instanceof Uint8Array || ArrayBuffer.isView(rawChunk)) {
          text = Buffer.from(rawChunk).toString('utf8');
        } else if (typeof rawChunk === 'string') {
          text = rawChunk;
        } else if (rawChunk?.choices?.[0]?.delta?.content) {
          const delta = rawChunk.choices[0].delta.content;
          full += delta;
          if (onToken) onToken(delta);
          continue;
        } else {
          continue;
        }
        buffer += text;
        const lines = buffer.split('\n');
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
          } catch {}
        }
      }
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
          } catch {}
        }
      }
      return full;
    } catch (err) {
      lastErr = err;
      if (String(err.message || '').includes('429') && attempt < 3) {
        const wait = Math.pow(2, attempt + 2) * 1000;
        console.warn(`[engine] specialist 429 rate limited, retrying in ${wait/1000}s (attempt ${attempt+1}/3)`);
        await new Promise(r => setTimeout(r, wait));
        continue;
      }
      throw err;
    }
  }
  throw lastErr || new Error('specialist stream failed');
}

async function saveArtifact(run, agentId, content, ext = 'md') {
  const dir = path.resolve('./deliverables', run.id);
  await fs.mkdir(dir, { recursive: true });
  const filename = `${String(run.artifacts.length + 1).padStart(2, '0')}-${agentId}.${ext}`;
  const full = path.join(dir, filename);
  await fs.writeFile(full, content, 'utf8');
  const stat = await fs.stat(full);
  return { filename, path: full, bytes: stat.size };
}

// Drain the interrupt queue. Returns the concatenated message or null.
async function drainInterrupts(run) {
  if (run.interruptQueue.length === 0) return null;
  const messages = run.interruptQueue.splice(0);
  const combined = messages.join(' / ');
  await emit(run, 'user.interrupted', { message: combined });
  return combined;
}

// Main orchestration entry point.
export async function runGoal(runId, goal) {
  const run = runs.get(runId);
  if (!run) throw new Error(`Run ${runId} not found`);

  const team = pickTeam(goal);
  run.team = team;
  run.status = 'running';
  const startedAt = Date.now();

  await emit(run, 'run.started', {
    goal,
    team: team.agents.map(id => ({ id, ...AGENTS[id] })),
    template: team.title,
  });

  try {
    // === PHASE 1: Conductor examines the goal ===
    await emit(run, 'conductor.phase', { phase: 'examine', label: 'Examining the goal' });
    let conductorBuffer = '';
    await conductorExamine(goal, {
      onToken: (delta) => {
        conductorBuffer += delta;
        // Emit batches to avoid flooding.
        if (conductorBuffer.length >= 12) {
          emit(run, 'conductor.token', { phase: 'examine', delta: conductorBuffer });
          conductorBuffer = '';
        }
      },
    });
    if (conductorBuffer) {
      await emit(run, 'conductor.token', { phase: 'examine', delta: conductorBuffer });
    }
    await emit(run, 'conductor.phase_done', { phase: 'examine' });
    await sleep(500); // brief pause to avoid rate limiting

    // === PHASE 2: Conductor assembles the team ===
    await emit(run, 'conductor.phase', { phase: 'assemble', label: 'Assembling the team' });
    // Announce each specialist joining (visual rhythm).
    for (const agentId of team.agents) {
      const agent = AGENTS[agentId];
      await emit(run, 'agent.joined', { agent_id: agentId, name: agent.name, icon: agent.icon, role: agent.role });
      await sleep(200);
    }
    conductorBuffer = '';
    await conductorAssemble(goal, team, {
      onToken: (delta) => {
        conductorBuffer += delta;
        if (conductorBuffer.length >= 12) {
          emit(run, 'conductor.token', { phase: 'assemble', delta: conductorBuffer });
          conductorBuffer = '';
        }
      },
    });
    if (conductorBuffer) {
      await emit(run, 'conductor.token', { phase: 'assemble', delta: conductorBuffer });
    }
    await emit(run, 'conductor.phase_done', { phase: 'assemble' });
    await sleep(500); // brief pause to avoid rate limiting

    // === PHASE 3: Run each specialist ===
    let context = '';
    const disagreements = [];
    const confidences = [];

    for (let i = 0; i < team.agents.length; i++) {
      const agentId = team.agents[i];
      const agent = AGENTS[agentId];

      // Check for user interrupts before this specialist runs.
      const interrupt = await drainInterrupts(run);

      // Conductor handoff (1-2 sentences, streamed).
      await emit(run, 'conductor.phase', {
        phase: 'handoff',
        label: `Handing off to ${agent.name}`,
        agent_id: agentId,
        step: i + 1,
        total_steps: team.agents.length,
      });
      conductorBuffer = '';
      await conductorHandoff(goal, agent, context, i + 1, team.agents.length, {
        onToken: (delta) => {
          conductorBuffer += delta;
          if (conductorBuffer.length >= 12) {
            emit(run, 'conductor.token', { phase: 'handoff', agent_id: agentId, delta: conductorBuffer });
            conductorBuffer = '';
          }
        },
      });
      if (conductorBuffer) {
        await emit(run, 'conductor.token', { phase: 'handoff', agent_id: agentId, delta: conductorBuffer });
      }
      await emit(run, 'conductor.phase_done', { phase: 'handoff', agent_id: agentId });
      await sleep(500); // brief pause to avoid rate limiting

      // Specialist thinking indicator.
      await emit(run, 'agent.thinking', {
        agent_id: agentId,
        name: agent.name,
        icon: agent.icon,
        step: i + 1,
        total_steps: team.agents.length,
      });

      // Build the user prompt with accumulated context + interrupt.
      const userPrompt = agent.buildUserPrompt(goal, context.slice(-4000), interrupt);

      // Stream the specialist LLM call.
      let specialistBuffer = '';
      const fullText = await streamLLM({
        system: agent.systemPrompt,
        user: userPrompt,
        onToken: (delta) => {
          specialistBuffer += delta;
          if (specialistBuffer.length >= 8) {
            emit(run, 'agent.token', { agent_id: agentId, delta: specialistBuffer });
            specialistBuffer = '';
          }
        },
      });
      if (specialistBuffer) {
        await emit(run, 'agent.token', { agent_id: agentId, delta: specialistBuffer });
      }

      // Parse structured blocks from the output.
      const confidence = parseConfidence(fullText);
      const disagreement = parseDisagreements(fullText);
      const visibleText = stripStructuredBlocks(fullText);

      if (confidence) {
        confidences.push(confidence.score);
        await emit(run, 'confidence.reported', {
          agent_id: agentId,
          agent_name: agent.name,
          score: confidence.score,
          reason: confidence.reason,
          alternatives: confidence.alternatives,
        });
      }

      if (disagreement) {
        disagreements.push({ agentId, agentName: agent.name, text: disagreement });
        await emit(run, 'debate.disagreement', {
          agent_id: agentId,
          agent_name: agent.name,
          text: disagreement,
        });
      }

      // Save the full artifact (with structured blocks intact).
      const artifact = await saveArtifact(run, agentId, fullText, team.deliverableExt);
      run.artifacts.push({
        agent_id: agentId,
        agent_name: agent.name,
        filename: artifact.filename,
        path: artifact.path,
        bytes: artifact.bytes,
        preview: visibleText.slice(0, 200) + (visibleText.length > 200 ? '...' : ''),
        confidence: confidence?.score || null,
      });

      // Emit completion + evidence.
      await emit(run, 'agent.completed', {
        agent_id: agentId,
        name: agent.name,
        text: visibleText,
        full_text: fullText,
        artifact: artifact.filename,
        bytes: artifact.bytes,
        step: i + 1,
        total_steps: team.agents.length,
        confidence: confidence?.score || null,
      });

      await emit(run, 'evidence.added', {
        agent_id: agentId,
        label: agent.evidenceLabel,
        agent_name: agent.name,
        artifact: artifact.filename,
      });

      // Accumulate context for the next agent.
      context += `\n\n### ${agent.name} output\n${fullText}`;
    }

    // === PHASE 4: Conductor resolves disagreements ===
    if (disagreements.length > 0) {
      await emit(run, 'conductor.phase', {
        phase: 'resolve',
        label: `Resolving ${disagreements.length} disagreement${disagreements.length > 1 ? 's' : ''}`,
      });
      conductorBuffer = '';
      const resolution = await conductorResolve(goal, disagreements, context, {
        onToken: (delta) => {
          conductorBuffer += delta;
          if (conductorBuffer.length >= 12) {
            emit(run, 'conductor.token', { phase: 'resolve', delta: conductorBuffer });
            conductorBuffer = '';
          }
        },
      });
      if (conductorBuffer) {
        await emit(run, 'conductor.token', { phase: 'resolve', delta: conductorBuffer });
      }
      await emit(run, 'conductor.phase_done', { phase: 'resolve' });

      // Save the resolution as an artifact.
      if (resolution) {
        const resArtifact = await saveArtifact(run, 'debate-resolution', resolution, team.deliverableExt);
        run.artifacts.push({
          agent_id: 'conductor',
          agent_name: 'Conductor (Debate Resolution)',
          filename: resArtifact.filename,
          path: resArtifact.path,
          bytes: resArtifact.bytes,
          preview: resolution.slice(0, 200) + '...',
          isDebateResolution: true,
        });
        await emit(run, 'debate.resolution', {
          text: resolution,
          artifact: resArtifact.filename,
          bytes: resArtifact.bytes,
          disagreement_count: disagreements.length,
        });
      }
    } else {
      await emit(run, 'conductor.phase', { phase: 'resolve', label: 'No disagreements — team aligned' });
      await emit(run, 'conductor.phase_done', { phase: 'resolve' });
    }

    // === PHASE 5: Save final combined deliverable ===
    const avgConfidence = confidences.length > 0
      ? Math.round(confidences.reduce((a, b) => a + b, 0) / confidences.length)
      : null;
    run.avgConfidence = avgConfidence;

    const finalDoc = buildFinalDeliverable(run, goal, context, confidences, disagreements);
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

    // === PHASE 6: Conductor summarizes ===
    await emit(run, 'conductor.phase', { phase: 'summarize', label: 'Wrapping up' });
    conductorBuffer = '';
    await conductorSummarize(goal, run.artifacts, avgConfidence || 0, {
      onToken: (delta) => {
        conductorBuffer += delta;
        if (conductorBuffer.length >= 12) {
          emit(run, 'conductor.token', { phase: 'summarize', delta: conductorBuffer });
          conductorBuffer = '';
        }
      },
    });
    if (conductorBuffer) {
      await emit(run, 'conductor.token', { phase: 'summarize', delta: conductorBuffer });
    }
    await emit(run, 'conductor.phase_done', { phase: 'summarize' });

    run.status = 'completed';
    run.endedAt = new Date().toISOString();
    run.durationMs = Date.now() - startedAt;

    await emit(run, 'run.completed', {
      status: 'completed',
      artifacts: run.artifacts.map(a => ({
        filename: a.filename,
        bytes: a.bytes,
        agent: a.agent_name,
        isFinal: !!a.isFinal,
      })),
      duration_ms: run.durationMs,
      final_artifact: finalArtifact.filename,
      avg_confidence: avgConfidence,
      disagreement_count: disagreements.length,
    });
  } catch (err) {
    run.status = 'failed';
    run.endedAt = new Date().toISOString();
    run.error = err.message;
    await emit(run, 'run.failed', { error: err.message, stack: err.stack });
  }
}

function buildFinalDeliverable(run, goal, context, confidences, disagreements) {
  const avgConf = confidences.length > 0
    ? Math.round(confidences.reduce((a, b) => a + b, 0) / confidences.length)
    : null;
  const lines = [
    `# Deliverable: ${goal}`,
    '',
    `**Produced by:** MaestroAgent`,
    `**Run ID:** ${run.id}`,
    `**Generated:** ${new Date().toISOString()}`,
    `**Team:** ${run.team.agents.map(id => AGENTS[id].name).join(' → ')}`,
    avgConf !== null ? `**Average specialist confidence:** ${avgConf}%` : '',
    `**Disagreements resolved:** ${disagreements.length}`,
    '',
    '---',
    '',
    '## Orchestration Summary',
    '',
    `This deliverable was produced by a team of ${run.team.agents.length} specialists, ` +
      `coordinated by Maestro's Conductor. ` +
      (disagreements.length > 0
        ? `${disagreements.length} disagreement${disagreements.length > 1 ? 's were' : ' was'} raised and resolved.`
        : 'No disagreements were raised — the team was aligned throughout.'),
    '',
    '---',
    '',
    '## Specialist Work',
    '',
    context.trim(),
    '',
    '---',
    '',
    '## Artifacts Produced',
    '',
    ...run.artifacts.map(a => `- **${a.filename}** (${a.bytes} bytes) — by ${a.agent_name}${a.confidence ? ` [confidence: ${a.confidence}%]` : ''}`),
    '',
  ];
  return lines.filter(l => l !== null).join('\n');
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
    interruptQueue: [],
    avgConfidence: null,
  };
  runs.set(id, run);
  return run;
}

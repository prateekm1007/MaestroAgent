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
  conductorLearn,
} from './conductor.js';
import {
  createLearningObject,
  setLessons,
  retrieveSimilar,
  formatRetrievedContext,
  initLearningStore,
} from './learning.js';
import {
  retrievePattern,
  formatPatternContext,
  initPatternStore,
  classifyGoal,
} from './patterns.js';
import {
  retrievePolicies,
  formatPolicyContext,
  validatePlan,
  initPolicyStore,
} from './policies.js';
import {
  retrieveControls,
  validatePlanAgainstGovernance,
  createControlForPolicy,
  initGovernanceStore,
} from './governance.js';
import { createReceipt, initReceiptStore } from './receipts.js';
import { extractEvidenceFromReceipt, createCase, retrievePrecedents, formatPrecedentContext, initEvidenceStore } from './evidence.js';
import { initSDKStore } from './sdk.js';
import { initDesignPartnerStore } from './design-partner.js';
import { initIntegrationStore } from './integrations.js';

// Initialize stores on module load.
initLearningStore().catch(err => console.warn('[engine] learning store init failed:', err.message));
initPatternStore().catch(err => console.warn('[engine] pattern store init failed:', err.message));
initPolicyStore().catch(err => console.warn('[engine] policy store init failed:', err.message));
initGovernanceStore().catch(err => console.warn('[engine] governance store init failed:', err.message));
initReceiptStore().catch(err => console.warn('[engine] receipt store init failed:', err.message));
initEvidenceStore().catch(err => console.warn('[engine] evidence store init failed:', err.message));
initSDKStore().catch(err => console.warn('[engine] sdk store init failed:', err.message));
initDesignPartnerStore().catch(err => console.warn('[engine] design-partner store init failed:', err.message));
initIntegrationStore().catch(err => console.warn('[engine] integration store init failed:', err.message));

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
// Records consumed interrupts on the run for the learning object.
async function drainInterrupts(run) {
  if (run.interruptQueue.length === 0) return null;
  const messages = run.interruptQueue.splice(0);
  const combined = messages.join(' / ');
  // Track consumed interrupts for the learning object.
  if (!run.consumedInterrupts) run.consumedInterrupts = [];
  run.consumedInterrupts.push({ message: combined, beforeAgent: run.currentAgentId || null });
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
    // === PHASE 0: Retrieve execution patterns + policies + governance + past learning ===
    // The planner searches PROVEN EXECUTION PATTERNS (hierarchical),
    // validates against OPERATING POLICIES + GOVERNANCE CONTROLS,
    // and references past learning objects.
    const patternsArr = retrievePattern(goal);
    const patternContext = formatPatternContext(patternsArr);
    const applicablePolicies = retrievePolicies();
    const policyContext = formatPolicyContext(applicablePolicies);
    const governanceControls = retrieveControls();
    const similar = retrieveSimilar(goal, 3);
    const pastContext = formatRetrievedContext(similar);

    if (patternsArr.length > 0) {
      for (const p of patternsArr) {
        await emit(run, 'pattern.retrieved', {
          goalClass: p.goalClass,
          scopeLevel: p.scopeLevel,
          scopeKey: p.scopeKey,
          projectCount: p.projectCount,
          acceptanceRate: p.acceptanceRate,
          predictedAvg: p.confidenceCalibration?.predictedAvg ?? null,
          version: p.version,
          knownFailures: p.observedFailures?.length || 0,
          knownCorrections: p.successfulCorrections?.length || 0,
        });
      }
    }
    if (applicablePolicies.length > 0) {
      const constitutional = applicablePolicies.filter(p => p.status === 'constitutional').length;
      const mandatory = applicablePolicies.filter(p => p.enforcement === 'mandatory' && p.status !== 'constitutional').length;
      await emit(run, 'policies.retrieved', {
        total: applicablePolicies.length,
        constitutional,
        mandatory,
        recommended: applicablePolicies.filter(p => p.enforcement === 'recommended').length,
        policies: applicablePolicies.map(p => ({
          rule: p.rule,
          scopeLevel: p.scopeLevel,
          category: p.category,
          enforcement: p.enforcement,
          status: p.status,
        })),
      });
    }
    if (governanceControls.length > 0) {
      const blocking = governanceControls.filter(c => c.blockExecution).length;
      await emit(run, 'governance.retrieved', {
        total: governanceControls.length,
        blocking,
        approvalRequired: governanceControls.filter(c => c.approvalRequired).length,
        controls: governanceControls.map(c => ({
          rule: c.policyRule,
          scopeLevel: c.scopeLevel,
          enforcement: c.enforcement,
          blockExecution: c.blockExecution,
          reviewer: c.reviewer,
          evidenceRequired: c.evidenceRequired,
        })),
      });
    }
    if (similar.length > 0) {
      await emit(run, 'learning.retrieved', {
        count: similar.length,
        past_goals: similar.map(o => o.goal),
        past_outcomes: similar.map(o => o.outcome),
      });
    }

    // Combine all context for the conductor.
    const goalClass = classifyGoal(goal);
    const precedentsArr = retrievePrecedents(goal, goalClass);
    const precedentContext = formatPrecedentContext(precedentsArr);
    const fullPastContext = [policyContext, precedentContext, patternContext, pastContext].filter(Boolean).join('\n\n');

    if (precedentsArr.length > 0) {
      await emit(run, 'precedents.retrieved', {
        count: precedentsArr.length,
        precedents: precedentsArr.map(p => ({
          goalClass: p.goalClass,
          scopeLevel: p.scopeLevel,
          caseCount: p.caseCount,
          successRate: p.successRate,
          typicalEvidence: p.typicalEvidence,
        })),
      });
    }

    // Store governance controls for validation after planning.
    run._governanceControls = governanceControls;
    run._patternsUsed = patternsArr.map(p => ({
      goalClass: p.goalClass,
      scopeLevel: p.scopeLevel,
      version: p.version,
      projectCount: p.projectCount,
    }));
    run._policiesApplied = applicablePolicies.map(p => ({
      policyId: p.id,
      rule: p.rule,
      enforcement: p.enforcement,
      status: p.status,
      scopeLevel: p.scopeLevel,
    }));

    // === PHASE 1: Conductor examines the goal ===
    const topPattern = patternsArr[0];
    const govNote = governanceControls.length > 0 ? ` · ${governanceControls.length} governance controls (${governanceControls.filter(c => c.blockExecution).length} blocking)` : '';
    const policyNote = applicablePolicies.length > 0 ? ` · ${applicablePolicies.length} policies` : '';
    const phaseLabel = topPattern
      ? `Examining the goal · ${topPattern.scopeLevel} pattern: ${topPattern.goalClass} (${topPattern.projectCount} projects)${policyNote}${govNote}${patternsArr.length > 1 ? ' + ' + (patternsArr.length - 1) + ' more' : ''}`
      : similar.length > 0
        ? `Examining the goal · ${similar.length} past project${similar.length > 1 ? 's' : ''} referenced${policyNote}${govNote}`
        : applicablePolicies.length > 0 || governanceControls.length > 0
          ? `Examining the goal · ${policyNote.slice(3)}${govNote}`
          : 'Examining the goal';
    await emit(run, 'conductor.phase', { phase: 'examine', label: phaseLabel });
    let conductorBuffer = '';
    await conductorExamine(goal, {
      onToken: (delta) => {
        conductorBuffer += delta;
        if (conductorBuffer.length >= 12) {
          emit(run, 'conductor.token', { phase: 'examine', delta: conductorBuffer });
          conductorBuffer = '';
        }
      },
    }, fullPastContext);
    if (conductorBuffer) {
      await emit(run, 'conductor.token', { phase: 'examine', delta: conductorBuffer });
    }
    await emit(run, 'conductor.phase_done', { phase: 'examine' });
    await sleep(1500); // pause to avoid rate limiting

    // === GOVERNANCE VALIDATION ===
    // The conductor's examine phase produced an implicit plan (the narration).
    // Validate that plan against governance controls.
    // If any CONSTITUTIONAL rule is violated, BLOCK execution.
    // This is constitutional execution — the planner refuses to violate governance.
    if (run._governanceControls && run._governanceControls.length > 0) {
      const planText = goal + ' ' + (conductorBuffer || ''); // simple plan proxy
      const validation = validatePlanAgainstGovernance(planText);

      if (validation.violations.length > 0) {
        // CONSTITUTIONAL VIOLATION — block execution.
        await emit(run, 'governance.violation', {
          violations: validation.violations,
          blocked: true,
          message: 'Execution blocked: constitutional rules would be violated.',
        });
        run.status = 'blocked';
        run.endedAt = new Date().toISOString();
        run.error = 'Execution blocked by governance controls: ' + validation.violations.map(v => v.control).join('; ');
        await emit(run, 'run.failed', {
          error: run.error,
          reason: 'governance_violation',
          violations: validation.violations,
        });
        // Still generate a receipt for audit purposes.
        await generateReceipt(run, validation);
        return;
      }

      if (validation.warnings.length > 0) {
        await emit(run, 'governance.warning', {
          warnings: validation.warnings,
          message: 'Mandatory policies not addressed — proceeding with warnings.',
        });
      }

      await emit(run, 'governance.validated', {
        allowed: validation.allowed,
        controlCount: validation.controlCount,
        evidenceRequired: validation.evidenceRequired,
        approvalsRequired: validation.approvalsRequired,
        message: `Plan validated against ${validation.controlCount} governance controls.`,
      });

      // Store validation results for the receipt.
      run._governanceValidation = validation;
    }

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
    await sleep(1500); // pause to avoid rate limiting

    // === PHASE 3: Run each specialist ===
    let context = '';
    const disagreements = [];
    const confidences = [];

    for (let i = 0; i < team.agents.length; i++) {
      const agentId = team.agents[i];
      const agent = AGENTS[agentId];
      run.currentAgentId = agentId; // for interrupt tracking

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
      await sleep(1500); // pause to avoid rate limiting

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

    // === PHASE 7: LEARN — extract lessons and create Learning Object ===
    // This is the constitutional principle in action:
    //   "Every completed project must make Maestro measurably better."
    // The learn phase runs AFTER the user-facing run.completed event,
    // so the user sees completion immediately. Lessons are extracted
    // in the background and stored for future runs.
    try {
      // Snapshot the interrupts that were consumed during the run.
      run.interruptQueueSnapshot = run.consumedInterrupts || [];
      // Create the learning object (outcome = pending until user feedback).
      const learningObj = createLearningObject(run);
      await emit(run, 'learning.created', {
        learning_id: learningObj.id,
        outcome: 'pending',
        message: 'Learning object created — awaiting user feedback',
      });

      // Run the conductor learn phase (not streamed to user — internal).
      await sleep(1500); // pause to avoid rate limiting
      const lessons = await conductorLearn(
        goal, team, context, disagreements, avgConfidence, { onToken: () => {} }
      );
      await setLessons(run.id, lessons);
      await emit(run, 'learning.lesson_extracted', {
        learning_id: learningObj.id,
        lessons_preview: lessons.slice(0, 300),
      });
      console.log(`[learning] run ${run.id} → learning object ${learningObj.id} (${lessons.length} chars of lessons)`);
    } catch (learnErr) {
      // Learning failure must NOT fail the run — the deliverable is already done.
      console.warn(`[learning] failed to extract lessons for run ${run.id}:`, learnErr.message);
    }

    // === PHASE 8: Generate Execution Receipt ===
    // Every execution produces an immutable receipt — the audit trail.
    // This is what enterprises pay millions for: governance + auditability.
    try {
      await generateReceipt(run, run._governanceValidation);
    } catch (receiptErr) {
      console.warn(`[receipts] failed to generate receipt for run ${run.id}:`, receiptErr.message);
    }
  } catch (err) {
    run.status = 'failed';
    run.endedAt = new Date().toISOString();
    run.error = err.message;
    await emit(run, 'run.failed', { error: err.message, stack: err.stack });
  }
}

// Generate an Execution Receipt for a run.
// This is the audit trail — it records WHAT was done, WHY, under which
// policies, with what evidence, and whether governance was satisfied.
async function generateReceipt(run, governanceValidation) {
  const evidence = [];
  const approvals = [];

  // Collect evidence from governance validation.
  if (governanceValidation?.evidenceRequired) {
    for (const req of governanceValidation.evidenceRequired) {
      evidence.push({
        type: 'policy_evidence',
        description: req.evidence,
        control: req.control,
        scope: req.scope,
        timestamp: new Date().toISOString(),
      });
    }
  }

  // Collect approvals.
  if (governanceValidation?.approvalsRequired) {
    for (const appr of governanceValidation.approvalsRequired) {
      approvals.push({
        required: true,
        granted: false, // In production, this would be a real approval flow
        reviewer: appr.reviewer,
        control: appr.control,
        scope: appr.scope,
        timestamp: null,
      });
    }
  }

  // Collect evidence from artifacts (each artifact is evidence of work done).
  for (const artifact of run.artifacts || []) {
    evidence.push({
      type: 'deliverable',
      description: artifact.agent_name + ' produced ' + artifact.filename,
      artifact: artifact.filename,
      bytes: artifact.bytes,
      timestamp: new Date().toISOString(),
    });
  }

  const receipt = await createReceipt(run, {
    policiesApplied: run._policiesApplied || [],
    patternsUsed: run._patternsUsed || [],
    evidence,
    approvals,
    exceptions: governanceValidation?.violations?.map(v => ({
      policyId: v.control,
      reason: v.severity,
      approvedBy: null,
    })) || [],
  });

  await emit(run, 'receipt.created', {
    receiptId: receipt.receiptId,
    receiptHash: receipt.receiptHash,
    policyCount: receipt.policiesApplied.length,
    patternCount: receipt.patternsUsed.length,
    evidenceCount: receipt.evidence.length,
    approvalCount: receipt.approvals.length,
    message: 'Execution receipt generated — audit trail available.',
  });

  // Extract evidence from the receipt and create a Case.
  // This is what makes governance ACTIVE — future runs will reason
  // about this case as a precedent.
  try {
    const evidenceItems = await extractEvidenceFromReceipt(receipt);
    const caseObj = await createCase(receipt, evidenceItems);
    await emit(run, 'evidence.extracted', {
      evidenceCount: evidenceItems.length,
      caseId: caseObj.id,
      caseOutcome: caseObj.outcome,
      message: `Evidence extracted — ${evidenceItems.length} items. Case created for precedent reasoning.`,
    });
    console.log(`[evidence] ${evidenceItems.length} evidence items + case ${caseObj.id.slice(0, 8)} created for run ${run.id.slice(0, 8)}`);
  } catch (evErr) {
    console.warn(`[evidence] failed to extract evidence: ${evErr.message}`);
  }

  return receipt;
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

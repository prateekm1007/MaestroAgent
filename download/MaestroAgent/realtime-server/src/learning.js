// learning.js — Maestro's Execution Intelligence layer.
//
// THE CONSTITUTIONAL PRINCIPLE:
//   "Every completed project must make Maestro measurably better."
//
// This file is the embodiment of that principle. Every completed run
// produces a Learning Object. Every new run retrieves relevant past
// Learning Objects and uses them to plan, route, and predict better.
//
// A Learning Object is worth more than the deliverable that produced it,
// because the deliverable serves one user once, while the Learning
// Object improves the next thousand projects.
//
// Learning Object shape:
//   {
//     id, runId, goal, goalCategory, teamTemplate,
//     specialists: [{ id, name, confidence, outputPreview }],
//     interrupts: [{ message, beforeAgent }],  // user corrections
//     predictedConfidence,  // average at run time
//     outcome: 'pending' | 'accepted' | 'rejected' | 'edited',
//     outcomeNotes: string,
//     lessons: string,  // extracted by conductor after completion
//     workflowScoreDelta: number,  // +1 accepted, -1 rejected, 0 edited
//     deliverableCount, durationMs,
//     createdAt
//   }

import { promises as fs } from 'node:fs';
import path from 'node:path';
import { updatePatternFromLearning } from './patterns.js';
import { checkForPolicyPromotion } from './policies.js';
import { createControlForPolicy } from './governance.js';

// In-memory store. Persisted to disk as JSONL.
const STORE_PATH = path.resolve('./learning-objects.jsonl');
const learningObjects = new Map(); // id -> LearningObject

// Load existing learning objects on startup.
export async function initLearningStore() {
  try {
    const data = await fs.readFile(STORE_PATH, 'utf8');
    for (const line of data.split('\n').filter(Boolean)) {
      try {
        const obj = JSON.parse(line);
        learningObjects.set(obj.id, obj);
      } catch {}
    }
    console.log(`[learning] loaded ${learningObjects.size} learning objects from disk`);
  } catch (err) {
    if (err.code !== 'ENOENT') console.warn('[learning] failed to load store:', err.message);
  }
}

// Persist a single learning object (append-only).
async function persist(obj) {
  try {
    await fs.appendFile(STORE_PATH, JSON.stringify(obj) + '\n', 'utf8');
  } catch (err) {
    console.warn('[learning] failed to persist:', err.message);
  }
}

// Create a learning object from a completed run.
// Called after the run completes (and before lessons are extracted).
export function createLearningObject(run) {
  const obj = {
    id: crypto.randomUUID(),
    runId: run.id,
    goal: run.goal,
    goalCategory: run.team?.title || 'unknown',
    teamTemplate: run.team?.agents || [],
    specialists: (run.artifacts || [])
      .filter(a => !a.isFinal && !a.isDebateResolution)
      .map(a => ({
        id: a.agent_id,
        name: a.agent_name,
        confidence: a.confidence ?? null,
        outputPreview: (a.preview || '').slice(0, 200),
      })),
    interrupts: run.interruptQueueSnapshot || [],
    predictedConfidence: run.avgConfidence ?? null,
    outcome: 'pending',
    outcomeNotes: '',
    lessons: '',  // filled in by conductor 'learn' phase
    workflowScoreDelta: 0,
    deliverableCount: run.artifacts?.length || 0,
    durationMs: run.durationMs || 0,
    createdAt: new Date().toISOString(),
  };
  learningObjects.set(obj.id, obj);
  return obj;
}

// Update a learning object with lessons extracted by the conductor.
export async function setLessons(runId, lessons) {
  for (const obj of learningObjects.values()) {
    if (obj.runId === runId) {
      obj.lessons = lessons;
      await persist(obj);
      return obj;
    }
  }
  return null;
}

// Record the user's outcome feedback. This closes the learning loop.
// Without outcome measurement, there is no learning — only data.
// When outcome is recorded, we ALSO update the Execution Pattern for
// this goal class. Patterns are the scalable abstraction — they
// aggregate across all Learning Objects of the same class.
export async function recordOutcome(runId, outcome, notes = '') {
  if (!['accepted', 'rejected', 'edited'].includes(outcome)) {
    throw new Error('outcome must be accepted | rejected | edited');
  }
  for (const obj of learningObjects.values()) {
    if (obj.runId === runId) {
      obj.outcome = outcome;
      obj.outcomeNotes = notes;
      obj.workflowScoreDelta = outcome === 'accepted' ? 1 : outcome === 'rejected' ? -1 : 0;
      await persist(obj);

      // Update the Execution Pattern for this goal class.
      // This is the key architectural step: individual project learning
      // becomes reusable execution knowledge.
      try {
        const pattern = await updatePatternFromLearning(obj);
        console.log(`[patterns] updated pattern for "${pattern.goalClass}" (v${pattern.version}, ${pattern.projectCount} projects)`);

        // LAW PROMOTION: check if any corrections in the pattern should
        // promote to Operating Policies. This is the governance layer —
        // when a correction is seen N times, it becomes mandatory.
        const promotedPolicies = await checkForPolicyPromotion(pattern);
        if (promotedPolicies.length > 0) {
          console.log(`[policies] ${promotedPolicies.length} policy(ies) created/reinforced from pattern "${pattern.goalClass}"`);

          // GOVERNANCE: create governance controls for any new mandatory
          // or constitutional policies. This makes them EXECUTABLE —
          // the planner will refuse to violate them.
          for (const policy of promotedPolicies) {
            if (policy.enforcement === 'mandatory' || policy.enforcement === 'constitutional') {
              if (!policy._controlCreated) {
                try {
                  await createControlForPolicy(policy);
                  policy._controlCreated = true;
                } catch (err) {
                  console.warn(`[governance] failed to create control for policy: ${err.message}`);
                }
              }
            }
          }
        }
      } catch (err) {
        console.warn(`[patterns] failed to update pattern: ${err.message}`);
      }

      return obj;
    }
  }
  return null;
}

// Retrieve the K most relevant learning objects for a new goal.
//
// Relevance is currently computed by simple keyword overlap.
// This is intentionally simple — the point is to prove the flywheel
// spins, not to build perfect retrieval. Embeddings come later.
//
// We also weight by outcome: accepted projects are preferred over
// rejected ones, because accepted projects represent workflows that
// actually worked.
export function retrieveSimilar(goal, k = 3) {
  const goalLower = goal.toLowerCase();
  const goalTokens = new Set(
    goalLower
      .replace(/[^a-z0-9\s]/g, ' ')
      .split(/\s+/)
      .filter(t => t.length > 2 && !STOPWORDS.has(t))
  );

  const scored = [];
  for (const obj of learningObjects.values()) {
    if (!obj.lessons && obj.outcome === 'pending') continue; // skip unlearned objects
    const objTokens = new Set(
      obj.goal.toLowerCase()
        .replace(/[^a-z0-9\s]/g, ' ')
        .split(/\s+/)
        .filter(t => t.length > 2)
    );
    // Jaccard-ish overlap.
    let overlap = 0;
    for (const t of goalTokens) if (objTokens.has(t)) overlap++;
    if (overlap === 0) continue;

    // Boost by outcome.
    const outcomeBoost = obj.outcome === 'accepted' ? 1.5 : obj.outcome === 'rejected' ? 0.5 : 1.0;
    // Boost by having lessons.
    const lessonBoost = obj.lessons ? 1.3 : 1.0;
    const score = overlap * outcomeBoost * lessonBoost;
    scored.push({ obj, score, overlap });
  }

  scored.sort((a, b) => b.score - a.score);
  return scored.slice(0, k).map(s => s.obj);
}

// Get stats for UI / debugging.
export function getStats() {
  const all = Array.from(learningObjects.values());
  return {
    total: all.length,
    withLessons: all.filter(o => o.lessons).length,
    accepted: all.filter(o => o.outcome === 'accepted').length,
    rejected: all.filter(o => o.outcome === 'rejected').length,
    edited: all.filter(o => o.outcome === 'edited').length,
    pending: all.filter(o => o.outcome === 'pending').length,
  };
}

// Format retrieved learning objects as context for the conductor's
// examine phase. This is the actual mechanism by which past projects
// make the next project better.
export function formatRetrievedContext(learningObjects) {
  if (!learningObjects || learningObjects.length === 0) return '';
  const lines = learningObjects.map((obj, i) => {
    const outcomeLabel = obj.outcome === 'accepted' ? '✓ accepted by user'
      : obj.outcome === 'rejected' ? '✗ rejected by user'
      : obj.outcome === 'edited' ? '~ user made edits'
      : '○ outcome pending';
    return `--- Past Project ${i + 1} (${outcomeLabel}) ---
Goal: ${obj.goal}
Team: ${obj.specialists.map(s => s.name).join(' → ')}
Predicted confidence: ${obj.predictedConfidence ?? 'unknown'}%
Duration: ${(obj.durationMs / 1000).toFixed(1)}s
${obj.lessons ? `Lessons learned:\n${obj.lessons}` : '(no lessons extracted yet)'}
${obj.outcomeNotes ? `User notes: ${obj.outcomeNotes}` : ''}`;
  });
  return lines.join('\n\n');
}

const STOPWORDS = new Set([
  'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'her',
  'was', 'one', 'our', 'out', 'has', 'have', 'his', 'how', 'its', 'may',
  'new', 'now', 'old', 'see', 'way', 'who', 'did', 'got', 'let', 'say',
  'she', 'too', 'use', 'with', 'this', 'that', 'from', 'they', 'will',
  'would', 'there', 'their', 'what', 'about', 'which', 'when', 'your',
  'make', 'made', 'want', 'need', 'into', 'some', 'them', 'than', 'then',
  'just', 'like', 'also', 'been', 'were',
]);

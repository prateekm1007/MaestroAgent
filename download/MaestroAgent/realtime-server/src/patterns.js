// patterns.js — Maestro's Execution Pattern Registry.
//
// ARCHITECTURE:
//   Run → Learning Object → Pattern Extraction → Pattern Registry → Planner → Run
//
// A Learning Object remembers WHAT HAPPENED in one project.
// An Execution Pattern remembers HOW TO DO a class of work.
//
// Patterns are extracted from multiple Learning Objects of the same goal
// class. They represent the proven workflow, observed failure modes,
// successful corrections, and calibrated confidence for that class.
//
// The planner doesn't search projects. It searches proven execution
// patterns. That's the scalable flywheel.
//
// Execution Pattern shape:
//   {
//     id,
//     goalClass,              // e.g. "Technical Blog", "Python Function", "Research Brief"
//     goalClassKeywords,      // tokens that map a new goal to this pattern
//     winningWorkflow,        // the specialist team that works for this class
//     observedFailures,       // what tends to go wrong
//     successfulCorrections,  // what fixes those failures
//     confidenceCalibration,  // { predictedAvg, realizedAcceptanceRate, calibrationNote }
//     acceptanceRate,         // % of projects with this pattern that were accepted
//     projectCount,           // how many projects contributed to this pattern
//     sourceRunIds,           // the Learning Objects that fed this pattern
//     lastUpdated,
//     version                 // bumped each time the pattern is updated
//   }

import { promises as fs } from 'node:fs';
import path from 'node:path';

const PATTERN_STORE_PATH = path.resolve('./execution-patterns.jsonl');
const patterns = new Map(); // id -> ExecutionPattern

// Load on startup.
export async function initPatternStore() {
  try {
    const data = await fs.readFile(PATTERN_STORE_PATH, 'utf8');
    for (const line of data.split('\n').filter(Boolean)) {
      try {
        const obj = JSON.parse(line);
        // Keep only the latest version of each pattern (by id).
        patterns.set(obj.id, obj);
      } catch {}
    }
    console.log(`[patterns] loaded ${patterns.size} execution patterns from disk`);
  } catch (err) {
    if (err.code !== 'ENOENT') console.warn('[patterns] failed to load store:', err.message);
  }
}

async function persist(pattern) {
  try {
    await fs.appendFile(PATTERN_STORE_PATH, JSON.stringify(pattern) + '\n', 'utf8');
  } catch (err) {
    console.warn('[patterns] failed to persist:', err.message);
  }
}

// Classify a goal into a goal class.
// This is intentionally simple — keyword matching. The point is to
// group similar goals so patterns can emerge across projects.
// Order matters: more specific checks first.
export function classifyGoal(goal) {
  const g = goal.toLowerCase();
  // Check for code-writing intent first — needs to actually be about
  // writing/implementing code, not just mentioning programming concepts.
  if (/\b(write|create|build|implement|generate)\s+(a\s+)?(python|javascript|typescript|rust|go|java|c\+\+|function|class|component|api|script|algorithm)\b/.test(g)) return 'Code Implementation';
  if (/\b(code|api endpoint|function that|class that|algorithm that|unit test|test suite)\b/.test(g)) return 'Code Implementation';
  if (/\b(research|investigat|study|explor|understand|learn about|brief|report on)\b/.test(g)) return 'Research Brief';
  if (/\b(write|blog|article|content|essay|story|copy|post|newsletter)\b/.test(g)) return 'Content Writing';
  if (/\b(analyz|data|insight|metric|kpi|report|trend|pattern|dashboard)\b/.test(g)) return 'Data Analysis';
  if (/\b(build|app|application|tool|software|saas|feature|prototype|mvp|product)\b/.test(g)) return 'Product Build';
  if (/\b(review|audit|assess|evaluat|check)\b/.test(g)) return 'Review & Assessment';
  if (/\b(plan|strategy|roadmap|design|architect)\b/.test(g)) return 'Planning & Strategy';
  if (/\b(email|letter|message|proposal|pitch|deck)\b/.test(g)) return 'Communication';
  return 'General Task';
}

// Extract keywords from a goal for pattern matching.
function extractKeywords(goal) {
  return goal.toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .split(/\s+/)
    .filter(t => t.length > 2 && !STOPWORDS.has(t));
}

// Find or create a pattern for a goal class.
function getOrCreatePattern(goalClass) {
  for (const p of patterns.values()) {
    if (p.goalClass === goalClass) return p;
  }
  const newPattern = {
    id: crypto.randomUUID(),
    goalClass,
    goalClassKeywords: [],
    winningWorkflow: [],
    observedFailures: [],
    successfulCorrections: [],
    confidenceCalibration: { predictedAvg: null, realizedAcceptanceRate: null, calibrationNote: '' },
    acceptanceRate: null,
    projectCount: 0,
    sourceRunIds: [],
    lastUpdated: new Date().toISOString(),
    version: 0,
  };
  patterns.set(newPattern.id, newPattern);
  return newPattern;
}

// Update a pattern with data from a completed Learning Object.
// This is called after the learning loop closes (user feedback recorded).
//
// The pattern aggregates across all Learning Objects of its goal class.
// Each new project refines the pattern.
export async function updatePatternFromLearning(learningObj) {
  const goalClass = classifyGoal(learningObj.goal);
  const pattern = getOrCreatePattern(goalClass);

  // Add this run's keywords to the pattern's keyword set.
  const newKeywords = extractKeywords(learningObj.goal);
  const existingKeywords = new Set(pattern.goalClassKeywords);
  for (const k of newKeywords) existingKeywords.add(k);
  pattern.goalClassKeywords = Array.from(existingKeywords).slice(0, 100);

  // Track the workflow (specialist team) — only if accepted or edited.
  if (learningObj.outcome !== 'rejected' && learningObj.teamTemplate?.length > 0) {
    const workflowKey = learningObj.teamTemplate.join('→');
    // Find existing workflow entry or add new one.
    let workflow = pattern.winningWorkflow.find(w => w.team === workflowKey);
    if (!workflow) {
      workflow = { team: workflowKey, specialists: learningObj.teamTemplate, count: 0, acceptedCount: 0 };
      pattern.winningWorkflow.push(workflow);
    }
    workflow.count++;
    if (learningObj.outcome === 'accepted') workflow.acceptedCount++;
  }

  // Extract observed failures and corrections from the lessons text.
  // The conductor's learn phase produces structured lessons:
  //   WHAT WORKED: ...
  //   WHAT TO DO DIFFERENTLY NEXT TIME: ...
  //   WORKFLOW PATTERN: ...
  //   CONFIDENCE CALIBRATION NOTE: ...
  if (learningObj.lessons) {
    const failures = extractSection(learningObj.lessons, 'WHAT TO DO DIFFERENTLY NEXT TIME');
    const corrections = extractSection(learningObj.lessons, 'WHAT WORKED');
    const calibrationNote = extractSection(learningObj.lessons, 'CONFIDENCE CALIBRATION NOTE');

    if (failures) {
      // Add each failure bullet to the pattern (deduped by first 60 chars).
      for (const bullet of failures.split('\n').filter(l => l.trim().startsWith('-'))) {
        const text = bullet.replace(/^\s*-\s*/, '').trim();
        if (!text || text.toLowerCase().includes('nothing notable')) continue;
        const exists = pattern.observedFailures.some(f => f.text.slice(0, 60) === text.slice(0, 60));
        if (!exists) {
          pattern.observedFailures.push({ text, firstSeen: learningObj.createdAt, occurrences: 1 });
        } else {
          const existing = pattern.observedFailures.find(f => f.text.slice(0, 60) === text.slice(0, 60));
          existing.occurrences = (existing.occurrences || 1) + 1;
        }
      }
    }

    if (corrections) {
      for (const bullet of corrections.split('\n').filter(l => l.trim().startsWith('-'))) {
        const text = bullet.replace(/^\s*-\s*/, '').trim();
        if (!text) continue;
        const exists = pattern.successfulCorrections.some(c => c.text.slice(0, 60) === text.slice(0, 60));
        if (!exists) {
          pattern.successfulCorrections.push({ text, firstSeen: learningObj.createdAt, occurrences: 1 });
        } else {
          const existing = pattern.successfulCorrections.find(c => c.text.slice(0, 60) === text.slice(0, 60));
          existing.occurrences = (existing.occurrences || 1) + 1;
        }
      }
    }

    if (calibrationNote) {
      pattern.confidenceCalibration.calibrationNote = calibrationNote.trim();
    }
  }

  // Update acceptance rate.
  pattern.sourceRunIds.push(learningObj.runId);
  pattern.projectCount = pattern.sourceRunIds.length;

  // Recalculate acceptance rate from all source runs.
  // (We need to look up outcomes — but we don't have them here directly.
  // For now, track from the learning object's outcome.)
  if (!pattern._outcomes) pattern._outcomes = [];
  pattern._outcomes.push(learningObj.outcome);
  const accepted = pattern._outcomes.filter(o => o === 'accepted').length;
  const total = pattern._outcomes.filter(o => o !== 'pending').length;
  pattern.acceptanceRate = total > 0 ? accepted / total : null;

  // Update confidence calibration.
  if (learningObj.predictedConfidence !== null) {
    const allPred = pattern.sourceRunIds.length;
    // We'll store the latest predicted confidence as the running average.
    if (!pattern.confidenceCalibration.predictedAvg) {
      pattern.confidenceCalibration.predictedAvg = learningObj.predictedConfidence;
    } else {
      // Running average.
      const n = pattern.projectCount;
      pattern.confidenceCalibration.predictedAvg =
        Math.round((pattern.confidenceCalibration.predictedAvg * (n - 1) + learningObj.predictedConfidence) / n);
    }
  }
  pattern.confidenceCalibration.realizedAcceptanceRate = pattern.acceptanceRate;

  // Bump version and persist.
  pattern.version++;
  pattern.lastUpdated = new Date().toISOString();
  // Don't persist the internal _outcomes field.
  const { _outcomes, ...persistable } = pattern;
  await persist(persistable);

  return pattern;
}

// Extract a section from the conductor's structured lessons output.
function extractSection(text, sectionName) {
  const regex = new RegExp(sectionName + ':?\\s*\\n([\\s\\S]*?)(?:\\n\\n[A-Z][A-Z ]+:|$)', 'i');
  const m = text.match(regex);
  return m ? m[1].trim() : '';
}

// Retrieve the best execution pattern for a new goal.
// Returns the pattern for the goal's class, or null if none exists yet.
export function retrievePattern(goal) {
  const goalClass = classifyGoal(goal);
  for (const p of patterns.values()) {
    if (p.goalClass === goalClass && p.projectCount > 0) {
      return p;
    }
  }
  return null;
}

// Format a pattern as context for the conductor's examine phase.
// This is how the planner "searches proven execution patterns"
// instead of searching individual projects.
export function formatPatternContext(pattern) {
  if (!pattern || pattern.projectCount === 0) return '';

  const workflowStr = pattern.winningWorkflow
    .sort((a, b) => b.acceptedCount - a.acceptedCount)
    .slice(0, 2)
    .map(w => `  - ${w.specialists.join(' → ')} (${w.acceptedCount}/${w.count} accepted)`)
    .join('\n');

  const failuresStr = pattern.observedFailures
    .slice(0, 3)
    .sort((a, b) => (b.occurrences || 1) - (a.occurrences || 1))
    .map(f => `  - ${f.text}${f.occurrences > 1 ? ` (seen ${f.occurrences}×)` : ''}`)
    .join('\n');

  const correctionsStr = pattern.successfulCorrections
    .slice(0, 3)
    .sort((a, b) => (b.occurrences || 1) - (a.occurrences || 1))
    .map(c => `  - ${c.text}${c.occurrences > 1 ? ` (confirmed ${c.occurrences}×)` : ''}`)
    .join('\n');

  const lines = [
    `--- Execution Pattern for: ${pattern.goalClass} ---`,
    `Projects observed: ${pattern.projectCount}`,
    `Acceptance rate: ${pattern.acceptanceRate !== null ? Math.round(pattern.acceptanceRate * 100) + '%' : 'unknown'}`,
    `Predicted confidence (avg): ${pattern.confidenceCalibration.predictedAvg ?? 'unknown'}%`,
    `Realized acceptance rate: ${pattern.confidenceCalibration.realizedAcceptanceRate !== null ? Math.round(pattern.confidenceCalibration.realizedAcceptanceRate * 100) + '%' : 'unknown'}`,
    '',
    `Proven workflows:`,
    workflowStr || '  (none yet)',
    '',
    `Known failure modes:`,
    failuresStr || '  (none yet)',
    '',
    `Successful corrections:`,
    correctionsStr || '  (none yet)',
    '',
  ];
  if (pattern.confidenceCalibration.calibrationNote) {
    lines.push(`Calibration note: ${pattern.confidenceCalibration.calibrationNote}`);
  }
  lines.push('---');
  return lines.join('\n');
}

// Get stats for all patterns.
export function getPatternStats() {
  const all = Array.from(patterns.values());
  return all.map(p => ({
    goalClass: p.goalClass,
    projectCount: p.projectCount,
    acceptanceRate: p.acceptanceRate,
    predictedAvg: p.confidenceCalibration?.predictedAvg ?? null,
    version: p.version,
  }));
}

const STOPWORDS = new Set([
  'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'her',
  'was', 'one', 'our', 'out', 'has', 'have', 'his', 'how', 'its', 'may',
  'new', 'now', 'old', 'see', 'way', 'who', 'did', 'got', 'let', 'say',
  'she', 'too', 'use', 'with', 'this', 'that', 'from', 'they', 'will',
  'would', 'there', 'their', 'what', 'about', 'which', 'when', 'your',
  'make', 'made', 'want', 'need', 'into', 'some', 'them', 'than', 'then',
  'just', 'like', 'also', 'been', 'were', 'write', 'short', 'about',
  'benefits', 'should', 'could',
]);

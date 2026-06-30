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
import { getCurrentScope, getScopeHierarchy, scopeKey } from './scope.js';

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

// Find or create a pattern for a goal class AT A SPECIFIC SCOPE LEVEL.
// Patterns are scoped — a company's "Content Writing" pattern is different
// from the global "Content Writing" pattern.
function getOrCreatePattern(goalClass, scopeLvl) {
  const sKey = scopeKey(scopeLvl);
  // Look for existing pattern with same goalClass + scope.
  for (const p of patterns.values()) {
    if (p.goalClass === goalClass && p.scopeKey === sKey) return p;
  }
  const newPattern = {
    id: crypto.randomUUID(),
    goalClass,
    scopeKey: sKey,
    scopeLevel: scopeLvl.level,
    scope: scopeLvl,
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
// The pattern is created/updated AT THE LEARNING OBJECT'S SCOPE.
// If the learning object has no scope, it defaults to the current scope.
export async function updatePatternFromLearning(learningObj) {
  const goalClass = classifyGoal(learningObj.goal);
  // Determine the scope level for this learning object.
  // Individual user's work creates individual-scoped patterns.
  // In production, the scope would come from the authenticated session.
  const scope = learningObj.scope || getCurrentScope();
  const hierarchy = getScopeHierarchy(scope);
  // Write to the most specific level available (individual if userId, else team, etc.)
  const writeLevel = hierarchy[0];
  const pattern = getOrCreatePattern(goalClass, writeLevel);

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
  if (learningObj.lessons) {
    const failures = extractSection(learningObj.lessons, 'WHAT TO DO DIFFERENTLY NEXT TIME');
    const corrections = extractSection(learningObj.lessons, 'WHAT WORKED');
    const calibrationNote = extractSection(learningObj.lessons, 'CONFIDENCE CALIBRATION NOTE');

    if (failures) {
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

  if (!pattern._outcomes) pattern._outcomes = [];
  pattern._outcomes.push(learningObj.outcome);
  const accepted = pattern._outcomes.filter(o => o === 'accepted').length;
  const total = pattern._outcomes.filter(o => o !== 'pending').length;
  pattern.acceptanceRate = total > 0 ? accepted / total : null;

  // Update confidence calibration.
  if (learningObj.predictedConfidence !== null) {
    const n = pattern.projectCount;
    if (!pattern.confidenceCalibration.predictedAvg) {
      pattern.confidenceCalibration.predictedAvg = learningObj.predictedConfidence;
    } else {
      pattern.confidenceCalibration.predictedAvg =
        Math.round((pattern.confidenceCalibration.predictedAvg * (n - 1) + learningObj.predictedConfidence) / n);
    }
  }
  pattern.confidenceCalibration.realizedAcceptanceRate = pattern.acceptanceRate;

  // Bump version and persist.
  pattern.version++;
  pattern.lastUpdated = new Date().toISOString();
  const { _outcomes, ...persistable } = pattern;
  await persist(persistable);

  // PROMOTION: after updating an individual pattern, check if we should
  // promote insights up to the team/department/company level.
  // This is how Organizational Playbooks emerge from individual work.
  await promotePatternIfNeeded(goalClass, scope, hierarchy);

  return pattern;
}

// PATTERN PROMOTION — the mechanism that creates Organizational Playbooks.
//
// When multiple individuals in the same team/department/company complete
// similar work, their individual patterns should aggregate into a
// higher-level pattern. This is how Sarah's + John's individual
// Content Writing patterns become a TEAM pattern that everyone on the
// platform team benefits from.
//
// Promotion rules (intentionally simple for now):
//   - When 2+ individual patterns exist for the same goal class in the
//     same team, promote to team level.
//   - When 2+ team patterns exist for the same department, promote to
//     department level.
//   - And so on up the hierarchy.
//
// The promoted pattern aggregates failures/corrections from all
// contributing patterns, weighted by occurrence count.
async function promotePatternIfNeeded(goalClass, scope, hierarchy) {
  // Find all patterns at each level for this goal class.
  for (let levelIdx = 1; levelIdx < hierarchy.length; levelIdx++) {
    const targetLevel = hierarchy[levelIdx];
    const targetKey = scopeKey(targetLevel);

    // Count patterns at the level BELOW this one (more specific).
    const childLevelIdx = levelIdx - 1;
    const childLevel = hierarchy[childLevelIdx];
    const childKey = scopeKey(childLevel);

    // Find all patterns at the child level for this goal class.
    // For individual → team promotion, children are all individual patterns
    // in the same team. We match by scopeKey prefix.
    const childPatterns = [];
    for (const p of patterns.values()) {
      if (p.goalClass !== goalClass) continue;
      if (p.scopeLevel !== childLevel.level) continue;
      // Check if the child pattern's scope is a child of the target level.
      // A child's scopeKey should start with the target's scope components.
      const targetParts = targetKey.split('|').filter(Boolean);
      const childParts = p.scopeKey.split('|').filter(Boolean);
      // All target parts must be present in child parts (child is more specific).
      const isChild = targetParts.every(tp => childParts.includes(tp));
      if (isChild && p.projectCount > 0) {
        childPatterns.push(p);
      }
    }

    // Promote if 2+ child patterns exist.
    if (childPatterns.length >= 2) {
      const promotedPattern = getOrCreatePattern(goalClass, targetLevel);

      // Aggregate failures from all children.
      const allFailures = new Map();
      for (const child of childPatterns) {
        for (const f of child.observedFailures) {
          const key = f.text.slice(0, 60);
          if (allFailures.has(key)) {
            allFailures.get(key).occurrences += (f.occurrences || 1);
          } else {
            allFailures.set(key, { text: f.text, occurrences: f.occurrences || 1 });
          }
        }
      }
      promotedPattern.observedFailures = Array.from(allFailures.values())
        .sort((a, b) => b.occurrences - a.occurrences)
        .slice(0, 10);

      // Aggregate corrections.
      const allCorrections = new Map();
      for (const child of childPatterns) {
        for (const c of child.successfulCorrections) {
          const key = c.text.slice(0, 60);
          if (allCorrections.has(key)) {
            allCorrections.get(key).occurrences += (c.occurrences || 1);
          } else {
            allCorrections.set(key, { text: c.text, occurrences: c.occurrences || 1 });
          }
        }
      }
      promotedPattern.successfulCorrections = Array.from(allCorrections.values())
        .sort((a, b) => b.occurrences - a.occurrences)
        .slice(0, 10);

      // Aggregate workflows.
      const workflowMap = new Map();
      for (const child of childPatterns) {
        for (const w of child.winningWorkflow) {
          if (workflowMap.has(w.team)) {
            const existing = workflowMap.get(w.team);
            existing.count += w.count;
            existing.acceptedCount += w.acceptedCount;
          } else {
            workflowMap.set(w.team, { ...w });
          }
        }
      }
      promotedPattern.winningWorkflow = Array.from(workflowMap.values())
        .sort((a, b) => b.acceptedCount - a.acceptedCount);

      // Aggregate project count and acceptance.
      promotedPattern.projectCount = childPatterns.reduce((sum, p) => sum + p.projectCount, 0);
      const totalAccepted = childPatterns.reduce((sum, p) => {
        const accepted = p._outcomes?.filter(o => o === 'accepted').length || 0;
        return sum + accepted;
      }, 0);
      const totalOutcomes = childPatterns.reduce((sum, p) => {
        const outcomes = p._outcomes?.filter(o => o !== 'pending').length || 0;
        return sum + outcomes;
      }, 0);
      promotedPattern.acceptanceRate = totalOutcomes > 0 ? totalAccepted / totalOutcomes : null;
      promotedPattern._outcomes = childPatterns.flatMap(p => p._outcomes || []);

      // Average confidence.
      const confidences = childPatterns
        .map(p => p.confidenceCalibration?.predictedAvg)
        .filter(c => c !== null && c !== undefined);
      if (confidences.length > 0) {
        promotedPattern.confidenceCalibration.predictedAvg =
          Math.round(confidences.reduce((a, b) => a + b, 0) / confidences.length);
      }
      promotedPattern.confidenceCalibration.realizedAcceptanceRate = promotedPattern.acceptanceRate;

      promotedPattern.version++;
      promotedPattern.lastUpdated = new Date().toISOString();
      promotedPattern.isPromoted = true;
      promotedPattern.sourcePatternIds = childPatterns.map(p => p.id);

      const { _outcomes, ...persistable } = promotedPattern;
      await persist(persistable);

      console.log(`[patterns] PROMOTED "${goalClass}" from ${childLevel.level} → ${targetLevel.level} (${childPatterns.length} patterns, ${promotedPattern.projectCount} total projects)`);
    }
  }
}

// Extract a section from the conductor's structured lessons output.
function extractSection(text, sectionName) {
  const regex = new RegExp(sectionName + ':?\\s*\\n([\\s\\S]*?)(?:\\n\\n[A-Z][A-Z ]+:|$)', 'i');
  const m = text.match(regex);
  return m ? m[1].trim() : '';
}

// Retrieve the best execution pattern for a new goal.
// CASCADES through the scope hierarchy:
//   individual → team → department → company → industry → global
//
// Returns ALL matching patterns, ordered from most specific to least.
// The conductor can then reference individual preferences that override
// company playbooks that override global laws.
//
// This is what makes Maestro work for both a solo founder (only global
// patterns) and a Fortune 500 company (all 6 levels populated).
export function retrievePattern(goal, scope = null) {
  const goalClass = classifyGoal(goal);
  const useScope = scope || getCurrentScope();
  const hierarchy = getScopeHierarchy(useScope);

  const results = [];
  for (const scopeLvl of hierarchy) {
    const sKey = scopeKey(scopeLvl);
    for (const p of patterns.values()) {
      if (p.goalClass === goalClass && p.scopeKey === sKey && p.projectCount > 0) {
        results.push(p);
        break; // one pattern per scope level
      }
    }
  }
  return results; // ordered: most specific first
}

// Format retrieved patterns (at multiple scope levels) as conductor context.
// Shows the conductor WHERE each piece of knowledge comes from.
export function formatPatternContext(patternsArr) {
  if (!patternsArr || patternsArr.length === 0) return '';

  const blocks = patternsArr.map((pattern, idx) => {
    const scopeLabel = pattern.scopeLevel === 'global' ? 'Global'
      : pattern.scopeLevel === 'industry' ? `Industry (${pattern.scope.industry})`
      : pattern.scopeLevel === 'company' ? `Company (${pattern.scope.organization})`
      : pattern.scopeLevel === 'department' ? `Department (${pattern.scope.department})`
      : pattern.scopeLevel === 'team' ? `Team (${pattern.scope.team})`
      : pattern.scopeLevel === 'individual' ? `Individual (${pattern.scope.userId})`
      : pattern.scopeLevel;

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
      `--- ${scopeLabel} Execution Pattern: ${pattern.goalClass} ---`,
      `Projects observed: ${pattern.projectCount}`,
      `Acceptance rate: ${pattern.acceptanceRate !== null ? Math.round(pattern.acceptanceRate * 100) + '%' : 'unknown'}`,
      '',
      `Proven workflows:`,
      workflowStr || '  (none yet)',
      '',
      `Known failure modes:`,
      failuresStr || '  (none yet)',
      '',
      `Successful corrections:`,
      correctionsStr || '  (none yet)',
    ];
    if (pattern.confidenceCalibration?.calibrationNote) {
      lines.push(`Calibration: ${pattern.confidenceCalibration.calibrationNote}`);
    }
    lines.push('---');
    return lines.join('\n');
  });

  return blocks.join('\n\n');
}

// Get stats for all patterns, grouped by scope level.
export function getPatternStats() {
  const all = Array.from(patterns.values());
  return all.map(p => ({
    goalClass: p.goalClass,
    scopeLevel: p.scopeLevel,
    scopeKey: p.scopeKey,
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

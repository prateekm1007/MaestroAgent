// policies.js — Maestro's Operating Policies & Execution Constitution.
//
// This is the GOVERNANCE LAYER above Execution Patterns.
//
// The 5-layer hierarchy:
//   1. Learning Object      — one execution
//   2. Execution Pattern    — a repeated workflow
//   3. Organizational Playbook — how Acme launches products (patterns at company scope)
//   4. Operating Policy     — what is mandatory (security review, legal review, etc.)
//   5. Execution Constitution — the company's immutable rules
//
// LAW PROMOTION:
//   When a pattern's "successful correction" is seen N times with high
//   acceptance, it promotes to an Operating Policy.
//   When a Policy is reinforced enough times (or violated dangerously),
//   it can promote to a Constitution Rule (immutable without approval).
//
// This is what makes Maestro learn not just WHAT WORKS, but
// HOW THE COMPANY GOVERNS ITSELF.
//
// Policy shape:
//   {
//     id,
//     rule,              // "Security review required before deployment"
//     scope,             // { level, organization, department, ... }
//     scopeKey,
//     category,          // 'security' | 'legal' | 'quality' | 'process' | 'accessibility' | 'custom'
//     enforcement,       // 'mandatory' | 'recommended' | 'optional'
//     evidenceRequired,  // what evidence must be produced to prove compliance
//     promotedFrom,      // pattern id this was promoted from (if applicable)
//     reinforcementCount,// how many times this rule has been reinforced
//     violationCount,    // how many times it was violated
//     createdAt,
//     lastReinforced,
//     status             // 'active' | 'proposed' | 'deprecated' | 'constitutional'
//   }
//
// Constitution Rule shape (same as Policy, but status='constitutional'
// and scope at company level — these are immutable without explicit approval).

import { promises as fs } from 'node:fs';
import path from 'node:path';
import { getCurrentScope, getScopeHierarchy, scopeKey } from './scope.js';

const POLICY_STORE_PATH = path.resolve('./operating-policies.jsonl');
const policies = new Map(); // id -> Policy

// Promotion thresholds — when a correction is seen this many times,
// it promotes to a Policy. When a Policy is reinforced this many times,
// it promotes to a Constitution Rule.
const POLICY_PROMOTION_THRESHOLD = 3;   // 3 occurrences → policy
const CONSTITUTION_PROMOTION_THRESHOLD = 10; // 10 reinforcements → constitutional

export async function initPolicyStore() {
  try {
    const data = await fs.readFile(POLICY_STORE_PATH, 'utf8');
    for (const line of data.split('\n').filter(Boolean)) {
      try {
        const obj = JSON.parse(line);
        policies.set(obj.id, obj);
      } catch {}
    }
    console.log(`[policies] loaded ${policies.size} operating policies from disk`);
  } catch (err) {
    if (err.code !== 'ENOENT') console.warn('[policies] failed to load store:', err.message);
  }
}

async function persist(policy) {
  try {
    await fs.appendFile(POLICY_STORE_PATH, JSON.stringify(policy) + '\n', 'utf8');
  } catch (err) {
    console.warn('[policies] failed to persist:', err.message);
  }
}

// Categorize a correction/failure text into a policy category.
function categorizeRule(text) {
  const t = text.toLowerCase();
  if (/security|vulnerab|threat|auth|encrypt|pci|compliance/.test(t)) return 'security';
  if (/legal|review|contract|liability|privacy|gdpr/.test(t)) return 'legal';
  if (/test|qa|quality|review|verify|validate/.test(t)) return 'quality';
  if (/accessib|a11y|wcag|screen reader/.test(t)) return 'accessibility';
  if (/deploy|release|rollback|staging|production/.test(t)) return 'process';
  if (/document|comment|readme|doc/.test(t)) return 'documentation';
  return 'custom';
}

// Determine the enforcement level based on how often the rule has been seen.
function determineEnforcement(reinforcementCount) {
  if (reinforcementCount >= CONSTITUTION_PROMOTION_THRESHOLD) return 'constitutional';
  if (reinforcementCount >= POLICY_PROMOTION_THRESHOLD) return 'mandatory';
  if (reinforcementCount >= 1) return 'recommended';
  return 'optional';
}

// Check if a correction from a pattern should be promoted to a Policy.
// Called after pattern update. If the pattern's correction has been seen
// N times, create or reinforce a Policy.
export async function checkForPolicyPromotion(pattern) {
  if (!pattern || !pattern.successfulCorrections) return [];

  const scope = pattern.scope || getCurrentScope();
  const hierarchy = getScopeHierarchy(scope);
  // Policies live at the SAME scope as the pattern that produced them.
  // A team pattern produces team policies. A company pattern produces
  // company policies.
  const policyScope = hierarchy.find(l => l.level === pattern.scopeLevel) || hierarchy[0];

  const promoted = [];

  for (const correction of pattern.successfulCorrections) {
    const occurrences = correction.occurrences || 1;
    if (occurrences < POLICY_PROMOTION_THRESHOLD) continue;

    // Check if a policy already exists for this correction at this scope.
    const sKey = scopeKey(policyScope);
    let existing = null;
    for (const p of policies.values()) {
      if (p.scopeKey === sKey && p.rule.slice(0, 60).toLowerCase() === correction.text.slice(0, 60).toLowerCase()) {
        existing = p;
        break;
      }
    }

    if (existing) {
      // Reinforce existing policy.
      existing.reinforcementCount = (existing.reinforcementCount || 0) + 1;
      existing.lastReinforced = new Date().toISOString();
      // Check for promotion to constitutional.
      if (existing.reinforcementCount >= CONSTITUTION_PROMOTION_THRESHOLD && existing.status !== 'constitutional') {
        existing.status = 'constitutional';
        existing.enforcement = 'constitutional';
        console.log(`[policies] PROMOTED to CONSTITUTIONAL: "${existing.rule.slice(0, 60)}..." at ${existing.scopeLevel} scope`);
      }
      const { ...persistable } = existing;
      await persist(persistable);
      promoted.push(existing);
    } else {
      // Create new policy.
      const category = categorizeRule(correction.text);
      const newPolicy = {
        id: crypto.randomUUID(),
        rule: correction.text,
        scope: policyScope,
        scopeKey: sKey,
        scopeLevel: policyScope.level,
        category,
        enforcement: determineEnforcement(occurrences),
        evidenceRequired: inferEvidenceRequired(correction.text, category),
        promotedFrom: pattern.id,
        reinforcementCount: occurrences,
        violationCount: 0,
        createdAt: new Date().toISOString(),
        lastReinforced: new Date().toISOString(),
        status: occurrences >= CONSTITUTION_PROMOTION_THRESHOLD ? 'constitutional' : 'active',
      };
      policies.set(newPolicy.id, newPolicy);
      await persist(newPolicy);
      console.log(`[policies] NEW POLICY [${category}] at ${newPolicy.scopeLevel} scope: "${newPolicy.rule.slice(0, 60)}..." (reinforced ${occurrences}×)`);
      promoted.push(newPolicy);
    }
  }

  return promoted;
}

// Infer what evidence must be produced to prove compliance with a rule.
function inferEvidenceRequired(ruleText, category) {
  const t = ruleText.toLowerCase();
  switch (category) {
    case 'security':
      return 'Threat model + security review sign-off';
    case 'legal':
      return 'Legal review approval';
    case 'quality':
      return 'Test results + QA sign-off';
    case 'accessibility':
      return 'WCAG compliance report';
    case 'process':
      return 'Deployment checklist + rollback plan';
    case 'documentation':
      return 'Updated documentation link';
    default:
      return 'Evidence of compliance';
  }
}

// Retrieve all active policies that apply to a given scope.
// Cascades through the hierarchy — a team inherits company policies.
export function retrievePolicies(scope = null) {
  const useScope = scope || getCurrentScope();
  const hierarchy = getScopeHierarchy(useScope);
  const applicable = [];

  for (const scopeLvl of hierarchy) {
    const sKey = scopeKey(scopeLvl);
    for (const p of policies.values()) {
      if (p.scopeKey === sKey && p.status !== 'deprecated') {
        applicable.push(p);
      }
    }
  }

  return applicable;
}

// Format policies as context for the conductor's examine phase.
// This tells the conductor what MANDATORY rules apply to this execution.
export function formatPolicyContext(policiesArr) {
  if (!policiesArr || policiesArr.length === 0) return '';

  const constitutional = policiesArr.filter(p => p.status === 'constitutional');
  const mandatory = policiesArr.filter(p => p.enforcement === 'mandatory' && p.status !== 'constitutional');
  const recommended = policiesArr.filter(p => p.enforcement === 'recommended');

  const lines = [];

  if (constitutional.length > 0) {
    lines.push('--- CONSTITUTIONAL RULES (immutable) ---');
    for (const p of constitutional) {
      lines.push(`  [${p.scopeLevel}] ${p.rule}`);
      if (p.evidenceRequired) lines.push(`    Evidence required: ${p.evidenceRequired}`);
    }
    lines.push('---');
  }

  if (mandatory.length > 0) {
    lines.push('--- MANDATORY POLICIES ---');
    for (const p of mandatory) {
      lines.push(`  [${p.scopeLevel}] ${p.rule}`);
      if (p.evidenceRequired) lines.push(`    Evidence required: ${p.evidenceRequired}`);
    }
    lines.push('---');
  }

  if (recommended.length > 0) {
    lines.push('--- RECOMMENDED PRACTICES ---');
    for (const p of recommended.slice(0, 3)) {
      lines.push(`  [${p.scopeLevel}] ${p.rule}`);
    }
    lines.push('---');
  }

  return lines.join('\n');
}

// Validate a plan against active policies.
// Returns { valid, violations, warnings }.
export function validatePlan(plan, scope = null) {
  const applicable = retrievePolicies(scope);
  const violations = [];
  const warnings = [];

  for (const policy of applicable) {
    if (policy.status === 'deprecated') continue;
    // Simple keyword-based check — does the plan address this policy?
    const planLower = (plan || '').toLowerCase();
    const ruleKeywords = policy.rule.toLowerCase()
      .split(/\s+/)
      .filter(w => w.length > 4 && !['should', 'must', 'always', 'never'].includes(w));
    const addressed = ruleKeywords.some(kw => planLower.includes(kw));

    if (!addressed) {
      if (policy.enforcement === 'constitutional' || policy.enforcement === 'mandatory') {
        violations.push({
          policy: policy.rule,
          scope: policy.scopeLevel,
          evidence: policy.evidenceRequired,
          severity: policy.enforcement,
        });
      } else if (policy.enforcement === 'recommended') {
        warnings.push({
          policy: policy.rule,
          scope: policy.scopeLevel,
        });
      }
    }
  }

  return {
    valid: violations.length === 0,
    violations,
    warnings,
    policyCount: applicable.length,
  };
}

// Get stats for all policies.
export function getPolicyStats() {
  const all = Array.from(policies.values());
  return {
    total: all.length,
    constitutional: all.filter(p => p.status === 'constitutional').length,
    mandatory: all.filter(p => p.enforcement === 'mandatory' && p.status !== 'constitutional').length,
    recommended: all.filter(p => p.enforcement === 'recommended').length,
    byScope: all.reduce((acc, p) => {
      acc[p.scopeLevel] = (acc[p.scopeLevel] || 0) + 1;
      return acc;
    }, {}),
    byCategory: all.reduce((acc, p) => {
      acc[p.category] = (acc[p.category] || 0) + 1;
      return acc;
    }, {}),
  };
}

// List all policies (for UI/debugging).
export function listPolicies() {
  return Array.from(policies.values()).map(p => ({
    id: p.id,
    rule: p.rule,
    scopeLevel: p.scopeLevel,
    scopeKey: p.scopeKey,
    category: p.category,
    enforcement: p.enforcement,
    status: p.status,
    reinforcementCount: p.reinforcementCount,
    evidenceRequired: p.evidenceRequired,
    lastReinforced: p.lastReinforced,
  }));
}

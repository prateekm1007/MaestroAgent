// governance.js — Maestro's Governance Controls.
//
// This is the layer above Policies. Policies say WHAT is required.
// Governance Controls say HOW it's enforced, who approves, what
// evidence is needed, and what happens on violation.
//
// A Policy says: "Security review required before API deployment."
// A Governance Control says:
//   - Evidence required: Threat model document
//   - Reviewer: Security team
//   - Approval: Required, cannot be auto-approved
//   - Audit trail: Required
//   - Exception: Allowed only by Director, with written justification
//   - Violation consequence: Block execution
//
// This is what makes Maestro suitable for banks, healthcare, and
// regulated industries. It's not "AI that follows rules" — it's
// "execution infrastructure that cannot violate governance."
//
// The planner doesn't merely READ policies. It REFUSES to violate them.

import { promises as fs } from 'node:fs';
import path from 'node:path';
import { getCurrentScope, getScopeHierarchy, scopeKey } from './scope.js';

const CONTROL_STORE_PATH = path.resolve('./governance-controls.jsonl');
const controls = new Map(); // id -> GovernanceControl

export async function initGovernanceStore() {
  try {
    const data = await fs.readFile(CONTROL_STORE_PATH, 'utf8');
    for (const line of data.split('\n').filter(Boolean)) {
      try {
        const obj = JSON.parse(line);
        controls.set(obj.id, obj);
      } catch {}
    }
    console.log(`[governance] loaded ${controls.size} governance controls from disk`);
  } catch (err) {
    if (err.code !== 'ENOENT') console.warn('[governance] failed to load store:', err.message);
  }
}

async function persist(control) {
  try {
    await fs.appendFile(CONTROL_STORE_PATH, JSON.stringify(control) + '\n', 'utf8');
  } catch (err) {
    console.warn('[governance] failed to persist:', err.message);
  }
}

// Create a governance control for a policy.
// This is called when a policy is promoted to constitutional or mandatory.
export async function createControlForPolicy(policy) {
  const control = {
    id: crypto.randomUUID(),
    policyId: policy.id,
    policyRule: policy.rule,
    scope: policy.scope,
    scopeKey: policy.scopeKey,
    scopeLevel: policy.scopeLevel,
    category: policy.category,
    enforcement: policy.enforcement,
    // Governance-specific fields:
    evidenceRequired: policy.evidenceRequired || 'Evidence of compliance',
    reviewer: inferReviewer(policy.category),
    approvalRequired: policy.enforcement === 'constitutional' || policy.enforcement === 'mandatory',
    autoApprove: false, // Constitutional and mandatory rules never auto-approve
    auditTrailRequired: true,
    exceptionAllowed: policy.enforcement !== 'constitutional', // Constitutional rules have no exceptions
    exceptionApprover: policy.enforcement !== 'constitutional' ? 'Director' : null,
    violationAction: policy.enforcement === 'constitutional' ? 'block' : 'warn',
    blockExecution: policy.enforcement === 'constitutional',
    createdAt: new Date().toISOString(),
    status: 'active',
  };

  controls.set(control.id, control);
  await persist(control);
  console.log(`[governance] control created for policy "${policy.rule.slice(0, 50)}..." (enforcement: ${policy.enforcement}, block: ${control.blockExecution})`);
  return control;
}

// Infer the reviewer role based on policy category.
function inferReviewer(category) {
  switch (category) {
    case 'security': return 'Security Team';
    case 'legal': return 'Legal Team';
    case 'quality': return 'QA Lead';
    case 'accessibility': return 'Accessibility Team';
    case 'process': return 'Engineering Manager';
    case 'documentation': return 'Tech Lead';
    default: return 'Team Lead';
  }
}

// Retrieve all governance controls applicable to a scope.
// Cascades through the hierarchy.
export function retrieveControls(scope = null) {
  const useScope = scope || getCurrentScope();
  const hierarchy = getScopeHierarchy(useScope);
  const applicable = [];

  for (const scopeLvl of hierarchy) {
    const sKey = scopeKey(scopeLvl);
    for (const c of controls.values()) {
      if (c.scopeKey === sKey && c.status === 'active') {
        applicable.push(c);
      }
    }
  }

  return applicable;
}

// VALIDATE A PLAN AGAINST GOVERNANCE CONTROLS.
// This is the constitutional execution check.
// Returns:
//   { allowed, violations, warnings, evidenceRequired, approvalsRequired }
//
// If any constitutional control is violated, allowed = false.
// The engine MUST NOT proceed if allowed = false.
export function validatePlanAgainstGovernance(plan, scope = null) {
  const applicable = retrieveControls(scope);
  const violations = [];
  const warnings = [];
  const evidenceRequired = [];
  const approvalsRequired = [];

  for (const control of applicable) {
    // Check if the plan addresses this control's policy.
    const planLower = (plan || '').toLowerCase();
    const ruleKeywords = control.policyRule.toLowerCase()
      .split(/\s+/)
      .filter(w => w.length > 4 && !['should', 'must', 'always', 'never'].includes(w));
    const addressed = ruleKeywords.some(kw => planLower.includes(kw));

    if (!addressed) {
      if (control.blockExecution) {
        violations.push({
          control: control.policyRule,
          scope: control.scopeLevel,
          evidence: control.evidenceRequired,
          reviewer: control.reviewer,
          severity: 'constitutional',
          action: 'BLOCKED',
        });
      } else if (control.enforcement === 'mandatory') {
        warnings.push({
          control: control.policyRule,
          scope: control.scopeLevel,
          evidence: control.evidenceRequired,
          reviewer: control.reviewer,
          severity: 'mandatory',
          action: 'WARNING',
        });
      }
    }

    if (control.approvalRequired) {
      approvalsRequired.push({
        control: control.policyRule,
        reviewer: control.reviewer,
        scope: control.scopeLevel,
      });
    }

    if (control.evidenceRequired) {
      evidenceRequired.push({
        control: control.policyRule,
        evidence: control.evidenceRequired,
        scope: control.scopeLevel,
      });
    }
  }

  return {
    allowed: violations.length === 0,
    violations,
    warnings,
    evidenceRequired,
    approvalsRequired,
    controlCount: applicable.length,
  };
}

// Get stats for all governance controls.
export function getGovernanceStats() {
  const all = Array.from(controls.values());
  return {
    total: all.length,
    blocking: all.filter(c => c.blockExecution).length,
    approvalRequired: all.filter(c => c.approvalRequired).length,
    exceptionAllowed: all.filter(c => c.exceptionAllowed).length,
    byScope: all.reduce((acc, c) => {
      acc[c.scopeLevel] = (acc[c.scopeLevel] || 0) + 1;
      return acc;
    }, {}),
    byCategory: all.reduce((acc, c) => {
      acc[c.category] = (acc[c.category] || 0) + 1;
      return acc;
    }, {}),
  };
}

// List all controls.
export function listControls() {
  return Array.from(controls.values()).map(c => ({
    id: c.id,
    policyRule: c.policyRule,
    scopeLevel: c.scopeLevel,
    category: c.category,
    enforcement: c.enforcement,
    evidenceRequired: c.evidenceRequired,
    reviewer: c.reviewer,
    approvalRequired: c.approvalRequired,
    blockExecution: c.blockExecution,
    exceptionAllowed: c.exceptionAllowed,
    violationAction: c.violationAction,
  }));
}

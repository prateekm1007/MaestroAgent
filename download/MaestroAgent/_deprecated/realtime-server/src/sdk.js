// sdk.js — Enterprise Operating Model SDK.
//
// This is how an enterprise DEFINES how they work:
//   - Organization hierarchy (divisions, departments, teams)
//   - Approval chains (who approves what, in what order)
//   - Governance policies (their specific rules, not generic ones)
//   - Workflow templates (their repeated execution patterns)
//   - Compliance mappings (which regulations apply to which work)
//   - Integration bindings (which tools connect to which workflows)
//
// The SDK takes a declarative operating model (YAML/JSON) and
// registers it with Maestro. From that point, every execution
// is governed by the enterprise's own operating model.
//
// This is the onboarding mechanism: an enterprise defines their
// operating model once, and Maestro enforces it forever.

import { promises as fs } from 'node:fs';
import path from 'node:path';
import { setCurrentScope, getScopeHierarchy, scopeKey } from './scope.js';
import { createControlForPolicy } from './policies.js';
import { recordOutcome } from './learning.js';

const MODEL_STORE_PATH = path.resolve('./operating-models.jsonl');
const models = new Map(); // orgId -> OperatingModel

export async function initSDKStore() {
  try {
    const data = await fs.readFile(MODEL_STORE_PATH, 'utf8');
    for (const line of data.split('\n').filter(Boolean)) {
      try {
        const obj = JSON.parse(line);
        models.set(obj.orgId, obj);
      } catch {}
    }
    console.log(`[sdk] loaded ${models.size} operating models from disk`);
  } catch (err) {
    if (err.code !== 'ENOENT') console.warn('[sdk] failed to load:', err.message);
  }
}

async function persist(model) {
  try { await fs.appendFile(MODEL_STORE_PATH, JSON.stringify(model) + '\n', 'utf8'); }
  catch (err) { console.warn('[sdk] persist failed:', err.message); }
}

// Register an enterprise operating model.
// This is the main SDK entry point.
//
// Example input:
// {
//   orgId: "acme-corp",
//   name: "Acme Corporation",
//   industry: "technology",
//   hierarchy: [
//     { division: "Engineering", departments: ["Platform", "Product", "Infrastructure"] },
//     { division: "Go-To-Market", departments: ["Sales", "Marketing", "Customer Success"] },
//   ],
//   approvalChains: [
//     {
//       name: "Standard Release",
//       steps: [
//         { reviewer: "Engineering Lead", role: "eng-lead", required: true },
//         { reviewer: "Security Team", role: "security", required: true, parallel: true },
//         { reviewer: "Legal", role: "legal", required: false, parallel: true },
//       ],
//       appliesTo: ["Product Build", "Code Implementation"],
//     },
//   ],
//   policies: [
//     {
//       rule: "Every customer-facing API requires security review",
//       enforcement: "mandatory",
//       category: "security",
//       evidenceRequired: "Security review sign-off",
//       scope: { level: "company" },
//     },
//   ],
//   workflowTemplates: [
//     {
//       name: "Product Feature Launch",
//       goalPattern: "launch|ship|release",
//       specialists: ["planner", "coder", "reviewer"],
//       requiredApprovals: ["Standard Release"],
//     },
//   ],
//   complianceMappings: [
//     { regulation: "SOC2", appliesTo: ["security", "process"], controls: ["CC1", "CC7"] },
//     { regulation: "GDPR", appliesTo: ["legal"], controls: ["Art.32"] },
//   ],
// }
export async function registerOperatingModel(modelDef) {
  const orgId = modelDef.orgId;
  if (!orgId) throw new Error('orgId is required');

  const model = {
    orgId,
    name: modelDef.name || orgId,
    industry: modelDef.industry || 'technology',
    hierarchy: modelDef.hierarchy || [],
    approvalChains: modelDef.approvalChains || [],
    policies: modelDef.policies || [],
    workflowTemplates: modelDef.workflowTemplates || [],
    complianceMappings: modelDef.complianceMappings || [],
    integrationBindings: modelDef.integrationBindings || [],
    registeredAt: new Date().toISOString(),
    version: 1,
    status: 'active',
  };

  // Persist the model.
  models.set(orgId, model);
  await persist(model);

  // Set the scope to this org so subsequent policy creation is scoped correctly.
  setCurrentScope({
    organization: orgId,
    industry: model.industry,
    department: null,
    team: null,
    userId: 'sdk-registrar',
  });

  // Register each policy as a governance control.
  // This makes the operating model EXECUTABLE — not just documented.
  const registeredPolicies = [];
  for (const policyDef of model.policies) {
    try {
      // Create the policy via the existing policy system.
      // We use a simplified internal creation path.
      const policy = {
        id: crypto.randomUUID(),
        rule: policyDef.rule,
        scope: { level: policyDef.scope?.level || 'company', organization: orgId, industry: model.industry },
        scopeKey: scopeKey({ level: policyDef.scope?.level || 'company', organization: orgId, industry: model.industry }),
        scopeLevel: policyDef.scope?.level || 'company',
        category: policyDef.category || 'custom',
        enforcement: policyDef.enforcement || 'recommended',
        evidenceRequired: policyDef.evidenceRequired || 'Evidence of compliance',
        promotedFrom: null,
        reinforcementCount: policyDef.enforcement === 'constitutional' ? 10 : 5,
        violationCount: 0,
        createdAt: new Date().toISOString(),
        lastReinforced: new Date().toISOString(),
        status: policyDef.enforcement === 'constitutional' ? 'constitutional' : 'active',
      };

      // Create governance control for mandatory/constitutional.
      if (policy.enforcement === 'mandatory' || policy.enforcement === 'constitutional') {
        await createControlForPolicy(policy);
      }
      registeredPolicies.push(policy);
    } catch (err) {
      console.warn(`[sdk] failed to register policy "${policyDef.rule.slice(0, 40)}...": ${err.message}`);
    }
  }

  console.log(`[sdk] registered operating model for "${model.name}" (${orgId}): ${model.hierarchy.length} divisions, ${model.approvalChains.length} approval chains, ${registeredPolicies.length} policies, ${model.workflowTemplates.length} workflow templates`);

  return {
    orgId,
    name: model.name,
    registeredPolicies: registeredPolicies.length,
    approvalChains: model.approvalChains.length,
    workflowTemplates: model.workflowTemplates.length,
    complianceMappings: model.complianceMappings.length,
    status: 'active',
    message: `Operating model registered. ${registeredPolicies.length} governance controls are now executable.`,
  };
}

// Retrieve an operating model.
export function getOperatingModel(orgId) {
  return models.get(orgId) || null;
}

// List all registered operating models.
export function listOperatingModels() {
  return Array.from(models.values()).map(m => ({
    orgId: m.orgId,
    name: m.name,
    industry: m.industry,
    divisions: m.hierarchy.length,
    approvalChains: m.approvalChains.length,
    policies: m.policies.length,
    workflowTemplates: m.workflowTemplates.length,
    complianceMappings: m.complianceMappings.length,
    registeredAt: m.registeredAt,
    status: m.status,
  }));
}

// Find a workflow template that matches a goal.
export function findWorkflowTemplate(orgId, goal) {
  const model = models.get(orgId);
  if (!model) return null;
  const g = goal.toLowerCase();
  for (const template of model.workflowTemplates) {
    if (template.goalPattern) {
      const patterns = template.goalPattern.split('|').map(p => p.trim());
      if (patterns.some(p => g.includes(p))) return template;
    }
  }
  return null;
}

// Get the approval chain for a goal class.
export function getApprovalChain(orgId, goalClass) {
  const model = models.get(orgId);
  if (!model) return null;
  for (const chain of model.approvalChains) {
    if (chain.appliesTo?.includes(goalClass)) return chain;
  }
  // Default to first chain.
  return model.approvalChains[0] || null;
}

// Get compliance mappings for a category.
export function getComplianceMappings(orgId, category) {
  const model = models.get(orgId);
  if (!model) return [];
  return model.complianceMappings.filter(m => m.appliesTo?.includes(category));
}

// Validate that an operating model is complete.
// Used by Design Partner Mode to guide onboarding.
export function validateOperatingModel(modelDef) {
  const issues = [];
  if (!modelDef.orgId) issues.push('orgId is required');
  if (!modelDef.name) issues.push('name is required');
  if (!modelDef.hierarchy || modelDef.hierarchy.length === 0) issues.push('at least one division is required');
  if (!modelDef.policies || modelDef.policies.length === 0) issues.push('at least one policy is recommended');
  if (!modelDef.approvalChains || modelDef.approvalChains.length === 0) issues.push('at least one approval chain is recommended');
  return {
    valid: issues.length === 0,
    issues,
    completeness: computeCompleteness(modelDef),
  };
}

function computeCompleteness(modelDef) {
  const checks = [
    { name: 'Organization defined', passed: !!modelDef.orgId },
    { name: 'Name provided', passed: !!modelDef.name },
    { name: 'Industry specified', passed: !!modelDef.industry },
    { name: 'Hierarchy defined', passed: (modelDef.hierarchy?.length || 0) > 0 },
    { name: 'Approval chains configured', passed: (modelDef.approvalChains?.length || 0) > 0 },
    { name: 'Policies defined', passed: (modelDef.policies?.length || 0) > 0 },
    { name: 'Workflow templates created', passed: (modelDef.workflowTemplates?.length || 0) > 0 },
    { name: 'Compliance mappings added', passed: (modelDef.complianceMappings?.length || 0) > 0 },
    { name: 'Integrations bound', passed: (modelDef.integrationBindings?.length || 0) > 0 },
  ];
  const passed = checks.filter(c => c.passed).length;
  return {
    percentage: Math.round((passed / checks.length) * 100),
    checks,
  };
}

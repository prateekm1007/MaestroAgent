// design-partner.js — Design Partner Mode.
//
// This is the enterprise onboarding framework. It guides an enterprise
// through defining their operating model, connecting integrations,
// running their first execution, and generating an ROI report.
//
// The onboarding flow:
//   1. Organization setup (name, industry, hierarchy)
//   2. Operating model definition (policies, approval chains)
//   3. Workflow templates (their repeated execution patterns)
//   4. Compliance mappings (SOC2, GDPR, HIPAA, etc.)
//   5. Integration bindings (Jira, GitHub, Slack, etc.)
//   6. First guided execution (proves the system works)
//   7. ROI report (proves the business value)
//
// Each design partner gets a guided onboarding experience that
// exercises every layer of the architecture.

import { promises as fs } from 'node:fs';
import path from 'node:path';
import { registerOperatingModel, validateOperatingModel, getOperatingModel } from './sdk.js';

const PARTNER_STORE_PATH = path.resolve('./design-partners.jsonl');
const partners = new Map(); // orgId -> DesignPartner

export async function initDesignPartnerStore() {
  try {
    const data = await fs.readFile(PARTNER_STORE_PATH, 'utf8');
    for (const line of data.split('\n').filter(Boolean)) {
      try {
        const obj = JSON.parse(line);
        partners.set(obj.orgId, obj);
      } catch {}
    }
    console.log(`[design-partner] loaded ${partners.size} design partners from disk`);
  } catch (err) {
    if (err.code !== 'ENOENT') console.warn('[design-partner] failed to load:', err.message);
  }
}

async function persist(partner) {
  try { await fs.appendFile(PARTNER_STORE_PATH, JSON.stringify(partner) + '\n', 'utf8'); }
  catch (err) { console.warn('[design-partner] persist failed:', err.message); }
}

// Start the onboarding flow for a new design partner.
export async function startOnboarding(orgDef) {
  const orgId = orgDef.orgId;
  if (!orgId) throw new Error('orgId is required');

  const partner = {
    orgId,
    name: orgDef.name || orgId,
    industry: orgDef.industry || 'technology',
    contactName: orgDef.contactName || '',
    contactEmail: orgDef.contactEmail || '',
    stage: 'organization_setup',
    stages: {
      organization_setup: { status: 'in_progress', startedAt: new Date().toISOString() },
      operating_model: { status: 'pending' },
      workflow_templates: { status: 'pending' },
      compliance_mappings: { status: 'pending' },
      integrations: { status: 'pending' },
      first_execution: { status: 'pending' },
      roi_report: { status: 'pending' },
    },
    operatingModel: null,
    firstRunId: null,
    roiReport: null,
    onboardedAt: null,
    createdAt: new Date().toISOString(),
  };

  partners.set(orgId, partner);
  await persist(partner);
  console.log(`[design-partner] onboarding started for "${partner.name}" (${orgId})`);
  return partner;
}

// Advance to the next onboarding stage.
export async function advanceStage(orgId, stageData = {}) {
  const partner = partners.get(orgId);
  if (!partner) throw new Error(`design partner ${orgId} not found`);

  const stageOrder = [
    'organization_setup',
    'operating_model',
    'workflow_templates',
    'compliance_mappings',
    'integrations',
    'first_execution',
    'roi_report',
  ];

  const currentIdx = stageOrder.indexOf(partner.stage);
  const currentStage = partner.stage;

  // Mark current stage as completed.
  partner.stages[currentStage].status = 'completed';
  partner.stages[currentStage].completedAt = new Date().toISOString();

  // Process stage-specific data.
  if (currentStage === 'operating_model' && stageData.model) {
    // Register the operating model via the SDK.
    const result = await registerOperatingModel(stageData.model);
    partner.operatingModel = result;
  }

  if (currentStage === 'first_execution' && stageData.runId) {
    partner.firstRunId = stageData.runId;
  }

  // Advance to next stage.
  if (currentIdx < stageOrder.length - 1) {
    const nextStage = stageOrder[currentIdx + 1];
    partner.stage = nextStage;
    partner.stages[nextStage].status = 'in_progress';
    partner.stages[nextStage].startedAt = new Date().toISOString();
  } else {
    // All stages complete.
    partner.stage = 'complete';
    partner.onboardedAt = new Date().toISOString();
  }

  await persist(partner);
  return partner;
}

// Get the current onboarding status.
export function getOnboardingStatus(orgId) {
  const partner = partners.get(orgId);
  if (!partner) return null;

  const stages = Object.entries(partner.stages).map(([name, data]) => ({
    name,
    status: data.status,
    ...(data.startedAt ? { startedAt: data.startedAt } : {}),
    ...(data.completedAt ? { completedAt: data.completedAt } : {}),
  }));

  const completed = stages.filter(s => s.status === 'completed').length;
  const total = stages.length;

  return {
    orgId: partner.orgId,
    name: partner.name,
    currentStage: partner.stage,
    progress: Math.round((completed / total) * 100),
    completedStages: completed,
    totalStages: total,
    stages,
    onboarded: partner.stage === 'complete',
    onboardedAt: partner.onboardedAt,
  };
}

// Generate a welcome guide for a design partner.
// This tells them exactly what to do at each stage.
export function getOnboardingGuide(orgId) {
  const partner = partners.get(orgId);
  if (!partner) return null;

  const guides = {
    organization_setup: {
      title: 'Step 1: Define Your Organization',
      description: 'Tell Maestro about your company structure — divisions, departments, and teams.',
      actions: [
        'Provide your organization name and industry',
        'Define your division structure (e.g. Engineering, Go-To-Market, Operations)',
        'List departments within each division',
        'Identify your primary contact for this onboarding',
      ],
      api: 'POST /api/sdk/operating-model with hierarchy field',
    },
    operating_model: {
      title: 'Step 2: Define Your Operating Model',
      description: 'Specify the governance policies and approval chains that Maestro should enforce.',
      actions: [
        'List your mandatory policies (e.g. "Security review required before deployment")',
        'Define approval chains (who approves what, in what order)',
        'Specify which policies are constitutional (immutable)',
        'Set evidence requirements for each policy',
      ],
      api: 'POST /api/sdk/operating-model with policies and approvalChains fields',
    },
    workflow_templates: {
      title: 'Step 3: Define Your Workflow Templates',
      description: 'Map your repeated execution patterns so Maestro can recognize and optimize them.',
      actions: [
        'Identify your top 3-5 repeated workflows (e.g. "Product Feature Launch")',
        'For each, specify which specialists are needed',
        'Specify which approval chains apply to each workflow',
        'Define goal patterns that trigger each template',
      ],
      api: 'POST /api/sdk/operating-model with workflowTemplates field',
    },
    compliance_mappings: {
      title: 'Step 4: Map Compliance Requirements',
      description: 'Connect your policies to regulatory frameworks (SOC2, GDPR, HIPAA, etc.).',
      actions: [
        'List applicable regulations for your industry',
        'Map each regulation to relevant policy categories',
        'Specify which controls apply (e.g. SOC2 CC1, CC7)',
        'Define evidence requirements for audit purposes',
      ],
      api: 'POST /api/sdk/operating-model with complianceMappings field',
    },
    integrations: {
      title: 'Step 5: Connect Your Tools',
      description: 'Bind Maestro to the tools your teams already use.',
      actions: [
        'Connect Jira (for issue tracking and project management)',
        'Connect GitHub (for code execution and PR reviews)',
        'Connect Slack (for notifications and approvals)',
        'Connect Confluence (for documentation)',
        'Connect ServiceNow (for IT service management)',
      ],
      api: 'POST /api/integrations/:provider/connect',
    },
    first_execution: {
      title: 'Step 6: Run Your First Execution',
      description: 'Complete a real workflow through Maestro to verify the system works.',
      actions: [
        'Choose a real goal your team needs to accomplish',
        'Submit it via the Maestro interface',
        'Watch the conductor, specialists, and governance in action',
        'Review the execution receipt and evidence',
      ],
      api: 'POST /api/runs with a real goal',
    },
    roi_report: {
      title: 'Step 7: Review Your ROI Report',
      description: 'See the measurable impact Maestro has on your execution.',
      actions: [
        'Review cycle time, rework rate, and compliance score',
        'Compare Before/After metrics',
        'Identify bottlenecks (approval latency, rework)',
        'Share the report with stakeholders',
      ],
      api: 'GET /api/roi-report',
    },
  };

  return {
    orgId: partner.orgId,
    name: partner.name,
    currentStage: partner.stage,
    guide: guides[partner.stage] || null,
    nextSteps: partner.stage === 'complete'
      ? 'Onboarding complete. Maestro is now your execution operating model.'
      : `Complete the current stage, then call POST /api/design-partner/${orgId}/advance`,
  };
}

// List all design partners.
export function listDesignPartners() {
  return Array.from(partners.values()).map(p => ({
    orgId: p.orgId,
    name: p.name,
    industry: p.industry,
    stage: p.stage,
    progress: Math.round(
      (Object.values(p.stages).filter(s => s.status === 'completed').length /
        Object.keys(p.stages).length) * 100
    ),
    onboarded: p.stage === 'complete',
    createdAt: p.createdAt,
    onboardedAt: p.onboardedAt,
  }));
}

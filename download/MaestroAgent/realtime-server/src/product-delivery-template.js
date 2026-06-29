// product-delivery-template.js — The Product Delivery Operating Model.
//
// This is THE WEDGE. Not "Enterprise AI" — Product Delivery.
//
// "We reduce software delivery cycle time while maintaining governance."
//
// This template pre-configures Maestro for software product teams:
//   - Org hierarchy tailored to product/engineering teams
//   - Approval chains for feature releases
//   - Governance policies for security, accessibility, quality
//   - Workflow templates for common product development tasks
//   - Compliance mappings (SOC2, accessibility standards)
//
// An enterprise can adopt this template in one call, then customize.
// This is how Maestro owns Product Development as a category.

export const PRODUCT_DELIVERY_TEMPLATE = {
  templateId: 'product-delivery',
  name: 'Product Delivery Operating Model',
  description: 'Pre-configured for software product teams. Reduce delivery cycle time while maintaining governance.',
  industry: 'technology',

  hierarchy: [
    {
      division: 'Engineering',
      departments: ['Platform', 'Product Engineering', 'Infrastructure', 'Security'],
    },
    {
      division: 'Product',
      departments: ['Product Management', 'Design', 'Research'],
    },
    {
      division: 'Operations',
      departments: ['DevOps', 'QA', 'Release Management'],
    },
  ],

  approvalChains: [
    {
      name: 'Standard Feature Release',
      description: 'Standard approval chain for new product features',
      steps: [
        { reviewer: 'Engineering Lead', role: 'eng-lead', required: true, sla: '4h' },
        { reviewer: 'Security Team', role: 'security', required: true, parallel: true, sla: '8h' },
        { reviewer: 'QA Lead', role: 'qa-lead', required: true, parallel: true, sla: '4h' },
        { reviewer: 'Product Manager', role: 'pm', required: true, sla: '4h' },
      ],
      appliesTo: ['Product Build', 'Code Implementation'],
    },
    {
      name: 'Customer-Facing Change',
      description: 'Additional approvals for customer-facing changes',
      steps: [
        { reviewer: 'Engineering Lead', role: 'eng-lead', required: true, sla: '4h' },
        { reviewer: 'Security Team', role: 'security', required: true, parallel: true, sla: '8h' },
        { reviewer: 'Accessibility Reviewer', role: 'a11y', required: true, parallel: true, sla: '8h' },
        { reviewer: 'Legal', role: 'legal', required: false, parallel: true, sla: '24h' },
        { reviewer: 'Product Manager', role: 'pm', required: true, sla: '4h' },
      ],
      appliesTo: ['Product Build'],
    },
    {
      name: 'Infrastructure Change',
      description: 'Approval chain for infrastructure and deployment changes',
      steps: [
        { reviewer: 'Infrastructure Lead', role: 'infra-lead', required: true, sla: '4h' },
        { reviewer: 'Security Team', role: 'security', required: true, sla: '8h' },
        { reviewer: 'DevOps', role: 'devops', required: true, sla: '4h' },
      ],
      appliesTo: ['Product Build', 'Code Implementation'],
    },
  ],

  policies: [
    {
      rule: 'Every customer-facing feature requires accessibility review before deployment',
      enforcement: 'constitutional',
      category: 'accessibility',
      evidenceRequired: 'WCAG 2.1 AA compliance report',
      scope: { level: 'company' },
    },
    {
      rule: 'Security review required before any API deployment',
      enforcement: 'mandatory',
      category: 'security',
      evidenceRequired: 'Threat model + security review sign-off',
      scope: { level: 'department', department: 'Engineering' },
    },
    {
      rule: 'All code changes require at least two reviewer approvals',
      enforcement: 'mandatory',
      category: 'quality',
      evidenceRequired: 'PR approval count >= 2',
      scope: { level: 'department', department: 'Engineering' },
    },
    {
      rule: 'Automated tests must pass before merge to main',
      enforcement: 'constitutional',
      category: 'quality',
      evidenceRequired: 'CI pipeline green status',
      scope: { level: 'department', department: 'Engineering' },
    },
    {
      rule: 'Design review required before implementing new UI components',
      enforcement: 'recommended',
      category: 'process',
      evidenceRequired: 'Design review sign-off',
      scope: { level: 'team', team: 'Product Engineering' },
    },
    {
      rule: 'Documentation must be updated for any API change',
      enforcement: 'mandatory',
      category: 'documentation',
      evidenceRequired: 'Updated API documentation link',
      scope: { level: 'department', department: 'Engineering' },
    },
    {
      rule: 'Rollback plan required for all production deployments',
      enforcement: 'constitutional',
      category: 'process',
      evidenceRequired: 'Rollback procedure documented',
      scope: { level: 'company' },
    },
  ],

  workflowTemplates: [
    {
      name: 'New Feature Development',
      goalPattern: 'build|implement|create|add|develop',
      specialists: ['planner', 'coder', 'reviewer'],
      requiredApprovals: ['Standard Feature Release'],
      estimatedCycleTime: '3-5 days',
    },
    {
      name: 'Bug Fix',
      goalPattern: 'fix|bug|issue|broken|error',
      specialists: ['coder', 'reviewer'],
      requiredApprovals: ['Standard Feature Release'],
      estimatedCycleTime: '1-2 days',
    },
    {
      name: 'API Design',
      goalPattern: 'api|endpoint|service|integration',
      specialists: ['planner', 'coder', 'reviewer'],
      requiredApprovals: ['Standard Feature Release'],
      estimatedCycleTime: '2-4 days',
    },
    {
      name: 'Product Launch',
      goalPattern: 'launch|ship|release|deploy',
      specialists: ['planner', 'coder', 'reviewer'],
      requiredApprovals: ['Customer-Facing Change'],
      estimatedCycleTime: '5-10 days',
    },
    {
      name: 'Infrastructure Update',
      goalPattern: 'infrastructure|deploy|migrate|configure',
      specialists: ['planner', 'coder', 'reviewer'],
      requiredApprovals: ['Infrastructure Change'],
      estimatedCycleTime: '2-5 days',
    },
  ],

  complianceMappings: [
    {
      regulation: 'SOC 2 Type II',
      appliesTo: ['security', 'process', 'quality'],
      controls: ['CC1 (Control Environment)', 'CC7 (System Operations)', 'CC8 (Change Management)'],
    },
    {
      regulation: 'WCAG 2.1 AA',
      appliesTo: ['accessibility'],
      controls: ['Perceivable', 'Operable', 'Understandable', 'Robust'],
    },
    {
      regulation: 'OWASP Top 10',
      appliesTo: ['security'],
      controls: ['A01-A10'],
    },
  ],

  integrationBindings: [
    { provider: 'jira', config: { syncIssues: true, autoCreateExecutions: true } },
    { provider: 'github', config: { reviewPRs: true, triggerOnPush: false } },
    { provider: 'slack', config: { approvalChannel: '#approvals', notifyChannel: '#engineering' } },
    { provider: 'confluence', config: { autoDocument: true, attachEvidence: true } },
  ],
};

// Get the template.
export function getProductDeliveryTemplate() {
  return PRODUCT_DELIVERY_TEMPLATE;
}

// Get a summary of the template for display.
export function getTemplateSummary() {
  const t = PRODUCT_DELIVERY_TEMPLATE;
  return {
    templateId: t.templateId,
    name: t.name,
    description: t.description,
    divisions: t.hierarchy.length,
    departments: t.hierarchy.reduce((sum, d) => sum + d.departments.length, 0),
    approvalChains: t.approvalChains.length,
    policies: t.policies.length,
    constitutionalRules: t.policies.filter(p => p.enforcement === 'constitutional').length,
    workflowTemplates: t.workflowTemplates.length,
    complianceMappings: t.complianceMappings.length,
    integrations: t.integrationBindings.length,
    promise: 'Reduce software delivery cycle time while maintaining governance.',
  };
}

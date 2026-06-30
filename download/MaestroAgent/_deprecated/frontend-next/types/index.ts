// types/index.ts — Shared TypeScript types for the Maestro frontend.

export interface AuthUser {
  id: string;
  email: string;
  name: string | null;
  role: 'org_admin' | 'dept_lead' | 'org_member' | 'org_viewer';
  department: string | null;
  team: string | null;
  org_id: string;
  org_name: string;
  org_slug: string;
  permissions: string[];
  auth_method: 'jwt' | 'api_key' | 'sso';
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  token_type: 'Bearer';
}

export interface Run {
  id: string;
  goal: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'blocked';
  team?: {
    title: string;
    agents: string[];
  };
  avg_confidence?: number;
  duration_ms?: number;
  started_at: string;
  ended_at?: string;
  error?: string;
  scope?: Scope;
}

export interface Scope {
  organization?: string;
  industry?: string;
  department?: string;
  team?: string;
  userId?: string;
}

export interface Artifact {
  id: string;
  run_id: string;
  agent_id: string;
  agent_name: string;
  filename: string;
  bytes: number;
  confidence: number | null;
  is_final: boolean;
  is_debate_resolution?: boolean;
  preview?: string;
  created_at: string;
}

export interface EventPayload {
  [key: string]: unknown;
}

export interface RunEvent {
  type: string;
  run_id: string;
  ts: string;
  event_id: string;
  payload: EventPayload;
}

export interface ExecutionReceipt {
  receiptId: string;
  runId: string;
  orgId: string;
  goal: string;
  goalClass?: string;
  scope?: Scope;
  plan?: Record<string, unknown>;
  policiesApplied?: PolicyApplied[];
  patternsUsed?: PatternUsed[];
  evidence?: EvidenceItem[];
  approvals?: Approval[];
  exceptions?: Exception[];
  confidence?: { predicted?: number; actual?: string };
  outcome?: { result: string; notes?: string };
  execution?: {
    durationMs?: number;
    artifactCount?: number;
    artifacts?: { filename: string; agent: string; bytes: number }[];
  };
  receiptHash: string;
  createdAt: string;
}

export interface PolicyApplied {
  policyId?: string;
  rule: string;
  enforcement: string;
  status?: string;
  scopeLevel?: string;
}

export interface PatternUsed {
  goalClass: string;
  scopeLevel: string;
  version: number;
  projectCount: number;
}

export interface EvidenceItem {
  id: string;
  type: string;
  description: string;
  reviewer?: string;
  timestamp: string;
}

export interface Approval {
  required: boolean;
  granted: boolean;
  reviewer: string;
  control: string;
  timestamp: string | null;
}

export interface Exception {
  policyId: string;
  reason: string;
  approvedBy: string | null;
}

export interface Metrics {
  headline: {
    cycleTimeHours: number;
    reworkRate: number;
    knowledgeReuseRate: number;
    complianceScore: number;
    hoursSaved: number;
    violationsPrevented: number;
    auditReadiness: number;
    acceptanceRate: number;
  };
  operational: {
    totalExecutions: number;
    totalArtifacts: number;
    totalEvidence: number;
    pendingApprovals: number;
    totalApprovals: number;
    approvalRate: number;
    blockedExecutions: number;
  };
  knowledge: {
    learningObjects: number;
    acceptedProjects: number;
    patterns: number;
    policies: number;
    constitutionalPolicies: number;
    governanceControls: number;
    blockingControls: number;
  };
}

export interface Integration {
  id: string;
  providerId: string;
  providerName: string;
  status: 'connected' | 'disconnected';
  capabilities: string[];
  connectedAt: string;
  lastSyncAt?: string;
  eventsReceived: number;
  eventsSent: number;
}

export interface OrgMember {
  id: string;
  email: string;
  name: string;
  role: string;
  department?: string;
  team?: string;
  joinedAt: string;
  lastLoginAt?: string;
}

export interface AuditLogEntry {
  id: string;
  action: string;
  resourceType?: string;
  resourceId?: string;
  metadata?: Record<string, unknown>;
  success: boolean;
  errorMessage?: string;
  ipAddress?: string;
  ts: string;
  userEmail?: string;
  userName?: string;
}

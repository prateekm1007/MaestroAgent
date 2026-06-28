// Maestro v6 — Core Domain Types
// Every type maps to the 5-layer stack.

// ============================================================
// LAYER 1: SIGNALS
// ============================================================

export type SignalType =
  | 'GITHUB' | 'JIRA' | 'SLACK' | 'CONFLUENCE' | 'FIGMA'
  | 'GOOGLE' | 'LINKEDIN' | 'TWITTER' | 'NEWS';

export interface Signal {
  id: string;
  sourceId: string;
  orgId: string;
  externalId: string;
  type: string; // "ticket.created", "pr.merged", etc.
  timestamp: string;
  actor: string;
  payload: Record<string, unknown>;
  hash: string;
}

export interface SignalSource {
  id: string;
  type: SignalType;
  name: string;
  scopes: string[];
  connectedAt: string;
  lastSyncAt: string | null;
  syncStatus: 'IDLE' | 'SYNCING' | 'ERROR' | 'RATE_LIMITED';
}

// ============================================================
// LAYER 2: ORGANIZATIONAL EXECUTION MODEL (OEM)
// ============================================================

export type EntityType = 'PERSON' | 'TEAM' | 'PROJECT' | 'SYSTEM' | 'CUSTOMER' | 'REGION';
export type RelationType = 'REPORTS_TO' | 'COLLABORATES_WITH' | 'REVIEWS' | 'DEPENDS_ON' | 'INFLUENCES';
export type LawStatus = 'INFERENCE_PENDING' | 'VALIDATED' | 'STRESSED' | 'INVALIDATED' | 'UNKNOWN_TO_LEADERSHIP';

export interface OrgEntity {
  id: string;
  orgId: string;
  type: EntityType;
  name: string;
  externalId?: string;
  attributes: Record<string, unknown>;
  influenceScore: number;
  isActive: boolean;
  linkedinUrl?: string;
  twitterHandle?: string;
  newsMentions: number;
  lastEnrichedAt?: string;
}

export interface OrgRelation {
  id: string;
  fromId: string;
  toId: string;
  type: RelationType;
  weight: number;
  evidence: Record<string, unknown>[];
}

export interface OrgLaw {
  id: string;
  orgId: string;
  code: string; // "L-0007"
  statement: string;
  confidence: number; // 0..1
  evidenceCount: number;
  counterExamples: number;
  knownToLeadership: boolean;
  status: LawStatus;
  lastVerifiedAt?: string;
  driftDetectedAt?: string;
  evidence: EvidenceArtifact[];
}

export interface EvidenceArtifact {
  source: string; // "jira:EMEA-1247", "slack:C-1247"
  timestamp: string;
  description: string;
  supportsOrRefutes: 'SUPPORTS' | 'REFUTES';
}

export interface OrgCapability {
  id: string;
  orgId: string;
  name: string;
  unit: string;
  currentValue: number;
  targetValue?: number;
  history: { timestamp: string; value: number }[];
}

// ============================================================
// LAYER 3: DECISION ENGINE
// ============================================================

export type DecisionStatus =
  | 'DRAFT' | 'PROPOSED' | 'IN_DEBATE' | 'APPROVED' | 'REJECTED' | 'DEFERRED' | 'REOPENED';
export type VerificationResult = 'PENDING' | 'HIT' | 'MISS';

export interface Decision {
  id: string;
  orgId: string;
  title: string;
  description: string;
  status: DecisionStatus;
  decisionQuestion: string; // Every screen answers one
  predictedState: PredictedState;
  recommendation: string;
  confidence: number;
  proposerId: string;
  stakeholders: StakeholderPosition[];
  linkedLawIds: string[];
  simulatorConfig: SimulatorConfig;
  simulatorOutputs: SimulatorOutputs;
  approvedAt?: string;
  approvedBy?: string;
  verifyDate?: string; // 90 days from approval
  verifiedAt?: string;
  verificationResult?: VerificationResult;
  meetingId?: string;
  createdAt: string;
  updatedAt: string;
}

export interface StakeholderPosition {
  entityId: string;
  name: string;
  role: string;
  position: 'APPROVE' | 'DISSENT' | 'DEFER' | 'NO_POSITION';
  reasoning?: string;
}

export interface PredictedState {
  horizon: number; // days, default 90
  leadingIndicators: { name: string; direction: 'UP' | 'DOWN' | 'WARNING'; source: string }[];
  capabilityDeltas: { capability: string; delta: number; unit: string }[];
  risks: { description: string; probability: number; impact: number; source?: string }[];
}

export interface SimulatorConfig {
  emea: number;
  apac: number;
  na: number;
  // Generic key-value for non-hiring decisions
  parameters: Record<string, number>;
}

export interface SimulatorOutputs {
  emeaCapacity: number;
  apacSupportRatio: string;
  p1ClusterProbability: number;
  attritionRisk: number;
  annualizedCost: number;
  confidence: number;
  confidenceNote: string;
}

export interface Prediction {
  id: string;
  orgId: string;
  statement: string;
  confidence: number;
  madeAt: string;
  verifyDate: string;
  verifiedAt?: string;
  result: VerificationResult;
  bucket: number; // floor(confidence * 10)
  decisionId?: string;
  lawId?: string;
  meetingId?: string;
}

export type DebateStatus = 'OPEN' | 'DEFERRED' | 'RESOLVED' | 'ARCHIVED';

export interface Debate {
  id: string;
  orgId: string;
  title: string;
  thesis: string;
  antithesis: string;
  structuralRead?: string;
  status: DebateStatus;
  thesisSupporters: StakeholderPosition[];
  antithesisSupporters: StakeholderPosition[];
  evidence: EvidenceArtifact[];
  linkedLawIds: string[];
  rulingDecisionId?: string;
  rulingAt?: string;
  precedentNote?: string;
  createdAt: string;
  updatedAt: string;
}

// ============================================================
// LAYER 4: EXECUTIVE COGNITION (Meeting Intelligence)
// ============================================================

export type MeetingStatus = 'SCHEDULED' | 'ACTIVE' | 'ENDED' | 'CANCELLED';
export type SynthesisStatus = 'PENDING' | 'PROCESSING' | 'COMPLETE' | 'FAILED';

export interface Meeting {
  id: string;
  orgId: string;
  title: string;
  startedAt: string;
  endedAt?: string;
  status: MeetingStatus;
  participants: MeetingParticipant[];
  consentLoggedAt?: string;
  transcript: TranscriptLine[];
  synthesisStatus: SynthesisStatus;
  synthesisLoggedAt?: string;
}

export interface MeetingParticipant {
  entityId: string;
  name: string;
  role: string;
  consentedAt?: string;
  consentMethod: 'EXPLICIT' | 'ORG_POLICY';
  isExternal: boolean;
  dossier?: ParticipantDossier;
}

export interface ParticipantDossier {
  linkedin?: { summary: string; url?: string; lastHarvestedAt: string };
  twitter?: { summary: string; handle?: string; lastHarvestedAt: string };
  news?: { summary: string; lastHarvestedAt: string; mentionCount: number };
  internal: { decisionsLogged: number; debatesRuled: number; influenceScore: number; alignmentPatterns?: string };
}

export interface TranscriptLine {
  ts: string; // "09:14"
  speakerId: string;
  speakerName: string;
  text: string;
  highlights: { text: string; type: 'TERM' | 'OBJECTION' }[];
}

export interface ActionItem {
  id: string;
  orgId: string;
  meetingId: string;
  text: string;
  assigneeId?: string;
  assigneeName?: string;
  dueDate?: string;
  source: string; // "transcript:09:18"
  destination?: 'JIRA' | 'CALENDAR' | 'CONFLUENCE' | 'EMAIL' | 'SLACK';
  externalId?: string;
  status: 'OPEN' | 'COMPLETED' | 'CANCELLED';
  completedAt?: string;
}

// ============================================================
// LAYER 5: BELIEF LAYER
// ============================================================

export interface CalibrationEntry {
  id: string;
  orgId: string;
  predictionId: string;
  predictedConfidence: number;
  bucket: number; // 0..9
  actualOutcome: VerificationResult;
  verifiedAt: string;
}

export interface SurpriseHitRate {
  orgId: string;
  date: string;
  shr30d: number;
  totalPredictions: number;
  hits: number;
  misses: number;
  withinBand: boolean; // 0.80 ≤ SHR ≤ 0.88
}

// ============================================================
// SHARED
// ============================================================

export interface ApiError {
  error: string;
  code: string;
  details?: unknown;
}

export interface PaginatedResponse<T> {
  data: T[];
  pagination: { cursor?: string; hasMore: boolean };
}

// Decision Question — every screen must declare one (v6 design rule)
export interface DecisionQuestion {
  surface: string;
  question: string;
}

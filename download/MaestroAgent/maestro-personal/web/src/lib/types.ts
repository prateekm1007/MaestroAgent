// MaestroAgent types — commitment intelligence data model

export type Confidence = number // 0.0 - 1.0

export type CommitmentState = 'active' | 'at_risk' | 'completed' | 'cancelled'

export type Owner = 'user' | 'other' | 'unknown'

export type Importance = 'high' | 'medium' | 'low'

export interface Commitment {
  id: string
  entity: string
  text: string
  dueDate: string // ISO
  state: CommitmentState
  confidence: Confidence
  importance: Importance
  isBlocking: boolean
  owner: Owner
  source: SignalSource
  createdAt: string
}

export interface SignalSource {
  type: 'email' | 'calendar' | 'slack' | 'manual'
  snippet: string
  timestamp: string
  sender?: string
}

export interface Evidence {
  signalId: string
  source: SignalSource
  text: string
  confidence: Confidence
}

export type WhisperType = 'at_risk' | 'preparation' | 'opportunity' | 'quiet'

export interface Whisper {
  id: string
  type: WhisperType
  title: string
  context: string
  probability?: number // 0-100, ONLY shown when probabilityBasis exists
  probabilityBasis?: string // factual basis for the probability (like weather: "6 days since last response, average is 2 days")
  suggestedActions: WhisperAction[]
  entity?: string
  createdAt: string
}

export interface ChangeItem {
  type: 'new' | 'transition' | 'deadline' | 'completion'
  text: string
  entity: string
  timeAgo: string
}

export interface WhisperAction {
  label: string
  action: 'send_followup' | 'reschedule' | 'review' | 'dismiss' | 'view_relationship'
}

export interface AskAnswer {
  query: string
  answer: string
  confidence: Confidence
  evidence: Evidence[]
  reasoning: string[]
  relatedCommitments: { entity: string; text: string; dueDate: string; owner: Owner }[]
}

export type LayoutMode = 'dominant' | 'prominent' | 'present' | 'quiet' | 'empty'

export type ViewTab = 'today' | 'ask' | 'commitments' | 'whisper' | 'more'

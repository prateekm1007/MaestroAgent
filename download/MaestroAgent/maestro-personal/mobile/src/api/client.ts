/**
 * API client for Maestro Personal mobile app.
 * Production-grade with auth, error handling, and all endpoints.
 */

const API_URL = (process.env.EXPO_PUBLIC_API_URL as string) || 'http://localhost:8766';

// ── Types ────────────────────────────────────────────────────────

export interface LoginResult {
  token: string;
  user_email: string;
  message: string;
}

export interface TheMoment {
  has_moment: boolean;
  commitment: {
    entity: string;
    text: string;
    claim_type: string;
    signal_id: string;
    timestamp: string;
    metadata?: Record<string, any>;
  } | null;
  why_this_one: string;
  source_evidence: Array<{ text: string; entity: string; timestamp: string }>;
}

export interface AskResult {
  answer: string;
  query: string;
  source_sentence: string;
  source_entity: string;
  source_timestamp: string;
  evidence_refs: any[];
  confidence: number;
  intelligence_source: string;
  llm_active: boolean;
  llm_provider: string;
  counterevidence: any[];
  unknowns: any[];
  as_of: string;
  decision_boundary: string;
  reasoning_chain: any[];
}

export interface Commitment {
  entity: string;
  text: string;
  claim_type: string;
  signal_id: string;
  is_commitment: boolean;
  is_at_risk: boolean;
  days_stale: number;
  deadline: string;
  calibration_note: string;
  confidence: number;
}

export interface TheOneResult {
  primary: Commitment | null;
  why_primary: string;
  secondary: Commitment[];
}

export interface Signal {
  signal_id: string;
  entity: string;
  text: string;
  signal_type: string;
  timestamp: string;
}

export interface WhatChangedShift {
  entity: string;
  description: string;
  timestamp: string;
  transition_type: string;
}

export interface Briefing {
  greeting: string;
  top_situation: any;
  watching_quietly: any[];
  ask_prompt: string;
}

export interface LLMStatus {
  configured: boolean;
  verified: boolean;
  active: boolean;
  provider: string;
  mode: string;
  probe_latency_ms: number;
}

export interface PrivacyMode {
  mode: string;
  description: string;
  egress_paths: string[];
}

export interface Calibration {
  brier_score: number | null;
  total_predictions: number;
  resolved: number;
  message: string;
}

export interface AuditLogEntry {
  timestamp: string;
  action: string;
  endpoint: string;
  resource_id: string;
  details: string;
}

export interface Metrics {
  commitment_completion_rate: number | null;
  silence_accuracy: number | null;
  engagement_signals: number;
}

export interface EntityGraph {
  exists: boolean;
  entity_name: string;
  total_interactions: number;
  active_commitments: number;
  completion_rate: number | null;
}

// ── Core fetch ───────────────────────────────────────────────────

async function apiFetch<T>(
  path: string,
  token: string,
  options: RequestInit = {}
): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${token}`,
    ...options.headers,
  };
  const res = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text.slice(0, 200)}`);
  }
  return res.json();
}

async function publicFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options.headers },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text.slice(0, 200)}`);
  }
  return res.json();
}

// ── Auth ─────────────────────────────────────────────────────────

export async function login(password: string): Promise<LoginResult> {
  return publicFetch<LoginResult>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ password }),
  });
}

export async function getHealth(): Promise<{ status: string }> {
  return publicFetch<{ status: string }>('/api/health');
}

export async function getLLMStatus(token: string): Promise<LLMStatus> {
  return apiFetch<LLMStatus>('/api/llm-status', token);
}

// ── Dashboard ────────────────────────────────────────────────────

export async function getTheMoment(token: string): Promise<TheMoment> {
  return apiFetch<TheMoment>('/api/the-moment', token);
}

export async function getBriefing(token: string): Promise<Briefing> {
  return apiFetch<Briefing>('/api/briefing', token);
}

export async function getWhatChangedShifts(token: string): Promise<{ primary: WhatChangedShift | null; secondary: WhatChangedShift[] }> {
  return apiFetch('/api/what-changed/the-shifts', token);
}

// ── Ask ──────────────────────────────────────────────────────────

export async function ask(token: string, query: string): Promise<AskResult> {
  return apiFetch<AskResult>('/api/ask', token, {
    method: 'POST',
    body: JSON.stringify({ query }),
  });
}

// ── Commitments ──────────────────────────────────────────────────

export async function getCommitments(token: string): Promise<Commitment[]> {
  return apiFetch<Commitment[]>('/api/commitments', token);
}

export async function getTheOne(token: string): Promise<TheOneResult> {
  return apiFetch<TheOneResult>('/api/commitments/the-one', token);
}

export async function correctSignal(
  token: string,
  signalId: string,
  action: 'complete' | 'dismiss' | 'cancel'
): Promise<{ status: string; message: string }> {
  return apiFetch(`/api/signals/${signalId}/correct?action=${action}`, token, {
    method: 'POST',
  });
}

// ── Signals ──────────────────────────────────────────────────────

export async function getSignals(token: string): Promise<Signal[]> {
  return apiFetch<Signal[]>('/api/signals', token);
}

export async function createSignal(
  token: string,
  entity: string,
  text: string,
  signalType: string = 'reported_statement',
  timestamp?: string
): Promise<Signal> {
  return apiFetch<Signal>('/api/signals', token, {
    method: 'POST',
    body: JSON.stringify({ entity, text, signal_type: signalType, ...(timestamp ? { timestamp } : {}) }),
  });
}

// ── Copilot ──────────────────────────────────────────────────────

export async function sendTranscriptChunk(
  token: string,
  text: string,
  speaker: string,
  entity: string
): Promise<any> {
  return apiFetch('/api/copilot/transcript', token, {
    method: 'POST',
    body: JSON.stringify({ text, speaker, entity }),
  });
}

// ── Settings ─────────────────────────────────────────────────────

export async function getPrivacyMode(token: string): Promise<PrivacyMode> {
  return apiFetch<PrivacyMode>('/api/privacy/mode', token);
}

export async function getCalibration(token: string): Promise<Calibration> {
  return apiFetch<Calibration>('/api/calibration', token);
}

export async function getAuditLog(token: string, limit: number = 50): Promise<{ events: AuditLogEntry[] }> {
  return apiFetch<{ events: AuditLogEntry[] }>(`/api/audit-log?limit=${limit}`, token);
}

export async function getMetrics(token: string): Promise<Metrics> {
  return apiFetch<Metrics>('/api/metrics', token);
}

export async function getEntityGraph(token: string, entityName: string): Promise<EntityGraph> {
  return apiFetch<EntityGraph>(`/api/graph/entity/${encodeURIComponent(entityName)}`, token);
}

export async function exportData(token: string): Promise<any> {
  return apiFetch('/api/account/export', token);
}

export async function deleteAccount(token: string): Promise<{ message: string }> {
  return apiFetch<{ message: string }>('/api/account', token, { method: 'DELETE' });
}

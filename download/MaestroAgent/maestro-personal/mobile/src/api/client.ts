/**
 * API client for Maestro Personal.
 *
 * Calls the FastAPI layer on port 8766. All requests require a bearer
 * token (obtained from login). The token is stored in SecureStore
 * (expo-secure-store) — NOT AsyncStorage. This is a Phase 1 security fix:
 * SecureStore uses the iOS Keychain / Android Keystore (encrypted at rest).
 *
 * This is a thin HTTP client — NO intelligence here. The API calls the
 * shell, the shell calls Core. The mobile app is a view layer.
 *
 * Token handling: every method accepts an optional `token` argument.
 * When omitted, the token is read from SecureStore ('maestro_token').
 * This matches the call sites in App.tsx which never pass the token
 * explicitly — the AuthProvider stores it in SecureStore on login.
 *
 * HTTP transport: axios. A request interceptor auto-attaches the Bearer
 * token via resolveToken() (reads from SecureStore when not passed
 * explicitly), and a response interceptor auto-logs-out on 401 by
 * clearing 'maestro_token' from SecureStore.
 */

import axios, { AxiosError, AxiosResponse, InternalAxiosRequestConfig } from 'axios';
import * as SecureStore from 'expo-secure-store';
import AsyncStorage from '@react-native-async-storage/async-storage';

const DEFAULT_API_URL =
  (process.env.EXPO_PUBLIC_API_URL as string) || 'http://localhost:8766';

// ─────────────────────────────────────────────────────────────────────
// Host configuration — get/set the API base URL at runtime
// ─────────────────────────────────────────────────────────────────────

let hostUrl: string = DEFAULT_API_URL;

/**
 * Returns the current API base URL the axios instance is pointing at.
 * Useful for the Settings screen / diagnostics.
 */
export function getHost(): string {
  return hostUrl;
}

/**
 * Switches the API base URL at runtime (e.g. to point at a different
 * Maestro backend). Updates the axios instance's `baseURL` and
 * persists the choice to SecureStore so it survives app restarts.
 */
export function setHost(url: string): void {
  hostUrl = url;
  api.defaults.baseURL = url;
  // Persist the choice securely. Fire-and-forget — a failure here
  // must not block the caller (the in-memory switch already happened).
  SecureStore.setItemAsync('maestro_host', url).catch(() => {
    /* ignore — non-fatal */
  });
}

// ─────────────────────────────────────────────────────────────────────
// Auth token helpers — read from SecureStore when not passed explicitly
// Phase 1 security fix: token stored in SecureStore (Keychain/Keystore),
// NOT AsyncStorage (which is plaintext JSON on disk).
// ─────────────────────────────────────────────────────────────────────

async function resolveToken(provided?: string): Promise<string | undefined> {
  if (provided) return provided;
  try {
    const t = await SecureStore.getItemAsync('maestro_token');
    return t || undefined;
  } catch {
    return undefined;
  }
}

// ─────────────────────────────────────────────────────────────────────
// Types — match the backend Pydantic response models in api.py
// ─────────────────────────────────────────────────────────────────────

export interface Situation {
  situation_id: string;
  entity: string;
  state: string;
  evidence_count: number;
}

export interface Signal {
  signal_id: string;
  entity: string;
  text: string;
  signal_type: string;
  timestamp: string;
  audit_log_error?: string | null;
  // Backend stores metadata JSON on the signals table; some endpoints
  // (e.g. /api/the-moment) inline the commitment's metadata here.
  metadata?: Record<string, any>;
}

export interface Commitment {
  entity: string;
  text: string;
  claim_type: string;
  signal_id: string;
  is_commitment: boolean;
  is_at_risk?: boolean;
  days_stale?: number;
  deadline?: string;
  calibration_note?: string;
  outcome_history?: string;
  confidence?: number;
  metadata?: Record<string, any>;
}

export interface AskResult {
  answer: string;
  query: string;
  source_sentence?: string;
  source_entity?: string;
  source_timestamp?: string;
  situation_state?: string;
  evidence_refs?: Array<Record<string, any>>;
  confidence?: number;
  counterevidence?: Array<Record<string, any>>;
  // Backend returns unknowns as list[str], but the App.tsx UI also
  // tolerates objects with a `description` field — type accordingly.
  unknowns?: Array<string | Record<string, any>>;
  intelligence_source?: string;
  as_of?: string;
  decision_boundary?: string;
  perspectives?: Array<Record<string, any>>;
  reasoning_chain?: string[];
  calibration_note?: string;
  consequence_paths?: string[];
  llm_active?: boolean;
  llm_provider?: string;
}

export interface WhatChangedItem {
  entity: string;
  text: string;
  type: string;
  is_meaningful: boolean;
}

// GET /api/what-changed/the-shifts → WhatChangedMasterpieceResponse
// Backend returns { the_shifts, silence_message }. App.tsx also accesses
// `.secondary` and per-item `.description` / `.timestamp` (legacy field
// names from an earlier API version) — those are kept optional so the
// view layer compiles without changing screen logic.
export interface WhatChangedShift {
  entity: string;
  text: string;
  type: string;
  is_meaningful: boolean;
  description?: string;
  timestamp?: string;
}

export interface WhatChangedMasterpiece {
  the_shifts: WhatChangedShift[];
  silence_message: string;
  // Legacy alias used by the App.tsx dashboard — populated by the API
  // when present, otherwise undefined (preserves prior render behavior).
  secondary?: WhatChangedShift[];
}

export interface PrepareItem {
  situation_id: string;
  entity?: string;
  meeting_context?: string;
  is_stale: boolean;
  the_forgotten?: string;
  the_open_question?: string;
  the_contradiction?: string;
  prep_points: string[];
  copilot_talking_points?: Array<Record<string, any>>;
  copilot_blocking_unknowns?: string[];
  copilot_can_decide?: string[];
  copilot_cannot_decide?: string[];
  copilot_timeline?: Array<Record<string, any>>;
}

export interface LoginResult {
  token: string;
  message: string;
  user_email?: string;
}

// ─────────────────────────────────────────────────────────────────────
// LLM status — GET /api/llm-status
// ─────────────────────────────────────────────────────────────────────

export interface LLMStatus {
  configured: boolean;
  verified: boolean;
  active: boolean;
  llm_active?: boolean;
  provider: string;
  probe_latency_ms: number;
  probe_error?: string;
  probe_cached_seconds?: number;
  available_providers?: string[];
  mode: string;
  intelligence_paths?: Record<string, string>;
  note?: string;
}

// ─────────────────────────────────────────────────────────────────────
// Briefing — GET /api/briefing (BriefingResponse)
// ─────────────────────────────────────────────────────────────────────

export interface Briefing {
  greeting: string;
  top_situation?: Record<string, any> | null;
  material_changes?: string[];
  unknowns?: string[];
  disputes?: Array<Record<string, any>>;
  can_decide_now?: string[];
  cannot_decide_yet?: string[];
  why_boundary?: string;
  next_step?: string;
  belief?: string;
  why_belief?: string;
  what_would_change_belief?: string;
  watching_quietly?: Array<Record<string, any>>;
  ask_prompt?: string;
}

// ─────────────────────────────────────────────────────────────────────
// The One — GET /api/commitments/the-one (CommitmentsMasterpieceResponse)
// ─────────────────────────────────────────────────────────────────────

export interface TheOneResult {
  primary: Commitment | null;
  why_primary: string;
  secondary?: Commitment[];
  overall_calibration?: string;
}

// ─────────────────────────────────────────────────────────────────────
// Privacy mode — GET /api/privacy/mode
// ─────────────────────────────────────────────────────────────────────

export interface PrivacyMode {
  mode: string;
  provider?: string;
  data_location?: string;
  description: string;
  egress_paths?: string[];
  [key: string]: any;
}

// ─────────────────────────────────────────────────────────────────────
// Calibration — GET /api/calibration
// Merges get_calibration_report() output + a `counts` dict from
// get_prediction_count(). The brier_score is `float | None` in Python.
// ─────────────────────────────────────────────────────────────────────

export interface Calibration {
  total_predictions?: number;
  resolved_predictions?: number;
  brier_score: number | null;
  message: string;
  has_sufficient_data?: boolean;
  counts?: {
    total?: number;
    resolved?: number;
    pending?: number;
  };
  // Full calibration report fields (10-bucket report) when >=10 resolved
  buckets?: Array<Record<string, any>>;
  small_bucket_warning?: string;
  [key: string]: any;
}

// ─────────────────────────────────────────────────────────────────────
// Audit log — GET /api/audit-log → { events: AuditLogEntry[] }
// Audit log table: id, user_email, action, endpoint, resource_id,
// details (JSON string), timestamp.
// ─────────────────────────────────────────────────────────────────────

export interface AuditLogEntry {
  id?: number;
  user_email?: string;
  action: string;
  endpoint: string;
  resource_id?: string;
  details?: string;
  timestamp: string;
}

export interface AuditLogResponse {
  events: AuditLogEntry[];
}

// ─────────────────────────────────────────────────────────────────────
// Metrics — GET /api/metrics
// Matches success_metrics.get_success_metrics() output.
// ─────────────────────────────────────────────────────────────────────

export interface Metrics {
  commitment_completion_rate: number;
  commitments_total?: number;
  commitments_completed?: number;
  commitments_missed?: number;
  commitments_active?: number;
  silence_accuracy?: number | null;
  silence_quality?: number | null;
  dismissal_rate?: number | null;
  calibration_trend?: string;
  brier_score?: number | null;
  engagement?: {
    signals_ingested: number;
    questions_asked?: number;
    corrections_made?: number;
    agents_active?: number;
  };
  learning_loop?: {
    predictions_registered?: number;
    predictions_resolved?: number;
    predictions_pending?: number;
    auto_resolved?: number;
  };
  computed_at?: string;
  // Legacy alias used by the SettingsScreen — populated when present,
  // otherwise undefined (preserves prior render behavior).
  engagement_signals?: number;
  [key: string]: any;
}

// ─────────────────────────────────────────────────────────────────────
// Signal correction — POST /api/signals/{signal_id}/correct
// ─────────────────────────────────────────────────────────────────────

export interface SignalCorrectionResult {
  signal_id: string;
  action: string;
  status: string;
  message: string;
}

// ─────────────────────────────────────────────────────────────────────
// Copilot transcript — POST /api/copilot/transcript
// ─────────────────────────────────────────────────────────────────────

export interface TranscriptCommitment {
  text?: string;
  deadline?: string;
  speaker?: string;
  entity?: string;
  action?: string;
  [key: string]: any;
}

export interface TranscriptChunkResult {
  commitments_detected?: TranscriptCommitment[];
  transitions?: any[];
  whisper?: Record<string, any>;
  error?: string;
  result?: string;
  [key: string]: any;
}

// ─────────────────────────────────────────────────────────────────────
// Axios instance + interceptors
// ─────────────────────────────────────────────────────────────────────

const api = axios.create({
  baseURL: hostUrl,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor — auto-attach the Bearer token from SecureStore
// (via resolveToken) for every outbound request that does not already
// carry an Authorization header. Methods that accept an explicit `token`
// arg still set it themselves before the interceptor runs; this is the
// safety net for callers that don't.
api.interceptors.request.use(async (config: InternalAxiosRequestConfig) => {
  if (!config.headers.Authorization) {
    const token = await resolveToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

// Response interceptor — auto-logout on 401 by clearing the token from
// SecureStore, and normalize the rejected error to match the prior
// apiFetch behavior (`API error <status>: <body>`).
api.interceptors.response.use(
  (response: AxiosResponse) => response,
  async (error: AxiosError) => {
    const status = error?.response?.status;
    if (status === 401) {
      try {
        await SecureStore.deleteItemAsync('maestro_token');
      } catch {
        /* ignore storage errors — logout is best-effort */
      }
    }
    if (error.response) {
      const raw = error.response.data;
      let body: string;
      if (typeof raw === 'string') {
        body = raw;
      } else if (raw === undefined || raw === null) {
        body = '';
      } else {
        body = JSON.stringify(raw);
      }
      return Promise.reject(new Error(`API error ${status}: ${body}`));
    }
    return Promise.reject(error);
  },
);

// ─────────────────────────────────────────────────────────────────────
// Auth / health
// ─────────────────────────────────────────────────────────────────────

export async function login(password: string): Promise<LoginResult> {
  const response = await api.post('/api/auth/login', { password });
  return response.data;
}

export async function getHealth(): Promise<{ status: string; service: string }> {
  const response = await api.get('/api/health');
  return response.data;
}

// ─────────────────────────────────────────────────────────────────────
// Situations / signals / ask / commitments
// ─────────────────────────────────────────────────────────────────────

export async function getSituations(token?: string): Promise<Situation[]> {
  const t = await resolveToken(token);
  const response = await api.get('/api/situations', {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

export async function createSignal(
  entity: string,
  text: string,
  signal_type: string,
  token?: string,
): Promise<Signal> {
  const t = await resolveToken(token);
  const response = await api.post(
    '/api/signals',
    { entity, text, signal_type },
    { headers: t ? { Authorization: `Bearer ${t}` } : undefined },
  );
  return response.data;
}

export async function getSignals(token?: string): Promise<Signal[]> {
  const t = await resolveToken(token);
  const response = await api.get('/api/signals', {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

export async function ask(query: string, token?: string): Promise<AskResult> {
  const t = await resolveToken(token);
  const response = await api.post(
    '/api/ask',
    { query },
    { headers: t ? { Authorization: `Bearer ${t}` } : undefined },
  );
  return response.data;
}

export async function getCommitments(token?: string): Promise<Commitment[]> {
  const t = await resolveToken(token);
  const response = await api.get('/api/commitments', {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

// ─────────────────────────────────────────────────────────────────────
// What Changed / Prepare
// ─────────────────────────────────────────────────────────────────────

export async function getWhatChanged(token?: string): Promise<WhatChangedItem[]> {
  const t = await resolveToken(token);
  const response = await api.get('/api/what-changed', {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

export async function getWhatChangedShifts(token?: string): Promise<WhatChangedMasterpiece> {
  const t = await resolveToken(token);
  const response = await api.get('/api/what-changed/the-shifts', {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

export async function getPrepare(token?: string): Promise<PrepareItem[]> {
  const t = await resolveToken(token);
  const response = await api.get('/api/prepare', {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

// ─────────────────────────────────────────────────────────────────────
// Whisper surface
// ─────────────────────────────────────────────────────────────────────

export interface WhisperItem {
  type: string;
  entity: string;
  title: string;
  body: string;
  priority: string;
  action_url: string;
}

export async function getWhispers(token?: string): Promise<WhisperItem[]> {
  const t = await resolveToken(token);
  const response = await api.get('/api/whisper', {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

// ─────────────────────────────────────────────────────────────────────
// THE MASTERPIECE — the single most important thing Maestro knows right now
// GET /api/the-moment (TheMomentResponse)
// ─────────────────────────────────────────────────────────────────────

export interface TheMoment {
  has_moment: boolean;
  commitment: {
    entity: string;
    text: string;
    claim_type: string;
    signal_id: string;
    timestamp: string;
    metadata?: {
      deadline?: string;
      [key: string]: any;
    };
    [key: string]: any;
  } | null;
  situation: {
    situation_id: string;
    entity: string;
    state: string;
    evidence_count: number;
  } | null;
  why_this_one: string;
  source_evidence: Array<{
    text: string;
    entity: string;
    timestamp: string;
    source: string;
  }>;
}

export async function getTheMoment(token?: string): Promise<TheMoment> {
  const t = await resolveToken(token);
  const response = await api.get('/api/the-moment', {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

// ─────────────────────────────────────────────────────────────────────
// Briefing — GET /api/briefing
// ─────────────────────────────────────────────────────────────────────

export async function getBriefing(token?: string): Promise<Briefing> {
  const t = await resolveToken(token);
  const response = await api.get('/api/briefing', {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

// ─────────────────────────────────────────────────────────────────────
// The One commitment — GET /api/commitments/the-one
// ─────────────────────────────────────────────────────────────────────

export async function getTheOne(token?: string): Promise<TheOneResult> {
  const t = await resolveToken(token);
  const response = await api.get('/api/commitments/the-one', {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

// ─────────────────────────────────────────────────────────────────────
// LLM status — GET /api/llm-status
// ─────────────────────────────────────────────────────────────────────

export async function getLLMStatus(token?: string): Promise<LLMStatus> {
  const t = await resolveToken(token);
  const response = await api.get('/api/llm-status', {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

// ─────────────────────────────────────────────────────────────────────
// Privacy / calibration / audit / metrics — Settings screen
// ─────────────────────────────────────────────────────────────────────

export async function getPrivacyMode(token?: string): Promise<PrivacyMode> {
  const t = await resolveToken(token);
  const response = await api.get('/api/privacy/mode', {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

export async function getCalibration(token?: string): Promise<Calibration> {
  const t = await resolveToken(token);
  const response = await api.get('/api/calibration', {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

export async function getAuditLog(token?: string): Promise<AuditLogResponse> {
  const t = await resolveToken(token);
  const response = await api.get('/api/audit-log', {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

export async function getMetrics(token?: string): Promise<Metrics> {
  const t = await resolveToken(token);
  const response = await api.get('/api/metrics', {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

// ─────────────────────────────────────────────────────────────────────
// Signal correction — POST /api/signals/{signal_id}/correct
// ─────────────────────────────────────────────────────────────────────

export async function correctSignal(
  signalId: string,
  action: 'complete' | 'dismiss' | 'cancel',
  token?: string,
): Promise<SignalCorrectionResult> {
  const t = await resolveToken(token);
  const response = await api.post(
    `/api/signals/${encodeURIComponent(signalId)}/correct?action=${encodeURIComponent(action)}`,
    null,
    { headers: t ? { Authorization: `Bearer ${t}` } : undefined },
  );
  return response.data;
}

// ─────────────────────────────────────────────────────────────────────
// Copilot transcript — POST /api/copilot/transcript
// ─────────────────────────────────────────────────────────────────────

export async function sendTranscriptChunk(
  text: string,
  speaker: string = '',
  entity: string = '',
  token?: string,
): Promise<TranscriptChunkResult> {
  const t = await resolveToken(token);
  const response = await api.post(
    '/api/copilot/transcript',
    { text, speaker, entity },
    { headers: t ? { Authorization: `Bearer ${t}` } : undefined },
  );
  return response.data;
}

// ─────────────────────────────────────────────────────────────────────
// Connectors — Gmail / Calendar sync
// ─────────────────────────────────────────────────────────────────────

export interface GmailSyncResult {
  signals_created: number;
  message: string;
}

export async function syncGmail(
  messages: Record<string, any>[],
  userEmail: string = 'me',
  token?: string,
): Promise<GmailSyncResult> {
  const t = await resolveToken(token);
  const response = await api.post(
    '/api/sync/gmail',
    { messages, user_email: userEmail },
    { headers: t ? { Authorization: `Bearer ${t}` } : undefined },
  );
  return response.data;
}

export async function syncCalendar(
  events: Record<string, any>[],
  userEmail: string = 'me',
  token?: string,
): Promise<GmailSyncResult> {
  const t = await resolveToken(token);
  const response = await api.post(
    '/api/sync/calendar',
    { events, user_email: userEmail },
    { headers: t ? { Authorization: `Bearer ${t}` } : undefined },
  );
  return response.data;
}

// ─────────────────────────────────────────────────────────────────────
// Account deletion / data export (privacy, not SaaS)
// ─────────────────────────────────────────────────────────────────────

export async function deleteAccount(token?: string): Promise<{ message: string; status: string }> {
  const t = await resolveToken(token);
  const response = await api.delete('/api/account', {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

export async function exportData(token?: string): Promise<{
  exported_at: string;
  signal_count: number;
  signals: Record<string, any>[];
}> {
  const t = await resolveToken(token);
  const response = await api.get('/api/account/export', {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

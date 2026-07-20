/**
 * API client for Maestro Personal.
 *
 * Calls the FastAPI layer on port 8766 (the Personal API). All requests require a bearer
 * token (obtained from login). The token is stored in SecureStore
 * (expo-secure-store) — NOT AsyncStorage. This is a Phase 1 security fix:
 * SecureStore uses the iOS Keychain / Android Keystore (encrypted at rest).
 *
 * P0-1 note (audit V2 2026-07-15): the audit flagged a "port mismatch"
 * between mobile (8766) and backend (8765). This was a misunderstanding —
 * there are TWO backends:
 *   - Personal API: port 8766 (this is what the mobile app calls)
 *   - Enterprise API: port 8765 (separate product, not used by mobile)
 * The mobile app correctly points to 8766. The env var
 * EXPO_PUBLIC_API_URL can override this for production deployments.
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

// Phase 1: HTTPS enforcement — in production, reject http:// (except localhost)
const IS_DEV = __DEV__;
function _validateHost(url: string): void {
  if (IS_DEV) return; // Dev mode allows http:// for local testing
  if (url.startsWith('http://') && !url.includes('localhost') && !url.includes('127.0.0.1')) {
    throw new Error(
      'Insecure API URL rejected: production builds require https://. ' +
      'Set a secure URL or run in dev mode.'
    );
  }
}

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
 *
 * Phase 1: In production builds, rejects http:// URLs (except localhost).
 */
export function setHost(url: string): void {
  _validateHost(url);
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
    // Web fallback: SecureStore not available on web
    try {
      const t = await AsyncStorage.getItem('maestro_token');
      return t || undefined;
    } catch {
      return undefined;
    }
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
  // P1 fix: send user_email as empty string (backend defaults to
  // default@personal.local when MAESTRO_PERSONAL_TOKEN is set).
  // Previously sent only { password } which could cause issues if
  // the backend expected user_email in the body.
  const response = await api.post('/api/auth/login', {
    user_email: '',
    password,
  });
  return response.data;
}

export async function register(email: string, password: string): Promise<LoginResult> {
  // Ports the web register() pattern. Calls /api/auth/register with
  // user_email + password. Returns the same LoginResult shape as login()
  // (token + message). Fixes the 4-round-old finding: zero references
  // to /api/auth/register anywhere in mobile/src.
  const response = await api.post('/api/auth/register', {
    user_email: email,
    password,
  });
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

export async function ask(query: string, sessionId?: string, token?: string): Promise<AskResult> {
  const t = await resolveToken(token);
  const body: Record<string, string> = { query };
  if (sessionId) {
    body.session_id = sessionId;
  }
  const response = await api.post(
    '/api/ask',
    body,
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
  // P0-5 fix (audit V2): Trusted Silence depth fields from DeliveryGovernor
  delivery_route?: string;
  delivery_explanation?: string;
  suppression_reason?: string;
  evidence_refs?: string[];
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

// P1-4 fix: retention policy status — GET /api/privacy/retention-status
export interface RetentionPolicy {
  timestamp: string;
  [key: string]: any;
}

export async function getRetentionPolicy(token?: string): Promise<RetentionPolicy> {
  const t = await resolveToken(token);
  const response = await api.get('/api/privacy/retention-status', {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

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

// ─────────────────────────────────────────────────────────────────────
// Connectors API (Phase 3)
// ─────────────────────────────────────────────────────────────────────

export interface Connector {
  provider: string;
  name: string;
  icon: string;
  category: string;
  phase: number;
  ingest_description: string;
  write_description: string;
  oauth_configured: boolean;
  connected: boolean;
  connected_at: string;
  last_ingest_at: string;
  commitments_ingested: number;
}

export interface ConnectorListResult {
  connectors: Connector[];
}

export interface ConnectorConnectResult {
  oauth_required?: boolean;
  authorization_url?: string;
  connected?: boolean;
  provider?: string;
}

export interface ConnectorIngestResult {
  provider: string;
  ingested: number;
  new_commitments: number;
  duplicates: number;
  ingested_at: string;
}

export interface Draft {
  draft_id: string;
  provider: string;
  recipient: string;
  subject: string;
  body: string;
  commitment_ref: string;
  evidence_refs: Array<{ entity: string; text: string; timestamp?: string }>;
  status: string;
  created_at: string;
  resolved_at: string;
}

export interface DraftListResult {
  drafts: Draft[];
}

export async function listConnectors(token?: string): Promise<ConnectorListResult> {
  const t = await resolveToken(token);
  const response = await api.get('/api/connectors', {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

export async function connectProvider(provider: string, oauthToken: string = '', token?: string): Promise<ConnectorConnectResult> {
  const t = await resolveToken(token);
  const response = await api.post(`/api/connectors/${provider}/connect`, { provider, oauth_token: oauthToken }, {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

export async function disconnectProvider(provider: string, token?: string): Promise<{ provider: string; connected: boolean }> {
  const t = await resolveToken(token);
  const response = await api.delete(`/api/connectors/${provider}`, {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

export async function ingestConnector(provider: string, token?: string): Promise<ConnectorIngestResult> {
  const t = await resolveToken(token);
  const response = await api.post(`/api/connectors/${provider}/ingest`, {}, {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

export async function listDrafts(status: string = 'pending', token?: string): Promise<DraftListResult> {
  const t = await resolveToken(token);
  const response = await api.get(`/api/drafts?status=${encodeURIComponent(status)}`, {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

export async function resolveDraft(draftId: string, resolution: 'approve' | 'deny' | 'use_draft', token?: string): Promise<{ draft_id: string; status: string; send_error?: string; sent_message_id?: string }> {
  const t = await resolveToken(token);
  const response = await api.post(`/api/drafts/${draftId}/resolve`, { resolution }, {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

// ─── Issue 5/6/7: Proactive drafting + push notifications ───────────

export async function generateAutoDraft(provider: string, recipient: string, token?: string): Promise<any> {
  const t = await resolveToken(token);
  const response = await api.post('/api/drafts/auto', { provider, recipient }, {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

export async function registerPushToken(pushToken: string, token?: string): Promise<any> {
  const t = await resolveToken(token);
  const response = await api.post('/api/auth/push-token', { push_token: pushToken }, {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

// ─── Ambient Intelligence (Phases 9, 11, 14, 16, 19, 20) ───────────
// These endpoints DERIVE intelligence from the user's signal history.
// The UI supplies only CONTEXT (am I in a call? which entity?) — never
// the conclusion. See P13 in ENTROPY_RECOVERY.md.

// Phase 19: Smart notifications
export interface SmartNotification {
  notification_id: string;
  type: string;
  priority: 'critical' | 'high' | 'medium' | 'low';
  title: string;
  body: string;
  action_url: string;
  action_label: string;
  created_at: string;
  metadata: Record<string, any>;
}

export interface SmartNotificationContext {
  is_in_call?: boolean;
  is_dnd_active?: boolean;
  is_focus_mode?: boolean;
  user_timezone?: string;
  limit?: number;
}

export async function getSmartNotifications(
  context: SmartNotificationContext = {},
  token?: string,
): Promise<{ notifications: SmartNotification[]; engine_available: boolean; count: number }> {
  const t = await resolveToken(token);
  const response = await api.post('/api/notifications/smart', context, {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

// Phase 9: Calendar awareness
export interface CalendarAwarenessMeeting {
  meeting_id: string;
  title: string;
  start_time: string;
  end_time: string;
  urgency: string;
  preparation_status: string;
  entity: string | null;
  open_commitments: number;
  overdue_commitments: number;
  suggested_talking_points: any[];
  risks_to_address: any[];
  opportunities_to_pursue: any[];
}

export async function getCalendarAwareness(
  hoursAhead: number = 48,
  token?: string,
): Promise<{ meetings: CalendarAwarenessMeeting[]; engine_available: boolean; count: number }> {
  const t = await resolveToken(token);
  const response = await api.post('/api/calendar/awareness', { hours_ahead: hoursAhead }, {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

// Phase 9: Commitment escalations
export interface CommitmentEscalation {
  commitment_id: string;
  commitment_text: string;
  owner: string;
  entity: string | null;
  health: string;
  escalation_level: string;
  days_until_due: number | null;
  days_overdue: number | null;
  nudge_text: string;
  nudge_channel: string;
  nudge_draft: string;
  failure_probability: number | null;
  failure_reason: string | null;
  related_commitments: string[];
}

export async function getEscalations(
  token?: string,
): Promise<{ escalations: CommitmentEscalation[]; engine_available: boolean; count: number; critical_count: number; overdue_count: number }> {
  const t = await resolveToken(token);
  const response = await api.get('/api/commitments/escalations', {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

// Phase 14: Cross-meeting threads
export interface MeetingSummary {
  meeting_id: string;
  title: string;
  entity: string | null;
  start_time: string;
  attendees: string[];
  topics: string[];
  decisions: string[];
  commitments: string[];
  sentiment: number | null;
}

export interface CrossMeetingThread {
  thread_id: string;
  entity: string;
  topic: string;
  meeting_count: number;
  meetings: MeetingSummary[];
  confidence: number;
  confidence_level: 'high' | 'medium' | 'low';
  requires_confirmation: boolean;
  topic_evolution: string[];
  decision_chain: any[];
  sentiment_trend: any;
}

export async function getThreads(
  entityFilter: string = '',
  token?: string,
): Promise<{ threads: CrossMeetingThread[]; engine_available: boolean; count: number; high_confidence_count: number }> {
  const t = await resolveToken(token);
  const response = await api.post('/api/threads', { entity_filter: entityFilter }, {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

export async function getThreadsForEntity(
  entity: string,
  token?: string,
): Promise<{ threads: CrossMeetingThread[]; engine_available: boolean; count: number; entity: string }> {
  const t = await resolveToken(token);
  const response = await api.get(`/api/threads/${encodeURIComponent(entity)}`, {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

export async function getDecisionHistory(
  entity: string,
  token?: string,
): Promise<{ decisions: any[]; engine_available: boolean; count: number; entity: string }> {
  const t = await resolveToken(token);
  const response = await api.get(`/api/threads/${encodeURIComponent(entity)}/decisions`, {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

// Phase 16: Meeting grader
export interface MeetingGradeReport {
  grade: string;
  effective_grade: string;
  score: number;
  factors: Record<string, any>;
  action_items: any[];
  action_item_completion_rate: number;
  follow_ups_pending: number;
  follow_ups_completed: number;
  user_override: string | null;
  confidence_label: string;
  meeting_id?: string;
  entity?: string;
  title?: string;
}

export async function getMeetingGrades(
  token?: string,
): Promise<{ grades: MeetingGradeReport[]; engine_available: boolean; count: number; average_score: number }> {
  const t = await resolveToken(token);
  const response = await api.get('/api/meetings/grades', {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

export async function getMeetingGrade(
  meetingId: string,
  token?: string,
): Promise<{ grade: MeetingGradeReport; engine_available: boolean }> {
  const t = await resolveToken(token);
  const response = await api.get(`/api/meetings/${encodeURIComponent(meetingId)}/grade`, {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

export async function overrideMeetingGrade(
  meetingId: string,
  grade: string,
  token?: string,
): Promise<{ grade: MeetingGradeReport; engine_available: boolean; message: string }> {
  const t = await resolveToken(token);
  const response = await api.post(`/api/meetings/${encodeURIComponent(meetingId)}/grade/override`, { grade }, {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

// Phase 11: Deal health
export interface DealHealthScore {
  entity: string;
  score: number;
  status: 'strong' | 'on_track' | 'at_risk' | 'critical';
  momentum: 'accelerating' | 'stable' | 'decelerating';
  confidence_label: string;
  calibration_denominator: number;
  risk_factors: any[];
  positive_indicators: string[];
  score_history: number[];
  compounding_adjustments: any[];
}

export async function getDealHealth(
  token?: string,
): Promise<{ deals: DealHealthScore[]; engine_available: boolean; count: number; strong_count: number; at_risk_count: number; critical_count: number }> {
  const t = await resolveToken(token);
  const response = await api.get('/api/deals/health', {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

export async function getDealHealthForEntity(
  entity: string,
  token?: string,
): Promise<{ deal_health: DealHealthScore; engine_available: boolean }> {
  const t = await resolveToken(token);
  const response = await api.get(`/api/deals/${encodeURIComponent(entity)}/health`, {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

// Phase 20: Advanced analytics
export interface TrendMetric {
  name: string;
  current_value: number;
  previous_value: number;
  direction: 'improving' | 'stable' | 'declining';
  change_percentage: number;
  period: string;
  description: string;
  evidence: Record<string, any>;
}

export interface OrgLearningReport {
  trends: TrendMetric[];
  team_performance: any[];
  laws_validated: number;
  laws_candidate: number;
  patterns_detected: number;
  brier_score: number | null;
  brier_score_previous: number | null;
  brier_trend: string | null;
  commitment_kept_rate: number;
  commitment_broken_rate: number;
  meeting_grade_average: number;
  deal_cycle_time_days: number;
  flywheel_summary?: string;
}

export async function getAnalyticsTrends(
  token?: string,
): Promise<{ report: OrgLearningReport | null; engine_available: boolean; flywheel_summary?: string; message?: string }> {
  const t = await resolveToken(token);
  const response = await api.get('/api/analytics/trends', {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

export async function getAnalyticsFlywheel(
  token?: string,
): Promise<{ summary: string; engine_available: boolean }> {
  const t = await resolveToken(token);
  const response = await api.get('/api/analytics/flywheel', {
    headers: t ? { Authorization: `Bearer ${t}` } : undefined,
  });
  return response.data;
}

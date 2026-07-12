/**
 * Production API client — axios with interceptors, secure storage, react-query.
 *
 * Production features:
 *   - axios with auto-token-attach interceptor
 *   - 401 → auto-logout
 *   - expo-secure-store for token (NOT AsyncStorage)
 *   - Server URL configurable (env var or login-screen input)
 *   - All 16+ endpoints typed
 */

import axios, { AxiosInstance, AxiosRequestConfig } from 'axios';
import * as SecureStore from 'expo-secure-store';
import AsyncStorage from '@react-native-async-storage/async-storage';

// ── Config ────────────────────────────────────────────────────────

const DEFAULT_HOST = 'http://localhost:8766';
const TOKEN_KEY = 'maestro_token';
const HOST_KEY = 'maestro_host';

export async function getHost(): Promise<string> {
  return (await AsyncStorage.getItem(HOST_KEY)) || DEFAULT_HOST;
}

export async function setHost(url: string): Promise<void> {
  await AsyncStorage.setItem(HOST_KEY, url);
}

export async function getToken(): Promise<string | null> {
  return SecureStore.getItemAsync(TOKEN_KEY);
}

export async function setToken(token: string): Promise<void> {
  await SecureStore.setItemAsync(TOKEN_KEY, token);
}

export async function clearToken(): Promise<void> {
  await SecureStore.deleteItemAsync(TOKEN_KEY);
}

// ── Axios instance with interceptors ─────────────────────────────

let _client: AxiosInstance | null = null;
let _currentHost: string = DEFAULT_HOST;

export async function getClient(): Promise<AxiosInstance> {
  const host = await getHost();
  if (_client && host === _currentHost) return _client;

  _currentHost = host;
  _client = axios.create({ baseURL: host, timeout: 30000 });

  // Request interceptor: auto-attach token
  _client.interceptors.request.use(async (config) => {
    const token = await getToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  });

  // Response interceptor: 401 → logout
  _client.interceptors.response.use(
    (response) => response,
    async (error) => {
      if (error.response?.status === 401) {
        await clearToken();
        // AuthContext will detect null token and show login
      }
      return Promise.reject(error);
    }
  );

  return _client;
}

// ── Types (same as before) ────────────────────────────────────────

export interface LoginResult { token: string; user_email: string; message: string; }
export interface TheMoment { has_moment: boolean; commitment: any; why_this_one: string; source_evidence: any[]; }
export interface AskResult { answer: string; query: string; source_sentence: string; source_entity: string; source_timestamp: string; evidence_refs: any[]; confidence: number; intelligence_source: string; llm_active: boolean; llm_provider: string; counterevidence: any[]; unknowns: any[]; as_of: string; decision_boundary: string; reasoning_chain: any[]; }
export interface Commitment { entity: string; text: string; claim_type: string; signal_id: string; is_commitment: boolean; is_at_risk: boolean; days_stale: number; deadline: string; calibration_note: string; confidence: number; }
export interface TheOneResult { primary: Commitment | null; why_primary: string; secondary: Commitment[]; }
export interface Signal { signal_id: string; entity: string; text: string; signal_type: string; timestamp: string; }
export interface WhatChangedShift { entity: string; description: string; timestamp: string; transition_type: string; }
export interface Briefing { greeting: string; top_situation: any; watching_quietly: any[]; ask_prompt: string; }
export interface LLMStatus { configured: boolean; verified: boolean; active: boolean; provider: string; mode: string; probe_latency_ms: number; }
export interface PrivacyMode { mode: string; description: string; egress_paths: string[]; }
export interface Calibration { brier_score: number | null; total_predictions: number; resolved: number; message: string; }
export interface AuditLogEntry { timestamp: string; action: string; endpoint: string; resource_id: string; details: string; }
export interface Metrics { commitment_completion_rate: number | null; silence_accuracy: number | null; engagement_signals: number; }
export interface EntityGraph { exists: boolean; entity_name: string; total_interactions: number; active_commitments: number; completion_rate: number | null; }

// ── API functions ─────────────────────────────────────────────────

async function get<T>(path: string): Promise<T> {
  const client = await getClient();
  const res = await client.get<T>(path);
  return res.data;
}

async function post<T>(path: string, body?: any): Promise<T> {
  const client = await getClient();
  const res = await client.post<T>(path, body);
  return res.data;
}

async function del<T>(path: string): Promise<T> {
  const client = await getClient();
  const res = await client.delete<T>(path);
  return res.data;
}

// ── Auth (no token needed) ────────────────────────────────────────

export async function login(password: string): Promise<LoginResult> {
  const host = await getHost();
  const res = await axios.post<LoginResult>(`${host}/api/auth/login`, { password });
  await setToken(res.data.token);
  return res.data;
}

export async function getHealth(): Promise<{ status: string }> {
  const host = await getHost();
  const res = await axios.get<{ status: string }>(`${host}/api/health`);
  return res.data;
}

// ── Authenticated endpoints ───────────────────────────────────────

export const getLLMStatus = () => get<LLMStatus>('/api/llm-status');
export const getTheMoment = () => get<TheMoment>('/api/the-moment');
export const getBriefing = () => get<Briefing>('/api/briefing');
export const getWhatChangedShifts = () => get<{ primary: WhatChangedShift | null; secondary: WhatChangedShift[] }>('/api/what-changed/the-shifts');
export const ask = (query: string) => post<AskResult>('/api/ask', { query });
export const getCommitments = () => get<Commitment[]>('/api/commitments');
export const getTheOne = () => get<TheOneResult>('/api/commitments/the-one');
export const correctSignal = (signalId: string, action: 'complete' | 'dismiss' | 'cancel') => post(`/api/signals/${signalId}/correct?action=${action}`);
export const getSignals = () => get<Signal[]>('/api/signals');
export const createSignal = (entity: string, text: string, signalType = 'reported_statement', timestamp?: string) =>
  post<Signal>('/api/signals', { entity, text, signal_type: signalType, ...(timestamp ? { timestamp } : {}) });
export const sendTranscriptChunk = (text: string, speaker: string, entity: string) =>
  post('/api/copilot/transcript', { text, speaker, entity });
export const getPrivacyMode = () => get<PrivacyMode>('/api/privacy/mode');
export const getCalibration = () => get<Calibration>('/api/calibration');
export const getAuditLog = (limit = 50) => get<{ events: AuditLogEntry[] }>(`/api/audit-log?limit=${limit}`);
export const getMetrics = () => get<Metrics>('/api/metrics');
export const getEntityGraph = (entityName: string) => get<EntityGraph>(`/api/graph/entity/${encodeURIComponent(entityName)}`);
export const exportData = () => get('/api/account/export');
export const deleteAccount = () => del<{ message: string }>('/api/account');

/**
 * API client for Maestro Personal.
 *
 * Calls the FastAPI layer on port 8766. All requests require a bearer
 * token (obtained from login). The token is stored in AsyncStorage.
 *
 * This is a thin HTTP client — NO intelligence here. The API calls the
 * shell, the shell calls Core. The mobile app is a view layer.
 */

const API_URL = (process.env.EXPO_PUBLIC_API_URL as string) || 'http://localhost:8766';

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
}

export interface Commitment {
  entity: string;
  text: string;
  claim_type: string;
  signal_id: string;
  is_commitment: boolean;
}

export interface AskResult {
  answer: string;
  query: string;
}

export interface WhatChangedItem {
  entity: string;
  text: string;
  type: string;
  is_meaningful: boolean;
}

export interface PrepareItem {
  situation_id: string;
  is_stale: boolean;
  prep_points: string[];
}

export interface LoginResult {
  token: string;
  message: string;
}

async function apiFetch(path: string, options: RequestInit = {}, token?: string): Promise<Response> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  const response = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (!response.ok) {
    const error = await response.text();
    throw new Error(`API error ${response.status}: ${error}`);
  }
  return response;
}

export async function login(password: string): Promise<LoginResult> {
  const response = await apiFetch('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ password }),
  });
  return response.json();
}

export async function getHealth(): Promise<{ status: string; service: string }> {
  const response = await apiFetch('/api/health');
  return response.json();
}

export async function getSituations(token: string): Promise<Situation[]> {
  const response = await apiFetch('/api/situations', {}, token);
  return response.json();
}

export async function createSignal(
  token: string,
  entity: string,
  text: string,
  signal_type: string
): Promise<Signal> {
  const response = await apiFetch('/api/signals', {
    method: 'POST',
    body: JSON.stringify({ entity, text, signal_type }),
  }, token);
  return response.json();
}

export async function getSignals(token: string): Promise<Signal[]> {
  const response = await apiFetch('/api/signals', {}, token);
  return response.json();
}

export async function ask(token: string, query: string): Promise<AskResult> {
  const response = await apiFetch('/api/ask', {
    method: 'POST',
    body: JSON.stringify({ query }),
  }, token);
  return response.json();
}

export async function getCommitments(token: string): Promise<Commitment[]> {
  const response = await apiFetch('/api/commitments', {}, token);
  return response.json();
}

export async function getWhatChanged(token: string): Promise<WhatChangedItem[]> {
  const response = await apiFetch('/api/what-changed', {}, token);
  return response.json();
}

export async function getPrepare(token: string): Promise<PrepareItem[]> {
  const response = await apiFetch('/api/prepare', {}, token);
  return response.json();
}

// v2: Whisper surface
export interface WhisperItem {
  type: string;
  entity: string;
  title: string;
  body: string;
  priority: string;
  action_url: string;
}

export async function getWhispers(token: string): Promise<WhisperItem[]> {
  const response = await apiFetch('/api/whisper', {}, token);
  return response.json();
}

// v2: Gmail sync
export interface GmailSyncResult {
  signals_created: number;
  message: string;
}

export async function syncGmail(
  token: string,
  messages: Record<string, any>[],
  userEmail: string = 'me'
): Promise<GmailSyncResult> {
  const response = await apiFetch('/api/sync/gmail', {
    method: 'POST',
    body: JSON.stringify({ messages, user_email: userEmail }),
  }, token);
  return response.json();
}

// v2: Calendar sync
export async function syncCalendar(
  token: string,
  events: Record<string, any>[],
  userEmail: string = 'me'
): Promise<GmailSyncResult> {
  const response = await apiFetch('/api/sync/calendar', {
    method: 'POST',
    body: JSON.stringify({ events, user_email: userEmail }),
  }, token);
  return response.json();
}

// v3: Account deletion
export async function deleteAccount(token: string): Promise<{ message: string; status: string }> {
  const response = await apiFetch('/api/account', { method: 'DELETE' }, token);
  return response.json();
}

// v3: Data export (GDPR/CCPA)
export async function exportData(token: string): Promise<{
  exported_at: string;
  signal_count: number;
  signals: Record<string, any>[];
}> {
  const response = await apiFetch('/api/account/export', {}, token);
  return response.json();
}

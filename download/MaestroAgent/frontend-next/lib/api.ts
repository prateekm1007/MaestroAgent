// lib/api.ts — API client for Maestro backend.

import type { AuthUser, TokenPair, Run, Metrics, ExecutionReceipt, Integration, OrgMember, AuditLogEntry } from '@/types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('access_token') || getCookie('access_token');
}

function getCookie(name: string): string | null {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
  return match ? match[2] : null;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...options.headers as Record<string, string>,
  };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers, credentials: 'include' });

  if (res.status === 401) {
    // Try refresh
    const refreshed = await refreshToken();
    if (refreshed) {
      const retryRes = await fetch(`${API_BASE}${path}`, { ...options, headers: { ...headers, Authorization: `Bearer ${refreshed}` }, credentials: 'include' });
      if (!retryRes.ok) throw new ApiError(retryRes.status, await retryRes.json());
      return retryRes.json();
    }
    // Redirect to login
    if (typeof window !== 'undefined') window.location.href = '/auth/login';
    throw new ApiError(401, { error: 'Authentication required' });
  }

  if (!res.ok) throw new ApiError(res.status, await res.json().catch(() => ({ error: res.statusText })));
  return res.json();
}

export class ApiError extends Error {
  status: number;
  body: Record<string, unknown>;
  constructor(status: number, body: Record<string, unknown>) {
    super(body.error || `HTTP ${status}`);
    this.status = status;
    this.body = body;
  }
}

async function refreshToken(): Promise<string | null> {
  try {
    const res = await fetch(`${API_BASE}/api/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: getCookie('refresh_token') }),
    });
    if (!res.ok) return null;
    const tokens: TokenPair = await res.json();
    localStorage.setItem('access_token', tokens.access_token);
    return tokens.access_token;
  } catch {
    return null;
  }
}

// ============================================================================
// AUTH
// ============================================================================

export const auth = {
  async register(data: { email: string; password: string; name: string; org_name: string; org_slug: string; industry?: string }) {
    return request<{ user: AuthUser; tokens: TokenPair }>('/api/auth/register', {
      method: 'POST', body: JSON.stringify(data),
    });
  },

  async login(data: { email: string; password: string; org_slug?: string }) {
    return request<{ user: AuthUser; tokens: TokenPair }>('/api/auth/login', {
      method: 'POST', body: JSON.stringify(data),
    });
  },

  async logout() {
    localStorage.removeItem('access_token');
    return request('/api/auth/logout', { method: 'POST' });
  },

  async me() {
    return request<{ user: AuthUser }>('/api/auth/me');
  },

  async getOrgs() {
    return request<{ organizations: any[] }>('/api/auth/orgs');
  },

  async getPermissions() {
    return request('/api/auth/permissions');
  },

  async createApiKey(data: { name: string; scopes?: string[]; expires_in_days?: number }) {
    return request('/api/auth/api-keys', { method: 'POST', body: JSON.stringify(data) });
  },

  async listApiKeys() {
    return request<{ api_keys: any[] }>('/api/auth/api-keys');
  },

  async revokeApiKey(id: string) {
    return request(`/api/auth/api-keys/${id}`, { method: 'DELETE' });
  },

  async inviteUser(data: { email: string; role: string; department?: string; team?: string }) {
    return request('/api/auth/invite', { method: 'POST', body: JSON.stringify(data) });
  },

  async listUsers() {
    return request<{ members: OrgMember[] }>('/api/auth/users');
  },

  async updateMemberRole(userId: string, role: string) {
    return request(`/api/auth/users/${userId}/role`, { method: 'PATCH', body: JSON.stringify({ role }) });
  },

  async removeMember(userId: string) {
    return request(`/api/auth/users/${userId}`, { method: 'DELETE' });
  },

  async getAuditLog(limit = 100, offset = 0) {
    return request<{ entries: AuditLogEntry[] }>(`/api/auth/audit-log?limit=${limit}&offset=${offset}`);
  },
};

// ============================================================================
// RUNS
// ============================================================================

export const runs = {
  async create(goal: string) {
    return request<{ run_id: string; status: string }>('/api/runs', {
      method: 'POST', body: JSON.stringify({ goal }),
    });
  },

  async list() {
    return request<Run[]>('/api/runs');
  },

  async get(id: string) {
    return request<Run>(`/api/runs/${id}`);
  },

  async getEvents(id: string) {
    return request<any[]>(`/api/runs/${id}/events`);
  },

  async interrupt(id: string, message: string) {
    return request(`/api/runs/${id}/interrupt`, { method: 'POST', body: JSON.stringify({ message }) });
  },

  async feedback(id: string, outcome: 'accepted' | 'rejected' | 'edited', notes?: string) {
    return request(`/api/runs/${id}/feedback`, { method: 'POST', body: JSON.stringify({ outcome, notes }) });
  },

  async getArtifacts(id: string) {
    return request<any[]>(`/api/runs/${id}/artifacts`);
  },

  artifactUrl(runId: string, filename: string) {
    return `${API_BASE}/api/runs/${runId}/artifacts/${filename}`;
  },
};

// ============================================================================
// METRICS
// ============================================================================

export const metrics = {
  async get() {
    return request<Metrics>('/api/metrics');
  },

  async roi() {
    return request('/api/roi-report');
  },

  async eii() {
    return request('/api/eii');
  },

  async ttv() {
    return request('/api/ttv');
  },

  async coi() {
    return request('/api/coi');
  },

  async cpr() {
    return request('/api/cpr');
  },

  async customerHealth() {
    return request('/api/customer-health');
  },

  async simulate(data: { type: string; [key: string]: unknown }) {
    return request('/api/simulate', { method: 'POST', body: JSON.stringify(data) });
  },

  async benchmarks() {
    return request('/api/benchmarks');
  },
};

// ============================================================================
// RECEIPTS
// ============================================================================

export const receipts = {
  async list(limit = 50) {
    return request<ExecutionReceipt[]>(`/api/receipts?limit=${limit}`);
  },

  async getByRun(runId: string) {
    return request<ExecutionReceipt>(`/api/runs/${runId}/receipt`);
  },

  async get(id: string) {
    return request<ExecutionReceipt>(`/api/receipts/${id}`);
  },

  async verify(id: string) {
    return request(`/api/receipts/${id}/verify`);
  },
};

// ============================================================================
// INTEGRATIONS
// ============================================================================

export const integrations = {
  async list() {
    return request<Integration[]>('/api/integrations');
  },

  async getProviders() {
    return request<any[]>('/api/integrations/providers');
  },

  async jiraHealth() {
    return request('/api/integrations/jira/health');
  },

  async githubHealth() {
    return request('/api/integrations/github/health');
  },

  async slackHealth() {
    return request('/api/integrations/slack/health');
  },

  async jiraAuthUrl() {
    return request<{ auth_url: string; state: string }>('/api/integrations/jira/auth');
  },

  async githubAuthUrl() {
    return request<{ auth_url: string; state: string }>('/api/integrations/github/auth');
  },

  async slackAuthUrl() {
    return request<{ auth_url: string; state: string }>('/api/integrations/slack/auth');
  },

  async disconnect(id: string) {
    return request(`/api/integrations/${id}`, { method: 'DELETE' });
  },
};

// ============================================================================
// RBAC
// ============================================================================

export const rbac = {
  async getInfo() {
    return request('/api/rbac/info');
  },

  async listRoles() {
    return request<{ roles: any[] }>('/api/rbac/roles');
  },

  async listDepartments() {
    return request<{ departments: any[] }>('/api/rbac/departments');
  },

  async listTeams(departmentId?: string) {
    const query = departmentId ? `?department_id=${departmentId}` : '';
    return request<{ teams: any[] }>(`/api/rbac/teams${query}`);
  },
};

// ============================================================================
// WEBSOCKET
// ============================================================================

export function connectWebSocket(runId: string, onEvent: (event: any) => void): WebSocket {
  const wsUrl = (process.env.NEXT_PUBLIC_WS_URL || API_BASE.replace('http', 'ws')) + `/ws/${runId}`;
  const ws = new WebSocket(wsUrl);

  ws.onmessage = (e) => {
    try {
      const event = JSON.parse(e.data);
      onEvent(event);
    } catch {}
  };

  return ws;
}

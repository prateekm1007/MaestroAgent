/**
 * API client — the browser-side bridge to the MaestroAgent backend.
 *
 * In the browser/PWA world there is no Tauri `invoke`. Instead we use
 * `fetch` for REST and `WebSocket` for streaming. The client auto-detects
 * the backend URL from:
 *   1. `import.meta.env.VITE_API_URL` (explicit override)
 *   2. same-origin (when the backend serves the PWA bundle in self-host mode)
 *   3. `http://localhost:8765` (dev mode with separate Vite + backend)
 *
 * All methods return typed promises. Errors are thrown as `ApiError`
 * with the HTTP status and body for debugging.
 */

export class ApiError extends Error {
  constructor(public status: number, public body: string, message?: string) {
    super(message || `API ${status}: ${body.slice(0, 200)}`);
    this.name = "ApiError";
  }
}

function apiUrl(path: string): string {
  const base =
    (import.meta as any).env?.VITE_API_URL ||
    (window.location.origin.startsWith("http://localhost:14")
      ? "http://localhost:8765"
      : window.location.origin);
  return `${base.replace(/\/$/, "")}${path}`;
}

function wsUrl(path: string): string {
  const base =
    (import.meta as any).env?.VITE_API_URL?.replace(/^http/, "ws") ||
    (window.location.origin.startsWith("http://localhost:14")
      ? "ws://localhost:8765"
      : window.location.origin.replace(/^http/, "ws"));
  return `${base.replace(/\/$/, "")}${path}`;
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown
): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const init: RequestInit = { method, headers };
  if (body !== undefined) init.body = JSON.stringify(body);

  const resp = await fetch(apiUrl(path), init);
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new ApiError(resp.status, text);
  }
  if (resp.status === 204) return undefined as T;
  return resp.json() as Promise<T>;
}

// --- Typed API surface ---

export interface StartRunRequest {
  template: string;
  goal: string;
  max_cost_usd?: number;
  max_iterations?: number;
  max_wall_clock_seconds?: number;
  default_provider?: string;
  default_model?: string;
  env?: Record<string, string>;
  extras?: Record<string, unknown>;
}

export interface StartRunResponse {
  run_id: string;
  status: string;
}

export interface RunSummary {
  run_id: string;
  status: string;
  iteration?: number;
  cost_usd?: number;
  current_node?: string;
  error?: string;
  metadata?: Record<string, unknown>;
}

export interface TemplateEntry {
  name: string;
  description: string;
  path: string;
}

export interface RunEvent {
  type: string;
  run_id: string;
  ts: string;
  event_id: string;
  payload: Record<string, unknown>;
}

export interface CostBreakdown {
  provider: string;
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
  calls: number;
}

export interface CostResponse {
  run_id: string;
  total_usd: number;
  breakdown: CostBreakdown[];
}

export interface LiveState {
  run_id: string;
  status: string;
  iteration: number;
  current_node: string | null;
  cost_usd: number;
  cost_breakdown: CostBreakdown[];
  agents: Array<{ id: string; kind: string; role?: string; status?: string; parent_id?: string }>;
  agent_edges: Array<{ parent: string; child: string }>;
  error: string | null;
}

export interface SpawnSubAgentRequest {
  parent_id: string;
  sub_goal: string;
  role?: string;
  backstory?: string;
  tools?: string[];
  llm_hint?: Record<string, string>;
  memory_scope?: string;
  max_iterations?: number;
}

export interface DebateRequest {
  topic: string;
  participants: string[];
  seek_consensus?: boolean;
  max_rounds?: number;
}

export interface CreateLoopRequest {
  loop_id: string;
  body_agent_id: string;
  exit_kind?: string;
  exit_config?: Record<string, unknown>;
  max_iterations?: number;
  max_cost_usd?: number;
  on_exceed?: string;
}

export interface HealthResponse {
  status: string;
  version: string;
  providers: string[];
  verifiers: string[];
  plugins: string[];
}

// --- API methods ---

export const api = {
  // Health
  health: () => request<HealthResponse>("GET", "/api/health"),
  doctor: () => request<Record<string, boolean>>("GET", "/api/doctor"),

  // Runs
  startRun: (req: StartRunRequest) =>
    request<StartRunResponse>("POST", "/api/runs", req),
  getRun: (runId: string) => request<RunSummary>("GET", `/api/runs/${runId}`),
  cancelRun: (runId: string) =>
    request<Record<string, unknown>>("POST", `/api/runs/${runId}/cancel`),
  resumeRun: (runId: string, humanInput?: unknown) =>
    request<Record<string, unknown>>("POST", `/api/runs/${runId}/resume`, humanInput || null),
  getRunHistory: (runId: string) =>
    request<Array<Record<string, unknown>>>("GET", `/api/runs/${runId}/history`),
  getAuditLog: (runId: string) =>
    request<Array<Record<string, unknown>>>("GET", `/api/runs/${runId}/audit`),
  getLiveState: (runId: string) => request<LiveState>("GET", `/api/runs/${runId}/live`),

  // Live control
  spawnSubagent: (runId: string, req: SpawnSubAgentRequest) =>
    request<Record<string, unknown>>("POST", `/api/runs/${runId}/spawn`, req),
  triggerDebate: (runId: string, req: DebateRequest) =>
    request<Record<string, unknown>>("POST", `/api/runs/${runId}/debate`, req),
  createLoop: (runId: string, req: CreateLoopRequest) =>
    request<Record<string, unknown>>("POST", `/api/runs/${runId}/loops`, req),

  // Templates
  listTemplates: () => request<TemplateEntry[]>("GET", "/api/templates"),

  // Costs
  getCost: (runId: string) => request<CostResponse>("GET", `/api/costs/${runId}`),
  listAllCosts: () =>
    request<Array<Record<string, unknown>>>("GET", "/api/costs"),

  // Memory
  recall: (req: {
    query: string;
    run_id?: string;
    agent_id?: string;
    scope?: string;
    top_k?: number;
  }) => request<Array<Record<string, unknown>>>("POST", "/api/memory/recall", req),
  listEpisodes: (runId: string) =>
    request<Array<Record<string, unknown>>>("GET", `/api/memory/episodes/${runId}`),
  promote: (req: {
    agent_id: string;
    content?: string;
    summary?: string;
    run_id?: string;
    scope?: string;
    tags?: string[];
  }) => request<Record<string, unknown>>("POST", "/api/memory/promote", req),

  // Agents
  getAgentTree: (runId: string) =>
    request<{ agents: Array<Record<string, unknown>>; edges: Array<Record<string, unknown>> }>(
      "GET",
      `/api/agents/${runId}/tree`
    ),

  // WebSocket URL helper
  wsUrl: (runId: string) => wsUrl(`/ws/${runId}`),

  // Base URL (for displaying in the status bar)
  baseUrl: () => apiUrl("").replace(/\/$/, ""),
};

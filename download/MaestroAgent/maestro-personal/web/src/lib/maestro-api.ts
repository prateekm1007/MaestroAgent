/**
 * Maestro Personal API client.
 *
 * Calls the Maestro Personal FastAPI server (port 8766 in this sandbox).
 * All requests route through the Caddy gateway using the `XTransformPort`
 * query parameter — never write the port in the URL path or host.
 *
 * If the live API is unreachable, every method falls back to demo data
 * so the CEO can see every screen working. The `mode` field on the
 * client tells you whether you're seeing real or demo data.
 */

import {
  demoAskResponse,
  demoAuditLog,
  demoBriefing,
  demoCalibration,
  demoCommitments,
  demoCommitmentsTheOne,
  demoConnectors,
  demoCopilotWhispers,
  demoDrafts,
  demoLlmStatus,
  demoPrivacyMode,
  demoSignals,
  demoTheMoment,
  demoTheShifts,
  demoTranscriptSeed,
  demoPostCallSummary,
} from "./demo-data";

const MAESTRO_PORT = "8766";
const TOKEN_KEY = "maestro.token";
const MODE_KEY = "maestro.mode"; // "live" | "demo"

export type MaestroMode = "live" | "demo" | "unknown";

export type TheMoment = typeof demoTheMoment;
export type Briefing = typeof demoBriefing;
export type TheShifts = typeof demoTheShifts;
export type CommitmentsTheOne = typeof demoCommitmentsTheOne;
export type Commitment = (typeof demoCommitments)[number];
export type Signal = (typeof demoSignals)[number];
export type AskResponse = ReturnType<typeof demoAskResponse>;
export type LlmStatus = typeof demoLlmStatus;
export type PrivacyMode = typeof demoPrivacyMode;
export type Calibration = typeof demoCalibration;
export type AuditLog = typeof demoAuditLog;
export type CopilotWhisper = (typeof demoCopilotWhispers)[number];
export type PostCallSummary = typeof demoPostCallSummary;
export type Connector = (typeof demoConnectors)[number];
export type Draft = (typeof demoDrafts)[number];
export type TranscriptLine = (typeof demoTranscriptSeed)[number];

/* ------------------------------------------------------------------ */
/*  Token + mode storage                                              */
/* ------------------------------------------------------------------ */

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(MODE_KEY);
}

export function getMode(): MaestroMode {
  if (typeof window === "undefined") return "unknown";
  return (window.localStorage.getItem(MODE_KEY) as MaestroMode) || "unknown";
}

function setMode(mode: MaestroMode): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(MODE_KEY, mode);
}

/* ------------------------------------------------------------------ */
/*  Low-level fetch with port routing                                 */
/* ------------------------------------------------------------------ */

async function maestroFetch<T>(
  path: string,
  options: RequestInit = {},
  fallback?: T,
): Promise<{ data: T; live: boolean }> {
  const sep = path.includes("?") ? "&" : "?";
  const url = `${path}${sep}XTransformPort=${MAESTRO_PORT}`;
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    const res = await fetch(url, { ...options, headers, signal: controller.signal });
    clearTimeout(timeout);
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    const data = (await res.json()) as T;
    setMode("live");
    return { data, live: true };
  } catch (err) {
    if (fallback !== undefined) {
      setMode("demo");
      return { data: fallback, live: false };
    }
    throw err;
  }
}

/* ------------------------------------------------------------------ */
/*  Health + login                                                    */
/* ------------------------------------------------------------------ */

export async function checkHealth(): Promise<boolean> {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 4000);
    const res = await fetch(`/api/health?XTransformPort=${MAESTRO_PORT}`, {
      signal: controller.signal,
    });
    clearTimeout(timeout);
    if (!res.ok) return false;
    const j = await res.json();
    return j?.status === "ok";
  } catch {
    return false;
  }
}

export type LoginResult = {
  ok: boolean;
  demo: boolean;
  message: string;
};

export async function login(password: string): Promise<LoginResult> {
  // Try the real API first.
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 6000);
    const res = await fetch(
      `/api/auth/login?XTransformPort=${MAESTRO_PORT}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_email: "default@personal.local", password }),
        signal: controller.signal,
      },
    );
    clearTimeout(timeout);
    if (res.ok) {
      const j = await res.json();
      setToken(j.token);
      setMode("live");
      return { ok: true, demo: false, message: "Logged in to live API." };
    }
    // 401 / 403 from the real API — fall through to demo check below
    // but only if password is "demo". Otherwise re-raise as auth failure.
    if (password !== "demo") {
      return { ok: false, demo: false, message: "Invalid credentials." };
    }
  } catch {
    // Network error — fall through to demo
  }

  // Demo fallback: accept password "demo".
  if (password === "demo") {
    setToken("demo-token");
    setMode("demo");
    return {
      ok: true,
      demo: true,
      message: "Demo mode. Showing sample data — the live API is not reachable.",
    };
  }

  return { ok: false, demo: false, message: "Invalid credentials." };
}

/* ------------------------------------------------------------------ */
/*  Surface endpoints — every method has a demo fallback              */
/* ------------------------------------------------------------------ */

export const maestroApi = {
  async getTheMoment(): Promise<{ data: TheMoment; live: boolean }> {
    return maestroFetch<TheMoment>("/api/the-moment", {}, demoTheMoment);
  },

  async getBriefing(): Promise<{ data: Briefing; live: boolean }> {
    return maestroFetch<Briefing>("/api/briefing", {}, demoBriefing);
  },

  async getTheShifts(): Promise<{ data: TheShifts; live: boolean }> {
    return maestroFetch<TheShifts>("/api/what-changed/the-shifts", {}, demoTheShifts);
  },

  async getCommitments(): Promise<{ data: Commitment[]; live: boolean }> {
    return maestroFetch<Commitment[]>("/api/commitments", {}, demoCommitments);
  },

  async getCommitmentsTheOne(): Promise<{ data: CommitmentsTheOne; live: boolean }> {
    return maestroFetch<CommitmentsTheOne>(
      "/api/commitments/the-one",
      {},
      demoCommitmentsTheOne,
    );
  },

  async getSignals(): Promise<{ data: Signal[]; live: boolean }> {
    return maestroFetch<Signal[]>("/api/signals", {}, demoSignals);
  },

  async createSignal(
    entity: string,
    text: string,
    signal_type: string,
  ): Promise<{ data: Signal; live: boolean }> {
    // Always optimistic — even demo mode echoes back a synthetic signal
    const body = JSON.stringify({ entity, text, signal_type });
    const fallback: Signal = {
      signal_id: `sig_local_${Date.now()}`,
      entity,
      text,
      signal_type,
      timestamp: new Date().toISOString(),
    };
    return maestroFetch<Signal>(
      "/api/signals",
      { method: "POST", body },
      fallback,
    );
  },

  async correctSignal(
    signal_id: string,
    action: "dismiss" | "complete" | "cancel",
  ): Promise<{ data: { ok: boolean }; live: boolean }> {
    const path = `/api/signals/${signal_id}/correct?action=${action}`;
    return maestroFetch<{ ok: boolean }>(
      path,
      { method: "POST" },
      { ok: true },
    );
  },

  async ask(query: string): Promise<{ data: AskResponse; live: boolean }> {
    const body = JSON.stringify({ query });
    return maestroFetch<AskResponse>(
      "/api/ask",
      { method: "POST", body },
      demoAskResponse(query),
    );
  },

  async getLlmStatus(): Promise<{ data: LlmStatus; live: boolean }> {
    return maestroFetch<LlmStatus>("/api/llm-status", {}, demoLlmStatus);
  },

  async getPrivacyMode(): Promise<{ data: PrivacyMode; live: boolean }> {
    return maestroFetch<PrivacyMode>("/api/privacy/mode", {}, demoPrivacyMode);
  },

  async getCalibration(): Promise<{ data: Calibration; live: boolean }> {
    return maestroFetch<Calibration>("/api/calibration", {}, demoCalibration);
  },

  async getAuditLog(): Promise<{ data: AuditLog; live: boolean }> {
    return maestroFetch<AuditLog>("/api/audit-log?limit=50", {}, demoAuditLog);
  },

  async getAccountExport(): Promise<{ data: unknown; live: boolean }> {
    return maestroFetch<unknown>(
      "/api/account/export",
      {},
      {
        exported_at: new Date().toISOString(),
        user_email: "default@personal.local",
        signal_count: demoSignals.length,
        signals: demoSignals,
        note: "Demo export — live API unreachable.",
      },
    );
  },

  async deleteAccount(): Promise<{ data: { ok: boolean }; live: boolean }> {
    return maestroFetch<{ ok: boolean }>(
      "/api/account",
      { method: "DELETE" },
      { ok: true },
    );
  },

  async postTranscript(
    text: string,
    speaker: string,
    entity: string,
  ): Promise<{ data: { whispers?: CopilotWhisper[]; ok: boolean }; live: boolean }> {
    const body = JSON.stringify({ text, speaker, entity, situation_id: "" });
    return maestroFetch<{ whispers?: CopilotWhisper[]; ok: boolean }>(
      "/api/copilot/transcript",
      { method: "POST", body },
      { ok: true, whispers: demoCopilotWhispers },
    );
  },

  async getPostCallSummary(payload: {
    meeting_title?: string;
    duration_seconds?: number;
    participants?: string[];
    transcript_chunks?: Array<{ speaker: string; text: string; timestamp?: string }>;
    suggestion_cards?: Array<Record<string, unknown>>;
    entity?: string;
    talk_ratio_pct?: number;
  }): Promise<{ data: PostCallSummary; live: boolean }> {
    const body = JSON.stringify({
      meeting_title: payload.meeting_title || "Meeting",
      duration_seconds: payload.duration_seconds || 0,
      participants: payload.participants || [],
      transcript_chunks: payload.transcript_chunks || [],
      suggestion_cards: payload.suggestion_cards || [],
      entity: payload.entity || "",
      talk_ratio_pct: payload.talk_ratio_pct || 0,
    });
    return maestroFetch<PostCallSummary>(
      "/api/copilot/post-call-ui",
      { method: "POST", body },
      demoPostCallSummary,
    );
  },

  async listConnectors(): Promise<{ data: { connectors: Connector[] }; live: boolean }> {
    return maestroFetch<{ connectors: Connector[] }>(
      "/api/connectors",
      {},
      { connectors: demoConnectors },
    );
  },

  async connectProvider(
    provider: string,
    oauthToken: string = "",
  ): Promise<{ data: Connector; live: boolean }> {
    const body = JSON.stringify({ provider, oauth_token: oauthToken });
    return maestroFetch<Connector>(
      `/api/connectors/${provider}/connect`,
      { method: "POST", body },
      demoConnectors.find((c) => c.provider === provider) || demoConnectors[0],
    );
  },

  async disconnectProvider(
    provider: string,
  ): Promise<{ data: { provider: string; connected: boolean }; live: boolean }> {
    return maestroFetch<{ provider: string; connected: boolean }>(
      `/api/connectors/${provider}`,
      { method: "DELETE" },
      { provider, connected: false },
    );
  },

  async ingestConnector(
    provider: string,
  ): Promise<{ data: { ingested: number; new_commitments: number; duplicates: number }; live: boolean }> {
    return maestroFetch<{ ingested: number; new_commitments: number; duplicates: number }>(
      `/api/connectors/${provider}/ingest`,
      { method: "POST" },
      { ingested: 4, new_commitments: 3, duplicates: 0 },
    );
  },

  async listDrafts(status: string = "pending"): Promise<{ data: { drafts: Draft[] }; live: boolean }> {
    return maestroFetch<{ drafts: Draft[] }>(
      `/api/drafts?status=${encodeURIComponent(status)}`,
      {},
      { drafts: demoDrafts },
    );
  },

  async createDraft(payload: {
    provider: string;
    recipient: string;
    commitment_text: string;
    entity?: string;
    evidence_refs?: Array<{ entity: string; text: string }>;
  }): Promise<{ data: Draft; live: boolean }> {
    const body = JSON.stringify(payload);
    return maestroFetch<Draft>(
      "/api/drafts",
      { method: "POST", body },
      demoDrafts[0],
    );
  },

  async resolveDraft(
    draftId: string,
    resolution: "approve" | "deny" | "use_draft",
  ): Promise<{ data: { draft_id: string; status: string; sent_message_id?: string }; live: boolean }> {
    const body = JSON.stringify({ resolution });
    return maestroFetch<{ draft_id: string; status: string; sent_message_id?: string }>(
      `/api/drafts/${draftId}/resolve`,
      { method: "POST", body },
      {
        draft_id: draftId,
        status: resolution === "approve" ? "approved" : resolution === "deny" ? "denied" : "used_as_draft",
        sent_message_id: resolution === "approve" ? `msg-${Date.now()}` : "",
      },
    );
  },
};

/* ------------------------------------------------------------------ */
/*  Helpers                                                           */
/* ------------------------------------------------------------------ */

export function confidenceTier(c: number): "high" | "medium" | "low" {
  if (c >= 0.7) return "high";
  if (c >= 0.4) return "medium";
  return "low";
}

export function confidenceColor(c: number): string {
  const tier = confidenceTier(c);
  if (tier === "high") return "bg-emerald-500";
  if (tier === "medium") return "bg-amber-500";
  return "bg-rose-500";
}

export function confidenceTextColor(c: number): string {
  const tier = confidenceTier(c);
  if (tier === "high") return "text-emerald-400";
  if (tier === "medium") return "text-amber-400";
  return "text-rose-400";
}

export function llmDotColor(status: LlmStatus | null): string {
  if (!status) return "bg-zinc-500";
  if (status.active) return "bg-emerald-500";
  if (status.configured) return "bg-amber-500";
  return "bg-zinc-500";
}

export function llmLabel(status: LlmStatus | null): string {
  if (!status) return "Unknown";
  if (status.active) return `LLM · ${status.provider}`;
  if (status.configured) return "LLM · configured, probe failed";
  return "Rule-based";
}

export function formatTimestamp(ts: string): string {
  if (!ts) return "—";
  try {
    const d = new Date(ts);
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return ts;
  }
}

export function formatRelative(ts: string): string {
  if (!ts) return "—";
  try {
    const d = new Date(ts);
    const diffMs = Date.now() - d.getTime();
    const mins = Math.floor(diffMs / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    return `${days}d ago`;
  } catch {
    return ts;
  }
}

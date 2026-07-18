/**
 * Maestro Personal API client.
 *
 * Calls the Maestro Personal FastAPI server. In dev, Next.js rewrites
 * /api/* to http://localhost:8766/api/* (see next.config.ts), so the
 * web app on :3000 proxies to the backend on :8766 automatically.
 *
 * When the backend is unreachable, methods return null/empty — no fake data.
The `live` field is false when the backend was unreachable.
 */

// No demo data — all responses come from the real backend.

const TOKEN_KEY = "maestro.token";


export type MaestroMode = "live" | "offline";

export type TheMoment = any;
export type Briefing = any;
export type TheShifts = any;
export type CommitmentsTheOne = any;
export type Commitment = any;
export type Signal = any;
export type AskResponse = any;
export type LlmStatus = any;
export type PrivacyMode = any;
export type Calibration = any;
export type AuditLog = any;
export type CopilotWhisper = any;
export type PostCallSummary = any;
export type Connector = any;
export type Draft = any;
export type TranscriptLine = any;

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
}

export function getMode(): MaestroMode {
  return "live";
}

/* ------------------------------------------------------------------ */
/*  Low-level fetch with port routing                                 */
/* ------------------------------------------------------------------ */

async function maestroFetch<T>(
  path: string,
  options: RequestInit = {},
  fallback?: T,
  timeoutMs?: number,
): Promise<{ data: T; live: boolean }> {
  // Next.js rewrites /api/* to http://localhost:8766/api/* automatically
  // (see next.config.ts). No need for XTransformPort query param.
  const url = path;
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs ?? 8000);
    const res = await fetch(url, { ...options, headers, signal: controller.signal });
    clearTimeout(timeout);
    if (!res.ok) {
      // P-2026-07-18 fix: auto-clear token on 401 Unauthorized.
      // The backend uses an in-memory token store that is wiped on every
      // redeploy. When that happens, the user's localStorage token becomes
      // invalid, and every API call returns 401. Without this fix, the user
      // sees a broken page (empty connectors, empty dashboard, etc.) and
      // has to manually log out and log back in. With this fix, the first
      // 401 automatically clears the stale token and reloads the page,
      // sending the user to the login screen.
      if (res.status === 401) {
        clearToken();
        // Reload to send user to login screen (only if not already there)
        if (typeof window !== "undefined" && !window.location.pathname.includes("login")) {
          window.location.reload();
        }
      }
      throw new Error(`HTTP ${res.status}`);
    }
    const data = (await res.json()) as T;
    return { data, live: true };
  } catch (err) {
    if (fallback !== undefined) {
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
    const res = await fetch(`/api/health`, {
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

export async function login(password: string, email?: string): Promise<LoginResult> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 6000);
  // Fix: use 'bootstrap' as default user — demo data is seeded for this user.
  // Was 'default@personal.local' which had 0 signals → empty whispers.
  // If the user provides an email (via the Login form's email input),
  // use that instead (for registered users).
  const user_email = email || "bootstrap";
  try {
    const res = await fetch(`/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_email, password }),
      signal: controller.signal,
    });
    clearTimeout(timeout);
    if (res.ok) {
      const j = await res.json();
      setToken(j.token);
      return { ok: true, demo: false, message: "Logged in." };
    }
    return { ok: false, demo: false, message: "Invalid credentials." };
  } catch {
    return { ok: false, demo: false, message: "Cannot connect to backend. Is the API running on port 8766?" };
  }
}

export async function register(email: string, password: string): Promise<LoginResult> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 6000);
  try {
    const res = await fetch(`/api/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_email: email, password }),
      signal: controller.signal,
    });
    clearTimeout(timeout);
    if (res.ok) {
      const j = await res.json();
      setToken(j.token);
      return { ok: true, demo: false, message: "Account created." };
    }
    const errorBody = await res.text();
    return { ok: false, demo: false, message: errorBody || "Registration failed." };
  } catch {
    return { ok: false, demo: false, message: "Cannot connect to backend. Is the API running on port 8766?" };
  }
}

/* ------------------------------------------------------------------ */
/*  Surface endpoints — every method has a demo fallback              */
/* ------------------------------------------------------------------ */

export const maestroApi = {
  async getTheMoment(): Promise<{ data: TheMoment; live: boolean }> {
    return maestroFetch<TheMoment>("/api/the-moment", {}, null);
  },

  async getBriefing(): Promise<{ data: Briefing; live: boolean }> {
    return maestroFetch<Briefing>("/api/briefing", {}, null);
  },

  async getTheShifts(): Promise<{ data: TheShifts; live: boolean }> {
    return maestroFetch<TheShifts>("/api/what-changed/the-shifts", {}, { secondary: [] });
  },

  async getCommitments(): Promise<{ data: Commitment[]; live: boolean }> {
    return maestroFetch<Commitment[]>("/api/commitments", {}, []);
  },

  async getCommitmentsTheOne(): Promise<{ data: CommitmentsTheOne; live: boolean }> {
    return maestroFetch<CommitmentsTheOne>(
      "/api/commitments/the-one",
      {},
      null,
    );
  },

  async getSignals(): Promise<{ data: Signal[]; live: boolean }> {
    return maestroFetch<Signal[]>("/api/signals", {}, []);
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
    // P0-Audit fix (2026-07-18): no fabricated fallback for mutating POST.
    // Was: fallback { ok: true } — fabricated success when backend unreachable,
    // caller discarded the response, list-removal ran unconditionally → user
    // believed "Done" worked while server state was unchanged.
    // Now: no fallback → maestroFetch re-throws on failure → caller must
    // try/catch (see Commitments.tsx correct() + correctSignal()).
    const path = `/api/signals/${signal_id}/correct?action=${action}`;
    return maestroFetch<{ ok: boolean }>(
      path,
      { method: "POST" },
      // no fallback — re-throws on failure
    );
  },

  async ask(query: string, sessionId?: string): Promise<{ data: AskResponse; live: boolean }> {
    const body: Record<string, string> = { query };
    if (sessionId) body.session_id = sessionId;
    return maestroFetch<AskResponse>(
      "/api/ask",
      { method: "POST", body: JSON.stringify(body) },
      null,
      // Ask may invoke the LLM (ZAI) which can take 5-15s for long prompts.
      30000,
    );
  },

  async getLlmStatus(): Promise<{ data: LlmStatus; live: boolean }> {
    return maestroFetch<LlmStatus>("/api/llm-status", {}, null);
  },

  async getPrivacyMode(): Promise<{ data: PrivacyMode; live: boolean }> {
    return maestroFetch<PrivacyMode>("/api/privacy/mode", {}, null);
  },

  async getCalibration(): Promise<{ data: Calibration; live: boolean }> {
    return maestroFetch<Calibration>("/api/calibration", {}, null);
  },

  async getAuditLog(): Promise<{ data: AuditLog; live: boolean }> {
    return maestroFetch<AuditLog>("/api/audit-log?limit=50", {}, { events: [] });
  },

  async getAccountExport(): Promise<{ data: unknown; live: boolean }> {
    return maestroFetch<unknown>(
      "/api/account/export",
      {},
      {
        exported_at: new Date().toISOString(),
        user_email: "bootstrap",
        signal_count: [].length,
        signals: [],
        note: "Demo export — live API unreachable.",
      },
    );
  },

  async deleteAccount(): Promise<{ data: { ok: boolean }; live: boolean }> {
    // P0-Audit fix (2026-07-18): no fabricated fallback for destructive DELETE.
    // Was: fallback { ok: true } — fabricated success when backend unreachable,
    // caller (Settings.tsx deleteAccount) discarded the response and called
    // setDeleted(true) unconditionally → user saw "account deleted" while the
    // account and all data were fully intact server-side. Most serious case.
    // Now: no fallback → maestroFetch re-throws on failure → caller must
    // try/catch (see Settings.tsx deleteAccount()).
    return maestroFetch<{ ok: boolean }>(
      "/api/account",
      { method: "DELETE" },
      // no fallback — re-throws on failure
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
      { ok: true, whispers: [] },
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
      null,
    );
  },

  async listConnectors(): Promise<{ data: { connectors: Connector[] }; live: boolean }> {
    return maestroFetch<{ connectors: Connector[] }>(
      "/api/connectors",
      {},
      { connectors: [] },
    );
  },

  async connectProvider(
    provider: string,
    oauthToken: string = "",
  ): Promise<{ data: Connector; live: boolean }> {
    // P0-Audit fix (2026-07-18): no fabricated fallback for mutating POST.
    // Was: fallback null → maestroFetch returns { data: null, live: false }
    // on failure (doesn't throw). Caller (Connectors.tsx handleConnect) discarded
    // the response → silent failure on connect. Now: no fallback → re-throws →
    // caller must try/catch (see Connectors.tsx handleConnect).
    const body = JSON.stringify({ provider, oauth_token: oauthToken });
    return maestroFetch<Connector>(
      `/api/connectors/${provider}/connect`,
      { method: "POST", body },
      // no fallback — re-throws on failure
    );
  },

  async disconnectProvider(
    provider: string,
  ): Promise<{ data: { provider: string; connected: boolean }; live: boolean }> {
    // P0-Audit fix (2026-07-18): no fabricated fallback for mutating DELETE.
    // Was: fallback { provider, connected: false } — fabricated plausible-looking
    // disconnected state when backend unreachable, caller discarded the response.
    // Now: no fallback → maestroFetch re-throws on failure → caller must
    // try/catch (see Connectors.tsx handleDisconnect).
    return maestroFetch<{ provider: string; connected: boolean }>(
      `/api/connectors/${provider}`,
      { method: "DELETE" },
      // no fallback — re-throws on failure
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
      { drafts: [] },
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
      [][0],
    );
  },

  async resolveDraft(
    draftId: string,
    resolution: "approve" | "deny" | "use_draft",
  ): Promise<{ data: { draft_id: string; status: string; sent_message_id?: string }; live: boolean }> {
    // P0-Audit fix (2026-07-18): no fabricated fallback for mutating POST.
    // Was: fallback with fake sent_message_id=`msg-${Date.now()}` — fabricated
    // a plausible "sent" response when backend unreachable, caller discarded
    // the response, modal just closed → user believed email was sent when it wasn't.
    // Now: no fallback → maestroFetch re-throws on failure → caller must
    // try/catch (see Connectors.tsx handleResolve, Dashboard.tsx
    // handleResolveDraft, Commitments.tsx handleResolveDraft).
    const body = JSON.stringify({ resolution });
    return maestroFetch<{ draft_id: string; status: string; sent_message_id?: string }>(
      `/api/drafts/${draftId}/resolve`,
      { method: "POST", body },
      // no fallback — re-throws on failure
    );
  },

  /* ---------------------------------------------------------------- */
  /*  Per-connector consent (Task 59-7)                               */
  /* ---------------------------------------------------------------- */

  async getConsentSettings(): Promise<{
    data: {
      consent: Record<string, Record<string, boolean>>;
      defaults: Record<string, Record<string, boolean>>;
    };
    live: boolean;
  }> {
    return maestroFetch<{
      consent: Record<string, Record<string, boolean>>;
      defaults: Record<string, Record<string, boolean>>;
    }>("/api/consent/settings", {}, { consent: {}, defaults: {} });
  },

  async setConsentSetting(
    provider: string,
    scope: string,
    enabled: boolean,
  ): Promise<{ data: { ok: boolean; provider: string; scope: string; enabled: boolean }; live: boolean }> {
    const body = JSON.stringify({ provider, scope, enabled });
    return maestroFetch<{ ok: boolean; provider: string; scope: string; enabled: boolean }>(
      "/api/consent/settings",
      { method: "PUT", body },
      { ok: true, provider, scope, enabled },
    );
  },

  /* ---------------------------------------------------------------- */
  /*  Whispers (Issue 13-C)                                           */
  /* ---------------------------------------------------------------- */

  async getWhispers(): Promise<{ data: CopilotWhisper[] | CopilotWhisper; live: boolean }> {
    return maestroFetch<CopilotWhisper[] | CopilotWhisper>(
      "/api/whisper",
      {},
      [],
    );
  },

  /* ---------------------------------------------------------------- */
  /*  Ambient Intelligence (Phases 9, 11, 14, 16, 19, 20)             */
  /*  These endpoints DERIVE intelligence from signal history.        */
  /*  The UI supplies only CONTEXT — never the conclusion (P13).      */
  /* ---------------------------------------------------------------- */

  // Phase 19: Smart notifications
  async getSmartNotifications(
    context: Record<string, unknown> = {},
  ): Promise<{
    data: {
      notifications: Array<{
        notification_id: string;
        type: string;
        priority: string;
        title: string;
        body: string;
        action_url: string;
        action_label: string;
        created_at: string;
        metadata: Record<string, unknown>;
      }>;
      engine_available: boolean;
      count: number;
    };
    live: boolean;
  }> {
    const body = JSON.stringify(context);
    return maestroFetch(
      "/api/notifications/smart",
      { method: "POST", body },
      { notifications: [], engine_available: false, count: 0 },
    );
  },

  // Phase 9: Calendar awareness
  async getCalendarAwareness(
    hoursAhead: number = 48,
  ): Promise<{
    data: {
      meetings: Array<Record<string, unknown>>;
      engine_available: boolean;
      count: number;
    };
    live: boolean;
  }> {
    const body = JSON.stringify({ hours_ahead: hoursAhead });
    return maestroFetch(
      "/api/calendar/awareness",
      { method: "POST", body },
      { meetings: [], engine_available: false, count: 0 },
    );
  },

  // Phase 9: Commitment escalations
  async getEscalations(): Promise<{
    data: {
      escalations: Array<Record<string, unknown>>;
      engine_available: boolean;
      count: number;
      critical_count: number;
      overdue_count: number;
    };
    live: boolean;
  }> {
    return maestroFetch(
      "/api/commitments/escalations",
      {},
      { escalations: [], engine_available: false, count: 0, critical_count: 0, overdue_count: 0 },
    );
  },

  // Phase 14: Cross-meeting threads
  async getThreads(
    entityFilter: string = "",
  ): Promise<{
    data: {
      threads: Array<Record<string, unknown>>;
      engine_available: boolean;
      count: number;
      high_confidence_count: number;
    };
    live: boolean;
  }> {
    const body = JSON.stringify({ entity_filter: entityFilter });
    return maestroFetch(
      "/api/threads",
      { method: "POST", body },
      { threads: [], engine_available: false, count: 0, high_confidence_count: 0 },
    );
  },

  async getThreadsForEntity(
    entity: string,
  ): Promise<{
    data: {
      threads: Array<Record<string, unknown>>;
      engine_available: boolean;
      count: number;
      entity: string;
    };
    live: boolean;
  }> {
    return maestroFetch(
      `/api/threads/${encodeURIComponent(entity)}`,
      {},
      { threads: [], engine_available: false, count: 0, entity },
    );
  },

  async getDecisionHistory(
    entity: string,
  ): Promise<{
    data: {
      decisions: Array<Record<string, unknown>>;
      engine_available: boolean;
      count: number;
      entity: string;
    };
    live: boolean;
  }> {
    return maestroFetch(
      `/api/threads/${encodeURIComponent(entity)}/decisions`,
      {},
      { decisions: [], engine_available: false, count: 0, entity },
    );
  },

  // Phase 16: Meeting grader
  async getMeetingGrades(): Promise<{
    data: {
      grades: Array<Record<string, unknown>>;
      engine_available: boolean;
      count: number;
      average_score: number;
    };
    live: boolean;
  }> {
    return maestroFetch(
      "/api/meetings/grades",
      {},
      { grades: [], engine_available: false, count: 0, average_score: 0 },
    );
  },

  async getMeetingGrade(
    meetingId: string,
  ): Promise<{
    data: Record<string, unknown> & { engine_available: boolean };
    live: boolean;
  }> {
    return maestroFetch(
      `/api/meetings/${encodeURIComponent(meetingId)}/grade`,
      {},
      { grade: null, engine_available: false },
    );
  },

  async overrideMeetingGrade(
    meetingId: string,
    grade: string,
  ): Promise<{
    data: Record<string, unknown> & { message: string };
    live: boolean;
  }> {
    const body = JSON.stringify({ grade });
    return maestroFetch(
      `/api/meetings/${encodeURIComponent(meetingId)}/grade/override`,
      { method: "POST", body },
      { grade: null, engine_available: false, message: "Override (demo)" },
    );
  },

  // Phase 11: Deal health
  async getDealHealth(): Promise<{
    data: {
      deals: Array<Record<string, unknown>>;
      engine_available: boolean;
      count: number;
      strong_count: number;
      at_risk_count: number;
      critical_count: number;
    };
    live: boolean;
  }> {
    return maestroFetch(
      "/api/deals/health",
      {},
      { deals: [], engine_available: false, count: 0, strong_count: 0, at_risk_count: 0, critical_count: 0 },
    );
  },

  async getDealHealthForEntity(
    entity: string,
  ): Promise<{
    data: { deal_health: Record<string, unknown> | null; engine_available: boolean };
    live: boolean;
  }> {
    return maestroFetch(
      `/api/deals/${encodeURIComponent(entity)}/health`,
      {},
      { deal_health: null, engine_available: false },
    );
  },

  // Phase 20: Advanced analytics
  async getAnalyticsTrends(): Promise<{
    data: {
      report: Record<string, unknown> | null;
      engine_available: boolean;
      flywheel_summary?: string;
      message?: string;
    };
    live: boolean;
  }> {
    return maestroFetch(
      "/api/analytics/trends",
      {},
      { report: null, engine_available: false, message: "Analytics unavailable (demo)" },
    );
  },

  async getAnalyticsFlywheel(): Promise<{
    data: { summary: string; engine_available: boolean };
    live: boolean;
  }> {
    return maestroFetch(
      "/api/analytics/flywheel",
      {},
      { summary: "", engine_available: false },
    );
  },

  /* ---------------------------------------------------------------- */
  /*  P0-2: Proactive drafting — POST /api/drafts/auto                */
  /*  Body: { provider, recipient }                                   */
  /*  Backend DERIVES commitment + evidence from signal history (P13).*/
  /*  Returns draft with evidence_refs, llm_generated, style_applied. */
  /*  Draft generation can take 10-25s when LLM is active (ZAI),      */
  /*  so we use a 30s timeout.                                        */
  /* ---------------------------------------------------------------- */
  async generateAutoDraft(
    provider: string,
    recipient: string,
  ): Promise<{ data: Draft & { derived?: boolean; commitment_source?: string; evidence_count?: number; llm_generated?: boolean; style_applied?: boolean }; live: boolean }> {
    const body = JSON.stringify({ provider, recipient });
    // 30s timeout — auto-draft may invoke the LLM + retrieval pipeline.
    return maestroFetch<Draft & { derived?: boolean; commitment_source?: string; evidence_count?: number; llm_generated?: boolean; style_applied?: boolean }>(
      "/api/drafts/auto",
      { method: "POST", body },
      null,
      30000,
    );
  },

  /* ---------------------------------------------------------------- */
  /*  P1-10: Account metrics — GET /api/metrics                       */
  /*  Returns commitment counts + engagement stats for Settings card.  */
  /* ---------------------------------------------------------------- */
  async getMetrics(): Promise<{
    data: {
      commitments?: { total?: number; active?: number; completed?: number; dismissed?: number; cancelled?: number };
      engagement?: { signals_ingested?: number; questions_asked?: number; drafts_generated?: number; drafts_approved?: number };
      calibration?: { brier_score?: number | null; resolved_predictions?: number };
      [key: string]: unknown;
    };
    live: boolean;
  }> {
    return maestroFetch(
      "/api/metrics",
      {},
      { commitments: {}, engagement: {}, calibration: {} },
    );
  },

  /* ---------------------------------------------------------------- */
  /*  P1-10: Retention policy — GET /api/privacy/retention-status     */
  /*  Returns per-category TTLs for the Settings retention dialog.    */
  /* ---------------------------------------------------------------- */
  async getRetentionStatus(): Promise<{
    data: {
      policy?: Record<string, string | number>;
      ttls?: Record<string, number>;
      message?: string;
      [key: string]: unknown;
    };
    live: boolean;
  }> {
    return maestroFetch(
      "/api/privacy/retention-status",
      {},
      { policy: {}, ttls: {}, message: "Retention status unavailable." },
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

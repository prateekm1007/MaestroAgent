/**
 * Zustand store — the single source of truth for the MaestroAgent PWA.
 *
 * Browser-first: all actions go through the `api` client (fetch + WS),
 * not Tauri `invoke`. The store manages:
 * - activeView — which panel is shown
 * - sidecarHealthy + apiUrl — backend connection state
 * - currentRun — the run being watched (or null)
 * - events — stream of events from the current run's WS subscription
 * - templates — list of available workflow templates
 * - liveState — agents + loops + cost snapshot
 * - modals — StartRun / Spawn / Debate / CreateLoop
 */

import { create } from "zustand";
import { api, type RunSummary, type RunEvent, type TemplateEntry, type LiveState } from "../lib/api";
import * as db from "../lib/db";

export type ViewId =
  | "dashboard" | "graph" | "agents" | "loops"
  | "terminal" | "files" | "metrics" | "templates";

export type WSStatus = "idle" | "connecting" | "open" | "reconnecting" | "error" | "closed";

interface AppState {
  activeView: ViewId;
  apiUrl: string;
  sidecarHealthy: boolean;
  online: boolean;
  installable: boolean;
  installPromptEvent: any | null;

  currentRun: RunSummary | null;
  runs: RunSummary[];
  events: RunEvent[];
  templates: TemplateEntry[];
  liveState: LiveState | null;

  // WebSocket state
  wsStatus: WSStatus;
  wsRetryCount: number;
  wsRunId: string | null;

  startRunModalOpen: boolean;
  spawnModalParent: string | null;
  debateModalParticipants: string[] | null;
  createLoopModalOpen: boolean;

  // Recent runs loaded from IndexedDB (for offline browsing)
  cachedRuns: db.CachedRun[];

  setActiveView: (v: ViewId) => void;
  checkHealth: () => Promise<void>;
  loadTemplates: () => Promise<void>;
  startRun: (req: {
    template: string;
    goal: string;
    max_cost_usd?: number;
    default_provider?: string;
    default_model?: string;
  }) => Promise<string>;
  resumeRun: (runId: string, humanInput?: unknown) => Promise<void>;
  cancelRun: (runId: string) => Promise<void>;
  refreshRun: (runId: string) => Promise<void>;
  refreshLiveState: (runId: string) => Promise<void>;
  spawnSubagent: (parentId: string, req: {
    sub_goal: string; role: string; backstory: string;
    tools: string[]; llm_hint: Record<string, string>;
    memory_scope: string; max_iterations: number;
  }) => Promise<void>;
  triggerDebate: (topic: string, participants: string[], seekConsensus: boolean) => Promise<void>;
  createLoop: (req: {
    loop_id: string; body_agent_id: string; exit_kind: string;
    exit_config: Record<string, unknown>; max_iterations: number;
    max_cost_usd?: number; on_exceed: string;
  }) => Promise<void>;
  subscribe: (runId: string) => void;
  unsubscribe: () => void;
  clearEvents: () => void;
  setInstallable: (e: any) => void;
  triggerInstall: () => Promise<void>;
  loadCachedRuns: () => Promise<void>;
  saveGraphDraft: (name: string, description: string, nodes: unknown[], edges: unknown[]) => Promise<void>;
  listGraphDrafts: () => Promise<db.SavedGraph[] | null>;
  deleteGraphDraft: (id: string) => Promise<void>;
  openStartRunModal: () => void;
  closeStartRunModal: () => void;
  openSpawnModal: (parentId: string) => void;
  closeSpawnModal: () => void;
  openDebateModal: (participants: string[]) => void;
  closeDebateModal: () => void;
  openCreateLoopModal: () => void;
  closeCreateLoopModal: () => void;
}

// --- WebSocket manager (module-level, singleton) ---
// We can't use React hooks inside Zustand, so we manage the WS manually
// with the same reconnection logic as useWebSocket.ts.
let wsInstance: WebSocket | null = null;
let wsReconnectTimer: ReturnType<typeof setTimeout> | null = null;
let wsRetryCount = 0;
let wsTargetRunId: string | null = null;

function wsConnect(runId: string, onMessage: (data: unknown) => void) {
  wsDisconnect();
  wsTargetRunId = runId;
  const url = api.wsUrl(runId);
  const setStatus = (status: WSStatus, retry: number) => {
    useAppStore.setState({ wsStatus: status, wsRetryCount: retry });
  };
  setStatus("connecting", wsRetryCount);

  try {
    wsInstance = new WebSocket(url);
  } catch (e) {
    setStatus("error", wsRetryCount);
    wsScheduleReconnect(runId, onMessage);
    return;
  }

  wsInstance.onopen = () => {
    wsRetryCount = 0;
    setStatus("open", 0);
    console.debug("WS connected to", url);
  };

  wsInstance.onmessage = (msg) => {
    try {
      const data = JSON.parse(msg.data);
      onMessage(data);
    } catch (e) {
      console.warn("WS: failed to parse message:", e);
    }
  };

  wsInstance.onerror = (e) => {
    console.warn("WS error:", e);
    setStatus("error", wsRetryCount);
  };

  wsInstance.onclose = () => {
    setStatus("closed", wsRetryCount);
    if (navigator.onLine && wsTargetRunId === runId) {
      wsScheduleReconnect(runId, onMessage);
    }
  };
}

function wsScheduleReconnect(runId: string, onMessage: (data: unknown) => void) {
  const maxRetries = 0; // 0 = infinite
  if (maxRetries > 0 && wsRetryCount >= maxRetries) return;
  const delay = Math.min(1000 * 2 ** wsRetryCount, 30_000);
  wsRetryCount++;
  useAppStore.setState({ wsStatus: "reconnecting", wsRetryCount });
  if (wsReconnectTimer) clearTimeout(wsReconnectTimer);
  wsReconnectTimer = setTimeout(() => {
    if (wsTargetRunId === runId) wsConnect(runId, onMessage);
  }, delay);
}

function wsDisconnect() {
  wsTargetRunId = null;
  if (wsReconnectTimer) {
    clearTimeout(wsReconnectTimer);
    wsReconnectTimer = null;
  }
  if (wsInstance) {
    wsInstance.onclose = null;
    wsInstance.onerror = null;
    wsInstance.onmessage = null;
    wsInstance.onopen = null;
    try { wsInstance.close(); } catch { /* ignore */ }
    wsInstance = null;
  }
  wsRetryCount = 0;
  useAppStore.setState({ wsStatus: "idle", wsRetryCount: 0 });
}

export const useAppStore = create<AppState>((set, get) => ({
  activeView: "dashboard",
  apiUrl: api.baseUrl(),
  sidecarHealthy: false,
  online: navigator.onLine,
  installable: false,
  installPromptEvent: null,

  currentRun: null,
  runs: [],
  events: [],
  templates: [],
  liveState: null,

  wsStatus: "idle",
  wsRetryCount: 0,
  wsRunId: null,

  startRunModalOpen: false,
  spawnModalParent: null,
  debateModalParticipants: null,
  createLoopModalOpen: false,

  cachedRuns: [],

  setActiveView: (v) => set({ activeView: v }),

  checkHealth: async () => {
    try {
      await api.health();
      set({ sidecarHealthy: true });
    } catch {
      set({ sidecarHealthy: false });
    }
  },

  loadTemplates: async () => {
    try {
      const templates = await api.listTemplates();
      set({ templates });
    } catch (e) {
      console.warn("failed to load templates:", e);
      set({ templates: [] });
    }
  },

  startRun: async (req) => {
    const result = await api.startRun(req);
    set({ currentRun: { run_id: result.run_id, status: result.status }, events: [] });
    get().subscribe(result.run_id);
    return result.run_id;
  },

  resumeRun: async (runId, humanInput) => {
    await api.resumeRun(runId, humanInput);
    get().subscribe(runId);
  },

  cancelRun: async (runId) => {
    await api.cancelRun(runId);
  },

  refreshRun: async (runId) => {
    try {
      const run = await api.getRun(runId);
      set({ currentRun: run });
    } catch (e) {
      console.warn("failed to refresh run:", e);
    }
  },

  refreshLiveState: async (runId) => {
    try {
      const live = await api.getLiveState(runId);
      set({ liveState: live });
    } catch (e) {
      console.warn("failed to refresh live state:", e);
    }
  },

  spawnSubagent: async (parentId, req) => {
    const currentRun = get().currentRun;
    if (!currentRun) return;
    await api.spawnSubagent(currentRun.run_id, { parent_id: parentId, ...req });
    set({ spawnModalParent: null });
    get().refreshLiveState(currentRun.run_id);
  },

  triggerDebate: async (topic, participants, seekConsensus) => {
    const currentRun = get().currentRun;
    if (!currentRun) return;
    await api.triggerDebate(currentRun.run_id, {
      topic, participants, seek_consensus: seekConsensus, max_rounds: 3,
    });
    set({ debateModalParticipants: null });
  },

  createLoop: async (req) => {
    const currentRun = get().currentRun;
    if (!currentRun) return;
    await api.createLoop(currentRun.run_id, req);
    set({ createLoopModalOpen: false });
  },

  subscribe: (runId) => {
    set({ wsRunId: runId, events: [] });
    // Load any cached events from IndexedDB first (instant replay).
    db.listEvents(runId).then((cached) => {
      if (cached && cached.length > 0) {
        set({ events: cached as RunEvent[] });
      }
    });
    wsConnect(runId, (data) => {
      const event = data as RunEvent;
      if (event.type === "connected") return;
      set((s) => ({ events: [...s.events.slice(-499), event] }));
      // Persist to IndexedDB for offline replay.
      db.cacheEvent({
        id: event.event_id,
        run_id: event.run_id,
        type: event.type,
        ts: event.ts,
        payload: event.payload,
      });
      if (
        event.type === "run.completed" ||
        event.type === "run.failed" ||
        event.type === "step.completed" ||
        event.type === "loop.exit"
      ) {
        get().refreshRun(runId);
        get().refreshLiveState(runId);
        // Cache the run summary for offline browsing.
        if (event.type === "run.completed" || event.type === "run.failed") {
          const run = get().currentRun;
          if (run) {
            db.cacheRun({
              id: run.run_id,
              run_id: run.run_id,
              status: run.status,
              goal: useAppStore.getState().currentRun?.metadata?.goal as string || "",
              template: useAppStore.getState().currentRun?.metadata?.template as string || "",
              cost_usd: run.cost_usd || 0,
              iteration: run.iteration || 0,
              ts: new Date().toISOString(),
            }).then(() => get().loadCachedRuns());
          }
        }
      }
    });
  },

  unsubscribe: () => {
    wsDisconnect();
    set({ wsRunId: null });
  },

  clearEvents: () => set({ events: [] }),

  loadCachedRuns: async () => {
    const runs = await db.listRuns();
    if (runs) set({ cachedRuns: runs });
  },

  saveGraphDraft: async (name, description, nodes, edges) => {
    const id = `graph_${Date.now().toString(36)}`;
    const now = new Date().toISOString();
    await db.saveGraph({
      id, name, description, nodes, edges, created_at: now, updated_at: now,
    });
  },

  listGraphDrafts: async () => {
    return db.listGraphs();
  },

  deleteGraphDraft: async (id) => {
    await db.deleteGraph(id);
  },

  setInstallable: (e) => set({ installable: true, installPromptEvent: e }),

  triggerInstall: async () => {
    const evt = get().installPromptEvent;
    if (!evt) return;
    evt.prompt();
    const { outcome } = await evt.userChoice;
    set({ installable: false, installPromptEvent: null });
    return outcome;
  },

  openStartRunModal: () => set({ startRunModalOpen: true }),
  closeStartRunModal: () => set({ startRunModalOpen: false }),
  openSpawnModal: (parentId) => set({ spawnModalParent: parentId }),
  closeSpawnModal: () => set({ spawnModalParent: null }),
  openDebateModal: (participants) => set({ debateModalParticipants: participants }),
  closeDebateModal: () => set({ debateModalParticipants: null }),
  openCreateLoopModal: () => set({ createLoopModalOpen: true }),
  closeCreateLoopModal: () => set({ createLoopModalOpen: false }),
}));

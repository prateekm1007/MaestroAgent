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

export type ViewId =
  | "dashboard" | "graph" | "agents" | "loops"
  | "terminal" | "files" | "metrics" | "templates";

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
  ws: WebSocket | null;
  liveState: LiveState | null;

  startRunModalOpen: boolean;
  spawnModalParent: string | null;
  debateModalParticipants: string[] | null;
  createLoopModalOpen: boolean;

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
  openStartRunModal: () => void;
  closeStartRunModal: () => void;
  openSpawnModal: (parentId: string) => void;
  closeSpawnModal: () => void;
  openDebateModal: (participants: string[]) => void;
  closeDebateModal: () => void;
  openCreateLoopModal: () => void;
  closeCreateLoopModal: () => void;
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
  ws: null,
  liveState: null,

  startRunModalOpen: false,
  spawnModalParent: null,
  debateModalParticipants: null,
  createLoopModalOpen: false,

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
    get().unsubscribe();
    const url = api.wsUrl(runId);
    const ws = new WebSocket(url);
    ws.onopen = () => console.debug("WS connected to", url);
    ws.onmessage = (msg) => {
      try {
        const event: RunEvent = JSON.parse(msg.data);
        if (event.type === "connected") return;
        set((s) => ({ events: [...s.events.slice(-499), event] }));
        if (
          event.type === "run.completed" ||
          event.type === "run.failed" ||
          event.type === "step.completed" ||
          event.type === "loop.exit"
        ) {
          get().refreshRun(runId);
          get().refreshLiveState(runId);
        }
      } catch (e) {
        console.warn("failed to parse WS message:", e);
      }
    };
    ws.onerror = (e) => console.warn("WS error:", e);
    ws.onclose = () => console.debug("WS closed");
    set({ ws });
  },

  unsubscribe: () => {
    const ws = get().ws;
    if (ws) { ws.close(); set({ ws: null }); }
  },

  clearEvents: () => set({ events: [] }),

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

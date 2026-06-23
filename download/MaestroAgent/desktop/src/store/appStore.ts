/**
 * Zustand store — the single source of truth for the desktop UI.
 *
 * Holds:
 * - activeView — which panel is currently shown
 * - sidecarHealthy + sidecarUrl — sidecar connection state
 * - currentRun — the run being watched (or null)
 * - runs — list of recent runs (for the dashboard)
 * - events — stream of events from the current run's WS subscription
 * - templates — list of available workflow templates
 *
 * Actions: checkSidecarHealth, startRun, resumeRun, cancelRun, subscribe,
 * setActiveView, etc.
 */

import { create } from "zustand";
import { invoke } from "@tauri-apps/api/core";

export type ViewId =
  | "dashboard"
  | "graph"
  | "agents"
  | "loops"
  | "terminal"
  | "files"
  | "metrics"
  | "templates";

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

interface AppState {
  activeView: ViewId;
  sidecarUrl: string;
  sidecarHealthy: boolean;
  currentRun: RunSummary | null;
  runs: RunSummary[];
  events: RunEvent[];
  templates: TemplateEntry[];
  ws: WebSocket | null;

  setActiveView: (v: ViewId) => void;
  setSidecarUrl: (url: string) => void;
  checkSidecarHealth: () => Promise<void>;
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
  subscribe: (runId: string) => void;
  unsubscribe: () => void;
  clearEvents: () => void;
}

export const useAppStore = create<AppState>((set, get) => ({
  activeView: "dashboard",
  sidecarUrl: "http://localhost:8765",
  sidecarHealthy: false,
  currentRun: null,
  runs: [],
  events: [],
  templates: [],
  ws: null,

  setActiveView: (v) => set({ activeView: v }),
  setSidecarUrl: (url) => set({ sidecarUrl: url }),

  checkSidecarHealth: async () => {
    try {
      const result = await invoke("sidecar_health");
      set({ sidecarHealthy: true });
      // Sidecar returns version, providers, etc.
      console.debug("sidecar health:", result);
    } catch (e) {
      set({ sidecarHealthy: false });
      console.warn("sidecar health check failed:", e);
    }
  },

  loadTemplates: async () => {
    try {
      const templates = await invoke<TemplateEntry[]>("list_templates");
      set({ templates });
    } catch (e) {
      console.warn("failed to load templates:", e);
      set({ templates: [] });
    }
  },

  startRun: async (req) => {
    const result = await invoke<{ run_id: string; status: string }>("start_run", { req });
    set({
      currentRun: { run_id: result.run_id, status: result.status },
      events: [],
    });
    get().subscribe(result.run_id);
    return result.run_id;
  },

  resumeRun: async (runId, humanInput) => {
    await invoke("resume_run", { runId, humanInput });
    get().subscribe(runId);
  },

  cancelRun: async (runId) => {
    await invoke("cancel_run", { runId });
  },

  refreshRun: async (runId) => {
    try {
      const run = await invoke<RunSummary>("get_run", { runId });
      set({ currentRun: run });
    } catch (e) {
      console.warn("failed to refresh run:", e);
    }
  },

  subscribe: (runId) => {
    // Close existing WS.
    get().unsubscribe();

    const url = `${get().sidecarUrl.replace("http", "ws")}/ws/${runId}`;
    const ws = new WebSocket(url);

    ws.onopen = () => {
      console.debug("WS connected to", url);
    };

    ws.onmessage = (msg) => {
      try {
        const event: RunEvent = JSON.parse(msg.data);
        if (event.type === "connected") return;
        set((s) => ({ events: [...s.events.slice(-499), event] }));

        // Refresh run summary on key events.
        if (
          event.type === "run.completed" ||
          event.type === "run.failed" ||
          event.type === "step.completed" ||
          event.type === "loop.exit"
        ) {
          get().refreshRun(runId);
        }
      } catch (e) {
        console.warn("failed to parse WS message:", e);
      }
    };

    ws.onerror = (e) => {
      console.warn("WS error:", e);
    };

    ws.onclose = () => {
      console.debug("WS closed");
    };

    set({ ws });
  },

  unsubscribe: () => {
    const ws = get().ws;
    if (ws) {
      ws.close();
      set({ ws: null });
    }
  },

  clearEvents: () => set({ events: [] }),
}));

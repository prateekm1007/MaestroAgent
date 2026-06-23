import { useEffect } from "react";
import { useAppStore } from "./store/appStore";
import { useOnlineStatus } from "./hooks";
import { useKeyboardShortcuts } from "./hooks/useKeyboardShortcuts";
import Sidebar from "./components/Sidebar";
import TopBar from "./components/TopBar";
import Dashboard from "./components/Dashboard";
import GraphBuilder from "./components/GraphBuilder";
import AgentTree from "./components/AgentTree";
import LoopsPanel from "./components/LoopsPanel";
import Terminal from "./components/Terminal";
import FileBrowser from "./components/FileBrowser";
import Metrics from "./components/Metrics";
import TemplatesGallery from "./components/TemplatesGallery";
import StartRunModal from "./components/StartRunModal";
import SpawnSubagentModal from "./components/SpawnSubagentModal";
import DebateModal from "./components/DebateModal";
import CreateLoopModal from "./components/CreateLoopModal";
import CommandPalette from "./components/CommandPalette";
import { Download, WifiOff, Wifi, Loader2, AlertCircle } from "lucide-react";

export default function App() {
  const activeView = useAppStore((s) => s.activeView);
  const apiUrl = useAppStore((s) => s.apiUrl);
  const checkHealth = useAppStore((s) => s.checkHealth);
  const loadCachedRuns = useAppStore((s) => s.loadCachedRuns);
  const online = useOnlineStatus();
  const { paletteOpen, commands, closePalette } = useKeyboardShortcuts();

  // PWA install prompt capture.
  useEffect(() => {
    const handler = (e: Event) => {
      e.preventDefault();
      useAppStore.getState().setInstallable(e);
    };
    window.addEventListener("beforeinstallprompt", handler);
    return () => window.removeEventListener("beforeinstallprompt", handler);
  }, []);

  // Health-check the backend on mount and every 30s.
  useEffect(() => {
    checkHealth();
    loadCachedRuns();
    const interval = setInterval(checkHealth, 30_000);
    return () => clearInterval(interval);
  }, [checkHealth, loadCachedRuns]);

  return (
    <div className="flex flex-col h-screen w-screen bg-surface-0">
      <TopBar />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-hidden p-4 scrollbar-thin">
          {activeView === "dashboard" && <Dashboard />}
          {activeView === "graph" && <GraphBuilder />}
          {activeView === "agents" && <AgentTree />}
          {activeView === "loops" && <LoopsPanel />}
          {activeView === "terminal" && <Terminal />}
          {activeView === "files" && <FileBrowser />}
          {activeView === "metrics" && <Metrics />}
          {activeView === "templates" && <TemplatesGallery />}
        </main>
      </div>
      <StatusBar apiUrl={apiUrl} online={online} />

      <StartRunModal />
      <SpawnSubagentModal />
      <DebateModal />
      <CreateLoopModal />
      <CommandPalette open={paletteOpen} commands={commands} onClose={closePalette} />
    </div>
  );
}

function StatusBar({ apiUrl, online }: { apiUrl: string; online: boolean }) {
  const currentRun = useAppStore((s) => s.currentRun);
  const sidecarHealthy = useAppStore((s) => s.sidecarHealthy);
  const wsStatus = useAppStore((s) => s.wsStatus);
  const wsRetryCount = useAppStore((s) => s.wsRetryCount);
  const installable = useAppStore((s) => s.installable);
  const triggerInstall = useAppStore((s) => s.triggerInstall);

  return (
    <div className="flex items-center gap-4 px-4 py-1 bg-surface-1 border-t border-surface-3 text-xs text-ink-low font-mono">
      {/* Online/offline */}
      {online ? (
        <Wifi className="w-3 h-3 text-accent-ok" />
      ) : (
        <span className="text-accent-warn flex items-center gap-1">
          <WifiOff className="w-3 h-3" /> offline
        </span>
      )}

      {/* Backend health */}
      <span className={sidecarHealthy ? "text-accent-ok" : "text-accent-err"}>
        ● {sidecarHealthy ? "engine online" : "engine offline"}
      </span>

      {/* WebSocket status */}
      {currentRun && (
        <span className={wsStatusColor(wsStatus)}>
          {wsStatus === "open" && "⟸ ws live"}
          {wsStatus === "connecting" && <><Loader2 className="w-3 h-3 animate-spin inline" /> ws connecting</>}
          {wsStatus === "reconnecting" && <><Loader2 className="w-3 h-3 animate-spin inline" /> ws retry {wsRetryCount}</>}
          {wsStatus === "error" && <><AlertCircle className="w-3 h-3 inline" /> ws error</>}
          {(wsStatus === "closed" || wsStatus === "idle") && "ws idle"}
        </span>
      )}

      <span className="text-surface-4">|</span>
      <span className="truncate">{apiUrl}</span>
      <span className="text-surface-4">|</span>

      {currentRun ? (
        <>
          <span>run: {currentRun.run_id.slice(0, 8)}</span>
          <span className={statusColor(currentRun.status)}>{currentRun.status}</span>
          {currentRun.cost_usd !== undefined && <span>${currentRun.cost_usd.toFixed(4)}</span>}
          {currentRun.iteration !== undefined && <span>iter: {currentRun.iteration}</span>}
        </>
      ) : (
        <span>no active run</span>
      )}

      {/* Keyboard shortcut hint */}
      <span className="ml-auto text-ink-low">
        <kbd className="px-1 py-0.5 bg-surface-2 rounded text-[10px]">⌘K</kbd> commands
      </span>

      {installable && (
        <button onClick={triggerInstall} className="btn-ghost text-xs" title="Install MaestroAgent as a PWA">
          <Download className="w-3 h-3" /> Install App
        </button>
      )}
    </div>
  );
}

function statusColor(status: string): string {
  switch (status) {
    case "running": return "text-accent-info";
    case "succeeded": return "text-accent-ok";
    case "failed": return "text-accent-err";
    case "paused":
    case "awaiting_human": return "text-accent-warn";
    default: return "text-ink-low";
  }
}

function wsStatusColor(status: string): string {
  switch (status) {
    case "open": return "text-accent-ok";
    case "connecting":
    case "reconnecting": return "text-accent-warn";
    case "error": return "text-accent-err";
    default: return "text-ink-low";
  }
}

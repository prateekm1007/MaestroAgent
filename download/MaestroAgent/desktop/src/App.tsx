import { useEffect } from "react";
import { useAppStore } from "./store/appStore";
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

/**
 * App — the MaestroAgent desktop shell.
 *
 * Layout:
 *   ┌────────────────────────────────────────────────────┐
 *   │ TopBar (status, sidecar health, quick actions)     │
 *   ├──┬─────────────────────────────────────────────────┤
 *   │S │                                                 │
 *   │i │  Main panel — switched by `activeView`          │
 *   │d │                                                 │
 *   │e │                                                 │
 *   │b │                                                 │
 *   │a │                                                 │
 *   │r │                                                 │
 *   ├──┴─────────────────────────────────────────────────┤
 *   │ StatusBar (run id, cost, iteration, errors)        │
 *   └────────────────────────────────────────────────────┘
 */
export default function App() {
  const activeView = useAppStore((s) => s.activeView);
  const sidecarUrl = useAppStore((s) => s.sidecarUrl);
  const checkSidecarHealth = useAppStore((s) => s.checkSidecarHealth);

  // Health-check the sidecar on mount and every 30s.
  useEffect(() => {
    checkSidecarHealth();
    const interval = setInterval(checkSidecarHealth, 30_000);
    return () => clearInterval(interval);
  }, [checkSidecarHealth]);

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
      <StatusBar sidecarUrl={sidecarUrl} />
    </div>
  );
}

function StatusBar({ sidecarUrl }: { sidecarUrl: string }) {
  const currentRun = useAppStore((s) => s.currentRun);
  const sidecarHealthy = useAppStore((s) => s.sidecarHealthy);

  return (
    <div className="flex items-center gap-4 px-4 py-1 bg-surface-1 border-t border-surface-3 text-xs text-ink-low font-mono">
      <span className={sidecarHealthy ? "text-accent-ok" : "text-accent-err"}>
        ● {sidecarHealthy ? "sidecar ok" : "sidecar down"}
      </span>
      <span>{sidecarUrl}</span>
      <span className="text-surface-4">|</span>
      {currentRun ? (
        <>
          <span>run: {currentRun.run_id.slice(0, 8)}</span>
          <span className={statusColor(currentRun.status)}>{currentRun.status}</span>
          {currentRun.cost_usd !== undefined && (
            <span>${currentRun.cost_usd.toFixed(4)}</span>
          )}
          {currentRun.iteration !== undefined && (
            <span>iter: {currentRun.iteration}</span>
          )}
        </>
      ) : (
        <span>no active run</span>
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

import { Play, Square, RefreshCw, Settings, Zap } from "lucide-react";
import { useAppStore } from "../store/appStore";

export default function TopBar() {
  const sidecarHealthy = useAppStore((s) => s.sidecarHealthy);
  const currentRun = useAppStore((s) => s.currentRun);
  const cancelRun = useAppStore((s) => s.cancelRun);
  const refreshRun = useAppStore((s) => s.refreshRun);
  const setActiveView = useAppStore((s) => s.setActiveView);

  return (
    <header className="flex items-center justify-between px-4 py-2 bg-surface-1 border-b border-surface-3">
      <div className="flex items-center gap-3">
        <h1 className="text-sm font-semibold text-ink-high">
          The Conductor for AI Agents
        </h1>
        <span
          className={`badge ${sidecarHealthy ? "badge-ok" : "badge-err"}`}
          title="Backend health"
        >
          <span className="w-1.5 h-1.5 rounded-full bg-current" />
          {sidecarHealthy ? "engine online" : "engine offline"}
        </span>
      </div>
      <div className="flex items-center gap-2">
        {currentRun && (
          <>
            <span className="text-xs text-ink-mid font-mono">
              {currentRun.run_id.slice(0, 8)}
            </span>
            <button
              onClick={() => refreshRun(currentRun.run_id)}
              className="btn-ghost"
              title="Refresh"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => cancelRun(currentRun.run_id)}
              className="btn-danger"
              title="Cancel run"
            >
              <Square className="w-3.5 h-3.5" />
              Cancel
            </button>
          </>
        )}
        <button onClick={() => setActiveView("templates")} className="btn-primary">
          <Zap className="w-3.5 h-3.5" />
          New Run
        </button>
        <button className="btn-ghost" title="Settings">
          <Settings className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
}

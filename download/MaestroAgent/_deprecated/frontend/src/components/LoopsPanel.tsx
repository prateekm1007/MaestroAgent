import { useMemo } from "react";
import { useAppStore } from "../store/appStore";
import { useInterval } from "../hooks";
import {
  RefreshCw, CheckCircle2, AlertTriangle, XCircle, Clock, Plus, Activity,
} from "lucide-react";

export default function LoopsPanel() {
  const events = useAppStore((s) => s.events);
  const currentRun = useAppStore((s) => s.currentRun);
  const openCreateLoopModal = useAppStore((s) => s.openCreateLoopModal);
  const refreshLiveState = useAppStore((s) => s.refreshLiveState);

  useInterval(() => currentRun && refreshLiveState(currentRun.run_id), currentRun ? 3000 : null);

  const loops = useMemo(() => {
    const byId: Record<string, {
      id: string; iterations: number; outcome?: string;
      lastScore?: number; conditionReason?: string; startedAt?: string; lastAt?: string;
    }> = {};
    events.forEach((e) => {
      const loopId = e.payload.loop_id as string | undefined;
      if (!loopId) return;
      if (!byId[loopId]) byId[loopId] = { id: loopId, iterations: 0 };
      if (e.type === "loop.iteration") {
        const iter = (e.payload.iteration as number) || 0;
        if (iter > byId[loopId].iterations) byId[loopId].iterations = iter;
        if (e.payload.score !== undefined) byId[loopId].lastScore = e.payload.score as number;
        if (e.payload.condition_reason) byId[loopId].conditionReason = e.payload.condition_reason as string;
        if (!byId[loopId].startedAt) byId[loopId].startedAt = e.ts;
        byId[loopId].lastAt = e.ts;
      }
      if (e.type === "loop.exit") {
        byId[loopId].outcome = e.payload.outcome as string;
        byId[loopId].lastAt = e.ts;
      }
    });
    return Object.values(byId).sort((a, b) => (b.startedAt || "").localeCompare(a.startedAt || ""));
  }, [events]);

  const activeCount = loops.filter((l) => !l.outcome).length;
  const completedCount = loops.filter((l) => l.outcome).length;

  return (
    <div className="h-full flex flex-col gap-4 overflow-hidden">
      <div className="panel p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            <RefreshCw className="w-5 h-5 text-accent-warn" />
            <div>
              <h2 className="text-sm font-semibold">Loops</h2>
              <p className="text-xs text-ink-low">
                Verifiable cycles: run until a condition is met, budget hit, or stagnation detected.
              </p>
            </div>
          </div>
          <button onClick={openCreateLoopModal} disabled={!currentRun} className="btn-primary disabled:opacity-40">
            <Plus className="w-3.5 h-3.5" /> New Loop
          </button>
        </div>
        <div className="grid grid-cols-4 gap-3">
          <MiniStat label="Total" value={loops.length} color="text-ink-high" />
          <MiniStat label="Active" value={activeCount} color="text-accent-info" />
          <MiniStat label="Completed" value={completedCount} color="text-accent-ok" />
          <MiniStat label="Escalated"
            value={loops.filter((l) => l.outcome === "stagnant" || l.outcome === "max_iterations").length}
            color="text-accent-warn" />
        </div>
      </div>
      <div className="panel flex-1 flex flex-col overflow-hidden">
        <div className="panel-header flex items-center justify-between">
          <span>Loop Monitor</span>
          <span className="text-xs text-ink-low font-mono normal-case">
            {currentRun ? currentRun.run_id.slice(0, 8) : "no run"}
          </span>
        </div>
        <div className="flex-1 overflow-y-auto scrollbar-thin p-4">
          {loops.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <Activity className="w-8 h-8 text-ink-low mb-2" />
              <p className="text-sm text-ink-mid">No loops yet</p>
              <p className="text-xs text-ink-low mt-1">
                Loops appear here when an agent enters a verifiable cycle.<br />
                Click "New Loop" to attach one manually.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {loops.map((loop) => <LoopCard key={loop.id} loop={loop} />)}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function MiniStat({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="bg-surface-2 rounded-md p-2">
      <div className="text-[10px] text-ink-low uppercase tracking-wide">{label}</div>
      <div className={`font-mono text-lg ${color}`}>{value}</div>
    </div>
  );
}

function LoopCard({ loop }: {
  loop: {
    id: string; iterations: number; outcome?: string;
    lastScore?: number; conditionReason?: string; startedAt?: string; lastAt?: string;
  };
}) {
  const { outcomeIcon, outcomeLabel, outcomeColor } = (() => {
    if (!loop.outcome) return {
      outcomeIcon: <Clock className="w-4 h-4 text-accent-info" />,
      outcomeLabel: "running", outcomeColor: "text-accent-info",
    };
    switch (loop.outcome) {
      case "exit_condition_met": return {
        outcomeIcon: <CheckCircle2 className="w-4 h-4 text-accent-ok" />,
        outcomeLabel: "condition met", outcomeColor: "text-accent-ok",
      };
      case "stagnant":
      case "budget_exhausted": return {
        outcomeIcon: <AlertTriangle className="w-4 h-4 text-accent-warn" />,
        outcomeLabel: loop.outcome.replace("_", " "), outcomeColor: "text-accent-warn",
      };
      case "max_iterations":
      case "error": return {
        outcomeIcon: <XCircle className="w-4 h-4 text-accent-err" />,
        outcomeLabel: loop.outcome.replace("_", " "), outcomeColor: "text-accent-err",
      };
      default: return {
        outcomeIcon: <RefreshCw className="w-4 h-4 text-accent-info" />,
        outcomeLabel: loop.outcome, outcomeColor: "text-accent-info",
      };
    }
  })();

  const progress = Math.min(100, (loop.iterations / 20) * 100);
  const scoreColor = loop.lastScore === undefined ? "text-ink-low"
    : loop.lastScore >= 0.85 ? "text-accent-ok"
    : loop.lastScore >= 0.5 ? "text-accent-warn" : "text-accent-err";

  return (
    <div className="bg-surface-2 border border-surface-3 rounded-md p-3 hover:border-surface-4 transition-colors">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <RefreshCw className={`w-4 h-4 ${loop.outcome ? "text-ink-low" : "text-accent-warn animate-spin-slow"}`} />
          <span className="text-sm font-mono text-ink-high">{loop.id}</span>
        </div>
        <div className="flex items-center gap-2">
          {outcomeIcon}
          <span className={`text-xs ${outcomeColor}`}>{outcomeLabel}</span>
        </div>
      </div>
      <div className="flex items-center gap-4 text-xs text-ink-mid mb-2">
        <span>iter: <span className="font-mono text-ink-high">{loop.iterations}</span></span>
        {loop.lastScore !== undefined && (
          <span>score: <span className={`font-mono ${scoreColor}`}>{loop.lastScore.toFixed(2)}</span></span>
        )}
        {loop.startedAt && (
          <span className="text-ink-low">started: <span className="font-mono">{formatTime(loop.startedAt)}</span></span>
        )}
      </div>
      {loop.conditionReason && (
        <div className="text-xs text-ink-low mb-2 italic">"{loop.conditionReason}"</div>
      )}
      <div className="h-1.5 bg-surface-4 rounded overflow-hidden">
        <div
          className={`h-full transition-all ${
            loop.outcome === "exit_condition_met" ? "bg-accent-ok"
              : loop.outcome ? "bg-accent-err" : "bg-maestro-500"
          }`}
          style={{ width: `${progress}%` }}
        />
      </div>
    </div>
  );
}

function formatTime(ts: string): string {
  try {
    const d = new Date(ts);
    return d.toLocaleTimeString("en-US", { hour12: false });
  } catch { return ts.slice(11, 19); }
}

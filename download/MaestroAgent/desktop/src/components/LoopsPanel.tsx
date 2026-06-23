import { useMemo } from "react";
import { useAppStore } from "../store/appStore";
import { RefreshCw, CheckCircle2, AlertTriangle, XCircle, Clock } from "lucide-react";

/** Loops panel — shows active and historical loops for the current run. */
export default function LoopsPanel() {
  const events = useAppStore((s) => s.events);

  // Group loop events by loop_id.
  const loops = useMemo(() => {
    const byId: Record<string, { id: string; iterations: number; outcome?: string; lastScore?: number }> = {};
    events.forEach((e) => {
      const loopId = e.payload.loop_id as string | undefined;
      if (!loopId) return;
      if (!byId[loopId]) byId[loopId] = { id: loopId, iterations: 0 };
      if (e.type === "loop.iteration") {
        byId[loopId].iterations = Math.max(
          byId[loopId].iterations,
          (e.payload.iteration as number) || 0
        );
        if (e.payload.score !== undefined) {
          byId[loopId].lastScore = e.payload.score as number;
        }
      }
      if (e.type === "loop.exit") {
        byId[loopId].outcome = e.payload.outcome as string;
      }
    });
    return Object.values(byId);
  }, [events]);

  return (
    <div className="panel h-full flex flex-col">
      <div className="panel-header">Loops</div>
      <div className="flex-1 overflow-y-auto scrollbar-thin p-4">
        {loops.length === 0 ? (
          <div className="text-ink-low text-sm">
            No loops yet. Loops appear here when an agent enters a verifiable cycle.
          </div>
        ) : (
          <div className="space-y-3">
            {loops.map((loop) => (
              <LoopCard key={loop.id} loop={loop} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function LoopCard({
  loop,
}: {
  loop: { id: string; iterations: number; outcome?: string; lastScore?: number };
}) {
  const outcomeIcon = (() => {
    if (!loop.outcome) return <Clock className="w-4 h-4 text-accent-info" />;
    switch (loop.outcome) {
      case "exit_condition_met": return <CheckCircle2 className="w-4 h-4 text-accent-ok" />;
      case "stagnant":
      case "budget_exhausted": return <AlertTriangle className="w-4 h-4 text-accent-warn" />;
      case "max_iterations":
      case "error": return <XCircle className="w-4 h-4 text-accent-err" />;
      default: return <RefreshCw className="w-4 h-4 text-accent-info" />;
    }
  })();

  const progress = Math.min(100, (loop.iterations / 20) * 100); // assume 20 max for the bar

  return (
    <div className="bg-surface-2 border border-surface-3 rounded-md p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <RefreshCw className="w-4 h-4 text-accent-warn" />
          <span className="text-sm font-mono text-ink-high">{loop.id}</span>
        </div>
        <div className="flex items-center gap-2">
          {outcomeIcon}
          <span className="text-xs text-ink-low">
            {loop.outcome || "running"}
          </span>
        </div>
      </div>
      <div className="flex items-center gap-3 text-xs text-ink-mid">
        <span>iter: <span className="font-mono text-ink-high">{loop.iterations}</span></span>
        {loop.lastScore !== undefined && (
          <span>
            score: <span className="font-mono text-ink-high">{loop.lastScore.toFixed(2)}</span>
          </span>
        )}
      </div>
      <div className="mt-2 h-1 bg-surface-4 rounded overflow-hidden">
        <div
          className="h-full bg-maestro-500 transition-all"
          style={{ width: `${progress}%` }}
        />
      </div>
    </div>
  );
}

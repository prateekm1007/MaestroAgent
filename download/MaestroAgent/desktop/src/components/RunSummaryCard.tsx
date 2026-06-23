import { useAppStore, RunSummary } from "../store/appStore";
import { Activity, DollarSign, Cpu, AlertTriangle } from "lucide-react";

export default function RunSummaryCard({ run }: { run: RunSummary | null }) {
  if (!run) {
    return (
      <div className="panel p-6 text-center">
        <Activity className="w-8 h-8 text-ink-low mx-auto mb-2" />
        <p className="text-sm text-ink-mid">No active run</p>
        <p className="text-xs text-ink-low mt-1">
          Pick a template from the sidebar to start.
        </p>
      </div>
    );
  }

  return (
    <div className="panel p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold">Active Run</h2>
        <span className={`badge ${statusBadge(run.status)}`}>
          {run.status}
        </span>
      </div>
      <div className="grid grid-cols-4 gap-3 text-sm">
        <Metric icon={DollarSign} label="Cost" value={`$${(run.cost_usd ?? 0).toFixed(4)}`} />
        <Metric icon={Activity} label="Iteration" value={String(run.iteration ?? 0)} />
        <Metric icon={Cpu} label="Node" value={run.current_node ?? "—"} />
        <Metric
          icon={AlertTriangle}
          label="Errors"
          value={run.error ? "1" : "0"}
          danger={!!run.error}
        />
      </div>
      {run.error && (
        <div className="mt-3 text-xs font-mono p-2 bg-accent-err/10 text-accent-err rounded">
          {run.error}
        </div>
      )}
    </div>
  );
}

function Metric({
  icon: Icon,
  label,
  value,
  danger,
}: {
  icon: typeof DollarSign;
  label: string;
  value: string;
  danger?: boolean;
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-1.5 text-xs text-ink-low">
        <Icon className={`w-3 h-3 ${danger ? "text-accent-err" : ""}`} />
        {label}
      </div>
      <div className={`font-mono text-lg ${danger ? "text-accent-err" : "text-ink-high"}`}>
        {value}
      </div>
    </div>
  );
}

function statusBadge(status: string): string {
  switch (status) {
    case "running": return "badge-info";
    case "succeeded": return "badge-ok";
    case "failed": return "badge-err";
    case "paused":
    case "awaiting_human": return "badge-warn";
    default: return "badge-info";
  }
}

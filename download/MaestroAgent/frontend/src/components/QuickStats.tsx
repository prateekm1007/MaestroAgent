import { useAppStore } from "../store/appStore";
import { Zap, Cpu, AlertCircle, Activity } from "lucide-react";

export default function QuickStats() {
  const events = useAppStore((s) => s.events);
  const llmCalls = events.filter((e) => e.type === "llm.call.completed").length;
  const toolCalls = events.filter((e) => e.type === "tool.call.completed").length;
  const errors = events.filter((e) => e.type.endsWith(".failed") || e.type === "budget.warning").length;
  const loopIters = events.filter((e) => e.type === "loop.iteration").length;
  const now = Date.now();
  const recent = events.filter((e) => {
    try { return now - new Date(e.ts).getTime() < 10_000; } catch { return false; }
  });
  const eventsPerSec = recent.length / 10;

  return (
    <div className="panel">
      <div className="panel-header">Quick Stats</div>
      <div className="grid grid-cols-2 gap-3 p-3 text-sm">
        <Stat icon={Activity} label="Events/sec" value={eventsPerSec.toFixed(1)} color="text-accent-info" />
        <Stat icon={Zap} label="LLM calls" value={String(llmCalls)} color="text-accent-ok" />
        <Stat icon={Cpu} label="Tool calls" value={String(toolCalls)} color="text-maestro-300" />
        <Stat icon={AlertCircle} label="Errors" value={String(errors)} color={errors > 0 ? "text-accent-err" : "text-ink-mid"} />
        <Stat icon={Zap} label="Loop iters" value={String(loopIters)} color="text-accent-warn" />
      </div>
    </div>
  );
}

function Stat({ icon: Icon, label, value, color }: {
  icon: typeof Zap; label: string; value: string; color: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-1.5 text-xs text-ink-low">
        <Icon className={`w-3 h-3 ${color}`} />
        {label}
      </div>
      <div className={`font-mono text-base ${color}`}>{value}</div>
    </div>
  );
}

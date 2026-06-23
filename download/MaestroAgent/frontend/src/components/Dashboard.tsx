import { useEffect } from "react";
import { useAppStore } from "../store/appStore";
import EventStream from "./EventStream";
import RunSummaryCard from "./RunSummaryCard";
import QuickStats from "./QuickStats";

export default function Dashboard() {
  const currentRun = useAppStore((s) => s.currentRun);
  const events = useAppStore((s) => s.events);
  const loadTemplates = useAppStore((s) => s.loadTemplates);

  useEffect(() => { loadTemplates(); }, [loadTemplates]);

  return (
    <div className="grid grid-cols-12 gap-4 h-full">
      <div className="col-span-8 flex flex-col gap-4 overflow-hidden">
        <RunSummaryCard run={currentRun} />
        <div className="panel flex-1 flex flex-col overflow-hidden">
          <div className="panel-header flex items-center justify-between">
            <span>Live Event Stream</span>
            <span className="text-xs text-ink-low normal-case font-mono">{events.length} events</span>
          </div>
          <EventStream events={events} />
        </div>
      </div>
      <div className="col-span-4 flex flex-col gap-4 overflow-hidden">
        <QuickStats />
        <div className="panel flex-1 overflow-hidden flex flex-col">
          <div className="panel-header">Run Status</div>
          <div className="p-4 overflow-y-auto scrollbar-thin text-sm space-y-3">
            {currentRun ? (
              <>
                <Row label="Run ID" value={currentRun.run_id} mono />
                <Row label="Status" value={currentRun.status} />
                <Row label="Iteration" value={String(currentRun.iteration ?? 0)} />
                <Row label="Cost" value={`$${(currentRun.cost_usd ?? 0).toFixed(4)}`} />
                <Row label="Node" value={currentRun.current_node ?? "—"} mono />
                {currentRun.error && (
                  <div className="text-accent-err text-xs font-mono p-2 bg-accent-err/10 rounded">
                    {currentRun.error}
                  </div>
                )}
              </>
            ) : (
              <div className="text-ink-low text-xs">No active run. Start one from Templates.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex justify-between gap-2">
      <span className="text-ink-low">{label}</span>
      <span className={`text-ink-high text-right truncate ${mono ? "font-mono text-xs" : ""}`}>{value}</span>
    </div>
  );
}

import { useAppStore, RunEvent } from "../store/appStore";

/** Scrollable list of events with type icons and color coding. */
export default function EventStream({ events }: { events: RunEvent[] }) {
  return (
    <div className="flex-1 overflow-y-auto scrollbar-thin font-mono text-xs">
      {events.length === 0 ? (
        <div className="p-4 text-ink-low">
          Waiting for events. Start a run to see live activity.
        </div>
      ) : (
        <ul className="divide-y divide-surface-2">
          {events.map((e) => (
            <li key={e.event_id} className="px-3 py-1.5 flex gap-3 hover:bg-surface-2">
              <span className="text-ink-low flex-shrink-0">{formatTime(e.ts)}</span>
              <span className={`flex-shrink-0 ${typeColor(e.type)}`}>
                {e.type}
              </span>
              <span className="text-ink-mid truncate">
                {summarize(e)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function formatTime(ts: string): string {
  try {
    const d = new Date(ts);
    return d.toLocaleTimeString("en-US", { hour12: false }) + "." +
      String(d.getMilliseconds()).padStart(3, "0");
  } catch {
    return ts.slice(11, 23);
  }
}

function typeColor(type: string): string {
  if (type.startsWith("run.")) return "text-maestro-300";
  if (type.startsWith("step.")) return "text-accent-info";
  if (type.startsWith("loop.")) return "text-accent-warn";
  if (type.startsWith("llm.")) return "text-accent-ok";
  if (type.startsWith("tool.")) return "text-accent-info";
  if (type.startsWith("agent.")) return "text-maestro-400";
  if (type.startsWith("hitl.")) return "text-accent-err";
  if (type.startsWith("budget.")) return "text-accent-err";
  return "text-ink-mid";
}

function summarize(e: RunEvent): string {
  const p = e.payload;
  const bits: string[] = [];
  for (const k of ["node_id", "loop_id", "iteration", "agent_id", "provider", "model", "outcome", "error", "reason", "score"]) {
    if (k in p && p[k] !== undefined && p[k] !== null) {
      bits.push(`${k}=${JSON.stringify(p[k])}`);
    }
  }
  return bits.join(" ");
}

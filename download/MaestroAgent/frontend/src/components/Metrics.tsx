import { useEffect, useState } from "react";
import { useAppStore } from "../store/appStore";
import { api, type CostResponse } from "../lib/api";
import {
  DollarSign, Cpu, TrendingUp, AlertTriangle, Activity, Zap,
  Sparkles, RefreshCw, Download,
} from "lucide-react";

export default function Metrics() {
  const currentRun = useAppStore((s) => s.currentRun);
  const events = useAppStore((s) => s.events);
  const [cost, setCost] = useState<CostResponse | null>(null);

  useEffect(() => {
    if (!currentRun) return;
    let active = true;
    const load = async () => {
      try {
        const result = await api.getCost(currentRun.run_id);
        if (active) setCost(result);
      } catch (e) { console.warn("failed to load cost:", e); }
    };
    load();
    const interval = setInterval(load, 5000);
    return () => { active = false; clearInterval(interval); };
  }, [currentRun]);

  const llmCalls = events.filter((e) => e.type === "llm.call.completed").length;
  const toolCalls = events.filter((e) => e.type === "tool.call.completed").length;
  const errors = events.filter((e) => e.type.endsWith(".failed")).length;
  const tokensIn = events.filter((e) => e.type === "llm.call.completed")
    .reduce((sum, e) => sum + ((e.payload.prompt_tokens as number) || 0), 0);
  const tokensOut = events.filter((e) => e.type === "llm.call.completed")
    .reduce((sum, e) => sum + ((e.payload.completion_tokens as number) || 0), 0);

  if (!currentRun) {
    return (
      <div className="panel h-full flex items-center justify-center">
        <div className="text-center">
          <Activity className="w-8 h-8 text-ink-low mx-auto mb-2" />
          <p className="text-sm text-ink-mid">No active run</p>
          <p className="text-xs text-ink-low mt-1">Start a run to see metrics.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto scrollbar-thin space-y-4">
      <div className="grid grid-cols-4 gap-3">
        <StatCard icon={DollarSign} label="Total Cost" value={`$${(cost?.total_usd ?? 0).toFixed(4)}`} color="text-accent-ok" />
        <StatCard icon={Zap} label="LLM Calls" value={String(llmCalls)} color="text-maestro-300" />
        <StatCard icon={Cpu} label="Tool Calls" value={String(toolCalls)} color="text-accent-info" />
        <StatCard icon={AlertTriangle} label="Errors" value={String(errors)} color={errors > 0 ? "text-accent-err" : "text-ink-mid"} />
      </div>

      <div className="panel">
        <div className="panel-header flex items-center gap-2">
          <TrendingUp className="w-3.5 h-3.5" /> Token Usage
        </div>
        <div className="p-4 grid grid-cols-3 gap-4">
          <TokenStat label="Prompt (in)" value={tokensIn} color="text-accent-info" />
          <TokenStat label="Completion (out)" value={tokensOut} color="text-accent-ok" />
          <TokenStat label="Total" value={tokensIn + tokensOut} color="text-ink-high" />
        </div>
        <div className="px-4 pb-4">
          <TokenBar inTokens={tokensIn} outTokens={tokensOut} />
        </div>
      </div>

      <div className="panel">
        <div className="panel-header flex items-center justify-between">
          <span>Cost Breakdown by Provider</span>
          <span className="text-xs text-ink-low font-mono normal-case">{cost?.breakdown.length ?? 0} providers</span>
        </div>
        <div className="overflow-x-auto">
          {cost && cost.breakdown.length > 0 ? (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-surface-3 text-left text-xs text-ink-low uppercase tracking-wide">
                  <th className="px-4 py-2">Provider</th>
                  <th className="px-4 py-2">Model</th>
                  <th className="px-4 py-2 text-right">Prompt tok</th>
                  <th className="px-4 py-2 text-right">Completion tok</th>
                  <th className="px-4 py-2 text-right">Calls</th>
                  <th className="px-4 py-2 text-right">Cost USD</th>
                  <th className="px-4 py-2">Share</th>
                </tr>
              </thead>
              <tbody>
                {cost.breakdown.map((b, i) => (
                  <tr key={i} className="border-b border-surface-2 hover:bg-surface-2">
                    <td className="px-4 py-2 font-mono text-xs text-maestro-300">{b.provider}</td>
                    <td className="px-4 py-2 font-mono text-xs text-ink-mid">{b.model}</td>
                    <td className="px-4 py-2 text-right font-mono text-xs">{b.prompt_tokens.toLocaleString()}</td>
                    <td className="px-4 py-2 text-right font-mono text-xs">{b.completion_tokens.toLocaleString()}</td>
                    <td className="px-4 py-2 text-right font-mono text-xs">{b.calls}</td>
                    <td className="px-4 py-2 text-right font-mono text-xs text-accent-ok">${b.cost_usd.toFixed(4)}</td>
                    <td className="px-4 py-2">
                      <div className="h-1.5 bg-surface-4 rounded overflow-hidden w-24">
                        <div className="h-full bg-maestro-500"
                          style={{ width: `${(b.cost_usd / Math.max(cost.total_usd, 0.0001)) * 100}%` }} />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t-2 border-surface-3">
                  <td colSpan={5} className="px-4 py-2 text-right text-xs text-ink-low uppercase">Total</td>
                  <td className="px-4 py-2 text-right font-mono text-sm text-accent-ok font-semibold">
                    ${cost.total_usd.toFixed(4)}
                  </td>
                  <td />
                </tr>
              </tfoot>
            </table>
          ) : (
            <div className="p-4 text-sm text-ink-low">No cost data yet.</div>
          )}
        </div>
      </div>

      <div className="panel">
        <div className="panel-header">Loop Iterations Over Time</div>
        <div className="p-4"><IterationHistogram events={events} /></div>
      </div>

      <MetaRecommendations />

      <div className="panel">
        <div className="panel-header">Export Project</div>
        <div className="p-4 flex items-center justify-between">
          <div>
            <p className="text-sm text-ink-mid">Download this run as a portable JSON project.</p>
            <p className="text-xs text-ink-low mt-1">
              Includes graph, state history, cost breakdown, and audit log.
            </p>
          </div>
          <button
            onClick={async () => {
              if (!currentRun) return;
              try {
                const project = await api.exportProject(currentRun.run_id);
                const blob = new Blob([JSON.stringify(project, null, 2)], { type: "application/json" });
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = `maestro-project-${currentRun.run_id.slice(0, 8)}.json`;
                a.click();
                URL.revokeObjectURL(url);
              } catch (e) {
                console.warn("export failed:", e);
              }
            }}
            className="btn-primary"
          >
            <Download className="w-3.5 h-3.5" /> Export JSON
          </button>
        </div>
      </div>
    </div>
  );
}

function MetaRecommendations() {
  const [recs, setRecs] = useState<Array<Record<string, unknown>>>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true); setError(null);
    try {
      const data = await api.getMetaRecommendations(20);
      setRecs(data.recommendations || []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  return (
    <div className="panel">
      <div className="panel-header flex items-center justify-between">
        <span className="flex items-center gap-2">
          <Sparkles className="w-3.5 h-3.5 text-maestro-400" />
          Meta-Agent Recommendations
        </span>
        <button onClick={load} disabled={loading} className="btn-ghost text-xs">
          <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} />
          {loading ? "Analyzing..." : "Refresh"}
        </button>
      </div>
      <div className="p-4">
        {error && (
          <div className="text-xs text-accent-err p-2 bg-accent-err/10 rounded font-mono mb-2">{error}</div>
        )}
        {recs.length === 0 && !loading ? (
          <div className="text-sm text-ink-low">
            No recommendations yet. Run a few workflows first to give the meta-agent data to analyze.
          </div>
        ) : (
          <div className="space-y-2">
            {recs.map((rec, i) => (
              <div key={i} className="bg-surface-2 border border-surface-3 rounded-md p-3">
                <div className="flex items-center gap-2 mb-1">
                  <span className={`badge text-[10px] ${
                    rec.severity === "critical" ? "badge-err"
                      : rec.severity === "warn" ? "badge-warn" : "badge-info"
                  }`}>{rec.severity as string}</span>
                  <span className="text-sm font-semibold text-ink-high">{rec.title as string}</span>
                </div>
                <p className="text-xs text-ink-mid mb-1">{rec.description as string}</p>
                <div className="flex items-center gap-3 text-[10px] text-ink-low">
                  <span>target: <code className="text-maestro-300">{rec.target as string}</code></span>
                  {rec.expected_savings_usd ? (
                    <span className="text-accent-ok">save ~${(rec.expected_savings_usd as number).toFixed(2)}</span>
                  ) : null}
                  <span>confidence: {((rec.confidence as number) * 100).toFixed(0)}%</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({ icon: Icon, label, value, color }: {
  icon: typeof DollarSign; label: string; value: string; color: string;
}) {
  return (
    <div className="panel p-4">
      <div className="flex items-center gap-1.5 text-xs text-ink-low mb-1">
        <Icon className={`w-3 h-3 ${color}`} /> {label}
      </div>
      <div className={`font-mono text-xl ${color}`}>{value}</div>
    </div>
  );
}

function TokenStat({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div>
      <div className="text-xs text-ink-low mb-1">{label}</div>
      <div className={`font-mono text-lg ${color}`}>{value.toLocaleString()}</div>
    </div>
  );
}

function TokenBar({ inTokens, outTokens }: { inTokens: number; outTokens: number }) {
  const total = Math.max(inTokens + outTokens, 1);
  const inPct = (inTokens / total) * 100;
  return (
    <div>
      <div className="flex h-3 rounded overflow-hidden">
        <div className="bg-accent-info" style={{ width: `${inPct}%` }} title={`prompt: ${inTokens}`} />
        <div className="bg-accent-ok" style={{ width: `${100 - inPct}%` }} title={`completion: ${outTokens}`} />
      </div>
      <div className="flex justify-between text-xs text-ink-low mt-1">
        <span><span className="inline-block w-2 h-2 bg-accent-info rounded-full mr-1" />prompt {inPct.toFixed(0)}%</span>
        <span><span className="inline-block w-2 h-2 bg-accent-ok rounded-full mr-1" />completion {(100 - inPct).toFixed(0)}%</span>
      </div>
    </div>
  );
}

function IterationHistogram({ events }: { events: ReturnType<typeof useAppStore.getState>["events"] }) {
  const byLoop: Record<string, number[]> = {};
  events.forEach((e) => {
    if (e.type !== "loop.iteration") return;
    const id = e.payload.loop_id as string;
    if (!id) return;
    if (!byLoop[id]) byLoop[id] = [];
    byLoop[id].push((e.payload.score as number) || 0);
  });
  const loops = Object.entries(byLoop);
  if (loops.length === 0) return <div className="text-sm text-ink-low">No loop iterations recorded.</div>;
  return (
    <div className="space-y-3">
      {loops.map(([id, scores]) => {
        const max = Math.max(...scores, 1);
        return (
          <div key={id}>
            <div className="flex justify-between text-xs text-ink-mid mb-1">
              <span className="font-mono">{id}</span><span>{scores.length} iters</span>
            </div>
            <div className="flex items-end gap-0.5 h-12">
              {scores.map((s, i) => (
                <div key={i} className="flex-1 bg-maestro-500 hover:bg-maestro-400 transition-colors rounded-t"
                  style={{ height: `${(s / max) * 100}%`, minHeight: "2px" }}
                  title={`iter ${i + 1}: score=${s.toFixed(2)}`} />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

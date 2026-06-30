import { useState } from "react";
import { useAppStore } from "../store/appStore";
import { X, RefreshCw, CheckCircle2, AlertTriangle, GitBranch, Layers, Sparkles } from "lucide-react";

type LoopKind = "simple" | "nested" | "parallel" | "meta";

const LOOP_KIND_META: Record<LoopKind, { label: string; description: string; icon: typeof RefreshCw }> = {
  simple: { label: "Simple Loop", description: "Run body until exit condition met.", icon: RefreshCw },
  nested: { label: "Nested Loop", description: "Loop whose body is another loop. Outer → inner.", icon: GitBranch },
  parallel: { label: "Parallel Loop", description: "Run N independent loops concurrently, merge results.", icon: Layers },
  meta: { label: "Meta Loop", description: "Supervisor picks which child loop to run each iteration.", icon: Sparkles },
};

export default function CreateLoopModal() {
  const isOpen = useAppStore((s) => s.createLoopModalOpen);
  const close = useAppStore((s) => s.closeCreateLoopModal);
  const createLoop = useAppStore((s) => s.createLoop);
  const liveState = useAppStore((s) => s.liveState);

  const [loopKind, setLoopKind] = useState<LoopKind>("simple");
  const [loopId, setLoopId] = useState("");
  const [bodyAgentId, setBodyAgentId] = useState("");
  // For parallel/meta: comma-separated child loop ids or agent ids.
  const [childAgents, setChildAgents] = useState("");
  const [exitKind, setExitKind] = useState<"tests" | "metric" | "critic" | "callable">("tests");
  const [testCommand, setTestCommand] = useState("pytest -x --tb=short");
  const [metricKey, setMetricKey] = useState("test_pass_rate");
  const [metricThreshold, setMetricThreshold] = useState(0.9);
  const [metricComparator, setMetricComparator] = useState(">=");
  const [criticRubric, setCriticRubric] = useState("");
  const [criticThreshold, setCriticThreshold] = useState(0.85);
  const [maxIters, setMaxIters] = useState(20);
  const [maxCost, setMaxCost] = useState(5);
  const [onExceed, setOnExceed] = useState<"escalate" | "pause" | "fail" | "continue">("escalate");
  const [launching, setLaunching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const agentIds = (liveState?.agents || []).map((a) => a.id);

  const handleSubmit = async () => {
    if (!loopId.trim()) { setError("Loop ID is required."); return; }
    if ((loopKind === "simple" || loopKind === "nested") && !bodyAgentId) {
      setError("Body agent is required for this loop kind."); return;
    }
    if ((loopKind === "parallel" || loopKind === "meta") && !childAgents.trim()) {
      setError("Child agents/loops are required for this loop kind."); return;
    }
    const exitConfig: Record<string, unknown> = {};
    if (exitKind === "tests") exitConfig.command = testCommand;
    else if (exitKind === "metric") {
      exitConfig.metric_key = metricKey;
      exitConfig.threshold = metricThreshold;
      exitConfig.comparator = metricComparator;
    } else if (exitKind === "critic") {
      exitConfig.rubric = criticRubric;
      exitConfig.threshold = criticThreshold;
    }
    // Embed loop kind + child agents (for parallel/meta/nested).
    exitConfig.loop_kind = loopKind;
    if (loopKind === "parallel" || loopKind === "meta") {
      exitConfig.child_agents = childAgents.split(",").map((s) => s.trim()).filter(Boolean);
    }
    setLaunching(true); setError(null);
    try {
      await createLoop({
        loop_id: loopId.trim(),
        body_agent_id: bodyAgentId || childAgents.split(",")[0]?.trim() || "",
        exit_kind: exitKind,
        exit_config: exitConfig, max_iterations: maxIters, max_cost_usd: maxCost, on_exceed: onExceed,
      });
      setLoopId("");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally { setLaunching(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-surface-1 border border-surface-3 rounded-lg w-full max-w-2xl max-h-[90vh] overflow-y-auto scrollbar-thin">
        <div className="flex items-center justify-between px-6 py-4 border-b border-surface-3">
          <div className="flex items-center gap-2">
            <RefreshCw className="w-4 h-4 text-accent-warn" />
            <h2 className="text-sm font-semibold">Create Loop</h2>
          </div>
          <button onClick={close} className="btn-ghost p-1"><X className="w-4 h-4" /></button>
        </div>
        <div className="p-6 space-y-4">
          {/* Loop kind selector */}
          <div>
            <label className="block text-xs text-ink-low uppercase tracking-wide mb-1.5">Loop kind</label>
            <div className="grid grid-cols-4 gap-2">
              {(Object.keys(LOOP_KIND_META) as LoopKind[]).map((k) => {
                const meta = LOOP_KIND_META[k];
                const Icon = meta.icon;
                return (
                  <button
                    key={k}
                    onClick={() => setLoopKind(k)}
                    className={`px-2 py-2 text-xs rounded-md border transition-colors text-left ${
                      loopKind === k
                        ? "border-maestro-500 bg-maestro-600/20 text-maestro-300"
                        : "border-surface-3 bg-surface-2 text-ink-mid hover:border-surface-4"
                    }`}
                  >
                    <Icon className="w-3 h-3 mb-1" />
                    <div className="font-semibold">{meta.label}</div>
                  </button>
                );
              })}
            </div>
            <p className="text-[10px] text-ink-low mt-1">{LOOP_KIND_META[loopKind].description}</p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-ink-low uppercase tracking-wide mb-1.5">Loop ID</label>
              <input type="text" value={loopId} onChange={(e) => setLoopId(e.target.value)}
                placeholder="e.g. fix_until_tests_pass" className="input w-full font-mono text-xs" />
            </div>
            {(loopKind === "simple" || loopKind === "nested") ? (
              <div>
                <label className="block text-xs text-ink-low uppercase tracking-wide mb-1.5">Body agent</label>
                <select value={bodyAgentId} onChange={(e) => setBodyAgentId(e.target.value)} className="input w-full">
                  <option value="">— select agent —</option>
                  {agentIds.map((id) => <option key={id} value={id}>{id}</option>)}
                </select>
              </div>
            ) : (
              <div>
                <label className="block text-xs text-ink-low uppercase tracking-wide mb-1.5">
                  {loopKind === "parallel" ? "Child agents (comma-separated)" : "Candidate agents (comma-separated)"}
                </label>
                <input type="text" value={childAgents} onChange={(e) => setChildAgents(e.target.value)}
                  placeholder="agent_a, agent_b, agent_c" className="input w-full font-mono text-xs" />
                <p className="text-[10px] text-ink-low mt-1">
                  {loopKind === "parallel"
                    ? "Each agent runs as an independent loop; results merged."
                    : "Supervisor picks one to run each iteration based on state."}
                </p>
              </div>
            )}
          </div>
          <div>
            <label className="block text-xs text-ink-low uppercase tracking-wide mb-1.5">Exit condition</label>
            <div className="grid grid-cols-4 gap-2 mb-3">
              {(["tests", "metric", "critic", "callable"] as const).map((k) => (
                <button key={k} onClick={() => setExitKind(k)}
                  className={`px-3 py-2 text-xs rounded-md border transition-colors ${
                    exitKind === k
                      ? "border-maestro-500 bg-maestro-600/20 text-maestro-300"
                      : "border-surface-3 bg-surface-2 text-ink-mid hover:border-surface-4"
                  }`}>
                  {k === "tests" && <CheckCircle2 className="w-3 h-3 inline mr-1" />}
                  {k === "metric" && <AlertTriangle className="w-3 h-3 inline mr-1" />}
                  {k}
                </button>
              ))}
            </div>
            {exitKind === "tests" && (
              <div>
                <label className="block text-xs text-ink-low mb-1">Test command</label>
                <input type="text" value={testCommand} onChange={(e) => setTestCommand(e.target.value)}
                  className="input w-full font-mono text-xs" />
              </div>
            )}
            {exitKind === "metric" && (
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <label className="block text-xs text-ink-low mb-1">Metric key</label>
                  <input type="text" value={metricKey} onChange={(e) => setMetricKey(e.target.value)}
                    className="input w-full font-mono text-xs" />
                </div>
                <div>
                  <label className="block text-xs text-ink-low mb-1">Comparator</label>
                  <select value={metricComparator} onChange={(e) => setMetricComparator(e.target.value)} className="input w-full">
                    <option value=">=">≥</option><option value="<=">≤</option>
                    <option value=">">&gt;</option><option value="<">&lt;</option><option value="=">=</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-ink-low mb-1">Threshold</label>
                  <input type="number" step="0.01" value={metricThreshold}
                    onChange={(e) => setMetricThreshold(Number(e.target.value))} className="input w-full" />
                </div>
              </div>
            )}
            {exitKind === "critic" && (
              <div className="space-y-2">
                <div>
                  <label className="block text-xs text-ink-low mb-1">Rubric</label>
                  <textarea value={criticRubric} onChange={(e) => setCriticRubric(e.target.value)}
                    placeholder="The output must..." rows={2} className="input w-full text-xs" />
                </div>
                <div>
                  <label className="block text-xs text-ink-low mb-1">Threshold (0-1)</label>
                  <input type="number" step="0.05" min="0" max="1" value={criticThreshold}
                    onChange={(e) => setCriticThreshold(Number(e.target.value))} className="input w-32" />
                </div>
              </div>
            )}
            {exitKind === "callable" && (
              <div className="text-xs text-ink-low p-2 bg-surface-2 rounded">
                Callable conditions are defined in Python code (templates). UI support coming in v0.2.
              </div>
            )}
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-xs text-ink-low uppercase tracking-wide mb-1.5">Max iterations</label>
              <input type="number" min={1} max={100} value={maxIters}
                onChange={(e) => setMaxIters(Number(e.target.value))} className="input w-full" />
            </div>
            <div>
              <label className="block text-xs text-ink-low uppercase tracking-wide mb-1.5">Max cost (USD)</label>
              <input type="number" step="0.5" min="0.5" value={maxCost}
                onChange={(e) => setMaxCost(Number(e.target.value))} className="input w-full" />
            </div>
            <div>
              <label className="block text-xs text-ink-low uppercase tracking-wide mb-1.5">On exceed</label>
              <select value={onExceed} onChange={(e) => setOnExceed(e.target.value as typeof onExceed)} className="input w-full">
                <option value="escalate">escalate (HITL)</option>
                <option value="pause">pause</option>
                <option value="fail">fail</option>
                <option value="continue">continue</option>
              </select>
            </div>
          </div>
          {error && <div className="text-xs text-accent-err p-2 bg-accent-err/10 rounded font-mono">{error}</div>}
        </div>
        <div className="flex items-center justify-end gap-2 px-6 py-4 border-t border-surface-3">
          <button onClick={close} className="btn-ghost">Cancel</button>
          <button onClick={handleSubmit} disabled={launching} className="btn-primary">
            <RefreshCw className="w-3.5 h-3.5" />
            {launching ? "Creating..." : "Create Loop"}
          </button>
        </div>
      </div>
    </div>
  );
}

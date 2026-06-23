import { useState } from "react";
import { useAppStore } from "../store/appStore";
import { X, UserPlus, Cpu, Network } from "lucide-react";

export default function SpawnSubagentModal() {
  const parentId = useAppStore((s) => s.spawnModalParent);
  const close = useAppStore((s) => s.closeSpawnModal);
  const spawnSubagent = useAppStore((s) => s.spawnSubagent);

  const [subGoal, setSubGoal] = useState("");
  const [role, setRole] = useState("Sub-agent");
  const [backstory, setBackstory] = useState("");
  const [tools, setTools] = useState<string[]>([]);
  const [provider, setProvider] = useState("ollama");
  const [model, setModel] = useState("");
  const [memoryScope, setMemoryScope] = useState("private");
  const [maxIters, setMaxIters] = useState(10);
  const [launching, setLaunching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!parentId) return null;

  const availableTools = ["shell", "file_read", "file_write", "git_status", "http_get", "web_search"];
  const toggleTool = (t: string) =>
    setTools((prev) => (prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t]));

  const handleSubmit = async () => {
    if (!subGoal.trim()) { setError("Sub-goal is required."); return; }
    setLaunching(true); setError(null);
    try {
      await spawnSubagent(parentId, {
        sub_goal: subGoal.trim(), role, backstory, tools,
        llm_hint: { provider, ...(model ? { model } : {}) },
        memory_scope: memoryScope, max_iterations: maxIters,
      });
      setSubGoal(""); setRole("Sub-agent"); setBackstory(""); setTools([]);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally { setLaunching(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-surface-1 border border-surface-3 rounded-lg w-full max-w-xl max-h-[90vh] overflow-y-auto scrollbar-thin">
        <div className="flex items-center justify-between px-6 py-4 border-b border-surface-3">
          <div className="flex items-center gap-2">
            <UserPlus className="w-4 h-4 text-maestro-400" />
            <h2 className="text-sm font-semibold">Spawn Sub-Agent</h2>
          </div>
          <button onClick={close} className="btn-ghost p-1"><X className="w-4 h-4" /></button>
        </div>
        <div className="p-6 space-y-4">
          <div className="bg-surface-2 border border-surface-3 rounded-md p-3 text-xs">
            <span className="text-ink-low">Parent supervisor: </span>
            <span className="font-mono text-maestro-300">{parentId}</span>
          </div>
          <div>
            <label className="block text-xs text-ink-low uppercase tracking-wide mb-1.5">Sub-goal</label>
            <textarea value={subGoal} onChange={(e) => setSubGoal(e.target.value)}
              placeholder="e.g. Implement user authentication with JWT" rows={2}
              className="input w-full resize-none" />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-ink-low uppercase tracking-wide mb-1.5">Role</label>
              <input type="text" value={role} onChange={(e) => setRole(e.target.value)} className="input w-full" />
            </div>
            <div>
              <label className="block text-xs text-ink-low uppercase tracking-wide mb-1.5">Memory scope</label>
              <select value={memoryScope} onChange={(e) => setMemoryScope(e.target.value)} className="input w-full">
                <option value="private">private</option>
                <option value="shared">shared</option>
                <option value="crew">crew</option>
              </select>
            </div>
          </div>
          <div>
            <label className="block text-xs text-ink-low uppercase tracking-wide mb-1.5">Backstory</label>
            <textarea value={backstory} onChange={(e) => setBackstory(e.target.value)}
              placeholder="e.g. 10 years building auth systems..." rows={2}
              className="input w-full resize-none" />
          </div>
          <div>
            <label className="block text-xs text-ink-low uppercase tracking-wide mb-1.5">
              <Cpu className="w-3 h-3 inline mr-1" />Tools (allowed)
            </label>
            <div className="flex flex-wrap gap-2">
              {availableTools.map((t) => (
                <button key={t} onClick={() => toggleTool(t)}
                  className={`badge ${tools.includes(t) ? "badge-info" : "bg-surface-3 text-ink-low"} cursor-pointer`}>
                  {t}
                </button>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-xs text-ink-low uppercase tracking-wide mb-1.5">
                <Network className="w-3 h-3 inline mr-1" />Provider
              </label>
              <select value={provider} onChange={(e) => setProvider(e.target.value)} className="input w-full">
                <option value="ollama">ollama</option>
                <option value="openai">openai</option>
                <option value="anthropic">anthropic</option>
                <option value="openrouter">openrouter</option>
                <option value="grok">grok</option>
                <option value="lmstudio">lmstudio</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-ink-low uppercase tracking-wide mb-1.5">Model</label>
              <input type="text" value={model} onChange={(e) => setModel(e.target.value)}
                placeholder="default" className="input w-full" />
            </div>
            <div>
              <label className="block text-xs text-ink-low uppercase tracking-wide mb-1.5">Max iters</label>
              <input type="number" min={1} max={50} value={maxIters}
                onChange={(e) => setMaxIters(Number(e.target.value))} className="input w-full" />
            </div>
          </div>
          {error && <div className="text-xs text-accent-err p-2 bg-accent-err/10 rounded font-mono">{error}</div>}
        </div>
        <div className="flex items-center justify-end gap-2 px-6 py-4 border-t border-surface-3">
          <button onClick={close} className="btn-ghost">Cancel</button>
          <button onClick={handleSubmit} disabled={launching} className="btn-primary">
            <UserPlus className="w-3.5 h-3.5" />
            {launching ? "Spawning..." : "Spawn Sub-Agent"}
          </button>
        </div>
      </div>
    </div>
  );
}

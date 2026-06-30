import { useState, useEffect } from "react";
import { useAppStore } from "../store/appStore";
import { useVoiceInput } from "../hooks";
import { Mic, MicOff, X, Play, DollarSign, Cpu, Zap } from "lucide-react";

/**
 * StartRunModal — configure and launch a new run.
 *
 * Features:
 * - Goal textarea with voice input (Web Speech API).
 * - Template picker (pre-filled from gallery selection).
 * - Budget slider (max cost in USD).
 * - Provider + model picker (fetched from sidecar health).
 * - Iteration cap.
 * - Launch button.
 */
export default function StartRunModal() {
  const isOpen = useAppStore((s) => s.startRunModalOpen);
  const close = useAppStore((s) => s.closeStartRunModal);
  const templates = useAppStore((s) => s.templates);
  const startRun = useAppStore((s) => s.startRun);
  const setActiveView = useAppStore((s) => s.setActiveView);

  const [template, setTemplate] = useState("build_saas_mvp");
  const [goal, setGoal] = useState("");
  const [maxCost, setMaxCost] = useState(10);
  const [maxIterations, setMaxIterations] = useState(100);
  const [provider, setProvider] = useState("ollama");
  const [model, setModel] = useState("");
  const [providers, setProviders] = useState<string[]>([]);
  const [launching, setLaunching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { listening, transcript, start, stop, reset, supported } = useVoiceInput();

  // Sync voice transcript into the goal field.
  useEffect(() => {
    if (transcript) {
      setGoal((prev) => (prev ? prev + " " + transcript : transcript));
      reset();
    }
  }, [transcript, reset]);

  // Load providers from sidecar.
  useEffect(() => {
    if (!isOpen) return;
    import("@tauri-apps/api/core").then(({ invoke }) => {
      invoke<string[]>("list_providers")
        .then((p) => setProviders(p))
        .catch(() => setProviders(["ollama"]));
    });
  }, [isOpen]);

  if (!isOpen) return null;

  const handleLaunch = async () => {
    if (!goal.trim()) {
      setError("Please enter a goal.");
      return;
    }
    setLaunching(true);
    setError(null);
    try {
      await startRun({
        template,
        goal: goal.trim(),
        max_cost_usd: maxCost,
        default_provider: provider,
        default_model: model || undefined,
      });
      close();
      setActiveView("dashboard");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLaunching(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-surface-1 border border-surface-3 rounded-lg w-full max-w-2xl max-h-[90vh] overflow-y-auto scrollbar-thin">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-surface-3">
          <div className="flex items-center gap-2">
            <Play className="w-4 h-4 text-maestro-400" />
            <h2 className="text-sm font-semibold">Start a New Run</h2>
          </div>
          <button onClick={close} className="btn-ghost p-1">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-6 space-y-5">
          {/* Template picker */}
          <div>
            <label className="block text-xs text-ink-low uppercase tracking-wide mb-1.5">
              Template
            </label>
            <select
              value={template}
              onChange={(e) => setTemplate(e.target.value)}
              className="input w-full"
            >
              <option value="blank">blank (no-op)</option>
              {templates.map((t) => (
                <option key={t.name} value={t.name}>
                  {t.name} — {t.description.slice(0, 60)}
                </option>
              ))}
            </select>
          </div>

          {/* Goal with voice input */}
          <div>
            <label className="block text-xs text-ink-low uppercase tracking-wide mb-1.5">
              Goal
            </label>
            <div className="relative">
              <textarea
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                placeholder="e.g. Build a notes SaaS with auth + Stripe"
                rows={3}
                className="input w-full resize-none pr-12"
              />
              {supported && (
                <button
                  onClick={listening ? stop : start}
                  className={`absolute right-2 top-2 p-1.5 rounded-md transition-colors ${
                    listening
                      ? "bg-accent-err/20 text-accent-err animate-pulse"
                      : "bg-surface-3 text-ink-mid hover:text-ink-high"
                  }`}
                  title={listening ? "Stop recording" : "Start voice input"}
                >
                  {listening ? <MicOff className="w-3.5 h-3.5" /> : <Mic className="w-3.5 h-3.5" />}
                </button>
              )}
            </div>
            {listening && (
              <p className="text-xs text-accent-err mt-1 flex items-center gap-1">
                <span className="w-1.5 h-1.5 bg-accent-err rounded-full animate-pulse" />
                Listening... speak your goal.
              </p>
            )}
            {!supported && (
              <p className="text-xs text-ink-low mt-1">
                Voice input not supported in this browser. Type your goal instead.
              </p>
            )}
          </div>

          {/* Budget + iterations */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="flex items-center justify-between text-xs text-ink-low uppercase tracking-wide mb-1.5">
                <span className="flex items-center gap-1">
                  <DollarSign className="w-3 h-3" /> Max Cost
                </span>
                <span className="text-accent-ok font-mono normal-case">${maxCost.toFixed(2)}</span>
              </label>
              <input
                type="range"
                min={0.5}
                max={100}
                step={0.5}
                value={maxCost}
                onChange={(e) => setMaxCost(Number(e.target.value))}
                className="w-full accent-maestro-500"
              />
              <div className="flex justify-between text-[10px] text-ink-low mt-0.5">
                <span>$0.50</span>
                <span>$100</span>
              </div>
            </div>
            <div>
              <label className="flex items-center justify-between text-xs text-ink-low uppercase tracking-wide mb-1.5">
                <span className="flex items-center gap-1">
                  <Zap className="w-3 h-3" /> Max Iterations
                </span>
                <span className="text-maestro-300 font-mono normal-case">{maxIterations}</span>
              </label>
              <input
                type="range"
                min={5}
                max={500}
                step={5}
                value={maxIterations}
                onChange={(e) => setMaxIterations(Number(e.target.value))}
                className="w-full accent-maestro-500"
              />
              <div className="flex justify-between text-[10px] text-ink-low mt-0.5">
                <span>5</span>
                <span>500</span>
              </div>
            </div>
          </div>

          {/* Provider + model */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-ink-low uppercase tracking-wide mb-1.5">
                <Cpu className="w-3 h-3 inline mr-1" />
                Provider
              </label>
              <select
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
                className="input w-full"
              >
                {(providers.length ? providers : ["ollama"]).map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-ink-low uppercase tracking-wide mb-1.5">
                Model (optional)
              </label>
              <input
                type="text"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder="default for provider"
                className="input w-full"
              />
            </div>
          </div>

          {/* Error */}
          {error && (
            <div className="text-xs text-accent-err p-2 bg-accent-err/10 rounded font-mono">
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-6 py-4 border-t border-surface-3">
          <button onClick={close} className="btn-ghost">
            Cancel
          </button>
          <button onClick={handleLaunch} disabled={launching} className="btn-primary">
            <Play className="w-3.5 h-3.5" />
            {launching ? "Launching..." : "Launch Run"}
          </button>
        </div>
      </div>
    </div>
  );
}

import { useState } from "react";
import { useAppStore } from "../store/appStore";
import { X, Swords, Users } from "lucide-react";

/**
 * DebateModal — trigger a debate between named agents.
 *
 * Triggered from the AgentTree when the user selects 2+ agents and
 * clicks "Debate". The debate runs as a structured multi-round
 * exchange with vote + critic.
 */
export default function DebateModal() {
  const participants = useAppStore((s) => s.debateModalParticipants);
  const close = useAppStore((s) => s.closeDebateModal);
  const triggerDebate = useAppStore((s) => s.triggerDebate);

  const [topic, setTopic] = useState("");
  const [seekConsensus, setSeekConsensus] = useState(true);
  const [launching, setLaunching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!participants || participants.length < 2) return null;

  const handleSubmit = async () => {
    if (!topic.trim()) {
      setError("Topic is required.");
      return;
    }
    setLaunching(true);
    setError(null);
    try {
      await triggerDebate(topic.trim(), participants, seekConsensus);
      setTopic("");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLaunching(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-surface-1 border border-surface-3 rounded-lg w-full max-w-lg">
        <div className="flex items-center justify-between px-6 py-4 border-b border-surface-3">
          <div className="flex items-center gap-2">
            <Swords className="w-4 h-4 text-accent-warn" />
            <h2 className="text-sm font-semibold">Trigger Debate</h2>
          </div>
          <button onClick={close} className="btn-ghost p-1">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-6 space-y-4">
          {/* Participants */}
          <div>
            <label className="flex items-center gap-1 text-xs text-ink-low uppercase tracking-wide mb-2">
              <Users className="w-3 h-3" />
              Participants ({participants.length})
            </label>
            <div className="flex flex-wrap gap-2">
              {participants.map((p) => (
                <span key={p} className="badge-info font-mono text-xs">{p}</span>
              ))}
            </div>
          </div>

          {/* Topic */}
          <div>
            <label className="block text-xs text-ink-low uppercase tracking-wide mb-1.5">
              Debate topic
            </label>
            <textarea
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="e.g. Should we use Postgres or MySQL for this SaaS?"
              rows={3}
              className="input w-full resize-none"
            />
          </div>

          {/* Consensus */}
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={seekConsensus}
              onChange={(e) => setSeekConsensus(e.target.checked)}
              className="accent-maestro-500"
            />
            <span className="text-sm text-ink-mid">
              Seek consensus (require quorum; otherwise escalate)
            </span>
          </label>

          {/* Debate flow explanation */}
          <div className="bg-surface-2 border border-surface-3 rounded-md p-3 text-xs text-ink-low space-y-1">
            <div className="font-semibold text-ink-mid mb-1">Debate flow:</div>
            <div>1. Each participant states their position.</div>
            <div>2. Each critiques the others' positions.</div>
            <div>3. Each revises their position in light of critiques.</div>
            <div>4. Final vote — majority (or quorum if consensus) wins.</div>
          </div>

          {error && (
            <div className="text-xs text-accent-err p-2 bg-accent-err/10 rounded font-mono">
              {error}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 px-6 py-4 border-t border-surface-3">
          <button onClick={close} className="btn-ghost">
            Cancel
          </button>
          <button onClick={handleSubmit} disabled={launching} className="btn-primary">
            <Swords className="w-3.5 h-3.5" />
            {launching ? "Starting..." : "Start Debate"}
          </button>
        </div>
      </div>
    </div>
  );
}

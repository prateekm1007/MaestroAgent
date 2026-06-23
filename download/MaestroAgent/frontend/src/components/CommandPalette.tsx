import { useEffect, useMemo, useRef, useState } from "react";
import { Search, CornerDownLeft } from "lucide-react";
import type { Command } from "../hooks/useKeyboardShortcuts";

/**
 * Command palette — Cmd+K (Linear/Notion-style).
 *
 * Opens with ⌘K / Ctrl+K. Fuzzy-filters commands by label. Arrow keys
 * navigate, Enter runs, Esc closes.
 */
export default function CommandPalette({
  open,
  commands,
  onClose,
}: {
  open: boolean;
  commands: Command[];
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setQuery("");
      setSelected(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  const filtered = useMemo(() => {
    if (!query.trim()) return commands;
    const q = query.toLowerCase();
    return commands.filter((c) =>
      c.label.toLowerCase().includes(q) || c.group?.toLowerCase().includes(q)
    );
  }, [commands, query]);

  // Group by `group` for display.
  const grouped = useMemo(() => {
    const out: Record<string, Command[]> = {};
    for (const c of filtered) {
      const g = c.group || "Commands";
      if (!out[g]) out[g] = [];
      out[g].push(c);
    }
    return out;
  }, [filtered]);

  const flat = filtered; // for arrow nav

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelected((s) => Math.min(s + 1, flat.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelected((s) => Math.max(s - 1, 0));
      } else if (e.key === "Enter") {
        e.preventDefault();
        flat[selected]?.action();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, flat, selected]);

  if (!open) return null;

  let runningIndex = 0;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-start justify-center pt-24 bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="bg-surface-1 border border-surface-3 rounded-lg w-full max-w-xl shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 px-4 py-3 border-b border-surface-3">
          <Search className="w-4 h-4 text-ink-low" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => { setQuery(e.target.value); setSelected(0); }}
            placeholder="Type a command or search..."
            className="flex-1 bg-transparent text-sm text-ink-high placeholder:text-ink-low focus:outline-none"
          />
          <kbd className="text-[10px] text-ink-low font-mono px-1.5 py-0.5 bg-surface-2 rounded">ESC</kbd>
        </div>
        <div className="max-h-80 overflow-y-auto scrollbar-thin p-2">
          {flat.length === 0 ? (
            <div className="px-3 py-6 text-center text-sm text-ink-low">No commands found</div>
          ) : (
            Object.entries(grouped).map(([group, cmds]) => (
              <div key={group} className="mb-1">
                <div className="px-3 py-1 text-[10px] text-ink-low uppercase tracking-wide">{group}</div>
                {cmds.map((cmd) => {
                  const idx = runningIndex++;
                  const isSel = idx === selected;
                  return (
                    <button
                      key={cmd.id}
                      onClick={cmd.action}
                      onMouseEnter={() => setSelected(idx)}
                      className={`w-full flex items-center justify-between px-3 py-2 rounded-md text-sm transition-colors ${
                        isSel ? "bg-maestro-600/20 text-maestro-300" : "text-ink-high hover:bg-surface-2"
                      }`}
                    >
                      <span>{cmd.label}</span>
                      {cmd.hint && (
                        <kbd className="text-[10px] text-ink-low font-mono px-1.5 py-0.5 bg-surface-3 rounded">
                          {cmd.hint}
                        </kbd>
                      )}
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>
        <div className="flex items-center justify-between px-4 py-2 border-t border-surface-3 text-[10px] text-ink-low">
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1">
              <CornerDownLeft className="w-3 h-3" /> run
            </span>
            <span>↑↓ navigate</span>
          </div>
          <span>MaestroAgent</span>
        </div>
      </div>
    </div>
  );
}

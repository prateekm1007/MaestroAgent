import { useEffect, useRef } from "react";
import { TerminalSquare } from "lucide-react";
import { useAppStore } from "../store/appStore";
import { formatTime } from "../lib/utils";

export default function Terminal() {
  const events = useAppStore((s) => s.events);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [events]);

  const lines = events.map((e) => {
    const detail = Object.entries(e.payload).slice(0, 4)
      .map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`).join(" ");
    return `[${formatTime(e.ts)}] ${e.type.padEnd(20)} ${detail}`;
  }).slice(-500);

  return (
    <div className="panel h-full flex flex-col">
      <div className="panel-header flex items-center justify-between">
        <span className="flex items-center gap-2">
          <TerminalSquare className="w-3.5 h-3.5" /> Terminal
        </span>
        <span className="text-xs text-ink-low font-mono normal-case">{lines.length} lines</span>
      </div>
      <div ref={scrollRef} className="flex-1 overflow-y-auto scrollbar-thin bg-surface-0 p-3 font-mono text-xs text-ink-mid">
        {lines.length === 0 ? (
          <div className="text-ink-low">$ waiting for output...</div>
        ) : (
          lines.map((line, i) => <div key={i} className="whitespace-pre-wrap break-all">{line}</div>)
        )}
      </div>
    </div>
  );
}

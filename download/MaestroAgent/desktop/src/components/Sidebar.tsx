import {
  LayoutDashboard,
  Workflow,
  Network,
  RefreshCw,
  TerminalSquare,
  FolderTree,
  BarChart3,
  LayoutTemplate,
  Conductor,
} from "lucide-react";
import { useAppStore, ViewId } from "../store/appStore";

const NAV: { id: ViewId; label: string; icon: typeof LayoutDashboard }[] = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "graph", label: "Graph Builder", icon: Workflow },
  { id: "agents", label: "Agents", icon: Network },
  { id: "loops", label: "Loops", icon: RefreshCw },
  { id: "terminal", label: "Terminal", icon: TerminalSquare },
  { id: "files", label: "Files", icon: FolderTree },
  { id: "metrics", label: "Metrics", icon: BarChart3 },
  { id: "templates", label: "Templates", icon: LayoutTemplate },
];

export default function Sidebar() {
  const activeView = useAppStore((s) => s.activeView);
  const setActiveView = useAppStore((s) => s.setActiveView);

  return (
    <aside className="w-56 bg-surface-1 border-r border-surface-3 flex flex-col">
      <div className="px-4 py-4 flex items-center gap-2 border-b border-surface-3">
        <Conductor className="w-5 h-5 text-maestro-400" />
        <div>
          <div className="text-sm font-semibold text-ink-high">MaestroAgent</div>
          <div className="text-[10px] text-ink-low font-mono">v0.1.0-alpha</div>
        </div>
      </div>

      <nav className="flex-1 py-2 overflow-y-auto scrollbar-thin">
        {NAV.map((item) => {
          const Icon = item.icon;
          const active = activeView === item.id;
          return (
            <button
              key={item.id}
              onClick={() => setActiveView(item.id)}
              className={`w-full flex items-center gap-3 px-4 py-2 text-sm transition-colors ${
                active
                  ? "bg-maestro-600/15 text-maestro-300 border-l-2 border-maestro-500"
                  : "text-ink-mid hover:bg-surface-2 hover:text-ink-high border-l-2 border-transparent"
              }`}
            >
              <Icon className="w-4 h-4" />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="px-4 py-3 border-t border-surface-3 text-[10px] text-ink-low font-mono">
        MIT · open source
      </div>
    </aside>
  );
}

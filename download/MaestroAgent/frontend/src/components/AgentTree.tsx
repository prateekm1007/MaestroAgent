import { useAppStore } from "../store/appStore";
import { useInterval } from "../hooks";
import {
  Network, Cpu, FileCode, UserPlus, Swords, ChevronDown, ChevronRight,
} from "lucide-react";
import { useCallback, useState } from "react";

interface AgentNode {
  id: string; kind: string; run_id?: string; scope?: string;
  role?: string; status?: string; parent_id?: string; sub_goal?: string;
}

export default function AgentTree() {
  const currentRun = useAppStore((s) => s.currentRun);
  const liveState = useAppStore((s) => s.liveState);
  const refreshLiveState = useAppStore((s) => s.refreshLiveState);
  const openSpawnModal = useAppStore((s) => s.openSpawnModal);
  const openDebateModal = useAppStore((s) => s.openDebateModal);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [selected, setSelected] = useState<Set<string>>(new Set());

  useInterval(() => currentRun && refreshLiveState(currentRun.run_id), currentRun ? 3000 : null);

  const agents = liveState?.agents || [];
  const edges = liveState?.agent_edges || [];
  const childrenOf: Record<string, string[]> = {};
  edges.forEach((e) => {
    if (!childrenOf[e.parent]) childrenOf[e.parent] = [];
    childrenOf[e.parent].push(e.child);
  });
  const childIds = new Set(edges.map((e) => e.child));
  const roots = agents.filter((n) => !childIds.has(n.id));

  const toggleExpand = useCallback((id: string) =>
    setExpanded((e) => ({ ...e, [id]: !e[id] })), []);

  const toggleSelect = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }, []);

  const handleDebate = () => {
    if (selected.size >= 2) {
      openDebateModal(Array.from(selected));
      setSelected(new Set());
    }
  };

  return (
    <div className="panel h-full flex flex-col">
      <div className="panel-header flex items-center justify-between">
        <span>Agent Hierarchy</span>
        <div className="flex items-center gap-2 normal-case font-normal">
          {selected.size >= 2 && (
            <button onClick={handleDebate} className="btn-ghost text-xs">
              <Swords className="w-3 h-3" /> Debate ({selected.size})
            </button>
          )}
          {selected.size > 0 && (
            <button onClick={() => setSelected(new Set())} className="text-xs text-ink-low hover:text-ink-high">
              clear
            </button>
          )}
          {currentRun && <span className="text-xs text-ink-low font-mono">{currentRun.run_id.slice(0, 8)}</span>}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto scrollbar-thin p-3">
        {agents.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <Network className="w-8 h-8 text-ink-low mb-2" />
            <p className="text-sm text-ink-mid">No agents yet</p>
            <p className="text-xs text-ink-low mt-1">
              Start a run to see the agent hierarchy grow.<br />
              Supervisors will spawn sub-agents dynamically.
            </p>
          </div>
        ) : (
          <ul className="space-y-0.5">
            {roots.map((r) => (
              <TreeNode key={r.id} node={r} allAgents={agents} childrenOf={childrenOf}
                depth={0} expanded={expanded} onToggleExpand={toggleExpand}
                selected={selected} onToggleSelect={toggleSelect}
                onSpawn={(id) => openSpawnModal(id)} />
            ))}
          </ul>
        )}
      </div>
      <div className="border-t border-surface-3 p-2 flex items-center gap-3 text-[10px] text-ink-low">
        <span>click agent to select</span><span>•</span>
        <span>select 2+ to debate</span><span>•</span>
        <span>click + to spawn sub-agent</span>
      </div>
    </div>
  );
}

function TreeNode({ node, allAgents, childrenOf, depth, expanded, onToggleExpand, selected, onToggleSelect, onSpawn }: {
  node: AgentNode; allAgents: AgentNode[];
  childrenOf: Record<string, string[]>; depth: number;
  expanded: Record<string, boolean>; onToggleExpand: (id: string) => void;
  selected: Set<string>; onToggleSelect: (id: string) => void;
  onSpawn: (id: string) => void;
}) {
  const childIds = childrenOf[node.id] || [];
  const children = childIds.map((cid) => allAgents.find((n) => n.id === cid)).filter(Boolean) as AgentNode[];
  const isExpanded = expanded[node.id] ?? true;
  const isSelected = selected.has(node.id);
  const hasChildren = children.length > 0;

  return (
    <li>
      <div
        className={`group flex items-center gap-1.5 py-1.5 px-2 rounded cursor-pointer transition-colors ${
          isSelected ? "bg-maestro-600/20 ring-1 ring-maestro-500" : "hover:bg-surface-2"
        }`}
        style={{ paddingLeft: `${depth * 20 + 8}px` }}
        onClick={() => onToggleSelect(node.id)}
      >
        {hasChildren ? (
          <button onClick={(e) => { e.stopPropagation(); onToggleExpand(node.id); }} className="text-ink-low hover:text-ink-high">
            {isExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          </button>
        ) : <span className="w-3" />}
        <NodeIcon kind={node.kind} />
        <span className="text-sm text-ink-high font-mono truncate flex-1">{node.id}</span>
        {node.role && <span className="text-[10px] text-ink-low truncate max-w-[120px]">{node.role}</span>}
        {node.scope && (
          <span className={`badge text-[10px] ${
            node.scope === "private" ? "badge-info" : node.scope === "shared" ? "badge-ok" : "badge-warn"
          }`}>{node.scope}</span>
        )}
        {node.status && (
          <span className={`badge text-[10px] ${
            node.status === "done" ? "badge-ok" : node.status === "failed" ? "badge-err" :
            node.status === "running" ? "badge-info" : node.status === "quarantined" ? "badge-err" : "badge-warn"
          }`}>{node.status}</span>
        )}
        {hasChildren && <span className="text-[10px] text-ink-low">({children.length})</span>}
        <button
          onClick={(e) => { e.stopPropagation(); onSpawn(node.id); }}
          className="opacity-0 group-hover:opacity-100 transition-opacity text-maestro-300 hover:text-maestro-200 p-0.5"
          title="Spawn sub-agent"
        >
          <UserPlus className="w-3 h-3" />
        </button>
      </div>
      {isExpanded && hasChildren && (
        <ul className="space-y-0.5">
          {children.map((c) => (
            <TreeNode key={c.id} node={c} allAgents={allAgents} childrenOf={childrenOf}
              depth={depth + 1} expanded={expanded} onToggleExpand={onToggleExpand}
              selected={selected} onToggleSelect={onToggleSelect} onSpawn={onSpawn} />
          ))}
        </ul>
      )}
    </li>
  );
}

function NodeIcon({ kind }: { kind: string }) {
  if (kind === "agent") return <Network className="w-3.5 h-3.5 text-maestro-400 flex-shrink-0" />;
  if (kind === "artifact") return <FileCode className="w-3.5 h-3.5 text-accent-info flex-shrink-0" />;
  return <Cpu className="w-3.5 h-3.5 text-ink-low flex-shrink-0" />;
}

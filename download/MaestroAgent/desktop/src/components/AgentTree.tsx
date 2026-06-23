import { useAppStore } from "../store/appStore";
import { invoke } from "@tauri-apps/api/core";
import { useEffect, useState } from "react";
import { Network, Cpu, FileCode } from "lucide-react";

interface AgentTreeNode {
  id: string;
  kind: string;
  run_id?: string;
  scope?: string;
}

interface AgentTreeEdge {
  parent: string;
  child: string;
}

/**
 * Agent hierarchy view — shows the live tree of supervisor + sub-agents
 * for the active run.
 */
export default function AgentTree() {
  const currentRun = useAppStore((s) => s.currentRun);
  const [nodes, setNodes] = useState<AgentTreeNode[]>([]);
  const [edges, setEdges] = useState<AgentTreeEdge[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!currentRun) return;
    setLoading(true);
    invoke<{ agents: AgentTreeNode[]; edges: AgentTreeEdge[] }>("get_agent_tree", { runId: currentRun.run_id })
      .then((data) => {
        setNodes(data.agents || []);
        setEdges(data.edges || []);
      })
      .catch((e) => console.warn("failed to load agent tree:", e))
      .finally(() => setLoading(false));
  }, [currentRun]);

  // Build a children map.
  const childrenOf: Record<string, string[]> = {};
  edges.forEach((e) => {
    if (!childrenOf[e.parent]) childrenOf[e.parent] = [];
    childrenOf[e.parent].push(e.child);
  });

  // Find roots (agents not in any edge as child).
  const childIds = new Set(edges.map((e) => e.child));
  const roots = nodes.filter((n) => !childIds.has(n.id));

  return (
    <div className="panel h-full flex flex-col">
      <div className="panel-header flex items-center justify-between">
        <span>Agent Hierarchy</span>
        {currentRun && (
          <span className="text-xs text-ink-low font-mono normal-case">
            {currentRun.run_id.slice(0, 8)}
          </span>
        )}
      </div>
      <div className="flex-1 overflow-y-auto scrollbar-thin p-4">
        {loading ? (
          <div className="text-ink-low text-sm">Loading...</div>
        ) : nodes.length === 0 ? (
          <div className="text-ink-low text-sm">
            No agents yet. Start a run to see the hierarchy grow.
          </div>
        ) : (
          <ul className="space-y-1">
            {roots.map((r) => (
              <TreeNode
                key={r.id}
                node={r}
                allNodes={nodes}
                childrenOf={childrenOf}
                depth={0}
              />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function TreeNode({
  node,
  allNodes,
  childrenOf,
  depth,
}: {
  node: AgentTreeNode;
  allNodes: AgentTreeNode[];
  childrenOf: Record<string, string[]>;
  depth: number;
}) {
  const childIds = childrenOf[node.id] || [];
  const children = childIds
    .map((cid) => allNodes.find((n) => n.id === cid))
    .filter(Boolean) as AgentTreeNode[];

  return (
    <li>
      <div
        className="flex items-center gap-2 py-1.5 px-2 rounded hover:bg-surface-2"
        style={{ marginLeft: depth * 20 }}
      >
        <NodeIcon kind={node.kind} />
        <span className="text-sm text-ink-high font-mono">{node.id}</span>
        {node.scope && (
          <span className="badge-info">{node.scope}</span>
        )}
        {children.length > 0 && (
          <span className="text-xs text-ink-low">({children.length} children)</span>
        )}
      </div>
      {children.length > 0 && (
        <ul className="space-y-1">
          {children.map((c) => (
            <TreeNode
              key={c.id}
              node={c}
              allNodes={allNodes}
              childrenOf={childrenOf}
              depth={depth + 1}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

function NodeIcon({ kind }: { kind: string }) {
  if (kind === "agent") return <Network className="w-3.5 h-3.5 text-maestro-400" />;
  if (kind === "artifact") return <FileCode className="w-3.5 h-3.5 text-accent-info" />;
  return <Cpu className="w-3.5 h-3.5 text-ink-low" />;
}

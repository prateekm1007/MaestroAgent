import { useCallback, useMemo } from "react";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  addEdge,
  BackgroundVariant,
  Connection,
  Edge,
  Node,
  NodeTypes,
  applyNodeChanges,
  applyEdgeChanges,
  NodeChange,
  EdgeChange,
} from "reactflow";
import "reactflow/dist/style.css";
import { useAppStore } from "../store/appStore";

/**
 * Visual graph builder — drag-and-drop workflow editor.
 *
 * Nodes are typed (agent, supervisor, loop, gate, hitl, tool). Edges
 * can be conditional. The view is bi-directional with a code view
 * (shown side-by-side in a future iteration).
 *
 * For v0.1 we render a static example graph + support adding/removing
 * nodes. Full template serialization is v0.2.
 */

const initialNodes: Node[] = [
  {
    id: "supervisor",
    type: "supervisor",
    position: { x: 250, y: 50 },
    data: { label: "Supervisor", role: "Senior Engineer" },
  },
  {
    id: "build_loop",
    type: "loop",
    position: { x: 250, y: 180 },
    data: { label: "Build Loop", condition: "tests pass", max_iters: 15 },
  },
  {
    id: "polish",
    type: "agent",
    position: { x: 250, y: 310 },
    data: { label: "Polish README", role: "Technical Writer" },
  },
  {
    id: "done",
    type: "terminal",
    position: { x: 250, y: 440 },
    data: { label: "Done" },
  },
];

const initialEdges: Edge[] = [
  { id: "e1", source: "supervisor", target: "build_loop", animated: true },
  { id: "e2", source: "build_loop", target: "polish" },
  { id: "e3", source: "polish", target: "done" },
];

const nodeTypes: NodeTypes = {
  supervisor: SupervisorNode,
  agent: AgentNode,
  loop: LoopNode,
  gate: GateNode,
  hitl: HitlNode,
  terminal: TerminalNode,
};

export default function GraphBuilder() {
  const [nodes, setNodes] = useNodesState(initialNodes);
  const [edges, setEdges] = useEdgesState(initialEdges);

  const onConnect = useCallback(
    (params: Connection) => setEdges((eds) => addEdge({ ...params, animated: true }, eds)),
    [setEdges]
  );

  return (
    <div className="panel h-full flex flex-col">
      <div className="panel-header flex items-center justify-between">
        <span>Graph Builder</span>
        <div className="flex items-center gap-2 normal-case font-normal">
          <button className="btn-ghost text-xs">+ Agent</button>
          <button className="btn-ghost text-xs">+ Loop</button>
          <button className="btn-ghost text-xs">+ Gate</button>
          <button className="btn-ghost text-xs">+ HITL</button>
        </div>
      </div>
      <div className="flex-1">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          fitView
          proOptions={{ hideAttribution: true }}
        >
          <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="#2a2a38" />
          <Controls className="!bg-surface-2 !border-surface-3" />
          <MiniMap
            className="!bg-surface-2 !border-surface-3"
            nodeColor={(n) => {
              switch (n.type) {
                case "supervisor": return "#8b5cf6";
                case "agent": return "#22c55e";
                case "loop": return "#f59e0b";
                case "terminal": return "#71717a";
                case "gate": return "#3b82f6";
                case "hitl": return "#ef4444";
                default: return "#71717a";
              }
            }}
          />
        </ReactFlow>
      </div>
    </div>
  );
}

// --- Custom node renderers ---

function NodeShell({
  color,
  label,
  subtitle,
  children,
}: {
  color: string;
  label: string;
  subtitle?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="px-3 py-2 rounded-md border bg-surface-2 shadow-lg min-w-[160px]">
      <div className="flex items-center gap-2">
        <div className="w-2 h-2 rounded-full" style={{ background: color }} />
        <div className="text-xs font-semibold text-ink-high">{label}</div>
      </div>
      {subtitle && <div className="text-[10px] text-ink-low mt-0.5">{subtitle}</div>}
      {children}
    </div>
  );
}

function SupervisorNode({ data }: { data: any }) {
  return (
    <NodeShell color="#8b5cf6" label={data.label} subtitle={data.role}>
      <div className="text-[10px] text-ink-low mt-1">spawns sub-agents</div>
    </NodeShell>
  );
}

function AgentNode({ data }: { data: any }) {
  return <NodeShell color="#22c55e" label={data.label} subtitle={data.role} />;
}

function LoopNode({ data }: { data: any }) {
  return (
    <NodeShell color="#f59e0b" label={`⟳ ${data.label}`} subtitle={`until: ${data.condition}`}>
      <div className="text-[10px] text-ink-low mt-1">max {data.max_iters} iters</div>
    </NodeShell>
  );
}

function GateNode({ data }: { data: any }) {
  return <NodeShell color="#3b82f6" label={`◇ ${data.label}`} subtitle="conditional" />;
}

function HitlNode({ data }: { data: any }) {
  return <NodeShell color="#ef4444" label={`⚠ ${data.label}`} subtitle="human approval" />;
}

function TerminalNode({ data }: { data: any }) {
  return <NodeShell color="#71717a" label={`■ ${data.label}`} />;
}

// --- Hooks to manage node/edge state (small wrappers around useState) ---

import { useState } from "react";

function useNodesState(initial: Node[]) {
  const [nodes, setNodes] = useState(initial);
  const onNodesChange = useCallback(
    (changes: NodeChange[]) => setNodes((nds) => applyNodeChanges(changes, nds)),
    []
  );
  return [nodes, setNodes, onNodesChange] as const;
}

function useEdgesState(initial: Edge[]) {
  const [edges, setEdges] = useState(initial);
  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => setEdges((eds) => applyEdgeChanges(changes, eds)),
    []
  );
  return [edges, setEdges, onEdgesChange] as const;
}

import { useCallback, useState, useMemo, useRef } from "react";
import ReactFlow, {
  Background, Controls, MiniMap, addEdge, BackgroundVariant,
  Connection, Edge, Node, NodeTypes, applyNodeChanges, applyEdgeChanges,
  NodeChange, EdgeChange, MarkerType, ReactFlowInstance,
} from "reactflow";
import "reactflow/dist/style.css";
import { useAppStore } from "../store/appStore";
import {
  Network, RefreshCw, Diamond, AlertTriangle, Square, Tool, Workflow,
  Download, Upload, Trash2, Play,
} from "lucide-react";

type NodeKind = "agent" | "supervisor" | "loop" | "gate" | "hitl" | "tool" | "terminal";

interface NodeData {
  label: string; role?: string; goal?: string;
  condition?: string; max_iters?: number; tool?: string;
  [key: string]: unknown;
}

const NODE_META: Record<NodeKind, { color: string; icon: typeof Network; label: string }> = {
  agent: { color: "#22c55e", icon: Network, label: "Agent" },
  supervisor: { color: "#8b5cf6", icon: Workflow, label: "Supervisor" },
  loop: { color: "#f59e0b", icon: RefreshCw, label: "Loop" },
  gate: { color: "#3b82f6", icon: Diamond, label: "Gate" },
  hitl: { color: "#ef4444", icon: AlertTriangle, label: "HITL" },
  tool: { color: "#06b6d4", icon: Tool, label: "Tool" },
  terminal: { color: "#71717a", icon: Square, label: "Terminal" },
};

const initialNodes: Node<NodeData>[] = [
  { id: "supervisor", type: "supervisor", position: { x: 320, y: 40 },
    data: { label: "MVP Supervisor", role: "Senior Engineer", goal: "Coordinate build" } },
  { id: "research", type: "agent", position: { x: 80, y: 180 },
    data: { label: "Researcher", role: "Researcher", goal: "Find best practices" } },
  { id: "architect", type: "agent", position: { x: 320, y: 180 },
    data: { label: "Architect", role: "Architect", goal: "Design system" } },
  { id: "build_loop", type: "loop", position: { x: 320, y: 320 },
    data: { label: "Build Loop", condition: "tests pass", max_iters: 15 } },
  { id: "polish", type: "agent", position: { x: 560, y: 180 },
    data: { label: "Polish README", role: "Writer", goal: "Polish README" } },
  { id: "hitl_review", type: "hitl", position: { x: 320, y: 460 }, data: { label: "Human Review" } },
  { id: "done", type: "terminal", position: { x: 320, y: 580 }, data: { label: "Done" } },
];

const initialEdges: Edge[] = [
  { id: "e1", source: "supervisor", target: "research", animated: true, markerEnd: { type: MarkerType.ArrowClosed } },
  { id: "e2", source: "supervisor", target: "architect", animated: true, markerEnd: { type: MarkerType.ArrowClosed } },
  { id: "e3", source: "supervisor", target: "polish", animated: true, markerEnd: { type: MarkerType.ArrowClosed } },
  { id: "e4", source: "architect", target: "build_loop", markerEnd: { type: MarkerType.ArrowClosed } },
  { id: "e5", source: "build_loop", target: "hitl_review", label: "on success", markerEnd: { type: MarkerType.ArrowClosed } },
  { id: "e6", source: "hitl_review", target: "done", label: "approved", markerEnd: { type: MarkerType.ArrowClosed } },
];

const nodeTypes: NodeTypes = Object.fromEntries(
  (Object.keys(NODE_META) as NodeKind[]).map((k) => [k, makeNodeComponent(k)])
);

function makeNodeComponent(kind: NodeKind) {
  return function MaestroNode({ data, selected }: { data: NodeData; selected?: boolean }) {
    const meta = NODE_META[kind];
    const Icon = meta.icon;
    return (
      <div
        className={`px-3 py-2 rounded-md border bg-surface-2 shadow-lg min-w-[160px] transition-shadow ${
          selected ? "ring-2 ring-maestro-500" : ""
        }`}
        style={{ borderColor: meta.color + "60" }}
      >
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: meta.color }} />
          <Icon className="w-3.5 h-3.5" style={{ color: meta.color }} />
          <div className="text-xs font-semibold text-ink-high truncate">{data.label}</div>
        </div>
        {data.role && <div className="text-[10px] text-ink-low mt-0.5">role: {data.role}</div>}
        {data.goal && <div className="text-[10px] text-ink-mid mt-0.5 truncate">→ {data.goal}</div>}
        {kind === "loop" && (
          <div className="text-[10px] text-ink-low mt-1 flex items-center gap-2">
            <span>until: <span className="text-accent-warn">{data.condition}</span></span>
            <span>max {data.max_iters}</span>
          </div>
        )}
        {kind === "hitl" && <div className="text-[10px] text-accent-err mt-1">requires human approval</div>}
      </div>
    );
  };
}

export default function GraphBuilder() {
  const [nodes, setNodes] = useState<Node<NodeData>[]>(initialNodes);
  const [edges, setEdges] = useState<Edge[]>(initialEdges);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const openStartRunModal = useAppStore((s) => s.openStartRunModal);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const rfInstance = useRef<ReactFlowInstance | null>(null);

  const onNodesChange = useCallback((changes: NodeChange[]) => setNodes((nds) => applyNodeChanges(changes, nds)), []);
  const onEdgesChange = useCallback((changes: EdgeChange[]) => setEdges((eds) => applyEdgeChanges(changes, eds)), []);
  const onConnect = useCallback((params: Connection) =>
    setEdges((eds) => addEdge({ ...params, animated: true, markerEnd: { type: MarkerType.ArrowClosed } }, eds)), []);
  const onInit = useCallback((instance: ReactFlowInstance) => { rfInstance.current = instance; }, []);

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault(); e.dataTransfer.dropEffect = "move";
  }, []);

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const kind = e.dataTransfer.getData("application/maestro-node-kind") as NodeKind;
    if (!kind) return;
    const bounds = wrapperRef.current?.getBoundingClientRect();
    if (!bounds) return;
    const position = rfInstance.current?.project({ x: e.clientX - bounds.left, y: e.clientY - bounds.top });
    if (!position) return;
    const id = `${kind}_${Date.now().toString(36)}`;
    const meta = NODE_META[kind];
    setNodes((nds) => [...nds, {
      id, type: kind, position,
      data: { label: `${meta.label} ${nodes.filter((n) => n.type === kind).length + 1}` },
    }]);
  }, [nodes]);

  const exportGraph = useCallback(() => {
    const data = { nodes, edges, version: "0.1.0" };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `maestro-graph-${Date.now()}.json`; a.click();
    URL.revokeObjectURL(url);
  }, [nodes, edges]);

  const importGraph = useCallback(() => {
    const input = document.createElement("input");
    input.type = "file"; input.accept = "application/json";
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) return;
      try {
        const data = JSON.parse(await file.text());
        if (Array.isArray(data.nodes) && Array.isArray(data.edges)) {
          setNodes(data.nodes); setEdges(data.edges);
        }
      } catch (e) { console.warn("failed to import graph:", e); }
    };
    input.click();
  }, []);

  const deleteSelected = useCallback(() => {
    if (!selectedNode) return;
    setNodes((nds) => nds.filter((n) => n.id !== selectedNode));
    setEdges((eds) => eds.filter((e) => e.source !== selectedNode && e.target !== selectedNode));
    setSelectedNode(null);
  }, [selectedNode]);

  const stats = useMemo(() => ({
    total: nodes.length,
    agents: nodes.filter((n) => n.type === "agent" || n.type === "supervisor").length,
    loops: nodes.filter((n) => n.type === "loop").length,
    edges: edges.length,
  }), [nodes, edges]);

  return (
    <div className="flex h-full gap-4">
      <div className="w-44 flex flex-col gap-2">
        <div className="panel">
          <div className="panel-header text-xs">Palette</div>
          <div className="p-2 space-y-1.5">
            {(Object.keys(NODE_META) as NodeKind[]).map((k) => {
              const meta = NODE_META[k];
              const Icon = meta.icon;
              return (
                <div
                  key={k}
                  draggable
                  onDragStart={(e) => {
                    e.dataTransfer.setData("application/maestro-node-kind", k);
                    e.dataTransfer.effectAllowed = "move";
                  }}
                  className="flex items-center gap-2 px-2 py-1.5 rounded-md bg-surface-2 hover:bg-surface-3 cursor-grab active:cursor-grabbing border border-transparent hover:border-surface-4 transition-colors"
                  title={`Drag to add ${meta.label}`}
                >
                  <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: meta.color }} />
                  <Icon className="w-3.5 h-3.5" style={{ color: meta.color }} />
                  <span className="text-xs text-ink-high">{meta.label}</span>
                </div>
              );
            })}
          </div>
        </div>
        <div className="panel">
          <div className="panel-header text-xs">Actions</div>
          <div className="p-2 space-y-1.5">
            <button onClick={exportGraph} className="w-full btn-ghost text-xs justify-start">
              <Download className="w-3 h-3" /> Export JSON
            </button>
            <button onClick={importGraph} className="w-full btn-ghost text-xs justify-start">
              <Upload className="w-3 h-3" /> Import JSON
            </button>
            <button onClick={deleteSelected} disabled={!selectedNode}
              className="w-full btn-danger text-xs justify-start disabled:opacity-40">
              <Trash2 className="w-3 h-3" /> Delete Selected
            </button>
            <button onClick={openStartRunModal} className="w-full btn-primary text-xs justify-center">
              <Play className="w-3 h-3" /> Run Graph
            </button>
          </div>
        </div>
        <div className="panel flex-1">
          <div className="panel-header text-xs">Stats</div>
          <div className="p-3 space-y-2 text-xs">
            <Stat label="Nodes" value={stats.total} color="text-ink-high" />
            <Stat label="Agents" value={stats.agents} color="text-accent-ok" />
            <Stat label="Loops" value={stats.loops} color="text-accent-warn" />
            <Stat label="Edges" value={stats.edges} color="text-accent-info" />
          </div>
        </div>
      </div>
      <div className="panel flex-1 flex flex-col">
        <div className="panel-header flex items-center justify-between">
          <span>Graph Builder</span>
          <span className="text-xs text-ink-low font-mono normal-case">
            {selectedNode ? `selected: ${selectedNode}` : "drag from palette →"}
          </span>
        </div>
        <div ref={wrapperRef} className="flex-1" onDragOver={onDragOver} onDrop={onDrop}>
          <ReactFlow
            nodes={nodes} edges={edges} nodeTypes={nodeTypes}
            onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
            onConnect={onConnect} onInit={onInit}
            onNodeClick={(_, node) => setSelectedNode(node.id)}
            onPaneClick={() => setSelectedNode(null)}
            fitView proOptions={{ hideAttribution: true }}
            defaultEdgeOptions={{ markerEnd: { type: MarkerType.ArrowClosed } }}
          >
            <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="#2a2a38" />
            <Controls className="!bg-surface-2 !border-surface-3" />
            <MiniMap
              className="!bg-surface-2 !border-surface-3"
              nodeColor={(n) => NODE_META[n.type as NodeKind]?.color || "#71717a"}
              nodeStrokeWidth={2}
            />
          </ReactFlow>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-ink-low">{label}</span>
      <span className={`font-mono ${color}`}>{value}</span>
    </div>
  );
}

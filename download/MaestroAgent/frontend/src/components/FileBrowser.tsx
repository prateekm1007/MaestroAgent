import { useState } from "react";
import { FolderTree, File, ChevronRight, ChevronDown } from "lucide-react";
import { formatBytes } from "../lib/utils";

interface FileEntry { name: string; path: string; is_dir: boolean; size?: number; }

export default function FileBrowser() {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [selected, setSelected] = useState<string | null>(null);

  const tree: FileEntry[] = [
    { name: "workspace", path: "/workspace", is_dir: true },
    { name: "src", path: "/workspace/src", is_dir: true },
    { name: "main.py", path: "/workspace/src/main.py", is_dir: false, size: 1234 },
    { name: "api", path: "/workspace/src/api", is_dir: true },
    { name: "routes.py", path: "/workspace/src/api/routes.py", is_dir: false, size: 5678 },
    { name: "tests", path: "/workspace/tests", is_dir: true },
    { name: "test_main.py", path: "/workspace/tests/test_main.py", is_dir: false, size: 910 },
    { name: "README.md", path: "/workspace/README.md", is_dir: false, size: 4321 },
    { name: "pyproject.toml", path: "/workspace/pyproject.toml", is_dir: false, size: 555 },
  ];

  return (
    <div className="panel h-full flex flex-col">
      <div className="panel-header flex items-center gap-2">
        <FolderTree className="w-3.5 h-3.5" /> File Browser
      </div>
      <div className="flex-1 overflow-y-auto scrollbar-thin p-2">
        <ul>
          {tree.map((entry) => (
            <li key={entry.path}>
              <FileRow entry={entry} depth={entry.path.split("/").length - 2}
                expanded={expanded[entry.path] || false} selected={selected === entry.path}
                onToggle={() => setExpanded((e) => ({ ...e, [entry.path]: !e[entry.path] }))}
                onSelect={() => setSelected(entry.path)} />
            </li>
          ))}
        </ul>
      </div>
      {selected && (
        <div className="border-t border-surface-3 p-2 text-xs text-ink-low font-mono">
          selected: {selected}
        </div>
      )}
    </div>
  );
}

function FileRow({ entry, depth, expanded, selected, onToggle, onSelect }: {
  entry: FileEntry; depth: number; expanded: boolean; selected: boolean;
  onToggle: () => void; onSelect: () => void;
}) {
  return (
    <div
      className={`flex items-center gap-1.5 py-1 px-2 rounded cursor-pointer hover:bg-surface-2 ${selected ? "bg-surface-2" : ""}`}
      style={{ paddingLeft: `${depth * 16 + 8}px` }}
      onClick={entry.is_dir ? onToggle : onSelect}
    >
      {entry.is_dir ? (
        expanded ? <ChevronDown className="w-3 h-3 text-ink-low" /> : <ChevronRight className="w-3 h-3 text-ink-low" />
      ) : <span className="w-3" />}
      {entry.is_dir ? <FolderTree className="w-3.5 h-3.5 text-accent-warn" /> : <File className="w-3.5 h-3.5 text-accent-info" />}
      <span className="text-sm text-ink-high">{entry.name}</span>
      {!entry.is_dir && entry.size !== undefined && (
        <span className="text-xs text-ink-low ml-auto">{formatBytes(entry.size)}</span>
      )}
    </div>
  );
}

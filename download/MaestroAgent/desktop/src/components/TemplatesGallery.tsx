import { useEffect, useState } from "react";
import { useAppStore } from "../store/appStore";
import {
  LayoutTemplate,
  Zap,
  Search,
  Star,
  Download,
  Play,
  Code2,
  FlaskConical,
  Rocket,
  ShoppingCart,
} from "lucide-react";

/**
 * Templates gallery — one-click workflow templates + marketplace stub.
 *
 * Shows:
 * - Built-in templates (from /api/templates) with descriptions.
 * - A "marketplace" stub section (placeholder for v1.0).
 * - Click a template → opens the StartRunModal pre-filled.
 */
export default function TemplatesGallery() {
  const templates = useAppStore((s) => s.templates);
  const loadTemplates = useAppStore((s) => s.loadTemplates);
  const openStartRunModal = useAppStore((s) => s.openStartRunModal);
  const [query, setQuery] = useState("");
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null);

  useEffect(() => {
    loadTemplates();
  }, [loadTemplates]);

  const filtered = templates.filter(
    (t) =>
      t.name.toLowerCase().includes(query.toLowerCase()) ||
      t.description.toLowerCase().includes(query.toLowerCase())
  );

  const categoryIcon = (name: string) => {
    if (name.includes("saas") || name.includes("mvp")) return Rocket;
    if (name.includes("research")) return FlaskConical;
    if (name.includes("ops") || name.includes("deploy")) return Code2;
    return LayoutTemplate;
  };

  return (
    <div className="h-full overflow-y-auto scrollbar-thin">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-semibold text-ink-high">Templates</h2>
          <p className="text-sm text-ink-low">
            One-click workflows. Pick a template, set a goal, run.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-ink-low absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search templates..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="input pl-8 w-64"
            />
          </div>
        </div>
      </div>

      {/* Built-in templates grid */}
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-3">
          <Zap className="w-4 h-4 text-maestro-400" />
          <h3 className="text-sm font-semibold text-ink-high uppercase tracking-wide">
            Built-in Workflows
          </h3>
          <span className="text-xs text-ink-low">({filtered.length})</span>
        </div>

        {filtered.length === 0 ? (
          <div className="panel p-8 text-center text-sm text-ink-low">
            {templates.length === 0
              ? "Loading templates... (make sure the sidecar is running)"
              : "No templates match your search."}
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-4">
            {filtered.map((t) => {
              const Icon = categoryIcon(t.name);
              const isSelected = selectedTemplate === t.name;
              return (
                <button
                  key={t.name}
                  onClick={() => setSelectedTemplate(t.name)}
                  onDoubleClick={() => {
                    setSelectedTemplate(t.name);
                    openStartRunModal();
                  }}
                  className={`panel p-4 text-left transition-all hover:border-maestro-500 ${
                    isSelected ? "border-maestro-500 ring-1 ring-maestro-500" : ""
                  }`}
                >
                  <div className="flex items-start gap-3 mb-2">
                    <div className="w-9 h-9 rounded-md bg-maestro-600/20 flex items-center justify-center flex-shrink-0">
                      <Icon className="w-4 h-4 text-maestro-300" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-semibold text-ink-high truncate">
                        {t.name}
                      </div>
                      <div className="text-[10px] text-ink-low font-mono">
                        {t.path.split("/").pop()}
                      </div>
                    </div>
                  </div>
                  <p className="text-xs text-ink-mid line-clamp-2 mb-3">
                    {t.description || "No description available."}
                  </p>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1 text-[10px] text-ink-low">
                      <Star className="w-3 h-3" />
                      <span>built-in</span>
                    </div>
                    <span className="text-xs text-maestro-300 font-medium">
                      {isSelected ? "Selected ✓" : "Select →"}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Action bar */}
      {selectedTemplate && (
        <div className="sticky bottom-0 left-0 right-0 bg-surface-1 border-t border-surface-3 p-3 flex items-center justify-between">
          <div className="text-sm">
            <span className="text-ink-low">Selected: </span>
            <span className="font-mono text-maestro-300">{selectedTemplate}</span>
          </div>
          <button onClick={openStartRunModal} className="btn-primary">
            <Play className="w-3.5 h-3.5" />
            Configure & Run
          </button>
        </div>
      )}

      {/* Marketplace stub */}
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-3">
          <ShoppingCart className="w-4 h-4 text-accent-warn" />
          <h3 className="text-sm font-semibold text-ink-high uppercase tracking-wide">
            Marketplace
          </h3>
          <span className="badge-warn">coming in v1.0</span>
        </div>
        <div className="panel p-6 text-center">
          <Download className="w-8 h-8 text-ink-low mx-auto mb-2" />
          <p className="text-sm text-ink-mid mb-1">
            Community templates & agent marketplace
          </p>
          <p className="text-xs text-ink-low">
            Browse, install, and share agent swarms with one click.
            The marketplace will support signed plugins, cost previews,
            and sandboxed trials.
          </p>
        </div>
      </div>

      {/* Featured swarms (stub) */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <Star className="w-4 h-4 text-accent-warn" />
          <h3 className="text-sm font-semibold text-ink-high uppercase tracking-wide">
            Featured Swarms
          </h3>
        </div>
        <div className="grid grid-cols-2 gap-3">
          {FEATURED.map((f) => (
            <div key={f.name} className="panel p-3 opacity-60">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-sm font-semibold text-ink-high">{f.name}</span>
                <span className="badge-info text-[10px]">{f.tag}</span>
              </div>
              <p className="text-xs text-ink-low">{f.description}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

const FEATURED = [
  {
    name: "MVP Builder Swarm",
    tag: "coding",
    description: "Full-stack SaaS MVP from a one-line goal: research → architect → build → test → polish.",
  },
  {
    name: "Research Crew",
    tag: "research",
    description: "Survey a topic, draft a report, polish until critic-approved. Cites sources.",
  },
  {
    name: "Ops Autopilot",
    tag: "ops",
    description: "Monitor infra, diagnose anomalies, file fixes. Cron + webhook triggered.",
  },
  {
    name: "Deploy Pipeline",
    tag: "devops",
    description: "Build → test → security scan → deploy to cloud. HITL gate before prod.",
  },
];

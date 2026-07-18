"use client";

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  Brain,
  CheckCircle2,
  Loader2,
  ShieldAlert,
  Sparkles,
  Target,
  XCircle,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import {
  type AgentDashboard,
  type AgentInsight,
  type SimulationResult,
  maestroApi,
} from "@/lib/maestro-api";

/**
 * Agents — wires the previously-orphaned /api/agents/* and
 * /api/commitments/simulate endpoints to a real UI surface.
 *
 * Round 69 forensic audit flagged these 4 routes as 0% wired despite
 * being squarely in-scope for Personal's pitch ("will this new commitment
 * conflict with what I've already promised?"). This component closes
 * that gap with two surfaces:
 *
 * 1. Commitment Simulator — type a proposed commitment, see risk level +
 *    conflicts + recommendation before you commit to it.
 * 2. Agent Dashboard — see what each of the 8 specialist agents (sales,
 *    customer_success, finance, product, engineering, strategy,
 *    communications, chief_of_staff) is flagging right now.
 */

const AGENT_LABELS: Record<string, string> = {
  sales: "Sales",
  customer_success: "Customer Success",
  finance: "Finance",
  product: "Product",
  engineering: "Engineering",
  strategy: "Strategy",
  communications: "Communications",
  chief_of_staff: "Chief of Staff",
};

const PRIORITY_STYLES: Record<string, string> = {
  low: "border-sky-500/30 bg-sky-500/[0.08] text-sky-300",
  medium: "border-amber-500/30 bg-amber-500/[0.08] text-amber-300",
  high: "border-rose-500/30 bg-rose-500/[0.08] text-rose-300",
};

const RISK_STYLES: Record<string, { ring: string; text: string; icon: typeof CheckCircle2 }> = {
  low: { ring: "border-emerald-500/40", text: "text-emerald-300", icon: CheckCircle2 },
  medium: { ring: "border-amber-500/40", text: "text-amber-300", icon: AlertTriangle },
  high: { ring: "border-rose-500/40", text: "text-rose-300", icon: ShieldAlert },
};

const RECOMMENDATION_LABELS: Record<string, string> = {
  proceed: "✅ Safe to proceed",
  "negotiate deadline": "⚠️ Negotiate the deadline",
  decline: "🛑 Decline or reschedule",
};

export function Agents() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">Agents</h2>
        <p className="text-sm text-muted-foreground mt-0.5">
          Simulate new commitments before you make them, and see what each
          specialist agent is flagging across your situations.
        </p>
      </div>

      <CommitmentSimulator />
      <AgentInsights />
    </div>
  );
}

/* ───────────────────────────────────────────────────────────────
 * Commitment Simulator
 * ─────────────────────────────────────────────────────────────── */

function CommitmentSimulator() {
  const { toast } = useToast();
  const [commitmentText, setCommitmentText] = useState("");
  const [entity, setEntity] = useState("");
  const [deadline, setDeadline] = useState("");
  const [simulating, setSimulating] = useState(false);
  const [result, setResult] = useState<SimulationResult | null>(null);

  async function runSimulation(e?: React.FormEvent) {
    e?.preventDefault();
    if (!commitmentText.trim() || !entity.trim()) {
      toast({
        title: "Missing fields",
        description: "Commitment text and entity are required.",
        variant: "destructive",
      });
      return;
    }
    setSimulating(true);
    setResult(null);
    try {
      const { data, live } = await maestroApi.simulateCommitment({
        commitment_text: commitmentText.trim(),
        entity: entity.trim(),
        deadline: deadline || undefined,
      });
      if (!live) {
        toast({
          title: "Backend unreachable",
          description: "Could not run the simulation.",
          variant: "destructive",
        });
        return;
      }
      setResult(data);
    } catch (e: any) {
      toast({
        title: "Simulation failed",
        description: e?.message || "Unknown error",
        variant: "destructive",
      });
    } finally {
      setSimulating(false);
    }
  }

  return (
    <Card className="border-border/60">
      <CardContent className="pt-6 space-y-4">
        <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
          <Target className="size-3.5" />
          <span>Commitment Simulator</span>
        </div>
        <p className="text-xs text-muted-foreground">
          Before you say "yes" — type the commitment you're about to make.
          Maestro checks it against your active commitments for deadline
          overlaps, entity overload, and topic conflicts.
        </p>

        <form onSubmit={runSimulation} className="space-y-3">
          <div className="space-y-1.5">
            <label htmlFor="sim-commitment" className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Commitment text
            </label>
            <Input
              id="sim-commitment"
              placeholder="e.g. I will deliver the Q4 launch deck by next Friday."
              value={commitmentText}
              onChange={(e) => setCommitmentText(e.target.value)}
              disabled={simulating}
              className="h-10"
            />
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <label htmlFor="sim-entity" className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Entity
              </label>
              <Input
                id="sim-entity"
                placeholder="e.g. Q4 Launch, Maria Garcia"
                value={entity}
                onChange={(e) => setEntity(e.target.value)}
                disabled={simulating}
                className="h-10"
              />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="sim-deadline" className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Deadline (optional)
              </label>
              <Input
                id="sim-deadline"
                type="date"
                value={deadline}
                onChange={(e) => setDeadline(e.target.value)}
                disabled={simulating}
                className="h-10"
              />
            </div>
          </div>

          <Button
            type="submit"
            disabled={simulating || !commitmentText.trim() || !entity.trim()}
            className="w-full h-10 bg-primary text-primary-foreground hover:bg-primary/90"
          >
            {simulating ? (
              <>
                <Loader2 className="size-4 animate-spin" />
                Simulating…
              </>
            ) : (
              <>
                <Zap className="size-4" />
                Simulate impact
              </>
            )}
          </Button>
        </form>

        {result && <SimulationResultCard result={result} />}
      </CardContent>
    </Card>
  );
}

function SimulationResultCard({ result }: { result: SimulationResult }) {
  const style = RISK_STYLES[result.risk_level] || RISK_STYLES.low;
  const Icon = style.icon;
  const recLabel = RECOMMENDATION_LABELS[result.recommendation] || result.recommendation;

  return (
    <div className={cn("rounded-lg border p-4 space-y-3", style.ring)}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <Icon className={cn("size-5", style.text)} />
          <div>
            <div className={cn("text-sm font-semibold capitalize", style.text)}>
              {result.risk_level} risk
            </div>
            <div className="text-xs text-muted-foreground">
              Risk score: {result.risk_score} · {result.active_commitment_count} active commitments
            </div>
          </div>
        </div>
        <Badge variant="outline" className={cn("capitalize", style.text)}>
          {recLabel}
        </Badge>
      </div>

      {result.conflicts.length > 0 ? (
        <div className="space-y-1.5">
          <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
            Conflicts detected ({result.conflicts.length})
          </div>
          <ul className="space-y-1.5">
            {result.conflicts.map((c, i) => (
              <li key={i} className="flex items-start gap-2 text-xs text-foreground/90 rounded-md border border-border/60 bg-muted/30 p-2">
                <AlertTriangle className="size-3.5 text-amber-500 mt-0.5 shrink-0" />
                <span>{c}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <div className="flex items-center gap-2 text-xs text-emerald-300">
          <CheckCircle2 className="size-3.5" />
          <span>No conflicts detected with your existing commitments.</span>
        </div>
      )}

      {result.entity_commitment_count > 0 && (
        <div className="text-xs text-muted-foreground">
          This entity already has {result.entity_commitment_count} active commitment{result.entity_commitment_count === 1 ? "" : "s"}.
        </div>
      )}
    </div>
  );
}

/* ───────────────────────────────────────────────────────────────
 * Agent Insights Dashboard
 * ─────────────────────────────────────────────────────────────── */

function AgentInsights() {
  const { toast } = useToast();
  const [dashboard, setDashboard] = useState<AgentDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [filterText, setFilterText] = useState("");

  async function load(filter?: string) {
    setLoading(true);
    try {
      const { data, live } = await maestroApi.getAgentDashboard(
        filter ? { text: filter } : undefined,
      );
      if (!live) {
        toast({
          title: "Backend unreachable",
          description: "Could not load agent insights.",
          variant: "destructive",
        });
      }
      setDashboard(data);
    } catch (e: any) {
      toast({
        title: "Failed to load insights",
        description: e?.message || "Unknown error",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function onFilterSubmit(e: React.FormEvent) {
    e.preventDefault();
    load(filterText);
  }

  const agentNames = dashboard ? Object.keys(dashboard.by_agent) : [];

  return (
    <Card className="border-border/60">
      <CardContent className="pt-6 space-y-4">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
            <Brain className="size-3.5" />
            <span>Agent Insights</span>
          </div>
          {dashboard && (
            <span className="text-[11px] text-muted-foreground/70">
              {dashboard.total_insights} insight{dashboard.total_insights === 1 ? "" : "s"} · {dashboard.agent_count} agent{dashboard.agent_count === 1 ? "" : "s"}
            </span>
          )}
        </div>

        <p className="text-xs text-muted-foreground">
          Each specialist agent watches your signals from a different angle —
          deal health, commitment risk, momentum, churn indicators. Filter
          by situation text to focus on a specific entity.
        </p>

        <form onSubmit={onFilterSubmit} className="flex gap-2">
          <Input
            placeholder="Filter by situation text (e.g. Alex Chen)"
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            disabled={loading}
            className="h-9"
          />
          <Button type="submit" variant="outline" size="sm" disabled={loading} className="h-9">
            {loading ? <Loader2 className="size-3.5 animate-spin" /> : <Sparkles className="size-3.5" />}
            Filter
          </Button>
        </form>

        {loading ? (
          <div className="py-12 text-center">
            <Loader2 className="size-5 animate-spin mx-auto text-muted-foreground" />
            <p className="text-xs text-muted-foreground mt-2">Loading agent insights…</p>
          </div>
        ) : !dashboard || dashboard.total_insights === 0 ? (
          <div className="py-12 text-center">
            <Brain className="size-6 mx-auto text-muted-foreground/50" />
            <p className="text-sm text-muted-foreground mt-2">No active insights right now.</p>
            <p className="text-xs text-muted-foreground/70 mt-1">
              Insights appear as agents detect risks across your commitments and deals.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {agentNames.map((agent) => {
              const group = dashboard.by_agent[agent];
              return (
                <div key={agent} className="space-y-2">
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-semibold">
                      {AGENT_LABELS[agent] || agent}
                    </h3>
                    <Badge variant="secondary" className="text-[10px]">
                      {group.count}
                    </Badge>
                  </div>
                  <div className="space-y-2">
                    {group.insights.map((insight, i) => (
                      <InsightCard key={i} insight={insight} />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function InsightCard({ insight }: { insight: AgentInsight }) {
  const priority = (insight.priority || "low").toLowerCase();
  const style = PRIORITY_STYLES[priority] || PRIORITY_STYLES.low;
  const confidencePct = Math.round((insight.confidence || 0) * 100);

  return (
    <div className="rounded-lg border border-border/60 bg-muted/20 p-3 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div className="text-sm font-medium text-foreground">{insight.title}</div>
        <Badge variant="outline" className={cn("capitalize text-[10px]", style)}>
          {priority}
        </Badge>
      </div>
      <p className="text-xs text-muted-foreground">{insight.body}</p>
      {insight.recommended_action && (
        <div className="flex items-start gap-1.5 text-xs text-foreground/80 pt-1 border-t border-border/40">
          <Sparkles className="size-3 text-primary mt-0.5 shrink-0" />
          <span>{insight.recommended_action}</span>
        </div>
      )}
      <div className="flex items-center gap-3 text-[10px] text-muted-foreground/70 pt-1">
        <span>Confidence: {confidencePct}%</span>
        {insight.evidence_chain && insight.evidence_chain.length > 0 && (
          <span>· {insight.evidence_chain.length} evidence ref{insight.evidence_chain.length === 1 ? "" : "s"}</span>
        )}
      </div>
    </div>
  );
}

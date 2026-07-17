"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Calendar,
  Code,
  Database,
  Facebook,
  Instagram,
  Link2,
  Loader2,
  Mail,
  MessageSquare,
  RefreshCw,
  Send,
  ShieldCheck,
  Sparkles,
  Twitter,
  Unlink,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import {
  type Connector,
  type Draft,
  maestroApi,
} from "@/lib/maestro-api";
import {
  DraftApprovalModal,
  type DraftWithMeta,
} from "@/components/maestro/DraftApprovalModal";

const PROVIDER_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  email: Mail,
  message: MessageSquare,
  code: Code,
  calendar: Calendar,
  chat: MessageSquare,
  social: Facebook,
};

export function Connectors() {
  const { toast } = useToast();
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyProvider, setBusyProvider] = useState<string | null>(null);
  const [selectedDraft, setSelectedDraft] = useState<DraftWithMeta | null>(null);
  const [resolving, setResolving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const [c, d] = await Promise.all([
      maestroApi.listConnectors(),
      maestroApi.listDrafts(),
    ]);
    setConnectors(c.data.connectors);
    setDrafts(d.data.drafts);
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // P0-Audit fix (2026-07-18): all 4 mutating handlers now use try/catch + .live
  // check + destructive toast on failure. Was: response discarded, setBusy(false)
  // in a finally never ran on unhandled rejection (now-maestroFetch throws), AND
  // the success path ran unconditionally even when the call failed silently via
  // fabricated fallback. Now: failure → destructive toast, success → real feedback.
  // Pattern matches Dashboard.tsx handleResolveDraft + Commitments.tsx handleResolveDraft.
  async function handleConnect(provider: string) {
    setBusyProvider(provider);
    try {
      const { live } = await maestroApi.connectProvider(provider);
      if (!live) {
        toast({ title: "Backend unreachable", description: "Could not connect provider.", variant: "destructive" });
        return;
      }
      toast({ title: "Connected", description: `${provider} is now connected.` });
      await load();
    } catch (e: any) {
      toast({ title: "Connect failed", description: e?.message || "Unknown error", variant: "destructive" });
    } finally {
      setBusyProvider(null);
    }
  }

  async function handleDisconnect(provider: string) {
    setBusyProvider(provider);
    try {
      const { live } = await maestroApi.disconnectProvider(provider);
      if (!live) {
        toast({ title: "Backend unreachable", description: "Could not disconnect provider.", variant: "destructive" });
        return;
      }
      toast({ title: "Disconnected", description: `${provider} has been disconnected.` });
      await load();
    } catch (e: any) {
      toast({ title: "Disconnect failed", description: e?.message || "Unknown error", variant: "destructive" });
    } finally {
      setBusyProvider(null);
    }
  }

  async function handleIngest(provider: string) {
    setBusyProvider(provider);
    try {
      const { data, live } = await maestroApi.ingestConnector(provider);
      if (!live) {
        toast({ title: "Backend unreachable", description: "Could not sync provider.", variant: "destructive" });
        return;
      }
      toast({
        title: "Synced",
        description: `${data.ingested} ingested, ${data.new_commitments} new commitments, ${data.duplicates} duplicates.`,
      });
      await load();
    } catch (e: any) {
      toast({ title: "Sync failed", description: e?.message || "Unknown error", variant: "destructive" });
    } finally {
      setBusyProvider(null);
    }
  }

  // handleResolve matches Dashboard.tsx handleResolveDraft + Commitments.tsx
  // handleResolveDraft — same action, same implementation shape across all
  // three call sites (Dashboard Moment/Whisper, Commitments rows, Connectors
  // pending-drafts list).
  async function handleResolve(draft: DraftWithMeta, resolution: "approve" | "deny" | "use_draft") {
    setResolving(true);
    try {
      const { live } = await maestroApi.resolveDraft(draft.draft_id, resolution);
      if (!live) {
        toast({ title: "Backend unreachable", description: "Could not reach the API.", variant: "destructive" });
        return;
      }
      if (resolution === "approve") {
        toast({ title: "Sent", description: "Your email has been sent." });
      } else if (resolution === "use_draft") {
        try {
          await navigator.clipboard?.writeText(draft.body || "");
        } catch { /* clipboard may be blocked */ }
        if (draft.recipient) {
          const subject = encodeURIComponent(draft.subject || "");
          const body = encodeURIComponent(draft.body || "");
          window.open(`mailto:${draft.recipient}?subject=${subject}&body=${body}`, "_blank");
        }
        toast({ title: "Opened in mail app", description: "Body copied to clipboard as backup." });
      } else {
        toast({ title: "Discarded", description: "Draft denied." });
      }
      setSelectedDraft(null);
      await load();
    } catch (e: any) {
      toast({ title: "Failed", description: e?.message || "Unknown error", variant: "destructive" });
    } finally {
      setResolving(false);
    }
  }

  const workConnectors = connectors.filter((c) => c.category === "work");
  const socialConnectors = connectors.filter((c) => c.category === "social");

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">Connectors</h2>
        <p className="text-sm text-muted-foreground mt-0.5">
          Connect your accounts to let Maestro passively ingest commitments and draft follow-ups.
          You approve every message — Maestro never auto-sends.
        </p>
      </div>

      {/* Pending Drafts — the approval flow */}
      {drafts.length > 0 && (
        <Card className="border-primary/40 border-l-4">
          <CardContent className="pt-6">
            <div className="flex items-center gap-2 mb-3">
              <Sparkles className="size-4 text-primary" />
              <h3 className="text-sm font-semibold">Pending Drafts Awaiting Your Approval</h3>
              <Badge variant="secondary" className="text-xs">{drafts.length}</Badge>
            </div>
            <p className="text-xs text-muted-foreground mb-4">
              Maestro drafted these based on your commitments. Review each one, then approve to send, discard, or use as a draft you can edit.
            </p>
            <div className="space-y-2">
              {drafts.map((draft) => (
                <DraftRow key={draft.draft_id} draft={draft} onReview={() => setSelectedDraft(draft)} />
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Work Connectors */}
      <div>
        <h3 className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground mb-3">Work Tools</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          {loading ? (
            <div className="col-span-2 py-8 text-center">
              <Loader2 className="size-5 animate-spin mx-auto text-muted-foreground" />
            </div>
          ) : (
            workConnectors.map((connector) => (
              <ConnectorCard
                key={connector.provider}
                connector={connector}
                busy={busyProvider === connector.provider}
                onConnect={() => handleConnect(connector.provider)}
                onDisconnect={() => handleDisconnect(connector.provider)}
                onIngest={() => handleIngest(connector.provider)}
              />
            ))
          )}
        </div>
      </div>

      {/* Social Connectors */}
      <div>
        <h3 className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground mb-3">
          Social Platforms — Phase 6 (coming later)
        </h3>
        <div className="grid gap-3 sm:grid-cols-2">
          {socialConnectors.map((connector) => (
            <ConnectorCard
              key={connector.provider}
              connector={connector}
              busy={busyProvider === connector.provider}
              onConnect={() => handleConnect(connector.provider)}
              onDisconnect={() => handleDisconnect(connector.provider)}
              onIngest={() => handleIngest(connector.provider)}
            />
          ))}
        </div>
      </div>

      {/* Trust + Privacy notice */}
      <Card className="border-border/60 bg-muted/30">
        <CardContent className="pt-6">
          <div className="flex items-start gap-3">
            <ShieldCheck className="size-5 text-emerald-600 mt-0.5 shrink-0" />
            <div className="text-sm space-y-2">
              <p className="font-medium">Your data is yours. Every action is audited.</p>
              <ul className="text-xs text-muted-foreground space-y-1">
                <li>• OAuth tokens are stored encrypted-at-rest. You can disconnect any connector at any time.</li>
                <li>• Maestro extracts commitments — it does not store raw message bodies.</li>
                <li>• Maestro <strong>never auto-sends</strong>. Every draft requires your explicit approval.</li>
                <li>• Every connector action (connect, disconnect, ingest, draft approve/deny) is logged in the audit trail.</li>
              </ul>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Draft Approval Modal */}
      <DraftApprovalModal
        draft={selectedDraft}
        open={!!selectedDraft}
        onOpenChange={(o) => !o && setSelectedDraft(null)}
        onResolve={handleResolve}
        resolving={resolving}
      />
    </div>
  );
}

/* ───────────────────────────────────────────────────────────────
 * Connector Card
 * ─────────────────────────────────────────────────────────────── */

function ConnectorCard({
  connector,
  busy,
  onConnect,
  onDisconnect,
  onIngest,
}: {
  connector: Connector;
  busy: boolean;
  onConnect: () => void;
  onDisconnect: () => void;
  onIngest: () => void;
}) {
  const Icon = PROVIDER_ICONS[connector.icon] || Link2;
  const connected = connector.connected;

  return (
    <Card className={cn("border-border/60", connected && "border-l-4 border-l-emerald-500/50")}>
      <CardContent className="pt-5 space-y-3">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className={cn(
              "size-8 rounded-lg flex items-center justify-center",
              connected ? "bg-emerald-500/10 text-emerald-600" : "bg-muted text-muted-foreground",
            )}>
              <Icon className="size-4" />
            </div>
            <div>
              <div className="text-sm font-medium">{connector.name}</div>
              <div className="text-[10px] text-muted-foreground uppercase tracking-wider">
                {connector.category} · Phase {connector.phase}
              </div>
            </div>
          </div>
          {connected ? (
            <Badge className="bg-emerald-500/10 text-emerald-700 border-emerald-500/30">
              <span className="size-1.5 rounded-full bg-emerald-500 mr-1" />
              Connected
            </Badge>
          ) : (
            <Badge variant="outline" className="text-muted-foreground">Not connected</Badge>
          )}
        </div>

        <p className="text-xs text-muted-foreground">{connector.ingest_description}</p>

        {connected && (
          <div className="flex items-center gap-3 text-xs">
            <span className="text-muted-foreground">
              <strong className="text-foreground">{connector.commitments_ingested}</strong> commitments ingested
            </span>
            {connector.last_ingest_at && (
              <span className="text-muted-foreground/70">
                · last sync {formatTimeAgo(connector.last_ingest_at)}
              </span>
            )}
          </div>
        )}

        <div className="flex items-center gap-2 pt-1">
          {!connected ? (
            <Button
              size="sm"
              className="h-8 bg-primary text-primary-foreground hover:bg-primary/90"
              onClick={onConnect}
              disabled={busy}
            >
              {busy ? <Loader2 className="size-3.5 animate-spin" /> : <Link2 className="size-3.5" />}
              Connect
            </Button>
          ) : (
            <>
              <Button
                size="sm"
                variant="outline"
                className="h-8"
                onClick={onIngest}
                disabled={busy}
              >
                {busy ? <Loader2 className="size-3.5 animate-spin" /> : <RefreshCw className="size-3.5" />}
                Sync now
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-8 text-destructive hover:text-destructive"
                onClick={onDisconnect}
                disabled={busy}
              >
                <Unlink className="size-3.5" />
                Disconnect
              </Button>
            </>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

/* ───────────────────────────────────────────────────────────────
 * Draft Row (in the pending drafts section)
 * ─────────────────────────────────────────────────────────────── */

function DraftRow({ draft, onReview }: { draft: DraftWithMeta; onReview: () => void }) {
  const Icon = draft.provider === "gmail" ? Mail : draft.provider === "slack" ? MessageSquare : draft.provider === "github" ? Code : Send;
  return (
    <div className="flex items-center gap-3 rounded-lg border border-border/60 bg-background/60 p-3">
      <div className="size-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center shrink-0">
        <Icon className="size-4" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 text-sm">
          <span className="font-medium truncate">{draft.recipient}</span>
          <Badge variant="outline" className="text-[10px] capitalize">{draft.provider}</Badge>
        </div>
        <div className="text-xs text-muted-foreground truncate">
          {draft.subject || draft.body.slice(0, 80) + "..."}
        </div>
      </div>
      <Button size="sm" className="h-8 bg-primary text-primary-foreground hover:bg-primary/90" onClick={onReview}>
        Review
      </Button>
    </div>
  );
}

/* ───────────────────────────────────────────────────────────────
 * Helpers
 * ─────────────────────────────────────────────────────────────── */

function formatTimeAgo(ts: string): string {
  if (!ts) return "never";
  try {
    const d = new Date(ts);
    const mins = Math.floor((Date.now() - d.getTime()) / 60000);
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    return `${days}d ago`;
  } catch {
    return ts;
  }
}

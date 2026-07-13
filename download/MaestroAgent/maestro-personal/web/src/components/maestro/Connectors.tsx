"use client";

import { useEffect, useState, useCallback } from "react";
import {
  AlertTriangle,
  Calendar,
  Check,
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
  X,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import {
  type Connector,
  type Draft,
  maestroApi,
} from "@/lib/maestro-api";

const PROVIDER_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  email: Mail,
  message: MessageSquare,
  code: Code,
  calendar: Calendar,
  chat: MessageSquare,
  social: Facebook,
};

export function Connectors() {
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyProvider, setBusyProvider] = useState<string | null>(null);
  const [selectedDraft, setSelectedDraft] = useState<Draft | null>(null);
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

  async function handleConnect(provider: string) {
    setBusyProvider(provider);
    await maestroApi.connectProvider(provider);
    await load();
    setBusyProvider(null);
  }

  async function handleDisconnect(provider: string) {
    setBusyProvider(provider);
    await maestroApi.disconnectProvider(provider);
    await load();
    setBusyProvider(null);
  }

  async function handleIngest(provider: string) {
    setBusyProvider(provider);
    await maestroApi.ingestConnector(provider);
    await load();
    setBusyProvider(null);
  }

  async function handleResolve(draft: Draft, resolution: "approve" | "deny" | "use_draft") {
    setResolving(true);
    await maestroApi.resolveDraft(draft.draft_id, resolution);
    setSelectedDraft(null);
    await load();
    setResolving(false);
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

function DraftRow({ draft, onReview }: { draft: Draft; onReview: () => void }) {
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
 * Draft Approval Modal — approve / deny / use draft
 * ─────────────────────────────────────────────────────────────── */

function DraftApprovalModal({
  draft,
  open,
  onOpenChange,
  onResolve,
  resolving,
}: {
  draft: Draft | null;
  open: boolean;
  onOpenChange: (o: boolean) => void;
  onResolve: (draft: Draft, resolution: "approve" | "deny" | "use_draft") => void;
  resolving: boolean;
}) {
  if (!draft) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="size-5 text-primary" />
            Draft for {draft.recipient}
          </DialogTitle>
          <DialogDescription>
            Maestro generated this draft from your commitments. Review it, then choose how to proceed.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* P25 fix: warn when a draft has no evidence backing */}
          {(!draft.evidence_refs || draft.evidence_refs.length === 0) && (
            <div className="rounded-md border border-amber-400/50 bg-amber-50 p-3 flex items-start gap-2">
              <AlertTriangle className="size-4 text-amber-600 mt-0.5 shrink-0" />
              <div className="text-xs text-amber-900">
                <p className="font-medium">This draft has no evidence backing</p>
                <p className="text-amber-800 mt-0.5">Review carefully before sending — Maestro could not find commitments in your signal history grounding this message.</p>
              </div>
            </div>
          )}

          {/* Provenance — the moat */}
          {draft.evidence_refs && draft.evidence_refs.length > 0 && (
            <div className="rounded-md border border-primary/30 bg-primary/5 p-3">
              <div className="text-[10px] uppercase tracking-wider text-primary font-medium mb-1">
                📎 Grounded in your commitments ({draft.evidence_refs.length} source{draft.evidence_refs.length === 1 ? "" : "s"})
              </div>
              {draft.evidence_refs.map((ref, i) => (
                <div key={i} className="text-xs text-muted-foreground mt-1">
                  <span className="italic">&quot;{ref.text}&quot;</span>
                  <span className="text-foreground/70"> — {ref.entity}</span>
                </div>
              ))}
            </div>
          )}

          {/* Subject */}
          {draft.subject && (
            <div>
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Subject</div>
              <div className="text-sm font-medium">{draft.subject}</div>
            </div>
          )}

          {/* Body */}
          <div>
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Message</div>
            <div className="rounded-md border border-border/60 bg-background/60 p-3">
              <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed">{draft.body}</pre>
            </div>
          </div>

          {/* Commitment ref */}
          {draft.commitment_ref && (
            <div className="text-xs text-muted-foreground">
              <strong className="text-foreground">Commitment:</strong> {draft.commitment_ref}
            </div>
          )}
        </div>

        <DialogFooter className="flex-col sm:flex-row gap-2">
          <Button
            variant="ghost"
            onClick={() => onResolve(draft, "deny")}
            disabled={resolving}
            className="text-destructive hover:text-destructive"
          >
            <X className="size-4" />
            Discard
          </Button>
          <Button
            variant="outline"
            onClick={() => onResolve(draft, "use_draft")}
            disabled={resolving}
          >
            {resolving ? <Loader2 className="size-4 animate-spin" /> : <Check className="size-4" />}
            Use as Draft
          </Button>
          <Button
            className="bg-primary text-primary-foreground hover:bg-primary/90"
            onClick={() => onResolve(draft, "approve")}
            disabled={resolving}
          >
            {resolving ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
            Approve & Send
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
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

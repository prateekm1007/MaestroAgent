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
  Briefcase,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import {
  type Connector,
  type ConnectResponse,
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
  briefcase: Briefcase,
};

export function Connectors() {
  const { toast } = useToast();
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyProvider, setBusyProvider] = useState<string | null>(null);
  const [selectedDraft, setSelectedDraft] = useState<DraftWithMeta | null>(null);
  const [resolving, setResolving] = useState(false);
  const [showWorkEmailForm, setShowWorkEmailForm] = useState(false);
  const [workEmailForm, setWorkEmailForm] = useState({
    host: "",
    port: "993",
    username: "",
    password: "",
  });

  // Auto-detect IMAP host from email domain — removes the #1 UX friction.
  // Users don't know their IMAP host; this fills it in for the common providers.
  const IMAP_HOST_MAP: Record<string, { host: string; port: string }> = {
    "gmail.com": { host: "imap.gmail.com", port: "993" },
    "googlemail.com": { host: "imap.gmail.com", port: "993" },
    "outlook.com": { host: "outlook.office365.com", port: "993" },
    "hotmail.com": { host: "outlook.office365.com", port: "993" },
    "live.com": { host: "outlook.office365.com", port: "993" },
    "office365.com": { host: "outlook.office365.com", port: "993" },
    "yahoo.com": { host: "imap.mail.yahoo.com", port: "993" },
    "icloud.com": { host: "imap.mail.me.com", port: "993" },
    "me.com": { host: "imap.mail.me.com", port: "993" },
    "mac.com": { host: "imap.mail.me.com", port: "993" },
    "zoho.com": { host: "imap.zoho.com", port: "993" },
    "protonmail.com": { host: "127.0.0.1", port: "1143" }, // ProtonMail Bridge
    "proton.me": { host: "127.0.0.1", port: "1143" },
    "fastmail.com": { host: "imap.fastmail.com", port: "993" },
  };

  function detectImapHost(email: string): { host: string; port: string } | null {
    const domain = email.split("@")[1]?.toLowerCase();
    if (!domain) return null;
    // Direct match
    if (IMAP_HOST_MAP[domain]) return IMAP_HOST_MAP[domain];
    // Partial match for custom domains on known providers (e.g., workspace.google)
    if (domain.includes("google")) return IMAP_HOST_MAP["gmail.com"];
    return null;
  }

  function handleWorkEmailUsernameChange(email: string) {
    const detected = detectImapHost(email);
    setWorkEmailForm({
      ...workEmailForm,
      username: email,
      host: detected?.host || workEmailForm.host,
      port: detected?.port || workEmailForm.port,
    });
  }

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
      const { data, live } = await maestroApi.connectProvider(provider);
      if (!live) {
        toast({ title: "Backend unreachable", description: "Could not connect provider.", variant: "destructive" });
        return;
      }

      // If the backend says OAuth is required, open the Google consent screen.
      // This is the 1-click OAuth flow: click → Google consent → connected.
      if (data?.oauth_required && data?.authorization_url) {
        // Open Google's OAuth consent page in a popup
        const popup = window.open(data.authorization_url, "gmail-oauth", "width=500,height=700");

        // Poll for the popup to close (user completed or cancelled)
        const pollInterval = setInterval(() => {
          if (popup?.closed) {
            clearInterval(pollInterval);
            // Re-fetch connector status from the server — NOT optimistic
            load().then(() => {
              // After re-fetch, check if the connector is now connected
              // The toast fires ONLY after the server confirms connection
              setTimeout(() => {
                const gmailConn = connectors.find((c) => c.provider === provider);
                if (gmailConn?.connected) {
                  toast({ title: "Connected", description: `${provider} is now connected.` });
                }
              }, 100);
            });
            setBusyProvider(null);
          }
        }, 500);

        // Also set a timeout to stop polling after 5 minutes
        setTimeout(() => clearInterval(pollInterval), 300000);
        return;
      }

      // If already connected (backend returned connected: true without OAuth)
      if (data?.connected) {
        toast({ title: "Connected", description: `${provider} is now connected.` });
        await load();
        return;
      }

      // If neither OAuth nor connected, something unexpected happened
      toast({ title: "Connect failed", description: "Unexpected response from server.", variant: "destructive" });
    } catch (e: any) {
      toast({ title: "Connect failed", description: e?.message || "Unknown error", variant: "destructive" });
    } finally {
      setBusyProvider(null);
    }
  }

  // Work Email (IMAP) connect — direct credentials, NOT OAuth.
  // The password is type="password" (masked), submitted over HTTPS,
  // and NOT persisted in client state after submission (cleared on success).
  async function handleWorkEmailConnect() {
    setBusyProvider("work_email");
    try {
      const credJson = JSON.stringify({
        host: workEmailForm.host,
        port: parseInt(workEmailForm.port) || 993,
        username: workEmailForm.username,
        password: workEmailForm.password,
      });

      const { data, live } = await maestroApi.connectProvider("work_email", credJson);
      if (!live) {
        toast({ title: "Backend unreachable", variant: "destructive" });
        return;
      }

      if (data?.connected) {
        toast({
          title: "Work email connected",
          description: `${workEmailForm.username} — ${data.ingested || 0} messages ingested`,
        });
        // CLEAR the password from client state immediately — no persistence
        setWorkEmailForm({ host: "", port: "993", username: "", password: "" });
        setShowWorkEmailForm(false);
        await load();
      } else {
        toast({ title: "Connect failed", description: "Unexpected response", variant: "destructive" });
      }
    } catch (e: any) {
      // The backend returns honest errors: "IMAP connection failed: check app password"
      const detail = e?.message || e?.detail || "Connection failed";
      toast({ title: "Work email connect failed", description: detail, variant: "destructive" });
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
                onConnect={() => {
                  if (connector.provider === "work_email") {
                    setShowWorkEmailForm(true);
                  } else {
                    handleConnect(connector.provider);
                  }
                }}
                onDisconnect={() => handleDisconnect(connector.provider)}
                onIngest={() => handleIngest(connector.provider)}
              />
            ))
          )}
        </div>
      </div>

      {/* Work Email (IMAP) Form — credential entry, masked, no client persistence */}
      {showWorkEmailForm && (
        <Card className="border-border/60">
          <CardContent className="pt-6 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Briefcase className="size-4" />
                <span className="text-sm font-semibold">Connect Work Email (IMAP)</span>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setShowWorkEmailForm(false);
                  setWorkEmailForm({ host: "", port: "993", username: "", password: "" });
                }}
              >
                Cancel
              </Button>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1 sm:col-span-2">
                <Label htmlFor="imap-username" className="text-xs">Work Email</Label>
                <Input
                  id="imap-username"
                  type="email"
                  placeholder="you@company.com"
                  value={workEmailForm.username}
                  onChange={(e) => handleWorkEmailUsernameChange(e.target.value)}
                />
                {workEmailForm.host && (
                  <p className="text-[10px] text-muted-foreground">
                    IMAP host auto-detected: <strong>{workEmailForm.host}:{workEmailForm.port}</strong>
                  </p>
                )}
              </div>
              <div className="space-y-1">
                <Label htmlFor="imap-host" className="text-xs">IMAP Host <span className="text-muted-foreground/50">(auto-filled)</span></Label>
                <Input
                  id="imap-host"
                  placeholder="imap.gmail.com"
                  value={workEmailForm.host}
                  onChange={(e) => setWorkEmailForm({ ...workEmailForm, host: e.target.value })}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="imap-port" className="text-xs">Port</Label>
                <Input
                  id="imap-port"
                  type="number"
                  placeholder="993"
                  value={workEmailForm.port}
                  onChange={(e) => setWorkEmailForm({ ...workEmailForm, port: e.target.value })}
                />
              </div>
              <div className="space-y-1 sm:col-span-2">
                <Label htmlFor="imap-password" className="text-xs">App Password</Label>
                <Input
                  id="imap-password"
                  type="password"
                  placeholder="••••••••••••"
                  value={workEmailForm.password}
                  onChange={(e) => setWorkEmailForm({ ...workEmailForm, password: e.target.value })}
                />
                <p className="text-[10px] text-muted-foreground">
                  App password required if 2FA is enabled — generate one in your
                  email provider's security settings. Do NOT use your regular password.
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <ShieldCheck className="size-3.5" />
              <span>
                Credentials are encrypted at rest and transmitted over HTTPS.
                The app password is never logged and never stored in your browser.
              </span>
            </div>
            <Button
              onClick={handleWorkEmailConnect}
              disabled={!workEmailForm.host || !workEmailForm.username || !workEmailForm.password || busyProvider === "work_email"}
              className="w-full"
            >
              {busyProvider === "work_email" ? (
                <>
                  <Loader2 className="size-4 animate-spin mr-2" />
                  Verifying connection…
                </>
              ) : (
                "Connect & Verify"
              )}
            </Button>
          </CardContent>
        </Card>
      )}

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

"use client";

import { useEffect, useState } from "react";
import { Database, Inbox as InboxIcon, Loader2, Mail } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { maestroApi } from "@/lib/maestro-api";

/**
 * MySources — shows the CURRENT USER's actual ingested signals, grouped by
 * source. This is the "real sources" view that the auditor (2026-07-24
 * item 1) demanded: a real user with real Gmail data sees THEIR signals
 * here, not a hardcoded synthetic fixture.
 *
 * The SyntheticInbox (Demo Inbox) is a separate, honestly-labeled section
 * for beta users to try the lifecycle without OAuth. This component is
 * what a connected user sees when they want to browse their actual data.
 *
 * Data source: GET /api/signals (token-scoped — returns ONLY the requesting
 * user's signals). Grouped by metadata.source field.
 */
type Signal = {
  signal_id: string;
  entity: string;
  text: string;
  signal_type: string;
  timestamp: string;
  metadata?: { source?: string; [k: string]: unknown };
};

function sourceLabel(source: string): string {
  if (!source) return "Unknown";
  if (source.startsWith("gmail")) return "Gmail";
  if (source.startsWith("yahoo")) return "Yahoo Mail";
  if (source.startsWith("microsoft")) return "Microsoft 365";
  if (source.startsWith("calendar")) return "Google Calendar";
  if (source.startsWith("slack")) return "Slack";
  if (source.startsWith("github")) return "GitHub";
  if (source.startsWith("imap") || source === "work_email") return "Work Email (IMAP)";
  if (source.startsWith("synthetic")) return "Demo Inbox";
  return source.charAt(0).toUpperCase() + source.slice(1);
}

export function MySources() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const { data, live } = await maestroApi.getSignals();
        if (!alive) return;
        if (!live) {
          setError("Backend unreachable");
          setLoading(false);
          return;
        }
        setSignals(Array.isArray(data) ? data : []);
      } catch (e: any) {
        if (alive) setError(e?.message || "Failed to load signals");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, []);

  // Group signals by source
  const grouped: Record<string, Signal[]> = {};
  for (const sig of signals) {
    const src = (sig.metadata?.source as string) || "unknown";
    if (!grouped[src]) grouped[src] = [];
    grouped[src].push(sig);
  }
  const sourceKeys = Object.keys(grouped).sort();

  if (loading) {
    return (
      <Card className="border-border/60">
        <CardContent className="pt-6 flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          Loading your sources…
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className="border-border/60">
        <CardContent className="pt-6 text-sm text-muted-foreground">{error}</CardContent>
      </Card>
    );
  }

  if (signals.length === 0) {
    return (
      <div className="space-y-4">
        <div>
          <h3 className="text-sm font-semibold flex items-center gap-2">
            <Database className="size-4" />
            My Sources
          </h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            Your ingested signals, grouped by source. This is your data — scoped
            to your account only. No other user can see these signals.
          </p>
        </div>
        <Card className="border-border/60">
          <CardContent className="pt-6 space-y-2">
            <div className="flex items-center gap-2 text-sm font-medium">
              <Database className="size-4 text-muted-foreground" />
              No signals yet
            </div>
            <p className="text-sm text-muted-foreground">
              Connect a source in the Connectors tab above. Once Maestro ingests
              your email or calendar, your signals will appear here — grouped by
              source, scoped to your account only.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <Database className="size-4" />
          My Sources
          <Badge variant="secondary" className="text-xs">{signals.length} signals</Badge>
        </h3>
        <p className="text-xs text-muted-foreground mt-0.5">
          Your ingested signals, grouped by source. This is your data — scoped
          to your account only. No other user can see these signals.
        </p>
      </div>

      {sourceKeys.map((src) => {
        const sigs = grouped[src];
        const label = sourceLabel(src);
        return (
          <Card key={src} className="border-border/60">
            <CardContent className="pt-4 space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Mail className="size-4 text-primary" />
                  <span className="text-sm font-medium">{label}</span>
                </div>
                <Badge variant="outline" className="text-xs">{sigs.length}</Badge>
              </div>
              <div className="space-y-1.5 max-h-48 overflow-y-auto">
                {sigs.slice(0, 10).map((sig) => (
                  <div key={sig.signal_id} className="text-xs rounded-md border border-border/40 bg-muted/20 p-2">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="font-medium truncate">{sig.entity || "—"}</span>
                      <span className="text-muted-foreground">{sig.signal_type}</span>
                    </div>
                    <p className="text-muted-foreground line-clamp-2">{sig.text}</p>
                  </div>
                ))}
                {sigs.length > 10 && (
                  <p className="text-[11px] text-muted-foreground text-center pt-1">
                    + {sigs.length - 10} more…
                  </p>
                )}
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

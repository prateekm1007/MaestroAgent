"use client";

import { useEffect, useState } from "react";
import { Inbox, Loader2, Mail } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * SyntheticInbox — 20 mutable demo emails for beta users to experience
 * the full commitment lifecycle without Gmail OAuth.
 *
 * Users can "Receive" an email → triggers commitment extraction.
 * Then check the Dashboard to see what Maestro detected.
 */

type SyntheticEmail = {
  id: string;
  from: string;
  from_name: string;
  subject: string;
  body: string;
  category: string;
  expected_effect: string;
};

type InboxStatus = {
  synthetic_emails_received: number;
  commitments: {
    active: number;
    completed: number;
    cancelled: number;
    total: number;
  };
};

const CATEGORY_META: Record<string, { icon: string; label: string; color: string }> = {
  new_commitment: { icon: "📋", label: "Commitment", color: "border-blue-500/30 bg-blue-500/[0.06]" },
  completion: { icon: "✅", label: "Completion", color: "border-green-500/30 bg-green-500/[0.06]" },
  cancellation: { icon: "❌", label: "Cancellation", color: "border-red-500/30 bg-red-500/[0.06]" },
  fyi: { icon: "📰", label: "FYI / Newsletter", color: "border-gray-500/30 bg-gray-500/[0.06]" },
  contradiction: { icon: "⚠️", label: "Contradiction", color: "border-amber-500/30 bg-amber-500/[0.06]" },
  ambiguous: { icon: "❓", label: "Ambiguous", color: "border-purple-500/30 bg-purple-500/[0.06]" },
};

export function SyntheticInbox() {
  const [emails, setEmails] = useState<SyntheticEmail[]>([]);
  const [status, setStatus] = useState<InboxStatus | null>(null);
  const [received, setReceived] = useState<Set<string>>(new Set());
  const [receiving, setReceiving] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [emailsRes, statusRes] = await Promise.all([
          fetch("/api/inbox/synthetic"),
          fetch("/api/inbox/synthetic/status", {
            headers: { Authorization: `Bearer ${localStorage.getItem("maestro.token") || ""}` },
          }),
        ]);
        if (!alive) return;
        const emailsData = await emailsRes.json();
        const statusData = statusRes.ok ? await statusRes.json() : null;
        setEmails(emailsData.emails || []);
        setStatus(statusData);
      } catch {
        // silent
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, []);

  const receiveEmail = async (id: string) => {
    setReceiving(id);
    try {
      await fetch(`/api/inbox/synthetic/${id}/receive`, {
        method: "POST",
        headers: { Authorization: `Bearer ${localStorage.getItem("maestro.token") || ""}` },
      });
      setReceived((prev) => new Set(prev).add(id));
      // Refresh status
      const statusRes = await fetch("/api/inbox/synthetic/status", {
        headers: { Authorization: `Bearer ${localStorage.getItem("maestro.token") || ""}` },
      });
      if (statusRes.ok) setStatus(await statusRes.json());
    } catch {
      // silent
    } finally {
      setReceiving(null);
    }
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <div>
          <h2 className="text-xl font-semibold tracking-tight">Demo Inbox</h2>
          <p className="text-sm text-muted-foreground mt-0.5">
            Receive sample emails to see how Maestro detects commitments and resolves them.
          </p>
        </div>
        <Card className="border-border/60">
          <CardContent className="pt-6">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              Loading inbox…
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold tracking-tight flex items-center gap-2">
          <Inbox className="size-5" />
          Demo Inbox
        </h2>
        <p className="text-sm text-muted-foreground mt-0.5">
          Receive sample emails to see how Maestro detects commitments, resolves completions, and filters noise.
        </p>
      </div>

      {/* Status bar */}
      {status && (
        <div className="flex flex-wrap gap-4 text-xs">
          <span className="rounded-md border border-border/60 bg-muted/30 px-3 py-1.5">
            <strong>{status.synthetic_emails_received}</strong> received
          </span>
          <span className="rounded-md border border-border/60 bg-muted/30 px-3 py-1.5">
            <strong>{status.commitments.total}</strong> commitments tracked
          </span>
          <span className="rounded-md border border-green-500/30 bg-green-500/[0.06] px-3 py-1.5">
            <strong>{status.commitments.completed}</strong> resolved
          </span>
          <span className="rounded-md border border-blue-500/30 bg-blue-500/[0.06] px-3 py-1.5">
            <strong>{status.commitments.active}</strong> active
          </span>
          <span className="rounded-md border border-red-500/30 bg-red-500/[0.06] px-3 py-1.5">
            <strong>{status.commitments.cancelled}</strong> cancelled
          </span>
        </div>
      )}

      {/* Email list */}
      <div className="space-y-3">
        {emails.map((email) => {
          const meta = CATEGORY_META[email.category] || CATEGORY_META.fyi;
          const isReceived = received.has(email.id);
          const isReceiving = receiving === email.id;
          return (
            <Card key={email.id} className={cn("border-border/60", isReceived && "opacity-60")}>
              <CardContent className="pt-4 pb-4">
                <div className="flex items-start gap-3">
                  <span className="text-lg shrink-0 mt-0.5">{meta.icon}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium truncate">{email.from_name}</span>
                      <span className={cn("text-[10px] px-1.5 py-0.5 rounded font-medium", meta.color)}>
                        {meta.label}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5 truncate">{email.subject}</p>
                    <p className="text-sm text-foreground/80 mt-1.5 line-clamp-2">{email.body}</p>
                    <p className="text-[11px] text-muted-foreground/70 mt-1.5 italic">
                      Expected: {email.expected_effect}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    variant={isReceived ? "secondary" : "default"}
                    onClick={() => receiveEmail(email.id)}
                    disabled={isReceived || isReceiving}
                    className="shrink-0"
                  >
                    {isReceived ? "✓ Received" : isReceiving ? "…" : "📥 Receive"}
                  </Button>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <p className="text-xs text-muted-foreground text-center">
        💡 Try receiving a commitment email first, then its completion email.
        Check the Dashboard to see Maestro resolve the commitment automatically.
      </p>
    </div>
  );
}

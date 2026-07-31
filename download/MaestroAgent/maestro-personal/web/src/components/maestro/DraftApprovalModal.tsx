"use client";

/**
 * Shared Draft Approval Modal — extracted from Connectors.tsx for reuse
 * across Dashboard (The Moment), Whisper cards, and Commitments list.
 *
 * Phase 1 (audit v21): send outcome is now rendered INLINE in the modal.
 * Every click produces a visible, persistent result:
 *   - approved + sent_message_id → green "Sent ✓" + message ID + close
 *   - send_failed → red "Not sent" + error + "Open in mail client" + "Reconnect Gmail"
 *   - ready_to_send (mailto) → "Open in mail client" button + toast
 *   - 409 → "Reconnect Gmail" CTA
 *   - invalid recipient → inline address prompt
 * No click produces no visible outcome.
 */

import {
  AlertTriangle,
  Check,
  ExternalLink,
  Loader2,
  Mail,
  RefreshCw,
  Send,
  Sparkles,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { type Draft } from "@/lib/maestro-api";

export type DraftWithMeta = Draft & {
  derived?: boolean;
  commitment_source?: string;
  evidence_count?: number;
  llm_generated?: boolean;
  style_applied?: boolean;
};

export type SendResult = {
  status: "idle" | "sending" | "sent" | "send_failed" | "ready_to_send" | "error";
  message_id?: string;
  error?: string;
  mailto_link?: string;
  needs_gmail?: boolean;
  needs_recipient?: boolean;
};

export function DraftApprovalModal({
  draft,
  open,
  onOpenChange,
  onResolve,
  resolving,
  sendResult,
  onOpenMailClient,
  onReconnectGmail,
}: {
  draft: DraftWithMeta | null;
  open: boolean;
  onOpenChange: (o: boolean) => void;
  onResolve: (draft: DraftWithMeta, resolution: "approve" | "deny" | "use_draft") => void;
  resolving: boolean;
  sendResult?: SendResult;
  onOpenMailClient?: () => void;
  onReconnectGmail?: () => void;
}) {
  if (!draft) return null;

  const result = sendResult || { status: "idle" as const };
  const isTerminal = result.status === "sent" || result.status === "send_failed" || result.status === "ready_to_send" || result.status === "error";

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
          {/* AI-generated / derived badges */}
          {(draft as DraftWithMeta).llm_generated && (
            <div className="text-[11px] text-amber-600 dark:text-amber-400 font-medium">
              ✨ AI-generated in your writing style
            </div>
          )}
          {!(draft as DraftWithMeta).llm_generated && (draft as DraftWithMeta).derived && (
            <div className="text-[11px] text-muted-foreground">
              📎 Derived from your commitment history
            </div>
          )}

          {/* P25 fix: warn when a draft has no evidence backing */}
          {(!draft.evidence_refs || draft.evidence_refs.length === 0) && (
            <div className="rounded-md border border-amber-400/50 bg-amber-50 p-3 flex items-start gap-2 dark:bg-amber-950/20">
              <AlertTriangle className="size-4 text-amber-600 mt-0.5 shrink-0" />
              <div className="text-xs text-amber-900 dark:text-amber-200">
                <p className="font-medium">This draft has no evidence backing</p>
                <p className="text-amber-800 dark:text-amber-300 mt-0.5">
                  Review carefully before sending — Maestro could not find commitments in your signal history grounding this message.
                </p>
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

          {/* Phase 1: Send outcome rendered INLINE — persistent, actionable */}
          {result.status === "sent" && (
            <div className="rounded-md border border-emerald-500/40 bg-emerald-500/10 p-4 space-y-2">
              <div className="flex items-center gap-2 text-emerald-700 dark:text-emerald-400">
                <Check className="size-5" />
                <span className="font-semibold">Email sent successfully</span>
              </div>
              {result.message_id && (
                <p className="text-xs text-muted-foreground">Message ID: <code className="text-foreground">{result.message_id}</code></p>
              )}
              <p className="text-xs text-muted-foreground">The recipient will see this in their inbox shortly.</p>
            </div>
          )}

          {result.status === "send_failed" && (
            <div className="rounded-md border border-red-500/40 bg-red-500/10 p-4 space-y-3">
              <div className="flex items-center gap-2 text-red-700 dark:text-red-400">
                <X className="size-5" />
                <span className="font-semibold">Not sent</span>
              </div>
              <p className="text-sm text-foreground/80">{result.error || "Unknown error"}</p>
              {result.needs_gmail && (
                <div className="space-y-2">
                  <p className="text-xs text-muted-foreground">Gmail is not connected. You can:</p>
                  <div className="flex flex-wrap gap-2">
                    {onReconnectGmail && (
                      <Button size="sm" variant="default" onClick={onReconnectGmail}>
                        <RefreshCw className="size-3.5" />
                        Reconnect Gmail
                      </Button>
                    )}
                    {onOpenMailClient && (
                      <Button size="sm" variant="outline" onClick={onOpenMailClient}>
                        <ExternalLink className="size-3.5" />
                        Open in mail client
                      </Button>
                    )}
                  </div>
                </div>
              )}
              {result.needs_recipient && (
                <p className="text-xs text-muted-foreground">
                  The recipient &ldquo;{draft.recipient}&rdquo; doesn&rsquo;t have a valid email address. Add one in the To field above.
                </p>
              )}
            </div>
          )}

          {result.status === "ready_to_send" && (
            <div className="rounded-md border border-blue-500/40 bg-blue-500/10 p-4 space-y-3">
              <div className="flex items-center gap-2 text-blue-700 dark:text-blue-400">
                <Mail className="size-5" />
                <span className="font-semibold">Ready to send</span>
              </div>
              <p className="text-sm text-foreground/80">
                Maestro prepared your email. Click below to open it in your mail client — review and send from there.
              </p>
              {onOpenMailClient && (
                <Button size="sm" variant="default" onClick={onOpenMailClient}>
                  <ExternalLink className="size-3.5" />
                  Open in mail client
                </Button>
              )}
            </div>
          )}

          {result.status === "error" && (
            <div className="rounded-md border border-red-500/40 bg-red-500/10 p-4 space-y-2">
              <div className="flex items-center gap-2 text-red-700 dark:text-red-400">
                <AlertTriangle className="size-5" />
                <span className="font-semibold">Error</span>
              </div>
              <p className="text-sm text-foreground/80">{result.error || "Something went wrong."}</p>
            </div>
          )}
        </div>

        <DialogFooter className="flex-col sm:flex-row gap-2">
          {/* When terminal, show Done button instead of action buttons */}
          {isTerminal ? (
            <Button
              className="bg-primary text-primary-foreground hover:bg-primary/90 w-full sm:w-auto"
              onClick={() => onOpenChange(false)}
            >
              Done
            </Button>
          ) : (
            <>
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
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

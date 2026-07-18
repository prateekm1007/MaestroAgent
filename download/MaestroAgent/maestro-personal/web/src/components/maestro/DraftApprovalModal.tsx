"use client";

/**
 * Shared Draft Approval Modal — extracted from Connectors.tsx for reuse
 * across Dashboard (The Moment), Whisper cards, and Commitments list.
 *
 * Actions per the mobile DraftApprovalModal.tsx:
 *  - Approve & Send  → resolveDraft(draft_id, "approve")
 *  - Use as Draft    → resolveDraft(draft_id, "use_draft") (web: also copies to clipboard)
 *  - Discard         → resolveDraft(draft_id, "deny")
 *
 * Shows: subject, body, evidence_refs (provenance — the moat), llm_generated
 * flag, derived flag, and a warning when evidence_refs is empty (P25).
 */

import {
  AlertTriangle,
  Check,
  Loader2,
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

export function DraftApprovalModal({
  draft,
  open,
  onOpenChange,
  onResolve,
  resolving,
}: {
  draft: DraftWithMeta | null;
  open: boolean;
  onOpenChange: (o: boolean) => void;
  onResolve: (draft: DraftWithMeta, resolution: "approve" | "deny" | "use_draft") => void;
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

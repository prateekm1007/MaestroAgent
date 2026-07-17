"use client";

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Loader2,
  Mail,
  Sparkles,
  XCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import {
  confidenceColor,
  confidenceTextColor,
  confidenceTier,
  formatTimestamp,
  type Commitment,
  type CommitmentsTheOne,
  maestroApi,
} from "@/lib/maestro-api";
import {
  DraftApprovalModal,
  type DraftWithMeta,
} from "./DraftApprovalModal";
import { Signals } from "./Signals";

export function Commitments({
  initialEntityFilter = "",
  onEntityFilterConsumed,
}: {
  initialEntityFilter?: string;
  onEntityFilterConsumed?: () => void;
} = {}) {
  const { toast } = useToast();
  const [theOne, setTheOne] = useState<CommitmentsTheOne | null>(null);
  const [list, setList] = useState<Commitment[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  // Phase 11 + 16 + 14: deal health per entity + meeting grades + cross-meeting threads
  const [dealHealth, setDealHealth] = useState<any[]>([]);
  const [meetingGrades, setMeetingGrades] = useState<any[]>([]);
  const [threads, setThreads] = useState<any[]>([]);

  // P0-6: Draft button state
  const [draftForReview, setDraftForReview] = useState<DraftWithMeta | null>(null);
  const [draftResolving, setDraftResolving] = useState(false);
  const [draftBusyEntity, setDraftBusyEntity] = useState<string | null>(null);

  // P1-12: Segmented control — Commitments | Signals
  const [tab, setTab] = useState<"commitments" | "signals">("commitments");

  // P1-8: Optional entity filter (set from Ask provenance deep-link)
  const [entityFilter, setEntityFilter] = useState(initialEntityFilter);

  useEffect(() => {
    if (initialEntityFilter) {
      setEntityFilter(initialEntityFilter);
      onEntityFilterConsumed?.();
    }
  }, [initialEntityFilter, onEntityFilterConsumed]);

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      const [one, all, dh, mg, th] = await Promise.all([
        maestroApi.getCommitmentsTheOne(),
        maestroApi.getCommitments(),
        maestroApi.getDealHealth(),
        maestroApi.getMeetingGrades(),
        maestroApi.getThreads(),
      ]);
      if (!alive) return;
      setTheOne(one.data);
      setList(all.data);
      setDealHealth(dh.data?.deals ?? []);
      setMeetingGrades(mg.data?.grades ?? []);
      setThreads(th.data?.threads ?? []);
      setLoading(false);
    })();
    return () => {
      alive = false;
    };
  }, []);

  async function correct(signal_id: string, action: "complete" | "dismiss" | "cancel") {
    setBusyId(signal_id);
    await maestroApi.correctSignal(signal_id, action);
    // Refetch both endpoints
    const [one, all] = await Promise.all([
      maestroApi.getCommitmentsTheOne(),
      maestroApi.getCommitments(),
    ]);
    setTheOne(one.data);
    setList(all.data);
    setBusyId(null);
  }

  // P0-6: Draft from The One or any commitment row — calls generateAutoDraft + opens shared modal
  async function handleDraft(entity: string) {
    if (!entity) return;
    setDraftBusyEntity(entity);
    try {
      const { data, live } = await maestroApi.generateAutoDraft("gmail", entity);
      if (!live || !data) {
        toast({
          title: "Draft generation failed",
          description: "Could not reach the API or no commitments found for this entity.",
          variant: "destructive",
        });
      } else {
        setDraftForReview(data as DraftWithMeta);
      }
    } catch (e: any) {
      toast({ title: "Draft failed", description: e?.message || "Unknown error", variant: "destructive" });
    } finally {
      setDraftBusyEntity(null);
    }
  }

  async function handleResolveDraft(draft: DraftWithMeta, resolution: "approve" | "deny" | "use_draft") {
    setDraftResolving(true);
    try {
      const { live } = await maestroApi.resolveDraft(draft.draft_id, resolution);
      if (!live) {
        toast({ title: "Backend unreachable", description: "Could not reach the API.", variant: "destructive" });
      } else if (resolution === "approve") {
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
      setDraftForReview(null);
    } catch (e: any) {
      toast({ title: "Failed", description: e?.message || "Unknown error", variant: "destructive" });
    } finally {
      setDraftResolving(false);
    }
  }

  // P1-8: Apply entity filter to the visible list
  const filteredList = entityFilter
    ? list.filter((c) => c.entity?.toLowerCase().includes(entityFilter.toLowerCase()))
    : list;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">Commitments</h2>
        <p className="text-sm text-muted-foreground mt-0.5">
          The one that matters most, and the rest.
        </p>
      </div>

      {/* P1-12: Segmented control — Commitments | Signals */}
      <div className="inline-flex items-center gap-1 p-1 rounded-lg bg-muted/40 border border-border/60">
        <button
          type="button"
          onClick={() => setTab("commitments")}
          className={cn(
            "px-3 py-1.5 text-sm font-medium rounded-md transition-colors",
            tab === "commitments"
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          Commitments
        </button>
        <button
          type="button"
          onClick={() => setTab("signals")}
          className={cn(
            "px-3 py-1.5 text-sm font-medium rounded-md transition-colors",
            tab === "signals"
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          Signals
        </button>
      </div>

      {/* P1-8: Entity filter banner (visible when deep-linked from Ask) */}
      {entityFilter && (
        <div className="flex items-center gap-2 text-xs rounded-md border border-amber-500/30 bg-amber-500/[0.08] px-3 py-2">
          <span className="text-amber-700 dark:text-amber-300 font-medium">
            Filtered by entity: <span className="font-mono">{entityFilter}</span>
          </span>
          <button
            type="button"
            onClick={() => setEntityFilter("")}
            className="ml-auto text-amber-700 dark:text-amber-300 hover:underline"
          >
            clear
          </button>
        </div>
      )}

      {tab === "signals" ? (
        <Signals />
      ) : (
        <>
          {/* The One */}
          {loading ? (
            <Card className="border-border/60">
              <CardContent className="pt-6 flex items-center justify-center py-10">
                <Loader2 className="size-5 text-muted-foreground animate-spin" />
              </CardContent>
            </Card>
          ) : theOne?.primary ? (
            <TheOneCard
              commitment={theOne.primary}
              why={theOne.why_primary}
              overallCalibration={theOne.overall_calibration}
              onCorrect={correct}
              onDraft={handleDraft}
              busy={busyId === theOne.primary.signal_id}
              draftBusy={draftBusyEntity === theOne.primary.entity}
            />
          ) : (
            <Card className="border-border/60 border-dashed">
              <CardContent className="pt-6 pb-8 text-center text-sm text-muted-foreground">
                No active commitments. You&apos;re caught up.
              </CardContent>
            </Card>
          )}

          {/* The rest */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold">All active</h3>
              <span className="text-xs text-muted-foreground">
                {loading ? "loading…" : `${filteredList.length} commitment${filteredList.length === 1 ? "" : "s"}`}
              </span>
            </div>
            <div className="space-y-3">
              {loading ? (
                <SkeletonCommitment />
              ) : filteredList.length === 0 ? (
                <Card className="border-border/60 border-dashed">
                  <CardContent className="pt-6 pb-8 text-center text-sm text-muted-foreground">
                    {entityFilter ? `No commitments match "${entityFilter}".` : "Nothing active."}
                  </CardContent>
                </Card>
              ) : (
                filteredList.map((c) => (
                  <CommitmentRow
                    key={c.signal_id}
                    c={c}
                    onCorrect={correct}
                    onDraft={handleDraft}
                    busy={busyId === c.signal_id}
                    draftBusy={draftBusyEntity === c.entity}
                  />
                ))
              )}
            </div>
          </div>

          {/* Phase 14: Cross-Meeting Threads (institutional memory) */}
          {threads.length > 0 && (
            <div>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold">Meeting Threads</h3>
                <span className="text-xs text-muted-foreground">
                  {threads.length} thread{threads.length === 1 ? "" : "s"}
                </span>
              </div>
              <div className="space-y-3">
                {threads.slice(0, 5).map((t) => (
                  <Card key={t.thread_id} className="border-border/60">
                    <CardContent className="py-3 px-4 space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="flex-1 min-w-0">
                          <p className="font-medium text-sm truncate">{t.entity}</p>
                          <p className="text-xs text-muted-foreground mt-0.5 truncate">{t.topic}</p>
                        </div>
                        <span
                          className={cn(
                            "text-xs px-2 py-0.5 rounded-full font-medium shrink-0 ml-2",
                            t.confidence_level === "high" ? "bg-green-500/15 text-green-600"
                              : t.confidence_level === "medium" ? "bg-yellow-500/15 text-yellow-600"
                              : "bg-muted text-muted-foreground"
                          )}
                        >
                          {t.meeting_count} meeting{t.meeting_count === 1 ? "" : "s"}
                        </span>
                      </div>
                      {t.topic_evolution && t.topic_evolution.length > 0 && (
                        <p className="text-xs text-muted-foreground">
                          Topic evolution: {t.topic_evolution.join(" → ")}
                        </p>
                      )}
                      {t.decision_chain && t.decision_chain.length > 0 && (
                        <p className="text-xs text-muted-foreground">
                          {t.decision_chain.length} decision{t.decision_chain.length === 1 ? "" : "s"} tracked
                        </p>
                      )}
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>
          )}

          {/* Phase 16: Meeting History with grades */}
          {meetingGrades.length > 0 && (
            <div>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold">Meeting History</h3>
                <span className="text-xs text-muted-foreground">
                  {meetingGrades.length} meeting{meetingGrades.length === 1 ? "" : "s"}
                </span>
              </div>
              <div className="space-y-3">
                {meetingGrades.slice(0, 5).map((g) => (
                  <Card key={g.meeting_id || g.entity} className="border-border/60">
                    <CardContent className="py-3 px-4 flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-sm truncate">
                          {g.entity || g.title || "Meeting"}
                        </p>
                        {g.title && g.title !== g.entity && (
                          <p className="text-xs text-muted-foreground mt-0.5 truncate">{g.title}</p>
                        )}
                        <p className="text-xs text-muted-foreground mt-1">{g.confidence_label}</p>
                      </div>
                      <span
                        className={cn(
                          "flex items-center justify-center rounded-lg w-9 h-9 text-lg font-black text-black shrink-0 ml-3",
                          g.grade === "A" ? "bg-green-500"
                            : g.grade === "B" ? "bg-yellow-500"
                            : g.grade === "C" ? "bg-yellow-600"
                            : "bg-red-500"
                        )}
                      >
                        {g.effective_grade || g.grade}
                      </span>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {/* P0-6: Shared Draft Approval Modal */}
      <DraftApprovalModal
        draft={draftForReview}
        open={!!draftForReview}
        onOpenChange={(o) => !o && setDraftForReview(null)}
        onResolve={handleResolveDraft}
        resolving={draftResolving}
      />
    </div>
  );
}

function TheOneCard({
  commitment,
  why,
  overallCalibration,
  onCorrect,
  onDraft,
  busy,
  draftBusy,
}: {
  commitment: Commitment;
  why: string;
  overallCalibration?: string;
  onCorrect: (id: string, action: "complete" | "dismiss" | "cancel") => void;
  onDraft: (entity: string) => void;
  busy: boolean;
  draftBusy: boolean;
}) {
  const tier = confidenceTier(commitment.confidence);
  return (
    <Card className="relative overflow-hidden border-border/60 surface-elevated">
      <div
        className="pointer-events-none absolute -top-24 -right-24 h-64 w-64 rounded-full bg-amber-500/[0.06] blur-3xl"
        aria-hidden
      />
      <CardContent className="relative pt-6 space-y-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
            <Sparkles className="size-3.5" />
            <span>The One</span>
          </div>
          {commitment.is_at_risk && (
            <span className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full bg-amber-500/15 text-amber-300 border border-amber-500/30">
              <AlertTriangle className="size-3" />
              at risk · {commitment.days_stale}d stale
            </span>
          )}
        </div>

        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">{commitment.entity}</p>
          <p className="text-2xl sm:text-3xl font-medium leading-tight text-balance">
            {commitment.text}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3 text-xs">
          {commitment.deadline && (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-muted/60 border border-border/60">
              <Clock className="size-3" />
              due {formatTimestamp(commitment.deadline)}
            </span>
          )}
          <span className={cn("font-mono font-medium", confidenceTextColor(commitment.confidence))}>
            {(commitment.confidence * 100).toFixed(0)}% confidence · {tier}
          </span>
          {commitment.outcome_history && (
            <span className="text-muted-foreground">
              history: {commitment.outcome_history}
            </span>
          )}
        </div>

        {/* Confidence meter */}
        <div className="h-1.5 w-full rounded-full bg-muted/60 overflow-hidden">
          <div
            className={cn("h-full rounded-full", confidenceColor(commitment.confidence))}
            style={{ width: `${Math.max(2, Math.min(100, commitment.confidence * 100))}%` }}
          />
        </div>

        {why && (
          <p className="text-sm text-muted-foreground">
            <span className="text-foreground/70">Why this one: </span>
            {why}
          </p>
        )}

        {overallCalibration && (
          <p className="text-xs text-muted-foreground/70 italic">
            Calibration: {overallCalibration}
          </p>
        )}

        {/* Action buttons */}
        <div className="flex flex-wrap gap-2 pt-1">
          <Button
            size="sm"
            variant="default"
            className="h-8"
            disabled={busy}
            onClick={() => onCorrect(commitment.signal_id, "complete")}
          >
            <CheckCircle2 className="size-3.5" />
            Complete
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-8"
            disabled={busy}
            onClick={() => onCorrect(commitment.signal_id, "dismiss")}
          >
            Dismiss
          </Button>
          <CancelWithConfirm onConfirm={() => onCorrect(commitment.signal_id, "cancel")} disabled={busy} />
          {/* P0-6: Draft button — generates auto-draft + opens shared modal */}
          <Button
            size="sm"
            variant="outline"
            className="h-8 bg-amber-500/10 border-amber-500/30 text-amber-700 dark:text-amber-300 hover:bg-amber-500/20 ml-auto"
            disabled={draftBusy}
            onClick={() => onDraft(commitment.entity)}
            title="Draft a follow-up email"
          >
            {draftBusy ? <Loader2 className="size-3.5 animate-spin" /> : <Mail className="size-3.5" />}
            Draft
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function CommitmentRow({
  c,
  onCorrect,
  onDraft,
  busy,
  draftBusy,
}: {
  c: Commitment;
  onCorrect: (id: string, action: "complete" | "dismiss" | "cancel") => void;
  onDraft: (entity: string) => void;
  busy: boolean;
  draftBusy: boolean;
}) {
  return (
    <Card className={cn("border-border/60", c.is_at_risk && "border-amber-500/30 bg-amber-500/[0.02]")}>
      <CardContent className="pt-5 space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-1 min-w-0 flex-1">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span className="font-medium text-foreground/90">{c.entity}</span>
              <span>·</span>
              <span className="capitalize">{c.claim_type.replace(/_/g, " ")}</span>
              {c.is_at_risk && (
                <span className="inline-flex items-center gap-1 text-amber-400">
                  <AlertTriangle className="size-3" />
                  {c.days_stale}d stale
                </span>
              )}
            </div>
            <p className="text-sm text-foreground/90 leading-relaxed">{c.text}</p>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
              {c.deadline && (
                <span className="inline-flex items-center gap-1">
                  <Clock className="size-3" />
                  {formatTimestamp(c.deadline)}
                </span>
              )}
              <span className={cn("font-mono", confidenceTextColor(c.confidence))}>
                {(c.confidence * 100).toFixed(0)}%
              </span>
              {c.outcome_history && <span>· {c.outcome_history}</span>}
            </div>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="default"
            className="h-7 text-xs"
            disabled={busy}
            onClick={() => onCorrect(c.signal_id, "complete")}
          >
            <CheckCircle2 className="size-3" />
            Complete
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="h-7 text-xs"
            disabled={busy}
            onClick={() => onCorrect(c.signal_id, "dismiss")}
          >
            Dismiss
          </Button>
          <CancelWithConfirm onConfirm={() => onCorrect(c.signal_id, "cancel")} disabled={busy} small />
          {/* P0-6: Draft button on each commitment row */}
          <Button
            size="sm"
            variant="ghost"
            className="h-7 text-xs bg-amber-500/10 text-amber-700 dark:text-amber-300 hover:bg-amber-500/20 ml-auto"
            disabled={draftBusy}
            onClick={() => onDraft(c.entity)}
            title="Draft a follow-up email"
          >
            {draftBusy ? <Loader2 className="size-3 animate-spin" /> : <Mail className="size-3" />}
            Draft
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function CancelWithConfirm({
  onConfirm,
  disabled,
  small,
}: {
  onConfirm: () => void;
  disabled: boolean;
  small?: boolean;
}) {
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button
          size={small ? "sm" : "sm"}
          variant="ghost"
          className={small ? "h-7 text-xs text-rose-300 hover:text-rose-200" : "h-8 text-rose-300 hover:text-rose-200"}
          disabled={disabled}
        >
          <XCircle className={small ? "size-3" : "size-3.5"} />
          Cancel
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Cancel this commitment?</AlertDialogTitle>
          <AlertDialogDescription>
            Cancelling marks the commitment as not going to happen. This is
            different from &ldquo;Dismiss&rdquo; (which removes it from your
            view) and &ldquo;Complete&rdquo; (which marks it as kept). This
            action propagates to the ledger and updates Maestro&apos;s
            predictions.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Keep it</AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            className="bg-rose-500/80 hover:bg-rose-500 text-white"
          >
            Yes, cancel it
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

function SkeletonCommitment() {
  return (
    <Card className="border-border/60">
      <CardContent className="pt-6 space-y-3">
        <div className="h-3 w-1/4 bg-muted/60 rounded animate-pulse" />
        <div className="h-5 w-3/4 bg-muted/40 rounded animate-pulse" />
        <div className="h-3 w-1/3 bg-muted/40 rounded animate-pulse" />
      </CardContent>
    </Card>
  );
}

"use client";

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Loader2,
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

export function Commitments() {
  const [theOne, setTheOne] = useState<CommitmentsTheOne | null>(null);
  const [list, setList] = useState<Commitment[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  // Phase 11 + 16: deal health per entity + meeting grades
  const [dealHealth, setDealHealth] = useState<any[]>([]);
  const [meetingGrades, setMeetingGrades] = useState<any[]>([]);

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      const [one, all, dh, mg] = await Promise.all([
        maestroApi.getCommitmentsTheOne(),
        maestroApi.getCommitments(),
        maestroApi.getDealHealth(),
        maestroApi.getMeetingGrades(),
      ]);
      if (!alive) return;
      setTheOne(one.data);
      setList(all.data);
      setDealHealth(dh.data?.deals ?? []);
      setMeetingGrades(mg.data?.grades ?? []);
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

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">Commitments</h2>
        <p className="text-sm text-muted-foreground mt-0.5">
          The one that matters most, and the rest.
        </p>
      </div>

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
          busy={busyId === theOne.primary.signal_id}
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
            {loading ? "loading…" : `${list.length} commitment${list.length === 1 ? "" : "s"}`}
          </span>
        </div>
        <div className="space-y-3">
          {loading ? (
            <SkeletonCommitment />
          ) : list.length === 0 ? (
            <Card className="border-border/60 border-dashed">
              <CardContent className="pt-6 pb-8 text-center text-sm text-muted-foreground">
                Nothing active.
              </CardContent>
            </Card>
          ) : (
            list.map((c) => (
              <CommitmentRow
                key={c.signal_id}
                c={c}
                onCorrect={correct}
                busy={busyId === c.signal_id}
              />
            ))
          )}
        </div>
      </div>

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
    </div>
  );
}

function TheOneCard({
  commitment,
  why,
  overallCalibration,
  onCorrect,
  busy,
}: {
  commitment: Commitment;
  why: string;
  overallCalibration?: string;
  onCorrect: (id: string, action: "complete" | "dismiss" | "cancel") => void;
  busy: boolean;
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
        </div>
      </CardContent>
    </Card>
  );
}

function CommitmentRow({
  c,
  onCorrect,
  busy,
}: {
  c: Commitment;
  onCorrect: (id: string, action: "complete" | "dismiss" | "cancel") => void;
  busy: boolean;
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

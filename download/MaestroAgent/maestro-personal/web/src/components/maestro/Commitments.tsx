"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Loader2,
  Mail,
  MessageSquare,
  Plus,
  Search,
  Sparkles,
  XCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import {
  confidenceColor,
  confidenceTextColor,
  confidenceTier,
  formatRelative,
  formatTimestamp,
  type Commitment,
  type CommitmentsTheOne,
  type Signal,
  maestroApi,
} from "@/lib/maestro-api";
import {
  DraftApprovalModal,
  type DraftWithMeta,
} from "./DraftApprovalModal";

// Signal types for the Add-Signal form (inlined from deleted Signals.tsx)
const SIGNAL_TYPES = [
  "reported_statement",
  "commitment_made",
  "commitment_received",
  "follow_up_required",
  "schedule_change",
  "material_objection",
  "observed_behavior",
  "outcome",
];

const SIGNALS_PAGE_SIZE = 50;

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

  // ── Signals-tab state (inlined from deleted Signals.tsx — matches mobile's
  // pattern of folding signal-correction UI into CommitmentsScreen rather than
  // keeping a standalone Signals screen) ──
  const [signals, setSignals] = useState<Signal[]>([]);
  const [signalsLoading, setSignalsLoading] = useState(false);
  const [signalsFilter, setSignalsFilter] = useState("");
  const [signalsPage, setSignalsPage] = useState(0);
  const [signalBusyId, setSignalBusyId] = useState<string | null>(null);
  const [newSignalEntity, setNewSignalEntity] = useState("");
  const [newSignalText, setNewSignalText] = useState("");
  const [newSignalType, setNewSignalType] = useState<string>("reported_statement");
  const [submittingSignal, setSubmittingSignal] = useState(false);

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

  // P0-Audit fix (2026-07-18): correct() now uses try/catch + .live check +
  // destructive toast on failure. Was: response discarded, list-refetch ran
  // unconditionally → user saw list unchanged (refetch returned same data
  // because backend state was unchanged) but had no idea the click failed.
  // Now: failure → destructive toast, success → refetch + toast.
  async function correct(signal_id: string, action: "complete" | "dismiss" | "cancel") {
    setBusyId(signal_id);
    try {
      const { live } = await maestroApi.correctSignal(signal_id, action);
      if (!live) {
        toast({ title: "Backend unreachable", description: "Could not correct the signal.", variant: "destructive" });
        return;
      }
      // Success — refetch both endpoints to reflect the server-side state change
      const [one, all] = await Promise.all([
        maestroApi.getCommitmentsTheOne(),
        maestroApi.getCommitments(),
      ]);
      setTheOne(one.data);
      setList(all.data);
      toast({
        title: action === "complete" ? "Marked complete" : action === "dismiss" ? "Dismissed" : "Cancelled",
        description: action === "complete" ? "Commitment closed." : "Removed from your view.",
      });
    } catch (e: any) {
      toast({ title: "Failed", description: e?.message || "Unknown error", variant: "destructive" });
    } finally {
      setBusyId(null);
    }
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

  // P1-#4 fix (2026-07-20): View Threads for Entity — calls getThreadsForEntity
  // and opens a modal showing the cross-meeting thread for that entity.
  // The client function existed but no UI called it (forensic audit P1 #4).
  const [threadsModalEntity, setThreadsModalEntity] = useState<string | null>(null);
  const [threadsModalData, setThreadsModalData] = useState<any[] | null>(null);
  const [threadsModalLoading, setThreadsModalLoading] = useState(false);
  async function handleViewThreads(entity: string) {
    if (!entity) return;
    setThreadsModalEntity(entity);
    setThreadsModalData(null);
    setThreadsModalLoading(true);
    try {
      const { data, live } = await maestroApi.getThreadsForEntity(entity);
      if (!live) {
        toast({ title: "Could not load threads", description: "API unreachable.", variant: "destructive" });
        setThreadsModalEntity(null);
      } else {
        setThreadsModalData(data?.threads ?? []);
      }
    } catch (e: any) {
      toast({ title: "Threads failed", description: e?.message || "Unknown error", variant: "destructive" });
      setThreadsModalEntity(null);
    } finally {
      setThreadsModalLoading(false);
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

  // ── Signals-tab handlers (inlined from deleted Signals.tsx) ──

  // Lazy-load signals only when user first switches to the Signals tab.
  // Avoids fetching /api/signals on the Commitments tab where it's not needed.
  useEffect(() => {
    if (tab !== "signals" || signals.length > 0 || signalsLoading) return;
    let alive = true;
    void (async () => {
      setSignalsLoading(true);
      const { data } = await maestroApi.getSignals();
      if (!alive) return;
      setSignals(data);
      setSignalsLoading(false);
    })();
    return () => {
      alive = false;
    };
  }, [tab]); // eslint-disable-line react-hooks/exhaustive-deps

  const filteredSignals = useMemo(() => {
    const q = signalsFilter.trim().toLowerCase();
    if (!q) return signals;
    return signals.filter(
      (s) =>
        s.entity.toLowerCase().includes(q) ||
        s.text.toLowerCase().includes(q) ||
        s.signal_type.toLowerCase().includes(q),
    );
  }, [signals, signalsFilter]);

  const totalSignalPages = Math.max(1, Math.ceil(filteredSignals.length / SIGNALS_PAGE_SIZE));
  const safeSignalPage = Math.min(signalsPage, totalSignalPages - 1);
  const pagedSignals = filteredSignals.slice(
    safeSignalPage * SIGNALS_PAGE_SIZE,
    (safeSignalPage + 1) * SIGNALS_PAGE_SIZE,
  );

  async function submitNewSignal(e: React.FormEvent) {
    e.preventDefault();
    if (!newSignalEntity.trim() || !newSignalText.trim()) return;
    setSubmittingSignal(true);
    const { data } = await maestroApi.createSignal(
      newSignalEntity.trim(),
      newSignalText.trim(),
      newSignalType,
    );
    setSignals((prev) => [data, ...prev]);
    setNewSignalEntity("");
    setNewSignalText("");
    setNewSignalType("reported_statement");
    setSubmittingSignal(false);
  }

  // P0-Audit fix (2026-07-18): correctSignal() now uses try/catch + .live check.
  // CRITICAL: the setSignals(prev => prev.filter(...)) list-removal moved INSIDE
  // the success branch. Was: ran unconditionally after the await → a failed
  // correction still visually removed the signal from the list, so the user
  // believed it worked when the backend state was unchanged.
  async function correctSignal(signal_id: string, action: "dismiss" | "complete" | "cancel") {
    setSignalBusyId(signal_id);
    try {
      const { live } = await maestroApi.correctSignal(signal_id, action);
      if (!live) {
        toast({ title: "Backend unreachable", description: "Could not correct the signal.", variant: "destructive" });
        return;
      }
      // Success — only NOW remove from list locally (API hides corrected signals on next fetch)
      setSignals((prev) => prev.filter((s) => s.signal_id !== signal_id));
      toast({
        title: action === "complete" ? "Marked complete" : action === "dismiss" ? "Dismissed" : "Cancelled",
        description: action === "complete" ? "Signal closed." : "Removed from your view.",
      });
    } catch (e: any) {
      toast({ title: "Failed", description: e?.message || "Unknown error", variant: "destructive" });
    } finally {
      setSignalBusyId(null);
    }
  }

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
        <SignalsTab
          signals={pagedSignals}
          loading={signalsLoading}
          filter={signalsFilter}
          onFilterChange={(v) => {
            setSignalsFilter(v);
            setSignalsPage(0);
          }}
          busyId={signalBusyId}
          onCorrect={correctSignal}
          newEntity={newSignalEntity}
          newText={newSignalText}
          newType={newSignalType}
          submitting={submittingSignal}
          onEntityChange={setNewSignalEntity}
          onTextChange={setNewSignalText}
          onTypeChange={setNewSignalType}
          onSubmitNew={submitNewSignal}
          page={safeSignalPage}
          totalPages={totalSignalPages}
          totalCount={filteredSignals.length}
          onPageChange={setSignalsPage}
        />
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
              onViewThreads={handleViewThreads}
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
                    onViewThreads={handleViewThreads}
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
                      <div className="flex items-center gap-2 shrink-0">
                        {/* P1-#6 fix (2026-07-20): Grade Override button — calls overrideMeetingGrade */}
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 text-xs"
                          onClick={async () => {
                            const newGrade = window.prompt(
                              `Override grade for ${g.entity || g.title || "this meeting"}.\nCurrent: ${g.effective_grade || g.grade}\nEnter new grade (A/B/C/D):`,
                              g.effective_grade || g.grade
                            );
                            if (!newGrade) return;
                            const upper = newGrade.trim().toUpperCase();
                            if (!["A", "B", "C", "D"].includes(upper)) {
                              toast({ title: "Invalid grade", description: "Must be A, B, C, or D.", variant: "destructive" });
                              return;
                            }
                            try {
                              const { live } = await maestroApi.overrideMeetingGrade(g.meeting_id, upper);
                              if (!live) {
                                toast({ title: "Override failed", description: "API unreachable.", variant: "destructive" });
                              } else {
                                toast({ title: "Grade overridden", description: `${g.entity || g.title}: ${g.grade} → ${upper}` });
                                // Refresh grades
                                const mg = await maestroApi.getMeetingGrades();
                                setMeetingGrades(mg.data?.grades ?? []);
                              }
                            } catch (e: any) {
                              toast({ title: "Override failed", description: e?.message || "Unknown error", variant: "destructive" });
                            }
                          }}
                          title="Override the meeting grade"
                        >
                          Override
                        </Button>
                        <span
                          className={cn(
                            "flex items-center justify-center rounded-lg w-9 h-9 text-lg font-black text-black",
                            g.grade === "A" ? "bg-green-500"
                              : g.grade === "B" ? "bg-yellow-500"
                              : g.grade === "C" ? "bg-yellow-600"
                              : "bg-red-500"
                          )}
                        >
                          {g.effective_grade || g.grade}
                        </span>
                      </div>
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

      {/* P1-#4 fix (2026-07-20): Threads-for-Entity modal — calls getThreadsForEntity */}
      <Dialog open={!!threadsModalEntity} onOpenChange={(o) => !o && setThreadsModalEntity(null)}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Cross-Meeting Threads: {threadsModalEntity}</DialogTitle>
            <DialogDescription>
              Decisions and signals tracked across meetings for this entity.
            </DialogDescription>
          </DialogHeader>
          {threadsModalLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="size-5 animate-spin text-muted-foreground" />
            </div>
          ) : threadsModalData && threadsModalData.length > 0 ? (
            <div className="space-y-3">
              {threadsModalData.map((t: any, i: number) => (
                <Card key={i} className="border-border/60">
                  <CardContent className="py-3 px-4 space-y-1">
                    <p className="text-sm font-medium">{t.entity || threadsModalEntity}</p>
                    <p className="text-sm text-foreground/80">{t.text || t.summary || t.topic}</p>
                    {t.timestamp && (
                      <p className="text-xs text-muted-foreground">{String(t.timestamp).slice(0, 10)}</p>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground py-6 text-center">
              No threads found for {threadsModalEntity}.
            </p>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function TheOneCard({
  commitment,
  why,
  overallCalibration,
  onCorrect,
  onDraft,
  onViewThreads,
  busy,
  draftBusy,
}: {
  commitment: Commitment;
  why: string;
  overallCalibration?: string;
  onCorrect: (id: string, action: "complete" | "dismiss" | "cancel") => void;
  onDraft: (entity: string) => void;
  onViewThreads?: (entity: string) => void;
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
  onViewThreads,
  busy,
  draftBusy,
}: {
  c: Commitment;
  onCorrect: (id: string, action: "complete" | "dismiss" | "cancel") => void;
  onDraft: (entity: string) => void;
  onViewThreads?: (entity: string) => void;
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
          {/* P1-#4 fix (2026-07-20): View Threads button — calls getThreadsForEntity */}
          <Button
            size="sm"
            variant="ghost"
            className="h-7 text-xs bg-blue-500/10 text-blue-700 dark:text-blue-300 hover:bg-blue-500/20"
            onClick={() => onViewThreads?.(c.entity)}
            title={`View cross-meeting threads for ${c.entity}`}
          >
            <MessageSquare className="size-3" />
            Threads
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

/* ───────────────────────────────────────────────────────────────
 * SignalsTab — inlined from deleted Signals.tsx.
 * Renders Add-Signal form + filter + signal table with correction buttons.
 * Mobile's CommitmentsScreen renders signals as a read-only FlatList; we keep
 * the Add-Signal form + correction buttons because web doesn't have swipe
 * gestures (mobile corrects via swipe). The segmented-control pattern matches.
 * ─────────────────────────────────────────────────────────────── */

function SignalsTab({
  signals,
  loading,
  filter,
  onFilterChange,
  busyId,
  onCorrect,
  newEntity,
  newText,
  newType,
  submitting,
  onEntityChange,
  onTextChange,
  onTypeChange,
  onSubmitNew,
  page,
  totalPages,
  totalCount,
  onPageChange,
}: {
  signals: Signal[];
  loading: boolean;
  filter: string;
  onFilterChange: (v: string) => void;
  busyId: string | null;
  onCorrect: (signal_id: string, action: "dismiss" | "complete" | "cancel") => void;
  newEntity: string;
  newText: string;
  newType: string;
  submitting: boolean;
  onEntityChange: (v: string) => void;
  onTextChange: (v: string) => void;
  onTypeChange: (v: string) => void;
  onSubmitNew: (e: React.FormEvent) => void;
  page: number;
  totalPages: number;
  totalCount: number;
  onPageChange: (p: number) => void;
}) {
  return (
    <div className="space-y-6">
      {/* Add-signal form */}
      <Card className="border-border/60">
        <CardContent className="pt-6">
          <form onSubmit={onSubmitNew} className="space-y-3">
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              <Plus className="size-3.5" />
              <span>Add a signal</span>
            </div>
            <div className="grid gap-3 md:grid-cols-[200px_1fr_220px_auto]">
              <Input
                placeholder="Entity (e.g. Maria Garcia)"
                value={newEntity}
                onChange={(e) => onEntityChange(e.target.value)}
                className="bg-input/40 border-border/60"
              />
              <Input
                placeholder="What you observed or were told"
                value={newText}
                onChange={(e) => onTextChange(e.target.value)}
                className="bg-input/40 border-border/60"
              />
              <Select value={newType} onValueChange={onTypeChange}>
                <SelectTrigger className="bg-input/40 border-border/60 w-full">
                  <SelectValue placeholder="Signal type" />
                </SelectTrigger>
                <SelectContent>
                  {SIGNAL_TYPES.map((t) => (
                    <SelectItem key={t} value={t}>
                      {t.replace(/_/g, " ")}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button type="submit" disabled={submitting || !newEntity.trim() || !newText.trim()}>
                {submitting ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />}
                Add
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {/* Filter + table */}
      <Card className="border-border/60">
        <CardContent className="pt-6 space-y-4">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <h3 className="text-sm font-semibold">All signals</h3>
            <div className="relative w-full sm:w-64">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground" />
              <Input
                value={filter}
                onChange={(e) => onFilterChange(e.target.value)}
                placeholder="Filter signals…"
                className="pl-9 h-8 text-sm bg-input/40 border-border/60"
              />
            </div>
          </div>

          {loading ? (
            <div className="py-12 flex items-center justify-center">
              <Loader2 className="size-5 text-muted-foreground animate-spin" />
            </div>
          ) : signals.length === 0 ? (
            <p className="text-sm text-muted-foreground py-8 text-center">
              {filter ? "No signals match your filter." : "No signals yet. Add one above."}
            </p>
          ) : (
            <div className="rounded-lg border border-border/60 overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead className="w-[140px]">Entity</TableHead>
                    <TableHead>Text</TableHead>
                    <TableHead className="w-[150px]">Type</TableHead>
                    <TableHead className="w-[140px]">When</TableHead>
                    <TableHead className="w-[180px] text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {signals.map((s) => (
                    <TableRow key={s.signal_id} className="group">
                      <TableCell className="font-medium text-foreground/90 align-top">
                        {s.entity}
                      </TableCell>
                      <TableCell className="text-foreground/80 align-top">
                        <span className="line-clamp-2">{s.text}</span>
                      </TableCell>
                      <TableCell className="align-top">
                        <span className="text-xs px-2 py-0.5 rounded-full bg-muted/60 border border-border/60 text-muted-foreground capitalize">
                          {s.signal_type.replace(/_/g, " ")}
                        </span>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground align-top" title={formatTimestamp(s.timestamp)}>
                        {formatRelative(s.timestamp)}
                      </TableCell>
                      <TableCell className="text-right align-top">
                        <div className="inline-flex gap-1 opacity-70 group-hover:opacity-100 transition-opacity">
                          <Button
                            size="sm"
                            variant="ghost"
                            className="h-7 px-2 text-xs text-emerald-300 hover:text-emerald-200"
                            disabled={busyId === s.signal_id}
                            onClick={() => onCorrect(s.signal_id, "complete")}
                            title="Mark complete"
                          >
                            <CheckCircle2 className="size-3.5" />
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground"
                            disabled={busyId === s.signal_id}
                            onClick={() => onCorrect(s.signal_id, "dismiss")}
                            title="Dismiss"
                          >
                            Dismiss
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            className="h-7 px-2 text-xs text-rose-300 hover:text-rose-200"
                            disabled={busyId === s.signal_id}
                            onClick={() => onCorrect(s.signal_id, "cancel")}
                            title="Cancel"
                          >
                            <XCircle className="size-3.5" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}

          {/* Pagination */}
          {totalCount > SIGNALS_PAGE_SIZE && (
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>
                Showing {page * SIGNALS_PAGE_SIZE + 1}–{Math.min(totalCount, (page + 1) * SIGNALS_PAGE_SIZE)} of {totalCount}
              </span>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 text-xs"
                  disabled={page === 0}
                  onClick={() => onPageChange(Math.max(0, page - 1))}
                >
                  Prev
                </Button>
                <span className="px-2 py-1.5">
                  {page + 1} / {totalPages}
                </span>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 text-xs"
                  disabled={page >= totalPages - 1}
                  onClick={() => onPageChange(Math.min(totalPages - 1, page + 1))}
                >
                  Next
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

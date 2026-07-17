"use client";

import { useEffect, useState } from "react";
import {
  ArrowRight,
  CalendarClock,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Eye,
  Loader2,
  Mail,
  Quote,
  Sparkles,
  Wind,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import {
  confidenceTextColor,
  formatRelative,
  type Briefing,
  type CopilotWhisper,
  type LlmStatus,
  type TheMoment,
  type TheShifts,
  maestroApi,
} from "@/lib/maestro-api";
import { MaestroMark } from "./mark";
import {
  DraftApprovalModal,
  type DraftWithMeta,
} from "./DraftApprovalModal";

export function Dashboard({
  llm,
  onAsk,
  onNavigate,
}: {
  llm: LlmStatus | null;
  onAsk: (query: string) => void;
  onNavigate: (view: "ask" | "commitments") => void;
}) {
  const { toast } = useToast();
  const [moment, setMoment] = useState<TheMoment | null>(null);
  const [shifts, setShifts] = useState<TheShifts | null>(null);
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [whispers, setWhispers] = useState<CopilotWhisper[]>([]);
  const [loading, setLoading] = useState(true);
  const [quickAsk, setQuickAsk] = useState("");
  // Ambient intelligence state (Phases 9, 11, 19)
  const [smartNotifs, setSmartNotifs] = useState<any[]>([]);
  const [escalations, setEscalations] = useState<any[]>([]);
  const [dealHealth, setDealHealth] = useState<any[]>([]);
  const [upcomingMeetings, setUpcomingMeetings] = useState<any[]>([]);

  // P0-1 + P0-4: state for Done/Skip/Draft/Snooze on The Moment
  const [momentBusy, setMomentBusy] = useState<"complete" | "dismiss" | "draft" | "snooze" | null>(null);
  // P0-3 + P0-4: shared draft approval modal
  const [draftForReview, setDraftForReview] = useState<DraftWithMeta | null>(null);
  const [draftResolving, setDraftResolving] = useState(false);

  async function refreshMoment() {
    const m = await maestroApi.getTheMoment();
    setMoment(m.data);
  }

  // P0-1: Done / Skip — call correctSignal, then refresh The Moment
  async function handleMomentCorrect(action: "complete" | "dismiss") {
    if (!moment?.commitment?.signal_id) return;
    setMomentBusy(action);
    try {
      const { data, live } = await maestroApi.correctSignal(moment.commitment.signal_id, action);
      if (!live) {
        toast({ title: "Backend unreachable", description: "Could not reach the API on :8766.", variant: "destructive" });
      } else {
        toast({
          title: action === "complete" ? "Marked complete" : "Skipped",
          description: action === "complete" ? "Nice — one less thing." : "Snoozed for now.",
        });
      }
      await refreshMoment();
    } catch (e: any) {
      toast({ title: "Failed", description: e?.message || "Unknown error", variant: "destructive" });
    } finally {
      setMomentBusy(null);
    }
  }

  // P1-2: Snooze — same API action as Skip (dismiss) + client-side 2h toast
  async function handleSnooze() {
    if (!moment?.commitment?.signal_id) return;
    setMomentBusy("snooze");
    try {
      const { live } = await maestroApi.correctSignal(moment.commitment.signal_id, "dismiss");
      if (!live) {
        toast({ title: "Backend unreachable", description: "Could not reach the API on :8766.", variant: "destructive" });
      } else {
        toast({ title: "Snoozed for 2 hours", description: "Maestro will remind you later this morning." });
      }
      await refreshMoment();
    } catch (e: any) {
      toast({ title: "Failed", description: e?.message || "Unknown error", variant: "destructive" });
    } finally {
      setMomentBusy(null);
    }
  }

  // P0-4: Draft from The Moment — call generateAutoDraft, open shared modal
  async function handleMomentDraft() {
    const entity = moment?.commitment?.entity;
    if (!entity) return;
    setMomentBusy("draft");
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
      setMomentBusy(null);
    }
  }

  // P0-5: Whisper "Draft follow-up" — call generateAutoDraft (was: onAsk)
  async function handleWhisperDraft(entity: string) {
    if (!entity) return;
    setMomentBusy("draft");
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
      setMomentBusy(null);
    }
  }

  // Resolve draft (shared modal) — approve / deny / use_draft
  async function handleResolveDraft(draft: DraftWithMeta, resolution: "approve" | "deny" | "use_draft") {
    setDraftResolving(true);
    try {
      const { live } = await maestroApi.resolveDraft(draft.draft_id, resolution);
      if (!live) {
        toast({ title: "Backend unreachable", description: "Could not reach the API.", variant: "destructive" });
      } else if (resolution === "approve") {
        toast({ title: "Sent", description: "Your email has been sent." });
      } else if (resolution === "use_draft") {
        // Web equivalent of mobile's Share.share: copy body to clipboard + open mailto:
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

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      const [m, s, b, w, sn, esc, dh, cal] = await Promise.all([
        maestroApi.getTheMoment(),
        maestroApi.getTheShifts(),
        maestroApi.getBriefing(),
        maestroApi.getWhispers(),
        maestroApi.getSmartNotifications({ limit: 5 }),
        maestroApi.getEscalations(),
        maestroApi.getDealHealth(),
        maestroApi.getCalendarAwareness(48),
      ]);
      if (!alive) return;
      setMoment(m.data);
      setShifts(s.data);
      setBriefing(b.data);
      setWhispers(Array.isArray(w.data) ? w.data : []);
      setSmartNotifs(sn.data?.notifications ?? []);
      setEscalations(esc.data?.escalations ?? []);
      setDealHealth(dh.data?.deals ?? []);
      setUpcomingMeetings(cal.data?.meetings ?? []);
      setLoading(false);
    })();
    // Issue 13-E: auto-refresh whispers every 60s
    const interval = setInterval(async () => {
      const w = await maestroApi.getWhispers();
      if (alive) setWhispers(Array.isArray(w.data) ? w.data : []);
    }, 60000);
    return () => {
      alive = false;
      clearInterval(interval);
    };
  }, []);

  function submitQuickAsk(e: React.FormEvent) {
    e.preventDefault();
    if (!quickAsk.trim()) return;
    onAsk(quickAsk.trim());
    setQuickAsk("");
  }

  return (
    <div className="space-y-6">
      {/* AMBIENT INTELLIGENCE — Smart Notifications (Phase 19) */}
      {smartNotifs.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-red-500 flex items-center gap-1.5">
            <span>🔔 Needs Attention</span>
          </h3>
          {smartNotifs.slice(0, 3).map((n) => (
            <button
              key={n.notification_id}
              onClick={() => onNavigate("commitments")}
              className={cn(
                "w-full text-left rounded-lg border p-3 transition-colors hover:bg-accent",
                n.priority === "critical" ? "border-red-300 bg-red-50 dark:bg-red-950/20" : "border-border bg-card"
              )}
            >
              <p className="font-semibold text-sm">{n.title}</p>
              <p className="text-sm text-muted-foreground mt-0.5 line-clamp-2">{n.body}</p>
            </button>
          ))}
        </div>
      )}

      {/* AMBIENT INTELLIGENCE — Commitment Escalations (Phase 9) */}
      {escalations.filter((e) => e.escalation_level === "high" || e.escalation_level === "critical").length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-red-500 flex items-center gap-1.5">
            <span>⚠️ Escalations</span>
          </h3>
          {escalations
            .filter((e) => e.escalation_level === "high" || e.escalation_level === "critical")
            .slice(0, 3)
            .map((e) => (
              <button
                key={e.commitment_id}
                onClick={() => onNavigate("commitments")}
                className={cn(
                  "w-full text-left rounded-lg border-l-4 border p-3 bg-card transition-colors hover:bg-accent",
                  e.escalation_level === "critical" ? "border-red-500" : "border-yellow-500"
                )}
              >
                <p className="font-semibold text-sm">
                  {e.entity ? `${e.entity} · ` : ""}{(e.commitment_text ?? "").slice(0, 60)}
                </p>
                {e.days_overdue ? (
                  <p className="text-xs text-red-500 font-medium mt-0.5">{e.days_overdue} days overdue</p>
                ) : null}
                {e.nudge_text ? (
                  <p className="text-sm text-muted-foreground mt-1 line-clamp-2">→ {e.nudge_text}</p>
                ) : null}
              </button>
            ))}
        </div>
      )}

      {/* AMBIENT INTELLIGENCE — Deal Health (Phase 11) */}
      {dealHealth.filter((d) => d.status === "at_risk" || d.status === "critical").length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-red-500 flex items-center gap-1.5">
            <span>📉 Deals at Risk</span>
          </h3>
          {dealHealth
            .filter((d) => d.status === "at_risk" || d.status === "critical")
            .slice(0, 3)
            .map((d) => (
              <div key={d.entity} className="flex items-center justify-between rounded-lg border p-3 bg-card">
                <div className="flex-1">
                  <p className="font-semibold text-sm">{d.entity}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {d.momentum === "decelerating" ? "↓ decelerating" : d.momentum === "accelerating" ? "↑ accelerating" : "→ stable"}
                  </p>
                </div>
                <span
                  className={cn(
                    "rounded-md px-2.5 py-1 text-sm font-bold text-black",
                    d.status === "critical" ? "bg-red-500" : "bg-yellow-500"
                  )}
                >
                  {Math.round(d.score)}%
                </span>
              </div>
            ))}
        </div>
      )}

      {/* AMBIENT INTELLIGENCE — Calendar Awareness (Phase 9) */}
      {upcomingMeetings.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-blue-500 flex items-center gap-1.5">
            <span>📅 Upcoming Meetings</span>
          </h3>
          {upcomingMeetings.slice(0, 2).map((m) => (
            <div key={m.meeting_id} className="rounded-lg border-l-4 border-yellow-500 border p-3 bg-card">
              <p className="font-semibold text-sm">{m.title || "Untitled Meeting"}</p>
              {m.entity ? (
                <p className="text-xs text-muted-foreground mt-0.5">{m.entity} · {m.urgency}</p>
              ) : null}
              {m.suggested_talking_points && m.suggested_talking_points.length > 0 && (
                <div className="mt-2">
                  <p className="text-xs font-semibold text-muted-foreground mb-1">TALKING POINTS</p>
                  {m.suggested_talking_points.slice(0, 3).map((tp: any, i: number) => (
                    <p key={i} className="text-sm text-foreground/90">
                      • {typeof tp === "string" ? tp : tp.text || tp.topic || JSON.stringify(tp)}
                    </p>
                  ))}
                </div>
              )}
              {typeof m.open_commitments === "number" && m.open_commitments > 0 ? (
                <p className="text-xs text-red-500 mt-2 font-medium">
                  {m.open_commitments} open commitment{m.open_commitments !== 1 ? "s" : ""}
                </p>
              ) : null}
            </div>
          ))}
        </div>
      )}

      {/* Greeting strip */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-xl font-semibold tracking-tight">
            {briefing?.greeting?.trim() || "Good morning."}
          </h2>
          <p className="text-sm text-muted-foreground mt-0.5">
            Here&apos;s what Maestro knows right now.
          </p>
        </div>
        <LlmBadge llm={llm} />
      </div>

      {/* The Moment — hero */}
      <TheMomentCard
        loading={loading}
        moment={moment}
        onNavigate={onNavigate}
        onCorrect={handleMomentCorrect}
        onSnooze={handleSnooze}
        onDraft={handleMomentDraft}
        busy={momentBusy}
      />

      {/* Issue 13-C: Whisper cards — "💌 Needs Attention" */}
      {!loading && whispers.length > 0 && (
        <WhisperCards
          whispers={whispers}
          onAsk={onAsk}
          onDraft={handleWhisperDraft}
          draftBusy={momentBusy === "draft"}
        />
      )}

      {/* What Changed + Briefing */}
      <div className="grid gap-6 lg:grid-cols-2">
        <WhatChangedCard loading={loading} shifts={shifts} />
        <BriefingCard loading={loading} briefing={briefing} onNavigate={onNavigate} />
      </div>

      {/* Quick Ask */}
      <Card className="border-border/60 bg-card/40">
        <CardContent className="pt-6">
          <form onSubmit={submitQuickAsk} className="flex flex-col sm:flex-row gap-3">
            <div className="relative flex-1">
              <Sparkles className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
              <Input
                value={quickAsk}
                onChange={(e) => setQuickAsk(e.target.value)}
                placeholder="Ask Maestro anything — “What did I promise Maria?”"
                className="pl-9 h-11 bg-input/40 border-border/60"
              />
            </div>
            <Button type="submit" size="lg" className="h-11" disabled={!quickAsk.trim()}>
              Ask
              <ArrowRight className="size-4" />
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* P0-3 + P0-4 + P0-5: Shared Draft Approval Modal */}
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

/* ---------------- The Moment ---------------- */

function TheMomentCard({
  loading,
  moment,
  onNavigate,
  onCorrect,
  onSnooze,
  onDraft,
  busy,
}: {
  loading: boolean;
  moment: TheMoment | null;
  onNavigate: (view: "ask" | "commitments") => void;
  onCorrect: (action: "complete" | "dismiss") => void;
  onSnooze: () => void;
  onDraft: () => void;
  busy: "complete" | "dismiss" | "draft" | "snooze" | null;
}) {
  const [expanded, setExpanded] = useState(false);
  const signalId = moment?.commitment?.signal_id;
  const disabled = !signalId || busy !== null;

  return (
    <Card className="relative overflow-hidden border-primary/40 border-l-4 surface-elevated">
      {/* Subtle ambient glow — Bumble warm */}
      <div
        className="pointer-events-none absolute -top-24 -left-24 h-64 w-64 rounded-full bg-primary/10 blur-3xl"
        aria-hidden
      />
      <CardContent className="relative pt-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-[0.18em]">
              The Moment
            </span>
          </div>
          <span className="text-[11px] text-muted-foreground/70">
            {loading ? "loading…" : "the one thing that matters most"}
          </span>
        </div>

        {loading ? (
          <div className="py-8 flex items-center justify-center">
            <Loader2 className="size-5 text-muted-foreground animate-spin" />
          </div>
        ) : moment?.has_moment && moment.commitment ? (
          <div className="space-y-5">
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="block w-full text-left space-y-2 group"
              aria-expanded={expanded}
              aria-controls="moment-evidence-panel"
            >
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-sm">
                  <span className="font-medium text-foreground">
                    {moment.commitment.entity}
                  </span>
                  {moment.situation?.state && (
                    <span className="text-muted-foreground">
                      · situation: {moment.situation.state.replace(/_/g, " ")}
                    </span>
                  )}
                  {moment.source_evidence && moment.source_evidence.length > 0 && (
                    <span className="ml-auto inline-flex items-center gap-1 text-[10px] text-muted-foreground/70 group-hover:text-muted-foreground">
                      {expanded ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
                      {expanded ? "hide evidence" : `${moment.source_evidence.length} source${moment.source_evidence.length === 1 ? "" : "s"}`}
                    </span>
                  )}
                </div>
                <p className="text-2xl sm:text-3xl font-medium leading-tight text-balance text-pretty">
                  {moment.commitment.text}
                </p>
              </div>
            </button>

            {/* P1-1: Expandable evidence panel */}
            {expanded && moment.source_evidence && moment.source_evidence.length > 0 && (
              <div id="moment-evidence-panel" className="space-y-2">
                {moment.source_evidence.map((ev: any, i: number) => (
                  <div key={i} className="flex gap-3 text-sm">
                    <Quote className="size-4 shrink-0 text-muted-foreground/70 mt-0.5" />
                    <div className="space-y-1">
                      <p className="text-muted-foreground italic">
                        &ldquo;{ev.text}&rdquo;
                      </p>
                      <p className="text-xs text-muted-foreground/70">
                        {ev.entity} ·{" "}
                        {formatRelative(ev.timestamp)} · source:{" "}
                        {ev.source}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Compact single provenance quote when not expanded */}
            {!expanded && moment.source_evidence?.[0] && (
              <div className="flex gap-3 text-sm">
                <Quote className="size-4 shrink-0 text-muted-foreground/70 mt-0.5" />
                <div className="space-y-1">
                  <p className="text-muted-foreground italic">
                    &ldquo;{moment.source_evidence[0].text}&rdquo;
                  </p>
                  <p className="text-xs text-muted-foreground/70">
                    {moment.source_evidence[0].entity} ·{" "}
                    {formatRelative(moment.source_evidence[0].timestamp)} · source:{" "}
                    {moment.source_evidence[0].source}
                  </p>
                </div>
              </div>
            )}

            <div className="flex flex-wrap items-center gap-2 pt-1">
              {moment.why_this_one && (
                <span className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full bg-muted/60 border border-border/60 text-muted-foreground">
                  <CalendarClock className="size-3" />
                  {moment.why_this_one}
                </span>
              )}
            </div>

            {/* P0-1 + P0-4 + P1-2: Done / Skip / Snooze / Draft actions */}
            <div className="flex flex-wrap items-center gap-2 pt-2">
              <Button
                size="sm"
                className="h-9 bg-emerald-500 text-white hover:bg-emerald-600"
                disabled={disabled}
                onClick={() => onCorrect("complete")}
                title={!signalId ? "No signal to mark complete" : undefined}
              >
                {busy === "complete" ? <Loader2 className="size-4 animate-spin" /> : <CheckCircle2 className="size-4" />}
                Done
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-9 text-muted-foreground hover:text-foreground"
                disabled={disabled}
                onClick={() => onCorrect("dismiss")}
              >
                {busy === "dismiss" ? <Loader2 className="size-4 animate-spin" /> : null}
                Skip
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-9 text-muted-foreground hover:text-foreground"
                disabled={disabled}
                onClick={onSnooze}
                title="Snooze for 2 hours (client-side)"
              >
                {busy === "snooze" ? <Loader2 className="size-4 animate-spin" /> : <CalendarClock className="size-4" />}
                Snooze 2h
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="h-9 bg-amber-500/10 border-amber-500/30 text-amber-700 dark:text-amber-300 hover:bg-amber-500/20"
                disabled={disabled}
                onClick={onDraft}
                title="Draft a follow-up email for this commitment"
              >
                {busy === "draft" ? <Loader2 className="size-4 animate-spin" /> : <Mail className="size-4" />}
                Draft
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-9 text-xs ml-auto"
                onClick={() => onNavigate("commitments")}
              >
                See all commitments
                <ArrowRight className="size-3" />
              </Button>
            </div>
          </div>
        ) : (
          <TrustedSilence why={moment?.why_this_one} />
        )}
      </CardContent>
    </Card>
  );
}

function TrustedSilence({ why }: { why?: string }) {
  return (
    <div className="py-10 flex flex-col items-center justify-center text-center gap-4">
      <div className="relative">
        <div className="absolute inset-0 rounded-full bg-emerald-500/10 blur-2xl" aria-hidden />
        <div className="relative size-14 rounded-full bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center">
          <Wind className="size-6 text-emerald-400" />
        </div>
      </div>
      <div className="space-y-1">
        <p className="text-xl font-medium">Nothing needs your attention right now.</p>
        <p className="text-sm text-muted-foreground max-w-sm">
          Maestro is watching quietly. When something deserves your attention,
          it will appear here.
        </p>
      </div>
      {why && (
        <p className="text-xs text-muted-foreground/60 max-w-md italic">{why}</p>
      )}
    </div>
  );
}

/* ---------------- What Changed ---------------- */

function WhatChangedCard({
  loading,
  shifts,
}: {
  loading: boolean;
  shifts: TheShifts | null;
}) {
  const items = shifts?.the_shifts ?? [];
  return (
    <Card className="border-border/60">
      <CardContent className="pt-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold">What changed</h3>
          <span className="text-[11px] text-muted-foreground/70">
            {loading ? "loading…" : items.length === 0 ? "silence" : `${items.length} material shift${items.length === 1 ? "" : "s"}`}
          </span>
        </div>
        {loading ? (
          <SkeletonRows n={2} />
        ) : items.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4">
            {shifts?.silence_message || "Nothing material changed since you last looked."}
          </p>
        ) : (
          <ul className="space-y-3">
            {items.map((s, i) => (
              <li
                key={i}
                className="rounded-lg border border-border/60 bg-muted/30 p-3"
              >
                <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
                  <span className="font-medium text-foreground/90">{s.entity}</span>
                  <span>·</span>
                  <span className="capitalize">{s.type.replace(/_/g, " ")}</span>
                </div>
                <p className="text-sm text-foreground/90 leading-relaxed">
                  {s.text}
                </p>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

/* ---------------- Briefing ---------------- */

function BriefingCard({
  loading,
  briefing,
  onNavigate,
}: {
  loading: boolean;
  briefing: Briefing | null;
  onNavigate: (view: "ask" | "commitments") => void;
}) {
  const watchingCount = briefing?.watching_quietly?.length ?? 0;
  return (
    <Card className="border-border/60">
      <CardContent className="pt-6 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">Briefing</h3>
          <span className="text-[11px] text-muted-foreground/70">
            {loading ? "loading…" : "situation-centric"}
          </span>
        </div>

        {loading ? (
          <SkeletonRows n={3} />
        ) : (
          <>
            {briefing?.top_situation && (
              <div className="rounded-lg border border-border/60 bg-muted/30 p-3">
                <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1">
                  Top situation
                </div>
                <p className="text-sm font-medium text-foreground/90">
                  {briefing.top_situation.entity}
                </p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {briefing.top_situation.summary ||
                    `state: ${briefing.top_situation.state}`}
                </p>
              </div>
            )}

            {briefing?.next_step && (
              <div className="text-sm">
                <span className="text-muted-foreground">Next step: </span>
                <span className="text-foreground/90">{briefing.next_step}</span>
              </div>
            )}

            {briefing?.can_decide_now && briefing.can_decide_now.length > 0 && (
              <div className="text-sm space-y-1">
                <div className="text-[11px] uppercase tracking-wider text-emerald-400/80">
                  Can decide now
                </div>
                <ul className="space-y-1">
                  {briefing.can_decide_now.map((d, i) => (
                    <li key={i} className="text-foreground/90 flex gap-2">
                      <span className="text-emerald-400/70">·</span>
                      <span>{d}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {briefing?.cannot_decide_yet && briefing.cannot_decide_yet.length > 0 && (
              <div className="text-sm space-y-1">
                <div className="text-[11px] uppercase tracking-wider text-amber-400/80">
                  Cannot decide yet
                </div>
                <ul className="space-y-1">
                  {briefing.cannot_decide_yet.map((d, i) => (
                    <li key={i} className="text-foreground/90 flex gap-2">
                      <span className="text-amber-400/70">·</span>
                      <span>{d}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <button
              type="button"
              onClick={() => onNavigate("ask")}
              className="w-full mt-2 flex items-center justify-between gap-2 rounded-lg border border-border/60 bg-muted/20 hover:bg-muted/40 transition-colors p-3 text-left"
            >
              <div className="flex items-center gap-2">
                <Eye className="size-4 text-muted-foreground" />
                <div>
                  <div className="text-sm font-medium">Watching quietly</div>
                  <div className="text-xs text-muted-foreground">
                    {watchingCount} situation{watchingCount === 1 ? "" : "s"} under observation
                  </div>
                </div>
              </div>
              <ArrowRight className="size-4 text-muted-foreground" />
            </button>
          </>
        )}
      </CardContent>
    </Card>
  );
}

/* ---------------- shared bits ---------------- */

export function LlmBadge({ llm }: { llm: LlmStatus | null }) {
  const active = !!llm?.active;
  const configured = !!llm?.configured;
  const color = active
    ? "bg-emerald-500"
    : configured
      ? "bg-amber-500"
      : "bg-zinc-500";
  const label = active
    ? `LLM · ${llm?.provider ?? "live"}`
    : configured
      ? "LLM configured"
      : "Rule-based";
  return (
    <div className="inline-flex items-center gap-2 rounded-full border border-border/60 bg-muted/30 px-3 py-1.5">
      <span className={cn("size-2 rounded-full", color)} aria-hidden />
      <span className="text-xs font-medium text-foreground/90">{label}</span>
    </div>
  );
}

function SkeletonRows({ n }: { n: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: n }).map((_, i) => (
        <div key={i} className="space-y-2">
          <div className="h-3 w-1/3 rounded bg-muted/60 animate-pulse" />
          <div className="h-3 w-2/3 rounded bg-muted/40 animate-pulse" />
        </div>
      ))}
    </div>
  );
}

// Issue 13-C: WhisperCards — "💌 Needs Attention" section on Dashboard.
// Shows proactive whispers (post-its) below The Moment card.
function WhisperCards({
  whispers,
  onAsk,
  onDraft,
  draftBusy,
}: {
  whispers: CopilotWhisper[];
  onAsk: (query: string) => void;
  onDraft: (entity: string) => void;
  draftBusy: boolean;
}) {
  // Normalize: whispers may be a single object or array
  const list = Array.isArray(whispers) ? whispers : [whispers];

  const priorityColor = (p: string) => {
    switch (p?.toLowerCase()) {
      case "critical": return "border-rose-500/40 bg-rose-500/[0.05]";
      case "high": return "border-amber-500/40 bg-amber-500/[0.05]";
      case "medium": return "border-blue-500/40 bg-blue-500/[0.05]";
      default: return "border-border/60 bg-muted/20";
    }
  };

  return (
    <Card className="border-border/60">
      <CardContent className="pt-6 space-y-3">
        <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
          <span className="text-base">💌</span>
          <span>Needs Attention ({list.length})</span>
        </div>
        <p className="text-xs text-muted-foreground">
          Proactive reminders — things Maestro noticed so you don&apos;t have to ask.
        </p>
        <div className="space-y-2">
          {list.slice(0, 5).map((w, i) => {
            const entity = w.entity || "";
            return (
              <div
                key={i}
                className={cn(
                  "rounded-lg border p-3 transition-colors",
                  priorityColor(w.priority || ""),
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs font-semibold text-foreground">
                        {entity || "Attention"}
                      </span>
                      {w.priority && (
                        <span className="text-[10px] uppercase tracking-wider text-muted-foreground/70">
                          {w.priority}
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-foreground/80 line-clamp-2">
                      {w.body || w.title || ""}
                    </p>
                  </div>
                  {/* P0-5: Draft follow-up now actually generates a draft (was: onAsk) */}
                  <div className="flex flex-col gap-1 shrink-0">
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-xs"
                      disabled={draftBusy || !entity}
                      onClick={() => onDraft(entity)}
                      title={!entity ? "No entity to draft for" : "Generate a follow-up email draft"}
                    >
                      {draftBusy ? <Loader2 className="size-3 animate-spin" /> : <Mail className="size-3" />}
                      Draft
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-xs text-muted-foreground"
                      onClick={() => onAsk(`What should I do about ${entity}?`)}
                    >
                      Ask
                    </Button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

export { MaestroMark };

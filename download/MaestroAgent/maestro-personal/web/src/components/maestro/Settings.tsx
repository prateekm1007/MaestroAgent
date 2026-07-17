"use client";

import { useEffect, useState } from "react";
import {
  Activity,
  Brain,
  CheckCircle2,
  Database,
  Download,
  Loader2,
  Shield,
  ShieldAlert,
  Trash2,
  ToggleLeft,
  ToggleRight,
  TrendingUp,
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import {
  formatTimestamp,
  type AuditLog,
  type Calibration,
  type LlmStatus,
  type PrivacyMode,
  maestroApi,
} from "@/lib/maestro-api";
import { Connectors } from "@/components/maestro/Connectors";

export function Settings() {
  const [llm, setLlm] = useState<LlmStatus | null>(null);
  const [privacy, setPrivacy] = useState<PrivacyMode | null>(null);
  const [calibration, setCalibration] = useState<Calibration | null>(null);
  const [audit, setAudit] = useState<AuditLog | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleted, setDeleted] = useState(false);
  const [consent, setConsent] = useState<Record<string, Record<string, boolean>> | null>(null);
  const [consentDefaults, setConsentDefaults] = useState<Record<string, Record<string, boolean>> | null>(null);
  // Phase 20: ambient analytics
  const [analyticsReport, setAnalyticsReport] = useState<any>(null);
  const [flywheelSummary, setFlywheelSummary] = useState("");

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      const [l, p, c, a, cs, at, af] = await Promise.all([
        maestroApi.getLlmStatus(),
        maestroApi.getPrivacyMode(),
        maestroApi.getCalibration(),
        maestroApi.getAuditLog(),
        maestroApi.getConsentSettings(),
        maestroApi.getAnalyticsTrends(),
        maestroApi.getAnalyticsFlywheel(),
      ]);
      if (!alive) return;
      setLlm(l.data);
      setPrivacy(p.data);
      setCalibration(c.data);
      setAudit(a.data);
      setConsent(cs.data.consent);
      setConsentDefaults(cs.data.defaults);
      setAnalyticsReport(at.data?.report ?? null);
      setFlywheelSummary(af.data?.summary ?? "");
      setLoading(false);
    })();
    return () => {
      alive = false;
    };
  }, []);

  async function exportData() {
    setExporting(true);
    const { data } = await maestroApi.getAccountExport();
    setExporting(false);
    // Trigger download
    const blob = new Blob([JSON.stringify(data, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `maestro-export-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  async function deleteAccount() {
    setDeleting(true);
    await maestroApi.deleteAccount();
    setDeleting(false);
    setDeleted(true);
  }

  if (deleted) {
    return (
      <div className="space-y-6">
        <div>
          <h2 className="text-xl font-semibold tracking-tight">Settings</h2>
        </div>
        <Card className="border-emerald-500/30 bg-emerald-500/[0.04]">
          <CardContent className="pt-6 flex items-start gap-3">
            <CheckCircle2 className="size-5 text-emerald-400 mt-0.5" />
            <div className="space-y-1">
              <p className="text-sm font-medium text-foreground">
                Account deleted.
              </p>
              <p className="text-xs text-muted-foreground">
                All your signals, commitments, and predictions have been
                removed. The audit log of this deletion is retained for
                compliance. Log out to return to the login screen.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">Settings</h2>
        <p className="text-sm text-muted-foreground mt-0.5">
          Trust through transparency. See exactly how Maestro is running.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* LLM status */}
        <Card className="border-border/60">
          <CardContent className="pt-6 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                <Brain className="size-3.5" />
                <span>LLM status</span>
              </div>
              {llm && (
                <span
                  className={cn(
                    "inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border",
                    llm.active
                      ? "border-emerald-500/30 bg-emerald-500/[0.08] text-emerald-300"
                      : llm.configured
                        ? "border-amber-500/30 bg-amber-500/[0.08] text-amber-300"
                        : "border-border/60 bg-muted/40 text-muted-foreground",
                  )}
                >
                  <span
                    className={cn(
                      "size-1.5 rounded-full",
                      llm.active
                        ? "bg-emerald-500"
                        : llm.configured
                          ? "bg-amber-500"
                          : "bg-zinc-500",
                    )}
                  />
                  {llm.active ? "active" : llm.configured ? "configured" : "off"}
                </span>
              )}
            </div>
            {loading || !llm ? (
              <SkeletonRow />
            ) : (
              <div className="space-y-2 text-sm">
                <Row label="Provider" value={llm.provider} />
                <Row label="Mode" value={llm.mode} />
                <Row
                  label="Verified"
                  value={llm.verified ? "yes" : "no — probe failed"}
                />
                <Row label="Probe latency" value={`${llm.probe_latency_ms}ms`} />
                {llm.probe_error && (
                  <Row label="Probe error" value={llm.probe_error} mono />
                )}
                {llm.note && (
                  <p className="text-xs text-muted-foreground italic pt-2 border-t border-border/60">
                    {llm.note}
                  </p>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Privacy mode */}
        <Card className="border-border/60">
          <CardContent className="pt-6 space-y-3">
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              <Shield className="size-3.5" />
              <span>Privacy mode</span>
            </div>
            {loading || !privacy ? (
              <SkeletonRow />
            ) : (
              <div className="space-y-2 text-sm">
                <Row
                  label="Mode"
                  value={privacy.mode}
                  highlight={privacy.mode === "local"}
                />
                {privacy.description && (
                  <p className="text-xs text-muted-foreground">{privacy.description}</p>
                )}
                {privacy.egress_paths && privacy.egress_paths.length > 0 && (
                  <div className="pt-2 border-t border-border/60 space-y-1.5">
                    <div className="text-[11px] uppercase tracking-wider text-muted-foreground/70">
                      Egress paths
                    </div>
                    {privacy.egress_paths.map((e, i) => (
                      <div key={i} className="text-xs space-y-0.5">
                        <div className="font-mono text-foreground/90">
                          → {e.destination}
                        </div>
                        <div className="text-muted-foreground pl-3">
                          {e.purpose}
                          {e.data && e.data !== "n/a" && ` · data: ${e.data}`}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Calibration */}
        <Card className="border-border/60">
          <CardContent className="pt-6 space-y-3">
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              <Activity className="size-3.5" />
              <span>Calibration</span>
            </div>
            {loading || !calibration ? (
              <SkeletonRow />
            ) : (
              <div className="space-y-3 text-sm">
                {calibration.brier_score !== null && calibration.brier_score !== undefined ? (
                  <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/[0.05] p-3">
                    <div className="text-[11px] uppercase tracking-wider text-emerald-300/80 mb-1">
                      Brier score
                    </div>
                    <div className="text-2xl font-mono font-semibold text-foreground">
                      {calibration.brier_score.toFixed(4)}
                    </div>
                    <div className="text-xs text-muted-foreground mt-1">
                      lower is better · 0.0 = perfect
                    </div>
                  </div>
                ) : (
                  <div className="rounded-lg border border-border/60 bg-muted/20 p-3">
                    <div className="text-[11px] uppercase tracking-wider text-muted-foreground/70 mb-1">
                      Status
                    </div>
                    <div className="text-sm text-foreground/80">
                      Insufficient calibration history
                    </div>
                    <div className="text-xs text-muted-foreground mt-1">
                      Keep tracking outcomes — Maestro will compute a real Brier
                      score once you have ≥10 resolved predictions.
                    </div>
                  </div>
                )}
                {calibration.counts && (
                  <div className="grid grid-cols-4 gap-2 text-center">
                    <Stat label="Total" value={calibration.counts.total} />
                    <Stat label="Resolved" value={calibration.counts.resolved} />
                    <Stat label="Hits" value={calibration.counts.hits} accent="emerald" />
                    <Stat label="Misses" value={calibration.counts.misses} accent="rose" />
                  </div>
                )}
                {calibration.message && (
                  <p className="text-xs text-muted-foreground italic">
                    {calibration.message}
                  </p>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Data + danger zone */}
        <Card className="border-border/60">
          <CardContent className="pt-6 space-y-3">
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              <Database className="size-3.5" />
              <span>Your data</span>
            </div>
            <p className="text-sm text-muted-foreground">
              Export everything Maestro knows about you, or delete your account
              and all associated data. Audit logs of these actions are retained
              for compliance.
            </p>
            <div className="space-y-2 pt-1">
              <Button
                variant="outline"
                className="w-full justify-start"
                onClick={exportData}
                disabled={exporting}
              >
                {exporting ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Download className="size-4" />
                )}
                Export my data (JSON)
              </Button>

              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button
                    variant="ghost"
                    className="w-full justify-start text-rose-300 hover:text-rose-200 hover:bg-rose-500/10"
                    disabled={deleting}
                  >
                    {deleting ? (
                      <Loader2 className="size-4 animate-spin" />
                    ) : (
                      <Trash2 className="size-4" />
                    )}
                    Delete account
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle className="flex items-center gap-2">
                      <ShieldAlert className="size-5 text-rose-400" />
                      Delete your account?
                    </AlertDialogTitle>
                    <AlertDialogDescription>
                      This permanently deletes all your signals, commitments,
                      predictions, outcomes, and graph data. The audit log of
                      this deletion is retained for compliance. This action
                      cannot be undone.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction
                      onClick={deleteAccount}
                      className="bg-rose-500/80 hover:bg-rose-500 text-white"
                    >
                      Yes, delete everything
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          </CardContent>
        </Card>

        {/* Phase 20: Insights — analytics trends + flywheel summary */}
        <Card className="border-border/60">
          <CardContent className="pt-6 space-y-3">
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              <TrendingUp className="size-3.5" />
              <span>Insights</span>
            </div>
            {flywheelSummary ? (
              <div>
                <p className="text-xs font-semibold text-foreground/80 mb-1">Flywheel</p>
                <p className="text-sm text-muted-foreground">{flywheelSummary}</p>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                No data yet — sync connectors to start the flywheel.
              </p>
            )}
            {analyticsReport && (
              <div className="pt-3 border-t border-border/40 space-y-2">
                <p className="text-xs font-semibold text-foreground/80">90-Day Trends</p>
                {analyticsReport.trends && analyticsReport.trends.length > 0 ? (
                  analyticsReport.trends.slice(0, 4).map((trend: any, i: number) => (
                    <div key={i} className="flex items-center justify-between">
                      <span className="text-xs text-muted-foreground capitalize">
                        {trend.name?.replace(/_/g, " ")}
                      </span>
                      <span
                        className={cn(
                          "text-xs font-semibold",
                          trend.direction === "improving" ? "text-emerald-500"
                            : trend.direction === "declining" ? "text-red-500"
                            : "text-muted-foreground"
                        )}
                      >
                        {trend.direction === "improving" ? "↑" : trend.direction === "declining" ? "↓" : "→"}{" "}
                        {Math.abs(trend.change_percentage || 0).toFixed(0)}%
                      </span>
                    </div>
                  ))
                ) : (
                  <p className="text-xs text-muted-foreground">
                    Commitment kept rate: {((analyticsReport.commitment_kept_rate || 0) * 100).toFixed(0)}%
                  </p>
                )}
                {analyticsReport.meeting_grade_average > 0 && (
                  <p className="text-xs text-muted-foreground">
                    Meeting grade avg: {analyticsReport.meeting_grade_average.toFixed(1)}/100
                  </p>
                )}
                {analyticsReport.patterns_detected > 0 && (
                  <p className="text-xs text-muted-foreground">
                    Patterns: {analyticsReport.patterns_detected} · Laws validated: {analyticsReport.laws_validated}
                  </p>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Connectors — connect/disconnect/sync (merged from old Connectors tab) */}
      <Connectors />

      {/* Per-connector consent (Task 59-7) */}
      <Card className="border-border/60">
        <CardContent className="pt-6 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              <Shield className="size-3.5" />
              <span>Per-connector consent</span>
            </div>
            <span className="text-[11px] text-muted-foreground/70">
              Granular data-access toggles per connector
            </span>
          </div>
          {loading || !consent || !consentDefaults ? (
            <SkeletonRow />
          ) : (
            <div className="space-y-3">
              <p className="text-xs text-muted-foreground">
                Toggle what each connector is allowed to do. Read access is on
                by default; write actions (drafts, posts, sends) are off by
                default and must be explicitly enabled.
              </p>
              {Object.entries(consentDefaults).map(([provider, scopes]) => (
                <div key={provider} className="rounded-lg border border-border/60 bg-muted/20 p-3">
                  <div className="text-sm font-medium capitalize mb-2">{provider}</div>
                  <div className="flex flex-wrap gap-3">
                    {Object.entries(scopes).map(([scope, defaultEnabled]) => {
                      const current = consent[provider]?.[scope] ?? defaultEnabled;
                      return (
                        <button
                          key={scope}
                          type="button"
                          onClick={async () => {
                            const next = !current;
                            // Optimistic update
                            setConsent((prev) => ({
                              ...prev,
                              [provider]: { ...prev?.[provider], [scope]: next },
                            }));
                            await maestroApi.setConsentSetting(provider, scope, next);
                          }}
                          className={cn(
                            "inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-md border transition-colors",
                            current
                              ? "border-emerald-500/30 bg-emerald-500/[0.08] text-emerald-300"
                              : "border-border/60 bg-muted/40 text-muted-foreground",
                          )}
                        >
                          {current ? (
                            <ToggleRight className="size-3.5" />
                          ) : (
                            <ToggleLeft className="size-3.5" />
                          )}
                          {scope.replace(/_/g, " ")}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Audit log */}
      <Card className="border-border/60">
        <CardContent className="pt-6 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              <Activity className="size-3.5" />
              <span>Audit log</span>
            </div>
            <span className="text-[11px] text-muted-foreground/70">
              {loading ? "loading…" : `${audit?.events?.length ?? 0} recent event${(audit?.events?.length ?? 0) === 1 ? "" : "s"}`}
            </span>
          </div>
          {loading || !audit ? (
            <SkeletonRow />
          ) : (
            <div className="rounded-lg border border-border/60 overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead className="w-[180px]">Timestamp</TableHead>
                    <TableHead className="w-[100px]">Action</TableHead>
                    <TableHead>Endpoint</TableHead>
                    {audit.events.some((e) => e.signal_id) && (
                      <TableHead className="w-[160px]">Signal</TableHead>
                    )}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {audit.events.map((e, i) => (
                    <TableRow key={i}>
                      <TableCell className="font-mono text-xs text-muted-foreground">
                        {formatTimestamp(e.timestamp)}
                      </TableCell>
                      <TableCell>
                        <span
                          className={cn(
                            "text-xs px-2 py-0.5 rounded-full border",
                            e.action === "read"
                              ? "border-border/60 bg-muted/40 text-muted-foreground"
                              : e.action === "write"
                                ? "border-emerald-500/30 bg-emerald-500/[0.08] text-emerald-300"
                                : e.action === "delete"
                                  ? "border-rose-500/30 bg-rose-500/[0.08] text-rose-300"
                                  : e.action === "correct"
                                    ? "border-amber-500/30 bg-amber-500/[0.08] text-amber-300"
                                    : "border-border/60 bg-muted/40 text-muted-foreground",
                          )}
                        >
                          {e.action}
                        </span>
                      </TableCell>
                      <TableCell className="font-mono text-xs text-foreground/80">
                        {e.endpoint}
                      </TableCell>
                      {audit.events.some((x) => x.signal_id) && (
                        <TableCell className="font-mono text-xs text-muted-foreground">
                          {e.signal_id || "—"}
                        </TableCell>
                      )}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Row({
  label,
  value,
  mono,
  highlight,
}: {
  label: string;
  value: string;
  mono?: boolean;
  highlight?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-muted-foreground text-xs uppercase tracking-wider">
        {label}
      </span>
      <span
        className={cn(
          "text-foreground/90 text-right text-sm",
          mono && "font-mono text-xs",
          highlight && "text-emerald-300",
        )}
      >
        {value}
      </span>
    </div>
  );
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent?: "emerald" | "rose";
}) {
  return (
    <div className="rounded-md border border-border/60 bg-muted/20 p-2">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground/70">
        {label}
      </div>
      <div
        className={cn(
          "text-lg font-mono font-semibold",
          accent === "emerald" && "text-emerald-400",
          accent === "rose" && "text-rose-400",
          !accent && "text-foreground",
        )}
      >
        {value}
      </div>
    </div>
  );
}

function SkeletonRow() {
  return (
    <div className="space-y-2">
      <div className="h-3 w-1/2 bg-muted/60 rounded animate-pulse" />
      <div className="h-3 w-2/3 bg-muted/40 rounded animate-pulse" />
      <div className="h-3 w-1/3 bg-muted/40 rounded animate-pulse" />
    </div>
  );
}

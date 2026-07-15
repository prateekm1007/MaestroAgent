"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CheckCircle2,
  Loader2,
  Plus,
  Search,
  XCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Card,
  CardContent,
} from "@/components/ui/card";
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
import { cn } from "@/lib/utils";
import {
  formatRelative,
  formatTimestamp,
  type Signal,
  maestroApi,
} from "@/lib/maestro-api";

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

const PAGE_SIZE = 50;

export function Signals() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");
  const [page, setPage] = useState(0);
  const [busyId, setBusyId] = useState<string | null>(null);

  // Add-signal form state
  const [entity, setEntity] = useState("");
  const [text, setText] = useState("");
  const [signalType, setSignalType] = useState<string>("reported_statement");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let alive = true;
    void (async () => {
      setLoading(true);
      const { data } = await maestroApi.getSignals();
      if (!alive) return;
      setSignals(data);
      setLoading(false);
    })();
    return () => {
      alive = false;
    };
  }, []);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return signals;
    return signals.filter(
      (s) =>
        s.entity.toLowerCase().includes(q) ||
        s.text.toLowerCase().includes(q) ||
        s.signal_type.toLowerCase().includes(q),
    );
  }, [signals, filter]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages - 1);
  const pageItems = filtered.slice(safePage * PAGE_SIZE, (safePage + 1) * PAGE_SIZE);

  async function submitNew(e: React.FormEvent) {
    e.preventDefault();
    if (!entity.trim() || !text.trim()) return;
    setSubmitting(true);
    const { data } = await maestroApi.createSignal(
      entity.trim(),
      text.trim(),
      signalType,
    );
    setSignals((prev) => [data, ...prev]);
    setEntity("");
    setText("");
    setSignalType("reported_statement");
    setSubmitting(false);
  }

  async function correct(signal_id: string, action: "dismiss" | "complete" | "cancel") {
    setBusyId(signal_id);
    await maestroApi.correctSignal(signal_id, action);
    // Remove from list (the API hides corrected signals on next fetch, but locally we hide too)
    setSignals((prev) => prev.filter((s) => s.signal_id !== signal_id));
    setBusyId(null);
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">Signals</h2>
        <p className="text-sm text-muted-foreground mt-0.5">
          Raw observations Maestro reasons over. Add anything you observed.
        </p>
      </div>

      {/* Add-signal form */}
      <Card className="border-border/60">
        <CardContent className="pt-6">
          <form onSubmit={submitNew} className="space-y-3">
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              <Plus className="size-3.5" />
              <span>Add a signal</span>
            </div>
            <div className="grid gap-3 md:grid-cols-[200px_1fr_220px_auto]">
              <Input
                placeholder="Entity (e.g. Maria Garcia)"
                value={entity}
                onChange={(e) => setEntity(e.target.value)}
                className="bg-input/40 border-border/60"
              />
              <Input
                placeholder="What you observed or were told"
                value={text}
                onChange={(e) => setText(e.target.value)}
                className="bg-input/40 border-border/60"
              />
              <Select value={signalType} onValueChange={setSignalType}>
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
              <Button type="submit" disabled={submitting || !entity.trim() || !text.trim()}>
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
                onChange={(e) => {
                  setFilter(e.target.value);
                  setPage(0);
                }}
                placeholder="Filter signals…"
                className="pl-9 h-8 text-sm bg-input/40 border-border/60"
              />
            </div>
          </div>

          {loading ? (
            <div className="py-12 flex items-center justify-center">
              <Loader2 className="size-5 text-muted-foreground animate-spin" />
            </div>
          ) : pageItems.length === 0 ? (
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
                  {pageItems.map((s) => (
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
                            onClick={() => correct(s.signal_id, "complete")}
                            title="Mark complete"
                          >
                            <CheckCircle2 className="size-3.5" />
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground"
                            disabled={busyId === s.signal_id}
                            onClick={() => correct(s.signal_id, "dismiss")}
                            title="Dismiss"
                          >
                            Dismiss
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            className="h-7 px-2 text-xs text-rose-300 hover:text-rose-200"
                            disabled={busyId === s.signal_id}
                            onClick={() => correct(s.signal_id, "cancel")}
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
          {filtered.length > PAGE_SIZE && (
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>
                Showing {safePage * PAGE_SIZE + 1}–{Math.min(filtered.length, (safePage + 1) * PAGE_SIZE)} of {filtered.length}
              </span>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 text-xs"
                  disabled={safePage === 0}
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                >
                  Prev
                </Button>
                <span className="px-2 py-1.5">
                  {safePage + 1} / {totalPages}
                </span>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 text-xs"
                  disabled={safePage >= totalPages - 1}
                  onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
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

"use client";

import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Brain,
  Clock,
  HelpCircle,
  History,
  Loader2,
  Quote,
  Search,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import {
  confidenceColor,
  confidenceTier,
  confidenceTextColor,
  formatRelative,
  formatTimestamp,
  type AskResponse,
  maestroApi,
} from "@/lib/maestro-api";

const SUGGESTED_QUERIES = [
  "What did I promise Maria?",
  "When is the design review with Alex?",
  "What did Sam commit to?",
  "What's at risk this week?",
];

export function Ask({
  initialQuery,
  onConsumed,
}: {
  initialQuery?: string;
  onConsumed: () => void;
}) {
  const [query, setQuery] = useState(initialQuery ?? "");
  const [busy, setBusy] = useState(false);
  const [response, setResponse] = useState<AskResponse | null>(null);
  const [history, setHistory] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  // Hydrate history from localStorage (last 10)
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem("maestro.ask.history");
      if (raw) setHistory(JSON.parse(raw));
    } catch {
      /* ignore */
    }
  }, []);

  // If parent passes an initial query (from Dashboard Quick Ask), fire it.
  useEffect(() => {
    if (initialQuery) {
      setQuery(initialQuery);
      void runAsk(initialQuery);
      onConsumed();
    }
  }, [initialQuery]);

  async function runAsk(q: string) {
    if (!q.trim()) return;
    setBusy(true);
    setResponse(null);
    const { data } = await maestroApi.ask(q.trim());
    setResponse(data);
    setBusy(false);
    // Update history
    setHistory((prev) => {
      const next = [q.trim(), ...prev.filter((x) => x !== q.trim())].slice(0, 10);
      try {
        window.localStorage.setItem("maestro.ask.history", JSON.stringify(next));
      } catch {
        /* ignore */
      }
      return next;
    });
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    void runAsk(query);
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-xl font-semibold tracking-tight">Ask Maestro</h2>
        <p className="text-sm text-muted-foreground mt-0.5">
          Ask anything. Every answer shows where it came from.
        </p>
      </div>

      {/* Search bar — the primary interaction */}
      <Card className="border-border/60 surface-elevated">
        <CardContent className="pt-6">
          <form onSubmit={submit} className="flex flex-col sm:flex-row gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
              <Input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="“What did I promise Maria?”"
                className="pl-9 h-12 text-base bg-input/40 border-border/60"
                disabled={busy}
              />
            </div>
            <Button type="submit" size="lg" className="h-12 px-6" disabled={busy || !query.trim()}>
              {busy ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
              {busy ? "Thinking…" : "Ask"}
            </Button>
          </form>

          {/* Suggested queries */}
          {!response && !busy && (
            <div className="mt-4 flex flex-wrap gap-2">
              {SUGGESTED_QUERIES.map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => {
                    setQuery(q);
                    void runAsk(q);
                  }}
                  className="text-xs px-3 py-1.5 rounded-full border border-border/60 bg-muted/30 hover:bg-muted/60 transition-colors text-muted-foreground hover:text-foreground"
                >
                  {q}
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-[1fr_280px]">
        {/* Answer column */}
        <div className="space-y-4">
          {busy && <AnswerSkeleton />}

          {!busy && response && <AnswerCard response={response} />}

          {!busy && !response && (
            <Card className="border-border/60 border-dashed">
              <CardContent className="pt-6 pb-8 flex flex-col items-center justify-center text-center gap-3">
                <div className="size-12 rounded-full bg-muted/40 flex items-center justify-center">
                  <Search className="size-5 text-muted-foreground" />
                </div>
                <div>
                  <p className="text-sm font-medium">Ask a question to begin.</p>
                  <p className="text-xs text-muted-foreground mt-1 max-w-sm">
                    Maestro will search every signal you&apos;ve stored, find the
                    source sentence, and answer with calibrated confidence.
                  </p>
                </div>
              </CardContent>
            </Card>
          )}
        </div>

        {/* History sidebar */}
        <div>
          <Card className="border-border/60">
            <CardContent className="pt-6">
              <div className="flex items-center gap-2 mb-3">
                <History className="size-4 text-muted-foreground" />
                <h3 className="text-sm font-semibold">History</h3>
              </div>
              {history.length === 0 ? (
                <p className="text-xs text-muted-foreground py-2">
                  No questions yet. Your last 10 will appear here.
                </p>
              ) : (
                <ul className="space-y-1 max-h-[60vh] overflow-y-auto pr-1">
                  {history.map((q, i) => (
                    <li key={i}>
                      <button
                        type="button"
                        onClick={() => {
                          setQuery(q);
                          void runAsk(q);
                        }}
                        className="w-full text-left text-sm px-2.5 py-2 rounded-md hover:bg-muted/40 transition-colors text-foreground/80 truncate"
                        title={q}
                      >
                        {q}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

/* ---------------- Answer card ---------------- */

function AnswerCard({ response }: { response: AskResponse }) {
  const tier = confidenceTier(response.confidence);
  const tierLabel = tier === "high" ? "High" : tier === "medium" ? "Medium" : "Low";
  const source = response.intelligence_source || (response.llm_active ? "llm" : "rules");

  return (
    <div className="space-y-4">
      {/* Main answer */}
      <Card className="border-border/60 surface-elevated">
        <CardContent className="pt-6 space-y-4">
          <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
            <Sparkles className="size-3.5" />
            <span>Answer</span>
          </div>
          <p className="text-lg sm:text-xl font-medium leading-snug text-balance text-pretty">
            {response.answer}
          </p>

          {/* Confidence meter */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground">Confidence</span>
                <span className={cn("font-mono font-medium", confidenceTextColor(response.confidence))}>
                  {(response.confidence * 100).toFixed(0)}% · {tierLabel}
                </span>
              </div>
              <span className="inline-flex items-center gap-1.5 text-muted-foreground">
                {source === "llm" ? (
                  <>
                    <Brain className="size-3.5" />
                    llm
                  </>
                ) : source === "rules" ? (
                  <>
                    <Brain className="size-3.5 opacity-50" />
                    rules
                  </>
                ) : (
                  <>
                    <Brain className="size-3.5 opacity-30" />
                    ranker
                  </>
                )}
              </span>
            </div>
            <div className="h-1.5 w-full rounded-full bg-muted/60 overflow-hidden">
              <div
                className={cn("h-full rounded-full transition-all", confidenceColor(response.confidence))}
                style={{ width: `${Math.max(2, Math.min(100, response.confidence * 100))}%` }}
              />
            </div>
          </div>

          {response.decision_boundary && (
            <div className="text-sm">
              <span className="text-muted-foreground">Decision: </span>
              <span className="text-foreground/90">{response.decision_boundary}</span>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Provenance panel */}
      {response.source_sentence && (
        <Card className="border-border/60">
          <CardContent className="pt-6 space-y-3">
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              <Quote className="size-3.5" />
              <span>Provenance</span>
            </div>
            <blockquote className="border-l-2 border-border pl-4 italic text-foreground/90">
              &ldquo;{response.source_sentence}&rdquo;
            </blockquote>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
              {response.source_entity && (
                <span>
                  <span className="text-muted-foreground/70">entity:</span>{" "}
                  <span className="text-foreground/80">{response.source_entity}</span>
                </span>
              )}
              {response.source_timestamp && (
                <span className="inline-flex items-center gap-1">
                  <Clock className="size-3" />
                  {formatTimestamp(response.source_timestamp)}
                </span>
              )}
              {response.as_of && (
                <span>
                  <span className="text-muted-foreground/70">as of:</span>{" "}
                  {formatTimestamp(response.as_of)}
                </span>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Counterevidence */}
      {response.counterevidence.length > 0 && (
        <Card className="border-rose-500/30 bg-rose-500/[0.04]">
          <CardContent className="pt-6 space-y-3">
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-rose-400/90">
              <AlertTriangle className="size-3.5" />
              <span>Counterevidence</span>
              <span className="text-muted-foreground/70 normal-case tracking-normal">
                · {response.counterevidence.length}
              </span>
            </div>
            <ul className="space-y-2">
              {response.counterevidence.map((c, i) => (
                <li key={i} className="rounded-lg border border-rose-500/20 bg-rose-500/[0.04] p-3">
                  <p className="text-sm text-foreground/90">
                    {c.text || (typeof c === "string" ? c : JSON.stringify(c))}
                  </p>
                  {(c as any).entity && (
                    <p className="text-xs text-muted-foreground mt-1">
                      {(c as any).entity}
                      {(c as any).timestamp && ` · ${formatRelative((c as any).timestamp)}`}
                    </p>
                  )}
                  {(c as any).why_it_matters && (
                    <p className="text-xs text-rose-300/80 mt-1.5 italic">
                      why it matters: {(c as any).why_it_matters}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* Unknowns */}
      {response.unknowns.length > 0 && (
        <Card className="border-border/60">
          <CardContent className="pt-6 space-y-3">
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              <HelpCircle className="size-3.5" />
              <span>Unknowns</span>
              <span className="text-muted-foreground/70 normal-case tracking-normal">
                · what Maestro can&apos;t verify
              </span>
            </div>
            <ul className="space-y-2">
              {response.unknowns.map((u, i) => (
                <li
                  key={i}
                  className="rounded-lg border border-border/60 bg-muted/20 p-3 text-sm text-muted-foreground"
                >
                  {u}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* Reasoning chain — collapsible-ish, but kept simple */}
      {response.reasoning_chain.length > 0 && (
        <Card className="border-border/60">
          <CardContent className="pt-6 space-y-3">
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              <Brain className="size-3.5" />
              <span>How Maestro arrived at this</span>
            </div>
            <ol className="space-y-1.5 text-sm">
              {response.reasoning_chain.map((r, i) => (
                <li key={i} className="flex gap-2 text-foreground/80">
                  <span className="text-muted-foreground/60 font-mono text-xs mt-0.5">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <span>{r}</span>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
      )}

      {/* Perspectives */}
      {response.perspectives.length > 0 && (
        <Card className="border-border/60">
          <CardContent className="pt-6 space-y-3">
            <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              Perspectives
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              {response.perspectives.map((p, i) => (
                <div
                  key={i}
                  className="rounded-lg border border-border/60 bg-muted/20 p-3"
                >
                  <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1">
                    {(p as any).lens || "view"}
                  </div>
                  <p className="text-sm text-foreground/90">
                    {(p as any).view || JSON.stringify(p)}
                  </p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Consequence paths */}
      {response.consequence_paths.length > 0 && (
        <Card className="border-border/60">
          <CardContent className="pt-6 space-y-3">
            <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              If you…
            </div>
            <ul className="space-y-2 text-sm">
              {response.consequence_paths.map((c, i) => (
                <li key={i} className="flex gap-2 text-foreground/80">
                  <ArrowRight className="size-3.5 shrink-0 text-muted-foreground mt-1" />
                  <span>{c}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function AnswerSkeleton() {
  return (
    <Card className="border-border/60">
      <CardContent className="pt-6 space-y-3">
        <div className="h-3 w-24 bg-muted/60 rounded animate-pulse" />
        <div className="h-5 w-3/4 bg-muted/40 rounded animate-pulse" />
        <div className="h-5 w-2/3 bg-muted/40 rounded animate-pulse" />
        <div className="h-1.5 w-full bg-muted/60 rounded-full animate-pulse mt-4" />
      </CardContent>
    </Card>
  );
}

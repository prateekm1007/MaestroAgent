"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Brain,
  Clock,
  HelpCircle,
  History,
  Loader2,
  Mic,
  MicOff,
  Quote,
  Search,
  Sparkles,
  Square,
  Volume2,
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
  getToken,
  type AskResponse,
  type Commitment,
  maestroApi,
} from "@/lib/maestro-api";

const SUGGESTED_QUERIES = [
  "What did I promise Maria?",
  "When is the design review with Alex?",
  "What did Sam commit to?",
  "What's at risk this week?",
];

const QA_HISTORY_KEY = "maestro.ask.qa_history";
const MAX_QA_PAIRS = 3;
const MAX_ANSWER_CHARS_IN_CONTEXT = 200;

// ── Autocomplete UX constants (ported from static/js/ask.js — Enterprise pattern) ──
// The Enterprise version calls GET /api/oem/autocomplete (forbidden — single-user
// Personal API has no such endpoint). We port the PATTERN only: debounce + dropdown
// + keyboard nav. Suggestions come from existing Personal data sources (history +
// entity names from /api/commitments), NOT a per-keystroke backend call.
const ASK_DEBOUNCE_MS = 150;
const MAX_SUGGESTIONS = 8;

type QaPair = { query: string; answer: string; timestamp: string };

type Suggestion = {
  text: string;
  source: "history" | "entity" | "suggested";
  label: string;
};

export function Ask({
  initialQuery,
  onConsumed,
  onViewCommitmentsForEntity,
}: {
  initialQuery?: string;
  onConsumed: () => void;
  onViewCommitmentsForEntity?: (entity: string) => void;
}) {
  // P1-3: stable session_id per Ask-tab visit (multi-turn LLM context)
  const [sessionId] = useState(() => crypto.randomUUID());
  const [query, setQuery] = useState(initialQuery ?? "");
  const [busy, setBusy] = useState(false);
  const [response, setResponse] = useState<AskResponse | null>(null);
  const [history, setHistory] = useState<string[]>([]);
  const [qaHistory, setQaHistory] = useState<QaPair[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  // P1-6: TTS state (window.speechSynthesis — no deps needed)
  const [speaking, setSpeaking] = useState(false);
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);

  // P1-7: Voice input state
  const [recording, setRecording] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  // ── Autocomplete state (ported from static/js/ask.js — Enterprise pattern) ──
  // The Enterprise version calls /api/oem/autocomplete per keystroke (forbidden here).
  // We port the PATTERN: 150ms debounce + dropdown + keyboard nav + ESC-to-close.
  // Suggestions come from: (1) localStorage maestro.ask.history (no request), and
  // (2) entity names from a ONE-TIME fetch of /api/commitments on mount (existing
  // Personal endpoint, not per-keystroke). No AbortController needed because we're
  // filtering cached arrays, not making per-keystroke network calls.
  const [autocompleteOpen, setAutocompleteOpen] = useState(false);
  const [selectedIdx, setSelectedIdx] = useState(-1);
  const [entityNames, setEntityNames] = useState<string[]>([]);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [debouncedQuery, setDebouncedQuery] = useState("");

  // One-time fetch of /api/commitments on mount — extracts unique entity names
  // for autocomplete suggestions. This is an existing Personal endpoint (also
  // fetched by Commitments.tsx), not a new request per keystroke.
  useEffect(() => {
    let alive = true;
    void (async () => {
      const { data } = await maestroApi.getCommitments();
      if (!alive) return;
      const names = Array.from(
        new Set((data as Commitment[]).map((c) => c.entity).filter(Boolean)),
      ) as string[];
      setEntityNames(names);
    })();
    return () => {
      alive = false;
    };
  }, []);

  // Debounce the query by 150ms before computing suggestions.
  // Ported from static/js/ask.js: clearTimeout + setTimeout pattern.
  useEffect(() => {
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    debounceTimerRef.current = setTimeout(() => {
      setDebouncedQuery(query);
    }, ASK_DEBOUNCE_MS);
    return () => {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    };
  }, [query]);

  // Compute suggestions from cached data (no per-keystroke network call).
  // Sources: localStorage history + entity names from /api/commitments + the
  // hardcoded SUGGESTED_QUERIES as a fallback when nothing else matches.
  const suggestions = useMemo<Suggestion[]>(() => {
    const q = debouncedQuery.trim().toLowerCase();
    if (!q) return [];
    const matches: Suggestion[] = [];
    const seen = new Set<string>();

    // 1. History matches (highest priority — user has typed this before)
    for (const h of history) {
      if (matches.length >= MAX_SUGGESTIONS) break;
      if (h.toLowerCase().includes(q) && !seen.has(h)) {
        matches.push({ text: h, source: "history", label: "recent" });
        seen.add(h);
      }
    }

    // 2. Entity-name matches → build a natural-language query template
    for (const entity of entityNames) {
      if (matches.length >= MAX_SUGGESTIONS) break;
      const eLower = entity.toLowerCase();
      if (eLower.includes(q)) {
        const template = `What did I promise ${entity}?`;
        if (!seen.has(template)) {
          matches.push({ text: template, source: "entity", label: `entity: ${entity}` });
          seen.add(template);
        }
      }
    }

    // 3. Suggested queries (fallback — only if user input matches a suggested query)
    for (const s of SUGGESTED_QUERIES) {
      if (matches.length >= MAX_SUGGESTIONS) break;
      if (s.toLowerCase().includes(q) && !seen.has(s)) {
        matches.push({ text: s, source: "suggested", label: "suggested" });
        seen.add(s);
      }
    }

    return matches;
  }, [debouncedQuery, history, entityNames]);

  // Open/close dropdown based on whether there are suggestions
  useEffect(() => {
    if (suggestions.length > 0 && debouncedQuery.trim() && !busy) {
      setAutocompleteOpen(true);
      setSelectedIdx(-1);
    } else {
      setAutocompleteOpen(false);
      setSelectedIdx(-1);
    }
  }, [suggestions, debouncedQuery, busy]);

  // Keyboard navigation — ported from static/js/ask.js:
  // ArrowDown/ArrowUp cycle through suggestions, Enter selects, Escape closes.
  function handleInputKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!autocompleteOpen) {
      // Pass through to the form's submit handler when no dropdown is open
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIdx((i) => (i + 1) % suggestions.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIdx((i) => (i - 1 + suggestions.length) % suggestions.length);
    } else if (e.key === "Enter" && selectedIdx >= 0) {
      e.preventDefault();
      const selected = suggestions[selectedIdx];
      if (selected) {
        setQuery(selected.text);
        setAutocompleteOpen(false);
        setSelectedIdx(-1);
        void runAsk(selected.text);
      }
    } else if (e.key === "Escape") {
      e.preventDefault();
      setAutocompleteOpen(false);
      setSelectedIdx(-1);
      inputRef.current?.focus();
    }
  }

  function selectSuggestion(s: Suggestion) {
    setQuery(s.text);
    setAutocompleteOpen(false);
    setSelectedIdx(-1);
    inputRef.current?.focus();
    void runAsk(s.text);
  }

  // Hydrate plain-string history (last 10) + Q&A pair history (last 3) from localStorage
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem("maestro.ask.history");
      if (raw) setHistory(JSON.parse(raw));
    } catch {
      /* ignore */
    }
    try {
      const raw = window.localStorage.getItem(QA_HISTORY_KEY);
      if (raw) setQaHistory(JSON.parse(raw));
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

  // Cleanup TTS on unmount
  useEffect(() => {
    return () => {
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  async function runAsk(q: string) {
    if (!q.trim()) return;
    setBusy(true);
    setResponse(null);
    // Stop any in-progress TTS when a new question starts
    stopSpeaking();

    // P1-4: Build context from last 3 Q&A pairs (mobile pattern)
    let contextualQuery = q.trim();
    if (qaHistory.length > 0) {
      const context = qaHistory
        .slice(0, MAX_QA_PAIRS)
        .map((p, i) => `Q${i + 1}: ${p.query}\nA${i + 1}: ${(p.answer || "").slice(0, MAX_ANSWER_CHARS_IN_CONTEXT)}`)
        .join("\n\n");
      contextualQuery = `Previous conversation:\n${context}\n\nCurrent question: ${q.trim()}`;
    }

    // P1-3: Pass stable session_id so backend maintains multi-turn context
    const { data } = await maestroApi.ask(contextualQuery, sessionId);
    setResponse(data);
    setBusy(false);

    // Update plain-string history (UI)
    setHistory((prev) => {
      const next = [q.trim(), ...prev.filter((x) => x !== q.trim())].slice(0, 10);
      try {
        window.localStorage.setItem("maestro.ask.history", JSON.stringify(next));
      } catch {
        /* ignore */
      }
      return next;
    });

    // P1-4: Update Q&A pair history (context for next question)
    if (data?.answer) {
      setQaHistory((prev) => {
        const pair: QaPair = {
          query: q.trim(),
          answer: data.answer,
          timestamp: new Date().toISOString(),
        };
        const next = [pair, ...prev].slice(0, MAX_QA_PAIRS);
        try {
          window.localStorage.setItem(QA_HISTORY_KEY, JSON.stringify(next));
        } catch {
          /* ignore */
        }
        return next;
      });
    }
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    void runAsk(query);
  }

  // P1-6: Read answer aloud
  function startSpeaking() {
    if (!response?.answer) return;
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(response.answer);
    u.onend = () => setSpeaking(false);
    u.onerror = () => setSpeaking(false);
    utteranceRef.current = u;
    window.speechSynthesis.speak(u);
    setSpeaking(true);
  }

  function stopSpeaking() {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    setSpeaking(false);
    utteranceRef.current = null;
  }

  // P1-7: Voice input via MediaRecorder → POST /api/copilot/transcribe
  async function startRecording() {
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      chunksRef.current = [];
      mr.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      mr.onstop = async () => {
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        stream.getTracks().forEach((t) => t.stop());
        await transcribeAndAsk(blob);
      };
      mr.start();
      mediaRecorderRef.current = mr;
      setRecording(true);
    } catch (e: any) {
      // Permission denied or no mic — show clear error, don't crash
      console.error("Mic access failed:", e);
      alert(`Could not access microphone: ${e?.message || e}`);
    }
  }

  function stopRecording() {
    if (mediaRecorderRef.current && recording) {
      mediaRecorderRef.current.stop();
      setRecording(false);
    }
  }

  async function transcribeAndAsk(blob: Blob) {
    try {
      const formData = new FormData();
      formData.append("audio", blob, "recording.webm");
      const token = getToken();
      const res = await fetch("/api/copilot/transcribe", {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
      });
      if (!res.ok) {
        alert(`Transcription failed: HTTP ${res.status}`);
        return;
      }
      const data = await res.json();
      const text: string = data.text || data.transcript || "";
      if (text.trim()) {
        setQuery(text);
        void runAsk(text);
      } else {
        alert("No speech detected in recording.");
      }
    } catch (e: any) {
      alert(`Transcription error: ${e?.message || e}`);
    }
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
                onKeyDown={handleInputKeyDown}
                placeholder="“What did I promise Maria?”"
                className="pl-9 h-12 text-base bg-input/40 border-border/60"
                disabled={busy}
                autoComplete="off"
                aria-autocomplete="list"
                aria-expanded={autocompleteOpen}
                aria-controls="ask-autocomplete-listbox"
                role="combobox"
              />
              {/* Autocomplete dropdown — ported from static/js/ask.js (Enterprise pattern).
                  Sources: localStorage history + entity names from /api/commitments.
                  NO /api/oem/autocomplete call (Enterprise-only, forbidden). */}
              {autocompleteOpen && suggestions.length > 0 && (
                <div
                  id="ask-autocomplete-listbox"
                  role="listbox"
                  aria-label="Ask suggestions"
                  className="absolute z-50 left-0 right-0 mt-1 rounded-md border border-border/60 bg-popover shadow-md overflow-hidden max-h-80 overflow-y-auto"
                >
                  <div className="px-3 py-1.5 text-[10px] uppercase tracking-wider text-muted-foreground/70 border-b border-border/40 bg-muted/20">
                    Suggestions · from your history + commitments
                  </div>
                  {suggestions.map((s, i) => (
                    <button
                      key={`${s.source}-${i}`}
                      type="button"
                      role="option"
                      aria-selected={i === selectedIdx}
                      onMouseEnter={() => setSelectedIdx(i)}
                      onClick={() => selectSuggestion(s)}
                      className={cn(
                        "w-full text-left px-3 py-2 text-sm flex items-center justify-between gap-2 transition-colors",
                        i === selectedIdx
                          ? "bg-accent text-accent-foreground"
                          : "hover:bg-muted/40",
                      )}
                    >
                      <span className="truncate">{s.text}</span>
                      <span className="text-[10px] uppercase tracking-wider text-muted-foreground/70 shrink-0">
                        {s.label}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            {/* P1-7: Voice input button */}
            <Button
              type="button"
              size="lg"
              variant="outline"
              className="h-12 px-4"
              onClick={recording ? stopRecording : startRecording}
              disabled={busy}
              title={recording ? "Stop recording" : "Speak your question"}
              aria-pressed={recording}
            >
              {recording ? <MicOff className="size-4 text-rose-500" /> : <Mic className="size-4" />}
            </Button>
            <Button type="submit" size="lg" className="h-12 px-6" disabled={busy || !query.trim()}>
              {busy ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
              {busy ? "Thinking…" : "Ask"}
            </Button>
          </form>

          {/* Recording indicator */}
          {recording && (
            <div className="mt-3 flex items-center gap-2 text-xs text-rose-500 font-medium animate-pulse">
              <span className="size-2 rounded-full bg-rose-500" />
              Recording… click stop when done.
            </div>
          )}

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

          {!busy && response && (
            <AnswerCard
              response={response}
              speaking={speaking}
              onSpeak={startSpeaking}
              onStopSpeak={stopSpeaking}
              onViewCommitmentsForEntity={onViewCommitmentsForEntity}
              onReAsk={(q) => {
                setQuery(q);
                void runAsk(q);
              }}
            />
          )}

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

function AnswerCard({
  response,
  speaking,
  onSpeak,
  onStopSpeak,
  onViewCommitmentsForEntity,
  onReAsk,
}: {
  response: AskResponse;
  speaking: boolean;
  onSpeak: () => void;
  onStopSpeak: () => void;
  onViewCommitmentsForEntity?: (entity: string) => void;
  onReAsk: (query: string) => void;
}) {
  const tier = confidenceTier(response.confidence);
  const tierLabel = tier === "high" ? "High" : tier === "medium" ? "Medium" : "Low";
  const source = response.intelligence_source || (response.llm_active ? "llm" : "rules");
  // P0 hydration fix: use state + useEffect for TTS support check (was: direct
  // typeof window check during render, which returns false on server, true on
  // client → hydration mismatch).
  const [ttsSupported, setTtsSupported] = useState(false);
  useEffect(() => {
    setTtsSupported(typeof window !== "undefined" && "speechSynthesis" in window);
  }, []);

  return (
    <div className="space-y-4">
      {/* Main answer */}
      <Card className="border-border/60 surface-elevated">
        <CardContent className="pt-6 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              <Sparkles className="size-3.5" />
              <span>Answer</span>
            </div>
            {/* P1-6: TTS toggle */}
            {ttsSupported && response.answer && (
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="h-7 text-xs"
                onClick={speaking ? onStopSpeak : onSpeak}
                title={speaking ? "Stop reading" : "Read answer aloud"}
              >
                {speaking ? <Square className="size-3.5" /> : <Volume2 className="size-3.5" />}
                {speaking ? "Stop" : "Speak"}
              </Button>
            )}
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
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                <Quote className="size-3.5" />
                <span>Provenance</span>
              </div>
              {/* P1-8: Deep-link to commitments filtered by this entity */}
              {response.source_entity && onViewCommitmentsForEntity && (
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  className="h-7 text-xs"
                  onClick={() => onViewCommitmentsForEntity(response.source_entity)}
                  title={`View commitments for ${response.source_entity}`}
                >
                  View commitments for {response.source_entity}
                  <ArrowRight className="size-3" />
                </Button>
              )}
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

      {/* Unknowns — P1-5: tappable chips that re-ask the question */}
      {response.unknowns.length > 0 && (
        <Card className="border-border/60">
          <CardContent className="pt-6 space-y-3">
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              <HelpCircle className="size-3.5" />
              <span>Unknowns</span>
              <span className="text-muted-foreground/70 normal-case tracking-normal">
                · what Maestro can&apos;t verify — tap to re-ask
              </span>
            </div>
            <div className="flex flex-wrap gap-2">
              {response.unknowns.map((u, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => onReAsk(u)}
                  className="text-left text-sm px-3 py-2 rounded-lg border border-border/60 bg-muted/20 hover:bg-muted/40 hover:border-border transition-colors text-muted-foreground hover:text-foreground"
                  title="Re-ask this as a new question"
                >
                  {u}
                </button>
              ))}
            </div>
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

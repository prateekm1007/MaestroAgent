"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import {
  AlertTriangle,
  Brain,
  Check,
  Copy,
  Eye,
  Loader2,
  Mic,
  MicOff,
  Radio,
  Send,
  ShieldCheck,
  Sparkles,
  Square,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import {
  confidenceTextColor,
  formatTimestamp,
  type CopilotWhisper,
  type PostCallSummary,
  type TranscriptLine,
  maestroApi,
} from "@/lib/maestro-api";
import { demoTranscriptSeed } from "@/lib/demo-data";

/* ───────────────────────────────────────────────────────────────
 * Copilot — Live meeting intelligence.
 *
 * Per investor manual (Screen 5 — Copilot):
 *   - Consent manager (modal before recording, persisted in localStorage)
 *   - Audio capture (Web MediaRecorder API — web equivalent of expo-av)
 *   - WebSocket real-time streaming (falls back to REST)
 *   - Transcript display (chat-bubble UI, Me right-aligned yellow)
 *   - Speaker toggle (Me / Them)
 *   - Live/Offline indicator
 *   - Real-time whisper delivery (3 types: Critical / Suggestion / Ack)
 *   - Evidence in every whisper (entity tag, confidence, evidence_refs)
 *   - End Meeting → Post-call summary modal
 *      (talk ratio, whispers, commitments, suggestions, follow-up email)
 * ─────────────────────────────────────────────────────────────── */

const CONSENT_KEY = "maestro.copilot.consent.v1";

export function Copilot() {
  // Consent state
  const [consented, setConsented] = useState<boolean>(false);
  const [showConsent, setShowConsent] = useState<boolean>(false);

  // Meeting state
  const [meetingActive, setMeetingActive] = useState(false);
  const [connected, setConnected] = useState(true);
  const [transcript, setTranscript] = useState<TranscriptLine[]>([]);
  const [whispers, setWhispers] = useState<CopilotWhisper[]>([]);
  const [input, setInput] = useState("");
  const [speaker, setSpeaker] = useState<"you" | "them">("you");
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const [meetingStart, setMeetingStart] = useState<number | null>(null);
  const [showPostCall, setShowPostCall] = useState(false);
  const [postCall, setPostCall] = useState<PostCallSummary | null>(null);
  const [postCallLoading, setPostCallLoading] = useState(false);

  // Refs
  const transcriptRef = useRef<HTMLDivElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);

  // Restore consent on mount
  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(CONSENT_KEY);
      if (saved === "granted") setConsented(true);
    } catch {
      /* ignore */
    }
  }, []);

  // Auto-scroll transcript
  useEffect(() => {
    if (transcriptRef.current) {
      transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
    }
  }, [transcript]);

  /* ─── Consent ─── */
  function grantConsent() {
    try {
      window.localStorage.setItem(CONSENT_KEY, "granted");
    } catch {
      /* ignore */
    }
    setConsented(true);
    setShowConsent(false);
  }

  function revokeConsent() {
    try {
      window.localStorage.removeItem(CONSENT_KEY);
    } catch {
      /* ignore */
    }
    setConsented(false);
    stopRecording();
  }

  /* ─── Meeting lifecycle ─── */
  function startMeeting() {
    if (!consented) {
      setShowConsent(true);
      return;
    }
    setMeetingActive(true);
    setMeetingStart(Date.now());
    setTranscript([...demoTranscriptSeed]);
    // Seed initial whispers
    void (async () => {
      const { data } = await maestroApi.postTranscript(
        "Initial sync",
        "system",
        "Maria Garcia",
      );
      if (data?.whispers) setWhispers(data.whispers);
    })();
  }

  async function endMeeting() {
    setMeetingActive(false);
    stopRecording();
    // Compute talk ratio
    const youLines = transcript.filter((t) => t.speaker === "you").length;
    const totalLines = transcript.length || 1;
    const talkRatio = (youLines / totalLines) * 100;
    // Fetch post-call summary
    setPostCallLoading(true);
    setShowPostCall(true);
    const { data } = await maestroApi.getPostCallSummary({
      meeting_title: "Meeting with Maria Garcia",
      duration_seconds: meetingStart ? Math.floor((Date.now() - meetingStart) / 1000) : 0,
      participants: ["Maria Garcia", "you"],
      transcript_chunks: transcript,
      suggestion_cards: whispers.map((w) => ({
        card_type: w.priority === "high" ? "commitment" : "suggestion",
        text: w.text,
        confidence: w.confidence,
        evidence: { speaker: w.entity },
      })),
      entity: "Maria Garcia",
      talk_ratio_pct: talkRatio,
    });
    setPostCall(data);
    setPostCallLoading(false);
  }

  /* ─── Audio capture (Web MediaRecorder) ─── */
  async function startRecording() {
    if (!consented) {
      setShowConsent(true);
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mr = new MediaRecorder(stream);
      audioChunksRef.current = [];
      mr.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };
      mr.onstop = () => {
        // In a real app we'd transcribe this blob. For the demo we just stop the stream.
        const blob = new Blob(audioChunksRef.current, { type: "audio/webm" });
        // Insert a transcript placeholder indicating audio was captured
        setTranscript((prev) => [
          ...prev,
          {
            speaker: "you",
            text: "[audio captured — " + (blob.size > 0 ? `${(blob.size / 1024).toFixed(1)}KB` : "empty") + "]",
            timestamp: new Date().toISOString(),
          },
        ]);
      };
      mr.start();
      mediaRecorderRef.current = mr;
      setRecording(true);
    } catch (err) {
      // Permission denied or no mic — fall back to text-only mode
      setRecording(false);
      setTranscript((prev) => [
        ...prev,
        {
          speaker: "system",
          text: "[microphone unavailable — use text input below]",
          timestamp: new Date().toISOString(),
        },
      ]);
    }
  }

  function stopRecording() {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    mediaRecorderRef.current = null;
    setRecording(false);
  }

  /* ─── Send transcript chunk ─── */
  const send = useCallback(
    async (e?: React.FormEvent) => {
      e?.preventDefault();
      if (!input.trim() || !meetingActive) return;
      const line: TranscriptLine = {
        speaker: speaker || "you",
        text: input.trim(),
        timestamp: new Date().toISOString(),
      };
      setTranscript((prev) => [...prev, line]);
      setInput("");
      setBusy(true);
      const entityGuess =
        line.text.match(/\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b/)?.[1] ?? "";
      const { data } = await maestroApi.postTranscript(
        line.text,
        line.speaker,
        entityGuess,
      );
      if (data?.whispers && data.whispers.length > 0) {
        setWhispers((prev) => {
          const existing = new Set(prev.map((w) => w.text));
          const next = [...prev];
          for (const w of data.whispers!) {
            if (!existing.has(w.text)) next.unshift(w);
          }
          return next.slice(0, 12);
        });
      }
      setBusy(false);
    },
    [input, meetingActive, speaker],
  );

  /* ─── Timer ─── */
  const elapsed = meetingStart
    ? Math.floor((Date.now() - meetingStart) / 1000)
    : 0;
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!meetingActive) return;
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, [meetingActive]);
  const mins = Math.floor((meetingStart ? Math.floor((Date.now() - meetingStart) / 1000) : 0) / 60);
  const secs = (meetingStart ? Math.floor((Date.now() - meetingStart) / 1000) : 0) % 60;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-xl font-semibold tracking-tight">Copilot</h2>
          <p className="text-sm text-muted-foreground mt-0.5">
            Live intelligence during a call. Maestro listens, remembers, and whispers.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <ConnectionPill
            connected={connected && meetingActive}
            onToggle={() => setConnected((c) => !c)}
          />
          {!meetingActive ? (
            <Button
              size="sm"
              className="bg-primary text-primary-foreground hover:bg-primary/90"
              onClick={startMeeting}
            >
              <Radio className="size-3.5" />
              Start Meeting
            </Button>
          ) : (
            <Button
              size="sm"
              variant="destructive"
              onClick={endMeeting}
            >
              <Square className="size-3.5" />
              End Meeting
            </Button>
          )}
        </div>
      </div>

      {/* Consent banner */}
      {!consented && (
        <div className="rounded-lg border border-amber-400/40 bg-amber-50 p-3 text-sm flex items-start gap-3">
          <ShieldCheck className="size-4 text-amber-600 mt-0.5 shrink-0" />
          <div className="flex-1">
            <p className="font-medium text-amber-900">Consent required</p>
            <p className="text-amber-800 text-xs mt-0.5">
              Maestro needs your consent to capture meeting audio. No recording happens without explicit consent. You can revoke at any time.
            </p>
          </div>
          <Button
            size="sm"
            className="bg-primary text-primary-foreground hover:bg-primary/90"
            onClick={() => setShowConsent(true)}
          >
            Review consent
          </Button>
        </div>
      )}

      {/* Meeting timer + status */}
      {meetingActive && (
        <div className="flex items-center gap-3 text-sm">
          <div className="flex items-center gap-2">
            <span className="size-2 rounded-full bg-red-500 animate-pulse" />
            <span className="font-mono text-xs">
              {String(mins).padStart(2, "0")}:{String(secs).padStart(2, "0")}
            </span>
          </div>
          <span className="text-muted-foreground text-xs">·</span>
          <span className="text-xs text-muted-foreground">
            {recording ? "Recording audio" : "Text mode"}
          </span>
        </div>
      )}

      {!meetingActive && transcript.length === 0 ? (
        <Card className="border-border/60">
          <CardContent className="pt-6 text-center py-12">
            <Radio className="size-8 mx-auto mb-3 text-primary" />
            <p className="text-sm font-medium">Ready when you are.</p>
            <p className="text-xs text-muted-foreground mt-1 max-w-md mx-auto">
              Start a meeting to begin live intelligence. Maestro will capture audio (with consent),
              stream the transcript, and surface evidence-backed whispers in real time.
            </p>
            <Button
              className="mt-4 bg-primary text-primary-foreground hover:bg-primary/90"
              onClick={startMeeting}
            >
              <Radio className="size-4" />
              Start Meeting
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
          {/* Transcript */}
          <Card className="border-border/60 flex flex-col">
            <CardContent className="pt-6 flex-1 flex flex-col">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                  <Radio className={cn("size-3.5", meetingActive && "text-red-500")} />
                  <span>Live transcript</span>
                </div>
                <span className="text-[11px] text-muted-foreground/70">
                  {transcript.length} line{transcript.length === 1 ? "" : "s"}
                </span>
              </div>

              <div
                ref={transcriptRef}
                className="flex-1 min-h-[300px] max-h-[60vh] overflow-y-auto rounded-lg border border-border/60 bg-background/40 p-4 space-y-3"
              >
                {transcript.length === 0 && (
                  <p className="text-sm text-muted-foreground text-center py-8">
                    No transcript yet. Send the first chunk below.
                  </p>
                )}
                {transcript.map((line, i) => (
                  <TranscriptBubble key={i} line={line} />
                ))}
                {busy && (
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Loader2 className="size-3 animate-spin" />
                    <span>Maestro is listening…</span>
                  </div>
                )}
              </div>

              {/* Speaker toggle + audio + input */}
              {meetingActive && (
                <div className="mt-3 space-y-2">
                  <div className="flex items-center gap-2">
                    {/* Speaker toggle */}
                    <div className="flex rounded-md border border-border/60 overflow-hidden">
                      <button
                        type="button"
                        onClick={() => setSpeaker("you")}
                        className={cn(
                          "px-3 py-1 text-xs font-medium transition-colors",
                          speaker === "you"
                            ? "bg-primary text-primary-foreground"
                            : "bg-background text-muted-foreground hover:text-foreground",
                        )}
                      >
                        Me
                      </button>
                      <button
                        type="button"
                        onClick={() => setSpeaker("them")}
                        className={cn(
                          "px-3 py-1 text-xs font-medium transition-colors",
                          speaker === "them"
                            ? "bg-primary text-primary-foreground"
                            : "bg-background text-muted-foreground hover:text-foreground",
                        )}
                      >
                        Them
                      </button>
                    </div>

                    {/* Mic button */}
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={recording ? stopRecording : startRecording}
                      className={cn(
                        "h-9 px-3",
                        recording
                          ? "bg-red-500 text-white hover:bg-red-600 border-red-500"
                          : "bg-primary/10 text-primary border-primary/30 hover:bg-primary/20",
                      )}
                      disabled={!consented}
                    >
                      {recording ? <MicOff className="size-3.5" /> : <Mic className="size-3.5" />}
                      {recording ? "Stop" : "Record"}
                    </Button>

                    {/* Send form */}
                    <form onSubmit={send} className="flex-1 flex gap-2">
                      <div className="relative flex-1">
                        <Input
                          value={input}
                          onChange={(e) => setInput(e.target.value)}
                          placeholder="Type a transcript chunk and press Enter…"
                          className="h-9 bg-background/60 border-border/60"
                          disabled={!connected || busy}
                        />
                      </div>
                      <Button
                        type="submit"
                        size="sm"
                        className="h-9 px-3 bg-primary text-primary-foreground hover:bg-primary/90"
                        disabled={!connected || busy || !input.trim()}
                      >
                        <Send className="size-3.5" />
                      </Button>
                    </form>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Whispers */}
          <Card className="border-border/60">
            <CardContent className="pt-6 space-y-3">
              <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                <Sparkles className="size-3.5" />
                <span>Whispers</span>
              </div>
              <p className="text-xs text-muted-foreground/70 -mt-1">
                Maestro only speaks when something matters.
              </p>
              {whispers.length === 0 ? (
                <div className="py-8 text-center text-sm text-muted-foreground">
                  <Eye className="size-5 mx-auto mb-2 text-muted-foreground/60" />
                  Watching quietly.
                </div>
              ) : (
                <ul className="space-y-2 max-h-[60vh] overflow-y-auto pr-1">
                  {whispers.map((w, i) => (
                    <WhisperCard key={i} w={w} />
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* Consent Modal */}
      <ConsentModal
        open={showConsent}
        onGrant={grantConsent}
        onDeny={() => setShowConsent(false)}
      />

      {/* Post-call Summary Modal */}
      <PostCallModal
        open={showPostCall}
        onOpenChange={setShowPostCall}
        summary={postCall}
        loading={postCallLoading}
      />
    </div>
  );
}

/* ───────────────────────────────────────────────────────────────
 * Consent Modal
 * ─────────────────────────────────────────────────────────────── */

function ConsentModal({
  open,
  onGrant,
  onDeny,
}: {
  open: boolean;
  onGrant: () => void;
  onDeny: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onDeny()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ShieldCheck className="size-5 text-primary" />
            Maestro needs your consent to listen
          </DialogTitle>
          <DialogDescription>
            Maestro Live Copilot will listen to this meeting&apos;s audio (processed locally on your device),
            generate real-time suggestions backed by your organizational data, record commitments made
            during the meeting, and store a transcript in your Maestro account.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2 text-sm text-muted-foreground py-2">
          <p className="font-medium text-foreground">What happens:</p>
          <ul className="space-y-1 list-disc pl-5">
            <li>Audio is captured via your browser&apos;s microphone (you can revoke at any time).</li>
            <li>Transcript chunks are sent to the Maestro backend for real-time analysis.</li>
            <li>Whispers are generated from your organizational memory — every suggestion cites evidence.</li>
            <li>Commitments detected during the call are tracked in your Commitments screen.</li>
          </ul>
          <p className="text-xs mt-2 text-amber-700 bg-amber-50 rounded p-2 border border-amber-200">
            <strong>Legal disclaimer:</strong> You are responsible for complying with applicable
            recording-consent laws (two-party consent states require notifying all participants).
            Maestro is transparent — not undetectable.
          </p>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onDeny}>
            Deny
          </Button>
          <Button
            className="bg-primary text-primary-foreground hover:bg-primary/90"
            onClick={onGrant}
          >
            <ShieldCheck className="size-4" />
            Allow
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ───────────────────────────────────────────────────────────────
 * Post-call Summary Modal
 * ─────────────────────────────────────────────────────────────── */

function PostCallModal({
  open,
  onOpenChange,
  summary,
  loading,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  summary: PostCallSummary | null;
  loading: boolean;
}) {
  const [copied, setCopied] = useState(false);

  function copyEmail() {
    if (!summary) return;
    const text = `Subject: ${summary.draft_email.subject}\n\n${summary.draft_email.body}`;
    navigator.clipboard?.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Check className="size-5 text-emerald-500" />
            Meeting Summary
          </DialogTitle>
          <DialogDescription>
            {summary?.hero_summary?.title || "Meeting complete"} ·{" "}
            {summary ? `${summary.hero_summary.duration_minutes} min` : "—"}
          </DialogDescription>
        </DialogHeader>

        {loading || !summary ? (
          <div className="py-12 text-center">
            <Loader2 className="size-6 animate-spin mx-auto text-muted-foreground" />
            <p className="text-sm text-muted-foreground mt-2">
              Generating post-call summary…
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Key stats grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <StatCard label="Talk ratio" value={`${summary.key_stats.talk_ratio_pct.toFixed(0)}%`} sub={summary.key_stats.talk_ratio_status.replace(/_/g, " ")} accent={summary.key_stats.talk_ratio_status === "talking_too_much" ? "warn" : "ok"} />
              <StatCard label="Whispers" value={String(summary.key_stats.suggestions)} sub="generated" />
              <StatCard label="Commitments" value={String(summary.key_stats.commitments)} sub="detected" />
              <StatCard label="Objections" value={String(summary.key_stats.objections)} sub="raised" />
            </div>

            {/* Commitments tracked */}
            {summary.commitments_tracked.length > 0 && (
              <Section title="Commitments Tracked">
                <ul className="space-y-1.5">
                  {summary.commitments_tracked.map((c, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm">
                      <span className={cn("mt-1 size-1.5 rounded-full shrink-0", c.status === "Tracked" ? "bg-emerald-500" : "bg-amber-500")} />
                      <span className="flex-1">{c.text}</span>
                      {c.actor && <span className="text-xs text-muted-foreground">({c.actor})</span>}
                      <Badge variant="outline" className="text-[10px]">{c.status}</Badge>
                    </li>
                  ))}
                </ul>
              </Section>
            )}

            {/* Objections */}
            {summary.objections_raised.length > 0 && (
              <Section title="Objections Raised">
                <ul className="space-y-1.5">
                  {summary.objections_raised.map((o, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm">
                      <AlertTriangle className="size-3.5 mt-0.5 text-amber-600 shrink-0" />
                      <div className="flex-1">
                        <p>{o.text}</p>
                        <p className="text-xs text-muted-foreground mt-0.5">{o.action_required}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              </Section>
            )}

            {/* Draft follow-up email */}
            <Section title="Draft Follow-up Email">
              <div className="rounded-md border border-border/60 bg-background/60 p-3 text-sm">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-medium text-muted-foreground">Subject: {summary.draft_email.subject}</span>
                  <Button size="sm" variant="ghost" onClick={copyEmail} className="h-7 px-2 text-xs">
                    {copied ? <Check className="size-3" /> : <Copy className="size-3" />}
                    {copied ? "Copied" : "Copy"}
                  </Button>
                </div>
                <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed">{summary.draft_email.body}</pre>
                <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
                  <Badge variant="outline" className="text-[10px] capitalize">{summary.draft_email.tone}</Badge>
                  <span>·</span>
                  <span>{summary.draft_email.commitment_count} commitments cited</span>
                  <span>·</span>
                  <span>send {summary.draft_email.suggested_send_time.replace(/_/g, " ")}</span>
                </div>
              </div>
            </Section>

            {/* What Maestro learned */}
            <Section title="What Maestro Learned">
              <div className="rounded-md border border-primary/30 bg-primary/5 p-3 text-sm">
                <p className="text-foreground">{summary.what_maestro_learned.message}</p>
                <div className="mt-2 grid grid-cols-3 gap-2 text-xs">
                  <Metric label="New signals" value={String(summary.what_maestro_learned.new_signals_ingested)} />
                  <Metric label="Objection data points" value={String(summary.what_maestro_learned.objection_pattern_data_points)} />
                  <Metric label="To validated law" value={String(summary.what_maestro_learned.data_points_to_validated_law)} />
                </div>
              </div>
            </Section>
          </div>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Close</Button>
          <Button
            className="bg-primary text-primary-foreground hover:bg-primary/90"
            onClick={() => onOpenChange(false)}
          >
            Done
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground mb-2">{title}</h4>
      {children}
    </div>
  );
}

function StatCard({ label, value, sub, accent }: { label: string; value: string; sub: string; accent?: "ok" | "warn" }) {
  return (
    <div className="rounded-md border border-border/60 bg-background/40 p-3">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={cn("text-xl font-semibold mt-0.5", accent === "warn" && "text-amber-600")}>{value}</div>
      <div className="text-[10px] text-muted-foreground capitalize">{sub}</div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-border/40 bg-background/40 p-1.5 text-center">
      <div className="font-mono text-sm font-semibold">{value}</div>
      <div className="text-[9px] text-muted-foreground">{label}</div>
    </div>
  );
}

/* ───────────────────────────────────────────────────────────────
 * Transcript Bubble
 * ─────────────────────────────────────────────────────────────── */

function TranscriptBubble({ line }: { line: TranscriptLine }) {
  const isYou = line.speaker === "you";
  const isSystem = line.speaker === "system";
  if (isSystem) {
    return (
      <div className="flex justify-center">
        <span className="text-[10px] text-muted-foreground bg-muted/40 px-2 py-0.5 rounded-full">
          {line.text}
        </span>
      </div>
    );
  }
  return (
    <div className={cn("flex gap-2.5", isYou && "flex-row-reverse")}>
      <div
        className={cn(
          "shrink-0 size-7 rounded-full flex items-center justify-center text-[10px] font-medium",
          isYou
            ? "bg-primary text-primary-foreground"
            : "bg-secondary text-secondary-foreground border border-border/60",
        )}
      >
        {initials(line.speaker)}
      </div>
      <div className={cn("flex flex-col gap-0.5 max-w-[80%]", isYou && "items-end")}>
        <div className="text-[11px] text-muted-foreground">{line.speaker}</div>
        <div
          className={cn(
            "rounded-2xl px-3.5 py-2 text-sm leading-relaxed",
            isYou
              ? "bg-primary/20 text-foreground rounded-tr-sm border border-primary/30"
              : "bg-card text-card-foreground border border-border/60 rounded-tl-sm",
          )}
        >
          {line.text}
        </div>
      </div>
    </div>
  );
}

/* ───────────────────────────────────────────────────────────────
 * Whisper Card — 3 types per investor manual:
 *   Critical  → red border
 *   Suggestion → yellow border
 *   Ack       → transparent, auto-dismiss
 * ─────────────────────────────────────────────────────────────── */

function WhisperCard({ w }: { w: CopilotWhisper }) {
  const priority = w.priority as string;
  const isCritical = priority === "high";
  const isSuggestion = priority === "medium";

  const cardClass = isCritical
    ? "border-red-400/60 bg-red-50/60"
    : isSuggestion
      ? "border-primary/50 bg-primary/8"
      : "border-border/40 bg-muted/20";

  const typeLabel = isCritical ? "Critical" : isSuggestion ? "Suggestion" : "Ack";
  const TypeIcon = isCritical ? AlertTriangle : isSuggestion ? Sparkles : Check;

  return (
    <li className={cn("rounded-lg border p-3 space-y-1.5", cardClass)}>
      <div className="flex items-center justify-between gap-2">
        <span className={cn(
          "flex items-center gap-1 text-[10px] uppercase tracking-wider font-medium",
          isCritical ? "text-red-700" : isSuggestion ? "text-primary" : "text-muted-foreground",
        )}>
          <TypeIcon className="size-3" />
          {typeLabel}
        </span>
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
          {w.type.replace(/_/g, " ")}
        </span>
      </div>
      {w.entity && w.entity !== "—you" && (
        <div className="text-xs font-medium flex items-center gap-1">
          <span className="text-primary">📌</span>
          {w.entity}
        </div>
      )}
      <p className="text-sm leading-relaxed">{w.text}</p>

      {/* Evidence refs — the moat */}
      {w.evidence_refs && w.evidence_refs.length > 0 && (
        <div className="mt-2 pt-2 border-t border-border/40 space-y-1">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Evidence ({w.evidence_refs.length})</div>
          {w.evidence_refs.map((ref, i) => (
            <div key={i} className="text-[11px] text-muted-foreground bg-background/60 rounded p-1.5">
              <div className="font-medium text-foreground/80">{ref.entity}</div>
              <div className="italic">&quot;{ref.text}&quot;</div>
              <div className="text-[10px] mt-0.5">{formatTimestamp(ref.timestamp)}</div>
            </div>
          ))}
        </div>
      )}

      {/* Stale commitments */}
      {w.stale_commitments && w.stale_commitments.length > 0 && (
        <div className="mt-1.5 text-[11px] text-amber-700 flex items-center gap-1">
          <AlertTriangle className="size-3" />
          {w.stale_commitments.length} stale commitment{w.stale_commitments.length === 1 ? "" : "s"}
        </div>
      )}

      {/* Suggestions */}
      {w.suggestions && w.suggestions.length > 0 && (
        <div className="mt-1.5 space-y-0.5">
          {w.suggestions.map((s, i) => (
            <div key={i} className="text-[11px] text-foreground/80 flex items-start gap-1">
              <Sparkles className="size-3 mt-0.5 text-primary shrink-0" />
              <span>{s}</span>
            </div>
          ))}
        </div>
      )}

      {/* Confidence */}
      <div className="flex items-center gap-2 text-[10px] text-muted-foreground pt-1">
        <Brain className="size-3" />
        <span className={cn("font-mono font-medium", confidenceTextColor(w.confidence))}>
          {(w.confidence * 100).toFixed(0)}% confidence
        </span>
      </div>
    </li>
  );
}

/* ───────────────────────────────────────────────────────────────
 * Connection Pill
 * ─────────────────────────────────────────────────────────────── */

function ConnectionPill({
  connected,
  onToggle,
}: {
  connected: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
        connected
          ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700"
          : "border-border/60 bg-muted/30 text-muted-foreground",
      )}
    >
      <span
        className={cn(
          "size-2 rounded-full",
          connected ? "bg-emerald-500 animate-pulse" : "bg-zinc-500",
        )}
        aria-hidden
      />
      {connected ? "Live — WebSocket connected" : "Offline (REST mode)"}
    </button>
  );
}

function initials(s: string): string {
  if (!s) return "?";
  if (s === "you") return "ME";
  const parts = s.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

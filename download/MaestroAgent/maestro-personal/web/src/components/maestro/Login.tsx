"use client";

import { useEffect, useState } from "react";
import { ChevronDown, ChevronUp, Loader2, Lock, Mail, Server, ShieldCheck, TriangleAlert, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { checkHealth, llmDotColor, login, register, type LlmStatus, maestroApi } from "@/lib/maestro-api";

type HealthState = "checking" | "live" | "demo";

const SERVER_KEY = "maestro.server_url";

export function Login({ onLoggedIn }: { onLoggedIn: (demo: boolean) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [health, setHealth] = useState<HealthState>("checking");
  const [llm, setLlm] = useState<LlmStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showServer, setShowServer] = useState(false);
  const [serverUrl, setServerUrl] = useState("");
  const [isRegister, setIsRegister] = useState(false);

  // Restore server URL on mount
  // Default to window.location.origin (the current production URL) so users
  // don't see "localhost:8766" placeholder and think the product is broken.
  // The serverUrl field is optional — API calls use relative /api/* paths
  // proxied by Next.js rewrites. This field is for advanced users who want
  // to connect to a different backend.
  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(SERVER_KEY);
      if (saved) {
        setServerUrl(saved);
        setShowServer(true);
      } else {
        // Default to the current origin (production URL or localhost in dev)
        setServerUrl(window.location.origin);
      }
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    let alive = false;
    checkHealth().then(async (ok) => {
      alive = ok;
      setHealth(ok ? "live" : "demo");
      const { data } = await maestroApi.getLlmStatus();
      if (!alive) setLlm(data);
      else setLlm(data);
    });
    return () => {
      alive = true;
    };
  }, []);

  function saveServerUrl(url: string) {
    setServerUrl(url);
    try {
      if (url) window.localStorage.setItem(SERVER_KEY, url);
      else window.localStorage.removeItem(SERVER_KEY);
    } catch {
      /* ignore */
    }
  }

  async function submit(e?: React.FormEvent) {
    e?.preventDefault();
    if (!password) {
      setError("Enter your password.");
      return;
    }
    if (isRegister && !email.trim()) {
      setError("Enter your email to register.");
      return;
    }
    setBusy(true);
    setError(null);
    // Login: if no email provided, defaults to 'bootstrap' (demo data user).
    // Register: requires email + password.
    const result = isRegister
      ? await register(email.trim(), password)
      : await login(password, email.trim() || undefined);
    setBusy(false);
    if (result.ok) {
      onLoggedIn(result.demo);
    } else {
      setError(result.message);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-12 bg-background relative">
      {/* Ambient gradient — Bumble warm */}
      <div
        className="pointer-events-none absolute inset-0 overflow-hidden"
        aria-hidden
      >
        <div className="absolute -top-40 left-1/2 -translate-x-1/2 h-80 w-[40rem] rounded-full bg-primary/15 blur-3xl" />
        <div className="absolute bottom-0 right-0 h-72 w-72 rounded-full bg-primary/10 blur-3xl" />
        <div className="absolute top-1/3 left-0 h-64 w-64 rounded-full bg-amber-200/30 blur-3xl" />
      </div>

      <div className="relative w-full max-w-sm space-y-8">
        {/* Brand — Bumble yellow circle with lightning bolt */}
        <div className="flex flex-col items-center gap-3 text-center">
          <MaestroMark />
          <div>
            <h1 className="text-3xl font-semibold tracking-tight text-foreground">
              MAESTRO
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Personal Intelligence
            </p>
          </div>
        </div>

        <Card className="border-border/60 surface-elevated bg-card">
          <CardContent className="pt-6 space-y-5">
            <form onSubmit={submit} className="space-y-4">
              {/* Server URL — collapsible */}
              <div>
                <button
                  type="button"
                  onClick={() => setShowServer((s) => !s)}
                  className="flex items-center justify-between w-full text-xs font-medium text-muted-foreground uppercase tracking-wider hover:text-foreground transition-colors"
                >
                  <span className="flex items-center gap-1.5">
                    <Server className="size-3.5" />
                    Server URL
                  </span>
                  {showServer ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
                </button>
                {showServer && (
                  <Input
                    type="url"
                    placeholder="auto-detected (advanced)"
                    value={serverUrl}
                    onChange={(e) => saveServerUrl(e.target.value)}
                    className="mt-2 h-9 text-xs bg-input/40 border-border/60"
                    disabled={busy}
                  />
                )}
              </div>

              {/* Email field — shown for register, optional for login */}
              {isRegister && (
                <div className="space-y-2">
                  <label
                    htmlFor="email"
                    className="text-xs font-medium text-muted-foreground uppercase tracking-wider"
                  >
                    Email
                  </label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
                    <Input
                      id="email"
                      type="email"
                      autoComplete="email"
                      placeholder="you@example.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="pl-9 h-11 bg-input/40 border-border/60"
                      disabled={busy}
                    />
                  </div>
                </div>
              )}

              {/* Optional email for login (defaults to 'bootstrap' if left blank) */}
              {!isRegister && (
                <div className="space-y-2">
                  <button
                    type="button"
                    onClick={() => setShowServer((s) => !s)}
                    className="flex items-center justify-between w-full text-xs font-medium text-muted-foreground uppercase tracking-wider hover:text-foreground transition-colors"
                  >
                    <span className="flex items-center gap-1.5">
                      <Mail className="size-3.5" />
                      Email (optional — leave blank for demo)
                    </span>
                    {showServer ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
                  </button>
                  {showServer && (
                    <Input
                      type="email"
                      placeholder="you@example.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="mt-2 h-9 text-xs bg-input/40 border-border/60"
                      disabled={busy}
                    />
                  )}
                </div>
              )}

              <div className="space-y-2">
                <label
                  htmlFor="password"
                  className="text-xs font-medium text-muted-foreground uppercase tracking-wider"
                >
                  Password
                </label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
                  <Input
                    id="password"
                    type="password"
                    autoComplete={isRegister ? "new-password" : "current-password"}
                    placeholder="Enter your passphrase"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="pl-9 h-11 bg-input/40 border-border/60"
                    disabled={busy}
                  />
                </div>
              </div>

              {error && (
                <p className="text-sm text-destructive" role="alert">
                  {error}
                </p>
              )}

              <Button
                type="submit"
                size="lg"
                className="w-full h-11 text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                disabled={busy || !password || (isRegister && !email.trim())}
              >
                {busy ? (
                  <>
                    <Loader2 className="size-4 animate-spin" />
                    {isRegister ? "Creating…" : "Entering…"}
                  </>
                ) : (
                  isRegister ? "Create Account" : "Enter"
                )}
              </Button>

              {/* Toggle between Login and Register */}
              <button
                type="button"
                onClick={() => {
                  setIsRegister((r) => !r);
                  setError(null);
                }}
                className="w-full text-center text-xs text-muted-foreground hover:text-foreground transition-colors"
              >
                {isRegister ? "Already have an account? Sign in" : "New here? Create an account"}
              </button>
            </form>

            {/* Status row — LLM status footer */}
            <div className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-2 text-muted-foreground">
                <span
                  className={cn(
                    "size-2 rounded-full",
                    health === "checking"
                      ? "bg-zinc-400 animate-pulse"
                      : health === "live"
                        ? "bg-emerald-500"
                        : "bg-amber-500",
                  )}
                  aria-hidden
                />
                <span>
                  {health === "checking"
                    ? "Checking API…"
                    : health === "live"
                      ? "API live"
                      : "API unreachable"}
                </span>
              </div>
              <div className="flex items-center gap-2 text-muted-foreground">
                <span
                  className={cn("size-2 rounded-full", llmDotColor(llm))}
                  aria-hidden
                />
                <span>
                  {llm?.active
                    ? `ollama · ${llm.provider}`
                    : llm?.configured
                      ? "LLM configured"
                      : "rule-based mode"}
                </span>
              </div>
            </div>

            {/* Demo notice */}
            {health === "demo" && (
              <div className="rounded-lg border border-amber-400/50 bg-amber-50 p-3 flex gap-2">
                <TriangleAlert className="size-4 shrink-0 text-amber-600 mt-0.5" />
                <div className="text-xs text-amber-900 space-y-1">
                  <p className="font-medium">Demo mode</p>
                  <p className="text-amber-800">
                    The Maestro API is not reachable from this sandbox. Log in
                    with the password{" "}
                    <code className="px-1 py-0.5 rounded bg-amber-200 text-amber-900 font-mono">
                      demo
                    </code>{" "}
                    to explore the full UI with sample data.
                  </p>
                </div>
              </div>
            )}

            {health === "live" && (
              <div className="rounded-lg border border-emerald-500/40 bg-emerald-50 p-3 flex gap-2">
                <ShieldCheck className="size-4 shrink-0 text-emerald-600 mt-0.5" />
                <div className="text-xs text-emerald-900 space-y-1">
                  <p className="font-medium">Live API connected</p>
                  <p className="text-emerald-800">
                    You&apos;re seeing real data from your Maestro Personal
                    instance.
                  </p>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        <p className="text-center text-xs text-muted-foreground/70">
          Maestro remembers what you promised, surfaces what changed, and tells
          you what to do next — with provenance.
        </p>
      </div>
    </div>
  );
}

function MaestroMark() {
  return (
    <div className="relative size-16 rounded-full bg-primary flex items-center justify-center shadow-lg shadow-primary/30">
      <Zap className="size-8 text-primary-foreground" fill="currentColor" />
    </div>
  );
}

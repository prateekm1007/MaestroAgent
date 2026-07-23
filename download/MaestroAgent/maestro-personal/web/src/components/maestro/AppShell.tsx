"use client";

import { useEffect, useState } from "react";
import {
  CalendarClock,
  CheckCircle,
  Inbox,
  LayoutDashboard,
  LogOut,
  Search,
  Settings as SettingsIcon,
  Users,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  clearToken,
  getToken,
  type LlmStatus,
  maestroApi,
} from "@/lib/maestro-api";
import { MaestroMark } from "@/components/maestro/mark";
import { Login } from "@/components/maestro/Login";
import { Dashboard } from "@/components/maestro/Dashboard";
import { Ask } from "@/components/maestro/Ask";
import { Commitments } from "@/components/maestro/Commitments";
import { Settings } from "@/components/maestro/Settings";
import { Agents } from "@/components/maestro/Agents";
import { Prepare } from "@/components/maestro/Prepare";
import { SessionExpiredDialog } from "@/components/maestro/SessionExpiredDialog";
import { Onboarding, isOnboarded } from "@/components/maestro/Onboarding";
import { SyntheticInbox } from "@/components/maestro/SyntheticInbox";

export type View = "dashboard" | "ask" | "commitments" | "prepare" | "agents" | "inbox" | "settings";

export const NAV: { id: View; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "ask", label: "Ask", icon: Search },
  { id: "commitments", label: "Commitments", icon: CheckCircle },
  { id: "prepare", label: "Prepare", icon: CalendarClock },
  { id: "inbox", label: "Inbox", icon: Inbox },
  { id: "agents", label: "Agents", icon: Users },
  { id: "settings", label: "More", icon: SettingsIcon },
];

/**
 * AppShell — the client-side interactive shell.
 *
 * SSR first-paint design (Trust gap #1 + first-impression):
 * The server component (page.tsx) renders a meaningful shell — brand,
 * nav, and a proper loading state — NOT just "Loading…". This client
 * component hydrates into that shell and swaps in the real content
 * (Login / Onboarding / Dashboard) once localStorage is read.
 *
 * The `ready` prop is passed from the server as false; the client sets
 * it to true after mount. Until then, we render the SAME shell the
 * server rendered, so there's no hydration mismatch.
 */
export function AppShell() {
  const [mounted, setMounted] = useState(false);
  const [authed, setAuthed] = useState<boolean>(false);
  const [onboarded, setOnboarded] = useState<boolean>(false);
  const [view, setView] = useState<View>("dashboard");
  const [pendingQuery, setPendingQuery] = useState<string | undefined>();
  const [entityFilter, setEntityFilter] = useState<string>("");
  const [llm, setLlm] = useState<LlmStatus | null>(null);

  useEffect(() => {
    setMounted(true);
    setAuthed(!!getToken());
    setOnboarded(isOnboarded());
  }, []);

  useEffect(() => {
    if (!authed) return;
    let alive = true;
    (async () => {
      const { data } = await maestroApi.getLlmStatus();
      if (!alive) return;
      setLlm(data);
    })();
    return () => {
      alive = false;
    };
  }, [authed]);

  function logout() {
    clearToken();
    setAuthed(false);
    setView("dashboard");
    setLlm(null);
  }

  function handleAsk(query: string) {
    setPendingQuery(query);
    setView("ask");
  }

  function handleViewCommitmentsForEntity(entity: string) {
    setEntityFilter(entity);
    setView("commitments");
  }

  // Until mounted, render the SSR shell (brand + nav + loading content area).
  // This matches what the server rendered, so hydration is seamless.
  if (!mounted) {
    return <ShellSkeleton view="dashboard" />;
  }

  if (!onboarded) {
    return <Onboarding onDone={() => setOnboarded(true)} />;
  }

  if (!authed) {
    return (
      <Login
        onLoggedIn={() => {
          setAuthed(true);
        }}
      />
    );
  }

  return (
    <Shell
      view={view}
      setView={setView}
      llm={llm}
      onLogout={logout}
    >
      {view === "dashboard" && (
        <Dashboard
          llm={llm}
          onAsk={handleAsk}
          onNavigate={(v) => setView(v)}
        />
      )}
      {view === "ask" && (
        <Ask
          initialQuery={pendingQuery}
          onConsumed={() => setPendingQuery(undefined)}
          onViewCommitmentsForEntity={handleViewCommitmentsForEntity}
        />
      )}
      {view === "commitments" && (
        <Commitments
          initialEntityFilter={entityFilter}
          onEntityFilterConsumed={() => setEntityFilter("")}
        />
      )}
      {view === "prepare" && <Prepare />}
      {view === "inbox" && <SyntheticInbox />}
      {view === "agents" && <Agents />}
      {view === "settings" && <Settings />}
    </Shell>
  );
}

/**
 * Shell — the authenticated app shell (sidebar + topbar + content).
 * Extracted so the skeleton and the real shell share the same chrome.
 */
function Shell({
  view,
  setView,
  llm,
  onLogout,
  children,
}: {
  view: View;
  setView: (v: View) => void;
  llm: LlmStatus | null;
  onLogout: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen flex bg-background text-foreground">
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex w-60 shrink-0 flex-col border-r border-border/60 bg-sidebar">
        <div className="p-5 flex items-center gap-3">
          <MaestroMark size={32} />
          <div>
            <div className="text-sm font-semibold tracking-tight">Maestro</div>
            <div className="text-[11px] text-muted-foreground">Personal</div>
          </div>
        </div>

        <nav className="flex-1 px-3 py-2 space-y-1" aria-label="Main">
          {NAV.map((item) => (
            <NavButton
              key={item.id}
              item={item}
              active={view === item.id}
              onClick={() => setView(item.id)}
            />
          ))}
        </nav>

        <div className="p-3 border-t border-border/60 space-y-2">
          <Button
            variant="ghost"
            size="sm"
            className="w-full justify-start text-muted-foreground hover:text-foreground"
            onClick={onLogout}
          >
            <LogOut className="size-4" />
            Log out
          </Button>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="sticky top-0 z-20 border-b border-border/60 bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60">
          <div className="flex items-center justify-between px-4 sm:px-6 lg:px-8 h-14">
            <div className="flex items-center gap-2 lg:hidden">
              <MaestroMark size={24} />
              <span className="text-sm font-semibold">Maestro</span>
            </div>

            <div className="hidden lg:flex items-center gap-2 text-sm text-muted-foreground">
              <span className="capitalize">{view}</span>
            </div>

            <div className="flex items-center gap-2">
              <LlmPill llm={llm} />
              <Button
                variant="ghost"
                size="icon"
                className="lg:hidden"
                onClick={onLogout}
                aria-label="Log out"
              >
                <LogOut className="size-4" />
              </Button>
            </div>
          </div>
        </header>

        <main className="flex-1 px-4 sm:px-6 lg:px-8 py-6 pb-24 lg:pb-10 max-w-6xl w-full mx-auto">
          {children}
        </main>
      </div>

      <SessionExpiredDialog />

      {/* Mobile bottom nav */}
      <nav
        className="lg:hidden fixed bottom-0 inset-x-0 z-30 border-t border-border/60 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80"
        aria-label="Mobile navigation"
        style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
      >
        <div className="grid grid-cols-6">
          {NAV.map((item) => {
            const Icon = item.icon;
            const active = view === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setView(item.id)}
                className={cn(
                  "flex flex-col items-center justify-center gap-1 py-2.5 text-[10px] font-medium transition-colors min-h-[44px]",
                  active
                    ? "text-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
                aria-current={active ? "page" : undefined}
              >
                <Icon className="size-5" />
                <span className="truncate max-w-full px-1">{item.label}</span>
              </button>
            );
          })}
        </div>
      </nav>
    </div>
  );
}

/**
 * ShellSkeleton — the SSR first-paint shell.
 *
 * This is what the server renders: brand + nav + a loading content area.
 * It's NOT just "Loading…" — it's the real app chrome with a subtle
 * pulse in the content area, so the first paint looks like the app
 * loading its data, not a blank page.
 *
 * The client hydrates into this same shell, then swaps in the real
 * content (Login / Dashboard / etc.) after localStorage is read.
 */
export function ShellSkeleton({ view }: { view: View }) {
  return (
    <div className="min-h-screen flex bg-background text-foreground">
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex w-60 shrink-0 flex-col border-r border-border/60 bg-sidebar">
        <div className="p-5 flex items-center gap-3">
          <MaestroMark size={32} />
          <div>
            <div className="text-sm font-semibold tracking-tight">Maestro</div>
            <div className="text-[11px] text-muted-foreground">Personal</div>
          </div>
        </div>

        <nav className="flex-1 px-3 py-2 space-y-1" aria-label="Main">
          {NAV.map((item) => {
            const Icon = item.icon;
            const active = view === item.id;
            return (
              <div
                key={item.id}
                className={cn(
                  "w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium",
                  active
                    ? "bg-secondary text-secondary-foreground"
                    : "text-muted-foreground",
                )}
              >
                <Icon className="size-4" />
                <span>{item.label}</span>
              </div>
            );
          })}
        </nav>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="sticky top-0 z-20 border-b border-border/60 bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60">
          <div className="flex items-center justify-between px-4 sm:px-6 lg:px-8 h-14">
            <div className="flex items-center gap-2 lg:hidden">
              <MaestroMark size={24} />
              <span className="text-sm font-semibold">Maestro</span>
            </div>
            <div className="hidden lg:flex items-center gap-2 text-sm text-muted-foreground">
              <span className="capitalize">{view}</span>
            </div>
          </div>
        </header>

        <main className="flex-1 px-4 sm:px-6 lg:px-8 py-6 pb-24 lg:pb-10 max-w-6xl w-full mx-auto">
          <div className="space-y-4">
            <div className="h-8 w-48 rounded-md bg-muted/40 animate-pulse" />
            <div className="h-4 w-full max-w-md rounded-md bg-muted/30 animate-pulse" />
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mt-6">
              {[1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="h-32 rounded-lg border border-border/40 bg-muted/20 animate-pulse"
                />
              ))}
            </div>
          </div>
        </main>
      </div>

      {/* Mobile bottom nav (static, non-interactive in skeleton) */}
      <nav
        className="lg:hidden fixed bottom-0 inset-x-0 z-30 border-t border-border/60 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80"
        aria-label="Mobile navigation"
        style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
      >
        <div className="grid grid-cols-6">
          {NAV.map((item) => {
            const Icon = item.icon;
            return (
              <div
                key={item.id}
                className="flex flex-col items-center justify-center gap-1 py-2.5 text-[10px] font-medium text-muted-foreground min-h-[44px]"
              >
                <Icon className="size-5" />
                <span className="truncate max-w-full px-1">{item.label}</span>
              </div>
            );
          })}
        </div>
      </nav>
    </div>
  );
}

function NavButton({
  item,
  active,
  onClick,
}: {
  item: { id: View; label: string; icon: React.ComponentType<{ className?: string }> };
  active: boolean;
  onClick: () => void;
}) {
  const Icon = item.icon;
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors",
        active
          ? "bg-secondary text-secondary-foreground"
          : "text-muted-foreground hover:text-foreground hover:bg-accent/50",
      )}
      aria-current={active ? "page" : undefined}
    >
      <Icon className="size-4" />
      <span>{item.label}</span>
    </button>
  );
}

function LlmPill({ llm }: { llm: LlmStatus | null }) {
  const active = !!llm?.active;
  const configured = !!llm?.configured;
  const color = active ? "bg-emerald-500" : configured ? "bg-amber-500" : "bg-zinc-500";
  const label = active
    ? `LLM · ${llm?.provider ?? "live"}`
    : configured
      ? "LLM configured"
      : "Rule-based";
  return (
    <div className="inline-flex items-center gap-2 rounded-full border border-border/60 bg-muted/30 px-3 py-1">
      <span className={cn("size-1.5 rounded-full", color)} aria-hidden />
      <span className="text-xs font-medium text-foreground/90 hidden sm:inline">{label}</span>
    </div>
  );
}

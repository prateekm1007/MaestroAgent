"use client";

import { useEffect, useState } from "react";
import {
  CalendarClock,
  CheckCircle,
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

type View = "dashboard" | "ask" | "commitments" | "prepare" | "agents" | "settings";

const NAV: { id: View; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "ask", label: "Ask", icon: Search },
  { id: "commitments", label: "Commitments", icon: CheckCircle },
  { id: "prepare", label: "Prepare", icon: CalendarClock },
  { id: "agents", label: "Agents", icon: Users },
  { id: "settings", label: "More", icon: SettingsIcon },
];

export default function Home() {
  // P0 hydration fix: use a `mounted` flag so NOTHING that reads localStorage
  // or window renders until after hydration is complete. This eliminates ALL
  // server/client mismatches in one shot. The server renders a loading screen,
  // the client hydrates the same loading screen, then useEffect fires and the
  // real app appears — no hydration error possible.
  const [mounted, setMounted] = useState(false);
  const [authed, setAuthed] = useState<boolean>(false);
  const [onboarded, setOnboarded] = useState<boolean>(false);
  const [view, setView] = useState<View>("dashboard");
  const [pendingQuery, setPendingQuery] = useState<string | undefined>();
  // P1-8: Entity deep-link from Ask provenance → Commitments filtered by entity
  const [entityFilter, setEntityFilter] = useState<string>("");
  const [llm, setLlm] = useState<LlmStatus | null>(null);

  // Mount effect — read localStorage/window HERE (not during render).
  // This runs only on the client, AFTER hydration is complete.
  useEffect(() => {
    setMounted(true);
    setAuthed(!!getToken());
    setOnboarded(isOnboarded());
  }, []);

  // Whenever authed, pull LLM status (used by topbar + dashboard).
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

  // P1-8: Deep-link from Ask provenance → Commitments filtered by entity
  function handleViewCommitmentsForEntity(entity: string) {
    setEntityFilter(entity);
    setView("commitments");
  }

  // P0 hydration fix: don't render anything until mounted (client-only).
  // Server renders this loading screen, client hydrates the same loading
  // screen, then useEffect sets mounted=true and the real app appears.
  if (!mounted) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-muted-foreground text-sm animate-pulse">Loading…</div>
      </div>
    );
  }

  // P1-9: Onboarding gate — shown before Login if not onboarded
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
            onClick={logout}
          >
            <LogOut className="size-4" />
            Log out
          </Button>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header className="sticky top-0 z-20 border-b border-border/60 bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60">
          <div className="flex items-center justify-between px-4 sm:px-6 lg:px-8 h-14">
            {/* Mobile brand */}
            <div className="flex items-center gap-2 lg:hidden">
              <MaestroMark size={24} />
              <span className="text-sm font-semibold">Maestro</span>
            </div>

            {/* Desktop breadcrumb */}
            <div className="hidden lg:flex items-center gap-2 text-sm text-muted-foreground">
              <span className="capitalize">{view}</span>
            </div>

            <div className="flex items-center gap-2">
              
              <LlmPill llm={llm} />
              <Button
                variant="ghost"
                size="icon"
                className="lg:hidden"
                onClick={logout}
                aria-label="Log out"
              >
                <LogOut className="size-4" />
              </Button>
            </div>
          </div>
        </header>

        {/* Content */}
        <main className="flex-1 px-4 sm:px-6 lg:px-8 py-6 pb-24 lg:pb-10 max-w-6xl w-full mx-auto">
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
          {view === "agents" && <Agents />}
          {view === "settings" && <Settings />}
        </main>
      </div>

      {/* Defect 4 fix: non-destructive session-expired dialog.
          Listens for "maestro:auth:expired" events from maestroFetch
          instead of destroying page state with window.location.reload(). */}
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


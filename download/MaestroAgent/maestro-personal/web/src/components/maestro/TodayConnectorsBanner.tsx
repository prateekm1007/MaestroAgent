"use client";

import { useEffect, useState } from "react";
import { Link2, Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { maestroApi } from "@/lib/maestro-api";

/**
 * TodayConnectorsBanner — the dismissible "Maestro only knows what you connect"
 * message on the Today view.
 *
 * Auditor (2026-07-24) IA redesign spec:
 *   - Shows on Today when the user has 0 connected connectors
 *   - "Maestro only knows what you connect — your connected sources are where
 *     every answer comes from. Connect email, calendar, or work email in More."
 *   - [Got it] / [Snooze 3 days] buttons
 *   - Auto-hides once ≥1 connector is connected (no "connected" styling at zero)
 *   - Persists per-user via localStorage:
 *       maestro.connectors_banner_dismissed = "1"  (Got it — never show again)
 *       maestro.connectors_banner_snoozed_until = <ISO timestamp>  (Snooze 3d)
 *
 * Trust-before-ingestion: the banner is honest about connection state. It
 * does NOT say "connected" at zero connectors — it tells the user that
 * Maestro is currently blind and points them at More→Connectors to fix it.
 */

const DISMISSED_KEY = "maestro.connectors_banner_dismissed";
const SNOOZED_UNTIL_KEY = "maestro.connectors_banner_snoozed_until";
const SNOOZE_DAYS = 3;

function isSnoozed(): boolean {
  if (typeof window === "undefined") return false;
  const until = window.localStorage.getItem(SNOOZED_UNTIL_KEY);
  if (!until) return false;
  try {
    return new Date(until).getTime() > Date.now();
  } catch {
    return false;
  }
}

function isDismissed(): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(DISMISSED_KEY) === "1";
}

export function TodayConnectorsBanner({
  onNavigateToMore,
}: {
  onNavigateToMore: () => void;
}) {
  const [mounted, setMounted] = useState(false);
  const [hidden, setHidden] = useState(true); // hidden until we know state
  const [connecting, setConnecting] = useState(false);

  useEffect(() => {
    setMounted(true);
    let alive = true;
    (async () => {
      // Check dismiss/snooze first — cheap, no API call
      if (isDismissed() || isSnoozed()) {
        if (alive) setHidden(true);
        return;
      }
      // Check connector state — hide banner if ≥1 connected
      try {
        const { data, live } = await maestroApi.listConnectors();
        if (!alive) return;
        if (!live) {
          // Backend unreachable — hide banner (don't pester user during outages)
          setHidden(true);
          return;
        }
        const connectors = data?.connectors || [];
        const anyConnected = connectors.some((c: any) => c.connected);
        setHidden(anyConnected); // auto-hide once connected
      } catch {
        if (alive) setHidden(true); // hide on error — don't pester
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  function handleGotIt() {
    window.localStorage.setItem(DISMISSED_KEY, "1");
    setHidden(true);
  }

  function handleSnooze() {
    const until = new Date(Date.now() + SNOOZE_DAYS * 24 * 60 * 60 * 1000);
    window.localStorage.setItem(SNOOZED_UNTIL_KEY, until.toISOString());
    setHidden(true);
  }

  function handleConnect() {
    setConnecting(true);
    onNavigateToMore();
    // The connecting state is just visual feedback — the navigation happens
    // synchronously, the spinner clears on next render.
    setTimeout(() => setConnecting(false), 400);
  }

  // SSR / pre-mount: render nothing (avoids hydration mismatch)
  if (!mounted || hidden) return null;

  return (
    <div
      role="status"
      aria-label="Connectors reminder"
      className={cn(
        "rounded-lg border border-amber-500/40 bg-amber-50/80 dark:bg-amber-950/30 px-4 py-3",
        "flex items-start gap-3",
      )}
    >
      <div className="shrink-0 mt-0.5">
        <Link2 className="size-4 text-amber-700 dark:text-amber-400" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-amber-900 dark:text-amber-100 leading-relaxed">
          <strong>Maestro only knows what you connect.</strong>{" "}
          Your connected sources are where every answer comes from. Connect
          email, calendar, or work email in <strong>More</strong>.
        </p>
        <div className="flex items-center gap-2 mt-2.5 flex-wrap">
          <Button
            size="sm"
            variant="default"
            className="h-7 text-xs"
            onClick={handleConnect}
            disabled={connecting}
          >
            {connecting ? (
              <Loader2 className="size-3 animate-spin mr-1.5" />
            ) : (
              <Link2 className="size-3 mr-1.5" />
            )}
            Connect a source
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="h-7 text-xs text-amber-800 dark:text-amber-300 hover:text-amber-900 dark:hover:text-amber-200"
            onClick={handleGotIt}
          >
            Got it
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="h-7 text-xs text-amber-700/80 dark:text-amber-400/80 hover:text-amber-800 dark:hover:text-amber-300"
            onClick={handleSnooze}
          >
            Snooze 3 days
          </Button>
        </div>
      </div>
      <button
        type="button"
        onClick={handleGotIt}
        className="shrink-0 text-amber-700/60 dark:text-amber-400/60 hover:text-amber-900 dark:hover:text-amber-200 transition-colors"
        aria-label="Dismiss"
      >
        <X className="size-4" />
      </button>
    </div>
  );
}

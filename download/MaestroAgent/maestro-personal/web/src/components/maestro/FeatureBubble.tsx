"use client";

/**
 * FeatureBubble — a small, dismissible, rotating tip bubble on the Today surface.
 *
 * Design intent: feels like a helpful coach, not a notification.
 *   - Shows one tip at a time, rotating every 15 seconds.
 *   - User can dismiss it (persisted in localStorage as
 *     `maestro.feature_bubble_dismissed` = "1").
 *   - User can replay it from More → Settings (which clears the flag).
 *   - Visually polished: rounded, subtle shadow, not intrusive.
 *
 * P40 (world-class Today surface): the bubble surfaces helpful capabilities
 * the user may not know about — evidenced answers, connectors, provenance,
 * correction, deltas, and the "one thing that needs attention" promise.
 */

import { useCallback, useEffect, useState } from "react";
import { Lightbulb, X } from "lucide-react";
import { cn } from "@/lib/utils";

const DISMISSED_KEY = "maestro.feature_bubble_dismissed";
const ROTATE_MS = 15_000;

export const FEATURE_BUBBLE_TIPS: readonly string[] = [
  "💡 Ask Maestro 'What did I promise Maria?' to get an evidenced answer with source links",
  "💡 Connect your email in More → Connectors to auto-ingest commitments",
  "💡 Click any commitment to see its provenance — the exact email, the exact sentence",
  "💡 Correct a mistake: dismiss any commitment and Maestro won't show it again",
  "💡 Ask 'What changed since Tuesday?' to see your commitment deltas",
  "💡 The Today view surfaces the one thing that needs your attention right now",
] as const;

export function isFeatureBubbleDismissed(): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(DISMISSED_KEY) === "1";
}

export function replayFeatureBubble(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(DISMISSED_KEY);
  // Emit a storage-like event so any mounted FeatureBubble can react even
  // though localStorage writes don't fire 'storage' in the same tab.
  window.dispatchEvent(new Event("maestro:feature-bubble-replay"));
}

export function FeatureBubble() {
  const [mounted, setMounted] = useState(false);
  const [dismissed, setDismissed] = useState(true);
  const [index, setIndex] = useState(0);
  const [visible, setVisible] = useState(false);

  // Sync dismissed state from localStorage (and listen for replay events
  // fired by the Settings screen).
  useEffect(() => {
    setMounted(true);
    const sync = () => {
      setDismissed(isFeatureBubbleDismissed());
    };
    sync();
    window.addEventListener("maestro:feature-bubble-replay", sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener("maestro:feature-bubble-replay", sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  // Pick a pseudo-random starting tip so returning users don't always see
  // tip #1. Deterministic per-session (no hydration mismatch because this
  // runs after mount).
  useEffect(() => {
    if (!mounted || dismissed) return;
    setIndex(Math.floor(Math.random() * FEATURE_BUBBLE_TIPS.length));
  }, [mounted, dismissed]);

  // Rotate the tip every ROTATE_MS. Pause rotation when the tab is hidden
  // (don't burn cycles / don't surprise the user on tab-switch-back).
  useEffect(() => {
    if (!mounted || dismissed) return;
    setVisible(true);
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        setIndex((i) => (i + 1) % FEATURE_BUBBLE_TIPS.length);
      }
    }, ROTATE_MS);
    return () => window.clearInterval(id);
  }, [mounted, dismissed]);

  const handleDismiss = useCallback(() => {
    // Smooth exit: hide first, then persist after the transition.
    setVisible(false);
    window.setTimeout(() => {
      if (typeof window !== "undefined") {
        window.localStorage.setItem(DISMISSED_KEY, "1");
      }
      setDismissed(true);
    }, 180);
  }, []);

  // SSR / pre-mount: render nothing to avoid hydration mismatch.
  if (!mounted || dismissed) return null;

  const tip = FEATURE_BUBBLE_TIPS[index] ?? FEATURE_BUBBLE_TIPS[0];

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label="Maestro tip"
      className={cn(
        "transition-all duration-200 ease-out",
        visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-1 pointer-events-none",
      )}
    >
      <div
        className={cn(
          "group relative flex items-start gap-3 rounded-2xl border border-border/60",
          "bg-card/95 backdrop-blur-sm px-4 py-3 shadow-sm",
          "hover:shadow-md transition-shadow",
        )}
      >
        <div
          className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary"
          aria-hidden
        >
          <Lightbulb className="size-4" />
        </div>

        <p className="flex-1 text-sm leading-relaxed text-foreground/90">
          {tip}
        </p>

        <button
          type="button"
          onClick={handleDismiss}
          aria-label="Dismiss tip"
          className={cn(
            "shrink-0 rounded-md p-1 text-muted-foreground/60",
            "hover:bg-accent hover:text-foreground transition-colors",
            "focus:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          )}
        >
          <X className="size-4" />
        </button>

        {/* Subtle progress indicator (rotates every ROTATE_MS) */}
        <span
          aria-hidden
          className="absolute bottom-0 left-4 right-4 h-0.5 overflow-hidden rounded-full bg-muted"
        >
          <span
            key={index}
            className="block h-full bg-primary/40 origin-left"
            style={{ animation: `feature-bubble-progress ${ROTATE_MS}ms linear forwards` }}
          />
        </span>
      </div>

      <style jsx>{`
        @keyframes feature-bubble-progress {
          from { transform: scaleX(0); }
          to { transform: scaleX(1); }
        }
      `}</style>
    </div>
  );
}

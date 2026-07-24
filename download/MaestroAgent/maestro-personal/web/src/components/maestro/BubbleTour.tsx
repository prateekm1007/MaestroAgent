"use client";

import { useEffect, useState } from "react";
import { CheckCircle, MoreHorizontal, Search, Sun, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { View } from "@/components/maestro/AppShell";

/**
 * BubbleTour — coach-mark tour for the 4-tab IA.
 *
 * Auditor (2026-07-24) IA redesign: trust/data disclosure first. The tour
 * walks the user through the 4 tabs in order:
 *   1. Today  — your morning view (The Moment, What Changed, upcoming meetings)
 *   2. Ask    — question your data, every answer cites its source
 *   3. Commitments — every promise you've made, drill down to source messages
 *   4. More   — connectors (where your data comes from), sources, agent controls
 *
 * Persist spec:
 *   - localStorage key "maestro.tour_dismissed" === "1" → never show again
 *   - The "Replay tour" button in More calls replayTour() which clears the flag
 *     and re-triggers the tour on the next render.
 *
 * Trust-first: step 4 (More) explicitly tells the user that Maestro only knows
 * what they connect — the connectors banner on Today reinforces this, and the
 * tour's last step points them at More→Connectors to actually connect.
 *
 * The tour auto-advances on click-anywhere or the Next button. Each step
 * is anchored to the corresponding nav tab (aria-label match) so it visually
 * points at the tab it's describing.
 */

const TOUR_DISMISSED_KEY = "maestro.tour_dismissed";
const TOUR_REPLAY_FLAG = "maestro.tour_replay"; // set by replayTour()

type TourStep = {
  view: View;
  title: string;
  body: string;
  cta: string;
};

const STEPS: TourStep[] = [
  {
    view: "today",
    title: "Today — your morning view",
    body:
      "Every morning, this is what matters now: the one Moment that needs you, " +
      "what changed since you last looked, and your next meeting. The folded " +
      "Prepare and Agent outputs live here as parts of your day — not as " +
      "orphaned tabs.",
    cta: "Next: Ask",
  },
  {
    view: "ask",
    title: "Ask — question your data",
    body:
      "Ask any question about what you've promised, to whom, by when. Every " +
      "answer cites the exact source sentence, entity, and timestamp. Try " +
      "\"prepare me for my 3pm\" — that intent used to be the Prepare tab, " +
      "now it's just a question.",
    cta: "Next: Commitments",
  },
  {
    view: "commitments",
    title: "Commitments — every promise you've made",
    body:
      "Every commitment Maestro detected, with state (active / completed / " +
      "cancelled / superseded). Click any commitment to drill down into the " +
      "source messages that produced it — that drill-down replaces the old " +
      "Inbox tab.",
    cta: "Next: More",
  },
  {
    view: "more",
    title: "More — connectors, sources, controls",
    body:
      "Maestro only knows what you connect. Connect email, calendar, or work " +
      "email here (one-click OAuth — no app passwords). Browse all sources, " +
      "tune agent controls, and adjust privacy/LLM settings. The connectors " +
      "banner on Today will hide once you connect your first source.",
    cta: "Got it",
  },
];

export function BubbleTour({
  currentView,
  onNavigate,
}: {
  currentView: View;
  onNavigate: (v: View) => void;
}) {
  const [step, setStep] = useState<number>(-1); // -1 = not showing
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    // Show tour on first run OR when replay flag is set
    const checkAndShow = () => {
      const dismissed = window.localStorage.getItem(TOUR_DISMISSED_KEY) === "1";
      const replay = window.localStorage.getItem(TOUR_REPLAY_FLAG) === "1";
      if (replay) {
        window.localStorage.removeItem(TOUR_REPLAY_FLAG);
        window.localStorage.removeItem(TOUR_DISMISSED_KEY);
        setStep(0);
        onNavigate("today");
      } else if (!dismissed) {
        setStep(0);
        onNavigate("today");
      }
    };
    checkAndShow();

    // Listen for in-page replay (from the "Replay tour" button in More)
    const onReplay = () => checkAndShow();
    window.addEventListener("maestro:replay-tour", onReplay);
    return () => {
      window.removeEventListener("maestro:replay-tour", onReplay);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Don't render until mounted (SSR safety + localStorage guard)
  if (!mounted) return null;
  if (step < 0 || step >= STEPS.length) return null;

  const current = STEPS[step];
  const isLast = step === STEPS.length - 1;

  function next() {
    if (isLast) {
      dismiss();
      return;
    }
    const nextStep = step + 1;
    setStep(nextStep);
    onNavigate(STEPS[nextStep].view);
  }

  function dismiss() {
    window.localStorage.setItem(TOUR_DISMISSED_KEY, "1");
    setStep(-1);
  }

  function skip() {
    dismiss();
  }

  // Anchor the bubble to the nav item matching the current step's view
  const navAnchor = current.view;

  return (
    <>
      {/* Backdrop — dim the page, click anywhere to advance */}
      <div
        className="fixed inset-0 z-40 bg-black/40 backdrop-blur-[1px]"
        onClick={next}
        aria-hidden
      />

      {/* Bubble — anchored near the corresponding nav item */}
      <div
        role="dialog"
        aria-label={`Tour step ${step + 1} of ${STEPS.length}: ${current.title}`}
        className="fixed z-50 left-1/2 -translate-x-1/2 top-20 sm:top-24 w-[calc(100vw-2rem)] max-w-md"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="rounded-lg border border-border bg-card shadow-xl">
          {/* Header — step indicator + close */}
          <div className="flex items-center justify-between px-4 pt-3 pb-2 border-b border-border/60">
            <div className="flex items-center gap-1.5">
              {STEPS.map((_, i) => (
                <span
                  key={i}
                  className={cn(
                    "h-1.5 rounded-full transition-all",
                    i === step ? "w-6 bg-primary" : "w-1.5 bg-muted-foreground/30",
                  )}
                  aria-hidden
                />
              ))}
            </div>
            <button
              type="button"
              onClick={skip}
              className="text-muted-foreground hover:text-foreground transition-colors"
              aria-label="Skip tour"
            >
              <X className="size-4" />
            </button>
          </div>

          {/* Body */}
          <div className="px-4 py-4 space-y-3">
            <div className="flex items-center gap-2">
              <StepIcon view={navAnchor} />
              <h3 className="text-sm font-semibold">{current.title}</h3>
            </div>
            <p className="text-sm text-muted-foreground leading-relaxed">
              {current.body}
            </p>
          </div>

          {/* Footer — Skip + Next/Finish */}
          <div className="flex items-center justify-between px-4 py-3 border-t border-border/60 bg-muted/20">
            <button
              type="button"
              onClick={skip}
              className="text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              Skip tour
            </button>
            <Button size="sm" onClick={next}>
              {current.cta}
            </Button>
          </div>
        </div>
      </div>
    </>
  );
}

function StepIcon({ view }: { view: View }) {
  const Icon =
    view === "today" ? Sun :
    view === "ask" ? Search :
    view === "commitments" ? CheckCircle :
    view === "more" ? MoreHorizontal :
    Sun;
  return <Icon className="size-4 text-primary" />;
}

/**
 * replayTour — called by the "Replay tour" button in More.
 * Sets a flag that the BubbleTour picks up on its next mount, then clears
 * the dismissed flag so the tour actually fires.
 *
 * We don't directly trigger the tour from here because the BubbleTour is
 * always mounted (it lives inside Shell), so we just need to flip its
 * state. The flag pattern is used so the same code path works on page
 * reload (the flag persists for one render cycle, then is consumed).
 *
 * To make this work in-page without a reload, we dispatch a custom event
 * that the BubbleTour listens for.
 */
export function replayTour() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOUR_DISMISSED_KEY);
  window.localStorage.setItem(TOUR_REPLAY_FLAG, "1");
  // Dispatch a custom event so an already-mounted BubbleTour picks it up
  // without requiring a page reload.
  window.dispatchEvent(new CustomEvent("maestro:replay-tour"));
}

"use client";

/**
 * Onboarding — 3-step first-visit flow (ported from mobile OnboardingScreen).
 *
 * Persists to localStorage key "maestro.onboarded" === "1".
 * Shown before Login if the flag is not set.
 *
 * Steps:
 *   1. Maestro remembers what you promised
 *   2. Ask Maestro anything (with sources)
 *   3. Trusted Silence (impossible questions return "no data found")
 */

import { useState } from "react";
import { Brain, Search, ShieldCheck, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

const ONBOARDED_KEY = "maestro.onboarded";

export function isOnboarded(): boolean {
  if (typeof window === "undefined") return true; // SSR — assume onboarded
  return window.localStorage.getItem(ONBOARDED_KEY) === "1";
}

export function completeOnboarding(): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(ONBOARDED_KEY, "1");
}

const STEPS = [
  {
    icon: Sparkles,
    title: "Maestro remembers what you promised.",
    body: "Every commitment you make — in email, Slack, or meetings — becomes a signal. Maestro surfaces the one thing that needs your attention right now.",
    cta: "Next",
  },
  {
    icon: Search,
    title: "Ask Maestro anything.",
    body: "Every answer cites the exact source sentence, entity, and timestamp. Not a hallucination — your own evidence, retrieved and verified.",
    cta: "Next",
  },
  {
    icon: ShieldCheck,
    title: "Trusted Silence.",
    body: "When Maestro does not know, it says so. Impossible questions return \"no data found\" instead of hallucinating — every answer is grounded in your own evidence.",
    cta: "Get Started",
  },
];

export function Onboarding({ onDone }: { onDone: () => void }) {
  const [step, setStep] = useState(0);
  const current = STEPS[step];
  const isLast = step === STEPS.length - 1;
  const Icon = current.icon;

  function handleNext() {
    if (isLast) {
      completeOnboarding();
      onDone();
    } else {
      setStep((s) => s + 1);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-10 bg-background">
      <div className="w-full max-w-md space-y-8">
        {/* Progress dots */}
        <div className="flex items-center justify-center gap-2" aria-label="Onboarding progress">
          {STEPS.map((_, i) => (
            <span
              key={i}
              aria-label={`Step ${i + 1} of ${STEPS.length}${i === step ? ", current" : ""}`}
              className={cn(
                "h-1.5 rounded-full transition-all",
                i === step ? "w-8 bg-primary" : "w-2 bg-muted-foreground/30",
              )}
            />
          ))}
        </div>

        {/* Icon */}
        <div className="flex items-center justify-center">
          <div
            className="size-20 rounded-full bg-primary/10 border border-primary/30 flex items-center justify-center"
            aria-hidden
          >
            <Icon className="size-9 text-primary" />
          </div>
        </div>

        {/* Card with title + body */}
        <Card className="border-border/60 surface-elevated">
          <CardContent className="pt-8 pb-6 px-6 space-y-4 text-center">
            <h1 className="text-2xl font-semibold tracking-tight text-balance">
              {current.title}
            </h1>
            <p className="text-sm text-muted-foreground leading-relaxed">
              {current.body}
            </p>
          </CardContent>
        </Card>

        {/* CTA */}
        <Button
          size="lg"
          className="w-full h-12 text-base"
          onClick={handleNext}
        >
          {current.cta}
        </Button>

        {/* Skip link */}
        {!isLast && (
          <button
            type="button"
            onClick={() => {
              completeOnboarding();
              onDone();
            }}
            className="block w-full text-center text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            Skip onboarding
          </button>
        )}

        {/* Brand */}
        <div className="flex items-center justify-center gap-2 pt-4 text-xs text-muted-foreground/70">
          <Brain className="size-3.5" />
          <span>Maestro · Personal</span>
        </div>
      </div>
    </div>
  );
}

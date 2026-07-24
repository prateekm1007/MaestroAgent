"use client";

import { useEffect, useState } from "react";
import {
  Briefcase,
  MoreHorizontal,
  Settings as SettingsIcon,
  Sparkles,
  Inbox as InboxIcon,
  Users,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Connectors } from "@/components/maestro/Connectors";
import { Settings } from "@/components/maestro/Settings";
import { SyntheticInbox } from "@/components/maestro/SyntheticInbox";
import { Agents } from "@/components/maestro/Agents";
import { replayTour } from "@/components/maestro/BubbleTour";

/**
 * More — the 4th tab. Hosts the folded capabilities from the 7→4 IA collapse.
 *
 * Auditor (2026-07-24) IA redesign: every capability that used to have its
 * own top-level tab is reachable here. The fold map:
 *   - Connectors  ← was reachable only via Settings; now first-class in More
 *                   (this is where the one-click Yahoo/Microsoft OAuth cards land)
 *   - Settings    ← the old "More" tab content (LLM, privacy, notifications, audit log)
 *   - Sources     ← folded Inbox (SyntheticInbox — browse/receive demo emails)
 *   - Agents      ← folded Agents tab (commitment simulator + agent insights)
 *   - Replay tour ← re-runs the BubbleTour coach-mark flow
 *
 * The sub-section is controlled by AppShell via the `initialSection` prop so
 * deep links from the fold map (e.g. "inbox" → More→Sources) land on the
 * right section.
 */
export type MoreSection = "connectors" | "settings" | "sources" | "agents" | "tour";

const SECTIONS: { id: MoreSection; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { id: "connectors", label: "Connectors", icon: Briefcase },
  { id: "sources", label: "Browse all sources", icon: InboxIcon },
  { id: "agents", label: "Agent controls", icon: Users },
  { id: "settings", label: "Settings", icon: SettingsIcon },
];

export function More({
  initialSection,
  onSectionChange,
  onAsk,
}: {
  initialSection: MoreSection;
  onSectionChange: (s: MoreSection) => void;
  onAsk: (query: string) => void;
}) {
  const [section, setSection] = useState<MoreSection>(initialSection);

  // Sync internal state if the parent routes to a new section (fold redirect)
  useEffect(() => {
    setSection(initialSection);
  }, [initialSection]);

  function selectSection(s: MoreSection) {
    setSection(s);
    onSectionChange(s);
  }

  function handleReplayTour() {
    replayTour();
    // After replay, navigate back to Today so the tour starts from the first tab
    onAsk(""); // no-op; the tour fires on next render of any view
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold tracking-tight flex items-center gap-2">
          <MoreHorizontal className="size-5" />
          More
        </h2>
        <p className="text-sm text-muted-foreground mt-0.5">
          Connectors, sources, agent controls, and settings. Everything that
          isn&apos;t your daily ritual lives here.
        </p>
      </div>

      {/* Sub-section tabs */}
      <div className="flex flex-wrap gap-2 border-b border-border/60 pb-3">
        {SECTIONS.map((s) => {
          const Icon = s.icon;
          const active = section === s.id;
          return (
            <button
              key={s.id}
              type="button"
              onClick={() => selectSection(s.id)}
              className={cn(
                "inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                active
                  ? "bg-secondary text-secondary-foreground"
                  : "text-muted-foreground hover:text-foreground hover:bg-accent/50",
              )}
              aria-current={active ? "page" : undefined}
              aria-label={s.label}
            >
              <Icon className="size-4" />
              {s.label}
            </button>
          );
        })}
        <button
          type="button"
          onClick={handleReplayTour}
          className="inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-accent/50 transition-colors"
          aria-label="Replay tour"
        >
          <Sparkles className="size-4" />
          Replay tour
        </button>
      </div>

      {/* Section content */}
      <div>
        {section === "connectors" && <Connectors />}
        {section === "sources" && <SyntheticInbox />}
        {section === "agents" && <Agents />}
        {section === "settings" && <Settings />}
      </div>
    </div>
  );
}

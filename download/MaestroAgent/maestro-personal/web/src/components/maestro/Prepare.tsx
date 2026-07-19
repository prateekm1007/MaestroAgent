"use client";

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CalendarClock,
  HelpCircle,
  Loader2,
  Sparkles,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import {
  type PrepareItem,
  maestroApi,
} from "@/lib/maestro-api";

/**
 * Prepare — wires /api/prepare to a real UI surface.
 *
 * P11 (wiring): the Prepare endpoint existed, was tested, but was never
 * called from the web frontend. This component is the wiring.
 * P12 (product-thesis): "tells you what to do next" is one of the three
 * thesis pillars. Pre-meeting preparation is the most actionable surface.
 *
 * Caller: page.tsx (included in the nav as "Prepare" tab)
 */

export function Prepare() {
  const { toast } = useToast();
  const [items, setItems] = useState<PrepareItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const { data } = await maestroApi.getPrepare();
        if (!alive) return;
        setItems(data);
      } catch {
        // silent — prepare is non-critical
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <div>
          <h2 className="text-xl font-semibold tracking-tight">Prepare</h2>
          <p className="text-sm text-muted-foreground mt-0.5">
            What you should know before your next meeting with each person.
          </p>
        </div>
        <Card className="border-border/60">
          <CardContent className="pt-6">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              Loading preparation intelligence…
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!items || items.length === 0) {
    return (
      <div className="space-y-6">
        <div>
          <h2 className="text-xl font-semibold tracking-tight">Prepare</h2>
          <p className="text-sm text-muted-foreground mt-0.5">
            What you should know before your next meeting with each person.
          </p>
        </div>
        <Card className="border-border/60">
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">
              No upcoming meetings or active situations to prepare for.
              Connect Google Calendar to get pre-meeting intelligence.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">Prepare</h2>
        <p className="text-sm text-muted-foreground mt-0.5">
          What you should know before your next meeting with each person.
        </p>
      </div>

      <div className="space-y-4">
        {items.map((item) => (
          <PrepareCard key={item.situation_id} item={item} />
        ))}
      </div>
    </div>
  );
}

function PrepareCard({ item }: { item: PrepareItem }) {
  const forgotten = item.the_forgotten || "";
  const openQ = item.the_open_question || "";
  const contradiction = item.the_contradiction || "";
  const prepPoints = item.prep_points || [];

  return (
    <Card className="border-border/60">
      <CardContent className="pt-6 space-y-4">
        {/* Entity header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="size-4 text-primary" />
            <h3 className="text-sm font-semibold">{item.entity}</h3>
          </div>
          <span className="text-xs text-muted-foreground">{item.meeting_context?.slice(0, 60)}</span>
        </div>

        {/* The three prep items */}
        <div className="space-y-3">
          {forgotten && (
            <div className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/[0.06] p-2.5">
              <CalendarClock className="size-3.5 text-amber-500 mt-0.5 shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">Forgotten commitment</div>
                <div className="text-sm text-foreground mt-0.5">{forgotten}</div>
              </div>
            </div>
          )}

          {openQ && (
            <div className="flex items-start gap-2 rounded-md border border-sky-500/30 bg-sky-500/[0.06] p-2.5">
              <HelpCircle className="size-3.5 text-sky-500 mt-0.5 shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">Open question</div>
                <div className="text-sm text-foreground mt-0.5">{openQ}</div>
              </div>
            </div>
          )}

          {contradiction && (
            <div className="flex items-start gap-2 rounded-md border border-rose-500/30 bg-rose-500/[0.06] p-2.5">
              <AlertTriangle className="size-3.5 text-rose-500 mt-0.5 shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">Contradiction</div>
                <div className="text-sm text-foreground mt-0.5">{contradiction}</div>
              </div>
            </div>
          )}

          {prepPoints.length > 0 && (
            <div className="space-y-1">
              <div className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">Prep points</div>
              <ul className="space-y-1">
                {prepPoints.map((p, i) => (
                  <li key={i} className="text-xs text-foreground/80 rounded-md border border-border/60 bg-muted/20 p-2">
                    {p}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {!forgotten && !openQ && !contradiction && prepPoints.length === 0 && (
            <p className="text-xs text-muted-foreground">No specific prep items for this entity.</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

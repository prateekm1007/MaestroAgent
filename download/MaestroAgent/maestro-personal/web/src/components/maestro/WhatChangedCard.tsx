"use client";

import { useEffect, useState } from "react";
import { Loader2, TrendingUp } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  type WhatChangedItem,
  maestroApi,
} from "@/lib/maestro-api";

/**
 * WhatChangedCard — wires /api/what-changed to the Dashboard.
 *
 * P11 (wiring): the endpoint existed, returned real data, but was never
 * called from the web frontend. The Dashboard had a WhatChangedCard that
 * used a DIFFERENT endpoint (/api/what-changed/the-shifts). This card
 * uses the direct /api/what-changed endpoint which returns per-signal
 * deltas with entity, text, and is_meaningful flags.
 *
 * P12 (product-thesis): "surfaces what changed" is one of the three
 * thesis pillars. This is the surface that answers "what happened while
 * I was away?"
 *
 * Caller: Dashboard.tsx (included in the Dashboard render)
 */
export function WhatChangedCard() {
  const [items, setItems] = useState<WhatChangedItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const { data } = await maestroApi.getWhatChanged();
        if (!alive) return;
        setItems(data);
      } catch {
        // silent — what-changed is non-critical
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
      <Card className="border-border/60">
        <CardContent className="pt-6">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            Loading what changed…
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!items || items.length === 0) {
    return null; // hide the card when there's nothing to show
  }

  return (
    <Card className="border-border/60">
      <CardContent className="pt-6 space-y-3">
        <div className="flex items-center gap-2">
          <TrendingUp className="size-4 text-primary" />
          <h3 className="text-sm font-semibold">What Changed</h3>
          <Badge variant="secondary" className="text-[10px]">{items.length}</Badge>
        </div>
        <p className="text-xs text-muted-foreground">
          Meaningful deltas since your last visit — new commitments, meeting changes, and deadline shifts.
        </p>
        <div className="space-y-2">
          {items.map((item, i) => (
            <div
              key={i}
              className={cn(
                "flex items-start gap-2 rounded-md border p-2.5",
                item.is_meaningful
                  ? "border-primary/30 bg-primary/[0.04]"
                  : "border-border/60 bg-muted/20",
              )}
            >
              <div className="flex-1 min-w-0">
                <div className="text-sm text-foreground truncate">{item.text}</div>
                <div className="text-xs text-muted-foreground mt-0.5">
                  <span className="capitalize">{item.entity}</span>
                  {item.type && <span> · {item.type.replace(/_/g, " ")}</span>}
                </div>
              </div>
              {item.is_meaningful && (
                <Badge variant="outline" className="text-[10px] text-primary border-primary/30">
                  meaningful
                </Badge>
              )}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

"use client";

import { useEffect, useState } from "react";
import { AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

const DEMO_EMAIL_KEY = "maestro.user_email";

export function setUserEmail(email: string) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(DEMO_EMAIL_KEY, email);
}

// Must mirror the backend `_ALLOWED_DEMO_IDENTITIES` set in
// src/maestro_personal_shell/routers/auth.py — these are the only
// identities the shared demo password is allowed to mint, and all of
// them read demo-seeded data (seeded by demo_seeder.py for both
// 'bootstrap' and 'default@personal.local'). The substring check on
// "bootstrap" / "demo" alone missed 'default@personal.local', causing
// the demo banner to be hidden when a user logged in with that email —
// so the Today tab showed Alex Chen / Jamie Lee demo signals with no
// "DEMO — sample data" label. Bug surfaced via user screenshot 2026-07-28.
const DEMO_IDENTITIES = new Set<string>([
  "default@personal.local",
  "bootstrap",
  "bootstrap@maestro.local",
]);

export function isDemoAccount(): boolean {
  if (typeof window === "undefined") return false;
  const email = (window.localStorage.getItem(DEMO_EMAIL_KEY) || "").trim().toLowerCase();
  if (!email) return false;
  if (DEMO_IDENTITIES.has(email)) return true;
  return email.includes("bootstrap") || email.includes("demo");
}

export function DemoBanner() {
  const [show, setShow] = useState(false);

  useEffect(() => {
    setShow(isDemoAccount());
  }, []);

  if (!show) return null;

  return (
    <div className=" border /40  dark:bg-amber-950/30 px-4 py-2 flex items-center gap-2">
      <AlertCircle className="size-4  dark:text-amber-400 shrink-0" />
      <span className="text-xs  dark:text-amber-100 font-medium">
        DEMO — sample data. This account shows synthetic fixtures for evaluation.
        Register a new account and connect your email to see your real commitments.
      </span>
    </div>
  );
}

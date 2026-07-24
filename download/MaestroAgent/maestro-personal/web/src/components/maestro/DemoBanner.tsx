"use client";

import { useEffect, useState } from "react";
import { AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

const DEMO_EMAIL_KEY = "maestro.user_email";

export function setUserEmail(email: string) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(DEMO_EMAIL_KEY, email);
}

export function isDemoAccount(): boolean {
  if (typeof window === "undefined") return false;
  const email = window.localStorage.getItem(DEMO_EMAIL_KEY) || "";
  return email.includes("bootstrap") || email.includes("demo");
}

export function DemoBanner() {
  const [show, setShow] = useState(false);

  useEffect(() => {
    setShow(isDemoAccount());
  }, []);

  if (!show) return null;

  return (
    <div className="rounded-md border border-amber-500/40 bg-amber-50 dark:bg-amber-950/30 px-4 py-2 flex items-center gap-2">
      <AlertCircle className="size-4 text-amber-600 dark:text-amber-400 shrink-0" />
      <span className="text-xs text-amber-900 dark:text-amber-100 font-medium">
        DEMO — sample data. This account shows synthetic fixtures for evaluation.
        Register a new account and connect your email to see your real commitments.
      </span>
    </div>
  );
}

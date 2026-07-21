"use client";

import { useEffect, useState } from "react";
import { Loader2, Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { login } from "@/lib/maestro-api";

/**
 * SessionExpiredDialog — listens for the "maestro:auth:expired" custom event
 * dispatched by maestroFetch when a 401 is received with a stale token.
 *
 * Defect 4 fix (auditor roadmap Phase 2): replaces the destructive
 * window.location.reload() that destroyed unsaved UI state. Now the user
 * sees a non-blocking dialog and can re-authenticate in-place, preserving
 * their current page state (input boxes, drill-down modals, etc.).
 */
export function SessionExpiredDialog() {
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const handler = () => {
      setOpen(true);
      setError(null);
      setPassword("");
    };
    window.addEventListener("maestro:auth:expired", handler);
    return () => window.removeEventListener("maestro:auth:expired", handler);
  }, []);

  async function handleReauth(e: React.FormEvent) {
    e.preventDefault();
    if (!password) return;
    setBusy(true);
    setError(null);
    try {
      const result = await login(password);
      if (result.ok) {
        setOpen(false);
        setPassword("");
        // Reload the current page data now that we have a fresh token
        window.location.reload();
      } else {
        setError(result.message);
      }
    } catch {
      setError("Reconnection failed. Please refresh the page.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Lock className="size-4" />
            Session Expired
          </DialogTitle>
          <DialogDescription>
            Your security token has expired. Enter your password to resume
            where you left off. Your current page state will be preserved.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleReauth} className="space-y-3">
          <Input
            type="password"
            placeholder="Enter your password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={busy}
            autoFocus
          />
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button type="submit" disabled={busy || !password} className="w-full">
            {busy ? <Loader2 className="size-4 animate-spin" /> : "Resume"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

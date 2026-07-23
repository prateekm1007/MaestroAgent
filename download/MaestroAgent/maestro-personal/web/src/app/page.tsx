import { AppShell, ShellSkeleton } from "@/components/maestro/AppShell";

/**
 * Home — SSR first-paint page (server component).
 *
 * Trust gap #1 + first-impression fix:
 * Previously this page was "use client" and rendered "Loading…" on the
 * server — a blank slogan shell until JS hydrated. Now the server renders
 * a meaningful shell (brand + nav + loading content area) via ShellSkeleton,
 * and the client hydrates into AppShell which swaps in the real content
 * (Login / Onboarding / Dashboard) after localStorage is read.
 *
 * The server renders ShellSkeleton; the client renders AppShell which
 * starts with ShellSkeleton (same markup → no hydration mismatch) and
 * then transitions to the authed/unauthed state.
 */
export default function Home() {
  return <AppShell />;
}

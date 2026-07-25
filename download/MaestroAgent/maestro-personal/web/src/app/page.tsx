import { AppShell } from "@/components/maestro/AppShell";

/**
 * Home — SSR first-paint page (server component).
 *
 * K3-UI-001 fix (2026-07-25): removed the dead ShellSkeleton import and the
 * misleading comment that claimed the server renders ShellSkeleton. The
 * server actually renders <AppShell /> (a client component), which means the
 * first paint is whatever AppShell emits on the server — typically a loading
 * skeleton via React Suspense or a static shell. The old comment described a
 * refactor that was never completed (or was reverted).
 *
 * Hydration safety: AppShell reads localStorage only inside useEffect (not
 * during render), so the first client render matches the server HTML. No
 * hydration mismatch.
 */
export default function Home() {
  return <AppShell />;
}

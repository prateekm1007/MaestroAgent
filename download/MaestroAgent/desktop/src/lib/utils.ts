/**
 * lib/utils — shared utility functions for the frontend.
 *
 * Kept intentionally small. Most logic lives in the store or hooks.
 */

/** Classnames helper — conditional className joiner. */
export function cn(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

/** Format a number as USD. */
export function formatUSD(n: number): string {
  return `$${n.toFixed(4)}`;
}

/** Format bytes as KB/MB. */
export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

/** Truncate a string to `max` chars with an ellipsis. */
export function truncate(s: string, max: number): string {
  return s.length > max ? s.slice(0, max - 1) + "…" : s;
}

/** Format an ISO timestamp as HH:MM:SS.mmm. */
export function formatTime(ts: string): string {
  try {
    const d = new Date(ts);
    return (
      String(d.getHours()).padStart(2, "0") + ":" +
      String(d.getMinutes()).padStart(2, "0") + ":" +
      String(d.getSeconds()).padStart(2, "0") + "." +
      String(d.getMilliseconds()).padStart(3, "0")
    );
  } catch {
    return ts.slice(11, 23);
  }
}

/** Sleep for `ms` milliseconds. */
export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Maestro brand mark — Bumble yellow circle with lightning bolt. */

import { Zap } from "lucide-react";

export function MaestroMark({ size = 32 }: { size?: number }) {
  return (
    <div
      className="relative rounded-full bg-primary flex items-center justify-center shadow shadow-primary/30"
      style={{ width: size, height: size }}
    >
      <Zap
        className="text-primary-foreground"
        style={{ width: size * 0.5, height: size * 0.5 }}
        fill="currentColor"
      />
    </div>
  );
}

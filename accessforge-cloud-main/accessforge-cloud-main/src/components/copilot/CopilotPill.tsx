import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * The product's pill convention, unchanged: rounded-full, 1px border, single
 * line, border-first for neutral states.  A tinted fill appears only when the
 * pill carries a real status meaning.
 */
export type CopilotPillTone = "neutral" | "heavy" | "resolved" | "unresolved" | "spark";

const toneClasses: Record<CopilotPillTone, string> = {
  neutral: "border-border text-fg-secondary",
  heavy: "border-primary/45 bg-primary/15 text-primary",
  resolved: "border-copilot-resolved/45 bg-copilot-resolved/15 text-copilot-resolved",
  unresolved: "border-destructive/45 bg-destructive/15 text-status-danger-foreground",
  spark: "border-copilot-spark/45 bg-copilot-spark/15 text-copilot-spark",
};

export function CopilotPill({
  tone = "neutral",
  mono = false,
  className,
  children,
}: {
  tone?: CopilotPillTone;
  /** Raw operational tokens read in the monospace face. */
  mono?: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex max-w-full items-center gap-1 truncate rounded-full border px-2.5 py-1 text-[10.5px] leading-none font-medium",
        mono && "font-mono tracking-tight",
        toneClasses[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

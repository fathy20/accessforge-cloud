import { forwardRef } from "react";
import { Sparkles } from "lucide-react";

import { useI18n } from "@/lib/i18n";
import { CopilotPill } from "./CopilotPill";

/**
 * Floating entry point, anchored to the bottom inline-end of the viewport and
 * persistent across pages.  The amber-gold spark reads as "AI" the way LEON's
 * own assistant entry point does, without borrowing coral (primary action) or
 * LEON's exact icon.
 */
export const CopilotLauncher = forwardRef<
  HTMLButtonElement,
  { expanded: boolean; onClick: () => void }
>(function CopilotLauncher({ expanded, onClick }, ref) {
  const { t } = useI18n();

  return (
    <button
      ref={ref}
      type="button"
      onClick={onClick}
      aria-expanded={expanded}
      aria-haspopup="dialog"
      className="fixed bottom-4 end-4 z-shell-overlay inline-flex cursor-pointer items-center gap-2 rounded-full border border-border bg-card py-2 ps-3 pe-2.5 shadow-surface-overlay transition-colors hover:bg-interactive-hover"
    >
      <Sparkles className="size-4 shrink-0 text-copilot-spark" aria-hidden="true" />
      <span className="text-label font-semibold whitespace-nowrap text-fg-primary">
        {t("copilot.launcher")}
      </span>
      <CopilotPill tone="spark">{t("copilot.beta")}</CopilotPill>
    </button>
  );
});

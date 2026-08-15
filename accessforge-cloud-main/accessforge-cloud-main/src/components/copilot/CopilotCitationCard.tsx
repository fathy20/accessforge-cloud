import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { CopilotPill, type CopilotPillTone } from "./CopilotPill";
import type { CopilotCitation, CopilotCitationTone } from "./types";

/**
 * The one genuinely new visual element in this feature: an elevated card with a
 * colored leading-edge bar, read like a flight-progress strip.  It stays inside
 * the assistant panel and is not propagated to the rest of the toolkit.
 *
 * The edge uses border-inline-start rather than border-left so it leads the card
 * in both the product's Arabic (RTL) and English (LTR) directions.
 */
const edgeClasses: Record<CopilotCitationTone, string> = {
  heavy: "border-s-primary",
  resolved: "border-s-copilot-resolved",
  unresolved: "border-s-destructive/70",
};

const tonePill: Record<CopilotCitationTone, CopilotPillTone> = {
  heavy: "heavy",
  resolved: "resolved",
  unresolved: "unresolved",
};

const toneLabelKey = {
  heavy: "copilot.tone.heavy",
  resolved: "copilot.tone.resolved",
  unresolved: "copilot.tone.unresolved",
} as const;

export function CopilotCitationCard({ citation }: { citation: CopilotCitation }) {
  const { t } = useI18n();

  return (
    <div
      className={cn(
        "mt-2.5 rounded-md border border-border border-s-[3px] bg-surface-overlay/60 p-3",
        edgeClasses[citation.tone],
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-label font-semibold text-fg-primary">{citation.headline}</p>
        <CopilotPill tone={tonePill[citation.tone]}>{t(toneLabelKey[citation.tone])}</CopilotPill>
      </div>

      {citation.facts.length > 0 && (
        <dl className="mt-2.5 flex flex-wrap gap-1.5">
          {citation.facts.map((fact) => (
            <div key={`${fact.label}-${fact.value}`} className="contents">
              <dt className="sr-only">{fact.label}</dt>
              <dd>
                <CopilotPill mono={fact.raw}>
                  <span className="font-sans text-fg-muted">{fact.label}</span>
                  <span className={cn("text-fg-primary", fact.raw && "font-mono")}>
                    {fact.value}
                  </span>
                </CopilotPill>
              </dd>
            </div>
          ))}
        </dl>
      )}

      {/*
        Mandatory on every data-backed answer: exactly what was queried, so a
        planner can verify the claim in LEON without taking our word for it.
      */}
      <p className="mt-2.5 border-t border-border/70 pt-2 font-mono text-[10.5px] leading-relaxed break-words text-fg-disabled">
        <span className="sr-only">{t("copilot.source_label")}: </span>
        {citation.source}
      </p>
    </div>
  );
}

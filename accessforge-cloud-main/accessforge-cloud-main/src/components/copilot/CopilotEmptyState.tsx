import { useI18n } from "@/lib/i18n";
import type { CopilotQuickTopic } from "./types";

/**
 * Shown before the first question.
 *
 * The three suggestion cards reuse the SAME quick-topic objects the composer
 * chips use, so a card and its chip can never send different questions.
 */

const TILE_TONE: Record<string, string> = {
  "crew-hours": "--copilot-accent-1",
  "heavy-status": "--copilot-accent-2",
  rosters: "--copilot-accent-3",
};

const TILE_MONOGRAM: Record<string, string> = {
  "crew-hours": "CH",
  "heavy-status": "HS",
  rosters: "RO",
};

const SUB_KEY = {
  "crew-hours": "copilot.suggest.crew_hours_sub",
  "heavy-status": "copilot.suggest.heavy_status_sub",
  rosters: "copilot.suggest.rosters_sub",
} as const;

export function CopilotEmptyState({
  firstName,
  quickTopics,
  onAsk,
}: {
  firstName: string;
  quickTopics: CopilotQuickTopic[];
  onAsk: (question: string) => void;
}) {
  const { t } = useI18n();

  return (
    <div className="flex h-full flex-col justify-center gap-[26px] px-1">
      <div className="copilot-rise" style={{ animationDelay: "0ms" }}>
        <h3
          className="copilot-greet text-[30px] font-bold leading-tight"
          style={{ fontFamily: "var(--font-display)" }}
        >
          {t("copilot.greeting", { name: firstName })}
        </h3>
        <p
          className="mt-1 text-[22px] font-semibold leading-tight"
          style={{ fontFamily: "var(--font-display)", color: "var(--copilot-faint)" }}
        >
          {t("copilot.greeting_sub")}
        </p>
      </div>

      <ul
        aria-label={t("copilot.suggestions_label")}
        className="copilot-rise flex flex-col gap-2.5"
        style={{ animationDelay: "70ms" }}
      >
        {quickTopics.map((topic, i) => {
          const tone = TILE_TONE[topic.id] ?? "--copilot-accent-1";
          const subKey = SUB_KEY[topic.id as keyof typeof SUB_KEY];
          return (
            <li key={topic.id}>
              <button
                type="button"
                onClick={() => onAsk(topic.question)}
                style={{ animationDelay: `${140 + i * 70}ms` }}
                className="copilot-suggest flex w-full items-center gap-3 rounded-[14px] border p-3 text-start focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--copilot-accent-1)]"
              >
                <span
                  aria-hidden="true"
                  className="grid size-[34px] shrink-0 place-items-center rounded-[10px] text-[13px] font-semibold"
                  style={{
                    fontFamily: "var(--font-display)",
                    color: `var(${tone})`,
                    background: `color-mix(in oklab, var(${tone}) 14%, transparent)`,
                  }}
                >
                  {TILE_MONOGRAM[topic.id] ??
                    topic.id.split("-").map((w) => w[0]).join("").slice(0, 2).toUpperCase()}
                </span>
                <span className="min-w-0">
                  <span
                    className="block text-[13.5px] font-semibold"
                    style={{ color: "var(--copilot-ink)" }}
                  >
                    {topic.label}
                  </span>
                  {subKey && (
                    <span
                      className="mt-0.5 block text-[12px]"
                      style={{ color: "var(--copilot-muted)" }}
                    >
                      {t(subKey)}
                    </span>
                  )}
                </span>
              </button>
            </li>
          );
        })}
      </ul>

      <p
        className="copilot-rise text-center text-[11.5px]"
        style={{ color: "var(--copilot-faint)", animationDelay: "350ms" }}
      >
        {t("copilot.footnote")}
      </p>
    </div>
  );
}

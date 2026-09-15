/**
 * Light / System / Dark as a segmented radiogroup.
 *
 * Three states rather than a switch, because "system" is a real preference that
 * a two-way toggle silently discards.
 *
 * Used both on the public landing page and inside the authenticated shell, so
 * labels come from the dictionary — the app runs in Arabic and hardcoded
 * English here would be the only untranslated control in the topbar.
 */

import { Monitor, Moon, Sun } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import type { DictKey } from "@/lib/i18n";
import { useTheme, type ThemePreference } from "@/lib/theme";

const OPTIONS: ReadonlyArray<{
  value: ThemePreference;
  labelKey: DictKey;
  Icon: typeof Sun;
}> = [
  { value: "light", labelKey: "top.theme_light", Icon: Sun },
  { value: "system", labelKey: "top.theme_system", Icon: Monitor },
  { value: "dark", labelKey: "top.theme_dark", Icon: Moon },
];

export function ThemeToggle({ className = "" }: { className?: string }) {
  const { preference, setPreference } = useTheme();
  const { t } = useI18n();

  return (
    <div
      role="radiogroup"
      aria-label={t("top.theme")}
      className={`inline-flex items-center gap-0.5 rounded-lg border border-border bg-card/60 p-0.5 ${className}`}
    >
      {OPTIONS.map(({ value, labelKey, Icon }) => {
        const active = preference === value;
        const label = t(labelKey);
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={label}
            title={label}
            onClick={() => setPreference(value)}
            className={
              // Colour-only transition, so the control never shifts under the pointer.
              "grid size-7 place-items-center rounded-md duration-[var(--motion-duration-fast)] " +
              "ease-[var(--motion-ease-standard)] transition-[background-color,color] " +
              "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--ring)] " +
              (active
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground hover:bg-[var(--interactive-hover)]")
            }
          >
            <Icon className="size-3.5" aria-hidden="true" />
          </button>
        );
      })}
    </div>
  );
}

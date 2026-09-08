/**
 * Light / System / Dark as a segmented radiogroup.
 *
 * A three-way control rather than a switch, because "system" is a real
 * preference that a two-way toggle throws away.
 */

import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme, type ThemePreference } from "@/lib/theme";

const OPTIONS: ReadonlyArray<{
  value: ThemePreference;
  label: string;
  Icon: typeof Sun;
}> = [
  { value: "light", label: "Light", Icon: Sun },
  { value: "system", label: "System", Icon: Monitor },
  { value: "dark", label: "Dark", Icon: Moon },
];

export function ThemeToggle({ className = "" }: { className?: string }) {
  const { preference, setPreference } = useTheme();

  return (
    <div
      role="radiogroup"
      aria-label="Colour theme"
      className={`inline-flex items-center gap-0.5 rounded-lg border border-border bg-card/60 p-0.5 ${className}`}
    >
      {OPTIONS.map(({ value, label, Icon }) => {
        const active = preference === value;
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
              // Colour-only transition at the fast token: no displacement, so
              // the control never shifts under the pointer.
              "grid size-7 place-items-center rounded-md duration-[var(--motion-duration-fast)] " +
              "ease-[var(--motion-ease-standard)] transition-[background-color,color] " +
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

import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { ModuleRegistryCard } from "@/components/app/ModuleRegistryCard";
import { usePermissions } from "@/lib/auth/use-permissions";
import { useI18n } from "@/lib/i18n";
import {
  getReadinessLabel,
  sortModules,
  type ModuleReadiness,
} from "@/lib/modules/registry";
import { readinessColor } from "@/lib/modules/readiness";
import { Card, CardContent } from "@/components/ui/card";

export const Route = createFileRoute("/_authenticated/modules/")({
  head: () => ({ meta: [{ title: "Modules · REDSEA" }] }),
  component: ModulesIndex,
});

export function ModulesIndex() {
  const perms = usePermissions();
  const { t } = useI18n();
  const modules = sortModules(perms.modules);
  const [active, setActive] = useState<ModuleReadiness | "all">("all");

  // Only offer chips for states that actually occur, so the row never shows a
  // filter that would return nothing.
  const counts = useMemo(() => {
    const map = new Map<ModuleReadiness, number>();
    for (const m of modules) map.set(m.readiness, (map.get(m.readiness) ?? 0) + 1);
    return [...map.entries()].sort((a, b) => b[1] - a[1]);
  }, [modules]);

  const shown = active === "all" ? modules : modules.filter((m) => m.readiness === active);

  return (
    <div className="mx-auto w-full max-w-[1180px] space-y-7">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-2">
          <p className="text-[12px] font-semibold uppercase tracking-[0.14em] text-primary">
            {t("shell.nav.workspace")} / {t("nav.modules")}
          </p>
          <h1
            className="text-[34px] font-bold leading-tight tracking-[-0.015em]"
            style={{ fontFamily: "var(--font-display)" }}
          >
            {t("nav.modules")}
          </h1>
          <p className="max-w-xl text-sm text-muted-foreground">
            {t("mod.index.description")}
          </p>
        </div>
      </header>

      {!perms.loading && modules.length > 0 && (
        <div className="flex flex-wrap gap-2" role="group" aria-label={t("nav.modules")}>
          <FilterChip
            label={t("mod.filter_all")}
            count={modules.length}
            colour="var(--primary)"
            active={active === "all"}
            onClick={() => setActive("all")}
          />
          {counts.map(([readiness, count]) => (
            <FilterChip
              key={readiness}
              label={getReadinessLabel({ readiness } as never, t)}
              count={count}
              colour={readinessColor(readiness)}
              active={active === readiness}
              onClick={() => setActive(readiness)}
            />
          ))}
        </div>
      )}

      {perms.loading ? (
        <div className="grid place-items-center p-10" role="status">
          <Loader2 className="size-5 animate-spin text-muted-foreground" />
          <span className="sr-only">{t("mod.loading")}</span>
        </div>
      ) : shown.length === 0 ? (
        <Card>
          <CardContent className="p-10 text-center text-sm text-muted-foreground">
            {t("mod.empty")}
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-[18px] [grid-template-columns:repeat(auto-fill,minmax(260px,1fr))]">
          {shown.map((module, i) => (
            <div
              key={module.key}
              className="module-enter"
              // 40ms cascade, capped so a long list does not stagger for seconds
              style={{ animationDelay: `${Math.min(i, 8) * 40}ms` }}
            >
              <ModuleRegistryCard
                module={module}
                canView={perms.canViewModule(module.key)}
                canRun={perms.canRunModule(module.key)}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function FilterChip({
  label,
  count,
  colour,
  active,
  onClick,
}: {
  label: string;
  count: number;
  colour: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={
        "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[12.5px] font-semibold whitespace-nowrap " +
        "duration-[var(--motion-duration-fast)] transition-colors " +
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--ring)] " +
        (active ? "" : "border-border text-muted-foreground hover:border-primary")
      }
      style={
        active
          ? {
              color: colour,
              borderColor: colour,
              backgroundColor: "color-mix(in oklab, " + colour + " 12%, transparent)",
            }
          : undefined
      }
    >
      <span
        aria-hidden="true"
        className="size-[7px] shrink-0 rounded-full"
        style={{ background: colour }}
      />
      {label}
      <span className="tabular-nums opacity-70">{count}</span>
    </button>
  );
}

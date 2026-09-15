import { Link } from "@tanstack/react-router";
import { useI18n } from "@/lib/i18n";
import {
  getModuleLabel,
  getReadinessLabel,
  type ModuleRegistryItem,
} from "@/lib/modules/registry";
import {
  moduleMonogram,
  readinessColor,
  readinessProgress,
} from "@/lib/modules/readiness";

interface ModuleRegistryCardProps {
  module: ModuleRegistryItem;
  canView: boolean;
  canRun: boolean;
}

/**
 * A module launcher card.
 *
 * Colour comes from the readiness ramp as a single CSS custom property set on
 * the card, so the badge, the progress fill and the tint all derive from one
 * value and cannot drift apart. Hover behaviour is expressed in styles.css
 * against `.module-card` rather than inline, because it drives several
 * descendants at once.
 */
export function ModuleRegistryCard({ module, canView, canRun }: ModuleRegistryCardProps) {
  const { t } = useI18n();
  const label = getModuleLabel(module, t);
  const readiness = getReadinessLabel(module, t);
  const colour = readinessColor(module.readiness);
  const progress = readinessProgress(module.readiness);
  const locked = !canView;
  const href = module.route;

  return (
    <article
      data-testid={`module-card-${module.key}`}
      className={
        "module-card group flex flex-col gap-3.5 rounded-2xl border border-border bg-card p-5 " +
        (locked ? "opacity-[0.72]" : "")
      }
      style={{ ["--ready" as string]: colour }}
    >
      <div className="flex items-start justify-between gap-3">
        <span
          aria-hidden="true"
          className="module-tile grid size-11 shrink-0 place-items-center rounded-xl text-[18px] font-semibold"
          style={{
            fontFamily: "var(--font-display)",
            background: "var(--ready-tile)",
            color: "var(--primary)",
          }}
        >
          {moduleMonogram(module.key)}
        </span>

        <span
          data-testid={`readiness-badge-${module.key}`}
          data-readiness={module.readiness}
          /* the readiness class makes the treatment inspectable per family,
             rather than the distinction living only in an inline style */
          className={
            `readiness-${module.readiness} ` +
            "inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-[11.5px] font-semibold whitespace-nowrap"
          }
          style={{
            color: "var(--ready)",
            backgroundColor: "color-mix(in oklab, var(--ready) 12%, transparent)",
          }}
        >
          <span
            aria-hidden="true"
            className="size-1.5 rounded-full"
            style={{ background: "var(--ready)" }}
          />
          {readiness}
        </span>
      </div>

      <div className="min-w-0">
        <h3
          className="truncate text-[17.5px] font-semibold"
          style={{ fontFamily: "var(--font-display)" }}
        >
          {label}
        </h3>
        {module.description && (
          <p className="mt-1 line-clamp-2 text-[12.5px] leading-[1.45] text-muted-foreground">
            {module.description}
          </p>
        )}
      </div>

      <div
        className="h-[3px] w-full overflow-hidden rounded-full"
        style={{ background: "var(--ready-track)" }}
        role="img"
        aria-label={`${readiness} — ${progress}%`}
      >
        <div
          className="module-progress h-full rounded-full"
          style={{ width: `${progress}%`, background: "var(--ready)" }}
        />
      </div>

      <div className="mt-auto flex items-center justify-between gap-2 pt-1">
        {href && canView ? (
          <Link
            to={href}
            className="module-ghost inline-flex h-8 items-center rounded-[9px] border border-border px-3 text-[12.5px] font-semibold whitespace-nowrap duration-[var(--motion-duration-fast)] transition-colors"
          >
            {t("mod.view")}
          </Link>
        ) : (
          <span className="text-[12.5px] text-muted-foreground">{t("mod.view")}</span>
        )}

        {locked ? (
          <span className="ms-auto text-[12px] text-muted-foreground">{t("mod.locked")}</span>
        ) : canRun && href ? (
          <Link
            to={href}
            className="module-run inline-flex h-8 items-center gap-1.5 rounded-[9px] bg-primary px-3 text-[12.5px] font-semibold text-primary-foreground whitespace-nowrap duration-[var(--motion-duration-fast)] transition-[filter]"
          >
            {t("mod.run")}
            {/* separate span so only the arrow travels on hover */}
            <span aria-hidden="true" className="module-arrow inline-block rtl:rotate-180">
              →
            </span>
          </Link>
        ) : null}
      </div>
    </article>
  );
}

import { Link } from "@tanstack/react-router";
import { ArrowRight, Lock } from "lucide-react";
import type { BadgeProps } from "@/components/ui/badge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { useI18n } from "@/lib/i18n";
import { DEFAULT_MODULE_ICON, MODULE_ICONS } from "@/lib/modules/icons";
import {
  getModuleLabel,
  getReadinessLabel,
  type ModuleReadiness,
  type ModuleRegistryItem,
} from "@/lib/modules/registry";
import { cn } from "@/lib/utils";

const WARNING_READINESS = new Set<ModuleReadiness>([
  "discovery_required",
  "not_migrated",
  "under_development",
]);

export function getReadinessBadgeProps(
  readiness: ModuleReadiness,
): Pick<BadgeProps, "variant" | "className"> {
  if (readiness === "available") {
    return {
      variant: "default",
      className: "bg-success text-success-foreground hover:bg-success/80",
    };
  }

  if (WARNING_READINESS.has(readiness)) {
    return {
      variant: "outline",
      className: "border-warning/50 bg-warning/10 text-warning-foreground",
    };
  }

  return { variant: "secondary", className: "text-muted-foreground" };
}

interface ModuleRegistryCardProps {
  module: ModuleRegistryItem;
  canView: boolean;
  canRun: boolean;
}

export function ModuleRegistryCard({ module, canView, canRun }: ModuleRegistryCardProps) {
  const { t } = useI18n();
  const Icon = MODULE_ICONS[module.key] ?? DEFAULT_MODULE_ICON;
  const label = getModuleLabel(module, t);
  const readinessLabel = getReadinessLabel(module, t);
  const readinessBadge = getReadinessBadgeProps(module.readiness);
  const clickable = canView && module.route !== null;

  const card = (
    <Card
      data-testid={`module-card-${module.key}`}
      className={cn(
        "h-full transition-all group",
        clickable
          ? "hover:border-primary/50 hover:shadow-md cursor-pointer"
          : "opacity-70 cursor-not-allowed",
      )}
    >
      <CardContent className="p-5 flex flex-col gap-3 h-full">
        <div className="flex items-start justify-between gap-2">
          <div className="size-10 rounded-lg bg-primary/10 grid place-items-center text-primary group-hover:bg-primary group-hover:text-primary-foreground transition-colors">
            <Icon className="size-5" />
          </div>
          <Badge
            variant={readinessBadge.variant}
            className={cn("text-[10px]", readinessBadge.className)}
            data-testid={`readiness-badge-${module.key}`}
          >
            {readinessLabel}
          </Badge>
        </div>
        <div className="flex-1">
          <h3 className="font-semibold text-base leading-tight">{label}</h3>
          {module.description && (
            <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
              {module.description}
            </p>
          )}
        </div>
        <div className="flex items-center justify-between pt-2 border-t border-border/50">
          <div className="flex gap-1">
            <Badge variant={canView ? "secondary" : "outline"} className="text-[10px]">
              {t("mod.access.view")}
            </Badge>
            <Badge variant={canRun ? "default" : "outline"} className="text-[10px]">
              {t("mod.access.run")}
            </Badge>
          </div>
          {clickable ? (
            <ArrowRight className="size-4 text-muted-foreground group-hover:text-primary group-hover:translate-x-0.5 transition-all rtl:rotate-180" />
          ) : (
            <Lock className="size-4 text-muted-foreground" />
          )}
        </div>
      </CardContent>
    </Card>
  );

  return clickable ? (
    <Link to={module.route as any} className="block">
      {card}
    </Link>
  ) : (
    <div>{card}</div>
  );
}

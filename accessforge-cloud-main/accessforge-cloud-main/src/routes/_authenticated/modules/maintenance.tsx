import { createFileRoute } from "@tanstack/react-router";
import { Loader2 } from "lucide-react";
import { ModuleRegistryCard } from "@/components/app/ModuleRegistryCard";
import { usePermissions } from "@/lib/auth/use-permissions";
import { useI18n } from "@/lib/i18n";
import { sortModules } from "@/lib/modules/registry";
import { Card, CardContent } from "@/components/ui/card";

export const Route = createFileRoute("/_authenticated/modules/maintenance")({
  head: () => ({ meta: [{ title: "Maintenance · REDSEA" }] }),
  component: MaintenancePage,
});

export function MaintenancePage() {
  const perms = usePermissions();
  const { t } = useI18n();
  const modules = sortModules(
    perms.modules.filter((module) => module.business_area === "maintenance"),
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{t("mod.maintenance.title")}</h1>
        <p className="text-sm text-muted-foreground">{t("mod.maintenance.status_note")}</p>
      </div>

      {perms.loading ? (
        <div className="p-10 grid place-items-center" role="status">
          <Loader2 className="size-5 animate-spin text-muted-foreground" />
          <span className="sr-only">{t("mod.loading")}</span>
        </div>
      ) : modules.length === 0 ? (
        <Card>
          <CardContent className="p-10 text-center text-sm text-muted-foreground">
            {t("mod.empty")}
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {modules.map((module) => (
            <ModuleRegistryCard
              key={module.key}
              module={module}
              canView={perms.canViewModule(module.key)}
              canRun={perms.canRunModule(module.key)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

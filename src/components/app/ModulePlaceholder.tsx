import { usePermissions } from "@/lib/auth/use-permissions";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Construction, ShieldAlert } from "lucide-react";

export function ModulePlaceholder({
  moduleKey,
  title,
  description,
}: {
  moduleKey: string;
  title: string;
  description: string;
}) {
  const perms = usePermissions();
  const canView = perms.canViewModule(moduleKey);
  const canRun = perms.canRunModule(moduleKey);

  if (!canView && !perms.loading) {
    return (
      <Card>
        <CardContent className="p-10 grid place-items-center text-center gap-2">
          <ShieldAlert className="size-10 text-destructive" />
          <h2 className="text-lg font-semibold">No access to this module</h2>
          <p className="text-sm text-muted-foreground max-w-md">
            Ask an administrator to grant you view access to <span className="font-mono">{moduleKey}</span>.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
          <p className="text-sm text-muted-foreground max-w-2xl">{description}</p>
        </div>
        <div className="flex gap-1.5">
          <Badge variant={canView ? "secondary" : "outline"}>
            {canView ? "View ✓" : "View ✗"}
          </Badge>
          <Badge variant={canRun ? "default" : "outline"}>
            {canRun ? "Run ✓" : "Run ✗"}
          </Badge>
        </div>
      </div>
      <Card>
        <CardContent className="p-10 grid place-items-center text-center text-muted-foreground">
          <Construction className="size-10 mb-3 text-primary" />
          <p className="text-sm max-w-md">
            Module UI scaffolded. Heavy processing (PyMuPDF / OCR / DOCX) runs on the Python worker —
            arriving in Phase 4 of the roadmap.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

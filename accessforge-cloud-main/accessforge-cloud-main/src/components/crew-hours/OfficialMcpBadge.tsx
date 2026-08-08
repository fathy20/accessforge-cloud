import { ShieldCheck } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { useI18n } from "@/lib/i18n";

export function OfficialMcpBadge() {
  const { t } = useI18n();

  return (
    <Badge
      variant="outline"
      className="gap-1.5 border-success/30 bg-success/10 text-success"
      aria-label={t("crew.official_mcp")}
    >
      <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
      {t("crew.official_mcp")}
    </Badge>
  );
}

import { ChevronDown, ChevronUp } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";
import { hasOfficialMcpTotal } from "./filters";
import { crewInitials, displayValue } from "./format";
import { OfficialMcpBadge } from "./OfficialMcpBadge";
import type { CrewHoursReport, CrewMemberSummary } from "./types";

interface CrewGroupHeaderProps {
  report: CrewHoursReport;
  crew: CrewMemberSummary;
  visibleFlightCount: number;
  hasClientSideDisplayFilter: boolean;
  isExpanded: boolean;
  onToggle: () => void;
}

export function CrewGroupHeader({
  report,
  crew,
  visibleFlightCount,
  hasClientSideDisplayFilter,
  isExpanded,
  onToggle,
}: CrewGroupHeaderProps) {
  const { t } = useI18n();
  const flightCountLabel = hasClientSideDisplayFilter
    ? t("crew.flight_count_filtered", {
        visible: visibleFlightCount,
        total: crew.flight_count,
      })
    : t("crew.flight_count", { count: crew.flight_count });

  return (
    <tr className="border-t-8 border-background bg-muted/30">
      <th colSpan={10} scope="rowgroup" className="p-2 text-start">
        <div className="flex min-w-[980px] flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <Button
            type="button"
            variant="ghost"
            onClick={onToggle}
            aria-expanded={isExpanded}
            className="min-w-0 flex-1 justify-start rounded-lg px-2 py-2 text-start focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 hover:bg-accent/60"
          >
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary/10 font-bold text-primary">
              {crewInitials(crew.display_name)}
            </div>
            <div className="min-w-0">
              <div className="flex min-w-0 items-center gap-2">
                <span className="truncate font-semibold" title={crew.display_name}>
                  {crew.display_name}
                </span>
                {crew.person_code && crew.display_name !== crew.person_code && (
                  <Badge variant="secondary" className="text-xs">
                    {crew.person_code}
                  </Badge>
                )}
              </div>
              <span className="block text-xs font-normal text-muted-foreground">
                {displayValue(crew.position_type)} · {flightCountLabel}
                {typeof crew.heavy_credits === "number" && (
                  <span className="ms-2 rounded bg-primary/10 px-1.5 py-0.5 font-mono text-[11px] font-semibold text-primary">
                    H.C {crew.heavy_credits}
                  </span>
                )}
              </span>
            </div>
          </Button>

          <div
            className="flex shrink-0 items-center gap-3"
            onClick={(event) => event.stopPropagation()}
          >
            {(crew.status === "TRN" || crew.official_total === "TRN") && (
              <Badge variant="secondary" className="font-mono text-xs">
                TRN
              </Badge>
            )}

            <div className="flex items-center gap-2 text-end text-xs">
              <div>
                <span className="block text-muted-foreground">{t("crew.official_total")}</span>
                <span
                  className={`font-mono font-semibold ${
                    hasOfficialMcpTotal(report, crew)
                      ? "text-foreground"
                      : "text-muted-foreground"
                  }`}
                >
                  {hasOfficialMcpTotal(report, crew)
                    ? displayValue(crew.official_total)
                    : t("crew.unavailable")}
                </span>
              </div>
              {hasOfficialMcpTotal(report, crew) && <OfficialMcpBadge />}
            </div>

            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-8 w-8 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              onClick={onToggle}
              aria-expanded={isExpanded}
              aria-label={t(
                isExpanded ? "crew.expand.collapse" : "crew.expand.expand",
              )}
            >
              {isExpanded ? (
                <ChevronUp className="h-4 w-4" aria-hidden="true" />
              ) : (
                <ChevronDown className="h-4 w-4" aria-hidden="true" />
              )}
            </Button>
          </div>
        </div>
      </th>
    </tr>
  );
}

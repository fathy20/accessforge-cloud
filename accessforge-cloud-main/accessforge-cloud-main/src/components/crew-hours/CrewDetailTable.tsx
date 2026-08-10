import { useI18n } from "@/lib/i18n";
import { hasOfficialMcpTotal, matchesDisplayFilters } from "./filters";
import { displayValue } from "./format";
import { CrewDetailFlightRow } from "./CrewDetailFlightRow";
import { CrewGroupHeader } from "./CrewGroupHeader";
import type {
  CrewHoursReport,
  CrewMemberSummary,
  PositionTokenFilter,
} from "./types";

interface CrewDetailTableProps {
  report: CrewHoursReport;
  crews: CrewMemberSummary[];
  aircraftFilter: string;
  positionTokenFilter: PositionTokenFilter;
  hasClientSideDisplayFilter: boolean;
  expandedCrew: Record<string, boolean>;
  onToggleCrew: (crewId: string) => void;
}

export function CrewDetailTable({
  report,
  crews,
  aircraftFilter,
  positionTokenFilter,
  hasClientSideDisplayFilter,
  expandedCrew,
  onToggleCrew,
}: CrewDetailTableProps) {
  const { t } = useI18n();
  const visibleCrews = crews.filter((crew) => {
    if (!hasClientSideDisplayFilter || crew.flights.length === 0) {
      return true;
    }

    return crew.flights.some((flight) =>
      matchesDisplayFilters(flight, aircraftFilter, positionTokenFilter),
    );
  });

  if (hasClientSideDisplayFilter && crews.length > 0 && visibleCrews.length === 0) {
    return (
      <div
        className="rounded-xl border border-border/80 bg-card p-8 text-center shadow-sm"
        role="status"
        aria-live="polite"
      >
        <p className="text-sm font-medium">{t("crew.filter.no_match")}</p>
        <p className="mt-2 text-xs text-muted-foreground">{t("crew.filter.reset_hint")}</p>
      </div>
    );
  }

  return (
    <div className="w-full min-w-0 overflow-x-auto rounded-xl border border-border/80 bg-card shadow-sm">
      <table
        className="w-full min-w-[980px] border-collapse text-start text-sm"
        aria-label={t("crew.table.detail_label")}
      >
        <caption className="sr-only">{t("crew.table.detail_label")}</caption>
        <thead className="bg-muted/20 text-xs uppercase text-muted-foreground">
          <tr>
            <th scope="col" className="whitespace-nowrap px-4 py-3 font-medium">
              {t("crew.table.position_type")}
            </th>
            <th scope="col" className="whitespace-nowrap px-4 py-3 font-medium">
              {t("crew.table.name")}
            </th>
            <th scope="col" className="whitespace-nowrap px-4 py-3 font-medium">
              {t("crew.table.date")}
            </th>
            <th scope="col" className="whitespace-nowrap px-4 py-3 font-medium">
              {t("crew.table.aircraft")}
            </th>
            <th scope="col" className="whitespace-nowrap px-4 py-3 font-medium">
              {t("crew.table.flight_number")}
            </th>
            <th scope="col" className="whitespace-nowrap px-4 py-3 font-medium">ADEP</th>
            <th scope="col" className="whitespace-nowrap px-4 py-3 font-medium">ADES</th>
            <th scope="col" className="whitespace-nowrap px-4 py-3 font-medium">OFF</th>
            <th scope="col" className="whitespace-nowrap px-4 py-3 font-medium">ON</th>
            <th scope="col" className="whitespace-nowrap px-4 py-3 font-medium">
              {t("crew.table.block_time")}
            </th>
          </tr>
        </thead>
        {visibleCrews.map((crew) => {
          const visibleFlights = crew.flights.filter((flight) =>
            matchesDisplayFilters(flight, aircraftFilter, positionTokenFilter),
          );
          const isExpanded = expandedCrew[crew.crew_id] ?? true;

          return (
            <tbody key={crew.crew_id} className="divide-y divide-border">
              <CrewGroupHeader
                report={report}
                crew={crew}
                visibleFlightCount={visibleFlights.length}
                hasClientSideDisplayFilter={hasClientSideDisplayFilter}
                isExpanded={isExpanded}
                onToggle={() => onToggleCrew(crew.crew_id)}
              />
              {isExpanded && (
                <>
                  {visibleFlights.map((flight, index) => (
                    <CrewDetailFlightRow
                      key={`${crew.crew_id}-${flight.flight_nid}-${index}`}
                      crew={crew}
                      flight={flight}
                    />
                  ))}
                  <tr className="bg-muted/10 font-semibold">
                    <td colSpan={9} className="px-4 py-3 text-end">
                      {t("crew.total")}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-end font-mono">
                      {hasOfficialMcpTotal(report, crew)
                        ? displayValue(crew.official_total)
                        : t("crew.unavailable")}
                    </td>
                  </tr>
                </>
              )}
            </tbody>
          );
        })}
        {crews.length === 0 && (
          <tbody>
            <tr>
              <td colSpan={10} className="px-4 py-10 text-center text-sm text-muted-foreground">
                {t("crew.empty.tab")}
              </td>
            </tr>
          </tbody>
        )}
      </table>
    </div>
  );
}

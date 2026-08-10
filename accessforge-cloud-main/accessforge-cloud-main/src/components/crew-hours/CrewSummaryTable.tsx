import { useI18n } from "@/lib/i18n";
import { hasOfficialMcpTotal } from "./filters";
import { displayOfficialHours, displayValue } from "./format";
import { OfficialMcpBadge } from "./OfficialMcpBadge";
import type { CrewHoursReport, CrewMemberSummary, ReportTabPosition } from "./types";

export function CrewSummaryTable({
  report,
  crews,
  position,
}: {
  report: CrewHoursReport;
  crews: CrewMemberSummary[];
  position: ReportTabPosition;
}) {
  const { t } = useI18n();
  const officialPositionTotal = report.official_totals_by_position?.[position];

  return (
    <div className="space-y-3">
      <div className="w-full min-w-0 overflow-x-auto rounded-xl border border-border/80 bg-card shadow-sm">
        <table
          className="w-full min-w-[760px] border-collapse text-start text-sm"
          aria-label={t("crew.table.summary_label")}
        >
          <caption className="sr-only">{t("crew.table.summary_label")}</caption>
          <thead className="bg-muted/20 text-xs uppercase text-muted-foreground">
            <tr>
              <th scope="col" className="whitespace-nowrap px-4 py-3 font-medium">
                {t("crew.table.position_type")}
              </th>
              <th scope="col" className="whitespace-nowrap px-4 py-3 font-medium">
                {t("crew.table.name")}
              </th>
              <th scope="col" className="whitespace-nowrap px-4 py-3 font-medium">
                {t("crew.table.crew_code")}
              </th>
              <th scope="col" className="whitespace-nowrap px-4 py-3 font-medium">
                {t("crew.table.flights")}
              </th>
              <th scope="col" className="whitespace-nowrap px-4 py-3 font-medium">
                {t("crew.table.official_total")}
              </th>
              <th scope="col" className="whitespace-nowrap px-4 py-3 font-medium">
                {t("crew.table.source")}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {crews.map((crew) => (
              <tr key={crew.crew_id} className="hover:bg-muted/10">
                <td className="whitespace-nowrap px-4 py-3 text-xs">
                  {displayValue(crew.position_type)}
                </td>
                <td className="px-4 py-3 font-medium">{displayValue(crew.display_name)}</td>
                <td className="px-4 py-3 font-mono text-xs">{displayValue(crew.person_code)}</td>
                <td className="px-4 py-3">{crew.flight_count}</td>
                <td className="whitespace-nowrap px-4 py-3 font-mono">
                  {hasOfficialMcpTotal(report, crew)
                    ? displayValue(crew.official_total)
                    : t("crew.unavailable")}
                </td>
                <td className="px-4 py-3">
                  {hasOfficialMcpTotal(report, crew) ? (
                    <OfficialMcpBadge />
                  ) : (
                    <span className="text-muted-foreground">{t("crew.unavailable")}</span>
                  )}
                </td>
              </tr>
            ))}
            {crews.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-sm text-muted-foreground">
                  {t("crew.empty.tab")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-info/20 bg-info/5 px-3 py-2 text-xs text-muted-foreground">
        <span>
          {t(position === "Cockpit" ? "crew.server_total.cockpit" : "crew.server_total.cabin")}
        </span>
        <span className="font-mono font-semibold text-foreground">
          {typeof officialPositionTotal === "string" && officialPositionTotal.trim().length > 0
            ? displayOfficialHours(report, position)
            : t("crew.unavailable")}
        </span>
      </div>
    </div>
  );
}

import { CrewDetailTable } from "./CrewDetailTable";
import { CrewSummaryTable } from "./CrewSummaryTable";
import type {
  CrewHoursReport,
  PositionTokenFilter,
  ReportTabDefinition,
} from "./types";

export function CrewReportTabPanel({
  report,
  tab,
  aircraftFilter,
  positionTokenFilter,
  hasClientSideDisplayFilter,
  expandedCrew,
  trnOverrides,
  onToggleCrew,
  onToggleTrn,
}: {
  report: CrewHoursReport;
  tab: ReportTabDefinition;
  aircraftFilter: string;
  positionTokenFilter: PositionTokenFilter;
  hasClientSideDisplayFilter: boolean;
  expandedCrew: Record<string, boolean>;
  trnOverrides: Record<string, boolean>;
  onToggleCrew: (crewId: string) => void;
  onToggleTrn: (crewId: string) => void;
}) {
  const crews = report.crew_members.filter((crew) => crew.position_type === tab.position);

  if (tab.summary) {
    return <CrewSummaryTable report={report} crews={crews} position={tab.position} />;
  }

  return (
    <CrewDetailTable
      report={report}
      crews={crews}
      aircraftFilter={aircraftFilter}
      positionTokenFilter={positionTokenFilter}
      hasClientSideDisplayFilter={hasClientSideDisplayFilter}
      expandedCrew={expandedCrew}
      trnOverrides={trnOverrides}
      onToggleCrew={onToggleCrew}
      onToggleTrn={onToggleTrn}
    />
  );
}

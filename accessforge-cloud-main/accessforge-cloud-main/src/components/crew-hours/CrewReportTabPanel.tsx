import { CrewDetailTable } from "./CrewDetailTable";
import { CrewSummaryTable } from "./CrewSummaryTable";
import { filterCrewMembers } from "./filters";
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
  crewSearch,
  selectedPosition,
  onToggleCrew,
}: {
  report: CrewHoursReport;
  tab: ReportTabDefinition;
  aircraftFilter: string;
  positionTokenFilter: PositionTokenFilter;
  hasClientSideDisplayFilter: boolean;
  expandedCrew: Record<string, boolean>;
  crewSearch: string;
  selectedPosition: string;
  onToggleCrew: (crewId: string) => void;
}) {
  const crews = filterCrewMembers(
    report.crew_members,
    crewSearch,
    selectedPosition,
  ).filter((crew) => crew.position_type === tab.position);

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
      onToggleCrew={onToggleCrew}
    />
  );
}

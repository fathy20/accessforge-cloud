import type {
  CrewHoursReport,
  CrewMemberSummary,
  FlightItem,
  PositionTokenFilter,
  PositioningToken,
  ReportTab,
  ReportTabPosition,
} from "./types";
import {
  ACTIVE_POSITION_TOKEN,
  ALL_AIRCRAFT,
  ALL_POSITION_TOKENS,
  OFFICIAL_MCP_SOURCE,
  POSITIONING_TOKENS,
} from "./types";

export function hasOfficialTotal(crew: CrewMemberSummary): boolean {
  return typeof crew.official_total === "string" && crew.official_total.trim().length > 0;
}

export function isPositioningToken(position: string | null): position is PositioningToken {
  return typeof position === "string" && POSITIONING_TOKENS.includes(position as PositioningToken);
}

export function isValidReportPeriod(period?: { from: string; to: string } | null): boolean {
  if (!period) {
    return false;
  }
  const datePattern = /^\d{4}-\d{2}-\d{2}$/;
  return datePattern.test(period.from) && datePattern.test(period.to) && period.from <= period.to;
}

export function reportTabPosition(tab: ReportTab): ReportTabPosition {
  return tab.startsWith("cockpit") ? "Cockpit" : "Cabin";
}

export function hasOfficialMcpTotal(report: CrewHoursReport, crew: CrewMemberSummary): boolean {
  return report.hours_source_status === OFFICIAL_MCP_SOURCE && hasOfficialTotal(crew);
}

export function matchesDisplayFilters(
  flight: FlightItem,
  aircraftFilter: string,
  positionTokenFilter: PositionTokenFilter,
): boolean {
  const matchesAircraft = aircraftFilter === ALL_AIRCRAFT || flight.aircraft_reg === aircraftFilter;
  const matchesPositionToken =
    positionTokenFilter === ALL_POSITION_TOKENS ||
    (positionTokenFilter === ACTIVE_POSITION_TOKEN
      ? !isPositioningToken(flight.position)
      : flight.position === positionTokenFilter);

  return matchesAircraft && matchesPositionToken;
}

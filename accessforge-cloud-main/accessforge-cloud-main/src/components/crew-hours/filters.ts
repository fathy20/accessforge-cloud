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
  return isStrictDateRange(period.from, period.to);
}

function isStrictCalendarDate(value: string): boolean {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) {
    return false;
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (month < 1 || month > 12 || day < 1) {
    return false;
  }
  const leapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const daysInMonth = [31, leapYear ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return day <= daysInMonth[month - 1];
}

export function isStrictDateRange(fromDate: string, toDate: string): boolean {
  return (
    isStrictCalendarDate(fromDate) &&
    isStrictCalendarDate(toDate) &&
    fromDate <= toDate
  );
}

export function buildCrewHoursReportQuery(fromDate: string, toDate: string): string | null {
  if (!isStrictDateRange(fromDate, toDate)) {
    return null;
  }
  return new URLSearchParams([
    ["from", fromDate],
    ["to", toDate],
  ]).toString();
}

export function filterCrewMembers(
  crews: CrewMemberSummary[],
  crewSearch: string,
  position: string,
): CrewMemberSummary[] {
  const query = crewSearch.trim().toLowerCase();
  const positionQuery = position.trim().toLowerCase();
  return crews.filter((crew) => {
    const matchesPosition =
      positionQuery === "" ||
      positionQuery === "all" ||
      crew.position_type?.toLowerCase() === positionQuery;
    const searchableValues = [crew.person_code, crew.display_name, crew.full_name];
    const matchesCrew =
      query === "" ||
      searchableValues.some(
        (value) => typeof value === "string" && value.toLowerCase().includes(query),
      );
    return matchesPosition && matchesCrew;
  });
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

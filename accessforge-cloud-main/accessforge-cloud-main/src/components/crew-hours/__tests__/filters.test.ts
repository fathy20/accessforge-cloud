import { describe, expect, it } from "vitest";

import {
  buildCrewHoursReportQuery,
  filterCrewMembers,
  isStrictDateRange,
  matchesDisplayFilters,
} from "../filters";
import {
  ACTIVE_POSITION_TOKEN,
  ALL_AIRCRAFT,
  ALL_POSITION_TOKENS,
} from "../types";
import type { CrewMemberSummary, FlightItem } from "../types";


function flight(
  flightNumber: string,
  aircraft: string,
  position: string,
): FlightItem {
  return {
    flight_nid: `fixture-${flightNumber}`,
    flight_number: flightNumber,
    departure_airport: "SSH",
    arrival_airport: "CAI",
    start_time_utc: "08:00",
    end_time_utc: "09:00",
    aircraft_reg: aircraft,
    aircraft_type: "A320",
    flight_date: "15-06-2026",
    block_time: "01:00",
    position,
    flight_training_type: null,
    is_trn: false,
  };
}


const crews: CrewMemberSummary[] = [
  {
    crew_id: "ALPHA",
    person_code: "AaM",
    display_name: "Alice Alpha",
    full_name: "Alice Alpha",
    position_type: "Cockpit",
    position_name: "CPT",
    status: "normal",
    official_total: "57:35",
    raw_official_total: "57:35",
    reference_total: null,
    variance_minutes: null,
    flight_count: 3,
    flights: [
      flight("RSX-ACTIVE", "SU-A", "CPT"),
      flight("RSX-PAD", "SU-A", "PAD"),
      flight("RSX-PSN", "SU-B", "PSN"),
    ],
  },
  {
    crew_id: "BRAVO",
    person_code: "BBB",
    display_name: "Bob Bravo",
    full_name: "Bob Bravo",
    position_type: "Cabin",
    position_name: "FA1",
    status: "normal",
    official_total: "10:00",
    raw_official_total: "10:00",
    reference_total: null,
    variance_minutes: null,
    flight_count: 1,
    flights: [flight("RSX-CABIN", "SU-A", "FA1")],
  },
];


describe("Crew Hours strict dates", () => {
  it("validates calendar dates and ordering without Date conversion", () => {
    expect(isStrictDateRange("2026-06-01", "2026-06-30")).toBe(true);
    expect(isStrictDateRange("2028-02-29", "2028-02-29")).toBe(true);
    expect(isStrictDateRange("2026-02-29", "2026-03-01")).toBe(false);
    expect(isStrictDateRange("2026-06-30", "2026-06-01")).toBe(false);
    expect(isStrictDateRange("06-01-2026", "2026-06-30")).toBe(false);
  });

  it("serializes each supplied date exactly once", () => {
    expect(buildCrewHoursReportQuery("2026-06-01", "2026-06-30")).toBe(
      "from=2026-06-01&to=2026-06-30",
    );
    expect(buildCrewHoursReportQuery("2026-06-30", "2026-06-01")).toBeNull();
  });
});

describe("Crew Hours local detail filters", () => {
  it("matches partial, full, code, and mixed-case searches and clear restores rows", () => {
    expect(filterCrewMembers(crews, "ali", "All").map((crew) => crew.crew_id)).toEqual([
      "ALPHA",
    ]);
    expect(filterCrewMembers(crews, "ALICE ALPHA", "All")).toHaveLength(1);
    expect(filterCrewMembers(crews, "aam", "All")).toHaveLength(1);
    expect(filterCrewMembers(crews, "", "All")).toEqual(crews);
  });

  it("combines loaded date scope, search, position, aircraft, and token filters", () => {
    const searched = filterCrewMembers(crews, "alice", "Cockpit");
    const visible = searched.flatMap((crew) =>
      crew.flights.filter((item) => matchesDisplayFilters(item, "SU-B", "PSN")),
    );

    expect(visible.map((item) => item.flight_number)).toEqual(["RSX-PSN"]);
    expect(crews[0].official_total).toBe("57:35");
    expect(
      crews[0].flights.filter((item) =>
        matchesDisplayFilters(item, ALL_AIRCRAFT, ACTIVE_POSITION_TOKEN),
      ).map((item) => item.flight_number),
    ).toEqual(["RSX-ACTIVE"]);
    expect(
      crews[0].flights.filter((item) =>
        matchesDisplayFilters(item, ALL_AIRCRAFT, ALL_POSITION_TOKENS),
      ),
    ).toHaveLength(3);
  });
});

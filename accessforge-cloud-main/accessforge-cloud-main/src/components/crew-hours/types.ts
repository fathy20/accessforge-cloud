export interface FlightItem {
  flight_nid: string;
  flight_number: string | null;
  departure_airport: string | null;
  arrival_airport: string | null;
  start_time_utc: string | null;
  end_time_utc: string | null;
  aircraft_reg: string | null;
  aircraft_type: string | null;
  flight_date: string | null;
  block_time: string | null;
  position: string | null;
  flight_training_type: string | null;
  is_trn: boolean;
  journey_log?: unknown;
}

export interface CrewMemberSummary {
  crew_id: string;
  person_code?: string;
  display_name: string;
  full_name: string | null;
  position_type?: string | null;
  position_name?: string;
  status: string;
  official_total: string | null;
  raw_official_total: string | null;
  reference_total: string | null;
  variance_minutes: number | null;
  flight_count: number;
  flights: FlightItem[];
}

export interface CrewHoursReport {
  period: { from: string; to: string };
  source: string;
  hours_source_status: string;
  total_crew: number;
  total_flights: number;
  records_count: number;
  official_totals_available: number;
  official_totals_unavailable: number;
  official_totals_by_position: Partial<Record<OfficialPosition, string>>;
  crew_members: CrewMemberSummary[];
}

export const OFFICIAL_MCP_SOURCE = "official_mcp_report";
export const POSITIONING_TOKENS = ["PAD", "PSN", "FDP", "FDPI", "RMP", "INSP"] as const;
export const ALL_AIRCRAFT = "__all_aircraft__";
export const ALL_POSITION_TOKENS = "All";
export const ACTIVE_POSITION_TOKEN = "Active";

export type OfficialPosition = "Cockpit" | "Cabin" | "Maintenance" | "Unclassified";
export type PositioningToken = (typeof POSITIONING_TOKENS)[number];
export type PositionTokenFilter =
  | typeof ALL_POSITION_TOKENS
  | typeof ACTIVE_POSITION_TOKEN
  | PositioningToken;
export type ReportTab = "cockpit" | "cockpit-summary" | "cabin" | "cabin-summary";
export type ReportTabPosition = Extract<OfficialPosition, "Cockpit" | "Cabin">;

export interface ReportTabDefinition {
  value: ReportTab;
  position: ReportTabPosition;
  summary: boolean;
}

export const REPORT_TABS: ReportTabDefinition[] = [
  { value: "cockpit", position: "Cockpit", summary: false },
  { value: "cockpit-summary", position: "Cockpit", summary: true },
  { value: "cabin", position: "Cabin", summary: false },
  { value: "cabin-summary", position: "Cabin", summary: true },
];

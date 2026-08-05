import logging
from datetime import date
from typing import Annotated, Any, Dict, List, Mapping, Protocol

from fastapi import Depends

from .errors import (
    CrewHoursCapabilityError,
    LeonAuthenticationError,
    LeonConfigurationError,
    LeonContractError,
    LeonResponseError,
    LeonTransportError,
)
from .leon_client import CrewHoursLeonClient, get_crew_hours_leon_client
from .mcp_report import OfficialMcpReport
from .schemas import (
    CrewHoursPeriod,
    CrewHoursReportResponse,
    CrewHoursRequest,
    CrewHoursResponse,
    CrewMemberSummary,
    FlightItem,
)

logger = logging.getLogger(__name__)

# Derived from LEON's own role-slot column labels; see docs/architecture/leon-report-wizard-columns.md.
# Reconciled against live June 2026 data.
# Known-unclassified tokens: PAD, PSN, FDP, FDPI, RMP, INSP (pending a business rule).
LEON_POSITION_GROUPS: Mapping[str, frozenset[str]] = {
    "Cockpit": frozenset(
        {
            "CPT",
            "CPT2",
            "CPT3",
            "CPT4",
            "CPT5",
            "FE",
            "FO",
            "FO2",
            "FO3",
            "FO4",
            "INS",
            "LTC",
            "LTE",
            "LTI",
            "OBS",
            "OBS2",
            "SP",
            "STB",
            "TRE",
            "TRI",
        }
    ),
    "Cabin": frozenset(
        {
            "EFA",
            "EFA2",
            "FA1",
            "FA2",
            "FA3",
            "FA4",
            "FA5",
            "FA6",
            "FA7",
            "FA8",
            "FA9",
            "FA10",
            "FA11",
            "FA12",
            "FA13",
            "FA14",
            "FA15",
            "IFA",
            "IFA2",
            "SFA",
            "SFA2",
            "SFA3",
        }
    ),
    "Maintenance": frozenset({"ENG1", "ENG2", "ENG3", "ENG4"}),
}


class CrewHoursService(Protocol):
    def get_crew_hours(self, request: CrewHoursRequest) -> CrewHoursResponse:
        ...

    def get_crew_hours_report(
        self,
        from_date: str,
        to_date: str,
        position: str | None = "All",
        crew_member: str | None = None,
    ) -> CrewHoursReportResponse:
        ...


class LiveCrewHoursService:
    def __init__(self, leon_client: CrewHoursLeonClient):
        self._leon_client = leon_client

    def get_crew_hours(self, request: CrewHoursRequest) -> CrewHoursResponse:
        return CrewHoursResponse(message="Crew Hours backend skeleton only. Not implemented yet.")

    def get_crew_hours_report(
        self,
        from_date: str,
        to_date: str,
        position: str | None = "All",
        crew_member: str | None = None,
    ) -> CrewHoursReportResponse:
        """Build the report from the authoritative MCP Report Wizard rows."""
        today = date.today()
        if not from_date:
            from_date = today.replace(day=1).isoformat()
        if not to_date:
            to_date = today.isoformat()

        try:
            official_report = self._leon_client.fetch_official_totals(from_date, to_date)
        except (
            LeonAuthenticationError,
            LeonConfigurationError,
            LeonContractError,
            LeonResponseError,
            LeonTransportError,
        ) as exc:
            logger.warning("LEON official MCP report unavailable (%s).", type(exc).__name__)
            raise

        if not isinstance(official_report, OfficialMcpReport):
            if not official_report:
                raise LeonConfigurationError("LEON official MCP report is not configured.")
            raise LeonContractError("LEON official report did not expose report rows.")

        return _build_mcp_report_response(
            official_report,
            from_date=from_date,
            to_date=to_date,
            position=position,
            crew_member=crew_member,
        )

def _build_mcp_report_response(
    report: OfficialMcpReport,
    *,
    from_date: str,
    to_date: str,
    position: str | None,
    crew_member: str | None,
) -> CrewHoursReportResponse:
    crew_map: Dict[str, Dict[str, Any]] = {}
    selected_row_count = 0
    unclassified_position_tokens: set[str] = set()
    unclassified_crew_codes: set[str] = set()
    position_query = (position or "All").strip().lower()
    crew_query = (crew_member or "").strip().lower()
    names_column_present = any(
        isinstance(row, Mapping) and "crew_names" in row for row in report.rows
    )
    position_column_present = any(
        isinstance(row, Mapping) and "crew_position_names" in row for row in report.rows
    )
    if not names_column_present:
        logger.info("LEON MCP report optional column 'crew_names' was absent from the report.")
    if not position_column_present:
        logger.info(
            "LEON MCP report optional column 'crew_position_names' was absent from the report."
        )
    if position_query != "all" and not position_column_present:
        raise CrewHoursCapabilityError(
            "LEON MCP report does not provide position data; remove the position filter."
        )

    for row in report.rows:
        if not isinstance(row, Mapping):
            raise LeonContractError("LEON MCP report row had an invalid shape.")
        codes = row.get("crew_codes")
        if not isinstance(codes, list) or any(not isinstance(code, str) for code in codes):
            raise LeonContractError("LEON MCP report row had invalid crew_codes.")
        names: list[str | None] | None = None
        positions: list[str | None] | None = None
        names_misaligned = False
        positions_misaligned = False
        if "crew_names" in row:
            raw_names = row["crew_names"]
            if isinstance(raw_names, list) and len(raw_names) == len(codes):
                names = _string_list(raw_names)
            else:
                names_misaligned = True
        if "crew_position_names" in row:
            raw_positions = row["crew_position_names"]
            if isinstance(raw_positions, list) and len(raw_positions) == len(codes):
                positions = _string_list(raw_positions)
            else:
                positions_misaligned = True
        if names_misaligned or positions_misaligned:
            logger.warning(
                "LEON MCP report crew arrays were misaligned for scope row %s.",
                row.get("scope_row_unique_id"),
            )
            names = None
            positions = None

        row_selected = False
        code_indices: dict[str, int] = {}
        for code_index, raw_code in enumerate(codes):
            code = raw_code.strip()
            if not code or code in code_indices:
                continue
            code_indices[code] = code_index

        for code, code_index in code_indices.items():
            full_name = _indexed_string(names, code_index)
            crew_position = _indexed_string(positions, code_index)
            position_type = _position_group(crew_position)
            if position_type is None and crew_position is not None:
                unclassified_position_tokens.add(crew_position.upper())
                unclassified_crew_codes.add(code)
            if position_query != "all" and not _matches_query(position_type, position_query):
                continue
            if crew_query and not (
                _matches_query(code, crew_query)
                or _matches_query(full_name, crew_query)
            ):
                continue

            row_selected = True
            key = code
            if key not in crew_map:
                crew_map[key] = {
                    "crew_id": key,
                    "person_code": key,
                    "full_name": full_name,
                    "position_name": crew_position,
                    "position_groups": [],
                    "has_trn": False,
                    "flights": [],
                }
            elif crew_map[key]["full_name"] is None and full_name is not None:
                crew_map[key]["full_name"] = full_name

            if position_type is not None:
                crew_map[key]["position_groups"].append(position_type)

            flight = _mcp_flight_item(row, crew_position)
            crew_map[key]["flights"].append(flight)
            if flight.is_trn:
                crew_map[key]["has_trn"] = True

        if row_selected:
            selected_row_count += 1

    if unclassified_position_tokens:
        logger.info(
            "LEON MCP report contained %d crew with unclassified positions: %s",
            len(unclassified_crew_codes),
            sorted(unclassified_position_tokens),
        )

    crew_summaries: List[CrewMemberSummary] = []
    official_totals = dict(report)
    for code, data in crew_map.items():
        official_total = official_totals.get(code)
        crew_summaries.append(
            CrewMemberSummary(
                crew_id=data["crew_id"],
                person_code=data["person_code"],
                display_name=data["full_name"] or code,
                full_name=data["full_name"],
                position_type=_most_frequent_position(data["position_groups"]),
                position_name=data["position_name"],
                status="TRN" if data["has_trn"] else "normal",
                official_total=official_total,
                raw_official_total=official_total,
                reference_total=None,
                variance_minutes=None,
                flight_count=len(data["flights"]),
                flights=data["flights"],
            )
        )

    official_totals_available = sum(
        1
        for item in crew_summaries
        if isinstance(item.official_total, str) and item.official_total.strip()
    )
    crew_summaries.sort(key=lambda item: (item.display_name.casefold(), item.person_code or ""))
    return CrewHoursReportResponse(
        period=CrewHoursPeriod(from_date=from_date, to_date=to_date),
        source="leon_mcp_report",
        hours_source_status="official_mcp_report",
        total_crew=len(crew_summaries),
        total_flights=selected_row_count,
        records_count=report.records_count,
        official_totals_available=official_totals_available,
        official_totals_unavailable=len(crew_summaries) - official_totals_available,
        crew_members=crew_summaries,
    )


def _mcp_flight_item(row: Mapping[str, Any], position: str | None) -> FlightItem:
    flight_nid = _optional_string(row.get("scope_row_unique_id"))
    if flight_nid is None:
        raise LeonContractError("LEON MCP report row did not provide scope_row_unique_id.")
    # positioning_crew remains intentionally unused; its alignment and semantics are unverified.
    return FlightItem(
        flight_nid=flight_nid,
        flight_number=_optional_string(row.get("flightNo")),
        departure_airport=_optional_string(row.get("jl_adep_preferred_code")),
        arrival_airport=_optional_string(row.get("jl_ades_preferred_code")),
        start_time_utc=_optional_string(row.get("JL_STD_UTC")),
        end_time_utc=_optional_string(row.get("JL_STA_UTC")),
        aircraft_reg=_optional_string(row.get("registration")),
        aircraft_type=_optional_string(row.get("acftType")),
        flight_date=_optional_string(row.get("date_STD_log_UTC")),
        block_time=_optional_string(row.get("blockTimeJourneyLog")),
        position=position,
        flight_training_type=None,
        is_trn=False,
        journey_log=None,
    )


def _string_list(value: Any) -> list[str | None]:
    if not isinstance(value, list):
        return []
    return [item.strip() if isinstance(item, str) and item.strip() else None for item in value]


def _indexed_string(values: list[str | None] | None, index: int) -> str | None:
    if values is None or index >= len(values):
        return None
    value = values[index]
    return value or None


def _optional_string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _position_group(position: str | None) -> str | None:
    if not isinstance(position, str) or not position.strip():
        return None
    token = position.strip().upper()
    for group, tokens in LEON_POSITION_GROUPS.items():
        if token in tokens:
            return group
    if token.startswith("FA") and token[2:].isdigit() and int(token[2:]) > 0:
        return "Cabin"
    return None


def _most_frequent_position(position_groups: list[str]) -> str | None:
    counts: dict[str, int] = {}
    most_frequent: str | None = None
    highest_count = 0
    for position_group in position_groups:
        counts[position_group] = counts.get(position_group, 0) + 1
        if counts[position_group] > highest_count:
            most_frequent = position_group
            highest_count = counts[position_group]
    return most_frequent


def _matches_query(value: str | None, query: str) -> bool:
    return bool(value) and query in value.lower()

def get_crew_hours_service(
    leon_client: Annotated[CrewHoursLeonClient, Depends(get_crew_hours_leon_client)],
) -> CrewHoursService:
    return LiveCrewHoursService(leon_client)

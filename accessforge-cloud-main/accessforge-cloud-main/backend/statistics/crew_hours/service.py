import logging
from datetime import date
from typing import Annotated, Any, Dict, List, Mapping, Protocol

from fastapi import Depends

from .augmented import AugmentedIndex
from .domain import is_trn_total, normalize_report_row
from .errors import (
    CrewHoursCapabilityError,
    LeonAuthenticationError,
    LeonConfigurationError,
    LeonContractError,
    LeonResponseError,
    LeonTransportError,
)
from .leon_client import CrewHoursLeonClient, get_crew_hours_leon_client
from .mcp_report import OfficialMcpReport, _format_minutes
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
# PSN is non-operating for that member's numeric total.  PAD, FDP, FDPI, RMP,
# and INSP retain the approved existing inclusion semantics.
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

        augmented_index = _fetch_augmented_index_safely(
            self._leon_client,
            from_date,
            to_date,
        )
        return _build_mcp_report_response(
            official_report,
            from_date=from_date,
            to_date=to_date,
            position=position,
            crew_member=crew_member,
            augmented_index=augmented_index,
        )


def _fetch_augmented_index_safely(
    leon_client: CrewHoursLeonClient,
    from_date: str,
    to_date: str,
) -> AugmentedIndex:
    fetcher = getattr(leon_client, "fetch_augmented_index", None)
    if not callable(fetcher):
        return AugmentedIndex(False, {}, 0, 0)
    try:
        index = fetcher(from_date, to_date)
        if not isinstance(index, AugmentedIndex):
            raise LeonContractError("LEON FTL augmented enrichment returned an invalid index.")
        return index
    except Exception as exc:
        logger.warning(
            "LEON FTL augmented enrichment period=%s..%s duty_rows=%d resolved=%d ambiguous=%d unavailable=%s error_type=%s",
            from_date,
            to_date,
            0,
            0,
            0,
            True,
            type(exc).__name__,
        )
        return AugmentedIndex(False, {}, 0, 0)


def _build_mcp_report_response(
    report: OfficialMcpReport,
    *,
    from_date: str,
    to_date: str,
    position: str | None,
    crew_member: str | None,
    augmented_index: AugmentedIndex | None = None,
) -> CrewHoursReportResponse:
    augmented_index = augmented_index or AugmentedIndex(False, {}, 0, 0)
    crew_map: Dict[str, Dict[str, Any]] = {}
    row_crew_codes: list[set[str]] = []
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
        normalized_row = normalize_report_row(row)
        if normalized_row.arrays_misaligned:
            logger.warning(
                "LEON MCP report crew arrays were misaligned for scope row %s.",
                row.get("scope_row_unique_id"),
            )

        row_codes: set[str] = set()
        for crew_slot in normalized_row.crew:
            code = crew_slot.code
            row_codes.add(code)
            # Preserve the established display contract: one misaligned optional
            # array degrades both display fields for this row.  The domain still
            # retains any independently aligned position array for PSN aggregation.
            full_name = None if normalized_row.arrays_misaligned else crew_slot.name
            crew_position = None if normalized_row.arrays_misaligned else crew_slot.position
            flight_position = (
                None if normalized_row.positions_misaligned else crew_slot.position
            )
            position_type = _position_group(crew_position)
            if position_type is None and crew_position is not None:
                unclassified_position_tokens.add(crew_position.upper())
                unclassified_crew_codes.add(code)
            key = code
            explicit_trn = is_trn_total(report.get(code))
            if key not in crew_map:
                crew_map[key] = {
                    "crew_id": key,
                    "person_code": key,
                    "full_name": full_name,
                    "position_name": crew_position,
                    "position_groups": [],
                    "has_trn": explicit_trn,
                    "flights": [],
                }
            elif crew_map[key]["full_name"] is None and full_name is not None:
                crew_map[key]["full_name"] = full_name
            if crew_map[key]["position_name"] is None and crew_position is not None:
                crew_map[key]["position_name"] = crew_position
            if explicit_trn:
                crew_map[key]["has_trn"] = True

            if position_type is not None:
                crew_map[key]["position_groups"].append(position_type)

            flight = _mcp_flight_item(
                row,
                flight_position,
                crew_code=code,
                augmented_index=augmented_index,
                is_trn=explicit_trn,
            )
            crew_map[key]["flights"].append(flight)
        row_crew_codes.append(row_codes)

    if unclassified_position_tokens:
        logger.info(
            "LEON MCP report contained %d crew with unclassified positions: %s",
            len(unclassified_crew_codes),
            sorted(unclassified_position_tokens),
        )

    official_totals = dict(report)
    for raw_code, official_total in official_totals.items():
        code = raw_code.strip()
        if not code:
            continue
        if code not in crew_map:
            crew_map[code] = {
                "crew_id": code,
                "person_code": code,
                "full_name": None,
                "position_name": None,
                "position_groups": [],
                "has_trn": is_trn_total(official_total),
                "flights": [],
            }
        elif is_trn_total(official_total):
            crew_map[code]["has_trn"] = True

    all_crew_summaries: List[CrewMemberSummary] = []
    for code, data in crew_map.items():
        official_total = official_totals.get(code)
        all_crew_summaries.append(
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

    official_totals_by_position_minutes: dict[str, int] = {}
    for item in all_crew_summaries:
        if (
            item.person_code is None
            or not isinstance(item.official_total, str)
            or not item.official_total.strip()
            or is_trn_total(item.official_total)
        ):
            continue
        minutes = report.total_minutes.get(item.person_code)
        if not isinstance(minutes, int):
            continue
        position_type = item.position_type or "Unclassified"
        official_totals_by_position_minutes[position_type] = (
            official_totals_by_position_minutes.get(position_type, 0) + minutes
        )
    official_totals_by_position = {
        position_type: _format_minutes(minutes)
        for position_type, minutes in official_totals_by_position_minutes.items()
    }

    crew_summaries = [
        item
        for item in all_crew_summaries
        if (
            position_query == "all"
            or _matches_query(item.position_type, position_query)
        )
        and (
            not crew_query
            or _matches_query(item.person_code, crew_query)
            or _matches_query(item.full_name, crew_query)
            or _matches_query(item.display_name, crew_query)
        )
    ]
    selected_codes = {
        item.person_code for item in crew_summaries if item.person_code is not None
    }
    selected_row_count = sum(
        1 for codes in row_crew_codes if not codes.isdisjoint(selected_codes)
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
        official_totals_by_position=official_totals_by_position,
        crew_members=crew_summaries,
    )


def _mcp_flight_item(
    row: Mapping[str, Any],
    position: str | None,
    *,
    is_trn: bool = False,
    crew_code: str | None = None,
    augmented_index: AugmentedIndex | None = None,
) -> FlightItem:
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
        flight_training_type="TRN" if is_trn else None,
        is_trn=is_trn,
        journey_log=None,
        augmented_heavy=(augmented_index or AugmentedIndex(False, {}, 0, 0)).lookup(
            crew_code,
            _optional_string(row.get("unique_id")),
        ),
    )


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

import logging
from datetime import date
from typing import Annotated, Any, Dict, List, Mapping, Protocol, Sequence

from fastapi import Depends

from .augmented import AugmentedIndex
from .crew_context import CREW_CONTEXT_CHUNK_DAYS, CrewContextEntry, CrewContextIndex, FlightContext
from .domain import buffered_query_dates, is_trn_total, normalize_report_row, utc_today
from .errors import (
    CrewHoursCapabilityError,
    LeonAuthenticationError,
    LeonConfigurationError,
    LeonContractError,
    LeonResponseError,
    LeonTransportError,
)
from .leon_client import CrewHoursLeonClient, get_crew_hours_leon_client
from .heavy import (
    decide_heavy,
    derive_heavy_detail,
    merge_route_airports,
    is_training_function,
    is_training_position,
)
from .mcp_report import OfficialMcpReport, _format_minutes
from .positions import LEON_POSITION_GROUPS
from .unknown_resolver import build_rotation_index, resolve_unknown_heavy
from .schemas import (
    CrewHoursPeriod,
    CrewHoursReportResponse,
    CrewHoursRequest,
    CrewHoursResponse,
    CrewMemberSummary,
    FlightItem,
)

logger = logging.getLogger(__name__)

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
        # UTC, never server-local (L-5 ruling 2026-08-18): the data is UTC-keyed.
        today = utc_today()
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
        crew_context_index = _fetch_crew_context_index_safely(
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
            crew_context_index=crew_context_index,
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


def _fetch_crew_context_index_safely(
    leon_client: CrewHoursLeonClient,
    from_date: str,
    to_date: str,
) -> CrewContextIndex:
    fetcher = getattr(leon_client, "fetch_crew_context_index", None)
    if not callable(fetcher):
        return CrewContextIndex(False, {})
    try:
        index = fetcher(from_date, to_date)
        if not isinstance(index, CrewContextIndex):
            raise LeonContractError("LEON flight-list crew context returned an invalid index.")
        logger.info(
            "LEON crew context period=%s..%s chunks=%d flights_indexed=%d unavailable=%s",
            from_date,
            to_date,
            _crew_context_chunk_count(from_date, to_date),
            len(index.by_flight),
            not index.available,
        )
        return index
    except Exception as exc:
        logger.warning(
            "LEON crew context period=%s..%s chunks=%d flights_indexed=0 unavailable=%s error_type=%s",
            from_date,
            to_date,
            _crew_context_chunk_count(from_date, to_date),
            True,
            type(exc).__name__,
        )
        return CrewContextIndex(False, {})


def _crew_context_chunk_count(from_date: str, to_date: str) -> int:
    try:
        buffered_from, buffered_to = buffered_query_dates(from_date, to_date)
        span_days = (
            date.fromisoformat(buffered_to) - date.fromisoformat(buffered_from)
        ).days + 1
        return (span_days + CREW_CONTEXT_CHUNK_DAYS - 1) // CREW_CONTEXT_CHUNK_DAYS
    except (TypeError, ValueError, LeonContractError):
        return 0


class _JoinHealthCounters:
    """Per-report join instrumentation across the three LEON identifier spaces.

    The Report Wizard's ``unique_id`` is joined against the FTL index (keyed
    by ``trNid``) and the flight-list index (keyed by ``flightNid``) on the
    UNVERIFIED assumption that they are the same number — the column docs mark
    it AMBIGUOUS. If they differ, every lookup misses and the whole report
    silently reads No; these counters make that failure loud instead.
    """

    __slots__ = (
        "augmented_hits",
        "augmented_attempts",
        "crew_context_hits",
        "crew_context_attempts",
    )

    def __init__(self) -> None:
        self.augmented_hits = 0
        self.augmented_attempts = 0
        self.crew_context_hits = 0
        self.crew_context_attempts = 0


# Below this hit rate, against a non-empty index, the join is presumed broken.
_JOIN_HEALTH_MINIMUM_HIT_RATE = 0.5


def _join_health_status(
    counters: _JoinHealthCounters,
    augmented_index: AugmentedIndex,
    crew_context_index: CrewContextIndex,
) -> str:
    def degraded(hits: int, attempts: int, index_size: int) -> bool:
        return (
            attempts > 0
            and index_size > 0
            and hits / attempts < _JOIN_HEALTH_MINIMUM_HIT_RATE
        )

    augmented_size = len(augmented_index.by_crew_sector) if augmented_index.available else 0
    context_size = len(crew_context_index.by_flight) if crew_context_index.available else 0
    if degraded(counters.augmented_hits, counters.augmented_attempts, augmented_size) or degraded(
        counters.crew_context_hits, counters.crew_context_attempts, context_size
    ):
        return "DEGRADED"
    return "OK"


def _build_mcp_report_response(
    report: OfficialMcpReport,
    *,
    from_date: str,
    to_date: str,
    position: str | None,
    crew_member: str | None,
    augmented_index: AugmentedIndex | None = None,
    crew_context_index: CrewContextIndex | None = None,
) -> CrewHoursReportResponse:
    augmented_index = augmented_index or AugmentedIndex(False, {}, 0, 0)
    crew_context_index = crew_context_index or CrewContextIndex(False, {})
    join_health_counters = _JoinHealthCounters()
    # Built once per report; STEP 4 needs each crew member's flights in time order.
    rotation_index = build_rotation_index(crew_context_index)
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
                crew_context_index=crew_context_index,
                rotation_index=rotation_index,
                is_trn=explicit_trn,
                join_health=join_health_counters,
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

    join_health = _join_health_status(
        join_health_counters, augmented_index, crew_context_index
    )
    # DEBUG when healthy: clean reports stay quiet (a pinned contract); the
    # counters always travel in the response, and degradation warns loudly.
    logger.debug(
        "Crew Hours join health period=%s..%s augmented=%d/%d crew_context=%d/%d status=%s",
        from_date,
        to_date,
        join_health_counters.augmented_hits,
        join_health_counters.augmented_attempts,
        join_health_counters.crew_context_hits,
        join_health_counters.crew_context_attempts,
        join_health,
    )
    if join_health == "DEGRADED":
        logger.warning(
            "Crew Hours join health DEGRADED: report unique_id values are not "
            "matching the FTL trNid / flight-list flightNid indices "
            "(augmented %d/%d, crew_context %d/%d). Run "
            "backend.statistics.crew_hours.tools.id_probe to confirm the join key.",
            join_health_counters.augmented_hits,
            join_health_counters.augmented_attempts,
            join_health_counters.crew_context_hits,
            join_health_counters.crew_context_attempts,
        )

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
        join_health=join_health,
        augmented_lookup_hits=join_health_counters.augmented_hits,
        augmented_lookup_attempts=join_health_counters.augmented_attempts,
        crew_context_hits=join_health_counters.crew_context_hits,
        crew_context_attempts=join_health_counters.crew_context_attempts,
        cabin_trainee_detection=(
            "active"
            if crew_context_index.available and crew_context_index.crew_function_available
            else "unavailable"
        ),
        crew_members=crew_summaries,
    )


def _mcp_flight_item(
    row: Mapping[str, Any],
    position: str | None,
    *,
    is_trn: bool = False,
    crew_code: str | None = None,
    augmented_index: AugmentedIndex | None = None,
    crew_context_index: CrewContextIndex | None = None,
    rotation_index: Mapping[str, tuple[FlightContext, ...]] | None = None,
    join_health: _JoinHealthCounters | None = None,
) -> FlightItem:
    flight_nid = _optional_string(row.get("scope_row_unique_id"))
    if flight_nid is None:
        raise LeonContractError("LEON MCP report row did not provide scope_row_unique_id.")
    augmented_index = augmented_index or AugmentedIndex(False, {}, 0, 0)
    crew_context_index = crew_context_index or CrewContextIndex(False, {})
    rotation_index = rotation_index if rotation_index is not None else {}
    leon_heavy = augmented_index.lookup(crew_code, row.get("unique_id"))
    leon_augmentation = augmented_index.lookup_raw(crew_code, row.get("unique_id"))
    unique_id = _optional_int(row.get("unique_id"))
    entries = (
        crew_context_index.by_flight.get(unique_id, ())
        if crew_context_index.available
        else ()
    )
    # EVN/SVX are airport codes in live data. Collect every route code we know
    # — the report row's [JL] preferred codes plus the flight-list context —
    # so the absolute rules fire when either source names the airport.
    flight_context = (
        crew_context_index.contexts.get(unique_id)
        if crew_context_index.available and unique_id is not None
        else None
    )
    route_airports = merge_route_airports(
        (
            _optional_string(row.get("jl_adep_preferred_code")),
            _optional_string(row.get("jl_ades_preferred_code")),
        ),
        (
            (flight_context.departure_airport, flight_context.arrival_airport)
            if flight_context
            else ()
        ),
    )
    if join_health is not None:
        # A hit is key-presence, not a non-None value: an ambiguous FTL value
        # still proves the identifiers joined.
        if augmented_index.available:
            join_health.augmented_attempts += 1
            if augmented_index.has_key(crew_code, row.get("unique_id")):
                join_health.augmented_hits += 1
        if crew_context_index.available:
            join_health.crew_context_attempts += 1
            if unique_id is not None and unique_id in crew_context_index.by_flight:
                join_health.crew_context_hits += 1
    derived_heavy, derived_reason = derive_heavy_detail(
        entries,
        _optional_string(row.get("acftType")),
        crew_context_index.tags_for(unique_id),
        route_airports=route_airports,
    )
    heavy_decision = decide_heavy(leon_heavy, derived_heavy, derived_reason)

    effective_heavy = heavy_decision.effective_heavy
    heavy_source = heavy_decision.heavy_source
    unknown_resolved = False
    unknown_resolution_reason: str | None = None
    # Rule 4 (owner rule set): with LEON silent, an over-threshold operating
    # count is final and never falls to the resolver — STEP 4 exists only for
    # the count rule's UNKNOWN outcome (rule 5).
    if effective_heavy is None and heavy_decision.derived_heavy is True:
        effective_heavy = True
        heavy_source = "LOCAL_RULE"
    # STEP 4 only runs where LEON genuinely returned no augmentation value.  When
    # the whole FTL index is unavailable we keep UNKNOWN rather than inventing a No.
    if effective_heavy is None and augmented_index.available:
        resolution = resolve_unknown_heavy(
            crew_context_index,
            rotation_index,
            unique_id,
            crew_code,
        )
        effective_heavy = resolution.effective_heavy
        # The badge marks a verdict the resolver ESTABLISHED, and it can only
        # establish a Yes: a No means "no qualifying rotation was found", which
        # is an absence of evidence, not a local resolution (owner ruling
        # 2026-08-19). Deterministic EVN/SVX/count verdicts never reach this
        # branch at all, so they can never carry it either.
        unknown_resolved = resolution.effective_heavy
        unknown_resolution_reason = resolution.reason
        heavy_source = "LOCAL_RULE"

    entry = _crew_entry(entries, crew_code)
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
        # The displayed Yes/No is the effective verdict, including any STEP 4 resolution.
        augmented_heavy=effective_heavy,
        leon_heavy=heavy_decision.leon_heavy,
        derived_heavy=heavy_decision.derived_heavy,
        effective_heavy=effective_heavy,
        heavy_source=heavy_source,
        heavy_reason=heavy_decision.heavy_reason,
        heavy_conflict=heavy_decision.heavy_conflict,
        leon_augmentation=leon_augmentation,
        is_training_position=is_training_position(entry.position if entry else position),
        is_training_function=is_training_function(entry.function if entry else None),
        unknown_resolved=unknown_resolved,
        unknown_resolution_reason=unknown_resolution_reason,
    )


def _crew_entry(
    entries: Sequence[CrewContextEntry],
    crew_code: str | None,
) -> CrewContextEntry | None:
    if not crew_code:
        return None
    normalized = crew_code.strip().upper()
    for entry in entries:
        if entry.crew_code and entry.crew_code.strip().upper() == normalized:
            return entry
    return None


def _optional_string(value: Any) -> str | None:
    # LENIENT by design (L-6 ruling 2026-08-18): report-row cells degrade to
    # None. Strict counterpart: crew_context._strict_string_or_none (raises on
    # a broken LEON contract). Same-name twin: local_answers._text. Keep the
    # semantics distinct; consolidation is Deliverable-3 material.
    return value.strip() if isinstance(value, str) and value.strip() else None


def _optional_int(value: Any) -> int | None:
    # Duplicate-by-design of local_answers._optional_int (L-6 ruling
    # 2026-08-18). Keep in sync until the Deliverable-3 parsing module.
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


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

"""LEON flight-list crew context used by the Heavy provenance engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
import logging
from typing import Any, Mapping, Sequence

from .config import LeonConfiguration
from .domain import buffered_query_dates
from .errors import LeonContractError, LeonResponseError
from .flight_query import _coerce_date, build_flight_list_query
from .graphql import LeonGraphQLExecutor
from .response_models import LeonFlight
from .token_provider import LeonAccessTokenProvider
from .transport import BearerAccessTokenHeaderBuilder, LeonHttpTransport


CREW_CONTEXT_CHUNK_DAYS = 7
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CrewContextEntry:
    pos_type: str | None
    position: str | None
    training_type: str | None
    crew_code: str | None = None
    crew_name: str | None = None
    # Work Schedule Function; "SFA" marks a cabin trainee.
    function: str | None = None


@dataclass(frozen=True)
class FlightContext:
    """Everything the Heavy rules and the UNKNOWN resolver need about one flight."""

    flight_nid: int
    start_time_utc: str | None
    end_time_utc: str | None
    flight_tags: tuple[str, ...]
    entries: tuple[CrewContextEntry, ...]


@dataclass(frozen=True)
class CrewContextIndex:
    available: bool
    by_flight: Mapping[int, tuple[CrewContextEntry, ...]]
    contexts: Mapping[int, FlightContext] = field(default_factory=dict)

    def tags_for(self, flight_nid: int | None) -> tuple[str, ...] | None:
        """Return the flight's tags, or None when this flight was never indexed."""

        if not self.available or flight_nid is None:
            return None
        context = self.contexts.get(flight_nid)
        return context.flight_tags if context is not None else None


def build_crew_context_index(
    flights: Sequence[LeonFlight | Mapping[str, object]],
) -> CrewContextIndex:
    """Build the immutable flight-NID to crew-context index in one pass."""

    by_flight: dict[int, tuple[CrewContextEntry, ...]] = {}
    contexts: dict[int, FlightContext] = {}
    for flight in flights:
        if isinstance(flight, LeonFlight):
            flight_nid_value = flight.flight_nid
            crew_list_value = flight.crew_list
            start_time_value: object = flight.start_time_utc
            end_time_value: object = flight.end_time_utc
            flight_tags_value: object = flight.flight_tags
        elif isinstance(flight, Mapping):
            flight_nid_value = flight.get("flightNid")
            crew_list_value = flight.get("crewList")
            start_time_value = flight.get("startTimeUTC")
            end_time_value = flight.get("endTimeUTC")
            flight_tags_value = flight.get("flightTags")
        else:
            raise LeonContractError("LEON flight item had an invalid shape.")

        flight_nid = _normalize_flight_nid(flight_nid_value)
        if crew_list_value is None:
            crew_list = []
        elif isinstance(crew_list_value, list):
            crew_list = crew_list_value
        else:
            raise LeonContractError("LEON flight crewList contained an invalid list.")
        entries: list[CrewContextEntry] = []
        for crew in crew_list:
            if not isinstance(crew, Mapping):
                raise LeonContractError("LEON flight crewList contained an invalid crew entry.")
            position_object = crew.get("position")
            if position_object is not None and not isinstance(position_object, Mapping):
                raise LeonContractError("LEON flight position contained an invalid object.")
            contact_object = crew.get("contact")
            if contact_object is not None and not isinstance(contact_object, Mapping):
                raise LeonContractError("LEON flight contact contained an invalid object.")
            work_schedule_object = crew.get("workSchedule")
            if work_schedule_object is not None and not isinstance(work_schedule_object, Mapping):
                raise LeonContractError("LEON flight workSchedule contained an invalid object.")
            entries.append(
                CrewContextEntry(
                    pos_type=_optional_string(
                        position_object.get("posType") if position_object else None
                    ),
                    position=_optional_string(
                        position_object.get("name") if position_object else None
                    ),
                    training_type=_optional_string(crew.get("flightTrainingType")),
                    crew_code=_normalized_crew_code(
                        contact_object.get("personCode") if contact_object else None
                    ),
                    crew_name=_contact_name(contact_object),
                    function=_optional_string(
                        work_schedule_object.get("function") if work_schedule_object else None
                    ),
                )
            )
        by_flight[flight_nid] = tuple(entries)
        contexts[flight_nid] = FlightContext(
            flight_nid=flight_nid,
            start_time_utc=_optional_string(start_time_value),
            end_time_utc=_optional_string(end_time_value),
            flight_tags=_flight_tag_labels(flight_tags_value),
            entries=tuple(entries),
        )
    return CrewContextIndex(available=True, by_flight=by_flight, contexts=contexts)


def fetch_crew_context_index(
    configuration: LeonConfiguration,
    transport: LeonHttpTransport,
    token_provider: LeonAccessTokenProvider,
    from_date: str,
    to_date: str,
) -> CrewContextIndex:
    """Fetch the buffered flight-list window in contiguous weekly chunks."""

    validated_from = _coerce_date(from_date)
    validated_to = _coerce_date(to_date)
    if validated_from > validated_to:
        raise LeonContractError("Crew context query start date must not be after end date.")
    buffered_from, buffered_to = buffered_query_dates(
        validated_from.isoformat(),
        validated_to.isoformat(),
    )
    buffered_start = _coerce_date(buffered_from)
    buffered_end = _coerce_date(buffered_to)
    executor = LeonGraphQLExecutor(
        configuration,
        transport,
        token_provider,
        BearerAccessTokenHeaderBuilder(),
    )
    flights: list[Mapping[str, object]] = []
    chunk_count = 0
    chunk_start = buffered_start
    include_crew_function = True
    while chunk_start <= buffered_end:
        chunk_end = min(
            chunk_start + timedelta(days=CREW_CONTEXT_CHUNK_DAYS - 1),
            buffered_end,
        )
        try:
            payload = executor.execute_query(
                build_flight_list_query(
                    chunk_start,
                    chunk_end,
                    include_crew_function=include_crew_function,
                )
            )
        except LeonResponseError:
            if not include_crew_function:
                raise
            # LEON rejected the optional Work Schedule Function selection.  Cabin
            # trainee detection degrades to "unknown" rather than failing the report.
            logger.warning(
                "LEON rejected the crew Work Schedule Function selection; "
                "cabin trainee detection is disabled for this report."
            )
            include_crew_function = False
            payload = executor.execute_query(
                build_flight_list_query(chunk_start, chunk_end, include_crew_function=False)
            )
        flights.extend(_parse_crew_context_flights(payload))
        chunk_count += 1
        chunk_start = chunk_end + timedelta(days=1)

    index = build_crew_context_index(flights)
    # Keep this aggregate log free of crew identifiers and upstream payloads.
    logger.info(
        "LEON crew context period=%s..%s chunks=%d flights_indexed=%d crew_function=%s unavailable=%s",
        validated_from.isoformat(),
        validated_to.isoformat(),
        chunk_count,
        len(index.by_flight),
        include_crew_function,
        not index.available,
    )
    return index


def _parse_crew_context_flights(
    data: Mapping[str, object],
) -> list[Mapping[str, object]]:
    """Parse only the flight identity and crew context needed by this index."""

    if not isinstance(data, Mapping):
        raise LeonResponseError("LEON GraphQL data had an invalid shape.")
    flight_list = data.get("flightList")
    if not isinstance(flight_list, list):
        raise LeonResponseError("LEON GraphQL data did not contain a flightList array.")

    flights: list[Mapping[str, object]] = []
    for item in flight_list:
        if not isinstance(item, Mapping):
            raise LeonResponseError("LEON flightList contained an invalid flight item.")
        crew_list = item.get("crewList")
        if crew_list is not None and not isinstance(crew_list, list):
            raise LeonContractError("LEON flight crewList contained an invalid list.")
        flight_tags = item.get("flightTags")
        if flight_tags is not None and not isinstance(flight_tags, list):
            raise LeonContractError("LEON flight flightTags contained an invalid list.")
        flights.append(
            {
                "flightNid": _normalize_flight_nid(item.get("flightNid")),
                "crewList": crew_list,
                "startTimeUTC": item.get("startTimeUTC"),
                "endTimeUTC": item.get("endTimeUTC"),
                "flightTags": flight_tags,
            }
        )
    return flights


def _flight_nid_as_int(flight: LeonFlight | Mapping[str, object]) -> int:
    if isinstance(flight, LeonFlight):
        value: Any = flight.flight_nid
    elif isinstance(flight, Mapping):
        value = flight.get("flightNid")
    else:
        value = None
    return _normalize_flight_nid(value)


def _normalize_flight_nid(value: object) -> int:
    if isinstance(value, bool):
        raise LeonContractError("LEON flight item had an invalid flightNid.")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError as exc:
            raise LeonContractError("LEON flight item had an invalid flightNid.") from exc
    raise LeonContractError("LEON flight item had an invalid flightNid.")


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise LeonContractError("LEON flight crew context contained an invalid string.")
    normalized = value.strip()
    return normalized or None


def _normalized_crew_code(value: object) -> str | None:
    """Crew codes are matched against the FTL index, which upper-cases them."""

    code = _optional_string(value)
    return code.upper() if code else None


def _contact_name(contact: Mapping[str, object] | None) -> str | None:
    if not contact:
        return None
    parts = [
        part
        for part in (_optional_string(contact.get("name")), _optional_string(contact.get("surname")))
        if part
    ]
    return " ".join(parts) or None


def _flight_tag_labels(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise LeonContractError("LEON flight flightTags contained an invalid list.")
    labels: list[str] = []
    for tag in value:
        if isinstance(tag, str):
            label = tag.strip()
        elif isinstance(tag, Mapping):
            label = _optional_string(tag.get("label")) or ""
        else:
            raise LeonContractError("LEON flight flightTags contained an invalid tag.")
        if label:
            labels.append(label.upper())
    return tuple(labels)

"""LEON FTL crew augmentation enrichment for Crew Hours."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import logging
from typing import Any, Mapping, Sequence

from .config import LeonConfiguration
from .domain import buffered_query_dates
from .errors import LeonContractError, LeonResponseError
from .flight_query import _coerce_date
from .graphql import LeonGraphQLExecutor
from .token_provider import LeonAccessTokenProvider
from .transport import (
    BearerAccessTokenHeaderBuilder,
    LeonHttpTransport,
)


logger = logging.getLogger(__name__)

AUGMENTED_TRUE = frozenset({"augmented", "doubled", "tripled"})
AUGMENTED_FALSE = frozenset({"normal"})


@dataclass(frozen=True)
class AugmentedIndex:
    available: bool
    by_crew_sector: Mapping[tuple[str, int], bool | None]
    resolved_count: int
    ambiguous_count: int

    def lookup(self, crew_code: str | None, flight_nid: str | None) -> bool | None:
        if not self.available:
            return None
        normalized_code = _normalize_crew_code(crew_code)
        normalized_flight_nid = _normalize_tr_nid(flight_nid)
        if normalized_code is None or normalized_flight_nid is None:
            return None
        return self.by_crew_sector.get((normalized_code, normalized_flight_nid))


def build_augmented_index(rows: Sequence[Mapping[str, Any]] | Mapping[str, Any]) -> AugmentedIndex:
    """Build a deterministic crew-code/sector-id augmentation index."""

    duty_rows = _coerce_duty_rows(rows)
    values_by_key: dict[tuple[str, int], set[bool | None]] = {}
    unrecognised_count = 0

    for duty in duty_rows:
        if not isinstance(duty, Mapping):
            raise LeonContractError("LEON FTL duty list contained an invalid duty row.")

        augmentation, recognized = _map_augmentation(duty.get("crewAugmentation"))
        if not recognized:
            unrecognised_count += 1

        crew_member = duty.get("crewMember")
        crew_code = (
            crew_member.get("code")
            if isinstance(crew_member, Mapping)
            else None
        )
        normalized_code = _normalize_crew_code(crew_code)
        sectors = duty.get("sectorList")
        if sectors is None:
            continue
        if not isinstance(sectors, list):
            raise LeonContractError("LEON FTL duty list contained an invalid sector list.")

        for sector in sectors:
            if not isinstance(sector, Mapping):
                raise LeonContractError("LEON FTL duty list contained an invalid sector.")
            normalized_tr_nid = _normalize_tr_nid(sector.get("trNid"))
            if normalized_code is None or normalized_tr_nid is None:
                continue
            key = (normalized_code, normalized_tr_nid)
            values_by_key.setdefault(key, set()).add(augmentation)

    if unrecognised_count:
        logger.warning(
            "LEON FTL augmented enrichment encountered %d unrecognised or missing enum value(s).",
            unrecognised_count,
        )

    by_crew_sector: dict[tuple[str, int], bool | None] = {}
    ambiguous_count = 0
    resolved_count = 0
    for key, values in values_by_key.items():
        if len(values) == 1:
            value = next(iter(values))
            by_crew_sector[key] = value
            if value is not None:
                resolved_count += 1
        else:
            ambiguous_count += 1
            by_crew_sector[key] = None

    return AugmentedIndex(
        available=True,
        by_crew_sector=by_crew_sector,
        resolved_count=resolved_count,
        ambiguous_count=ambiguous_count,
    )


def fetch_augmented_index(
    configuration: LeonConfiguration,
    transport: LeonHttpTransport,
    token_provider: LeonAccessTokenProvider,
    from_date: str,
    to_date: str,
) -> AugmentedIndex:
    """Fetch one bulk FTL duty-list window and build its local index."""

    validated_from = _coerce_date(from_date)
    validated_to = _coerce_date(to_date)
    if validated_from > validated_to:
        raise LeonContractError("Crew augmentation query start date must not be after end date.")
    buffered_from, buffered_to = buffered_query_dates(
        validated_from.isoformat(),
        validated_to.isoformat(),
    )
    query = build_duty_list_query(buffered_from, buffered_to)
    executor = LeonGraphQLExecutor(
        configuration,
        transport,
        token_provider,
        BearerAccessTokenHeaderBuilder(),
    )
    payload = executor.execute_query(query)
    duty_rows = _extract_duty_rows(payload)
    index = build_augmented_index(duty_rows)
    logger.info(
        "LEON FTL augmented enrichment period=%s..%s duty_rows=%d resolved=%d ambiguous=%d unavailable=%s",
        validated_from.isoformat(),
        validated_to.isoformat(),
        len(duty_rows),
        index.resolved_count,
        index.ambiguous_count,
        not index.available,
    )
    return index


def build_duty_list_query(start: date | str, end: date | str) -> str:
    """Build the validated FTL duty-list GraphQL query."""

    start_date = _coerce_date(start)
    end_date = _coerce_date(end)
    if start_date > end_date:
        raise LeonContractError("Crew augmentation query start date must not be after end date.")
    return f'''query {{
  ftl {{
    dutyList(timeInterval: {{ start: "{start_date.isoformat()}T00:00:00Z", end: "{end_date.isoformat()}T23:59:59Z" }}) {{
      crewMember {{ code loginNid }}
      crewAugmentation
      sectorList {{ trNid }}
    }}
  }}
}}'''


def _coerce_duty_rows(
    rows: Sequence[Mapping[str, Any]] | Mapping[str, Any],
) -> list[Any]:
    if isinstance(rows, Mapping):
        return _extract_duty_rows(rows)
    if isinstance(rows, (str, bytes)) or not isinstance(rows, Sequence):
        raise LeonContractError("LEON FTL duty list was not an array.")
    return list(rows)


def _extract_duty_rows(payload: Mapping[str, Any]) -> list[Any]:
    if not isinstance(payload, Mapping):
        raise LeonResponseError("LEON GraphQL response did not contain an FTL object.")
    ftl = payload.get("ftl")
    if not isinstance(ftl, Mapping):
        raise LeonResponseError("LEON GraphQL response did not contain an FTL object.")
    duty_list = ftl.get("dutyList")
    if not isinstance(duty_list, list):
        raise LeonResponseError("LEON GraphQL response did not contain a dutyList array.")
    return duty_list


def _map_augmentation(value: Any) -> tuple[bool | None, bool]:
    normalized = value.strip().casefold() if isinstance(value, str) else None
    if normalized in AUGMENTED_TRUE:
        return True, True
    if normalized in AUGMENTED_FALSE:
        return False, True
    return None, False


def _normalize_crew_code(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().upper()
    return normalized or None


def _normalize_tr_nid(value: Any) -> int | None:
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

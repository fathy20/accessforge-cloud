"""Compare the local FDP model with LEON's own FTL engine, duty by duty.

LEON's ``ftl.dutyList`` exposes what its FTL engine computed for every
member-duty: ``fdpStartTime``/``fdpEndTime``/``fdpLength``, ``maxFdpLength``,
``fdpExtension``, ``sectorCount``, ``isAcclimated``, ``localTimeOffset``,
``restFacility``, ``crewAugmentation`` and per-sector ``reportingTime``/
``blockStartTime``. That is the ground truth this tool measures against:

* report time  — is LEON's FDP start really 1:30 before the first block-off?
* off duty     — is LEON's FDP end really 0:30 after the last block-on?
* the limit    — does our Table A/B lookup (band from LEON's own local offset,
                 LEON's sector count, LEON's acclimatisation flag) equal
                 LEON's ``maxFdpLength`` minus any ``fdpExtension``?
* augmentation — how often does our ``fdpLength > limit`` observation coincide
                 with LEON's ``crewAugmentation``? This is a model-vs-LEON
                 agreement statistic and nothing more.

**It does not test Heavy.** Heavy is a Red Sea business/policy verdict — the
owner's rulings, LEON's ``crewAugmentation`` and the approved precedence table
decide it. The EgyptAir OM sets FDP limits, extensions, rest and positioning
rules; it never defines Heavy and never mentions an allowance. Neither
direction of implication holds: only 49 of 779 augmented June duties exceed
the base limit (median about 5 h below it — extra crew is also carried for
training, ferry, familiarisation and standby cover), and a duty over the base
limit may be legal by split duty, commander's discretion, the cabin +1:00 or
the positioning-landings exclusion without any extra crew at all. The
``our_needs_augmentation`` column is that inequality, not a verdict; nothing
here may change a verdict, a credit, an export cell or a total.

Trap in the output, deliberately left in place: **``leon_basic_max`` is not a
basic limit.** It is ``maxFdpLength - fdpExtension``, and ``fdpExtension`` is
0:00 in 1,770 of 1,770 June duties — so on an augmented duty it is LEON's
POST-augmentation ceiling (a flat 15:00 cockpit / 16:00 cabin), not the base
table value. Compare against ``our_limit`` for the base figure. The column
name is unchanged on purpose: it is written into ``leon_duties.csv`` and
downstream analysis reads it.

Usage (read-only against LEON, reads LEON_* from .env like the app):

    python -m backend.statistics.crew_hours.tools.fdp_leon_compare --months 2026-06 --out DIR
"""

from __future__ import annotations

import argparse
import calendar
import csv
import json
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import backend.config  # noqa: F401

from ..augmented import MAX_DUTY_LIST_INTERVAL_DAYS
from ..config import load_leon_configuration
from ..fdp import (
    DEFAULT_TABLES,
    POST_FLIGHT_DUTY,
    REPORT_BEFORE_DEPARTURE,
    FdpTables,
    start_band,
    tables_for,
)
from ..graphql import LeonGraphQLExecutor
from ..token_provider import LeonAccessTokenProvider
from ..transport import HttpxLeonTransport
from .id_probe import BearerAccessTokenHeaderBuilder

QUERY = """query {{
  ftl {{
    dutyList(timeInterval: {{ start: "{start}T00:00:00Z", end: "{end}T23:59:59Z" }}) {{
      crewMember {{ code }}
      crewAugmentation
      isCabinCrew
      isAcclimated
      localTimeOffset
      restFacility
      hasViolation
      sectorCount
      dutyStartTime
      dutyEndTime
      fdpStartTime
      fdpEndTime
      fdpLength
      maxFdpLength
      fdpExtension
      splitDutyTime
      discretionLength
      blockStartTime
      blockEndTime
      previousDutyEndTime
      homeAirport {{ icao }}
      startAirport {{ icao }}
      sectorList {{ trNid reportingTime startAirport {{ icao }} endAirport {{ icao }} }}
    }}
  }}
}}"""


def _parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    text = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _parse_duration(value: Any) -> timedelta | None:
    """LEON TimeLong: seconds, or 'H:MM' / 'HH:MM:SS'."""

    if value is None:
        return None
    if isinstance(value, (int, float)):
        return timedelta(seconds=float(value))
    text = str(value).strip()
    if not text:
        return None
    if text.lstrip("-").isdigit():
        return timedelta(seconds=int(text))
    negative = text.startswith("-")
    parts = text.lstrip("-").split(":")
    try:
        numbers = [int(p) for p in parts]
    except ValueError:
        return None
    hours, minutes = numbers[0], numbers[1] if len(numbers) > 1 else 0
    seconds = numbers[2] if len(numbers) > 2 else 0
    result = timedelta(hours=hours, minutes=minutes, seconds=seconds)
    return -result if negative else result


def _parse_offset(value: Any) -> timedelta | None:
    """TimezoneOffset: seconds, minutes, or '+03:00'."""

    if value is None:
        return None
    if isinstance(value, (int, float)):
        seconds = float(value)
        # Heuristic: |v| <= 14*60 -> minutes; otherwise seconds.
        return timedelta(minutes=seconds) if abs(seconds) <= 14 * 60 else timedelta(seconds=seconds)
    text = str(value).strip()
    sign = -1 if text.startswith("-") else 1
    text = text.lstrip("+-")
    if ":" in text:
        hours, minutes = text.split(":")[:2]
        return sign * timedelta(hours=int(hours), minutes=int(minutes))
    if text.isdigit():
        return _parse_offset(sign * int(text))
    return None


def _fmt(delta: timedelta | None) -> str:
    if delta is None:
        return ""
    total = int(delta.total_seconds() // 60)
    sign = "-" if total < 0 else ""
    total = abs(total)
    return f"{sign}{total // 60}:{total % 60:02d}"


def month_range(year_month: str) -> tuple[date, date]:
    year, month = (int(part) for part in year_month.split("-"))
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def fetch_duties(executor: LeonGraphQLExecutor, start: date, end: date) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    chunk_start = start
    while chunk_start <= end:
        chunk_end = min(chunk_start + timedelta(days=MAX_DUTY_LIST_INTERVAL_DAYS - 1), end)
        payload = executor.execute_query(QUERY.format(start=chunk_start.isoformat(), end=chunk_end.isoformat()))
        duties = (payload.get("ftl") or {}).get("dutyList") or []
        rows.extend(d for d in duties if isinstance(d, Mapping))
        chunk_start = chunk_end + timedelta(days=1)
    return rows


def analyse(duty: Mapping[str, Any], tables: FdpTables) -> dict[str, Any]:
    fdp_start = _parse_dt(duty.get("fdpStartTime"))
    fdp_end = _parse_dt(duty.get("fdpEndTime"))
    block_start = _parse_dt(duty.get("blockStartTime"))
    block_end = _parse_dt(duty.get("blockEndTime"))
    previous_end = _parse_dt(duty.get("previousDutyEndTime"))
    fdp_length = _parse_duration(duty.get("fdpLength"))
    max_fdp = _parse_duration(duty.get("maxFdpLength"))
    extension = _parse_duration(duty.get("fdpExtension")) or timedelta(0)
    offset = _parse_offset(duty.get("localTimeOffset"))
    sectors = duty.get("sectorCount")
    acclimated = duty.get("isAcclimated")
    sector_list = duty.get("sectorList") or []
    first_report = _parse_dt(sector_list[0].get("reportingTime")) if sector_list else None

    row: dict[str, Any] = {
        "crew_code": (duty.get("crewMember") or {}).get("code"),
        "is_cabin": duty.get("isCabinCrew"),
        "crew_augmentation": duty.get("crewAugmentation"),
        "rest_facility": duty.get("restFacility"),
        "has_violation": duty.get("hasViolation"),
        "home": (duty.get("homeAirport") or {}).get("icao"),
        "start_airport": (duty.get("startAirport") or {}).get("icao"),
        "route": "-".join(
            f"{(s.get('startAirport') or {}).get('icao', '?')}>{(s.get('endAirport') or {}).get('icao', '?')}"
            for s in sector_list
        ),
        "fdp_start": duty.get("fdpStartTime"),
        "fdp_end": duty.get("fdpEndTime"),
        "leon_fdp": _fmt(fdp_length),
        "leon_max_fdp": _fmt(max_fdp),
        "leon_extension": _fmt(extension),
        "leon_split": _fmt(_parse_duration(duty.get("splitDutyTime"))),
        "leon_discretion": _fmt(_parse_duration(duty.get("discretionLength"))),
        "sectors": sectors,
        "is_acclimated": acclimated,
        "local_offset": duty.get("localTimeOffset"),
        "report_before_block": _fmt(block_start - fdp_start) if block_start and fdp_start else "",
        "post_flight_after_block": _fmt(fdp_end - block_end) if block_end and fdp_end else "",
        "first_sector_report_vs_fdp_start": _fmt(first_report - fdp_start) if first_report and fdp_start else "",
        "our_band": "",
        "our_table": "",
        "our_limit": "",
        # Misnamed, and kept so (it ships in leon_duties.csv): `fdpExtension`
        # is 0:00 in every observed duty, so on an augmented duty this is
        # LEON's POST-augmentation ceiling, not a base limit. The base table
        # figure is `our_limit` above.
        "leon_basic_max": _fmt(max_fdp - extension) if max_fdp is not None else "",
        "limit_match": "",
        "our_needs_augmentation": "",
        "leon_says_augmented": duty.get("crewAugmentation") not in (None, "normal", "NORMAL", "Normal"),
    }

    if fdp_start is None or offset is None or not isinstance(sectors, int) or sectors < 1:
        row["limit_match"] = "insufficient_data"
        return row

    local_start = fdp_start.astimezone(timezone(offset))
    band = start_band(local_start)
    row["our_band"] = band
    limit: timedelta | None
    if acclimated is False and previous_end is not None:
        rest = fdp_start - previous_end
        rest_band = tables.rest_band(rest)
        row["our_table"] = f"B({_fmt(rest)})"
        limit = tables.table_b_limit(rest_band, sectors) if rest_band else None
    else:
        row["our_table"] = "A" if acclimated is not False else "A(assumed)"
        limit = tables.table_a_limit(band, sectors)
    if limit is not None and duty.get("isCabinCrew"):
        limit = limit + timedelta(hours=1)
    row["our_limit"] = _fmt(limit)
    if limit is None or max_fdp is None:
        row["limit_match"] = "no_limit"
    else:
        basic = max_fdp - extension
        row["limit_match"] = "match" if abs((basic - limit).total_seconds()) < 60 else "mismatch"
    if fdp_length is not None and limit is not None:
        row["our_needs_augmentation"] = fdp_length > limit
    return row


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--months", nargs="+", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--tables", default=None, help="om-2009 (default) | ecar-2016")
    args = parser.parse_args(argv)
    tables = tables_for(args.tables) if args.tables else DEFAULT_TABLES

    configuration = load_leon_configuration()
    transport = HttpxLeonTransport()
    executor = LeonGraphQLExecutor(
        configuration, transport, LeonAccessTokenProvider(configuration, transport), BearerAccessTokenHeaderBuilder()
    )

    rows: list[dict[str, Any]] = []
    for year_month in args.months:
        start, end = month_range(year_month)
        print(f"Fetching FTL duties {start}..{end} ...", file=sys.stderr, flush=True)
        duties = fetch_duties(executor, start, end)
        print(f"  {len(duties)} member-duties", file=sys.stderr, flush=True)
        for duty in duties:
            row = analyse(duty, tables)
            row["month"] = year_month
            rows.append(row)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if rows:
        with (out / "leon_duties.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    flown = [r for r in rows if r["leon_fdp"]]
    summary = {
        "duties": len(rows),
        "with_fdp": len(flown),
        "report_before_block": dict(Counter(r["report_before_block"] for r in flown).most_common(6)),
        "post_flight_after_block": dict(Counter(r["post_flight_after_block"] for r in flown).most_common(6)),
        "first_sector_report_vs_fdp_start": dict(Counter(r["first_sector_report_vs_fdp_start"] for r in flown).most_common(4)),
        "limit_match": dict(Counter(r["limit_match"] for r in flown)),
        "limit_match_cockpit_only": dict(Counter(r["limit_match"] for r in flown if not r["is_cabin"])),
        "acclimated": dict(Counter(str(r["is_acclimated"]) for r in flown)),
        "local_offset": dict(Counter(str(r["local_offset"]) for r in flown).most_common(5)),
        "rest_facility": dict(Counter(str(r["rest_facility"]) for r in flown)),
        "crew_augmentation": dict(Counter(str(r["crew_augmentation"]) for r in flown)),
        "our_needs_vs_leon_augmented": dict(
            Counter(f"ours={r['our_needs_augmentation']} leon={r['leon_says_augmented']}" for r in flown if r["our_needs_augmentation"] != "")
        ),
        "mismatch_examples": [
            {k: r[k] for k in ("month", "crew_code", "is_cabin", "route", "fdp_start", "sectors", "is_acclimated", "local_offset", "our_band", "our_table", "our_limit", "leon_max_fdp", "leon_extension", "leon_basic_max", "crew_augmentation")}
            for r in flown if r["limit_match"] == "mismatch"
        ][:25],
    }
    (out / "leon_compare_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Answer operational questions directly from LEON's MCP Report Wizard.

Wingman lives on LEON's GraphQL endpoint.  The MCP endpoint is a separate host
that stays up independently, and it already carries crew codes, names, flight
numbers, dates and block times.  Roster and hours questions are therefore
answerable without Wingman at all — and with a stronger citation, because the
answer points at real report rows rather than at an assistant's prose.

Anything this module cannot answer returns None so the caller can fall through
to Wingman.  It never guesses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Callable, Mapping, Sequence

from ..statistics.crew_hours.crew_context import (
    CrewContextEntry,
    CrewContextIndex,
    FlightContext,
)
from ..statistics.crew_hours.domain import normalize_report_row
from ..statistics.crew_hours.unknown_resolver import build_rotation_index
from ..statistics.crew_hours.heavy import (
    classify_flight_heavy,
    operating_cabin_count,
    operating_cockpit_count,
)
from ..statistics.crew_hours.mcp_report import OfficialMcpReport
from ..statistics.crew_hours.positions import (
    CABIN_POS_TYPE,
    COCKPIT_POS_TYPE,
    HEAVY_CABIN_THRESHOLD,
    HEAVY_COCKPIT_THRESHOLD,
)
from ..statistics.crew_hours.service import _position_group
from .schemas import CopilotAnswer, CopilotCitation, CopilotFact

Intent = str
INTENT_ROSTER = "ROSTER"
INTENT_HOURS = "HOURS"
INTENT_HEAVY = "HEAVY"

# Keep both languages: the toolkit ships Arabic-first.
_ROSTER_WORDS = ("roster", "rostered", "who is on", "who's on", "who is flying", "schedule",
                 "الجدول", "مين طاير", "من على")
_HOURS_WORDS = ("hours", "logged", "block time", "total", "ساعات", "سجل")
_HEAVY_WORDS = ("heavy", "augmented", "هيفي", "معزز")

_ISO_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")

# A message that is *nothing but* a flight number and a date -- "RSX331 on
# 2026-06-02" -- is someone answering the "Which flight?" prompt. Without this
# it matches no keyword, falls out of local routing entirely, and ends up at
# Wingman, which cannot answer it either.
#
# CAVEAT -- READ BEFORE ADDING ANOTHER CLARIFYING QUESTION.
# This is a heuristic, not slot filling. It is only sound while HEAVY is the
# SOLE intent that asks a clarifying question, because a bare flight+date can
# then only be answering that one. The moment a second clarifying question
# exists (roster or hours asking "which day?", "which crew?", ...), a bare
# answer becomes ambiguous and this rule will silently misroute it to HEAVY.
# At that point replace this with a real pending-intent round trip: have the
# clarifying answer carry the intent it is waiting on (CopilotAnswer ->
# frontend -> next request), and consult that here instead of guessing.
# Anchored at both ends on purpose: anything with extra words is left to the
# keyword rules above, so "hours for RSX331 on 2026-06-02" still reads as HOURS.
_BARE_FLIGHT = re.compile(
    r"^\W*([A-Z]{2,3}\s?-?\s?\d{1,4})\W+(?:on\s+)?(\d{4}-\d{2}-\d{2})\W*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Period:
    start: date
    end: date
    label: str


def detect_intent(question: str) -> Intent | None:
    text = question.strip().casefold()
    if not text:
        return None
    # Heavy is checked first: "is this flight augmented" also contains no
    # roster/hours words, but "heavy hours" should still read as Heavy.
    if any(word in text for word in _HEAVY_WORDS):
        return INTENT_HEAVY
    if any(word in text for word in _ROSTER_WORDS):
        return INTENT_ROSTER
    if any(word in text for word in _HOURS_WORDS):
        return INTENT_HOURS
    # Checked last, so an explicit keyword always wins over the bare pattern.
    if _BARE_FLIGHT.match(question.strip()):
        return INTENT_HEAVY
    return None


def resolve_period(question: str, today: date) -> Period | None:
    text = question.strip().casefold()
    explicit = _ISO_DATE.search(question)
    if explicit:
        try:
            parsed = date.fromisoformat(explicit.group(1))
        except ValueError:
            return None
        return Period(parsed, parsed, parsed.isoformat())
    if "tomorrow" in text or "غدا" in text or "بكرة" in text:
        day = today + timedelta(days=1)
        return Period(day, day, "tomorrow")
    if "yesterday" in text or "امبارح" in text or "أمس" in text:
        day = today - timedelta(days=1)
        return Period(day, day, "yesterday")
    if "today" in text or "اليوم" in text:
        return Period(today, today, "today")
    if "this week" in text or "الاسبوع" in text or "الأسبوع" in text:
        start = today - timedelta(days=today.weekday())
        return Period(start, start + timedelta(days=6), "this week")
    if "this month" in text or "الشهر" in text:
        return Period(today.replace(day=1), today, "this month")
    return None


def answer_locally(
    question: str,
    *,
    today: date,
    fetch_report: Callable[[str, str], OfficialMcpReport],
) -> CopilotAnswer | None:
    """Return a grounded answer, or None to let Wingman handle the question."""

    intent = detect_intent(question)
    if intent is None:
        return None
    period = resolve_period(question, today)
    if intent == INTENT_HEAVY:
        return _heavy_answer(question, period, fetch_report)
    if period is None:
        return None

    report = fetch_report(period.start.isoformat(), period.end.isoformat())
    if intent == INTENT_ROSTER:
        return _roster_answer(report, period)
    return _hours_answer(report, period, question)


_FLIGHT_NUMBER = re.compile(r"\b([A-Z]{2,3}\s?-?\s?\d{1,4})\b")


def _heavy_answer(
    question: str,
    period: Period | None,
    fetch_report: Callable[[str, str], OfficialMcpReport],
) -> CopilotAnswer | None:
    """Answer Heavy from the MCP report's own crew positions and flight tags.

    This is the local rule only.  LEON's own crewAugmentation value lives on
    the FTL GraphQL endpoint, and the report carries no flightTrainingType or
    Work Schedule Function, so LINE_TRAINING/LINE_CHECK and SFA cabin trainees
    cannot be excluded here.  The answer says so rather than implying parity.
    """

    match = _FLIGHT_NUMBER.search(question.upper())
    if match is None or period is None:
        # Same ask LEON's own assistant makes: it cannot answer cold either.
        return CopilotAnswer(
            text=(
                "Which flight? Give me the flight number and the date "
                "(for example \"RSX431 on 2026-06-02\") and I will check the "
                "operating crew on that sector."
            ),
        )

    wanted = match.group(1).replace(" ", "").replace("-", "")
    # M-1 ruling (2026-08-18): fetch one day beyond the asked period on both
    # sides. The fetcher trims by DUTY-ATTRIBUTED date, so a cross-midnight
    # neighbour (or the asked leg itself, when a rider difference re-attributes
    # it to the previous day's duty) lands outside a single-day fetch. The
    # extra rows only feed the STEP-4 index; the answer still targets the
    # asked flight on the asked date via the row's own calendar date below.
    report = fetch_report(
        (period.start - timedelta(days=1)).isoformat(),
        (period.end + timedelta(days=1)).isoformat(),
    )
    rows = [
        row
        for row in report.rows
        if (_text(row.get("flightNo")) or "").upper().replace(" ", "").replace("-", "")
        == wanted
        and _row_in_period(row, period)
    ]
    if not rows:
        return CopilotAnswer(
            text=(
                f"No flight {wanted} on {period.start.isoformat()} in the LEON report. "
                "Check the number or the date."
            ),
            citation=CopilotCitation(
                tone="unresolved",
                headline=f"{wanted} — not found",
                facts=[CopilotFact(label="Date", value=period.start.isoformat(), raw=True)],
                source=_source(period),
            ),
        )

    # A flight number can appear on several report rows and some carry no crew
    # at all, so take the one that actually lists the operating crew.
    row = max(rows, key=lambda candidate: len(_entries_from_row(candidate)))
    entries = _entries_from_row(row)

    # ONE engine for every surface (owner ruling 2026-08-17): the same facade
    # the Crew Hours report uses. EVN/SVX are flight-level absolutes — EVN
    # vetoes even a cockpit-count Yes — and STEP 4 (the rotation rule) runs
    # here too, over an index built from the same report rows. LEON's FTL
    # augmentation value is not reachable on this path, so leon_heavy is None.
    index = _context_index_from_report(report)
    adep = _text(row.get("jl_adep_preferred_code"))
    ades = _text(row.get("jl_ades_preferred_code"))
    verdict, reason_code = classify_flight_heavy(
        index,
        build_rotation_index(index),
        _row_flight_nid(row),
        aircraft_type=_text(row.get("acftType")),
        # The report row's own codes, not only the ones the context copied:
        # one airport can arrive as IATA here and ICAO there, and the facade
        # must see every form or an ICAO-coded SVX leg reads as Not Heavy.
        route_airports=(adep, ades),
    )
    cockpit = operating_cockpit_count(entries)
    cabin = operating_cabin_count(entries)
    reason = _describe_reason(
        reason_code, adep=adep, ades=ades, cockpit=cockpit, cabin=cabin
    )

    if verdict is None:
        return CopilotAnswer(
            text=(
                f"{wanted} on {period.start.isoformat()}: the LEON report lists no crew "
                "positions for that sector, so Heavy cannot be determined."
            ),
            citation=CopilotCitation(
                tone="unresolved",
                headline=f"{wanted} — indeterminate",
                facts=[CopilotFact(label="Rule", value=reason, raw=True)],
                source=_source(period),
            ),
        )

    unique_id = row.get("unique_id") or row.get("scope_row_unique_id")
    return CopilotAnswer(
        text=(
            f"{wanted} on {period.start.isoformat()}: "
            f"{'Heavy' if verdict else 'Not Heavy'} by the local rule "
            f"({reason}). Operating crew {cockpit} cockpit / {cabin} cabin. "
            "LEON's own augmentation value is not reachable right now, and the "
            "report carries no training-flight flag, so trainees on a training "
            "sector are still counted."
        ),
        citation=CopilotCitation(
            tone="heavy" if verdict else "resolved",
            headline=f"{wanted} — {period.start.isoformat()}",
            facts=[
                CopilotFact(label="Rule", value=reason, raw=True),
                CopilotFact(label="Cockpit", value=str(cockpit), raw=True),
                CopilotFact(label="Cabin", value=str(cabin), raw=True),
                # Route, not tags: SVX/EVN are matched on ADEP/ADES.
                CopilotFact(
                    label="Route",
                    value=f"{adep or '—'}->{ades or '—'}",
                    raw=True,
                ),
            ],
            source=(
                "LEON MCP · get-report-wizard-flight-scope-report · "
                f"unique_id {unique_id} · {reason}"
            ),
        ),
    )


def _entries_from_row(row: Mapping[str, Any]) -> list[CrewContextEntry]:
    """Rebuild crew context from the report so the audited rule engine runs."""

    entries: list[CrewContextEntry] = []
    for slot in normalize_report_row(row).crew:
        group = _position_group(slot.position)
        if group == "Cockpit":
            pos_type = COCKPIT_POS_TYPE
        elif group == "Cabin":
            pos_type = CABIN_POS_TYPE
        else:
            pos_type = group
        entries.append(
            CrewContextEntry(
                pos_type=pos_type,
                position=slot.position,
                # Neither flag is exposed by the report; see the docstring above.
                training_type=None,
                crew_code=slot.code,
                crew_name=slot.name,
                function=None,
            )
        )
    return entries


def _row_in_period(row: Mapping[str, Any], period: Period) -> bool:
    """True when the row's OWN calendar date falls inside the asked period.

    The widened Heavy fetch returns neighbouring days too; answer targeting
    uses the row's `date_STD_log_UTC`, not the fetcher's duty attribution.
    Rows without a parseable date stay eligible (required-column contract).
    """

    source_date = normalize_report_row(row).source_date
    return source_date is None or period.start <= source_date <= period.end


def _row_flight_nid(row: Mapping[str, Any]) -> int | None:
    """The row identifier the engine indexes by; unique_id == flightNid == trNid
    (confirmed live via tools/id_probe on 2026-06-16/20/22)."""

    return _optional_int(row.get("unique_id")) or _optional_int(
        row.get("scope_row_unique_id")
    )


def _optional_int(value: Any) -> int | None:
    # Duplicate-by-design of service._optional_int and shape-twin of
    # augmented._normalize_tr_nid (lenient, None on junk) — unlike
    # crew_context._normalize_flight_nid, which RAISES because a bad flightNid
    # is a broken LEON contract (L-6 ruling 2026-08-18). Keep in sync.
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


def _context_index_from_report(report: OfficialMcpReport) -> CrewContextIndex:
    """Build the engine's flight index from the MCP report rows themselves.

    This is what lets STEP 4 (the rotation rule) run on the Copilot path: the
    same fetch that answers "is this flight Heavy?" carries the member's
    neighbouring sectors for that UTC day. Rows without a usable identifier
    are skipped; duplicate identifiers keep the row with the fullest crew.
    """

    contexts: dict[int, FlightContext] = {}
    by_flight: dict[int, tuple[CrewContextEntry, ...]] = {}
    for row in report.rows:
        flight_nid = _row_flight_nid(row)
        if flight_nid is None:
            continue
        entries = tuple(_entries_from_row(row))
        existing = contexts.get(flight_nid)
        if existing is not None and len(entries) <= len(existing.entries):
            continue
        normalized = normalize_report_row(row)
        contexts[flight_nid] = FlightContext(
            flight_nid=flight_nid,
            start_time_utc=normalized.off_utc.isoformat() if normalized.off_utc else None,
            end_time_utc=normalized.on_utc.isoformat() if normalized.on_utc else None,
            flight_tags=_tags_from_row(row),
            entries=entries,
            departure_airport=_text(row.get("jl_adep_preferred_code")),
            arrival_airport=_text(row.get("jl_ades_preferred_code")),
        )
        by_flight[flight_nid] = entries
    return CrewContextIndex(available=True, by_flight=by_flight, contexts=contexts)


def _describe_reason(
    reason_code: str,
    *,
    adep: str | None,
    ades: str | None,
    cockpit: int,
    cabin: int,
) -> str:
    """Human-readable citation text for an engine reason code."""

    route = f"ADEP={adep or '—'}, ADES={ades or '—'}"
    if reason_code in ("SVX_AIRPORT", "SVX_TAG"):
        return f"SVX override ({route})"
    if reason_code in ("EVN_AIRPORT", "EVN_TAG"):
        return f"EVN override ({route})"
    if reason_code == "EXTRA_COCKPIT_CREW":
        return f"effective cockpit count = {cockpit} > {HEAVY_COCKPIT_THRESHOLD}"
    if reason_code == "EXTRA_CABIN_CREW":
        return f"effective cabin count = {cabin} > {HEAVY_CABIN_THRESHOLD}"
    if reason_code == "NONE":
        return (
            f"effective cockpit count = {cockpit} <= {HEAVY_COCKPIT_THRESHOLD}; "
            f"effective cabin count = {cabin} <= {HEAVY_CABIN_THRESHOLD}"
        )
    if reason_code == "SAME_DAY_SHORT_BREAK_SAME_CREW":
        return "rotation rule: paired with an adjacent leg (same operating crew, break < 4h)"
    return f"rotation rule: {reason_code}"


def _tags_from_row(row: Mapping[str, Any]) -> tuple[str, ...]:
    # Report-ROW tag parser; twin of crew_context._flight_tag_labels, which
    # parses the GraphQL flight-list shape (L-6 ruling 2026-08-18).
    raw = row.get("flightTags")
    if not isinstance(raw, list):
        return ()
    labels = []
    for tag in raw:
        label = tag.get("label") if isinstance(tag, Mapping) else tag
        if isinstance(label, str) and label.strip():
            labels.append(label.strip().upper())
    return tuple(labels)


def _source(period: Period) -> str:
    return (
        "LEON MCP · get-report-wizard-flight-scope-report · "
        f"{period.start.isoformat()}..{period.end.isoformat()}"
    )


def _roster_answer(report: OfficialMcpReport, period: Period) -> CopilotAnswer:
    crew_by_code: dict[str, str] = {}
    flight_numbers: list[str] = []
    for row in report.rows:
        normalized = normalize_report_row(row)
        for slot in normalized.crew:
            crew_by_code.setdefault(slot.code, slot.name or slot.code)
        number = _text(row.get("flightNo"))
        if number and number not in flight_numbers:
            flight_numbers.append(number)

    if not crew_by_code:
        return CopilotAnswer(
            text=f"No crew are rostered {period.label}. LEON returned no flights for that day.",
            citation=CopilotCitation(
                tone="resolved",
                headline=f"Roster — {period.label}",
                facts=[CopilotFact(label="Flights", value="0", raw=True)],
                source=_source(period),
            ),
        )

    names = sorted(crew_by_code.values(), key=str.casefold)
    listed = ", ".join(names[:25])
    remainder = f" (+{len(names) - 25} more)" if len(names) > 25 else ""
    return CopilotAnswer(
        text=(
            f"{len(names)} crew are rostered {period.label} across "
            f"{len(report.rows)} flights: {listed}{remainder}."
        ),
        citation=CopilotCitation(
            tone="resolved",
            headline=f"Roster — {period.label}",
            facts=[
                CopilotFact(label="Crew", value=str(len(names)), raw=True),
                CopilotFact(label="Flights", value=str(len(report.rows)), raw=True),
                CopilotFact(
                    label="Numbers",
                    value=", ".join(flight_numbers[:6]) or "—",
                    raw=True,
                ),
            ],
            source=_source(period),
        ),
    )


def _hours_answer(
    report: OfficialMcpReport,
    period: Period,
    question: str,
) -> CopilotAnswer:
    named = _match_named_crew(report, question)
    if named is not None:
        code, display, total = named
        return CopilotAnswer(
            text=f"{display} logged {total} {period.label}.",
            citation=CopilotCitation(
                tone="resolved",
                headline=f"Crew hours — {period.label}",
                facts=[
                    CopilotFact(label="Crew", value=code, raw=True),
                    CopilotFact(label="Total", value=total, raw=True),
                ],
                source=_source(period),
            ),
        )

    minutes = sum(
        value for value in report.total_minutes.values() if isinstance(value, int)
    )
    crew_count = len([code for code in report if str(code).strip()])
    return CopilotAnswer(
        text=(
            f"{crew_count} crew logged {_format_minutes(minutes)} in total {period.label}, "
            f"across {len(report.rows)} flights. Name a crew member for their own total."
        ),
        citation=CopilotCitation(
            tone="resolved",
            headline=f"Crew hours — {period.label}",
            facts=[
                CopilotFact(label="Crew", value=str(crew_count), raw=True),
                CopilotFact(label="Total", value=_format_minutes(minutes), raw=True),
                CopilotFact(label="Flights", value=str(len(report.rows)), raw=True),
            ],
            source=_source(period),
        ),
    )


# LEON crew codes are short uppercase tokens that collide with ordinary words
# ("HAS", "AND", "THE"), so a codefolded match would pick a random crew member
# out of any sentence. Codes are matched case-sensitively; name parts are
# matched case-insensitively but never against these.
_STOPWORDS = frozenset({
    "has", "have", "had", "the", "and", "for", "was", "were", "who", "how", "many",
    "this", "that", "from", "with", "not", "are", "all", "our", "his", "her", "them",
    "hours", "crew", "month", "week", "day", "logged", "total", "roster", "flight",
})


def _match_named_crew(
    report: OfficialMcpReport,
    question: str,
) -> tuple[str, str, str] | None:
    """Find a crew member the question actually names, by code or by name."""

    text = question.casefold()
    names_by_code: dict[str, str] = {}
    for row in report.rows:
        for slot in normalize_report_row(row).crew:
            if slot.name:
                names_by_code.setdefault(slot.code, slot.name)

    for code, total in report.items():
        code_text = str(code).strip()
        if not code_text:
            continue
        # Case-sensitive: only an explicitly written code counts.
        if re.search(rf"\b{re.escape(code_text)}\b", question):
            return code_text, names_by_code.get(code_text, code_text), str(total)

    for code, total in report.items():
        code_text = str(code).strip()
        display = names_by_code.get(code_text)
        if not code_text or not display:
            continue
        parts = [
            part.casefold()
            for part in re.split(r"\W+", display)
            if len(part) > 2 and part.casefold() not in _STOPWORDS
        ]
        if any(re.search(rf"\b{re.escape(part)}\b", text) for part in parts):
            return code_text, display, str(total)
    return None


def _format_minutes(total_minutes: int) -> str:
    hours, minutes = divmod(max(total_minutes, 0), 60)
    return f"{hours:02d}:{minutes:02d}"


def _text(value: Any) -> str | None:
    # LENIENT report-row parser; twin of service._optional_string, distinct
    # from the STRICT crew_context._strict_string_or_none (L-6 ruling
    # 2026-08-18). Keep in sync until the Deliverable-3 parsing module.
    return value.strip() if isinstance(value, str) and value.strip() else None

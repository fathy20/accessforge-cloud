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

from ..statistics.crew_hours.cabin_heavy import (
    CabinCrewMember,
    CabinFlight,
    classify_cabin_augmented_heavy,
    classify_cockpit_heavy,
)
from ..statistics.crew_hours.crew_context import CrewContextEntry
from ..statistics.crew_hours.domain import normalize_report_row
from ..statistics.crew_hours.heavy import (
    operating_cabin_count,
    operating_cockpit_count,
)
from ..statistics.crew_hours.mcp_report import OfficialMcpReport
from ..statistics.crew_hours.positions import CABIN_POS_TYPE, COCKPIT_POS_TYPE
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
    report = fetch_report(period.start.isoformat(), period.end.isoformat())
    rows = [
        row
        for row in report.rows
        if (_text(row.get("flightNo")) or "").upper().replace(" ", "").replace("-", "")
        == wanted
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

    # Cockpit and cabin are classified independently. Cockpit keeps its existing
    # rule untouched; cabin uses the corrected one, where SVX/EVN are matched
    # against the real ADEP/ADES airport codes rather than flightTags (which this
    # operator never populates, so those overrides had never fired).
    flight = CabinFlight(
        adep=_text(row.get("jl_adep_preferred_code")),
        ades=_text(row.get("jl_ades_preferred_code")),
        aircraft_registration=_text(row.get("registration")),
        # The augmented reference dataset lives on the Crew Hours service path,
        # not here, so the UNKNOWN pairing rule cannot run on this path.
        is_unknown=False,
    )
    cockpit_heavy, cockpit_reason = classify_cockpit_heavy(flight, entries)
    cabin_heavy, cabin_reason = classify_cabin_augmented_heavy(
        flight, _cabin_crew_from_row(row)
    )

    # Same combination as before the split: cockpit is evaluated first and wins.
    verdict = bool(cockpit_heavy or cabin_heavy) if entries else None
    reason = cockpit_reason if cockpit_heavy else cabin_reason
    cockpit = operating_cockpit_count(entries)
    cabin = operating_cabin_count(entries)

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
                    value=f"{flight.adep or '—'}->{flight.ades or '—'}",
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


def _cabin_crew_from_row(row: Mapping[str, Any]) -> list[CabinCrewMember]:
    """Cabin crew only — cockpit is classified from a separate list.

    ``function`` is always None: LEON exposes no Work Schedule Function field,
    so the TRN exclusion cannot run. The classifier flags that in its reason
    rather than treating a missing Function as "not a trainee".
    """

    return [
        CabinCrewMember(crew_code=slot.code, position=slot.position, function=None)
        for slot in normalize_report_row(row).crew
        if _position_group(slot.position) == "Cabin"
    ]


def _tags_from_row(row: Mapping[str, Any]) -> tuple[str, ...]:
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
    return value.strip() if isinstance(value, str) and value.strip() else None

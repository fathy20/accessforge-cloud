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

from ..statistics.crew_hours.domain import normalize_report_row
from ..statistics.crew_hours.mcp_report import OfficialMcpReport
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
    if intent == INTENT_HEAVY:
        # Heavy needs the FTL augmentation index and flight-list crew context,
        # both of which live on LEON's GraphQL endpoint. Refuse plainly rather
        # than answer Heavy from incomplete data.
        return None

    period = resolve_period(question, today)
    if period is None:
        return None

    report = fetch_report(period.start.isoformat(), period.end.isoformat())
    if intent == INTENT_ROSTER:
        return _roster_answer(report, period)
    return _hours_answer(report, period, question)


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

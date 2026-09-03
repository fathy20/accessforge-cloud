"""Crew Hours workbook, laid out exactly like the manual month sheet.

The template is pinned to ``Stactstics hany/6-Jun 26 Hrs.xlsx`` — the sheet the
operation has always produced by hand.  Four tabs (``Cockpit``,
``Cockpit Summary``, ``Cabin``, ``Cabin Summary``), one block per crew member,
and only the names, the dates and the month label change from run to run.

Two deliberate departures from the hand-made file:

* Totals are written as **values**, never as ``=SUM(...)``.  An official total
  comes from LEON and is never recomputed here (ADR: official totals are read,
  not derived), and a value renders identically to the formula it replaces.
* A trailing ``Report Information`` tab records period, operator and generation
  time.  It is the export's audit trail; it sits after the four template tabs
  and does not disturb them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from io import BytesIO
import re

from openpyxl import Workbook
from openpyxl.cell.cell import Cell
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.page import PageMargins

from .positions import CREW_SET_EXCLUDED_POSITIONS
from .schemas import CrewHoursReportResponse, CrewMemberSummary, FlightItem


XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Columns A..K of every detail block, verbatim from the manual sheet — the
# trailing space in "ADEP " included, because that is what the sheet carries.
DETAIL_HEADERS = (
    "Position type",
    "Name",
    "Surname",
    "Date",
    "Aircraft",
    "Flight number",
    "ADEP ",
    "ADES",
    "OFF",
    "ON",
    "Block time",
    # The manual sheet leaves column L unlabelled; we label it, because the
    # Heavy verdict here is ours and every tab now carries it.
    "Heavy",
)
_COL_POSITION, _COL_NAME, _COL_SURNAME, _COL_DATE = 1, 2, 3, 4
_COL_AIRCRAFT, _COL_FLIGHT_NUMBER, _COL_ADEP, _COL_ADES = 5, 6, 7, 8
_COL_OFF, _COL_ON, _COL_BLOCK = 9, 10, 11
_COL_MARKER = 12

# Summary tab geometry. H.C is ours — the manual sheet stops at Block time.
_SUM_COL_INDEX, _SUM_COL_NAME, _SUM_COL_SURNAME, _SUM_COL_TOTAL = 1, 2, 3, 4
_SUM_COL_CREDITS = 5

DETAIL_START_ROW = 4
BLOCK_GAP_ROWS = 3
SUMMARY_TITLE_ROW = 1
SUMMARY_HEADER_ROW = 2
SUMMARY_FIRST_DATA_ROW = 3

TEMPLATE_SHEETS = ("Cockpit", "Cockpit Summary", "Cabin", "Cabin Summary")
INFORMATION_SHEET = "Report Information"

_NOT_AVAILABLE = "Not available"
_NOT_ACTIVE = "Not-Active"
# The one hours_source_status the dashboard accepts as an official total.
OFFICIAL_MCP_SOURCE = "official_mcp_report"

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
_DURATION_PATTERN = re.compile(
    r"^\s*(?P<hours>\d+):(?P<minutes>[0-5]\d)(?::(?P<seconds>[0-5]\d))?\s*$"
)
_CLOCK_PATTERN = re.compile(
    r"^\s*(?P<hours>[01]?\d|2[0-3]):(?P<minutes>[0-5]\d)(?::(?P<seconds>[0-5]\d))?\s*$"
)
# LEON report rows carry the log date as DD-MM-YYYY; fixtures and the API
# period use ISO. Both reach this module, so both have to parse.
_SOURCE_DATE_PATTERN = re.compile(r"\d{2}-\d{2}-\d{4}")
_MONTH_NAMES = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)

# "White, Background 1, Darker 15%" in the manual sheet; the flat RGB renders
# the same in every viewer and survives a theme change.
_BAND_FILL = PatternFill(fill_type="solid", fgColor="D9D9D9")

_HEADER_FONT = Font(name="Calibri", size=14, bold=True)
_TOTAL_NAME_FONT = Font(name="Calibri", size=16)
_TOTAL_VALUE_FONT = Font(name="Calibri", size=16, bold=True)
_DATA_FONT = Font(name="Calibri", size=11)
_SUMMARY_TITLE_FONT = Font(name="Calibri", size=16, bold=True)
_SUMMARY_NAME_FONT = Font(name="Calibri", size=16)
_SUMMARY_INDEX_FONT = Font(name="Calibri", size=11)
_LABEL_FONT = Font(name="Calibri", size=11, bold=True)

_MEDIUM = Side(style="medium")
_DASHED = Side(style="dashed")
_THIN = Side(style="thin")

_BOX = Border(left=_MEDIUM, right=_MEDIUM, top=_MEDIUM, bottom=_MEDIUM)
_BAND_LEFT = Border(left=_MEDIUM, top=_MEDIUM, bottom=_MEDIUM)
_BAND_MIDDLE = Border(top=_MEDIUM, bottom=_MEDIUM)
_BAND_RIGHT = Border(right=_MEDIUM, top=_MEDIUM, bottom=_MEDIUM)
_EDGE_LEFT = Border(left=_MEDIUM)
_EDGE_RIGHT = Border(right=_MEDIUM)
# Summary rows are separated by a single dashed rule drawn on each row's top.
_SUMMARY_ROW_LEFT = Border(left=_MEDIUM, top=_DASHED)
_SUMMARY_ROW_MIDDLE = Border(top=_DASHED)
_SUMMARY_ROW_RIGHT = Border(left=_MEDIUM, right=_MEDIUM, top=_DASHED)
_INFO_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

_CENTER = Alignment(horizontal="center", vertical="center")
_RIGHT = Alignment(horizontal="right", vertical="center")
_LEFT = Alignment(horizontal="left", vertical="center")
_WRAP_LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)
# Data rows carry horizontal alignment only, as the manual sheet does.
_ROW_CENTER = Alignment(horizontal="center")
_ROW_RIGHT_ALIGN = Alignment(horizontal="right")
_ROW_LEFT_ALIGN = Alignment(horizontal="left")

# Per-column (alignment) of a flight row, mirroring the manual sheet: the first
# name is right-aligned and the surname left-aligned so the pair reads as one
# centred name across B and C.
_FLIGHT_ALIGNMENTS = {
    _COL_POSITION: _ROW_CENTER,
    _COL_NAME: _ROW_RIGHT_ALIGN,
    _COL_SURNAME: _ROW_LEFT_ALIGN,
    _COL_DATE: _ROW_CENTER,
    _COL_AIRCRAFT: _ROW_CENTER,
    _COL_FLIGHT_NUMBER: _ROW_CENTER,
    _COL_ADEP: _ROW_RIGHT_ALIGN,
    _COL_ADES: _ROW_LEFT_ALIGN,
    _COL_OFF: _ROW_CENTER,
    _COL_ON: _ROW_CENTER,
    _COL_BLOCK: _ROW_CENTER,
    _COL_MARKER: _ROW_CENTER,
}

_DETAIL_WIDTHS = {
    "Cockpit": (18.15, 20.0, 13.7, 11.15, 10.7, 19.45, 8.85, 8.0, 6.3, 6.0, 16.55, 8.45),
    "Cabin": (18.85, 18.45, 14.15, 15.7, 10.45, 17.3, 8.15, 7.55, 8.45, 6.0, 13.45, 8.45),
}
_SUMMARY_WIDTHS = {
    "Cockpit": (5.0, 18.15, 25.7, 14.3, 8.0),
    "Cabin": (5.0, 35.55, 32.0, 21.0, 8.0),
}


# --------------------------------------------------------------------------
# value coercion
# --------------------------------------------------------------------------


@dataclass
class _Issues:
    """Values LEON sent that this module could not turn into a number or a date.

    Collected rather than raised, then named on the Report Information tab so a
    blank or text cell in the sheet always has a stated reason.
    """

    durations: list[str] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)


def _write_string(cell: Cell, value: str | None) -> None:
    """Write text safely so spreadsheet formulas cannot be injected."""

    if value is None:
        cell.value = None
        return
    if value.startswith(_FORMULA_PREFIXES):
        value = f"'{value}"
    cell.value = value


def _parse_duration(value: str) -> float | None:
    """Return a duration as a fraction of a day, or None if it is not one."""

    match = _DURATION_PATTERN.fullmatch(value)
    if match is None:
        return None
    hours = int(match.group("hours"))
    minutes = int(match.group("minutes"))
    seconds = int(match.group("seconds") or 0)
    return (hours * 60 * 60 + minutes * 60 + seconds) / (24 * 60 * 60)


def _parse_clock(value: str | None) -> time | None:
    """Accept a bare ``HH:MM`` wall clock or a full ISO timestamp."""

    if not value:
        return None
    match = _CLOCK_PATTERN.fullmatch(value)
    if match is not None:
        return time(
            int(match.group("hours")),
            int(match.group("minutes")),
            int(match.group("seconds") or 0),
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.time().replace(microsecond=0)


def _parse_date(value: str | None) -> datetime | None:
    """Accept LEON's DD-MM-YYYY log date as well as any ISO date or timestamp.

    Returns None rather than raising: one malformed date must not cost the
    operator the whole download. Callers record what they could not read so
    the blank cell is explained on the Report Information tab.
    """

    if not value:
        return None
    text = value.strip()
    if _SOURCE_DATE_PATTERN.fullmatch(text):
        try:
            return datetime.strptime(text, "%d-%m-%Y")
        except ValueError:
            return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return datetime(parsed.year, parsed.month, parsed.day)


def _write_flight_date(cell: Cell, value: str | None, unreadable: list[str]) -> None:
    """Write the leg date, keeping anything unreadable visible as text."""

    if not value:
        cell.value = None
        return
    parsed = _parse_date(value)
    if parsed is None:
        _write_string(cell, value)
        unreadable.append(value)
        return
    cell.value = parsed


def _period_month(report: CrewHoursReportResponse) -> date:
    """The month the sheet is labelled with — the first day of the period."""

    start = _parse_date(report.period.from_date)
    if start is None:
        return date(1900, 1, 1)
    return date(start.year, start.month, 1)


def _month_label(month: date) -> str:
    return f"{_MONTH_NAMES[month.month - 1]}.{month.year % 100:02d}"


def _split_name(crew: CrewMemberSummary) -> tuple[str, str]:
    """Split "Name Surname" the way LEON joins it: first token, then the rest."""

    source = crew.full_name or crew.display_name or ""
    first, _, rest = source.strip().partition(" ")
    return first, rest.strip()


def _sort_key(crew: CrewMemberSummary) -> tuple[str, str]:
    first, surname = _split_name(crew)
    return (first.casefold(), surname.casefold())


def _is_non_operating(flight: FlightItem) -> bool:
    position = (flight.position or "").strip().upper()
    return bool(position) and position in CREW_SET_EXCLUDED_POSITIONS


def _position_type_display(crew: CrewMemberSummary, flight: FlightItem) -> str:
    if _is_non_operating(flight):
        return _NOT_ACTIVE
    return crew.position_type or "Unclassified"


def _is_training(flight: FlightItem) -> bool:
    return bool(flight.is_training_position or flight.is_training_function or flight.is_trn)


def _leg_verdict(flight: FlightItem) -> bool | None:
    """The Heavy verdict the dashboard shows for this leg.

    Twin of ``CrewDetailFlightRow.tsx``: the question is "did this leg's duty
    earn THIS member a Heavy credit?", so the member-duty allowance wins and
    the flight-level value is only the fallback for payloads predating it.
    Both legs of a credited duty therefore read Yes together.
    """

    if flight.duty_credit is None:
        return flight.augmented_heavy
    return flight.duty_credit


def _marker_display(flight: FlightItem) -> str:
    """Column L: the leg's one-word verdict, in the manual sheet's vocabulary."""

    position = (flight.position or "").strip().upper()
    if position == "PAD":
        return "PAD"
    if _is_training(flight):
        return "TRN"
    verdict = _leg_verdict(flight)
    if verdict is True:
        return "Yes"
    if verdict is False:
        return "No"
    return "Unknown"


# --------------------------------------------------------------------------
# cell writers
# --------------------------------------------------------------------------


def _write_duration(
    cell: Cell, value: str | None, unparsed: list[str], *, number_format: str = "[h]:mm"
) -> float | None:
    """Write a duration numerically; keep unparsable text as text.

    A single leg's block time is under a day and uses ``h:mm``; anything that
    accumulates (a member's month, the sheet's grand total) needs the elapsed
    ``[h]:mm`` so 58 hours does not render as 10.
    """

    if value is None:
        cell.value = None
        return None
    parsed = _parse_duration(value)
    if parsed is None:
        _write_string(cell, value)
        if value:
            unparsed.append(value)
        return None
    cell.value = parsed
    cell.number_format = number_format
    return parsed


def _official_totals_are_live(report: CrewHoursReportResponse) -> bool:
    """Twin of ``hasOfficialMcpTotal``: a total counts only when LEON's official
    MCP report is the source. Anything else reads unavailable on screen, so it
    must read unavailable here too."""

    return report.hours_source_status == OFFICIAL_MCP_SOURCE


def _write_official_total(
    cell: Cell, value: str | None, unparsed: list[str], *, official: bool = True
) -> float | None:
    """The member's LEON total: a duration, the literal TRN, or 'Not available'."""

    if not official or value is None or value == "":
        _write_string(cell, _NOT_AVAILABLE)
        return None
    if value == "TRN":
        _write_string(cell, value)
        return None
    return _write_duration(cell, value, unparsed)


def _style(cell: Cell, *, font: Font, border: Border, alignment: Alignment,
           fill: PatternFill | None = None, number_format: str | None = None) -> None:
    cell.font = font
    cell.border = border
    cell.alignment = alignment
    if fill is not None:
        cell.fill = fill
    if number_format is not None:
        cell.number_format = number_format


def _band_border(column: int, last_column: int) -> Border:
    if column == 1:
        return _BAND_LEFT
    if column == last_column:
        return _BAND_RIGHT
    return _BAND_MIDDLE


# --------------------------------------------------------------------------
# detail tab
# --------------------------------------------------------------------------


def _configure_detail_sheet(worksheet, group: str) -> None:
    worksheet.sheet_view.showGridLines = False
    worksheet.page_setup.orientation = "landscape"
    worksheet.page_setup.fitToWidth = 1
    worksheet.page_setup.fitToHeight = 0
    worksheet.sheet_properties.pageSetUpPr.fitToPage = True
    worksheet.page_margins = PageMargins(left=0.25, right=0.25, top=0.5, bottom=0.5)
    for column, width in enumerate(_DETAIL_WIDTHS[group], start=1):
        worksheet.column_dimensions[get_column_letter(column)].width = width


def _write_block_headers(worksheet, row: int) -> None:
    for column, header in enumerate(DETAIL_HEADERS, start=1):
        cell = worksheet.cell(row=row, column=column)
        _write_string(cell, header)
        _style(cell, font=_HEADER_FONT, border=_BOX, alignment=_CENTER, fill=_BAND_FILL)
    worksheet.cell(row=row, column=_COL_DATE).number_format = "[$-409]dd/mmm/yy;@"
    worksheet.cell(row=row, column=_COL_ADEP).alignment = _RIGHT
    worksheet.cell(row=row, column=_COL_ADES).alignment = _LEFT
    worksheet.cell(row=row, column=_COL_BLOCK).number_format = "[h]:mm"
    worksheet.row_dimensions[row].height = 30


def _write_flight_row(
    worksheet,
    row: int,
    crew: CrewMemberSummary,
    flight: FlightItem,
    issues: _Issues,
) -> None:
    first, surname = _split_name(crew)

    _write_string(worksheet.cell(row=row, column=_COL_POSITION), _position_type_display(crew, flight))
    _write_string(worksheet.cell(row=row, column=_COL_NAME), first)
    _write_string(worksheet.cell(row=row, column=_COL_SURNAME), surname)
    _write_flight_date(
        worksheet.cell(row=row, column=_COL_DATE), flight.flight_date, issues.dates
    )
    _write_string(worksheet.cell(row=row, column=_COL_AIRCRAFT), flight.aircraft_reg)
    _write_string(worksheet.cell(row=row, column=_COL_FLIGHT_NUMBER), flight.flight_number)
    _write_string(worksheet.cell(row=row, column=_COL_ADEP), flight.departure_airport)
    _write_string(worksheet.cell(row=row, column=_COL_ADES), flight.arrival_airport)
    worksheet.cell(row=row, column=_COL_OFF).value = _parse_clock(flight.start_time_utc)
    worksheet.cell(row=row, column=_COL_ON).value = _parse_clock(flight.end_time_utc)
    _write_duration(
        worksheet.cell(row=row, column=_COL_BLOCK),
        flight.block_time,
        issues.durations,
        number_format="h:mm",
    )
    _write_string(worksheet.cell(row=row, column=_COL_MARKER), _marker_display(flight))

    for column in range(1, _COL_MARKER + 1):
        cell = worksheet.cell(row=row, column=column)
        border = Border()
        if column == _COL_POSITION:
            border = _EDGE_LEFT
        elif column in (_COL_BLOCK, _COL_MARKER):
            border = _EDGE_RIGHT
        _style(cell, font=_DATA_FONT, border=border, alignment=_FLIGHT_ALIGNMENTS[column])
    worksheet.cell(row=row, column=_COL_DATE).number_format = "yyyy\\-mm\\-dd"
    worksheet.cell(row=row, column=_COL_OFF).number_format = "h:mm"
    worksheet.cell(row=row, column=_COL_ON).number_format = "h:mm"
    worksheet.row_dimensions[row].height = 15


def _write_block_total(
    worksheet,
    row: int,
    crew: CrewMemberSummary,
    month: date,
    *,
    official: bool,
    issues: _Issues,
) -> None:
    """The banded closing row: name, month, the word Total, the official total.

    The manual sheet closes the block with ``=SUM`` over the block's own rows.
    We write the member's LEON total instead — same rendering, and the number
    stays the one LEON reported rather than one this file recomputed.
    """

    first, surname = _split_name(crew)
    _write_string(worksheet.cell(row=row, column=_COL_POSITION), first)
    _write_string(worksheet.cell(row=row, column=_COL_NAME), surname)
    worksheet.cell(row=row, column=_COL_DATE).value = month
    _write_string(worksheet.cell(row=row, column=_COL_OFF), "Total")
    _write_official_total(
        worksheet.cell(row=row, column=_COL_BLOCK),
        crew.official_total,
        issues.durations,
        official=official,
    )
    # The H.C badge the dashboard puts on the crew header goes in the spare
    # cell under the Heavy column, so the block closes with both numbers.
    _write_string(worksheet.cell(row=row, column=_COL_MARKER), f"H.C {crew.heavy_credits}")

    for column in range(1, _COL_MARKER + 1):
        cell = worksheet.cell(row=row, column=column)
        _style(
            cell,
            font=_TOTAL_NAME_FONT,
            border=_band_border(column, _COL_MARKER),
            alignment=_CENTER,
            fill=_BAND_FILL,
        )
    worksheet.cell(row=row, column=_COL_POSITION).alignment = _RIGHT
    worksheet.cell(row=row, column=_COL_NAME).alignment = _LEFT
    worksheet.cell(row=row, column=_COL_NAME).border = _BAND_RIGHT
    for column in (_COL_DATE, _COL_OFF, _COL_BLOCK, _COL_MARKER):
        worksheet.cell(row=row, column=column).font = _TOTAL_VALUE_FONT
    worksheet.cell(row=row, column=_COL_DATE).number_format = "mmm-yy"
    worksheet.cell(row=row, column=_COL_BLOCK).border = _BOX
    worksheet.merge_cells(start_row=row, start_column=_COL_DATE, end_row=row, end_column=_COL_ADES)
    worksheet.merge_cells(start_row=row, start_column=_COL_OFF, end_row=row, end_column=_COL_ON)


def _build_detail_sheet(
    worksheet,
    report: CrewHoursReportResponse,
    group: str,
    crews: list[CrewMemberSummary],
    issues: _Issues,
) -> None:
    _configure_detail_sheet(worksheet, group)
    month = _period_month(report)
    official = _official_totals_are_live(report)

    row = DETAIL_START_ROW
    for crew in crews:
        _write_block_headers(worksheet, row)
        row += 1
        for flight in crew.flights:
            _write_flight_row(worksheet, row, crew, flight, issues)
            row += 1
        _write_block_total(worksheet, row, crew, month, official=official, issues=issues)
        row += 1 + BLOCK_GAP_ROWS


# --------------------------------------------------------------------------
# summary tab
# --------------------------------------------------------------------------


def _configure_summary_sheet(worksheet, group: str) -> None:
    worksheet.sheet_view.showGridLines = False
    worksheet.sheet_view.zoomScale = 80
    worksheet.page_setup.orientation = "portrait"
    worksheet.page_setup.fitToWidth = 1
    worksheet.page_setup.fitToHeight = 0
    worksheet.sheet_properties.pageSetUpPr.fitToPage = True
    worksheet.page_margins = PageMargins(left=0.35, right=0.35, top=0.5, bottom=0.5)
    for column, width in enumerate(_SUMMARY_WIDTHS[group], start=1):
        worksheet.column_dimensions[get_column_letter(column)].width = width


def _build_summary_sheet(
    worksheet,
    report: CrewHoursReportResponse,
    group: str,
    crews: list[CrewMemberSummary],
    issues: _Issues,
) -> None:
    _configure_summary_sheet(worksheet, group)
    month = _period_month(report)
    official = _official_totals_are_live(report)
    banded = (_SUM_COL_NAME, _SUM_COL_SURNAME, _SUM_COL_TOTAL, _SUM_COL_CREDITS)

    title = worksheet.cell(row=SUMMARY_TITLE_ROW, column=_SUM_COL_NAME)
    _write_string(title, f"{group} HRS.{_month_label(month)}")
    for column in banded:
        _style(
            worksheet.cell(row=SUMMARY_TITLE_ROW, column=column),
            font=_SUMMARY_TITLE_FONT,
            border=Border(bottom=_MEDIUM),
            alignment=_CENTER,
            fill=_BAND_FILL,
        )
    worksheet.merge_cells(
        start_row=SUMMARY_TITLE_ROW,
        start_column=_SUM_COL_NAME,
        end_row=SUMMARY_TITLE_ROW,
        end_column=_SUM_COL_CREDITS,
    )

    _write_string(worksheet.cell(row=SUMMARY_HEADER_ROW, column=_SUM_COL_NAME), "Name")
    _write_string(worksheet.cell(row=SUMMARY_HEADER_ROW, column=_SUM_COL_TOTAL), "Block time")
    _write_string(worksheet.cell(row=SUMMARY_HEADER_ROW, column=_SUM_COL_CREDITS), "H.C")
    for column in banded:
        _style(
            worksheet.cell(row=SUMMARY_HEADER_ROW, column=column),
            font=_SUMMARY_TITLE_FONT,
            border=_BAND_LEFT if column not in (_SUM_COL_TOTAL, _SUM_COL_CREDITS) else _BOX,
            alignment=_CENTER,
            fill=_BAND_FILL,
        )
    worksheet.merge_cells(
        start_row=SUMMARY_HEADER_ROW,
        start_column=_SUM_COL_NAME,
        end_row=SUMMARY_HEADER_ROW,
        end_column=_SUM_COL_SURNAME,
    )

    row = SUMMARY_FIRST_DATA_ROW
    running_total = 0.0
    running_credits = 0
    for index, crew in enumerate(crews, start=1):
        first, surname = _split_name(crew)
        index_cell = worksheet.cell(row=row, column=_SUM_COL_INDEX)
        index_cell.value = index
        _style(index_cell, font=_SUMMARY_INDEX_FONT, border=Border(), alignment=_ROW_CENTER)
        _write_string(worksheet.cell(row=row, column=_SUM_COL_NAME), first)
        _write_string(worksheet.cell(row=row, column=_SUM_COL_SURNAME), surname)
        total = _write_official_total(
            worksheet.cell(row=row, column=_SUM_COL_TOTAL),
            crew.official_total,
            issues.durations,
            official=official,
        )
        if total is not None:
            running_total += total
        credits_cell = worksheet.cell(row=row, column=_SUM_COL_CREDITS)
        credits_cell.value = crew.heavy_credits
        running_credits += crew.heavy_credits
        _style(
            credits_cell,
            font=_SUMMARY_NAME_FONT,
            border=_SUMMARY_ROW_RIGHT,
            alignment=_ROW_CENTER,
        )
        _style(
            worksheet.cell(row=row, column=_SUM_COL_NAME),
            font=_SUMMARY_NAME_FONT,
            border=_SUMMARY_ROW_LEFT,
            alignment=_ROW_RIGHT_ALIGN,
        )
        _style(
            worksheet.cell(row=row, column=_SUM_COL_SURNAME),
            font=_SUMMARY_NAME_FONT,
            border=_SUMMARY_ROW_MIDDLE,
            alignment=_ROW_LEFT_ALIGN,
        )
        total_cell = worksheet.cell(row=row, column=_SUM_COL_TOTAL)
        total_cell.font = _SUMMARY_NAME_FONT
        total_cell.border = _SUMMARY_ROW_RIGHT
        total_cell.alignment = _ROW_CENTER
        row += 1

    _write_string(worksheet.cell(row=row, column=_SUM_COL_NAME), "Total")
    grand_total = worksheet.cell(row=row, column=_SUM_COL_TOTAL)
    grand_total.value = running_total
    worksheet.cell(row=row, column=_SUM_COL_CREDITS).value = running_credits
    for column in banded:
        _style(
            worksheet.cell(row=row, column=column),
            font=_SUMMARY_TITLE_FONT,
            border=_BAND_LEFT if column not in (_SUM_COL_TOTAL, _SUM_COL_CREDITS) else _BOX,
            alignment=_CENTER,
            fill=_BAND_FILL,
        )
    grand_total.number_format = "[h]:mm"
    worksheet.merge_cells(
        start_row=row, start_column=_SUM_COL_NAME, end_row=row, end_column=_SUM_COL_SURNAME
    )


# --------------------------------------------------------------------------
# information tab
# --------------------------------------------------------------------------


def _utc_iso(generated_at: datetime) -> str:
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)
    return generated_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_label_value(worksheet, row: int, label: str, value: str | None) -> None:
    label_cell = worksheet.cell(row=row, column=1)
    value_cell = worksheet.cell(row=row, column=2)
    _write_string(label_cell, label)
    _write_string(value_cell, value)
    _style(label_cell, font=_LABEL_FONT, border=_INFO_BORDER, alignment=_LEFT, fill=_BAND_FILL)
    _style(value_cell, font=_DATA_FONT, border=_INFO_BORDER, alignment=_WRAP_LEFT)


def _build_information_sheet(
    worksheet,
    report: CrewHoursReportResponse,
    generated_at: datetime,
    generated_by: str,
    issues: _Issues,
) -> None:
    worksheet.sheet_view.showGridLines = False
    worksheet.column_dimensions["A"].width = 30
    worksheet.column_dimensions["B"].width = 85
    worksheet.page_margins = PageMargins(left=0.35, right=0.35, top=0.5, bottom=0.5)

    title = worksheet.cell(row=1, column=1)
    _write_string(title, "Crew Hours — Report Information")
    for column in (1, 2):
        _style(
            worksheet.cell(row=1, column=column),
            font=_SUMMARY_TITLE_FONT,
            border=_BOX,
            alignment=_LEFT,
            fill=_BAND_FILL,
        )
    worksheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=2)
    worksheet.row_dimensions[1].height = 26

    _write_label_value(worksheet, 3, "Report period from", report.period.from_date)
    _write_label_value(worksheet, 4, "Report period to", report.period.to_date)
    _write_label_value(worksheet, 5, "Generated at UTC", _utc_iso(generated_at))
    _write_label_value(worksheet, 6, "Generated by", generated_by)
    _write_label_value(worksheet, 7, "Source", "LEON MCP")
    _write_label_value(
        worksheet,
        8,
        "Crew handling",
        "Cockpit and Cabin only. Maintenance and unclassified crew are not "
        "exported — the sheet has no tab for them.",
    )
    durations = list(dict.fromkeys(issues.durations))
    _write_label_value(
        worksheet,
        9,
        "Unparsed durations",
        "None"
        if not durations
        else "Unparsed duration strings were preserved as text: " + ", ".join(durations),
    )
    dates = list(dict.fromkeys(issues.dates))
    _write_label_value(
        worksheet,
        10,
        "Unreadable dates",
        "None"
        if not dates
        else "Dates LEON sent in an unrecognised format, kept as text: " + ", ".join(dates),
    )
    _write_label_value(
        worksheet,
        11,
        "Blank leg cells",
        "ADEP, ADES, OFF, ON, Block time and Date come from the LEON Journey "
        "Log. A leg with no journey log filed shows its flight number and "
        "aircraft with those cells empty — nothing was dropped here.",
    )


# --------------------------------------------------------------------------
# entry points
# --------------------------------------------------------------------------


def build_crew_hours_workbook(
    report: CrewHoursReportResponse,
    *,
    generated_at: datetime | None = None,
    generated_by: str = "",
) -> BytesIO:
    generated_at = generated_at or datetime.now(timezone.utc)
    workbook = Workbook()

    cockpit = workbook.active
    cockpit.title = "Cockpit"
    cockpit_summary = workbook.create_sheet("Cockpit Summary")
    cabin = workbook.create_sheet("Cabin")
    cabin_summary = workbook.create_sheet("Cabin Summary")
    information = workbook.create_sheet(INFORMATION_SHEET)

    by_group = {
        group: sorted(
            (crew for crew in report.crew_members if crew.position_type == group),
            key=_sort_key,
        )
        for group in ("Cockpit", "Cabin")
    }
    issues = _Issues()
    _build_detail_sheet(cockpit, report, "Cockpit", by_group["Cockpit"], issues)
    _build_summary_sheet(cockpit_summary, report, "Cockpit", by_group["Cockpit"], issues)
    _build_detail_sheet(cabin, report, "Cabin", by_group["Cabin"], issues)
    _build_summary_sheet(cabin_summary, report, "Cabin", by_group["Cabin"], issues)
    _build_information_sheet(information, report, generated_at, generated_by, issues)

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return output


def _safe_filename_component(value: str) -> str:
    collapsed = re.sub(r"[^A-Za-z0-9._-]+", "-", value)
    return collapsed.strip("-") or "unknown"


def build_crew_hours_filename(report: CrewHoursReportResponse, _generated_at: datetime) -> str:
    """Name the file after the month, the way the manual sheet is named."""

    start = _parse_date(report.period.from_date)
    end = _parse_date(report.period.to_date)
    if start is not None and end is not None and (start.year, start.month) == (end.year, end.month):
        month = date(start.year, start.month, 1)
        stem = f"{_MONTH_NAMES[month.month - 1]}-{month.year % 100:02d}-Hrs"
        return _safe_filename_component(stem) + ".xlsx"
    from_date = _safe_filename_component(report.period.from_date)
    to_date = _safe_filename_component(report.period.to_date)
    return f"crew-hours-{from_date}-to-{to_date}.xlsx"

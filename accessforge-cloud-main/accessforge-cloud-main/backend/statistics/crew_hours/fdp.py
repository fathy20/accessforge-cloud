"""Flying Duty Period (FDP) model — a shadow validator. NOT a Heavy rule.

Source: EgyptAir Operations Manual Chapter 7 "Flight Time Limitation",
Issue 2 Rev 00, STD SEP.09, pages 7.1-2 … 7.1-11 (the owner's scans
`reference.pdf` and `flight limitation pdf.pdf`). Plan and open rulings:
`docs/architecture/heavy-fdp-regulatory-model-plan-2026-09-03.md`. The
independent read of all ten OM pages, which is the evidence for everything
below: `Heavy_FDP_Report/independent_review/FINDINGS.md`.

RETRACTION (2026-09-08)
-----------------------
This docstring used to present the inequality below as the definition of
"Heavy". That claim is withdrawn. It was never in the OM, and it does not
hold against the data.

* **The OM does not define Heavy.** Chapter 7 regulates flight-time limits,
  rest and positioning. Across all ten pages the word "Heavy" never appears,
  nor does "H.C", nor any word for allowance, wage, bonus, compensation or
  overtime, in Arabic or English. Nothing in the OM is authority for or
  against a Heavy verdict, in either direction.
* **Heavy is a Red Sea business/policy verdict.** Its authority is the
  owner's rulings (the EVN and SVX absolutes, the domestic-route ruling, the
  SP trainee-slot ruling), LEON's ``crewAugmentation``, and the approved
  precedence table in ``heavy.py``. None of those is an FDP calculation.
* **Augmentation does not prove the base limit was exceeded.** Of 779
  augmented June member-duties, only 49 exceed the base table limit and the
  median augmented duty sits roughly 5 h *below* it. Operators carry extra
  crew for training, ferry, familiarisation and standby cover as well. The
  OM's own augmentation clause is a safety provision — an extra licensed
  flight-deck member (7.1-6 2-2-1), a rest facility (7.1-6 2-2-2), 50% more
  cabin crew when relief is carried (7.1-10 7-2-6) — never a payment trigger.
* **An over-limit FDP does not prove Heavy either.** The OM offers other
  routes to legality: split duty (7.1-6 2-3), commander's discretion up to
  3:00 (7.1-7 2-6), the cabin +1:00 (7.1-10 7-2-1), and the exclusion of a
  positioning member's landings from his sector count (7.1-7 2-4-1).

What this module actually computes — one regulatory quantity, nothing more:

    planned FDP  vs  maximum FDP(table, local start band, sectors)

  planned FDP   = 1:30 before the first scheduled departure
                  -> 0:30 after the last landing            (OM 7.1-4 2-1-3)
  maximum FDP   = Table A when the member starts acclimatised (local start
                  band x sectors), Table B otherwise (preceding rest x sectors)
                                                            (OM 7.1-4 2-1)
  positioning   = duty, never a sector; when it precedes the FDP it is inside
                  the FDP                                   (OM 7.1-7 2-4-1)
  cabin crew    = cockpit limit + 1:00                      (OM 7.1-10 7-2-1)

``FdpAssessment.needs_augmentation`` is that comparison and only that: "the
planned duty is longer than the base two-pilot table limit". Read it as a
regulatory observation, never as a Heavy verdict, and never as a claim about
why extra crew was or was not rostered.

STATUS: SHADOW / VALIDATION ONLY. Nothing here changes a Heavy verdict, a
credit, an export cell, or a total, and nothing here may. The service paints
the assessment beside the existing verdict and into the decision trace for
back-testing and diagnostics. ``credit_vs_fdp`` in `tools/fdp_backtest.py`
compares a business boolean against a safety model, so disagreement between
them is the expected state, not an error signal.

Citations: every FDP rule above is stated verbatim in the OM and was verified
page by page in the review cited at the top. The ECAR Part 121 Subpart Q /
CAP 371 paragraph numbers this module also used to cite are NOT verified
against an official ECAA text; where they survive in the comments below they
are marked UNVERIFIED, and the OM paragraph is the authority in each case.

Pure module: no I/O, no service imports, plain dataclasses only. The tables
are DATA, versioned, because the 2009 OM and the 2016 ECAR differ in two
cells and Red Sea's approved manual decides which applies (ruling R1 —
answered by the data: LEON is configured with the OM-2009 values).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal, Mapping, Sequence

from .allowance import NEUTRAL_POSITIONS, RIDE_POSITIONS, AllowanceLeg, parse_leg_start_end
from .trace import HeavyTraceStep, format_break, step

CrewType = Literal["cockpit", "cabin"]

REPORT_BEFORE_DEPARTURE = timedelta(hours=1, minutes=30)
POST_FLIGHT_DUTY = timedelta(minutes=30)
CABIN_FDP_EXTRA = timedelta(hours=1)

# In-flight relief (OM 7.1-6 2-2; ECAR 121.504(c) / CAP 371 §12.3 UNVERIFIED):
# rest under 3 h counts for nothing even if non-consecutive (2-2-3); from 3 h
# the FDP extends by half the rest in a bunk (cap 18 h; cabin 19 h) or a third
# of the rest in a seat (cap 15 h; cabin 16 h). Confirmed verbatim in the OM.
# Note for anyone comparing against LEON: LEON awards the 15:00/16:00 seat cap
# outright whenever the crew is augmented and a rest facility exists, without
# reference to the rest actually taken, and never uses the bunk tier.
RELIEF_MINIMUM_REST = timedelta(hours=3)
RELIEF_CAPS: Mapping[tuple[str, CrewType], timedelta] = {
    ("bunk", "cockpit"): timedelta(hours=18),
    ("bunk", "cabin"): timedelta(hours=19),
    ("seat", "cockpit"): timedelta(hours=15),
    ("seat", "cabin"): timedelta(hours=16),
}
# Split duty (OM 7.1-6 2-3; ECAR 121.505 / CAP 371 §13.1 UNVERIFIED): ground
# rest under 3 h extends nothing; 3–10 h extends the FDP by half the
# consecutive rest. Confirmed verbatim in the OM, which states no cap of its
# own — the table's domain stops at 10 h, so its implied ceiling is 5:00.
SPLIT_DUTY_MINIMUM_REST = timedelta(hours=3)
SPLIT_DUTY_MAXIMUM_REST = timedelta(hours=10)

# The four Table A rows, by LOCAL time of the FDP start.
BAND_06_08 = "06:00-07:59"
BAND_08_15 = "08:00-14:59"
BAND_15_22 = "15:00-21:59"
BAND_22_06 = "22:00-05:59"
TABLE_A_BANDS = (BAND_06_08, BAND_08_15, BAND_15_22, BAND_22_06)

# Table B rows, by length of preceding rest.
REST_OVER_30 = "over_30"
REST_18_TO_30 = "18_to_30"
REST_UNDER_18 = "under_18"


def _hm(text: str) -> timedelta:
    hours, minutes = text.split(":")
    return timedelta(hours=int(hours), minutes=int(minutes))


def _row(*cells: str) -> tuple[timedelta, ...]:
    return tuple(_hm(cell) for cell in cells)


@dataclass(frozen=True)
class FdpTables:
    """One published version of Tables A and B, verbatim."""

    version: str
    source: str
    # Table A: band -> limits for 1..8+ sectors (8 cells).
    table_a: Mapping[str, tuple[timedelta, ...]]
    # Table B: rest band -> limits for 1..7+ sectors (7 cells).
    table_b: Mapping[str, tuple[timedelta, ...]]
    # Which Table B row a preceding rest under 18 h uses; None = not permitted.
    under_18_row: str | None

    def table_a_limit(self, band: str, sectors: int) -> timedelta:
        row = self.table_a[band]
        return row[min(max(sectors, 1), len(row)) - 1]

    def rest_band(self, preceding_rest: timedelta) -> str | None:
        if preceding_rest > timedelta(hours=30):
            return REST_OVER_30
        if preceding_rest >= timedelta(hours=18):
            return REST_18_TO_30
        return self.under_18_row

    def table_b_limit(self, rest_band: str, sectors: int) -> timedelta:
        row = self.table_b[rest_band]
        return row[min(max(sectors, 1), len(row)) - 1]


# The owner's document: EgyptAir OM Chapter 7, STD SEP.09, page 7.1-4 and the
# printed Table A/B page. Fractions read as quarters (9¼ = 9:15). Verified
# cell for cell against the Arabic 7.1-4 / 7.1-5 pages. Two cells there are
# typeset non-monotonically (Table A 22:00–05:59 × 6 sectors, Table B row 1 ×
# 6–7 sectors); the monotonic English insert is used, and neither cell is
# reachable — no Red Sea duty exceeds 4 sectors.
TABLES_OM_2009 = FdpTables(
    version="om-2009",
    source="EgyptAir Operations Manual Ch.7 Flight Time Limitation, STD SEP.09 (reference.pdf)",
    table_a={
        BAND_06_08: _row("13:00", "12:15", "11:30", "10:45", "10:00", "9:15", "9:00", "9:00"),
        BAND_08_15: _row("14:00", "13:15", "12:30", "11:45", "11:00", "10:15", "9:30", "9:00"),
        BAND_15_22: _row("13:00", "12:15", "11:30", "10:45", "10:00", "9:15", "9:00", "9:00"),
        BAND_22_06: _row("11:00", "10:15", "9:30", "9:00", "9:00", "9:00", "9:00", "9:00"),
    },
    table_b={
        REST_OVER_30: _row("13:00", "12:15", "11:30", "10:45", "10:00", "9:15", "9:00"),
        REST_18_TO_30: _row("12:00", "11:15", "10:30", "9:45", "9:00", "9:00", "9:00"),
    },
    # OM/CAP 371 label the first row "Over 30": a rest under 18 h before a
    # non-acclimatised start has no row, i.e. it is not a rosterable FDP.
    under_18_row=None,
)

# ECAR Part 121 Subpart Q, 01-Jan-2016, 121.503. UNVERIFIED against an
# official ECAA text — transcribed from a third-party copy and kept only so
# ruling R1 has something to select. Differs from the 2009 OM in the
# 08:00–14:59 row (3–8 sectors) and labels Table B's first row
# "Up to 18 or over 30". LEON is configured with the OM-2009 values.
TABLES_ECAR_2016 = FdpTables(
    version="ecar-2016",
    source="ECAR Part 121 Subpart Q, The Avoidance of Excessive Fatigue in Aircrew, 01-Jan-2016",
    table_a={
        BAND_06_08: _row("13:00", "12:15", "11:30", "10:45", "10:00", "9:15", "9:00", "9:00"),
        BAND_08_15: _row("14:00", "13:15", "11:45", "11:15", "10:45", "10:15", "9:45", "9:30"),
        BAND_15_22: _row("13:00", "12:15", "11:30", "10:45", "10:00", "9:15", "9:00", "9:00"),
        BAND_22_06: _row("11:00", "10:15", "9:30", "9:00", "9:00", "9:00", "9:00", "9:00"),
    },
    table_b={
        REST_OVER_30: _row("13:00", "12:15", "11:30", "10:45", "10:00", "9:15", "9:00"),
        REST_18_TO_30: _row("12:00", "11:15", "10:30", "9:45", "9:00", "9:00", "9:00"),
    },
    under_18_row=REST_OVER_30,
)

TABLES_BY_VERSION: Mapping[str, FdpTables] = {
    TABLES_OM_2009.version: TABLES_OM_2009,
    TABLES_ECAR_2016.version: TABLES_ECAR_2016,
}
# The owner supplied the 2009 OM; it stays the default until ruling R1.
DEFAULT_TABLES = TABLES_OM_2009


def tables_for(version: str | None) -> FdpTables:
    if not version:
        return DEFAULT_TABLES
    try:
        return TABLES_BY_VERSION[version.strip().lower()]
    except KeyError as exc:
        raise ValueError(
            f"Unknown FDP table version {version!r}; expected one of {sorted(TABLES_BY_VERSION)}"
        ) from exc


# --- Local time ---------------------------------------------------------------


def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    """weekday: Monday=0 … Sunday=6."""

    next_month = date(year + (month == 12), month % 12 + 1, 1)
    last_day = next_month - timedelta(days=1)
    return last_day - timedelta(days=(last_day.weekday() - weekday) % 7)


def egypt_utc_offset(moment_utc: datetime) -> timedelta:
    """Egypt standard time is UTC+2. Since 2023 daylight saving (UTC+3) runs
    from 00:00 local on the last Friday of April to 24:00 local on the last
    Thursday of October. 2015–2022 had no DST."""

    year = moment_utc.year
    if year < 2023:
        return timedelta(hours=2)
    dst_start = datetime.combine(_last_weekday_of_month(year, 4, 4), time.min, tzinfo=timezone.utc) - timedelta(hours=2)
    dst_end = datetime.combine(_last_weekday_of_month(year, 10, 3) + timedelta(days=1), time.min, tzinfo=timezone.utc) - timedelta(hours=3)
    return timedelta(hours=3) if dst_start <= moment_utc < dst_end else timedelta(hours=2)


def start_band(local_start: datetime) -> str:
    minutes = local_start.hour * 60 + local_start.minute
    if 6 * 60 <= minutes < 8 * 60:
        return BAND_06_08
    if 8 * 60 <= minutes < 15 * 60:
        return BAND_08_15
    if 15 * 60 <= minutes < 22 * 60:
        return BAND_15_22
    return BAND_22_06


# --- Extensions (implemented for completeness; not applied in shadow mode) -----


def relief_extension(total_in_flight_rest: timedelta, *, in_bunk: bool, crew_type: CrewType = "cockpit") -> timedelta:
    """How much in-flight relief adds to the table limit (before the cap)."""

    if total_in_flight_rest < RELIEF_MINIMUM_REST:
        return timedelta(0)
    return total_in_flight_rest / (2 if in_bunk else 3)


def relief_cap(*, in_bunk: bool, crew_type: CrewType = "cockpit") -> timedelta:
    return RELIEF_CAPS[("bunk" if in_bunk else "seat", crew_type)]


def split_duty_extension(consecutive_ground_rest: timedelta) -> timedelta:
    """Half the ground rest when it is 3–10 h; nothing outside that range
    (under 3 h is no rest; over 10 h is a rest period, not a split)."""

    if SPLIT_DUTY_MINIMUM_REST <= consecutive_ground_rest <= SPLIT_DUTY_MAXIMUM_REST:
        return consecutive_ground_rest / 2
    return timedelta(0)


# --- Assessment ------------------------------------------------------------------


@dataclass(frozen=True)
class FdpWindow:
    start_utc: datetime
    end_utc: datetime
    sectors: int
    leg_keys: tuple[str, ...]

    @property
    def planned(self) -> timedelta:
        return self.end_utc - self.start_utc


@dataclass(frozen=True)
class FdpAssessment:
    """One duty measured against the two-pilot limit."""

    tables_version: str
    crew_type: CrewType
    window: FdpWindow
    local_start: datetime
    band: str
    table: str                       # "A" or "B"
    acclimatised: bool
    limit: timedelta | None          # None: no rosterable limit (Table B, rest < 18 h)
    limit_reason: str
    trace: tuple[HeavyTraceStep, ...] = field(default_factory=tuple)

    @property
    def margin(self) -> timedelta | None:
        return None if self.limit is None else self.window.planned - self.limit

    # NOT a Heavy verdict, and not a claim about why crew were rostered: it is
    # "the planned duty is longer than the base two-pilot table limit" and
    # nothing else. The name is kept because it is read by the schema, the
    # trace and the back-test tool. See the retraction in the module docstring.
    @property
    def needs_augmentation(self) -> bool | None:
        return None if self.limit is None else self.window.planned > self.limit


def _parsed(legs: Sequence[AllowanceLeg]) -> list[tuple[AllowanceLeg, datetime, datetime]]:
    parsed = []
    for leg in legs:
        times = parse_leg_start_end(leg)
        if times is not None:
            parsed.append((leg, times[0], times[1]))
    parsed.sort(key=lambda item: item[1])
    return parsed


def _position(leg: AllowanceLeg) -> str:
    return (leg.position or "").strip().upper()


def rotation_window(legs: Sequence[AllowanceLeg]) -> FdpWindow | None:
    """The duty as a two-pilot crew would have to fly it: every leg a sector,
    report 1:30 before the first departure, off duty 0:30 after the last
    landing (OM 7.1-4 2-1-3). This answers "is this rotation longer than the
    base two-pilot limit?" — a regulatory question. It does not answer "is
    this rotation Heavy?", which is a Red Sea policy question decided
    elsewhere."""

    parsed = _parsed(legs)
    if not parsed:
        return None
    return FdpWindow(
        start_utc=parsed[0][1] - REPORT_BEFORE_DEPARTURE,
        end_utc=max(end for _, _, end in parsed) + POST_FLIGHT_DUTY,
        sectors=len(parsed),
        leg_keys=tuple(leg.key for leg, _, _ in parsed),
    )


def member_window(legs: Sequence[AllowanceLeg]) -> FdpWindow | None:
    """One member's own FDP: positioning before the first operated leg is
    inside the FDP but not a sector (OM 7.1-7 2-4-1 — a positioning member's
    landings are not counted for him, and travel immediately before operating
    is counted continuously); positioning after the last operated leg is duty,
    not FDP (inferred from 7.1-7 2-4-1 read with 7.1-6 2-2-4 and the 7.1-2 §3
    duty-period definition; ECAR 121.506 / 121.504(d) UNVERIFIED). Neutral
    positions (OBS, STB, SP, OPS) are ignored. None when the member operated
    nothing."""

    parsed = [(leg, s, e) for leg, s, e in _parsed(legs) if _position(leg) not in NEUTRAL_POSITIONS]
    operated = [(leg, s, e) for leg, s, e in parsed if _position(leg) not in RIDE_POSITIONS and _position(leg) != "PSN"]
    if not operated:
        return None
    last_operated_end = max(end for _, _, end in operated)
    # Rides that precede the first operated leg belong to the FDP.
    first_operated_start = operated[0][1]
    in_fdp = [(leg, s, e) for leg, s, e in parsed if s <= first_operated_start or (leg, s, e) in operated]
    return FdpWindow(
        start_utc=in_fdp[0][1] - REPORT_BEFORE_DEPARTURE,
        end_utc=last_operated_end + POST_FLIGHT_DUTY,
        sectors=len(operated),
        leg_keys=tuple(leg.key for leg, _, _ in in_fdp),
    )


def assess(
    window: FdpWindow,
    *,
    tables: FdpTables = DEFAULT_TABLES,
    crew_type: CrewType = "cockpit",
    acclimatised: bool = True,
    preceding_rest: timedelta | None = None,
    local_offset: timedelta | None = None,
) -> FdpAssessment:
    """Measure a window against the applicable table, with a trace.

    ``acclimatised`` defaults to True because the data to decide otherwise
    (previous duty end place/time) is not in the report yet (ruling R4 in
    the plan); Table B is implemented and tested for when it is.
    """

    offset = egypt_utc_offset(window.start_utc) if local_offset is None else local_offset
    local_start = window.start_utc.astimezone(timezone(offset))
    band = start_band(local_start)
    steps: list[HeavyTraceStep] = [
        step(
            "FDP_SHADOW_WINDOW",
            f"FDP {format_break(window.planned)} over {window.sectors} sector(s)",
            report_utc=window.start_utc.strftime("%Y-%m-%dT%H:%MZ"),
            off_duty_utc=window.end_utc.strftime("%Y-%m-%dT%H:%MZ"),
            local_start=local_start.strftime("%H:%M") + f" (UTC{'+' if offset >= timedelta(0) else '-'}{abs(offset).seconds // 3600})",
            rule="1:30 before first departure to 0:30 after last landing (OM 2-1-3)",
            legs=list(window.leg_keys),
        )
    ]

    if acclimatised or preceding_rest is None:
        table = "A"
        limit: timedelta | None = tables.table_a_limit(band, window.sectors)
        limit_reason = f"Table A ({tables.version}), local start {band}, {window.sectors} sector(s)"
        if not acclimatised:
            limit_reason += "; preceding rest unknown, Table A assumed"
    else:
        table = "B"
        rest_band = tables.rest_band(preceding_rest)
        if rest_band is None:
            limit = None
            limit_reason = (
                f"Table B ({tables.version}): preceding rest {format_break(preceding_rest)} is under 18 h — "
                "no rosterable limit"
            )
        else:
            limit = tables.table_b_limit(rest_band, window.sectors)
            limit_reason = f"Table B ({tables.version}), preceding rest {format_break(preceding_rest)} ({rest_band}), {window.sectors} sector(s)"
    if limit is not None and crew_type == "cabin":
        limit = limit + CABIN_FDP_EXTRA
        limit_reason += "; cabin +1:00 (OM 7-2-1)"

    steps.append(
        step(
            "FDP_SHADOW_LIMIT",
            "no limit" if limit is None else f"maximum FDP {format_break(limit)}",
            table=table,
            tables_version=tables.version,
            band=band,
            sectors=window.sectors,
            acclimatised=acclimatised,
            crew_type=crew_type,
            reason=limit_reason,
        )
    )
    assessment = FdpAssessment(
        tables_version=tables.version,
        crew_type=crew_type,
        window=window,
        local_start=local_start,
        band=band,
        table=table,
        acclimatised=acclimatised,
        limit=limit,
        limit_reason=limit_reason,
    )
    # The wording below ("needs augmentation (Heavy)") is the shipped trace
    # text and is kept byte-for-byte so recorded traces stay comparable. It is
    # inaccurate: the step reports one thing only — whether the planned duty
    # exceeds the base two-pilot table limit. It is not a Heavy verdict, and a
    # Heavy verdict is never derived from it. See the module docstring.
    steps.append(
        step(
            "FDP_SHADOW_VERDICT",
            (
                "undetermined"
                if assessment.needs_augmentation is None
                else f"{'over' if assessment.needs_augmentation else 'within'} the two-pilot limit by "
                f"{format_break(abs(assessment.margin))} -> {'needs augmentation (Heavy)' if assessment.needs_augmentation else 'two-pilot legal (not Heavy)'}"
            ),
            planned=format_break(window.planned),
            limit=None if limit is None else format_break(limit),
            margin=None if assessment.margin is None else format_break(assessment.margin),
            note="shadow only — does not change the verdict, the export, or the credit",
        )
    )
    return FdpAssessment(**{**assessment.__dict__, "trace": tuple(steps)})


def assess_rotation(legs: Sequence[AllowanceLeg], **options) -> FdpAssessment | None:
    window = rotation_window(legs)
    return None if window is None else assess(window, **options)


def assess_member(legs: Sequence[AllowanceLeg], **options) -> FdpAssessment | None:
    window = member_window(legs)
    return None if window is None else assess(window, **options)

"""Heavy allowance credits — per MEMBER, per DUTY (owner model, 2026-08-20).

Validated against the manual reference workbook "Cockpit July Crew Allowance":
54 of 55 named cockpit members matched exactly (the one exception is a
suspected omission in the sheet itself, flagged to the owner). The old
flight-level verdict matched 6 of 54.

The model, in full:

  H.C(member) = number of the member's DUTIES that earn a credit.

  duty   = maximal run of the member's own legs joined by breaks strictly
           below 4h. Calendar dates never gate anything: 21:50 -> 03:35(+1)
           is one duty. A duty belongs to the UTC date of its FIRST leg
           (the anchor), and is credited only if that anchor falls inside
           the requested window.

  credit = (a) LEON crewAugmentation True on >=1 leg the member OPERATED
               (the 3-pilot CGN/OSL sectors: LEON marks the whole operating
               cockpit), or
           (b) the member OPERATED >=1 leg and RODE PAD on >=1 leg of the
               same duty (the crew-swap pattern: fly out, rest back).

  OBS / OBS2 / STB / SP / OPS are NEUTRAL: never operate, never ride.
  PSN rides ONLY on a rotation-scale sector (>= PSN_RIDE_MINIMUM): the airline
  codes the swap-rest leg sometimes PAD, sometimes PSN (owner cases 09-06 and
  29-06). A short PSN base shuttle stays neutral — July evidence: a 0:40
  shuttle inside an operated duty earned nothing in the reference sheet.

  EVN sectors contribute nothing in either role (owner absolute; numerically
  neutral in the July validation but kept as ruled).

  An SVX sector is NOT a credit source by itself: adding "operated an SVX
  leg" over-counted July (50/54 vs 52/54). SVX rotations are crew-swap duties,
  so rule (b) already credits the members who actually augmented.

Pure module: no I/O, no service imports, plain dataclasses only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Mapping, Sequence

from .positions import airport_code_forms
from .trace import format_break

BREAK_LIMIT = timedelta(hours=4)
RIDE_POSITIONS = frozenset({"PAD"})
# PSN is a ride ONLY on a rotation-scale sector (owner cases 09-06 and 29-06:
# CPT+PSN and PSN+FO across OPO leg pairs of 5:20-5:45 must credit). A short
# PSN base shuttle is mere repositioning and stays neutral - July evidence:
# Karim Fekry's 0:40 HRG->SSH shuttle inside an operated duty earned nothing
# in the reference sheet. The threshold sits between those observed extremes
# (0:50 shuttles vs 5h+ rotation sectors); July revalidates at 53/54 with it.
PSN_RIDE_MINIMUM = timedelta(hours=2)
NEUTRAL_POSITIONS = frozenset({"OBS", "OBS2", "STB", "SP", "OPS", "FAOBS"})
_EVN_FORMS = airport_code_forms("EVN")

CREDIT_LEON = "LEON_AUGMENTED"
CREDIT_SWAP = "OPERATE_PLUS_RIDE"


@dataclass(frozen=True)
class AllowanceLeg:
    """One leg of one member, exactly as the report row carries it."""

    key: str                      # flight_nid — identifies the leg back in the UI
    flight_date: str | None      # DD-MM-YYYY (live rows) — or None
    start_time: str | None       # HH:MM or full ISO
    end_time: str | None
    position: str | None
    leon_heavy: bool | None
    departure_airport: str | None
    arrival_airport: str | None


@dataclass(frozen=True)
class DutyCredit:
    """One duty of one member, with the verdict and why."""

    anchor_utc_date: str
    credited: bool
    source: str | None            # CREDIT_LEON | CREDIT_SWAP | None
    reason: str
    leg_keys: tuple[str, ...]


@dataclass(frozen=True)
class AllowanceResult:
    credits: int
    duties: tuple[DutyCredit, ...]
    # leg key -> (in a credited duty, its source); legs with unusable times
    # are absent and therefore never painted as credited.
    by_leg: Mapping[str, tuple[bool, str | None]]


def _parse_leg_start_end(leg: AllowanceLeg) -> tuple[datetime, datetime] | None:
    """UTC start/end from either a full ISO stamp or date + HH:MM.

    Live report rows carry `flight_date` as DD-MM-YYYY and times as bare HH:MM;
    an end at or before the start crosses midnight. Unusable times exclude the
    leg from duty chaining entirely — a chain cannot be built on guesses.
    """

    start_text = (leg.start_time or "").strip()
    end_text = (leg.end_time or "").strip()
    if not start_text or not end_text:
        return None

    iso = _parse_iso_pair(start_text, end_text)
    if iso is not None:
        return iso

    date_text = (leg.flight_date or "").strip()
    if not date_text:
        return None
    try:
        day = datetime.strptime(date_text, "%d-%m-%Y").replace(tzinfo=timezone.utc)
        h1, m1 = (int(part) for part in start_text.split(":")[:2])
        h2, m2 = (int(part) for part in end_text.split(":")[:2])
    except (ValueError, AttributeError):
        return None
    start = day.replace(hour=h1, minute=m1)
    end = day.replace(hour=h2, minute=m2)
    if end <= start:
        end += timedelta(days=1)
    return start, end


def _parse_iso_pair(start_text: str, end_text: str) -> tuple[datetime, datetime] | None:
    def one(text: str) -> datetime | None:
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    start = one(start_text)
    end = one(end_text)
    if start is None or end is None:
        return None
    return start, end


def _is_evn_leg(leg: AllowanceLeg) -> bool:
    codes = {
        (leg.departure_airport or "").strip().upper(),
        (leg.arrival_airport or "").strip().upper(),
    }
    return bool(codes & _EVN_FORMS)


def _judge_duty(
    legs: Sequence[tuple[AllowanceLeg, timedelta]],
) -> tuple[str | None, str]:
    operated = ridden = leon_aug = False
    for leg, duration in legs:
        position = (leg.position or "").strip().upper()
        if position in NEUTRAL_POSITIONS:
            continue
        if _is_evn_leg(leg):
            continue
        if position in RIDE_POSITIONS:
            ridden = True
            continue
        if position == "PSN":
            if duration >= PSN_RIDE_MINIMUM:
                ridden = True
            continue
        operated = True
        if leg.leon_heavy is True:
            leon_aug = True

    if leon_aug:
        return CREDIT_LEON, "LEON marked an operated sector augmented"
    if operated and ridden:
        return CREDIT_SWAP, "operated one leg and rode another in the same duty"
    if ridden:
        return None, "rode PAD only — no operated leg in this duty"
    if operated:
        return None, "operated only — no PAD leg and no LEON augmentation"
    return None, "no operated or PAD leg (neutral slots / EVN only)"


def compute_member_credits(
    legs: Sequence[AllowanceLeg],
    *,
    window_start: str | None = None,
    window_end: str | None = None,
) -> AllowanceResult:
    """The member's H.C for the window, with one DutyCredit per duty."""

    timed: list[tuple[datetime, datetime, AllowanceLeg]] = []
    for leg in legs:
        parsed = _parse_leg_start_end(leg)
        if parsed is not None:
            timed.append((parsed[0], parsed[1], leg))
    timed.sort(key=lambda item: item[0])

    duties: list[list[tuple[datetime, datetime, AllowanceLeg]]] = []
    current: list[tuple[datetime, datetime, AllowanceLeg]] = []
    previous_end: datetime | None = None
    for start, end, leg in timed:
        if previous_end is not None and (start - previous_end) >= BREAK_LIMIT:
            duties.append(current)
            current = []
        current.append((start, end, leg))
        previous_end = end
    if current:
        duties.append(current)

    results: list[DutyCredit] = []
    by_leg: dict[str, tuple[bool, str | None]] = {}
    credits = 0
    for duty in duties:
        anchor = duty[0][0]
        anchor_date = anchor.date().isoformat()
        in_window = _within(anchor_date, window_start, window_end)
        source, reason = _judge_duty([(leg, end - start) for start, end, leg in duty])
        credited = in_window and source is not None
        if not in_window:
            reason = f"duty anchored {anchor_date}, outside the requested window"
            source = None
        if credited:
            credits += 1
        results.append(
            DutyCredit(
                anchor_utc_date=anchor_date,
                credited=credited,
                source=source if credited else None,
                reason=reason,
                leg_keys=tuple(leg.key for _, _, leg in duty),
            )
        )
        for _, _, leg in duty:
            by_leg[leg.key] = (credited, source if credited else None)

    return AllowanceResult(credits=credits, duties=tuple(results), by_leg=by_leg)


def _within(anchor_date: str, window_start: str | None, window_end: str | None) -> bool:
    if window_start and anchor_date < window_start:
        return False
    if window_end and anchor_date > window_end:
        return False
    return True


def describe_break_limit() -> str:
    """The strict limit as shown in traces (kept with format_break for parity)."""

    return format_break(BREAK_LIMIT)

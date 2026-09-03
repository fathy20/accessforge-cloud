"""Heavy allowance credits — per MEMBER, per DUTY.

First validated 2026-08-20 against the manual reference workbook "Cockpit July
Crew Allowance" (54 of 55 named cockpit members; the exception is a suspected
omission in the sheet itself). Extended 2026-09-02 by owner ruling with the
sector minimum, the domestic veto, the strict 3h link, and month-boundary
painting.

The model, in full:

  H.C(member) = number of the member's DUTIES that earn a credit.

  duty   = maximal run of the member's own legs joined by breaks strictly
           below 4h. Calendar dates never gate anything: 21:50 -> 03:35(+1)
           is one duty. A duty belongs to the UTC date of its FIRST leg (the
           anchor). The duty EARNS on its own merits; the credit is COUNTED
           only when the anchor falls inside the requested window — so a
           rotation straddling a month end paints both of its legs Heavy on
           their respective sheets and is paid exactly once, in the month it
           departed.

  credit = (a) LEON crewAugmentation True on >=1 leg the member OPERATED
               (the 3-pilot CGN/OSL sectors: LEON marks the whole operating
               cockpit). LEON's value is authoritative — the gates below
               never re-judge it. Or:
           (b) the crew-swap pattern: the member RODE (any PAD; a PSN only
               when chained to a neighbouring leg by a break under 3:00) and
               OPERATED an international sector longer than 4:00, with a
               break under 3:00 between the ride and that sector.

  Domestic sectors (both ends Egyptian) never qualify, never accumulate
  hours toward the minimum, and are painted No even inside a credited swap
  duty (owner 23-06 case: the HRG->SSH shuttle reads No while the SSH->OPO
  leg of the same duty reads Yes).

  OBS / OBS2 / STB / SP / OPS are NEUTRAL: never operate, never ride.

  EVN sectors contribute nothing in either role (owner absolute; also
  subsumed by the sector minimum — EVN legs run ~2:40-2:55).

  An SVX sector is NOT a credit source by itself: adding "operated an SVX
  leg" over-counted July (50/54 vs 52/54). SVX rotations are crew-swap duties,
  so rule (b) already credits the members who actually augmented.

Pure module: no I/O, no service imports, plain dataclasses only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Mapping, Sequence

from .positions import airport_code_forms, is_domestic_sector
from .trace import format_break

BREAK_LIMIT = timedelta(hours=4)
# A sector only carries a rotation when it is long enough to BE one (owner
# ruling 2026-09-02). Strictly greater: exactly 4:00 does not qualify.
# Evidence it is per-sector and never a sum: Karim Fekry's 11-07 duty totals
# 6:30 across a 0:40 shuttle and two ~3:15 sectors, and the July sheet paid it
# nothing. Applies ONLY to the local swap rule — never to a value LEON stated.
SECTOR_MINIMUM = timedelta(hours=4)
# The ride and the operated sector must belong to the same rotation, not merely
# the same duty: owner ruling 2026-09-02, "the break is LESS than 3 hours" —
# strictly under, so exactly 3:00 does not link. The real July pairs sit at
# 1:05-1:30, comfortably inside it.
SWAP_LINK_BREAK = timedelta(hours=3)
# Any PAD is a ride — no extra condition (owner ruling 2026-09-02).
RIDE_POSITIONS = frozenset({"PAD"})
# A PSN leg rides only when chained to the member's neighbouring leg — the one
# before or the one after — by a break strictly under this (owner ruling
# 2026-09-02: "PSN — look at the one before or after it; the break is less than
# 3 hours"). Calendar dates never gate the chain: an overnight rotation return
# chains exactly like a same-day one, consistent with the duty model above.
PSN_CHAIN_BREAK = timedelta(hours=3)
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


def _is_domestic_leg(leg: AllowanceLeg) -> bool:
    return is_domestic_sector(leg.departure_airport, leg.arrival_airport)


def _gap(
    first: tuple[datetime, datetime],
    second: tuple[datetime, datetime],
) -> timedelta:
    """Ground time between two sectors, whichever of them flew first."""

    first_start, first_end = first
    second_start, second_end = second
    if second_start >= first_end:
        return second_start - first_end
    if second_end <= first_start:
        return first_start - second_end
    return timedelta(0)


def _psn_chained(
    start: datetime,
    end: datetime,
    previous: tuple[AllowanceLeg, datetime, datetime] | None,
    following: tuple[AllowanceLeg, datetime, datetime] | None,
) -> bool:
    """Is this PSN leg chained to a neighbouring leg?

    Chained = the break to the neighbour before or after is strictly under
    PSN_CHAIN_BREAK. Either neighbour is enough; calendar dates never gate it
    (owner ruling 2026-09-02 — an overnight return chains like a same-day one).
    """

    if previous is not None:
        _, _, prev_end = previous
        if timedelta(0) <= (start - prev_end) < PSN_CHAIN_BREAK:
            return True
    if following is not None:
        _, next_start, _ = following
        if timedelta(0) <= (next_start - end) < PSN_CHAIN_BREAK:
            return True
    return False


def _judge_duty(
    legs: Sequence[tuple[AllowanceLeg, datetime, datetime]],
) -> tuple[str | None, str]:
    """Judge one duty of one member against the owner's rule set.

    Every leg here is already the member's own record (the AugmentedIndex is
    keyed per crew member + sector). PSN chain evidence: owner cases 09-06
    (CPT HRG->OPO 13:20, PSN OPO->SSH 14:45 -> 1:25 break) and 29-06
    (PSN HRG->OPO 20:20, FO back 21:25 -> 1:05 break).

    The swap credit does NOT require a ride. It requires a qualifying
    international sector (over the sector minimum) paired, under the link
    break, with ANY other real leg of the duty — a PAD/PSN ride, or another
    operated leg (owner ruling 2026-09-02, the "Cairo to Russia and back"
    example: both legs are operated, neither is a ride, both are Heavy).
    A domestic leg is never that partner either: 23-06 stays uncredited
    because its only neighbour, HRG->SSH, is domestic and so contributes
    nothing — the member needed a genuine return to earn it, and had none.
    """

    ordered = sorted(legs, key=lambda item: item[1])
    rides: list[tuple[datetime, datetime]] = []
    operated: list[tuple[AllowanceLeg, datetime, datetime]] = []
    member_leon_augmented = False
    for index, (leg, start, end) in enumerate(ordered):
        position = (leg.position or "").strip().upper()
        if position in NEUTRAL_POSITIONS:
            continue
        if _is_evn_leg(leg):
            continue
        if position in RIDE_POSITIONS:
            rides.append((start, end))
            continue
        if position == "PSN":
            previous = ordered[index - 1] if index > 0 else None
            following = ordered[index + 1] if index + 1 < len(ordered) else None
            if _psn_chained(start, end, previous, following):
                rides.append((start, end))
            continue
        operated.append((leg, start, end))
        if leg.leon_heavy is True:
            member_leon_augmented = True

    # LEON's own crewAugmentation is authoritative and is never re-judged here
    # (owner ruling 2026-09-02: "LEON pulls it correctly"). The sector minimum
    # and the domestic veto exist to fill the gap where LEON said nothing —
    # they do not overrule what it did say.
    if member_leon_augmented:
        return CREDIT_LEON, "LEON marked an operated sector augmented"
    if not operated:
        return None, "rode PAD only — no operated leg in this duty"

    # International operated legs can partner each other, same as a ride:
    # a genuine round trip (operate out, operate back) is exactly as Heavy
    # as operate-out/ride-back. Domestic legs never partner anything.
    international_operated = [
        (leg, start, end) for leg, start, end in operated if not _is_domestic_leg(leg)
    ]

    for index, (leg, start, end) in enumerate(international_operated):
        if (end - start) <= SECTOR_MINIMUM:
            continue
        partners = rides + [
            (other_start, other_end)
            for other_index, (_, other_start, other_end) in enumerate(international_operated)
            if other_index != index
        ]
        if any(_gap((start, end), partner) < SWAP_LINK_BREAK for partner in partners):
            return (
                CREDIT_SWAP,
                "operated an international sector over "
                f"{format_break(SECTOR_MINIMUM)} with another leg of the duty "
                f"under {format_break(SWAP_LINK_BREAK)} from it",
            )
    return (
        None,
        "no operated sector qualifies: each is domestic, at or under "
        f"{format_break(SECTOR_MINIMUM)}, or has no other leg of the duty "
        f"under {format_break(SWAP_LINK_BREAK)} from it",
    )


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
        source, reason = _judge_duty([(leg, start, end) for start, end, leg in duty])
        # A duty that straddles a month end is ONE rotation and both of its
        # legs are Heavy, whichever sheet each lands on (owner ruling
        # 2026-09-02). The window only decides where the CREDIT is counted —
        # against the month of the first sector — so a rotation is never paid
        # twice and never disappears from the sheet it flew in.
        earned = source is not None
        counted = earned and in_window
        if earned and not in_window:
            reason = (
                f"{reason}; counted against {anchor_date}, outside this window"
            )
        elif not in_window:
            reason = f"duty anchored {anchor_date}, outside the requested window"
        if counted:
            credits += 1
        results.append(
            DutyCredit(
                anchor_utc_date=anchor_date,
                credited=counted,
                source=source if counted else None,
                reason=reason,
                leg_keys=tuple(leg.key for _, _, leg in duty),
            )
        )
        # Every leg inherits the duty verdict EXCEPT two carve-outs that are
        # painted No without touching the count: a PSN leg that did not itself
        # satisfy the chain rule (it merely sits inside a heavy duty, e.g. an
        # early repositioning after an overnight PAD return), and a domestic
        # hop inside a swap-credited duty.
        for index, (start, end, leg) in enumerate(duty):
            position = (leg.position or "").strip().upper()
            # A domestic hop is never itself Heavy, even inside a credited
            # rotation (owner 23-06 ruling: the HRG->SSH 0:40 shuttle reads No
            # while the SSH->OPO leg of the same duty reads Yes). Only the
            # swap rule is carved: a CREDIT_LEON duty keeps painting all its
            # legs, because LEON's own value is never re-judged here.
            if earned and source == CREDIT_SWAP and _is_domestic_leg(leg):
                by_leg[leg.key] = (False, None)
                continue
            if earned and position == "PSN":
                previous = duty[index - 1] if index > 0 else None
                following = duty[index + 1] if index + 1 < len(duty) else None
                chained = _psn_chained(
                    start,
                    end,
                    (previous[2], previous[0], previous[1]) if previous else None,
                    (following[2], following[0], following[1]) if following else None,
                )
                if not chained:
                    by_leg[leg.key] = (False, None)
                    continue
            by_leg[leg.key] = (earned, source if earned else None)

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

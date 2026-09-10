# Crew Hours — Augmented Crew (Heavy) rules

The owner-approved rule set (agreed 2026-08-15/17) for deciding whether a leg
is "Heavy" (augmented crew). One engine implements it for every surface:
`backend/statistics/crew_hours/heavy.py::classify_flight_heavy`, used by both
the Crew Hours service and the Copilot. Output is always Yes/No, never
Unknown — except when the whole FTL index is unavailable.

Authoritative rationale:
`accessforge-cloud-main/accessforge-cloud-main/docs/architecture/crew-hours-heavy-precedence-adr-2026-08-17.md`.
Settled disputes: `../development/closed-questions.md`.

## Precedence (evaluated in order)

1. **Trainees excluded first.** Cockpit trainees by role slot (OPS/SP); cabin
   trainees by Work Schedule Function == "SFA" (never Position-only). NOTE:
   LEON currently rejects the `workSchedule { function }` selection, so cabin
   trainee detection is OFF in production and the report says so via
   `cabin_trainee_detection: "unavailable"`.
2. **EVN airport → never Heavy** (absolute; vetoes everything below, wins over
   SVX). **SVX airport → always Heavy** (absolute). Matched on ADEP/ADES
   codes; legacy flight tags are a secondary signal only. **Both code systems
   count** (2026-08-19): `SVX ↔ USSS`, `EVN ↔ UDYZ`, held in
   `positions.AIRPORT_CODE_ALIASES`; exact equality on either form, never a
   substring. The report row's preferred codes and the flight-list context's
   codes are UNIONED, and a match on any of them counts — one airport can
   arrive as IATA from one source and ICAO from the other.
3. **LEON's `crewAugmentation` value**, when present. If it disagrees with an
   airport absolute, the absolute wins and the row carries
   `heavy_conflict=True`, `heavy_source="LOCAL_RULE"` (warning logged).
4. **Operating-crew counts:** `cockpit_count > 2` or `cabin_count > 4` → Yes
   (`EXTRA_COCKPIT_CREW` / `EXTRA_CABIN_CREW`). Thresholds are the operator
   standard complement (2 cockpit + 4 cabin, derived from June 2026 data);
   positioning slots (PSN, PAD, OBS, OBS2, STB) never count as operating crew.
   A LEON-silent count-Yes is final — STEP 4 cannot override it.
5. **STEP 4 rotation resolver** — only when LEON is silent AND the count rule
   is UNKNOWN. Three parts of this were corrected by owner rulings on
   2026-08-19:
   - **A TRUE out-and-back**, not a chain: `neighbour.departure ==
     current.arrival` **AND** `neighbour.arrival == current.departure`. The old
     either-direction test made any same-direction pair with a stable roster
     and a short break report Heavy. Missing airport data still fails closed
     (`ROTATION_MISMATCH`).
   - **Break < 4h strict** (4:00 rejects), midnight-safe window anchored on the
     first sector's UTC start date. Unchanged.
   - **Crew CONTINUITY, not role identity**: each leg's comparison set is its
     operating crew UNION everyone present on BOTH legs in any capacity, plus
     the subject. A member who flew out as FO and rode home as PAD used to
     vanish from one side of a symmetric set equality and break the rotation for
     EVERY member of it. Riders present on only ONE leg stay excluded.
   - **Pairing direction**: the backward neighbour is always searched; the
     forward one only when nothing connected precedes this leg.
   - A member positioned PSN on the leg being judged is No immediately
     (`PSN_POSITIONING`). Unchanged.
   - **The badge means the resolver established Heavy = True.** A resolver No
     means "no qualifying rotation was found" and carries NO badge.
     `unknown_resolution_reason` is still recorded either way (diagnostic, not a
     claim), and `heavy_source` stays `LOCAL_RULE`.

6. **Every leg carries a `heavy_trace`** (2026-08-19) — the ordered list of
   rules evaluated, each with its outcome and the inputs it saw: airports as
   received in every form and from both sources, times as received, operating
   counts with thresholds, and the two crew sets compared. Shown as a
   `Decision trace` disclosure on the verdict cell of EVERY leg, deterministic
   or resolver-decided. Offline renderer for the four reviewed cases:
   `python -m backend.statistics.crew_hours.tools.heavy_cases`.

## Data joins

Report Wizard rows join the FTL index and flight-list index on
`unique_id == flightNid == trNid` — CONFIRMED live (id_probe, 2026-06-16/20/22,
RSX331 = 67230742 everywhere). Every run still reports
`augmented_lookup_hits/attempts`, `crew_context_hits/attempts` and
`join_health` ("DEGRADED" below a 50% hit rate against a non-empty index) as a
regression tripwire.

## Two crew-set concepts — deliberately different (M-2/I-2 rulings 2026-08-18)

- **TOTALS crew rule** — `CrewSlot.counts_in_totals` (PSN-only exclusion,
  2026-08-09 parity ruling). Governs per-member numeric block-time totals.
- **ROTATION crew identity** — `positions.crew_set_identity`, exposed as
  `NormalizedReportRow.rotation_crew_set` (duty grouping) and
  `unknown_resolver.rotation_crew_codes` (STEP-4 comparison). Excludes
  PSN, PAD, OBS, OBS2, STB (2026-08-17 one-identity ruling).
- **UI position-filter vocabulary** — frontend `UI_POSITION_FILTER_TOKENS`
  (6 tokens incl. FDP/FDPI/RMP/INSP) is a display filter ONLY; it is not,
  and must never be aligned with, the backend count rule
  (`POSITIONING_POSITIONS`, PSN/PAD).

Unifying any two of these silently changes displayed numbers or verdicts —
each carries a comment naming its governing ruling.

## Invariants (do not change without an owner ruling)

- Thresholds cockpit > 2 / cabin > 4 — re-derive from data if fleet or cabin
  policy changes; never restore the older inverted pair (cockpit > 4 /
  cabin > 2).
- UNKNOWN is never displayed; PAD block-time inclusion in numeric totals is
  unchanged by all of the above; official block-time totals are untouched.
- The red badge means only "the rotation resolver ESTABLISHED Heavy = True"
  (corrected 2026-08-19) — never anything else, and never a resolver No.
- `heavy.py`, `unknown_resolver.py`, and `trace.py` stay pure: no I/O, no
  service imports. `derive_heavy_detail` delegates to
  `derive_heavy_detail_traced`, so a traced verdict and an untraced one cannot
  diverge.

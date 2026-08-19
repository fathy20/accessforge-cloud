# ADR — Heavy Precedence (EVN/SVX above LEON) and the Midnight-Safe Duty Window

- Date: 2026-08-17 (amended twice same day: live UI review → Decision 1a;
  owner rulings Q1–Q3 → Decision 5: one engine for every surface)
- Status: Accepted, implemented, test-pinned
- Scope: `backend/statistics/crew_hours/heavy.py`, `unknown_resolver.py`,
  `crew_context.py`, `positions.py`, `service.py`, `schemas.py`, the
  crew-hours detail row UI
- Supersedes: the LEON-first precedence in `decide_heavy` and the
  calendar-date equality check in STEP 4

## Decision 1a — EVN/SVX are AIRPORT-based rules; tags kept as a secondary signal

**Live-review correction (2026-06 screenshots).** The absolute rules were
first wired to LEON `flightTags`; live data proved LEON does not tag these
flights — SVX (Yekaterinburg) and EVN (Yerevan) appear in the **route**
(ADEP/ADES). Evidence trail:

- RSX331 SSH→SVX and RSX332 SVX→SSH (16-06): no tag, no LEON value; the tag
  rule never fired, RSX331 read Yes only by resolver luck and RSX332 read No.
  Both must be **Yes / `SVX_AIRPORT`**, deterministically.
- RSX121/RSX122 SSH↔EVN (20/21-06): both must be **No / `EVN_AIRPORT`** by
  rule, not by the resolver — and therefore carry no resolver badge.

A flight is now an SVX flight when its departure **or** arrival airport equals
`SVX` (exact code match after trim+uppercase — never a substring match), or
the SVX tag is present; same for EVN. Route codes are collected from **both**
sources — the report row's `jl_adep_preferred_code`/`jl_ades_preferred_code`
and the flight-list `FlightContext` airports — and either source matching
counts. New reasons `EVN_AIRPORT`/`SVX_AIRPORT` were added; the existing
`EVN_TAG`/`SVX_TAG` literals remain valid for the tag path. (The Copilot path
had already independently established the airport-based interpretation:
`backend/statistics/crew_hours/cabin_heavy.py`, module docstring lines 9–12
— "SVX and EVN are airport codes, checked against ADEP/ADES … no flight in
the operator's data carries any tag at all" — landed in commit `6860c8e`,
imported by `backend/copilot/local_answers.py`, covered by
`backend/tests/test_cabin_heavy.py`.)

## Decision 1 — Absolute rules beat the LEON value

The approved business precedence is, highest first:

1. **EVN tag → Heavy = NO. Absolute.**
2. **SVX tag → Heavy = YES. Absolute.** (EVN wins if both ever co-occur.)
3. LEON `crewAugmentation` (`augmented|doubled|tripled` → YES, `normal` → NO).
4. Local operating-crew count (`cockpit > 2` or `cabin > 4`), after excluding
   cockpit trainees (OPS/SP), non-operating cockpit (OBS/OBS2/STB), cabin
   trainees (WorkSchedule Function `SFA`), and LINE_TRAINING/LINE_CHECK legs.
5. STEP 4 UNKNOWN resolver; everything unresolvable is NO, never UNKNOWN.

`decide_heavy` previously evaluated `leon_heavy` first, so a LEON value
overrode the tags — rules 1/2 could never beat rule 3. It now checks the tag
reasons (`EVN_TAG`/`SVX_TAG`, produced by `derive_heavy_detail`, which already
evaluated tags before counts) **before** the LEON value:

- Tag present → `effective_heavy` follows the tag, `heavy_source="LOCAL_RULE"`,
  `heavy_reason` is the tag.
- If LEON disagrees, `heavy_conflict=True` and a warning is logged — the report
  shows that the tag won rather than hiding the disagreement.
- No tag → the original LEON-first table is byte-for-byte unchanged.

## Decision 2 — Midnight-safe duty window in STEP 4

The old resolver rejected any neighbour whose UTC calendar date differed from
the current leg's (`DIFFERENT_DAY`), so a rotation departing 22:30Z and
returning 01:00Z next day — the classic out-and-back — could never resolve
Heavy. Dates are no longer compared directly:

- **The break gate is primary**: `0 <= break < 4h` strictly. 3:59 connects;
  **exactly 4:00 does not** (the old `> UNKNOWN_MAX_BREAK` comparison wrongly
  let 4:00 pass; per the 2026-08-09 parity report the invariant is
  `0 <= break < 4h`).
- A pair passing the break gate belongs to **one duty anchored on the first
  sector's UTC start date**, regardless of a midnight rollover.
- `DIFFERENT_DAY` is reserved for genuinely disjoint days: the neighbour
  starts on a different UTC date **and** more than 24 hours from the current
  leg's start (outside any duty window). A failed break inside that window —
  including exactly 4:00 across midnight — reports `BREAK_EXCEEDS_LIMIT`,
  because the break is the binding failure there. (The task's test matrix
  item 8 pins 4:00-across-midnight as `BREAK_EXCEEDS_LIMIT`; the 24-hour
  window is how "genuinely disjoint" is made precise and deterministic.)

## Decision 3 — Rotation continuity, PSN, and operating crew sets

- **Rotation continuity** is now required: a qualifying neighbour must chain
  airports with the current leg (`neighbour.departure == current.arrival` or
  `neighbour.arrival == current.departure`). `FlightContext` carries
  `departure_airport`/`arrival_airport` from the flight list (ICAO preferred,
  IATA fallback; both sides of the comparison come from the same source, so
  only internal consistency matters). Missing airport data **fails closed**
  as `ROTATION_MISMATCH` — continuity that cannot be established is not
  assumed.
- **PSN short-circuit**: a member positioned `PSN` on the current leg is NO
  immediately (`PSN_POSITIONING`), with no neighbour search. The existing
  "no position/function known → NO" (`UNKNOWN_POSITION`) is unchanged.
- **Operating crew comparison**: the same-crew check compares crew-code sets
  excluding every positioning/non-operating slot on either leg — `PSN`, `PAD`,
  and the non-operating cockpit slots `OBS`/`OBS2`/`STB` — order-independent.
  Live evidence: RSX6081 HRG→OPO (22-06) carried a cockpit `PAD` rider that
  RSX6082 OPO→HRG did not; with PSN-only exclusion the comparison failed and
  the rotation wrongly read No. PSN/PAD are likewise excluded from the
  operating cockpit/cabin counts (their block-time inclusion semantics are
  untouched). PAD members are **not** short-circuited the way PSN is: a PAD
  rider's row follows the flight-level absolute rules and, in STEP 4, their
  own rotation.
- The `_weaker` closest-near-miss reason ranking is preserved;
  `ROTATION_MISMATCH` ranks between `DIFFERENT_DAY` and
  `BREAK_EXCEEDS_LIMIT`.

## Knowledge base authority (added 2026-08-18)

The **repo-root `MCP_Memory/` tree** (two levels above this app directory,
tracked in this repository) is the one authoritative knowledge base. A nested
single-file `MCP_Memory/` next to the app code absorbed the 2026-08-17/18
decision entries while the root KB never saw them — that split is exactly how
this project briefly "lost" the settled join-key finding. The nested tree was
mirrored into the root decision log (`MCP_Memory/development/decision-log.md`)
and `MCP_Memory/development/closed-questions.md`, then deleted (history:
commits `e30917e` / `06611b0`). Do not recreate a nested MCP_Memory; new
decisions go to the root tree, with this ADR holding the full Heavy rationale.

## Decision 4 — Join health is instrumented, not assumed

**VERIFIED LIVE (probe runs on days 2026-06-16 / -20 / -22; recorded here
2026-08-18): `unique_id == flightNid == trNid`.** `id_probe.py` returned the
same number from all three endpoints — e.g. RSX331 = `67230742` in the Report
Wizard row, the flight list, and the FTL index — with airports returned as
ICAO (HESH→USSS). A full live June 2026 report subsequently showed
`join_health: OK` with `augmented_lookup_hits 1892/2493` and
`crew_context_hits 2107/2493`. The join key is confirmed; the instrumentation
below stays in place as a regression tripwire, not as an open question.

At design time the pipeline joined Report Wizard rows (`unique_id`) to the FTL
index (`trNid`) and the flight-list index (`flightNid`) on a then-unverified
assumption that these are the same number (the column ADR marks the report
identifiers AMBIGUOUS). If they differed, every lookup would miss and the
whole report silently read No. Instead of guessing a remapping:

- Every report run counts `augmented_lookup_hits/attempts` and
  `crew_context_hits/attempts` (a *hit* is key presence, so an ambiguous FTL
  value still counts as a joined identifier) and returns them in the response.
- `join_health: "DEGRADED"` is set — and a warning logged — when a hit rate
  is below 50% against a non-empty index: the "IDs don't match" signature.
  Empty or unavailable indices are not degradation; they are "LEON returned
  nothing".
- `backend/statistics/crew_hours/tools/id_probe.py` fetches one day from all
  three endpoints and prints `scope_row_unique_id`, `unique_id`,
  `unique_leg_number`, `trip_nid`, `flightNid`, and `trNid` side by side so an
  operator can confirm the key once against live data. Any remapping is a
  reviewed change, never an ad-hoc patch.

## UI

The red exclamation badge means exactly one thing: *this leg was not found in
LEON's augmented data and its verdict was decided by the local rotation rule.*

- **Every** leg that entered STEP 4 sets `unknown_resolved=True` and
  `heavy_source="LOCAL_RULE"` — Yes or No outcome alike — so **both** legs of
  a resolver-decided rotation carry the badge (live evidence: 22-06 RSX6081
  HRG→OPO and 23-06 RSX6084 OPO→SSH, both absent from augmented data, both
  badged).
- Deterministic verdicts — LEON values, `EVN_AIRPORT`/`SVX_AIRPORT`,
  tag rules, crew-count rules — never set `unknown_resolved`, so EVN/SVX
  rows render clean Yes/No with no badge (RSX121/RSX122 evidence).

The badge carries an accessible label and the tooltip shows the resolution
reason plus the message "Not found in LEON augmented data — resolved by local
rotation rule" (EN + AR). Additive; row layout and interactions unchanged.

## Decision 5 — One engine for every surface (owner rulings Q1–Q3, 2026-08-17)

The Copilot previously classified Heavy through a second engine
(`cabin_heavy.py`) with contradictory rules; a cross-consistency test proved
three divergences live. Owner rulings resolved every open question:

- **Cabin trainee = Work Schedule Function == "SFA"** — never Position-only
  (SFA the *position* is a normal senior cabin rank), never
  Position-AND-Function-TRN. LEON currently rejects the
  `workSchedule {{ function }}` selection, so the rule cannot fire; the report
  says so via `cabin_trainee_detection: "unavailable"` rather than implying
  exclusion happened. Follow-up: enable the Function field on LEON's side.
- **EVN/SVX are flight-level absolutes** — EVN vetoes a cockpit-count Yes on
  every surface.
- **No SP/OPS cabin exclusion** — removed with the old engine.
- **Rule-4 finalization** — a LEON-silent over-threshold count is final
  (`LOCAL_RULE`/`EXTRA_*`, no badge); STEP 4 runs only when the count rule
  returns UNKNOWN, exactly as rules 4/5 are written. (The service previously
  let the resolver override a count-derived Yes.)

`heavy.classify_flight_heavy` composes derive → decide → resolve as the one
flight-level verdict; `copilot/local_answers.py` builds its flight index from
the same MCP report rows (so STEP 4 genuinely runs there — the hardcoded
`is_unknown=False` dead end is gone) and maps engine reason codes to its
citation prose. `cabin_heavy.py` survives one release as a warning shim, then
is deleted. `backend/tests/test_heavy_cross_consistency.py` pins report ≡
Copilot on the five screenshot cases permanently.

## Decision 6 — Five corrections from the June 2026 UI review (owner rulings, 2026-08-19)

Every item here was diagnosed from live screenshots, ruled on by the owner, and
landed with a failing test first. Each one superseded a rule written above; the
superseded text is named so the two are never read as still coexisting.

### 6.1 — Airport codes are matched on BOTH code systems (D-1)

**Root cause (owner-accepted, 2026-08-19): neither surface could see the second
code form of an airport.** `_route_matches` compared route airports against the
literal `"SVX"`/`"EVN"`, while `crew_context._airport_code` prefers ICAO. An
ICAO-coded leg therefore contributed `USSS`/`UDYZ`, matched nothing, and read
Not Heavy — on the Crew Hours report **and** in the Copilot, identically.

An earlier framing of this defect said the Copilot facade was *structurally
blind* to the airport rule. That framing is **withdrawn and is not the record**:
`copilot.local_answers._context_index_from_report` already copied the report
row's `jl_adep/jl_ades_preferred_code` into the `FlightContext` it built, which
is why the IATA-coded `SVX` Copilot test passed before any change. There was one
root cause, not two, and it hit both surfaces the same way.

The fix, in two parts:

- `positions.AIRPORT_CODE_ALIASES` holds `SVX ↔ USSS` and `EVN ↔ UDYZ`.
  Matching is exact equality after trim+uppercase against **either** form —
  still never a substring, so `USSSX` and `UDYZA` do not match. Adding a third
  airport to an absolute rule means adding it to that one map.
- `classify_flight_heavy` grew a `route_airports` parameter and
  `merge_route_airports` unions it with the context's codes, each spelling kept
  as received. The report passes the row's preferred codes; the Copilot passes
  the same row fields. This removes the coupling that left the facade dependent
  on whatever the context happened to copy, even though that coupling was not
  itself the bug.

### 6.2 — Crew continuity, not role identity (D-2). Supersedes Decision 3's third bullet.

`rotation_crew_codes` → `crew_set_identity` drops every positioning slot, and
the STEP-4 comparison was a symmetric set equality. A member who flew out as FO
and rode home as PAD therefore vanished from one side only — which broke the
rotation not just for them but for **every** member of it (live case RSX6077
HRG→LIS 14:25–20:40 / RSX6078 LIS→HRG 21:50–03:35+1).

**The implemented rule, stated in full (owner-accepted 2026-08-19):** for each
leg, the comparison set is

> that leg's **operating crew** ∪ **everyone present on both legs in any
> capacity** ∪ **the subject member**.

Riders present on only ONE leg stay excluded — that part of Decision 3 was
correct (RSX6081/RSX6082).

Why not the ruling's literal wording: "the operating crew of both legs plus the
subject member on both legs" is not on its own sufficient. For subject C1 in case
B the two sides would still read `{C1,C2,C3}` against `{C1,C3}`, because the PAD
rider C2 is a *different* member and is still dropped, so C1 would still break.
The owner ruled the OUTCOME — YES on both legs for **every** member — and
confirmed on 2026-08-19 that the outcome governs and the set description was
imprecise. The rule above is what delivers it.

**Knock-on, deliberate — do not "fix" it:** a member riding **PSN** on the other
leg no longer breaks their colleagues' rotation either, for the same reason —
they are present on both legs, so their presence is continuous. `PSN` keeps its
immediate NO on the leg *being judged*, which is a different rule and unchanged.
Pinned by `test_psn_keeps_its_immediate_no`.

### 6.3 — Rotation continuity is a TRUE out-and-back. Supersedes Decision 3's first bullet.

`_rotation_chained` accepted a shared airport in *either* direction, so a chain
onward qualified: any same-direction pair with a stable roster and a break under
four hours was reported Heavy. That contradicts the original rule ("flew out and
came back") and was a live wrong-verdict class, not a theoretical one.
`_rotation_out_and_back` now requires `neighbour.departure == current.arrival`
**AND** `neighbour.arrival == current.departure`. The predicate is symmetric, so
it reads the same whether the neighbour precedes or follows the current leg, and
missing airport data still fails closed as `ROTATION_MISMATCH`.

Evidence: case C, RSX8891 HRG→SSH then RSX6083 SSH→OPO, break 0:50, identical
roster — every other gate passes and only this one produces the correct No.
Consequence recorded in the tests: the pre-existing case-4 pair (RSX6081 HRG→OPO
then RSX6084 OPO→SSH) now reports `ROTATION_MISMATCH` rather than
`BREAK_EXCEEDS_LIMIT`, because the rotation check runs before the break
arithmetic.

## Unchanged, deliberately

- Thresholds `cockpit > 2` / `cabin > 4` and the trainee sets.
- Official block-time totals: Heavy is a classification only.
- All existing public `FlightItem`/response field names (new fields are
  additive).
- UNKNOWN is never a final displayed verdict.

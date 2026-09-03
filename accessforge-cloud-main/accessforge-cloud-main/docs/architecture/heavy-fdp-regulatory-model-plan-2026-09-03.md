# Heavy from first principles: the FDP model — analysis and plan (2026-09-03)

Status: **SHADOW IMPLEMENTED 2026-09-03, awaiting owner rulings** (section 7). `backend/statistics/crew_hours/fdp.py` (pure, versioned tables `om-2009` default / `ecar-2016` via `CREW_HOURS_FDP_TABLES`) is wired into the report as `FlightItem.fdp_shadow` plus three `FDP_SHADOW_*` trace steps per leg; tests `backend/tests/test_crew_hours_fdp.py` (29). It changes no verdict, export cell, or credit, and nothing will until the
rulings land. Source documents: the owner's scan
`reference.pdf` (EgyptAir Operations Manual, Chapter 7 "Flight Time
Limitation", STD SEP.09, pages 7.1-2/3/4/10/11 + the printed Table A/B), and
the regulation it implements, ECAR Part 121 Subpart Q "The Avoidance of
Excessive Fatigue in Aircrew" (ECAA, 01-Jan-2016), which is itself the UK
CAP 371 scheme. Where the three differ it is called out.

## 1. What the document actually says

Definitions (OM 7.1-2, ECAR 121.501):

| Term | Rule |
|---|---|
| Flying Duty Period (FDP) | Any duty period in which the member flies as crew. Starts when the operator requires report, includes pre- and immediate post-flight duties. **Starts 1:30 before the scheduled departure of the first flight and ends 0:30 after the last landing** (OM 2-1-3, ECAR 121.503(d)). |
| Duty period | Continuous period of work: flying as crew **or as passenger**, positioning, ground training, standby. The owner's margin note reads "يقصد بها التشغيل" (means operating). |
| Positioning | Moving crew as passengers at the operator's order. **Counts as duty, never as a sector.** Positioning that immediately precedes an FDP is **part of that FDP** (ECAR 121.506). |
| Split duty | One FDP made of two or more parts separated by **less than a minimum rest period** (OM 7, handwritten "overday"). |
| Local night | 8 hours between 22:00 and 08:00 local. |
| Acclimatised | 3 consecutive local nights free of duty inside a 2-hour-wide time-zone band; stays acclimatised until a duty ends where local time differs by more than 2 hours (ECAR 121.503(b), OM 2-1-1). |

Maximum FDP for a two-pilot crew (OM 2-1, ECAR 121.503). Table A when the
FDP starts where the member is acclimatised, Table B otherwise:

| Table A: local start | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8+ |
|---|---|---|---|---|---|---|---|---|
| 06:00–07:59 | 13:00 | 12:15 | 11:30 | 10:45 | 10:00 | 9:15 | 9:00 | 9:00 |
| 08:00–14:59 (OM 2009) | 14:00 | 13:15 | 12:30 | 11:45 | 11:00 | 10:15 | 9:30 | 9:00 |
| 08:00–14:59 (ECAR 2016) | 14:00 | 13:15 | 11:45 | 11:15 | 10:45 | 10:15 | 9:45 | 9:30 |
| 15:00–21:59 | 13:00 | 12:15 | 11:30 | 10:45 | 10:00 | 9:15 | 9:00 | 9:00 |
| 22:00–05:59 | 11:00 | 10:15 | 9:30 | 9:00 | 9:00 | 9:00 | 9:00 | 9:00 |

| Table B: preceding rest | 1 | 2 | 3 | 4 | 5 | 6 | 7+ |
|---|---|---|---|---|---|---|---|
| Over 30 h (ECAR: "up to 18 or over 30") | 13:00 | 12:15 | 11:30 | 10:45 | 10:00 | 9:15 | 9:00 |
| 18–30 h | 12:00 | 11:15 | 10:30 | 9:45 | 9:00 | 9:00 | 9:00 |

(The OM scan prints 9¼ where ECAR prints 9:15; same value. The 08:00–14:59
row and the Table B row-1 label genuinely differ between the 2009 OM and the
2016 ECAR — see ruling R3.)

How the limit is **extended** — this is where "Heavy" comes from:

| Mechanism | Rule (ECAR 121.504 / 121.505, CAP 371 §12–13) |
|---|---|
| In-flight relief (augmented crew) | An additional, equally qualified crew member is carried. Total in-flight rest under 3 h counts for nothing. From 3 h: FDP may be extended by **½ of the rest taken in a bunk (cap 18 h; cabin 19 h)** or **⅓ of the rest taken in a seat (cap 15 h; cabin 16 h)**. Rest seat/bunk must be screened from flight deck and passengers. A relieved member wholly free for the rest of the flight is thereafter **positioning**. |
| Split duty | Ground rest under 3 h: no extension. 3–10 h: FDP extended by **½ the consecutive rest**. Rest excludes post/pre-flight duties; over 6 h needs a bed. |
| Commander's discretion | Further extension of the FDP actually worked (OM 2-6, ECAR 121.508; text not in the scan). |

Other limits that shape rosters: night flying ≤ 18 h in 72 h; minimum rest =
the longer of the preceding duty or 12 h (11 h away from base, ECAR 121.511);
900 flying hours per 12 months (OM 6-3). Cabin crew (OM 7, ECAR 121.516):
FDP may be **one hour longer** than the cockpit's and is measured from the
cockpit's report time; rest may be one hour shorter; **when augmentation is
used to extend the FDP, the required cabin crew is increased by 50% of the
minimum** (7-2-6 / 121.516(b)(6)); minimum cabin crew is one per 50 seats
(8-1(b)).

## 2. What "Heavy" is, once you read it this way

A rotation is Heavy when its **planned FDP exceeds the Table A/B maximum for
its start band and sector count**. The operator then has exactly two legal
ways to fly it, and both are what Red Sea pays H.C for:

1. **Augmentation** — carry a third pilot (in-flight relief). LEON records
   this as `crewAugmentation = true` on the operating cockpit (the CGN/OSL
   3-pilot sectors). Cabin crew rises by 50%.
2. **Crew swap** — carry two full crews; each member operates one leg and
   positions on the other. Each member's *own* FDP then ends 0:30 after the
   leg they operated, so it is legal without relief, while the *rotation* is
   still over the two-pilot limit. LEON does not mark this; the allowance
   model's rule (b) ("operate + ride under a 3 h link") is how the current
   code recognises it.

Every existing heuristic is a proxy for the one inequality
`FDP(rotation) > MaxFDP(start band, sectors, acclimatisation)`:

| Current rule | What it approximates |
|---|---|
| SVX always Heavy | SSH–SVX ≈ 5:20 out / 6:10 back; the rotation's FDP (≈ 14:45) is over every 2-sector limit |
| EVN never Heavy | SSH–EVN ≈ 2:55 / 3:20; FDP ≈ 9:25 is under even the night band's 10:15 |
| Domestic never Heavy | Sectors far too short to reach any limit |
| Sector minimum 4:00 | Two sectors over 4 h plus 1:30 + turnaround + 0:30 exceed 12:15 |
| Link break under 3:00 (swap) / 4:00 (duty) | "Separated by less than a minimum rest period" = one FDP |
| Cockpit count > 2 | Augmentation actually rostered (mechanism 1) |
| Cabin count > 4 | The 50% increase on a 4-attendant minimum (should be ≥ 6, see R6) |

## 3. Does the inequality reproduce the owner's rulings? Yes, on every case with times

Egypt local time = UTC+3 in these months (Egypt reinstated DST in 2023).
FDP = first STD − 1:30 → last STA + 0:30. Positioning before the operated
leg is inside the FDP but not a sector.

| Owner case (fixture) | Legs (UTC) | FDP | Band, sectors → limit | Result | Owner verdict |
|---|---|---|---|---|---|
| SVX 16-06 (RSX331/332) | SSH–SVX 17:15–22:35, back 23:50–06:00 | 14:45 | 18:45 local → 15:00–21:59, 2 → 12:15 | over by 2:30 → **Heavy** | Yes |
| CGN 10-07, LEON 3-pilot | HRG–CGN 17:05–22:15, back 23:40–04:40 | 13:35 | 18:35 → 12:15 | over by 1:20 → **Heavy** | Yes (LEON) |
| LIS 10-06, FO out / PAD back | 14:25–20:40, 21:50–03:35 | 15:10 | 15:55 → 12:15 | over → **Heavy**; the member's own FDP (1 operated sector) is 8:15 < 13:00, which is why the swap is legal | Yes (credit) |
| VKO 02-07, PAD out / CPT back | 14:25–19:50 (ride), 21:20–03:20 | 14:55 | 15:55 → **1 sector** (ride ≠ sector) → 13:00 | over → **Heavy** | Yes (credit) |
| ALA 28/29-07 | 19:05–00:55, ride 02:10–08:45 | 15:40 | 20:35 → 12:15 | over → **Heavy** | Yes (credit) |
| LED 31-07 | 17:20–22:45, ride 23:50–05:20 | 14:00 | 18:50 → 12:15 | over → **Heavy** | Yes (credit, painted on both months) |
| EVN 01-07 | SSH–EVN 23:05–02:00, back 03:10–06:30 | 9:25 | 00:35 → 22:00–05:59, 2 → 10:15 | under by 0:50 → **No** | No |
| KRR 11-07 | 09:40–12:50, 15:00–18:20 | 10:40 | 11:10 → 08:00–14:59, 2 → 13:15 | under → **No** | No |
| OPO 23-06, shuttle + out only | HRG–SSH 05:30–06:10, SSH–OPO 07:00–13:00 | 9:30 | 07:00 → 06:00–07:59, 2 → 12:15 | under → **No** | No |
| OPO 23-06 with the return | + OPO–SSH 14:15–20:00 | 16:30 | 3 sectors → 11:30 | over by 5:00 → **Heavy** | Yes |

Ten for ten, with no airport special-casing, no sector minimum, and no
3-hour link constant. The airport rules and the allowance heuristics were
correct *because* they track this inequality on the routes Red Sea flies.

## 4. Where the model and the current code would disagree

These are real differences, each needing an owner ruling before any code changes a verdict.

1. **"Same duty" width.** Code: break < 4:00 (duty) / < 3:00 (swap link). Regulation: parts separated by less than *minimum rest* (12 h, 11 h away) are one FDP, extended by ½ the ground rest when that rest is 3–10 h. A 5-hour outstation turnaround is one split-duty FDP by the book and two duties by the code.
2. **Start-band dependence.** A 2-sector rotation starting 08:00–14:59 local is allowed 13:15. An SVX rotation planned at 13:10 would be legal two-pilot by the book; the owner's SVX absolute says Heavy regardless. The model should *show* this, not overrule the policy.
3. **Table version.** The 2009 OM and the 2016 ECAR differ in the 08:00–14:59 row (3–8 sectors) and in Table B's first row label. Red Sea's own approved OM/OpSpec governs; the tables must be data, not code.
4. **Acclimatisation needs history.** Table B applies when the duty starts where the member is not acclimatised (an SVX/LED layover start after < 3 local nights). It needs the previous duty's end place and time and the preceding rest length — data the report does not carry today.
5. **Positioning inside the FDP.** A PAD ride *before* the operated leg extends the member's FDP (VKO case) but is not a sector; a ride *after* is duty, not FDP. The allowance rule treats both rides symmetrically; the book does not.
6. **Cabin threshold.** `cabin_count > 4` flags a 5-attendant cabin as augmented. By 7-2-6 an augmented cabin is the minimum plus 50%: 4 → 6. Five may be a supernumerary/trainer, not augmentation. Conversely cabin FDP is one hour longer, so cabin "needs Heavy" one hour later than the cockpit.
7. **Time zone.** Bands are in the *local time of the acclimatised place*; Egypt is UTC+3 in summer and UTC+2 in winter since 2023. The 07:59/08:00 and 21:59/22:00 edges move the limit by up to one hour, and a duty that starts at an outstation uses that station's clock only if the member is acclimatised there.

## 5. Proposed design

Pure module `backend/statistics/crew_hours/fdp.py` (no I/O, no service
imports — the same discipline as `heavy.py`, `unknown_resolver.py`,
`allowance.py`):

```
FdpTables            versioned data: table_a[band][sectors], table_b[rest_band][sectors],
                     cabin_extra = 1:00, report_before = 1:30, post_flight = 0:30,
                     relief (bunk ½ cap 18, seat ⅓ cap 15), split (3–10 h → ½)
build_fdp(legs, member, rides_before, local_tz)      -> Fdp(start, end, sectors, band, planned)
acclimatisation(history)                              -> "A" | ("B", rest_hours) | "unknown"
max_fdp(tables, fdp, acclimatisation, crew_type)     -> limit, with the row/column it used
regulatory_heavy(fdp, limit)                          -> RegulatoryVerdict(needs_augmentation, margin,
                                                        trace steps in the existing heavy_trace format)
```

Integration, in this order:

1. **Shadow mode.** Add `regulatory_heavy`, `fdp_planned`, `fdp_limit`,
   `fdp_margin` to every leg and duty as *additional* fields and trace steps.
   Nothing that exists today changes value. The UI shows the margin in the
   decision-trace disclosure only.
2. **Back-test.** Run June and July: compare `regulatory_heavy` against LEON
   `crewAugmentation`, the current engine's verdict, and the manual sheets
   (`refrance_output/`, `Stactstics hany/`). Produce the disagreement list
   with the trace for each. This is the evidence the rulings in section 7
   need.
3. **Owner rulings** (section 7), recorded in `closed-questions.md` and the
   Heavy ADR as Decision 7.
4. **Promotion**, only as ruled: candidates are (a) replace the 4:00 sector
   minimum and 3:00 link with the FDP inequality plus the split-duty rule,
   (b) keep EVN/SVX/domestic as *documented policy overrides* that the trace
   reports as "policy, agrees/disagrees with the FDP model", (c) a cabin
   threshold derived from the 50% rule per aircraft type, (d) a compliance
   view: legs whose FDP exceeds the two-pilot limit with no augmentation and
   no swap recorded — the book says those should not have flown as rostered.
5. **Data:** add `previous_duty_end_at/place` and `rest_before` to the crew
   context (LEON duty history), an airport → time zone table with Egypt DST
   rules, and per-aircraft minimum cabin crew (`positions.minimum_required_cabin`
   already exists).

Tests (golden, failing-first): the ten cases above as a table-driven suite;
band edges 07:59/08:00, 14:59/15:00, 21:59/22:00, 05:59/06:00 in UTC+2 and
UTC+3; sector counting with a positioning ride before/after; split-duty
extension at 2:59, 3:00, 10:00, 10:01; relief extension with bunk vs seat
and the 18/15 h caps; cabin +1 h; Table B selection from history; both table
versions selectable, with the 2009/2016 differing cells asserted.

Effort: module + tests ≈ 2 days; shadow fields + trace ≈ 1 day; back-test
report ≈ 1 day; promotion depends on rulings.

## 6. What this does NOT change

The H.C allowance stays **per member-duty, one credit per duty**, counted in
the month the duty departed. Block-time totals are untouched. LEON's own
`crewAugmentation` stays authoritative where present. The red badge keeps
its meaning. All of that is orthogonal to *why* a rotation is Heavy.

## 7. Rulings needed from the owner

R1. Which tables govern Red Sea: the 2009 OM values in the scan, ECAR 2016, or Red Sea's own approved OM (please provide its Chapter 7)?
R2. Same duty = break under 4:00 (today) or "less than minimum rest" with the split-duty extension (the book)?
R3. Keep SVX/EVN/domestic as policy absolutes even where the FDP model disagrees? (Recommended: yes, but show the disagreement in the trace.)
R4. Cabin augmentation = `cabin_count >= minimum × 1.5` per aircraft type, or the current `> 4`?
R5. Does a positioning ride *before* the operated leg extend the member's FDP for the allowance (the book says yes; the CGN/VKO sheets suggest yes)?
R6. Is the compliance view (over-limit legs with no augmentation/swap) wanted, and who receives it?
R7. The scan is missing OM pages 7.1-5 to 7.1-9 (sections 2-2 augmentation, 2-3 split duty, 2-6 commander's discretion, 3 rest, 4 standby, 5–6 cumulative limits). Please scan them; ECAR 2016 was used to fill the gap and R1 decides whether that is acceptable.

Sources: the owner's `reference.pdf`; [ECAR Part 121 Subpart Q (2016)](https://crewscheduling.wordpress.com/wp-content/uploads/2015/03/ecar-121-subpart-q-2016.pdf); [UK CAA CAP 371, 4th edition](https://understandingeasa2016ftl.wordpress.com/wp-content/uploads/2016/06/cap371_20041.pdf).


## 8. Verification against LEON's own FTL engine (2026-09-03, June 2026)

`ftl.dutyList` exposes what LEON computed per member-duty: `fdpStartTime`,
`fdpEndTime`, `fdpLength`, `maxFdpLength`, `fdpExtension`, `splitDutyTime`,
`discretionLength`, `sectorCount`, `isAcclimated`, `localTimeOffset`,
`lastAcclimatisationOffset`, `restFacility`, `crewAugmentation`,
`isCabinCrew`, and per sector `reportingTime`. Tool:
`backend/statistics/crew_hours/tools/fdp_leon_compare.py`; results outside
the repo in `E:\work\REDSEA\web\Heavy_FDP_Report\leon_compare\`.

| Check (1,562 flown member-duties) | Result |
|---|---|
| Our Table A limit == LEON `maxFdpLength` (cockpit, no extension) | **524 / 547 (96%)**; the 23 others are split duty (+½ ground rest, e.g. 3:20 → 14:55), commander's discretion (+2:00 → 13:30), augmentation cap (15:00), or a band taken in another acclimatisation zone (Lisbon +1 after LPPT) |
| Table version LEON is configured with | **OM 2009 values** (12:30 for 3 sectors in 08:00–14:59, not ECAR's 11:45) → answers R1 |
| Cabin limit | cockpit + 1:00, confirmed (14:00, 12:00, 14:15, 11:15) |
| Augmented maximum, rest facility SEAT | 15:00 cockpit / 16:00 cabin (1,321 duties SEAT, 8 BUNK, 233 NONE) |
| FDP start vs first block-off | **not a constant**: 1:30 (272), 1:25 (185), 1:40 (155), 1:35, 1:20, 1:15 … per station/flight (HECA 2:25, LPPT 2:20, LPPR 2:00); FDP start == first sector `reportingTime` in 1,553/1,562 |
| FDP end vs last block-on | **0:00** — Red Sea's configuration ends the FDP at on-blocks; the OM's 0:30 is not added |
| Acclimatisation | `isAcclimated` True for all 1,562; Table B unused in June |
| `crewAugmentation` | NORMAL 783, AUGMENTED 39, DOUBLED 740 (cabin double complement on the Moscow/St Petersburg legs) |
| Our inequality vs LEON flag | agree 824; ours-No/LEON-Yes 730 (600 = cabin DOUBLED single-sector duties, FDP 7:00–8:00; 4 = cockpit ENGM augmented at 12:45 < 13:15 — augmentation is a planning decision with margin); ours-Yes/LEON-No 8 (all split duty or discretion, legal in LEON) |

Consequences for the design:

1. **LEON's FTL values are the primary source** for regulatory Heavy: the
   `crewAugmentation` flag (already used) plus `fdpLength`/`maxFdpLength`
   for the margin. They embody Red Sea's approved configuration, including
   per-flight report times, the on-blocks FDP end, split duty, discretion,
   and acclimatisation zones that a local recomputation cannot know.
2. **The local model becomes a validator/fallback**, fed with LEON's inputs
   (first-sector `reportingTime` instead of 1:30; post-flight 0:00 under this
   configuration; band from `lastAcclimatisationOffset`), and raises a
   disagreement instead of overriding. With these two corrections the EVN
   night pair of 02/03-06 measures 10:15 exactly, not 10:45 — inside the
   limit, agreeing with the owner's rule.
3. **The allowance is a policy layer** over both: who is paid (cockpit,
   cabin), the unit (rotation vs duty — a cabin member on a doubled Moscow
   flight has one duty per leg while the cockpit has one rotation), and the
   documented exceptions (SVX, EVN, domestic). Cabin DOUBLED legs are genuine
   augmentation in LEON's data, not an artefact; whether they earn one credit
   per leg is ruling R8.

New rulings from this section: **R1 is answered by the data (OM 2009)**;
**R9** — adopt LEON FTL fields as the primary regulatory source and demote
the fixed 1:30/0:30 constants to a fallback (recommended).

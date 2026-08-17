# Development Decision Log

## 2026-08-18 — Join key CONFIRMED live; docs corrected to match

- **`unique_id == flightNid == trNid` is settled, not open.** `id_probe.py`
  was run against live LEON for days 2026-06-16 / -20 / -22 in an earlier
  session: all three endpoints returned the same identifier (RSX331 =
  `67230742` across Report Wizard, flight list, and FTL), airports came back
  ICAO (HESH→USSS). A live June 2026 report then showed `join_health: OK`,
  `augmented_lookup_hits 1892/2493`, `crew_context_hits 2107/2493`. The only
  in-repo record of this was the `_row_flight_nid` docstring in
  `backend/copilot/local_answers.py`; the ADR (Decision 4) and the 2026-08-17
  entry below still said UNVERIFIED — both are corrected as of this entry.
  Do not re-run the probe or re-decide the key; the hit-rate instrumentation
  remains as a regression tripwire only.
- **The `workSchedule { function }` gap is documented, not unverified.** LEON
  *rejects* the selection (live 2026-06 run) — that rejection is the reason
  the cabin-trainee rule (Function == "SFA", the Q1 ruling) does not fire in
  production. Surfaced as `cabin_trainee_detection: "unavailable"` in report
  metadata (pinned by tests in `test_crew_hours_heavy.py`). Follow-up stays
  open on LEON's side: enable the Function field.

## 2026-08-17 — Owner rulings: one Heavy engine, trainee definition, consolidation

- **Q1 ruling — cabin trainee = Work Schedule Function == "SFA"** (the
  `heavy.py` reading). NO Position-only fallback: SFA as a *position* is a
  normal senior cabin rank; a Position-only rule would exclude operating crew.
  **Known gap**: LEON currently rejects the `workSchedule { function }`
  selection (live 2026-06 run: *"LEON rejected the crew Work Schedule Function
  selection; cabin trainee detection is disabled for this report"*), so the
  rule does not fire in production. The report now surfaces this as
  `cabin_trainee_detection: "unavailable"` in the response metadata so nobody
  assumes trainees were excluded. **Follow-up open**: get the Function field
  enabled on LEON's side.
- **Q2 ruling — EVN/SVX are FLIGHT-LEVEL absolutes.** EVN vetoes even a
  cockpit-count Yes. The Copilot's "cockpit stays frozen, overrides are
  cabin-only" behavior was wrong and is retired (its pinned test inverted).
- **Q3 ruling — the `{"SP","OPS"}` cabin exclusion is removed.** OPS/SP are
  cockpit trainee slots; no approved cabin rule used them. Pinned by
  `test_no_sp_ops_cabin_exclusion_exists`.
- **Consolidation executed**: `heavy.classify_flight_heavy` is the single
  flight-level engine; `copilot/local_answers.py` builds a flight index from
  the same MCP report rows and calls it (STEP 4 now genuinely runs on the
  Copilot path — the `is_unknown=False` dead end is gone). `cabin_heavy.py`
  is a one-release deprecation shim (warns, delegates to the engine), then
  deleted; its rule tests migrated to the heavy/resolver suites, its citation
  formats to the copilot suite. `test_heavy_cross_consistency.py` is now a
  committed, permanently-green gate over the five screenshot cases.
- **Discovered and resolved during consolidation — rule-4 finalization**: the
  service allowed STEP 4 to override a count-derived Yes when LEON was silent,
  contradicting written rule 4 ("count over threshold → YES") and rule 5
  (resolver runs only on the count rule's UNKNOWN). Both surfaces now finalize
  a LEON-silent count-Yes as `LOCAL_RULE`/`EXTRA_*` with no resolver badge;
  `decide_heavy`'s pinned pure-function table is untouched. A LEON-silent,
  over-complement flight that a non-qualifying rotation previously flipped to
  No now reads Yes — that is the written rule.

## 2026-08-17 — Heavy pipeline: live UI review corrections (screenshot evidence)

- **EVN/SVX are airport-based rules; tags kept as secondary signal.** LEON
  does not tag these flights — SVX/EVN appear in ADEP/ADES. A flight is
  SVX/EVN when either route airport equals the code (exact match after
  trim+uppercase, from the report row `jl_adep/jl_ades_preferred_code` OR the
  flight-list context; either source counts) or the legacy tag is present.
  New reasons `SVX_AIRPORT`/`EVN_AIRPORT`; existing `*_TAG` literals kept.
  Evidence: RSX331/RSX332 SSH↔SVX 16-06 (both now Yes deterministically —
  RSX332 previously read No), RSX121/RSX122 SSH↔EVN 20/21-06 (both No by
  rule, badge-free). Precedence unchanged: EVN → No absolute, SVX → Yes
  absolute, EVN wins if both.
- **Badge semantics tightened.** The red exclamation means only "absent from
  LEON augmented data, decided by the local rotation rule". Every leg that
  enters STEP 4 gets `unknown_resolved=True` + `heavy_source=LOCAL_RULE`
  regardless of Yes/No — so BOTH legs of a resolver-decided rotation carry
  the badge (RSX6081/RSX6084 22/23-06). Airport/tag/count-decided rows never
  set it (RSX121/RSX122 badges removed).
- **Operating-crew comparison excludes all positioning/non-operating slots**
  (`PSN`, `PAD`, `OBS`, `OBS2`, `STB`), not just PSN. Evidence:
  RSX6081/RSX6082 HRG↔OPO 22-06 — a cockpit PAD rider on the outbound leg
  broke the crew-set match and wrongly forced No on both legs; now both Yes
  via SAME_DAY_SHORT_BREAK_SAME_CREW, symmetrically. PSN/PAD are also
  excluded from operating cockpit/cabin counts; block-time inclusion for PAD
  is untouched. PAD is NOT short-circuited like PSN — a PAD member's row
  follows the flight-level rules.
- **INTENTIONAL BEHAVIORAL CHANGE — PAD/PSN removed from the operating
  counts** (`operating_cockpit_count` / `operating_cabin_count` in
  `backend/statistics/crew_hours/heavy.py`). Before this change a PAD rider
  counted as operating crew and could tip a flight over the `cockpit > 2` /
  `cabin > 4` threshold: RSX6081 HRG→OPO 22-06 carried CPT+FO+PAD and would
  have read `EXTRA_COCKPIT_CREW` (Yes) from the rider alone. Any flight whose
  Heavy verdict flips Yes→No after this date, where the old Yes came from a
  PAD/PSN slot inflating the count, traces to this decision. Thresholds and
  the trainee sets are unchanged; PAD block-time inclusion in numeric totals
  is unchanged. Pinned by
  `test_crew_hours_heavy.py::TestAirportBasedAbsoluteRules::test_positioning_members_never_count_as_operating_crew`.
- The midnight rollover in RSX6082 (ends 03:50 next UTC day, starts 22:00
  same date) passes the duty-window logic unchanged — confirmed by test, no
  code change needed for that suspect.

## 2026-08-17 — Crew Hours Heavy pipeline corrections

- **Absolute tags above LEON.** `decide_heavy` evaluates `EVN_TAG`/`SVX_TAG`
  before the LEON `crewAugmentation` value. EVN forces No, SVX forces Yes; a
  disagreeing LEON value sets `heavy_conflict=True` with
  `heavy_source="LOCAL_RULE"` and logs a warning. Without a tag the LEON-first
  table is unchanged. (Previously the LEON value silently overrode the tags.)
- **STEP 4 break boundary.** `break >= 4h` rejects: 3:59 connects, exactly
  4:00 does not, matching the 2026-08-09 parity invariant `0 <= break < 4h`.
  The old `>` comparison wrongly let 4:00 pass.
- **Midnight-safe duty window.** STEP 4 no longer compares calendar UTC dates.
  A pair passing the break gate is one duty anchored on the first sector's UTC
  start date, rollover included. `DIFFERENT_DAY` is reserved for genuinely
  disjoint days: a different UTC date AND more than 24h start-to-start.
  A failed break inside the window (incl. 4:00 across midnight) reports
  `BREAK_EXCEEDS_LIMIT`.
- **Rotation continuity required.** A qualifying neighbour must chain airports
  with the current leg; `FlightContext` now carries departure/arrival codes
  (ICAO preferred, IATA fallback) parsed from the flight list. Missing airport
  data fails closed as `ROTATION_MISMATCH`.
- **PSN semantics in STEP 4.** A member positioned `PSN` on the leg is No
  immediately (`PSN_POSITIONING`, no neighbour search), and the same-crew
  comparison excludes PSN members on both legs so a positioning passenger on
  the return leg cannot break the match.
- **Join health instrumented, not assumed.** The Report-Wizard `unique_id` ↔
  FTL `trNid` ↔ flight-list `flightNid` equivalence remains UNVERIFIED (column
  ADR: AMBIGUOUS). *[Superseded — confirmed live; see the 2026-08-18 entry.]*
  Each report run exposes
  `augmented_lookup_hits/attempts` and `crew_context_hits/attempts` plus
  `join_health` ("DEGRADED" below a 50% hit rate against a non-empty index,
  with a warning log). `backend/statistics/crew_hours/tools/id_probe.py`
  prints all six candidate identifiers side by side for one live day so the
  operator can confirm the key once. No remapping was guessed in code.
- **UI provenance.** Locally-resolved rows (`heavy_source=LOCAL_RULE` +
  `unknown_resolved`) show a red exclamation badge with the reason and the
  localized message "Not found in LEON augmented data — resolved by local
  rotation rule" (EN + AR). Additive only; layout unchanged.
- **Unchanged by design:** thresholds (`cockpit > 2`, `cabin > 4`), trainee
  sets, official block-time totals, all existing response field names, and the
  rule that UNKNOWN is never a displayed verdict.

Full rationale: `docs/architecture/crew-hours-heavy-precedence-adr-2026-08-17.md`.

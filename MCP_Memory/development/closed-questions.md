# Closed Questions — settled with evidence; do NOT re-open or re-derive

Each item below was decided with live evidence or an explicit owner ruling.
Re-deciding any of them without new owner input or new live evidence is a
regression. Rationale: `accessforge-cloud-main/accessforge-cloud-main/docs/architecture/crew-hours-heavy-precedence-adr-2026-08-17.md`.

## Crew Hours (Heavy)

1. **Join key: `unique_id == flightNid == trNid`.** CONFIRMED live via
   `backend/statistics/crew_hours/tools/id_probe.py` on days 2026-06-16/-20/-22
   (RSX331 = 67230742 on all three endpoints; ICAO airports, HESH→USSS). Live
   June 2026 report: `join_health: OK`, augmented 1892/2493, crew_context
   2107/2493. The hit-rate instrumentation is a regression tripwire, not an
   open question. Do not re-run the probe.

2. **LEON rejects `workSchedule { function }`.** A known, documented gap — not
   an unverified guess (live 2026-06 run returned an explicit rejection). It is
   the reason the cabin-trainee rule does not fire in production. Surfaced as
   `cabin_trainee_detection: "unavailable"` in report metadata, pinned by
   tests. The follow-up (enable the Function field) is on LEON's side.

3. **EVN/SVX are AIRPORT-code rules, flight-level absolutes.** Matched against
   ADEP/ADES (exact match after trim+uppercase; report row
   `jl_adep/jl_ades_preferred_code` OR flight-list context); legacy flight tags
   kept only as a secondary signal — no flight in June 2026 carried one.
   EVN → No absolute (vetoes even a count Yes), SVX → Yes absolute, EVN wins if
   both. Evidence: RSX331/RSX332 SSH↔SVX 16-06 both Yes; RSX121/RSX122 SSH↔EVN
   20/21-06 both No, badge-free.

4. **Cabin trainee = Work Schedule Function == "SFA" ONLY.** Owner ruling
   (Q1, 2026-08-17). Never Position-only — SFA as a *position* is a normal
   senior cabin rank; a Position rule would exclude operating crew.

5. **The `{"SP","OPS"}` cabin exclusion is REMOVED.** Owner ruling (Q3):
   OPS/SP are cockpit trainee slots; no approved cabin rule ever used them.
   Pinned by `test_no_sp_ops_cabin_exclusion_exists`.

6. **PAD/PSN (and OBS/OBS2/STB) never count as operating crew.** Excluded from
   the operating cockpit/cabin counts and from STEP 4's same-crew comparison
   on both legs. PSN is short-circuited to No (`PSN_POSITIONING`); PAD is not —
   a PAD rider's row follows the flight-level rules. Block-time inclusion for
   PAD is untouched. Evidence: RSX6081/RSX6082 HRG↔OPO 22-06 (a cockpit PAD
   rider wrongly broke the crew-set match and inflated the count).

7. **STEP 4 break gate is strict: `break >= 4h` rejects.** 3:59 connects,
   exactly 4:00 does not (parity invariant `0 <= break < 4h`). The duty window
   is midnight-safe — anchored on the first sector's UTC start date, rollover
   included; `DIFFERENT_DAY` requires a different UTC date AND >24h
   start-to-start.

8. **Badge semantics.** The red exclamation means exactly one thing: "absent
   from LEON augmented data, decided by the local rotation rule". Every leg
   that enters STEP 4 gets `unknown_resolved=True` + `heavy_source=LOCAL_RULE`
   regardless of Yes/No (both legs of a resolved rotation carry it);
   airport/tag/count-decided rows never do.

Also settled (context, same ADR): thresholds are the operator standard
complement — cockpit > 2, cabin > 4, derived from June 2026 data (304
flights: standard 2+4) — re-derive from data if the fleet or cabin policy
changes, never restore old numbers; UNKNOWN is never a displayed verdict;
STEP 4 can never override a count-derived Yes.

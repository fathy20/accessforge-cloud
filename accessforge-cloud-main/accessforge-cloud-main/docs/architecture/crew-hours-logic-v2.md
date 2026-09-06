# Crew Hours — LOGIC v2 (locked 2026-09-03)

**What this file is.** The complete, owner-validated logic the Crew Hours
module runs on today, written down as a single source so it can be restored
exactly if the work that follows it does not pan out.

**Why it exists.** The next slice re-derives Heavy from the regulation (the
owner's `reference.pdf` → the FDP model). That work runs in *shadow* and is
allowed to fail. If it does, or if the owner rejects it, **this document is
the state to return to** — no reconstruction from memory, no guessing.

**Git anchor:** `b47172d` on `fix/crew-hours-heavy-airport-rules`.
Everything below is live at that commit. The FDP work added on top of it
changes nothing described here.

---

## 0. The three layers, deliberately separate

Unifying any two of them silently changes displayed numbers or verdicts.

| Layer | Question it answers | Where it lives |
|---|---|---|
| **Heavy verdict** (per leg) | Was this leg flown with an augmented crew? | `heavy.py`, `unknown_resolver.py` |
| **H.C allowance** (per member-duty) | Does this member earn a Heavy credit for this duty? | `allowance.py` |
| **Block-time totals** | How many hours did this member fly? | LEON official totals, untouched |

The allowance is **not** a sum of leg verdicts. A member can have a No leg
inside a credited duty (the 23-06 domestic shuttle) and a Yes leg in an
uncredited one. That is intended.

---

## 1. Heavy verdict — precedence, evaluated in order

One engine for every surface (report + Copilot):
`heavy.py::classify_flight_heavy`. Output is always Yes/No, never Unknown,
except when the whole FTL index is unavailable.

1. **Trainees excluded first.** Cockpit trainees by role slot (`OPS`, `SP`);
   cabin trainees by Work Schedule Function `== "SFA"` only, never by
   Position. LEON currently rejects the `workSchedule { function }`
   selection, so cabin trainee detection is **off in production** and the
   report says so via `cabin_trainee_detection: "unavailable"`.

2. **Airport absolutes.** `EVN` → **never Heavy** (vetoes everything below,
   and beats SVX). `SVX` → **always Heavy**. Matched on ADEP/ADES, exact
   equality after trim+uppercase, never substring. **Both code systems
   count**: `SVX ↔ USSS`, `EVN ↔ UDYZ` (`positions.AIRPORT_CODE_ALIASES`).
   The report row's preferred codes and the flight-list context's codes are
   **unioned**; a match on either counts. Legacy flight tags are a secondary
   signal only (no June 2026 flight carried one).

3. **Domestic sector** (both ends Egyptian) → No by local rule. Deliberately
   *not* an absolute: an explicit LEON `crewAugmentation` value overrides it.

4. **LEON's `crewAugmentation`**, when present. If it disagrees with an
   airport absolute, the absolute wins, the row carries `heavy_conflict=True`
   and `heavy_source="LOCAL_RULE"`, and a warning is logged.

5. **Operating-crew counts.** `cockpit_count > 2` or `cabin_count > 4` → Yes
   (`EXTRA_COCKPIT_CREW` / `EXTRA_CABIN_CREW`). Positioning slots (`PSN`,
   `PAD`, `OBS`, `OBS2`, `STB`) never count as operating crew. **A
   LEON-silent count-Yes is final** — it never falls through to step 6.

6. **STEP 4 rotation resolver** — only when LEON is silent *and* the count
   rule is UNKNOWN:
   - **True out-and-back required**: `neighbour.departure == current.arrival`
     AND `neighbour.arrival == current.departure`. A chain onward is not a
     rotation. Missing airport data fails closed (`ROTATION_MISMATCH`).
   - **Break < 4h strict** (exactly 4:00 rejects), midnight-safe, anchored on
     the first sector's UTC start date.
   - **Crew CONTINUITY, not role identity.** Each leg's comparison set is:
     that leg's operating crew ∪ everyone present on BOTH legs in any
     capacity ∪ the subject member. Riders present on only one leg stay
     excluded. *Knock-on, deliberate:* a member riding PSN on the other leg
     no longer breaks their colleagues' rotation. Do not "fix" this.
   - **Pairing direction**: backward neighbour always searched; forward only
     when nothing connected precedes this leg.
   - A member positioned `PSN` **on the leg being judged** is No immediately
     (`PSN_POSITIONING`).
   - **The badge means the resolver established Heavy = True.** A resolver No
     is "no qualifying rotation found" — absence of evidence — and carries no
     badge. `unknown_resolution_reason` is still recorded either way.

7. **Every leg carries a `heavy_trace`**: the ordered rules evaluated, each
   with its outcome and the inputs it saw (airports in every form received,
   times as received, counts with thresholds, the two crew sets compared).

### Invariants (do not change without an owner ruling)

- Thresholds cockpit `> 2` / cabin `> 4`. **Never** restore the older
  inverted pair (cockpit > 4 / cabin > 2).
- UNKNOWN is never displayed. PAD block-time inclusion in numeric totals is
  unchanged by all of the above. Official block-time totals are untouched.
- `heavy.py`, `unknown_resolver.py`, `trace.py` stay pure: no I/O, no service
  imports. `derive_heavy_detail` delegates to `derive_heavy_detail_traced`,
  so a traced verdict and an untraced one cannot diverge.

### Two crew-set concepts, deliberately different

| Concept | Excludes | Governs |
|---|---|---|
| `CrewSlot.counts_in_totals` | PSN only | per-member numeric block-time totals |
| `positions.crew_set_identity` | PSN, PAD, OBS, OBS2, STB | duty grouping + STEP-4 comparison |
| frontend `UI_POSITION_FILTER_TOKENS` | — | **display filter only**; never align it with the backend count rule |

---

## 2. H.C allowance — per member, per duty

**`H.C(member) = the number of that member's DUTIES that earn a credit.`**

Validated 2026-08-20 against the manual "Cockpit July Crew Allowance"
workbook: **54 of 55** named cockpit members matched (the exception is a
suspected omission in the sheet itself). Extended 2026-09-02 by owner ruling.

- **Duty** = a maximal run of the member's own legs joined by breaks strictly
  under 4h. Calendar dates gate nothing: 21:50 → 03:35(+1) is one duty. A
  duty belongs to the UTC date of its **first** leg (the anchor).
- The duty **earns** on its own merits; the credit is **counted** only when
  the anchor falls inside the requested window. A rotation straddling a month
  end paints both legs Heavy on their respective sheets and is paid **once**,
  in the month it departed.
- **Credit sources:**
  - `LEON_AUGMENTED` — LEON `crewAugmentation` True on ≥1 leg the member
    **operated**. Authoritative; the gates below never re-judge it.
  - `OPERATE_PLUS_RIDE` — the member operated an **international** sector
    **longer than 4:00**, paired with **any other real leg of the duty**
    (a PAD ride; a PSN chained by a break under 3:00; or another operated
    leg) under a **3:00** link break.
- **Domestic sectors** (both ends Egyptian) never qualify, never accumulate
  toward the minimum, and are painted No even inside a credited swap duty.
- **`OBS`, `OBS2`, `STB`, `SP`, `OPS`, `FAOBS` are neutral**: never operate,
  never ride.
- **EVN sectors** contribute nothing in either role.
- **An SVX sector is not a credit source by itself** — adding it over-counted
  July (50/54 vs 52/54). SVX rotations are crew-swap duties, so the swap rule
  already credits the members who actually augmented.

Constants: `BREAK_LIMIT 4:00` · `SECTOR_MINIMUM 4:00` (strictly greater) ·
`SWAP_LINK_BREAK 3:00` · `PSN_CHAIN_BREAK 3:00`.

---

## 3. Data joins and health

Report Wizard rows join the FTL index and flight-list index on
`unique_id == flightNid == trNid` — confirmed live (id_probe 2026-06-16/20/22,
RSX331 = 67230742 on all three endpoints). Every run reports
`augmented_lookup_hits/attempts`, `crew_context_hits/attempts` and
`join_health` ("DEGRADED" below a 50% hit rate against a non-empty index) as
a regression tripwire. June 2026 live: `join_health: OK`, augmented
1886/2480, crew_context 2094/2480.

---

## 4. Export

The XLSX is pinned to the hand-made month sheet: no Maintenance sheet, Heavy
on both tabs, totals written as values not formulas.

---

## 5. What is SHADOW and must never affect any of the above

`fdp.py` + `FlightItem.fdp_shadow` + the `FDP_SHADOW_*` trace steps compute
the regulatory FDP assessment of each duty. They are **display and
diagnostics only**. If any of them ever changes `effective_heavy`,
`duty_credit`, `heavy_credits`, or an export cell, that is a bug.

The two read-only tools that produced the evidence:
`tools/fdp_backtest.py` (shadow vs displayed verdict, June/July) and
`tools/fdp_leon_compare.py` (our tables vs LEON's own FTL engine).

---

## 6. How to restore this state

The FDP work sits in three commits on top of the anchor:

```
b47172d  fdp_leon_compare tool + LEON verification
62e8ca3  fdp_backtest tool + June/July results
38dee99  regulatory FDP model in shadow mode + plan
```

To return to the pre-PDF logic:

```bash
git revert --no-commit b47172d 62e8ca3 38dee99 && git commit -m "revert(crew-hours): drop the shadow FDP model, return to LOGIC v2"
```

Nothing else has to be undone: no migration, no schema change to the crew
tables, no verdict or credit was ever routed through the shadow model.

**Verification after restoring:** the backend suite must pass (723 at the
anchor, 694 before the FDP tests existed), and `test_crew_hours_allowance.py`,
`test_crew_hours_heavy_rules.py`, `test_heavy_cross_consistency.py` must all
be green — those are the tests that pin sections 1 and 2 of this document.

---

## 7. Tests that pin this logic

| Rule | Test |
|---|---|
| Heavy precedence, airport aliases, D-1/D-2 rulings | `test_crew_hours_heavy_rules.py` |
| Engine parity across report and Copilot | `test_heavy_cross_consistency.py` |
| Allowance model, month-straddling, the owner cases | `test_crew_hours_allowance.py` |
| Deprecated cabin_heavy wrappers still warn and delegate | `test_cabin_heavy_deprecated.py` |
| Export shape pinned to the manual sheet | `test_crew_hours_export.py` |
| No `{"SP","OPS"}` cabin exclusion exists | `test_no_sp_ops_cabin_exclusion_exists` |
| PSN keeps its immediate No, colleague stays Yes | `test_psn_keeps_its_immediate_no` |

---

## 8. Authorities

- Precedence rationale: `crew-hours-heavy-precedence-adr-2026-08-17.md`
- Settled disputes (do not re-open): `MCP_Memory/development/closed-questions.md`
- Business summary: `MCP_Memory/business-logic/crew-hours-heavy.md`
- The shadow work and its open rulings:
  `heavy-fdp-regulatory-model-plan-2026-09-03.md`

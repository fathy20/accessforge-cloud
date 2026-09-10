# Heavy from the FDP engine — implementation plan v2 (2026-09-03)

**Status:** REVISED after review. Author: Fable 5.1. Reviewer: GPT-6 Astra
(APPROVE-WITH-CHANGES, 6 blockers — all accepted, all folded in below).
Rollback point: `docs/architecture/crew-hours-logic-v2.md` (code anchor
`708574e`).

### What the review changed

| # | Astra's blocker | Verified? | Resolution |
|---|---|---|---|
| 1 | `fdpLength > maxFdpLength` conflates three different questions | yes — `maxFdpLength` already includes extensions, and 4 cockpit duties are augmented *below* the basic limit | §2a: three named quantities, and Phase D reframed |
| 2 | Extending `AugmentedIndex` is unsafe; an FDP field rejection makes the **whole** index unavailable | yes — `service.py:132` type-checks, `:233` reads `by_crew_sector`, tests build it positionally, and `_fetch_augmented_index_safely` swallows every exception | Phase A rewritten: separate index, separate availability |
| 3 | Phase B lacks inputs and a duty identity | yes — plan said `localTimeOffset`, evidence said `lastAcclimatisationOffset`; `_paint_fdp_shadow` groups by *allowance* duty and assumes cockpit | Phase B rewritten around LEON's own member-duty |
| 4 | The policy object changes meaning while keeping names | yes — `domestic="never"` would override a LEON-True domestic leg, which today earns; `paid_groups` cannot express R8 | Phase C narrowed |
| 5 | The gates never test the number that matters | yes — `fdp_backtest` records per-leg `duty_credit`, never `member.heavy_credits` | **Phase 0** added |
| 6 | The rollback anchor was wrong | yes — `b47172d` is one of the three commits to revert | fixed in LOGIC v2 (`6a9f30a`) |

Also accepted, scheduled as small independent fixes (Astra's non-blocking 3
and 4, both verified): `allowance._parse_leg_start_end` calls
`day.replace(hour=…)` *outside* its `try`, so `"25:00"` raises instead of
returning `None`; and `tables_for(os.environ[...])` at `service.py:372` raises
on a bad value and takes the **whole report** down for a shadow feature.

This supersedes the *approach* of
`heavy-fdp-regulatory-model-plan-2026-09-03.md` (which proposed computing the
FDP ourselves). The LEON verification in its section 8 changed the design:
**LEON already computes the regulatory answer; we should consume it, not
re-derive it.**

---

## 1. What changed and why this plan is different

> **Correction, 2026-09-08.** This section opened by quoting the framing
> *"a rotation needs augmentation when its planned FDP exceeds the Table A/B
> maximum … the operator then flies it with a third pilot or with two crews"*
> as "the mechanism behind every Heavy heuristic". **Retracted.** Exceeding
> the base limit is one reason an operator may roster extra crew; it is not
> the definition of Heavy, not a necessary condition for augmentation, and
> not sufficient for it either.
>
> * The EgyptAir OM sets FDP limits, extensions, rest and positioning rules.
>   Read in full (ten pages, 7.1-2 … 7.1-11) it **never uses the word
>   "Heavy"** and never mentions an allowance, wage, bonus or overtime. It
>   cannot define Heavy or a Heavy allowance.
> * **Heavy is a Red Sea business/policy verdict**, decided by the owner's
>   rulings, LEON's `crewAugmentation`, and the approved precedence table.
> * Only **49 of 779** augmented June member-duties exceed the base limit;
>   the median augmented duty is about **5 h below** it. Extra crew is also
>   carried for training, ferry, familiarisation and standby cover.
> * A duty **over** the base limit may still be lawful with no extra crew —
>   split duty (7.1-6 §2-3), commander's discretion up to 3:00 (7.1-7 §2-6),
>   the cabin +1:00 (7.1-10 §7-2-1), the positioning-landings exclusion
>   (7.1-7 §2-4-1).
>
> The three-layer architecture in section 2 already assumes this separation
> and is unaffected: layer 2 validates, layer 3 decides pay, and layer 2 never
> writes a verdict. What follows below stands, minus the retracted framing.

Reading the owner's `reference.pdf` (EgyptAir OM Ch.7; the ECAR 121 Subpart Q
and CAP 371 equivalences are UNVERIFIED and not load-bearing) gave the
regulatory mechanism the FDP model measures.

Then we measured our implementation of that against **LEON's own FTL engine**
(`ftl.dutyList`, June 2026, 1,562 flown member-duties):

| Finding | Consequence |
|---|---|
| Our Table A limit == LEON's `maxFdpLength` on **524/547** cockpit duties (96%) | The reading of the regulation is right |
| The other 23 are split duty, commander's discretion, the augmentation cap, or another acclimatisation zone | Our model lacks inputs LEON has |
| LEON is configured with the **OM-2009** table values | Settles R1 from the old plan |
| Cabin limit == cockpit + 1:00 | Confirmed |
| FDP start is the **per-flight/station reporting time** (1:05–2:55, mode 1:30), *not* a constant | Our 1:30 constant was wrong |
| FDP ends at **on-blocks** (post-flight 0:00), not +0:30 | Our +0:30 was wrong |
| All June crew were acclimatised; Table B unused | Table B is dormant, not dead |

**Therefore:** LEON's FTL fields are the regulatory source of truth. They
embody Red Sea's *approved* configuration — per-flight report times, the
on-blocks end, split duty, discretion, acclimatisation zones — none of which
a local recomputation can know. Our model's job changes from *decide* to
*validate and explain*.

---

## 2. Target architecture — three layers, explicitly separated

```
  LEON FTL engine  ──►  Layer 1: REGULATORY FACTS (ingested, never invented)
                            fdpLength, maxFdpLength, fdpExtension,
                            sectorCount, isAcclimated, localTimeOffset,
                            restFacility, crewAugmentation, per-sector reportingTime
                                    │
                                    ├──►  Layer 2: VALIDATOR (fdp.py, fed LEON's inputs)
                                    │        recomputes the table limit and compares.
                                    │        Disagreement  ⇒  trace step + health counter.
                                    │        NEVER overrides Layer 1.
                                    │
                                    └──►  Layer 3: POLICY (allowance)
                                             who is paid · unit of payment ·
                                             documented exceptions (SVX/EVN/domestic)
                                             Owner-configurable, back-tested before any change.
```

Rules that must hold:

- Layer 2 never writes a verdict. Layer 3 never reads Layer 2 except through
  an explicit, owner-ruled switch.
- When LEON is silent or the FTL index is unavailable, the **existing v2
  logic** (LOGIC v2 §1) is the fallback — unchanged.
- Every layer keeps writing to `heavy_trace`, so one disclosure explains the
  whole chain.

---

## 2a. Three quantities that must never be conflated (blocker 1)

| Name | Definition | Source |
|---|---|---|
| `basic_limit` | The Table A/B maximum for this duty's band, sectors and acclimatisation, **before** any extension | our validator, or LEON's `maxFdpLength − fdpExtension` when they agree |
| `allowed_limit` | What this duty was actually permitted, **after** split duty, discretion and the augmentation cap | LEON's `maxFdpLength` |
| `recorded_augmentation` | What was actually rostered (`NORMAL` / `AUGMENTED` / `DOUBLED` / `TRIPLED`) | LEON's `crewAugmentation`, kept raw |

- "This duty is **longer than the base table limit**" ⇔ `fdpLength >
  basic_limit`. **Not** the same as "this rotation needed augmentation": the
  OM's split duty, commander's discretion, cabin +1:00 and
  positioning-landings exclusion each make an over-limit duty lawful with no
  extra crew (corrected 2026-09-08 — this line previously read "This rotation
  **needed** augmentation ⇔ `fdpLength > basic_limit`").
- "This duty was **legal**" ⇔ `fdpLength <= allowed_limit`.
- "This member **earns H.C**" is neither — it is Layer 3 policy, and the OM
  has nothing to say about it: Chapter 7 never mentions Heavy, H.C or any
  allowance in any of its ten pages.

The June evidence proves the three are independent, in both directions: four
cockpit ENGM duties are `AUGMENTED` at 12:45 against a 13:15 basic limit —
augmented while under the limit — and month-wide only 49 of 779 augmented
duties are over the base limit at all, the median sitting about 5 h under it.
So the flag never proves an overrun, and an overrun never proves the flag.
Any statement that mixes them is a bug, not a shortcut.

## 3. Phases

### Phase 0 — prove "no behaviour change" is provable (do this first)

Astra's highest-value change, accepted. Before any ingestion, build the gate
that makes every later phase's central promise falsifiable.

1. A snapshot harness that pins **inputs**: the LEON MCP rows, FTL duty rows
   and flight-list context for a fixed set of windows, recorded to disk so a
   baseline and a candidate run on *identical* data.
2. Windows that cross month boundaries in both directions:
   May/June, June/July, July/August.
3. A comparison that asserts **zero** unapproved change in: every member's
   `heavy_credits`; each duty's identity and anchor date; every leg's
   `duty_credit` and `credit_source`; `effective_heavy`, `heavy_source`,
   `heavy_reason`, `unknown_resolved`; the official totals; and the export
   cells.
4. Failure-path cases: an FDP field rejected by LEON, a partial FTL payload,
   and a duplicate-key conflict must each leave the credits untouched.

**Nothing in Phase A–E starts until this gate is green and committed.**

### Phase A — ingest the FTL facts (shadow, no behaviour change)

**Rewritten after blocker 2.** `AugmentedIndex` must not change shape at all.
Its type is checked, its `by_crew_sector` map is read directly, tests build it
positionally, and — decisively — `_fetch_augmented_index_safely` catches
*every* exception and returns an unavailable index. Adding fields to its query
would mean that one rejected FDP field silently drops augmentation for the
whole month, which changes credits and disables STEP 4.

1. **A second, independent query and index.** `FtlDutyIndex` is built by its
   own fetch, keyed `(crew_code, trNid)` → frozen `FtlDuty`. `AugmentedIndex`
   keeps its current query, shape, constructor and semantics, untouched.
2. **Independent availability.** `ftl_duty_index.available` is separate from
   `augmented_index.available`. An FDP fetch or parse failure logs, sets its
   own index unavailable, and **cannot** affect augmentation. A test asserts
   exactly this: force the FDP query to raise, assert credits are identical.
3. **Field-rejection fallback.** If LEON rejects any new selection, retry once
   with the reduced field set and record `ftl_fdp_detection: "unavailable"` in
   the response — the `cabin_trainee_detection` precedent.
4. Surface per leg as `FlightItem.ftl` (new, optional): `fdp`, `max_fdp`,
   `extension`, `basic_limit`, `sectors`, `acclimatised`, `rest_facility`,
   `augmentation` (raw string, never a boolean), `duty_start`, `duty_end`,
   `duty_key`.
5. **Health, reported honestly** (Astra's nitpick 1): not one 50% ratio, but
   `matched / valid / missing / ambiguous / unavailable`, split cockpit vs
   cabin, and counted over the **buffered** legs the allowance actually uses,
   not only the displayed rows.

**Done when:** Phase 0's gate is still green with ingestion on; the
force-a-rejection test proves credits are unaffected; June + July pull with
the new counters populated.

### Phase B — turn the local model into a validator

**Rewritten after blocker 3.**

1. **Compare LEON's member-duty against itself.** The unit is LEON's own duty
   (its sector list and `trNid`s), *not* the allowance's duty grouping.
   `_paint_fdp_shadow` currently measures an allowance-grouped rotation and
   assumes `crew_type="cockpit"` even for cabin — both wrong for a validator.
   Keep the LEON duty key distinct from `scope_row_unique_id`.
2. **Take LEON's own window.** Use `fdpStartTime`/`fdpEndTime` directly rather
   than reconstructing them; then *separately* report how they relate to the
   first `reportingTime` and to on-blocks. The observed match was 1553/1562,
   not all — so it is an observation to monitor, never an assumption.
3. **Full input set**, or refuse to judge: `lastAcclimatisationOffset` (not
   `localTimeOffset` — the evidence in §8 of the prior plan is explicit),
   `isAcclimated`, `sectorCount`, `isCabinCrew`, `splitDutyTime`,
   `discretionLength`, `restFacility`, `previousDutyEndTime`.
4. **Insufficient data is a first-class outcome** (Astra's nitpick 2). Today
   `fdp.py` silently falls back to Table A when acclimatisation is unknown and
   clamps `sectors <= 0` to 1. In validator mode those become
   `INSUFFICIENT_DATA`, never a limit that reads like a verdict.
5. Emit `FDP_VALIDATE_*` trace steps classifying each gap: `split_duty`,
   `discretion`, `augmentation_cap`, `other_zone`, `insufficient_data`,
   `unexplained`. A classification must be *evidenced* — the mere presence of
   a non-zero `splitDutyTime` does not license ignoring an arbitrary
   difference; the arithmetic has to close.
6. `unexplained` is the tripwire, pinned at 0 on the June snapshot.

### Phase C — the allowance becomes explicit policy

**Narrowed after blocker 4.** The first draft renamed today's behaviour into
options that quietly meant something else: `domestic="never"` would have
overridden a LEON-True operated domestic leg, which *does* earn today
(`allowance.py:221` — LEON is authoritative and the gates never re-judge it),
and `paid_groups` could only remove cabin *entirely*, which is not what R8
asks. It also lost information: `AllowanceLeg.leon_heavy` flattens
`AUGMENTED`/`DOUBLED`/`TRIPLED` to a boolean before any policy could see it.

So: **no general configuration engine.** A versioned, closed policy record:

- `version` + `effective_from`, both recorded on every computed credit, so a
  number can always be explained by the policy that produced it.
- The unit stays **member-duty anchored on the first leg's UTC date**. Not an
  option — it is a validated invariant (LOGIC v2 §2).
- Entitlement is expressed as *evidence and precedence*, not as flags: which
  `crewAugmentation` values count as evidence, for which crew group, and what
  each source requires. Raw augmentation strings reach this layer intact.
- Airport handling keeps today's exact semantics, including that domestic is
  a local-rule No that a LEON value overrides — not an absolute.

R3 and R4 move out of "open rulings" into **standing constants**: the
regulatory cabin minimum is not evidence that the approved *allowance*
threshold of `> 4` changed, and domestic was never an absolute like EVN/SVX.
Changing either needs new evidence, not a preference.

Default behaviour is unchanged and proven so by Phase 0, not asserted.

### Phase D — "duties worth reviewing", not a compliance verdict

**Reframed after blocker 1.** The earlier framing ("over the limit with no
augmentation and no swap recorded") treated *an unpaid allowance* as evidence
that no augmentation happened. It is not: the allowance is a pay policy, and
LEON's own `crewAugmentation` and `maxFdpLength` are the operational record.

The output is therefore a review list built only from LEON's own numbers —
duties where `fdpLength > allowed_limit`, or where `fdpLength > basic_limit`
with `recorded_augmentation == NORMAL` and no extension that explains it.
Recomputed with Phase B's corrected inputs several of today's 120 disappear
(the EVN night pair lands exactly on 10:15, not over). It is a report tab for
humans, never a verdict and never an input to pay.

### Phase E — promotion, only per owner rulings

Candidates, each independently switchable:
- replace the 4:00 sector minimum / 3:00 link with "same FDP per LEON";
- cabin threshold from the 50% rule (`minimum × 1.5`) instead of `> 4`;
- EVN/SVX/domestic become documented *policy* overrides that the trace reports
  as agreeing or disagreeing with the regulatory answer.

---

## 4. Open rulings

| # | Question | Status |
|---|---|---|
| R1 | Which FDP tables govern | **Answered by data**: LEON is configured with OM-2009 |
| R2 | Same duty = break < 4h (today) or LEON's own duty grouping | open |
| R3 | Keep SVX/EVN/domestic as absolutes where they disagree | open (recommend: yes, and show the disagreement) |
| R4 | Cabin augmentation threshold: `minimum × 1.5` or `> 4` | open |
| R5 | Does a ride *before* the operated leg extend the member's FDP for the allowance | open (book says yes; LEON's own duty answers it per member) |
| R6 | Compliance view wanted, and for whom | open |
| R7 | Missing OM pages 7.1-5 … 7.1-9 | **closed 2026-09-08** — the owner supplied the full ten-page chapter; relief 7.1-6 §2-2, split duty 7.1-6 §2-3, positioning 7.1-7 §2-4-1, discretion 7.1-7 §2-6, rest 7.1-8 §3, standby 7.1-9 §4, cabin 7.1-10 §7 all read verbatim |
| R8 | **Does a cabin member earn H.C on a single-sector Moscow/LED duty** because the cabin was DOUBLED, when their own duty is ~7:50 vs a 13:00 limit? | open — evidence gathered **in parallel**, not blocking |
| R9 | Adopt LEON FTL fields as the primary regulatory source, demote our constants to a validator | open (recommend: yes — this plan assumes it) |

**On R8, the proposed principle** (Astra's Q4, accepted): entitlement follows
*being assigned to and operating within an approved augmented/doubled crew
complement*, **not** how close that individual came to their own FDP limit.
Augmentation working as intended — shortening each member's personal duty — is
not a reason to withdraw the allowance. Evidence required before recommending
it to the owner: the cabin allowance rule or an approved payment sheet; a
matched positive and negative sample tying member → roster → actual role →
duty → the DOUBLED flag; and confirmation from whoever configures LEON of what
that flag denotes. Note the flag is read from a **member-duty** and spread
across its sectors (`augmented.py:72`) — that alone does not establish it is
an independent property of the flight's cabin complement. The 981 rows must be
converted to member-duties and monthly credits before any financial impact is
shown to the owner; rows are not money.

---

## 5. What this plan explicitly does NOT do

- It does not change any displayed verdict, export cell, or credit until an
  owner ruling says so.
- It does not touch block-time totals.
- It does not re-open anything in `MCP_Memory/development/closed-questions.md`.
- It does not require a database migration.

## 6. Verification gates for every phase

**Rewritten after blocker 5.** The old list never checked the number that
matters. `fdp_backtest` records a per-leg `duty_credit`, which can be True in
a month whose credit was counted elsewhere; and both tools exit 0 whether or
not they found disagreements, so "the tool ran" was passing for "the tool
agreed".

1. **Phase 0 parity gate** — zero unapproved change in per-member
   `heavy_credits`, duty identity and anchor, per-leg credit flags, verdict
   provenance and badge, official totals, and export cells, across the three
   boundary-crossing windows. Runs on the pinned snapshot, so a LEON-side
   change cannot be mistaken for a code change.
2. `fdp_leon_compare` — `unexplained == 0`, and it must **exit non-zero**
   when that is violated.
3. Full backend suite green.
4. `npx tsc --noEmit` and `npx vitest run` green.
5. Diff reviewed against the phase's stated scope.

A phase is not done until all five pass. For any phase that could touch pay,
the delta table (members gained, members lost, per month) goes to the owner
*before* the change lands, never after.

---

## 7. Execution order

1. **Phase 0** — the parity gate. Implementer: Opus. Nothing else starts first.
2. The two verified bugs, as independent commits: the `"25:00"` parser crash
   in `allowance._parse_leg_start_end`, and `tables_for` taking the whole
   report down over a shadow setting.
3. **Phase A** — separate FTL index and its failure isolation.
4. **Phase B** — validator on LEON's own duty. In parallel: gather the R8
   evidence, which needs no code.
5. **Phase C / D** — only once the evidence is in and the owner has ruled.
6. **Phase E** — promotion, one switch at a time, each with a delta table.

## 8. Configuration drift — the risk this design creates

Making LEON the source of truth means a silent change to LEON's FTL
configuration would flow straight through, and the validator — which borrows
LEON's own reporting times and offsets — could well agree with it. So the
validator is *not* drift detection. Record the observable configuration
fingerprint (the basic limits actually seen per band and sector count, the
augmentation caps, the report-time distribution) each run, alert on change,
and **halt promotion** when the fingerprint moves without review. Never adjust
pay automatically in response.

## 9. Standing constraints for every implementer on this plan

- The rollback point is `docs/architecture/crew-hours-logic-v2.md`. Its
  §1 and §2 invariants must hold, and Phase 0 must be able to prove it.
- Do not re-open anything in `MCP_Memory/development/closed-questions.md`.
- `heavy.py`, `unknown_resolver.py`, `trace.py`, `fdp.py`, `allowance.py`
  stay pure: no I/O, no service imports.
- No verdict, credit, export cell, or block-time total changes without an
  owner ruling recorded in the ADR.

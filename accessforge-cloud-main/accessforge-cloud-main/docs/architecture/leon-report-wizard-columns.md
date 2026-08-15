# LEON Report Wizard — Flight Scope Column List

This ADR records what the captured Report Wizard column metadata can and cannot establish for the Crew Hours flight-scope design. It does not treat a column label as proof of the returned value shape.

## Provenance

Captured by the orchestrator during a read-only LEON metadata discovery call; raw artifact
not retained in the repository.

The artifact provenance is:

- tool: get-report-wizard-flight-scope-columns-list
- arguments: {}
- MCP protocol: 2025-03-26
- initialize: HTTP 200 (no Mcp-Session-Id header returned by the server)
- tools/call: HTTP 200, content-type text/event-stream, 106,753 body bytes
- captured: 2026-08-05
- columns returned: 1181
- location in payload: result.content[0].text -> JSON string -> array of column objects
- definition keys: exactly three -> "id", "label", "comment"
- no report rows were fetched; no personal data; no token in the artifact

The independent count in this ADR is 1,181 objects in the artifact's columns array, matching the captured count.

## Column definition shape

The definition is metadata only. A real example is:

~~~json
{"id": "scope_row_unique_id", "label": "Scope row unique ID", "comment": null}
~~~

LEON returns only id, label, and an optional free-text comment. There is no data-type field, nullable field, or scalar-vs-array field. Accordingly, Type, Nullable, and Scalar/Array are recorded as not provided by LEON throughout the resolution table. Where a plural label appears, an array is mentioned only as an inference from the label and is not stated as a fact about the response.

## Target column resolution

Status meanings:

- RESOLVED means one generic, unambiguous metadata match for the target interpretation.
- AMBIGUOUS means more than one plausible metadata candidate remains; the candidates are not collapsed into one answer.
- UNRESOLVED means the requested generic field is not present, even if an adjacent aggregate or role-specific field exists.

| # | Target | Column ID | Exact label | Type | Nullable | Scalar/Array | Status | Notes |
|---:|---|---|---|---|---|---|---|---|
| 1 | Position type | — | — | not provided by LEON | not provided by LEON | not provided by LEON | UNRESOLVED | No generic scalar Position type column exists. The closest aggregate is crew_position_names with exact label Crew position names. Role slots such as crew_CPT with label CPT [Cockpit] and crew_FO with label FO [Cockpit] are fixed roles, not a generic per-crew-member position field. |
| 2 | Crew first name | — | — | not provided by LEON | not provided by LEON | not provided by LEON | UNRESOLVED | No generic first-name column exists. crew_names has exact label Crew names and is an aggregate candidate; role-specific fields such as crew_CPT_name with label CPT name [Cockpit] are not a generic first-name field. |
| 3 | Crew surname | — | — | not provided by LEON | not provided by LEON | not provided by LEON | UNRESOLVED | No column with a surname, family-name, or generic last-name meaning was found. |
| 4 | Crew code / person code | crew_codes | Crew codes | not provided by LEON | not provided by LEON | not provided by LEON; array inferred from plural label | RESOLVED | crew_codes is the one generic crew-code match and is already confirmed in production use. No separate generic person code field was returned; crew_CMD with label Commander code is role-specific. |
| 5 | Date ADEP UTC | dateUTC<br>date_STD_log_UTC | Date ADEP [Plan][UTC]<br>Date ADEP [JL][UTC] | not provided by LEON for both candidates | not provided by LEON for both candidates | not provided by LEON for both candidates | AMBIGUOUS | Recommend date_STD_log_UTC because this module uses official actual values. dateUTC is the planned variant and is the wrong choice where the [JL] variant exists. |
| 6 | Aircraft registration | registration | Aircraft | not provided by LEON | not provided by LEON | not provided by LEON | RESOLVED | registration is the generic current-aircraft match used by the customer header Aircraft. initial_aircraft_registration with label Initial aircraft registration is historical and is not the generic current registration. |
| 7 | Aircraft type | acftType | Aircraft type | not provided by LEON | not provided by LEON | not provided by LEON | RESOLVED | acftType is the exact generic label. ICAOAcftType and IATAAcftType are qualified representations, while initial_aircraft_type is historical. |
| 8 | Flight number | flightNo | Flight number | not provided by LEON | not provided by LEON | not provided by LEON | RESOLVED | flightNo is the exact generic match. flight_no_iaco with label ICAO flight number and flight_no_iata with label IATA flight number are qualified alternatives; the mixed spelling in flight_no_iaco is reproduced literally. |
| 9 | ADEP | ADEPICAO<br>ADEP_ICAO_log<br>ADEPIATA<br>ADEP_IATA_log<br>ADEP_FAA<br>ADEP_FAA_log<br>ADEP_available_code<br>ADEP_available_code_log<br>ADEPCity<br>ADEP_City_log<br>ADEPName<br>ADEP_Name_log<br>ADEP_custom_code<br>ADEP_preferred_code<br>jl_adep_preferred_code | ADEP ICAO [Plan]<br>ADEP ICAO [JL]<br>ADEP IATA [Plan]<br>ADEP IATA [JL]<br>ADEP FAA [Plan]<br>ADEP FAA [JL]<br>ADEP [Available Code] [Plan]<br>ADEP [Available Code] [JL]<br>ADEP city [Plan]<br>ADEP city [JL]<br>ADEP name [Plan]<br>ADEP name [JL]<br>ADEP custom code [Plan]<br>ADEP preferred code [Plan]<br>ADEP preferred code [JL] | not provided by LEON for all candidates | not provided by LEON for all candidates | not provided by LEON for all candidates | AMBIGUOUS | Recommend jl_adep_preferred_code with exact label ADEP preferred code [JL], because it is the customer's export label and the module's actual-only rule. The target remains ambiguous at metadata level because LEON also exposes several airport formats and names. |
| 10 | ADES | ADESICAO<br>ADES_ICAO_log<br>ADESIATA<br>ADES_IATA_log<br>ADES_FAA<br>ADES_FAA_log<br>ADES_available_code<br>ADES_available_code_log<br>ADESCity<br>ADES_City_log<br>ADESName<br>ADES_Name_log<br>ADES_custom_code<br>ADES_preferred_code<br>jl_ades_preferred_code | ADES ICAO [Plan]<br>ADES ICAO [JL]<br>ADES IATA [Plan]<br>ADES IATA [JL]<br>ADES FAA [Plan]<br>ADES FAA [JL]<br>ADES [Available Code] [Plan]<br>ADES [Available Code] [JL]<br>ADES city [Plan]<br>ADES city [JL]<br>ADES name [Plan]<br>ADES name [JL]<br>ADES custom code [Plan]<br>ADES preferred code [Plan]<br>ADES preferred code [JL] | not provided by LEON for all candidates | not provided by LEON for all candidates | not provided by LEON for all candidates | AMBIGUOUS | Recommend jl_ades_preferred_code with exact label ADES preferred code [JL], because it is the customer's export label and the module's actual-only rule. The target remains ambiguous at metadata level because LEON also exposes several airport formats and names. |
| 11 | OFF | STDUTC<br>STDLT<br>JL_STD_UTC<br>JL_STD_LT<br>FW_STD_UTC<br>FW_STD_LT<br>JL_ATD_UTC<br>JL_ATD_LT<br>FW_ATD_UTC<br>FW_ATD_LT | STD [UTC]<br>STD [LT]<br>BLOFF [JL][UTC]<br>BLOFF [JL][LT]<br>BLOFF [FW][UTC]<br>BLOFF [FW][LT]<br>T/O [JL][UTC]<br>T/O [JL][LT]<br>T/O [FW][UTC]<br>T/O [FW][LT] | not provided by LEON for all candidates | not provided by LEON for all candidates | not provided by LEON for all candidates | AMBIGUOUS | Recommend JL_STD_UTC with exact label BLOFF [JL][UTC]. It is the actual block-off endpoint, and it is consistent with the customer's ON minus OFF equals Block time fact. T/O fields are airborne endpoints; STD fields are scheduled endpoints; FW fields are Flight Watch rather than official JL. |
| 12 | ON | STAUTC<br>STALT<br>JL_STA_UTC<br>JL_STA_LT<br>FW_STA_UTC<br>FW_STA_LT<br>JL_ATA_UTC<br>JL_ATA_LT<br>FW_ATA_UTC<br>FW_ATA_LT | STA [UTC]<br>STA [LT]<br>BLON [JL][UTC]<br>BLON [JL][LT]<br>BLON [FW][UTC]<br>BLON [FW][LT]<br>LDG [JL][UTC]<br>LDG [JL][LT]<br>LDG [FW][UTC]<br>LDG [FW][LT] | not provided by LEON for all candidates | not provided by LEON for all candidates | not provided by LEON for all candidates | AMBIGUOUS | Recommend JL_STA_UTC with exact label BLON [JL][UTC]. It is the actual block-on endpoint paired with JL_STD_UTC. LDG fields are airborne endpoints; STA fields are scheduled endpoints; FW fields are Flight Watch rather than official JL. |
| 13 | Block Time Journey Log | blockTimeJourneyLog | Block time [JL] | not provided by LEON | not provided by LEON | not provided by LEON | RESOLVED | blockTimeJourneyLog is the exact confirmed production column. block_time_journey_log_decimal with label Block time [JL][DEC] is a decimal representation, while blockTimePlan is the wrong planned variant. |
| 14 | PAD / positioning / Not-Active | positioning_crew | Positioning crew | not provided by LEON | not provided by LEON | not provided by LEON | UNRESOLVED | positioning_crew is a partial match for positioning, but no PAD, Not-Active, inactive, or generic crew-active column exists in the metadata. flight_status with label Flight status is a flight status, not proof of a crew exclusion flag. |
| 15 | Stable row identifier | scope_row_unique_id<br>unique_id<br>unique_leg_number<br>trip_nid | Scope row unique ID<br>Unique ID<br>Unique leg number<br>Trip nid | not provided by LEON for all candidates | not provided by LEON for all candidates | not provided by LEON for all candidates | AMBIGUOUS | Recommend scope_row_unique_id because its exact label names the report-scope row. unique_id and unique_leg_number remain plausible row/leg identifiers, while trip_nid is trip-level. A one-row report-scope probe is required to disambiguate values and duplicate behavior. |

For rows with multiple candidates, the ID and label lists are aligned by position. All IDs above are copied literally from the artifact; no ID has been normalized.

## Architecture-deciding answers

### A. Crew code

Yes, a generic crew-code column exists: crew_codes with exact label Crew codes. It is one of the four IDs already confirmed in production use. The label supports only the inference that the value may be an aggregate or array; LEON did not provide cardinality or type, so metadata alone does not prove one code per report row. No separate generic person code column exists.

### B. Generic scalar per-crew fields

No generic scalar per-crew-member columns for Name, Surname, or Position type are present. The generic crew fields are aggregate/plural-labelled fields such as crew_codes, crew_names, crew_position_names, crew_home_bases, and crew_phones. LEON also exposes fixed role slots, including crew_CPT_name, crew_FO_name, crew_CMD_name, and many cabin-role name columns, but a CPT or FO slot is not a generic per-crew-member record. The metadata therefore supports aggregate crew data plus role slots, not a proven crew-expanded row shape.

### C. PAD, positioning, and Not-Active

positioning_crew with exact label Positioning crew exists. No column with PAD, Not-Active, inactive, or generic crew-active wording exists. flight_status is present but is a flight status and has no returned values in this artifact, so it cannot be used as a crew-level exclusion rule from metadata alone.

### D. Stable per-row or per-flight identifier

The metadata contains scope_row_unique_id, unique_id, unique_leg_number, and trip_nid. scope_row_unique_id is the strongest candidate because its label explicitly names a scope row, but the list contains no values and does not establish uniqueness, persistence, or whether multiple crew records share one flight row. A one-row report-scope probe must verify the identifier behavior before it is a join key.

### E. Total column count

The artifact contains 1,181 column objects. This count was independently computed from the columns array and agrees with the captured columns returned value.

### F. OFF and ON semantics

For OFF, recommend JL_STD_UTC with label BLOFF [JL][UTC]; for ON, recommend JL_STA_UTC with label BLON [JL][UTC]. The metadata distinguishes these block endpoints from JL_ATD_UTC and JL_ATA_UTC, whose labels are T/O and LDG and therefore describe airborne endpoints. The customer's exact ON minus OFF equals Block time relationship supports the BLOFF/BLON pairing with blockTimeJourneyLog, but the metadata alone does not prove response values or calculation behavior.

## [JL] vs [Plan] warning

The module's business rule is official actual values only. Whenever a [JL] variant exists, the [Plan] variant is the wrong choice for this module.

| Target | Planned or scheduled candidate | Actual candidate | Module choice |
|---|---|---|---|
| Date ADEP UTC | dateUTC — Date ADEP [Plan][UTC] | date_STD_log_UTC — Date ADEP [JL][UTC] | Use date_STD_log_UTC. |
| ADEP preferred code | ADEP_preferred_code — ADEP preferred code [Plan] | jl_adep_preferred_code — ADEP preferred code [JL] | Use jl_adep_preferred_code. |
| ADES preferred code | ADES_preferred_code — ADES preferred code [Plan] | jl_ades_preferred_code — ADES preferred code [JL] | Use jl_ades_preferred_code. |
| Other ADEP/ADES representations | ADEPICAO, ADEPIATA, ADEP_FAA, ADEP_available_code, ADEPCity, ADEPName and their ADES counterparts are [Plan] candidates | ADEP_ICAO_log, ADEP_IATA_log, ADEP_FAA_log, ADEP_available_code_log, ADEP_City_log, ADEP_Name_log and the preferred-code [JL] fields | Select the required actual [JL] representation; do not substitute a [Plan] field. |
| OFF | STDUTC — STD [UTC] and STDLT — STD [LT] are scheduled endpoints; FW_STD_UTC and FW_STD_LT are Flight Watch | JL_STD_UTC — BLOFF [JL][UTC] and JL_STD_LT — BLOFF [JL][LT] | Use JL_STD_UTC for the UTC export interpretation. |
| ON | STAUTC — STA [UTC] and STALT — STA [LT] are scheduled endpoints; FW_STA_UTC and FW_STA_LT are Flight Watch | JL_STA_UTC — BLON [JL][UTC] and JL_STA_LT — BLON [JL][LT] | Use JL_STA_UTC for the UTC export interpretation. |
| Block time | blockTimePlan — Block time [Plan] | blockTimeJourneyLog — Block time [JL] | Use blockTimeJourneyLog. |

The FW fields are also not a substitute for official [JL] values. The [LT] variants may be relevant to a different export contract, but the customer's Date ADEP [JL][UTC] header makes the UTC candidates the recommended pair here.

## Columns relevant to Crew Hours but not in the 15 targets

These are a curated set of additional definitions that can help identity, role interpretation, filtering, or reconciliation. They remain metadata-only; their response type and cardinality are not established.

| Column ID | Exact label | Why it is useful |
|---|---|---|
| numberOfCrew | Number of crew | Count cross-check for aggregate crew fields. |
| cockpitCrew | Cockpit crew | Cockpit cohort context. |
| cockpit_crew_full_names | Cockpit Crew Full names | Human-readable cockpit aggregate for reconciliation. |
| cabinCrew | Cabin crew | Cabin cohort context. |
| crew_home_bases | Crew homebases | Base context for crew assignment reconciliation. |
| crew_CMD | Commander code | Role-specific code useful for commander matching. |
| crew_CMD_name | Commander name | Role-specific display and reconciliation. |
| crew_CPT | CPT [Cockpit] | Fixed captain slot, if role-slot reporting is used. |
| crew_CPT_name | CPT name [Cockpit] | Fixed captain name slot. |
| crew_FO | FO [Cockpit] | Fixed first-officer slot. |
| crew_FO_name | FO name [Cockpit] | Fixed first-officer name slot. |
| crew_FE | FE [Cockpit] | Fixed flight-engineer slot. |
| crew_INS | INS [Cockpit] | Fixed instructor slot. |
| crew_captains | CPT [Cockpit] | Aggregate captain list for role reconciliation. |
| crew_opr_captain_list | Captains | Operational captain aggregate. |
| crew_opr_officer_list | Officers | Operational officer aggregate. |
| crew_opr_inflight_personnel_list | Inflight service personnel | Operational inflight-personnel aggregate. |
| crew_opr_fa_list | Flight attendants | Operational cabin-personnel aggregate. |
| crew_opr_fe_list | Flight engineer | Operational engineer aggregate. |
| crew_opr_sfa_list | Senior flight attendants | Operational senior-cabin aggregate. |
| pilotFlying | Pilot flying [JL] | Actual role context from the Journey Log. |
| pilot_flying_full_name | Pilot flying full name [JL] | Actual display value for pilot-flying reconciliation. |
| pilot_monitoring | Pilot monitoring [JL] | Actual role context from the Journey Log. |
| pilot_monitoring_full_name | Pilot monitoring full name [JL] | Actual display value for pilot-monitoring reconciliation. |
| flight_status | Flight status | Candidate flight-level filter, not a crew-active flag. |
| initial_flight_status | Initial flight status | Historical status comparison. |
| flight_has_log | Flight has a log? | Identifies whether a Journey Log exists. |
| jl_number_of_legs_in_a_trip | Number of legs in a trip  [JL] | Actual trip/leg reconciliation. |
| is_last_leg_in_a_trip_jl | Is last leg in a trip? [JL] | Actual trip-boundary handling. |
| fatigue_score | Fatigue score [JL] | Potential fatigue-related review context. |
| jl_fatigue_score_other | Fatigue score - other crew [JL] | Other-crew fatigue context. |
| jl_rest_facility | In-flight Rest Facility [JL] | Actual rest context relevant to hours review. |
| jl_crew_transport | Crew transport [JL] | Actual crew logistics context when reconciling exceptions. |

The curated list contains 33 additional definitions. Omitted additional Crew Hours candidates from this curated set: 0; the remaining definitions were not classified as genuinely useful for this ADR, and this section is not an exhaustive semantic classification of all 1,181 definitions.

## Notes and anomalies

- The customer's Excel headers are labels, not IDs. The exact customer labels ADEP preferred code [JL], ADES preferred code [JL], Aircraft type, Aircraft, Flight number, and Block time [JL] are present, but the corresponding IDs use mixed naming conventions.
- The supplied customer export has 2,484 data rows and no crew-code column. Its requested headers include Position type, Name, Surname, Date ADEP [JL][UTC], Aircraft type, Aircraft, Flight number, ADEP preferred code [JL], ADES preferred code [JL], OFF, ON, and Block time [JL].
- flightNo, acftType, registration, JL_STD_UTC, and blockTimeJourneyLog are intentionally reproduced with their artifact spelling and casing. flight_no_iaco is also reproduced literally even though its label says ICAO flight number.
- The artifact has no literal generic column named Position type, Name, Surname, OFF, or ON. OFF and ON are semantic export headers; the relevant LEON labels are BLOFF and BLON.
- The search found jl_hobbs_off with label Hobbs off [JL], jl_tah_off with label Tach off [JL], and jl_off_task with label Off task time [JL][UTC]. These are instrument or task fields, not flight block endpoints. Likewise, jl_hobbs_on, jl_tah_on, and jl_on_task are not substitutes for BLON.
- The four supplied production-confirmed IDs are crew_codes, crew_names, blockTimeJourneyLog, and blockTimePlan. Their production confirmation does not add type or cardinality keys to this metadata artifact, and blockTimePlan remains the wrong choice for this actual-only module.
- The role-specific name columns, for example crew_CPT_name and crew_FO_name, cannot be reinterpreted as a generic scalar first-name or surname field.
- No report rows were fetched by the captured call. No value-level conclusion is made about nulls, arrays, formats, duplicate IDs, or actual row expansion.
- comment is optional free text and is not a type contract. A null comment is not evidence that a value is scalar, nullable, or required.
- **Post-capture live finding (June 2026).** Target 14 is recorded above as UNRESOLVED at the column level, and that remains correct: no PAD / Not-Active column exists. A later read-only report call showed that positioning is expressed as a **value** inside `crew_position_names` — `PAD` appeared 216 times, alongside `PSN`, `FDP`, `FDPI`, `RMP` and `INSP` — while `positioning_crew` was an empty array in every row. None of those six tokens is declared in LEON's role-slot vocabulary, so they map to `position_type = null` and are excluded from Cockpit/Cabin filtering. Their official block time is still included in every total, per the approved Operations rule recorded in `crew-hours-source-decision.md`.

## What this file does NOT establish

Metadata alone cannot prove:

- row cardinality, including whether a report row is per flight, per leg, per crew member, or an aggregate;
- value formats, timezone encoding, duration units, array serialization, or whether names are full names versus components;
- whether every listed column is accepted by a report-scope execution, even when its definition is returned by the list tool;
- response size, pagination behavior, payload limits, or the size of a report containing these columns;
- uniqueness or long-term stability of scope_row_unique_id, unique_id, unique_leg_number, or trip_nid;
- that ON minus OFF is computed by LEON rather than observed in the customer's export.

Those questions require a bounded report-scope execution or another authoritative data contract. They are intentionally left as follow-up validation rather than inferred from this artifact.

import unittest

from backend.statistics.crew_hours.crew_context import (
    CrewContextEntry,
    CrewContextIndex,
    FlightContext,
)
from backend.statistics.crew_hours.augmented import AugmentedIndex
from backend.statistics.crew_hours.mcp_report import OfficialMcpReport
from backend.statistics.crew_hours.heavy import (
    decide_heavy,
    derive_heavy,
    derive_heavy_detail,
    is_training_function,
    is_training_position,
    operating_cabin_count,
    operating_cockpit_count,
)
from backend.statistics.crew_hours.positions import (
    HEAVY_CABIN_THRESHOLD,
    HEAVY_COCKPIT_THRESHOLD,
)
from backend.statistics.crew_hours.service import LiveCrewHoursService, _build_mcp_report_response
from backend.statistics.crew_hours.unknown_resolver import (
    build_rotation_index,
    resolve_unknown_heavy,
)


def _entry(
    *,
    pos_type: str | None = "COCKPIT",
    position: str | None = "FO",
    training_type: str | None = None,
    crew_code: str | None = None,
    function: str | None = None,
) -> CrewContextEntry:
    return CrewContextEntry(
        pos_type=pos_type,
        position=position,
        training_type=training_type,
        crew_code=crew_code,
        function=function,
    )


class TestHeavyDecision(unittest.TestCase):
    def test_precedence_table_is_exact(self):
        cases = (
            (True, True, True, True, "LEON_AND_LOCAL", "MULTIPLE_RULES", False),
            (True, False, True, False, "LEON", "LEON_AUGMENTED", False),
            (True, None, True, None, "LEON", "LEON_AUGMENTED", False),
            (False, True, False, True, "LEON", "EXTRA_COCKPIT_CREW", True),
            (False, False, False, False, "LEON", "NONE", False),
            (False, None, False, None, "LEON", "NONE", False),
            (None, True, None, True, "UNKNOWN", "EXTRA_COCKPIT_CREW", False),
            (None, False, None, False, "UNKNOWN", "UNKNOWN", False),
            (None, None, None, None, "UNKNOWN", "UNKNOWN", False),
        )
        # LEON silent + no absolute tag leaves effective_heavy None so STEP 4 can run.

        for leon, derived, effective, expected_derived, source, reason, conflict in cases:
            with self.subTest(leon=leon, derived=derived):
                decision = decide_heavy(leon, derived)
                self.assertIs(decision.leon_heavy, leon)
                self.assertIs(decision.derived_heavy, expected_derived)
                self.assertIs(decision.effective_heavy, effective)
                self.assertEqual(decision.heavy_source, source)
                self.assertEqual(decision.heavy_reason, reason)
                self.assertIs(decision.heavy_conflict, conflict)

    def test_thresholds_match_the_operator_standard_complement(self):
        # June 2026 Report Wizard, 304 flights carrying crew: cockpit was 2 on
        # 289 and never above 3; cabin was 4 on 236. Heavy means "more than
        # standard", so a standard 2+4 flight must not be Heavy. The originally
        # agreed pair (cockpit 4 / cabin 2) was inverted and flagged 92% Heavy.
        self.assertEqual((HEAVY_COCKPIT_THRESHOLD, HEAVY_CABIN_THRESHOLD), (2, 4))

        standard = [_entry()] * 2 + [_entry(pos_type="CABIN", position="FA1")] * 4
        self.assertIs(derive_heavy(standard, "B738 - 737-800"), False)

        extra_cockpit = [*standard, _entry()]
        self.assertIs(derive_heavy(extra_cockpit, "B738 - 737-800"), True)

        extra_cabin = [*standard, _entry(pos_type="CABIN", position="FA5")]
        self.assertIs(derive_heavy(extra_cabin, "B738 - 737-800"), True)

    def test_cockpit_threshold_is_strictly_greater(self):
        standard = [_entry()] * HEAVY_COCKPIT_THRESHOLD
        self.assertIs(derive_heavy(standard, "B738 - 737-800"), False)
        self.assertIs(derive_heavy([*standard, _entry()], "B738 - 737-800"), True)

    def test_cabin_threshold_is_strictly_greater(self):
        def cabin(count: int) -> list[CrewContextEntry]:
            return [_entry(pos_type="CABIN", position="FA1")] * count

        self.assertIs(derive_heavy(cabin(HEAVY_CABIN_THRESHOLD), "B738"), False)
        self.assertIs(derive_heavy(cabin(HEAVY_CABIN_THRESHOLD + 1), "B738"), True)

    def test_cockpit_trainees_ops_and_sp_never_count(self):
        # A standard cockpit plus two trainees must stay at the standard count,
        # otherwise the trainees alone would tip the flight into Heavy.
        entries = [_entry()] * HEAVY_COCKPIT_THRESHOLD + [
            _entry(position=" ops "),
            _entry(position="SP"),
        ]

        self.assertTrue(is_training_position("OPS"))
        self.assertTrue(is_training_position(" sp "))
        self.assertFalse(is_training_position("FO"))
        self.assertEqual(operating_cockpit_count(entries), HEAVY_COCKPIT_THRESHOLD)
        self.assertIs(derive_heavy(entries, "B738"), False)

    def test_cabin_trainees_are_excluded_by_work_schedule_function(self):
        entries = [_entry(pos_type="CABIN", position="FA1")] * 2 + [
            _entry(pos_type="CABIN", position="FA3", function=" sfa "),
        ]

        self.assertTrue(is_training_function("SFA"))
        self.assertFalse(is_training_function("FA"))
        self.assertEqual(operating_cabin_count(entries), 2)
        self.assertIs(derive_heavy(entries, "B738"), False)

    def test_training_types_and_non_operating_positions_are_excluded(self):
        entries = [_entry()] * HEAVY_COCKPIT_THRESHOLD + [
            _entry(training_type=" LINE_TRAINING "),
            _entry(training_type="line_check"),
            _entry(position=" OBS "),
            _entry(position="obs2"),
            _entry(position=" STB "),
        ]

        self.assertEqual(operating_cockpit_count(entries), HEAVY_COCKPIT_THRESHOLD)
        self.assertIs(derive_heavy(entries, "B738"), False)

    def test_non_cockpit_position_types_are_excluded(self):
        entries = [_entry()] * HEAVY_COCKPIT_THRESHOLD + [
            _entry(pos_type="NOT-ACTIVE"),
            _entry(pos_type="MAINTENANCE"),
            _entry(pos_type="GROUND"),
        ]

        self.assertEqual(operating_cockpit_count(entries), HEAVY_COCKPIT_THRESHOLD)
        self.assertIs(derive_heavy(entries, "B738"), False)

    def test_evn_is_never_heavy_and_wins_over_every_other_rule(self):
        heavy_entries = [_entry()] * 10
        self.assertIs(derive_heavy(heavy_entries, "B738", ("evn",)), False)
        self.assertIs(derive_heavy(heavy_entries, "B738", ("SVX", "EVN")), False)
        self.assertIs(derive_heavy([], "B738", ("EVN",)), False)

    def test_svx_is_always_heavy(self):
        self.assertIs(derive_heavy([_entry()], "B738", (" svx ",)), True)
        self.assertIs(derive_heavy([], "B738", ("SVX",)), True)

    def test_no_crew_context_is_unknown_not_false(self):
        self.assertIs(derive_heavy([], "B738"), None)
        self.assertIs(derive_heavy(None, "B738"), None)
        self.assertIs(derive_heavy([], "B738", ()), None)

    def test_cockpit_trainee_exclusion_decides_the_threshold_side(self):
        # Matrix 4: four cockpit where one is SP → operating 3 → Heavy;
        # three cockpit where one is SP → operating 2 → falls through to NONE.
        three_operating_plus_sp = [_entry()] * 3 + [_entry(position="SP")]
        self.assertEqual(
            derive_heavy_detail(three_operating_plus_sp, "B738"),
            (True, "EXTRA_COCKPIT_CREW"),
        )

        two_operating_plus_sp = [_entry()] * 2 + [_entry(position="SP")]
        self.assertEqual(
            derive_heavy_detail(two_operating_plus_sp, "B738"),
            (False, "NONE"),
        )

    def test_cabin_trainee_exclusion_decides_the_threshold_side(self):
        # Matrix 5: five cabin where one has Function SFA → operating 4 → NONE;
        # five all operating → Heavy.
        def cabin(function: str | None = None) -> CrewContextEntry:
            return _entry(pos_type="CABIN", position="FA1", function=function)

        four_operating_plus_sfa = [cabin()] * 4 + [cabin(function="SFA")]
        self.assertEqual(
            derive_heavy_detail(four_operating_plus_sfa, "B738"),
            (False, "NONE"),
        )

        five_operating = [cabin()] * 5
        self.assertEqual(
            derive_heavy_detail(five_operating, "B738"),
            (True, "EXTRA_CABIN_CREW"),
        )


class TestAirportBasedAbsoluteRules(unittest.TestCase):
    """EVN/SVX are AIRPORT codes in live data; tags are a secondary signal.

    Live evidence (2026-06 UI review): RSX331/RSX332 SSH↔SVX and RSX121/RSX122
    SSH↔EVN carry no LEON flight tag — the codes appear in ADEP/ADES only.
    """

    def test_svx_airport_in_the_route_forces_heavy(self):
        for route in (("SSH", "SVX"), ("SVX", "SSH"), (" svx ", None)):
            with self.subTest(route=route):
                self.assertEqual(
                    derive_heavy_detail([_entry()] * 2, "B738", None, route_airports=route),
                    (True, "SVX_AIRPORT"),
                )

    def test_evn_airport_forces_not_heavy_and_wins_over_svx(self):
        self.assertEqual(
            derive_heavy_detail([_entry()] * 10, "B738", None, route_airports=("SSH", "EVN")),
            (False, "EVN_AIRPORT"),
        )
        # EVN wins even when both codes appear in the route.
        self.assertEqual(
            derive_heavy_detail([], "B738", None, route_airports=("EVN", "SVX")),
            (False, "EVN_AIRPORT"),
        )
        # ...and even when an SVX tag is present alongside an EVN airport.
        self.assertEqual(
            derive_heavy_detail([], "B738", ("SVX",), route_airports=("SSH", "EVN")),
            (False, "EVN_AIRPORT"),
        )

    def test_airport_match_is_exact_not_substring(self):
        standard = [_entry()] * 2
        self.assertEqual(
            derive_heavy_detail(standard, "B738", None, route_airports=("SVXX", "EVNA")),
            (False, "NONE"),
        )

    def test_airport_reasons_beat_a_conflicting_leon_value(self):
        svx = decide_heavy(False, True, "SVX_AIRPORT")
        self.assertIs(svx.effective_heavy, True)
        self.assertEqual(svx.heavy_source, "LOCAL_RULE")
        self.assertEqual(svx.heavy_reason, "SVX_AIRPORT")
        self.assertTrue(svx.heavy_conflict)

        evn = decide_heavy(True, False, "EVN_AIRPORT")
        self.assertIs(evn.effective_heavy, False)
        self.assertEqual(evn.heavy_reason, "EVN_AIRPORT")
        self.assertTrue(evn.heavy_conflict)

    def test_tags_remain_a_secondary_signal(self):
        # No airports supplied: the old tag path still decides with tag reasons.
        self.assertEqual(
            derive_heavy_detail([], "B738", ("SVX",)), (True, "SVX_TAG")
        )
        self.assertEqual(
            derive_heavy_detail([], "B738", ("EVN",), route_airports=("SSH", "HRG")),
            (False, "EVN_TAG"),
        )

    def test_positioning_members_never_count_as_operating_crew(self):
        # A PAD or PSN slot must not tip the operating counts over a threshold.
        cockpit = [_entry()] * 2 + [_entry(position="PAD"), _entry(position="PSN")]
        self.assertEqual(operating_cockpit_count(cockpit), 2)
        self.assertEqual(derive_heavy_detail(cockpit, "B738"), (False, "NONE"))

        cabin = [_entry(pos_type="CABIN", position="FA1")] * 4 + [
            _entry(pos_type="CABIN", position="PAD"),
        ]
        self.assertEqual(operating_cabin_count(cabin), 4)
        self.assertEqual(derive_heavy_detail(cabin, "B738"), (False, "NONE"))


def _screenshot_row(
    unique_id: int,
    flight_number: str,
    adep: str,
    ades: str,
    crew_codes: list[str],
    positions: list[str],
) -> dict:
    return {
        "scope_row_unique_id": f"row-{unique_id}",
        "unique_id": unique_id,
        "flightNo": flight_number,
        "crew_codes": crew_codes,
        "crew_names": [f"Crew {code}" for code in crew_codes],
        "crew_position_names": positions,
        "acftType": "B738 - 737-800",
        "blockTimeJourneyLog": "01:30",
        "jl_adep_preferred_code": adep,
        "jl_ades_preferred_code": ades,
    }


class TestScreenshotEvidence(unittest.TestCase):
    """Sanitized replicas of the five live UI review cases (2026-06)."""

    def _response(self, rows, contexts):
        totals = {
            code: "10:00" for row in rows for code in row["crew_codes"]
        }
        return _build_mcp_report_response(
            OfficialMcpReport(totals, rows),
            from_date="2026-06-01",
            to_date="2026-06-30",
            position="All",
            crew_member=None,
            # LEON is silent for every case: available FTL index, no values.
            augmented_index=AugmentedIndex(True, {}, 0, 0, {}),
            crew_context_index=_unknown_index(*contexts),
        )

    @staticmethod
    def _flights_by_leg(response, crew_code):
        member = next(
            item for item in response.crew_members if item.person_code == crew_code
        )
        return {flight.flight_number: flight for flight in member.flights}

    def _context(self, unique_id, start, end, codes_positions, adep, ades):
        entries = tuple(
            _entry(position=position, crew_code=code)
            for code, position in codes_positions
        )
        return FlightContext(
            flight_nid=unique_id,
            start_time_utc=start,
            end_time_utc=end,
            flight_tags=(),
            entries=entries,
            departure_airport=adep,
            arrival_airport=ades,
        )

    def test_case_1_svx_rotation_is_yes_on_both_legs_without_badges(self):
        # 16-06: RSX331 SSH→SVX 17:15–22:35, RSX332 SVX→SSH 23:50–06:00(+1).
        # No LEON value, no tags. The PAD member's row follows the flight verdict.
        rows = [
            _screenshot_row(501, "RSX331", "SSH", "SVX", ["C1", "P1"], ["CPT", "PAD"]),
            _screenshot_row(502, "RSX332", "SVX", "SSH", ["C1"], ["CPT"]),
        ]
        contexts = [
            self._context(
                501, "2026-06-16T17:15:00Z", "2026-06-16T22:35:00Z",
                [("C1", "CPT"), ("P1", "PAD")], "SSH", "SVX",
            ),
            self._context(
                502, "2026-06-16T23:50:00Z", "2026-06-17T06:00:00Z",
                [("C1", "CPT")], "SVX", "SSH",
            ),
        ]

        response = self._response(rows, contexts)

        for code in ("C1",):
            for flight in self._flights_by_leg(response, code).values():
                self.assertIs(flight.augmented_heavy, True)
                self.assertEqual(flight.heavy_reason, "SVX_AIRPORT")
                self.assertEqual(flight.heavy_source, "LOCAL_RULE")
                self.assertFalse(flight.unknown_resolved)
                self.assertFalse(flight.heavy_conflict)
        # Screenshot 1: the PAD member shows Yes on the SVX leg.
        pad_flight = self._flights_by_leg(response, "P1")["RSX331"]
        self.assertIs(pad_flight.augmented_heavy, True)
        self.assertEqual(pad_flight.heavy_reason, "SVX_AIRPORT")
        self.assertFalse(pad_flight.unknown_resolved)

    def test_case_2_evn_rotation_is_no_on_both_legs_without_badges(self):
        # 20/21-06: RSX121 SSH→EVN 22:05–01:00(+1), RSX122 EVN→SSH 02:05–05:30.
        rows = [
            _screenshot_row(511, "RSX121", "SSH", "EVN", ["C1"], ["CPT"]),
            _screenshot_row(512, "RSX122", "EVN", "SSH", ["C1"], ["CPT"]),
        ]
        contexts = [
            self._context(
                511, "2026-06-20T22:05:00Z", "2026-06-21T01:00:00Z",
                [("C1", "CPT")], "SSH", "EVN",
            ),
            self._context(
                512, "2026-06-21T02:05:00Z", "2026-06-21T05:30:00Z",
                [("C1", "CPT")], "EVN", "SSH",
            ),
        ]

        response = self._response(rows, contexts)

        for flight in self._flights_by_leg(response, "C1").values():
            self.assertIs(flight.augmented_heavy, False)
            self.assertEqual(flight.heavy_reason, "EVN_AIRPORT")
            self.assertEqual(flight.heavy_source, "LOCAL_RULE")
            # Deterministic rule, NOT the resolver: no badge fields.
            self.assertFalse(flight.unknown_resolved)

    def test_case_3_pad_member_does_not_break_the_rotation_yes(self):
        # 22-06: RSX6081 HRG→OPO 15:00–21:00 (carries a PAD member),
        # RSX6082 OPO→HRG 22:00–03:50(+1). Break 1:00, same operating crew.
        rows = [
            _screenshot_row(601, "RSX6081", "HRG", "OPO", ["C1", "C2", "P1"], ["CPT", "FO", "PAD"]),
            _screenshot_row(602, "RSX6082", "OPO", "HRG", ["C1", "C2"], ["CPT", "FO"]),
        ]
        contexts = [
            self._context(
                601, "2026-06-22T15:00:00Z", "2026-06-22T21:00:00Z",
                [("C1", "CPT"), ("C2", "FO"), ("P1", "PAD")], "HRG", "OPO",
            ),
            self._context(
                602, "2026-06-22T22:00:00Z", "2026-06-23T03:50:00Z",
                [("C1", "CPT"), ("C2", "FO")], "OPO", "HRG",
            ),
        ]

        response = self._response(rows, contexts)

        for code in ("C1", "C2"):
            flights = self._flights_by_leg(response, code)
            for leg in ("RSX6081", "RSX6082"):
                flight = flights[leg]
                self.assertIs(flight.augmented_heavy, True, f"{code} {leg}")
                self.assertEqual(
                    flight.unknown_resolution_reason, "SAME_DAY_SHORT_BREAK_SAME_CREW"
                )
                # Resolver-decided: the badge shows on BOTH legs.
                self.assertTrue(flight.unknown_resolved)
                self.assertEqual(flight.heavy_source, "LOCAL_RULE")

    def test_case_4_unresolvable_chain_is_no_with_badges_on_both_legs(self):
        # 22-06 RSX6081 HRG→OPO then 23-06 RSX6084 OPO→SSH: next duty day, the
        # rotation never returns. Both legs entered STEP 4, so both carry the badge.
        rows = [
            _screenshot_row(611, "RSX6081", "HRG", "OPO", ["C1", "C2"], ["CPT", "FO"]),
            _screenshot_row(612, "RSX6084", "OPO", "SSH", ["C1", "C2"], ["CPT", "FO"]),
        ]
        contexts = [
            self._context(
                611, "2026-06-22T15:00:00Z", "2026-06-22T21:00:00Z",
                [("C1", "CPT"), ("C2", "FO")], "HRG", "OPO",
            ),
            self._context(
                612, "2026-06-23T08:00:00Z", "2026-06-23T12:00:00Z",
                [("C1", "CPT"), ("C2", "FO")], "OPO", "SSH",
            ),
        ]

        response = self._response(rows, contexts)

        for code in ("C1", "C2"):
            flights = self._flights_by_leg(response, code)
            for leg in ("RSX6081", "RSX6084"):
                flight = flights[leg]
                self.assertIs(flight.augmented_heavy, False, f"{code} {leg}")
                self.assertTrue(flight.unknown_resolved, f"{code} {leg}")
                self.assertEqual(flight.heavy_source, "LOCAL_RULE")
                self.assertEqual(
                    flight.unknown_resolution_reason, "BREAK_EXCEEDS_LIMIT"
                )

    def test_step_four_entry_always_flags_unknown_resolved(self):
        # A leg absent from the crew-context index still entered STEP 4: its No
        # is resolver-decided and must carry the badge fields.
        rows = [_screenshot_row(621, "RSX700", "HRG", "SSH", ["C1"], ["CPT"])]

        response = self._response(rows, [])

        flight = self._flights_by_leg(response, "C1")["RSX700"]
        self.assertIs(flight.augmented_heavy, False)
        self.assertTrue(flight.unknown_resolved)
        self.assertEqual(flight.heavy_source, "LOCAL_RULE")
        self.assertEqual(flight.unknown_resolution_reason, "NO_FLIGHT_CONTEXT")

    def test_airport_rule_fires_from_the_report_row_when_context_is_missing(self):
        # Either airport source counts: here only the report row carries SVX.
        rows = [_screenshot_row(631, "RSX331", "SSH", "SVX", ["C1"], ["CPT"])]

        response = self._response(rows, [])

        flight = self._flights_by_leg(response, "C1")["RSX331"]
        self.assertIs(flight.augmented_heavy, True)
        self.assertEqual(flight.heavy_reason, "SVX_AIRPORT")
        self.assertFalse(flight.unknown_resolved)


class TestAbsoluteTagPrecedence(unittest.TestCase):
    """EVN/SVX are absolute: they beat a conflicting LEON crewAugmentation value."""

    def test_evn_tag_beats_a_leon_augmented_value(self):
        # Matrix 1: EVN + LEON augmented → NO, conflict, tag won.
        with self.assertLogs("backend.statistics.crew_hours.heavy", level="WARNING") as logs:
            decision = decide_heavy(True, False, "EVN_TAG")

        self.assertIs(decision.effective_heavy, False)
        self.assertEqual(decision.heavy_reason, "EVN_TAG")
        self.assertEqual(decision.heavy_source, "LOCAL_RULE")
        self.assertTrue(decision.heavy_conflict)
        self.assertIs(decision.leon_heavy, True)
        self.assertTrue(any("EVN_TAG" in line for line in logs.output))

    def test_svx_tag_beats_a_leon_normal_value(self):
        # Matrix 2: SVX + LEON normal → YES, conflict, tag won.
        with self.assertLogs("backend.statistics.crew_hours.heavy", level="WARNING") as logs:
            decision = decide_heavy(False, True, "SVX_TAG")

        self.assertIs(decision.effective_heavy, True)
        self.assertEqual(decision.heavy_reason, "SVX_TAG")
        self.assertEqual(decision.heavy_source, "LOCAL_RULE")
        self.assertTrue(decision.heavy_conflict)
        self.assertTrue(any("SVX_TAG" in line for line in logs.output))

    def test_tag_with_agreeing_or_silent_leon_carries_no_conflict(self):
        cases = (
            (False, False, "EVN_TAG", False),
            (None, False, "EVN_TAG", False),
            (True, True, "SVX_TAG", True),
            (None, True, "SVX_TAG", True),
        )
        for leon, derived, reason, effective in cases:
            with self.subTest(leon=leon, reason=reason):
                decision = decide_heavy(leon, derived, reason)
                self.assertIs(decision.effective_heavy, effective)
                self.assertEqual(decision.heavy_source, "LOCAL_RULE")
                self.assertEqual(decision.heavy_reason, reason)
                self.assertFalse(decision.heavy_conflict)

    def test_evn_and_svx_together_evn_wins_end_to_end(self):
        # Matrix 3: the tags never co-fire; EVN wins at derivation and the
        # decision preserves that verdict even against a LEON YES.
        detail = derive_heavy_detail([_entry()] * 10, "B738", ("SVX", "EVN"))
        self.assertEqual(detail, (False, "EVN_TAG"))

        decision = decide_heavy(True, detail[0], detail[1])
        self.assertIs(decision.effective_heavy, False)
        self.assertEqual(decision.heavy_reason, "EVN_TAG")

    def test_without_a_tag_the_leon_first_table_is_unchanged(self):
        decision = decide_heavy(False, True, "EXTRA_COCKPIT_CREW")
        self.assertIs(decision.effective_heavy, False)
        self.assertEqual(decision.heavy_source, "LEON")
        self.assertTrue(decision.heavy_conflict)

        agreeing = decide_heavy(True, True, "EXTRA_CABIN_CREW")
        self.assertIs(agreeing.effective_heavy, True)
        self.assertEqual(agreeing.heavy_source, "LEON_AND_LOCAL")

    def _tagged_report_response(self, tag: str, leon_value: bool):
        report = OfficialMcpReport(
            {"C1": "01:30"},
            [
                {
                    "scope_row_unique_id": "row-401",
                    "unique_id": 401,
                    "crew_codes": ["C1"],
                    "crew_names": ["Crew One"],
                    "crew_position_names": ["CPT"],
                    "acftType": "B738 - 737-800",
                    "blockTimeJourneyLog": "01:30",
                }
            ],
        )
        context = FlightContext(
            flight_nid=401,
            start_time_utc="2026-06-01T06:00:00Z",
            end_time_utc="2026-06-01T09:00:00Z",
            flight_tags=(tag,),
            entries=(_entry(crew_code="C1"),),
        )
        return _build_mcp_report_response(
            report,
            from_date="2026-06-01",
            to_date="2026-06-30",
            position="All",
            crew_member=None,
            augmented_index=AugmentedIndex(
                available=True,
                by_crew_sector={("C1", 401): leon_value},
                resolved_count=1,
                ambiguous_count=0,
                raw_by_crew_sector={("C1", 401): "augmented" if leon_value else "normal"},
            ),
            crew_context_index=CrewContextIndex(
                available=True,
                by_flight={401: context.entries},
                contexts={401: context},
            ),
        )

    def test_evn_tag_overrides_leon_augmented_in_the_report(self):
        response = self._tagged_report_response("EVN", leon_value=True)

        flight = response.crew_members[0].flights[0]
        self.assertIs(flight.augmented_heavy, False)
        self.assertIs(flight.effective_heavy, False)
        self.assertEqual(flight.heavy_reason, "EVN_TAG")
        self.assertEqual(flight.heavy_source, "LOCAL_RULE")
        self.assertTrue(flight.heavy_conflict)
        self.assertIs(flight.leon_heavy, True)

    def test_svx_tag_overrides_leon_normal_in_the_report(self):
        response = self._tagged_report_response("SVX", leon_value=False)

        flight = response.crew_members[0].flights[0]
        self.assertIs(flight.augmented_heavy, True)
        self.assertEqual(flight.heavy_reason, "SVX_TAG")
        self.assertEqual(flight.heavy_source, "LOCAL_RULE")
        self.assertTrue(flight.heavy_conflict)
        self.assertIs(flight.leon_heavy, False)


def _representative_report() -> OfficialMcpReport:
    return OfficialMcpReport(
        {"C1": "01:30", "C2": "01:30", "C3": "01:30"},
        [
            {
                "scope_row_unique_id": "row-101",
                "unique_id": 101,
                "crew_codes": ["C1", "C2"],
                "crew_names": ["Crew One", "Crew Two"],
                "crew_position_names": ["CPT", "FO"],
                "acftType": "B738 - 737-800",
                "blockTimeJourneyLog": "01:30",
            },
            {
                "scope_row_unique_id": "row-102",
                "unique_id": 102,
                "crew_codes": ["C3"],
                "crew_names": ["Crew Three"],
                "crew_position_names": ["CPT"],
                "acftType": "B738 - 737-800",
                "blockTimeJourneyLog": "01:30",
            },
        ],
    )


def _representative_context() -> CrewContextIndex:
    return CrewContextIndex(
        available=True,
        by_flight={
            # Five operating cockpit crew: over the threshold, so the local rule fires too.
            101: (_entry(), _entry(), _entry(), _entry(), _entry()),
            102: (_entry(), _entry()),
        },
    )


def _flight_context(
    flight_nid: int,
    start: str,
    end: str,
    crew_codes: tuple[str, ...],
    flight_tags: tuple[str, ...] = (),
    *,
    adep: str | None = "HRG",
    ades: str | None = "XYZ",
) -> FlightContext:
    entries = tuple(
        _entry(position="CPT", crew_code=code) for code in crew_codes
    )
    return FlightContext(
        flight_nid=flight_nid,
        start_time_utc=start,
        end_time_utc=end,
        flight_tags=flight_tags,
        entries=entries,
        departure_airport=adep,
        arrival_airport=ades,
    )


class TestHeavyServiceIntegration(unittest.TestCase):
    def test_effective_heavy_always_equals_leon_and_augmented_value_is_unchanged(self):
        report = _representative_report()
        augmented = AugmentedIndex(
            available=True,
            by_crew_sector={("C1", 101): True, ("C2", 101): False},
            resolved_count=2,
            ambiguous_count=0,
            raw_by_crew_sector={("C1", 101): "augmented", ("C2", 101): "normal"},
        )
        enabled = _build_mcp_report_response(
            report,
            from_date="2026-06-01",
            to_date="2026-06-30",
            position="All",
            crew_member=None,
            augmented_index=augmented,
            crew_context_index=_representative_context(),
        )
        disabled = _build_mcp_report_response(
            report,
            from_date="2026-06-01",
            to_date="2026-06-30",
            position="All",
            crew_member=None,
            augmented_index=augmented,
            crew_context_index=CrewContextIndex(False, {}),
        )

        enabled_flights = [
            flight
            for member in enabled.crew_members
            for flight in member.flights
        ]
        disabled_flights = [
            flight
            for member in disabled.crew_members
            for flight in member.flights
        ]
        self.assertTrue(enabled_flights)
        for flight in enabled_flights:
            if flight.leon_heavy is not None:
                self.assertIs(flight.effective_heavy, flight.leon_heavy)
        self.assertEqual(
            [flight.augmented_heavy for flight in enabled_flights],
            [flight.augmented_heavy for flight in disabled_flights],
        )
        # STEP 4 turns the unresolvable UNKNOWN into a No; LEON's own values are untouched.
        self.assertEqual(
            [flight.augmented_heavy for flight in enabled_flights],
            [True, False, False],
        )
        c1_flight = enabled.crew_members[0].flights[0]
        self.assertEqual(c1_flight.leon_augmentation, "augmented")
        self.assertEqual(c1_flight.heavy_source, "LEON_AND_LOCAL")
        self.assertEqual(c1_flight.heavy_reason, "MULTIPLE_RULES")
        c2_flight = next(
            flight
            for member in enabled.crew_members
            for flight in member.flights
            if flight.leon_heavy is False
        )
        self.assertTrue(c2_flight.heavy_conflict)

    def test_service_fetches_each_enrichment_index_once(self):
        class FakeClient:
            def __init__(self):
                self.augmented_calls = 0
                self.context_calls = 0

            def fetch_official_totals(self, from_date, to_date):
                return _representative_report()

            def fetch_augmented_index(self, from_date, to_date):
                self.augmented_calls += 1
                return AugmentedIndex(False, {}, 0, 0)

            def fetch_crew_context_index(self, from_date, to_date):
                self.context_calls += 1
                return _representative_context()

        client = FakeClient()
        response = LiveCrewHoursService(client).get_crew_hours_report(
            "2026-06-01", "2026-06-30"
        )

        self.assertEqual(client.augmented_calls, 1)
        self.assertEqual(client.context_calls, 1)
        self.assertTrue(response.crew_members)


def _unknown_index(*contexts: FlightContext) -> CrewContextIndex:
    return CrewContextIndex(
        available=True,
        by_flight={context.flight_nid: context.entries for context in contexts},
        contexts={context.flight_nid: context for context in contexts},
    )


class TestUnknownResolution(unittest.TestCase):
    def _resolve(self, index: CrewContextIndex, flight_nid: int, crew_code: str):
        return resolve_unknown_heavy(
            index,
            build_rotation_index(index),
            flight_nid,
            crew_code,
        )

    def test_same_day_short_break_and_same_crew_is_yes(self):
        index = _unknown_index(
            _flight_context(201, "2026-06-01T06:00:00Z", "2026-06-01T09:00:00Z", ("C1", "C2")),
            _flight_context(
                202, "2026-06-01T12:00:00Z", "2026-06-01T15:00:00Z", ("C1", "C2"),
                adep="XYZ", ades="HRG",
            ),
        )

        resolution = self._resolve(index, 201, "C1")

        self.assertTrue(resolution.effective_heavy)
        self.assertTrue(resolution.resolved)
        self.assertEqual(resolution.reason, "SAME_DAY_SHORT_BREAK_SAME_CREW")

    def test_break_longer_than_four_hours_is_no(self):
        index = _unknown_index(
            _flight_context(201, "2026-06-01T06:00:00Z", "2026-06-01T09:00:00Z", ("C1", "C2")),
            _flight_context(
                202, "2026-06-01T14:00:00Z", "2026-06-01T17:00:00Z", ("C1", "C2"),
                adep="XYZ", ades="HRG",
            ),
        )

        resolution = self._resolve(index, 201, "C1")

        self.assertFalse(resolution.effective_heavy)
        self.assertEqual(resolution.reason, "BREAK_EXCEEDS_LIMIT")

    def test_midnight_crossing_rotation_with_short_break_is_yes(self):
        # The 2026-08-09 parity report: a duty is anchored on its first leg's
        # UTC date and may roll past midnight; the old calendar-date equality
        # check wrongly resolved this out-and-back as DIFFERENT_DAY.
        index = _unknown_index(
            _flight_context(201, "2026-06-01T22:00:00Z", "2026-06-01T23:00:00Z", ("C1", "C2")),
            _flight_context(
                202, "2026-06-02T01:00:00Z", "2026-06-02T03:00:00Z", ("C1", "C2"),
                adep="XYZ", ades="HRG",
            ),
        )

        resolution = self._resolve(index, 201, "C1")

        self.assertTrue(resolution.effective_heavy)
        self.assertEqual(resolution.reason, "SAME_DAY_SHORT_BREAK_SAME_CREW")

    def test_changed_crew_set_is_no(self):
        index = _unknown_index(
            _flight_context(201, "2026-06-01T06:00:00Z", "2026-06-01T09:00:00Z", ("C1", "C2")),
            _flight_context(
                202, "2026-06-01T12:00:00Z", "2026-06-01T15:00:00Z", ("C1", "C3"),
                adep="XYZ", ades="HRG",
            ),
        )

        resolution = self._resolve(index, 201, "C1")

        self.assertFalse(resolution.effective_heavy)
        self.assertEqual(resolution.reason, "CREW_SET_CHANGED")

    def test_unknown_position_is_no(self):
        context = FlightContext(
            flight_nid=201,
            start_time_utc="2026-06-01T06:00:00Z",
            end_time_utc="2026-06-01T09:00:00Z",
            flight_tags=(),
            entries=(_entry(position=None, function=None, crew_code="C1"),),
        )
        index = _unknown_index(context)

        resolution = self._resolve(index, 201, "C1")

        self.assertFalse(resolution.effective_heavy)
        self.assertEqual(resolution.reason, "UNKNOWN_POSITION")

    def test_lone_flight_has_no_neighbour(self):
        index = _unknown_index(
            _flight_context(201, "2026-06-01T06:00:00Z", "2026-06-01T09:00:00Z", ("C1",)),
        )

        resolution = self._resolve(index, 201, "C1")

        self.assertFalse(resolution.effective_heavy)
        self.assertEqual(resolution.reason, "NO_NEIGHBOUR_FLIGHT")

    def test_unavailable_augmented_index_leaves_the_flight_unknown(self):
        report = OfficialMcpReport(
            {"C1": "01:30"},
            [
                {
                    "scope_row_unique_id": "row-201",
                    "unique_id": 201,
                    "crew_codes": ["C1"],
                    "crew_names": ["Crew One"],
                    "crew_position_names": ["CPT"],
                    "acftType": "B738 - 737-800",
                    "blockTimeJourneyLog": "01:30",
                }
            ],
        )

        response = _build_mcp_report_response(
            report,
            from_date="2026-06-01",
            to_date="2026-06-30",
            position="All",
            crew_member=None,
            augmented_index=AugmentedIndex(False, {}, 0, 0),
            crew_context_index=_unknown_index(
                _flight_context(201, "2026-06-01T06:00:00Z", "2026-06-01T09:00:00Z", ("C1",)),
            ),
        )

        flight = response.crew_members[0].flights[0]
        self.assertIsNone(flight.augmented_heavy)
        self.assertFalse(flight.unknown_resolved)

    def test_service_resolves_unknown_flights_end_to_end(self):
        report = OfficialMcpReport(
            {"C1": "03:00"},
            [
                {
                    "scope_row_unique_id": "row-201",
                    "unique_id": 201,
                    "crew_codes": ["C1"],
                    "crew_names": ["Crew One"],
                    "crew_position_names": ["CPT"],
                    "acftType": "B738 - 737-800",
                    "blockTimeJourneyLog": "01:30",
                },
                {
                    "scope_row_unique_id": "row-202",
                    "unique_id": 202,
                    "crew_codes": ["C1"],
                    "crew_names": ["Crew One"],
                    "crew_position_names": ["CPT"],
                    "acftType": "B738 - 737-800",
                    "blockTimeJourneyLog": "01:30",
                },
            ],
        )

        response = _build_mcp_report_response(
            report,
            from_date="2026-06-01",
            to_date="2026-06-30",
            position="All",
            crew_member=None,
            # Available index, but neither sector carries a value for C1.
            augmented_index=AugmentedIndex(True, {}, 0, 0, {}),
            crew_context_index=_unknown_index(
                _flight_context(201, "2026-06-01T06:00:00Z", "2026-06-01T09:00:00Z", ("C1",)),
                _flight_context(
                    202, "2026-06-01T12:00:00Z", "2026-06-01T15:00:00Z", ("C1",),
                    adep="XYZ", ades="HRG",
                ),
            ),
        )

        flights = response.crew_members[0].flights
        self.assertEqual([flight.augmented_heavy for flight in flights], [True, True])
        for flight in flights:
            self.assertTrue(flight.unknown_resolved)
            self.assertEqual(flight.heavy_source, "LOCAL_RULE")
            self.assertEqual(
                flight.unknown_resolution_reason,
                "SAME_DAY_SHORT_BREAK_SAME_CREW",
            )

    def test_evn_tag_resolves_without_step_four(self):
        report = OfficialMcpReport(
            {"C1": "01:30"},
            [
                {
                    "scope_row_unique_id": "row-201",
                    "unique_id": 201,
                    "crew_codes": ["C1"],
                    "crew_names": ["Crew One"],
                    "crew_position_names": ["CPT"],
                    "acftType": "B738 - 737-800",
                    "blockTimeJourneyLog": "01:30",
                }
            ],
        )

        response = _build_mcp_report_response(
            report,
            from_date="2026-06-01",
            to_date="2026-06-30",
            position="All",
            crew_member=None,
            augmented_index=AugmentedIndex(True, {}, 0, 0, {}),
            crew_context_index=_unknown_index(
                _flight_context(
                    201,
                    "2026-06-01T06:00:00Z",
                    "2026-06-01T09:00:00Z",
                    ("C1",),
                    flight_tags=("EVN",),
                ),
            ),
        )

        flight = response.crew_members[0].flights[0]
        self.assertIs(flight.augmented_heavy, False)
        self.assertEqual(flight.heavy_reason, "EVN_TAG")
        self.assertFalse(flight.unknown_resolved)


class TestClassifyFlightHeavy(unittest.TestCase):
    """The single flight-level engine every surface calls (ruling 2026-08-17)."""

    def _index(self, *contexts):
        return _unknown_index(*contexts)

    def test_evn_vetoes_a_cockpit_count_yes(self):
        # Ruling Q2: EVN/SVX are flight-level absolutes.
        from backend.statistics.crew_hours.heavy import classify_flight_heavy
        from backend.statistics.crew_hours.unknown_resolver import build_rotation_index

        context = FlightContext(
            flight_nid=901,
            start_time_utc="2026-06-20T22:05:00Z",
            end_time_utc="2026-06-21T01:00:00Z",
            flight_tags=(),
            entries=(_entry(crew_code="C1"), _entry(crew_code="C2"), _entry(crew_code="C3")),
            departure_airport="SSH",
            arrival_airport="EVN",
        )
        index = self._index(context)

        verdict, reason = classify_flight_heavy(index, build_rotation_index(index), 901)

        self.assertIs(verdict, False)
        self.assertEqual(reason, "EVN_AIRPORT")

    def test_rule_4_count_finalizes_when_leon_is_silent(self):
        # Rule 4: an over-threshold operating count is final — it never falls
        # to the resolver (rule 5 covers only the count rule's UNKNOWN).
        from backend.statistics.crew_hours.heavy import classify_flight_heavy
        from backend.statistics.crew_hours.unknown_resolver import build_rotation_index

        context = FlightContext(
            flight_nid=902,
            start_time_utc=None,  # even without times: count decides, no STEP 4
            end_time_utc=None,
            flight_tags=(),
            entries=(_entry(crew_code="C1"), _entry(crew_code="C2"), _entry(crew_code="C3")),
            departure_airport="SSH",
            arrival_airport="HRG",
        )
        index = self._index(context)

        verdict, reason = classify_flight_heavy(index, build_rotation_index(index), 902)

        self.assertIs(verdict, True)
        self.assertEqual(reason, "EXTRA_COCKPIT_CREW")

    def test_step_four_fires_for_any_operating_member(self):
        from backend.statistics.crew_hours.heavy import classify_flight_heavy
        from backend.statistics.crew_hours.unknown_resolver import build_rotation_index

        index = self._index(
            _flight_context(903, "2026-06-22T15:00:00Z", "2026-06-22T21:00:00Z", ("C1", "C2")),
            _flight_context(
                904, "2026-06-22T22:00:00Z", "2026-06-23T03:50:00Z", ("C1", "C2"),
                adep="XYZ", ades="HRG",
            ),
        )

        verdict, reason = classify_flight_heavy(index, build_rotation_index(index), 903)

        self.assertIs(verdict, True)
        self.assertEqual(reason, "SAME_DAY_SHORT_BREAK_SAME_CREW")

    def test_no_context_is_indeterminate_and_all_positioning_is_no(self):
        from backend.statistics.crew_hours.heavy import classify_flight_heavy
        from backend.statistics.crew_hours.unknown_resolver import build_rotation_index

        empty = self._index()
        self.assertEqual(
            classify_flight_heavy(empty, build_rotation_index(empty), 999),
            (None, "UNKNOWN"),
        )

        riders_only = FlightContext(
            flight_nid=905,
            start_time_utc="2026-06-25T08:00:00Z",
            end_time_utc="2026-06-25T11:00:00Z",
            flight_tags=(),
            entries=(_entry(position="PAD", crew_code="P1"), _entry(position="PSN", crew_code="P2")),
            departure_airport="HRG",
            arrival_airport="SSH",
        )
        index = self._index(riders_only)
        self.assertEqual(
            classify_flight_heavy(index, build_rotation_index(index), 905),
            (False, "NONE"),
        )


class TestOwnerRulings20260817(unittest.TestCase):
    """Q1/Q3 pins: trainee = Function=='SFA' only; no SP/OPS cabin rule."""

    def test_missing_function_never_excludes_a_cabin_member(self):
        # Q1: no Position-only fallback — SFA as a POSITION is a normal senior
        # cabin rank, so five operating cabin including position-SFA is Heavy.
        entries = [
            _entry(pos_type="CABIN", position="FA1"),
            _entry(pos_type="CABIN", position="FA2"),
            _entry(pos_type="CABIN", position="FA3"),
            _entry(pos_type="CABIN", position="FA4"),
            _entry(pos_type="CABIN", position="SFA", function=None),
        ]
        self.assertEqual(operating_cabin_count(entries), 5)
        self.assertEqual(derive_heavy_detail(entries, "B738"), (True, "EXTRA_CABIN_CREW"))

    def test_sfa_position_with_a_non_sfa_function_still_counts(self):
        entries = [
            _entry(pos_type="CABIN", position="SFA", function="CCM"),
        ] + [_entry(pos_type="CABIN", position=f"FA{i}") for i in range(1, 5)]
        self.assertEqual(operating_cabin_count(entries), 5)

    def test_no_sp_ops_cabin_exclusion_exists(self):
        # Q3: OPS/SP are cockpit trainee slots; there is no approved cabin
        # rule using them — a cabin-typed SP/OPS member counts as operating.
        entries = [
            _entry(pos_type="CABIN", position="SP"),
            _entry(pos_type="CABIN", position="OPS"),
        ] + [_entry(pos_type="CABIN", position=f"FA{i}") for i in range(1, 4)]
        self.assertEqual(operating_cabin_count(entries), 5)


class TestCabinTraineeDetectionMetadata(unittest.TestCase):
    """Q1: when LEON withholds Function, the report says so — never implies
    trainees were excluded when they were not."""

    def _response(self, crew_context_index):
        return _build_mcp_report_response(
            _representative_report(),
            from_date="2026-06-01",
            to_date="2026-06-30",
            position="All",
            crew_member=None,
            augmented_index=AugmentedIndex(True, {}, 0, 0, {}),
            crew_context_index=crew_context_index,
        )

    def test_unavailable_when_leon_rejects_the_function_selection(self):
        index = CrewContextIndex(
            available=True, by_flight={}, contexts={}, crew_function_available=False
        )
        self.assertEqual(self._response(index).cabin_trainee_detection, "unavailable")

    def test_unavailable_when_the_context_index_is_missing_entirely(self):
        self.assertEqual(
            self._response(CrewContextIndex(False, {})).cabin_trainee_detection,
            "unavailable",
        )

    def test_active_when_function_data_was_supplied(self):
        self.assertEqual(
            self._response(_representative_context()).cabin_trainee_detection,
            "active",
        )

    def test_rule_4_count_yes_is_final_in_the_report_and_carries_no_badge(self):
        # LEON silent + over-threshold count: YES via LOCAL_RULE, resolver
        # never consulted, no unknown_resolved badge fields.
        report = OfficialMcpReport(
            {"C1": "01:30"},
            [{
                "scope_row_unique_id": "row-902",
                "unique_id": 902,
                "crew_codes": ["C1"],
                "crew_names": ["Crew One"],
                "crew_position_names": ["CPT"],
                "acftType": "B738 - 737-800",
                "blockTimeJourneyLog": "01:30",
            }],
        )
        context = FlightContext(
            flight_nid=902,
            start_time_utc="2026-06-25T08:00:00Z",
            end_time_utc="2026-06-25T11:00:00Z",
            flight_tags=(),
            entries=(_entry(crew_code="C1"), _entry(crew_code="C2"), _entry(crew_code="C3")),
            departure_airport="SSH",
            arrival_airport="HRG",
        )
        response = _build_mcp_report_response(
            report,
            from_date="2026-06-01",
            to_date="2026-06-30",
            position="All",
            crew_member=None,
            augmented_index=AugmentedIndex(True, {}, 0, 0, {}),
            crew_context_index=_unknown_index(context),
        )

        flight = response.crew_members[0].flights[0]
        self.assertIs(flight.augmented_heavy, True)
        self.assertEqual(flight.heavy_source, "LOCAL_RULE")
        self.assertEqual(flight.heavy_reason, "EXTRA_COCKPIT_CREW")
        self.assertFalse(flight.unknown_resolved)


class TestJoinHealth(unittest.TestCase):
    """The report must expose, never hide, an ID-mismatch across LEON sources."""

    def test_mismatched_join_keys_flag_degraded_health(self):
        # Matrix 11: both indices are non-empty but keyed by IDs that never
        # match the report rows — the "IDs don't match" signature.
        report = _representative_report()
        augmented = AugmentedIndex(
            available=True,
            by_crew_sector={("C1", 999_101): True, ("C2", 999_101): False},
            resolved_count=2,
            ambiguous_count=0,
            raw_by_crew_sector={("C1", 999_101): "augmented"},
        )
        mismatched_context = _unknown_index(
            _flight_context(888_101, "2026-06-01T06:00:00Z", "2026-06-01T09:00:00Z", ("C1", "C2")),
        )

        with self.assertLogs("backend.statistics.crew_hours.service", level="WARNING") as logs:
            response = _build_mcp_report_response(
                report,
                from_date="2026-06-01",
                to_date="2026-06-30",
                position="All",
                crew_member=None,
                augmented_index=augmented,
                crew_context_index=mismatched_context,
            )

        self.assertEqual(response.join_health, "DEGRADED")
        self.assertEqual(response.augmented_lookup_attempts, 3)
        self.assertEqual(response.augmented_lookup_hits, 0)
        self.assertEqual(response.crew_context_attempts, 3)
        self.assertEqual(response.crew_context_hits, 0)
        self.assertTrue(any("join" in line.lower() for line in logs.output))

        # Every row falls to STEP 4 with no context and resolves NO — visible
        # as a degraded join, never as a silently all-No report.
        flights = [
            flight for member in response.crew_members for flight in member.flights
        ]
        self.assertTrue(flights)
        for flight in flights:
            self.assertIs(flight.augmented_heavy, False)

    def test_matching_join_keys_report_ok(self):
        response = _build_mcp_report_response(
            _representative_report(),
            from_date="2026-06-01",
            to_date="2026-06-30",
            position="All",
            crew_member=None,
            augmented_index=AugmentedIndex(
                available=True,
                by_crew_sector={("C1", 101): True, ("C2", 101): False},
                resolved_count=2,
                ambiguous_count=0,
                raw_by_crew_sector={},
            ),
            crew_context_index=_representative_context(),
        )

        self.assertEqual(response.join_health, "OK")
        self.assertEqual(response.augmented_lookup_attempts, 3)
        self.assertEqual(response.augmented_lookup_hits, 2)
        self.assertEqual(response.crew_context_attempts, 3)
        self.assertEqual(response.crew_context_hits, 3)

    def test_empty_indices_are_not_reported_as_degraded(self):
        # An empty index is "LEON returned nothing", not an ID mismatch.
        response = _build_mcp_report_response(
            _representative_report(),
            from_date="2026-06-01",
            to_date="2026-06-30",
            position="All",
            crew_member=None,
            augmented_index=AugmentedIndex(True, {}, 0, 0, {}),
            crew_context_index=CrewContextIndex(True, {}, {}),
        )

        self.assertEqual(response.join_health, "OK")
        self.assertEqual(response.augmented_lookup_hits, 0)

    def test_unavailable_indices_do_not_count_attempts(self):
        response = _build_mcp_report_response(
            _representative_report(),
            from_date="2026-06-01",
            to_date="2026-06-30",
            position="All",
            crew_member=None,
            augmented_index=AugmentedIndex(False, {}, 0, 0),
            crew_context_index=CrewContextIndex(False, {}),
        )

        self.assertEqual(response.join_health, "OK")
        self.assertEqual(response.augmented_lookup_attempts, 0)
        self.assertEqual(response.crew_context_attempts, 0)


if __name__ == "__main__":
    unittest.main()

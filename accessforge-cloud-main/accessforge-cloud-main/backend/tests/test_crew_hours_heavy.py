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
            _flight_context(202, "2026-06-01T12:00:00Z", "2026-06-01T15:00:00Z", ("C1", "C2")),
        )

        resolution = self._resolve(index, 201, "C1")

        self.assertTrue(resolution.effective_heavy)
        self.assertTrue(resolution.resolved)
        self.assertEqual(resolution.reason, "SAME_DAY_SHORT_BREAK_SAME_CREW")

    def test_break_longer_than_four_hours_is_no(self):
        index = _unknown_index(
            _flight_context(201, "2026-06-01T06:00:00Z", "2026-06-01T09:00:00Z", ("C1", "C2")),
            _flight_context(202, "2026-06-01T14:00:00Z", "2026-06-01T17:00:00Z", ("C1", "C2")),
        )

        resolution = self._resolve(index, 201, "C1")

        self.assertFalse(resolution.effective_heavy)
        self.assertEqual(resolution.reason, "BREAK_EXCEEDS_LIMIT")

    def test_different_utc_day_is_no_even_with_a_short_break(self):
        index = _unknown_index(
            _flight_context(201, "2026-06-01T22:00:00Z", "2026-06-01T23:00:00Z", ("C1", "C2")),
            _flight_context(202, "2026-06-02T01:00:00Z", "2026-06-02T03:00:00Z", ("C1", "C2")),
        )

        resolution = self._resolve(index, 201, "C1")

        self.assertFalse(resolution.effective_heavy)
        self.assertEqual(resolution.reason, "DIFFERENT_DAY")

    def test_changed_crew_set_is_no(self):
        index = _unknown_index(
            _flight_context(201, "2026-06-01T06:00:00Z", "2026-06-01T09:00:00Z", ("C1", "C2")),
            _flight_context(202, "2026-06-01T12:00:00Z", "2026-06-01T15:00:00Z", ("C1", "C3")),
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
                _flight_context(202, "2026-06-01T12:00:00Z", "2026-06-01T15:00:00Z", ("C1",)),
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


if __name__ == "__main__":
    unittest.main()

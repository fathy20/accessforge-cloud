import unittest
from datetime import datetime, timedelta, timezone

from backend.statistics.crew_hours.cabin_heavy import (
    FUNCTION_UNAVAILABLE_NOTE,
    AdjacentLeg,
    CabinCrewMember,
    CabinFlight,
    classify_cabin_augmented_heavy,
    classify_cockpit_heavy,
)
from backend.statistics.crew_hours.crew_context import CrewContextEntry
from backend.statistics.crew_hours.heavy import derive_heavy_detail
from backend.statistics.crew_hours.positions import (
    HEAVY_CABIN_THRESHOLD,
    HEAVY_COCKPIT_THRESHOLD,
)

DAY = datetime(2026, 6, 2, tzinfo=timezone.utc)


def _cabin(count, position="FA1", function=None, prefix="C"):
    return [
        CabinCrewMember(crew_code=f"{prefix}{i}", position=position, function=function)
        for i in range(count)
    ]


def _flight(**overrides):
    base = dict(
        adep="SSH",
        ades="VKO",
        start_time_utc=DAY.replace(hour=6),
        end_time_utc=DAY.replace(hour=9),
        aircraft_registration="SURSA",
    )
    base.update(overrides)
    return CabinFlight(**base)


class TestAirportOverrides(unittest.TestCase):
    def test_svx_forces_heavy_regardless_of_cabin_count(self):
        for adep, ades in (("SVX", "VKO"), ("VKO", "svx ")):
            for crew in ([], _cabin(1), _cabin(9)):
                heavy, reason = classify_cabin_augmented_heavy(
                    _flight(adep=adep, ades=ades), crew
                )
                self.assertTrue(heavy)
                self.assertIn("SVX override", reason)

    def test_evn_forces_not_heavy_regardless_of_cabin_count(self):
        for adep, ades in (("EVN", "VKO"), ("VKO", "evn")):
            for crew in ([], _cabin(1), _cabin(9)):
                heavy, reason = classify_cabin_augmented_heavy(
                    _flight(adep=adep, ades=ades), crew
                )
                self.assertFalse(heavy)
                self.assertIn("EVN override", reason)

    def test_overrides_short_circuit_before_the_count_rule(self):
        # 9 cabin would otherwise be Heavy; EVN must still win.
        heavy, reason = classify_cabin_augmented_heavy(
            _flight(adep="EVN"), _cabin(9)
        )
        self.assertFalse(heavy)
        self.assertNotIn("effective cabin count", reason)

        # 1 cabin would otherwise be Not Heavy; SVX must still win.
        heavy, reason = classify_cabin_augmented_heavy(_flight(ades="SVX"), _cabin(1))
        self.assertTrue(heavy)
        self.assertNotIn("effective cabin count", reason)


class TestExclusionsAndThreshold(unittest.TestCase):
    def test_sp_and_ops_are_excluded_from_the_count(self):
        crew = _cabin(3) + [
            CabinCrewMember("X1", "OPS"),
            CabinCrewMember("X2", "SP"),
        ]

        heavy, reason = classify_cabin_augmented_heavy(_flight(), crew)

        self.assertFalse(heavy)
        self.assertIn("effective cabin count = 3", reason)

    def test_threshold_boundary_four_no_five_yes(self):
        heavy, reason = classify_cabin_augmented_heavy(
            _flight(), _cabin(HEAVY_CABIN_THRESHOLD)
        )
        self.assertFalse(heavy)
        self.assertIn(f"= {HEAVY_CABIN_THRESHOLD} <= {HEAVY_CABIN_THRESHOLD}", reason)

        heavy, reason = classify_cabin_augmented_heavy(
            _flight(), _cabin(HEAVY_CABIN_THRESHOLD + 1)
        )
        self.assertTrue(heavy)
        self.assertIn(f"= {HEAVY_CABIN_THRESHOLD + 1} > {HEAVY_CABIN_THRESHOLD}", reason)


class TestTraineeHandling(unittest.TestCase):
    def test_missing_function_is_flagged_never_silently_assumed(self):
        crew = _cabin(3) + [CabinCrewMember("S1", "SFA", function=None)]

        heavy, reason = classify_cabin_augmented_heavy(_flight(), crew)

        # SFA is still counted — a missing Function is not evidence of anything.
        self.assertIn("effective cabin count = 4", reason)
        self.assertIn(FUNCTION_UNAVAILABLE_NOTE, reason)
        self.assertFalse(heavy)

    def test_confirmed_trainee_is_excluded_when_function_is_supplied(self):
        crew = _cabin(4) + [
            CabinCrewMember("S1", "SFA", function="TRN"),
            CabinCrewMember("S2", "SFA", function="TRN"),
        ]

        heavy, reason = classify_cabin_augmented_heavy(_flight(), crew)

        self.assertIn("effective cabin count = 4", reason)
        self.assertNotIn(FUNCTION_UNAVAILABLE_NOTE, reason)
        self.assertFalse(heavy)

    def test_sfa_with_a_non_trn_function_still_counts(self):
        crew = _cabin(4) + [CabinCrewMember("S1", "SFA", function="CABIN")]

        heavy, reason = classify_cabin_augmented_heavy(_flight(), crew)

        self.assertTrue(heavy)
        self.assertIn("effective cabin count = 5", reason)


class TestUnknownPairing(unittest.TestCase):
    def _unknown(self, leg_start_hour, leg_crew, day_offset=0):
        crew = _cabin(2)
        leg_start = DAY.replace(hour=0) + timedelta(days=day_offset, hours=leg_start_hour)
        return classify_cabin_augmented_heavy(
            _flight(
                is_unknown=True,
                adjacent_legs=(
                    AdjacentLeg(
                        start_time_utc=leg_start,
                        end_time_utc=leg_start + timedelta(hours=2),
                        cabin_crew=leg_crew,
                    ),
                ),
            ),
            crew,
        )

    def test_same_crew_same_day_break_within_four_hours_is_heavy(self):
        # flight ends 09:00; leg starts 12:54 -> 3.9h
        heavy, reason = self._unknown(12.9, _cabin(2))
        self.assertTrue(heavy)
        self.assertIn("gap=3.9h", reason)
        self.assertIn("same crew", reason)

    def test_same_crew_same_day_break_over_four_hours_is_not_heavy(self):
        heavy, reason = self._unknown(13.1, _cabin(2))
        self.assertFalse(heavy)
        self.assertIn("> 4h", reason)

    def test_same_crew_different_utc_day_is_not_heavy_even_with_short_break(self):
        # Leg starts 00:30 the next day: break well under 4h, but a different day.
        heavy, reason = classify_cabin_augmented_heavy(
            _flight(
                is_unknown=True,
                start_time_utc=DAY.replace(hour=21),
                end_time_utc=DAY.replace(hour=23),
                adjacent_legs=(
                    AdjacentLeg(
                        start_time_utc=DAY.replace(hour=0) + timedelta(days=1, minutes=30),
                        end_time_utc=DAY.replace(hour=0) + timedelta(days=1, hours=2),
                        cabin_crew=_cabin(2),
                    ),
                ),
            ),
            _cabin(2),
        )
        self.assertFalse(heavy)
        self.assertIn("different UTC day", reason)

    def test_different_crew_set_is_not_heavy(self):
        heavy, reason = self._unknown(10.0, _cabin(2, prefix="Z"))
        self.assertFalse(heavy)
        self.assertIn("different cabin crew set", reason)

    def test_no_adjacent_leg_is_not_heavy(self):
        heavy, reason = classify_cabin_augmented_heavy(
            _flight(is_unknown=True), _cabin(2)
        )
        self.assertFalse(heavy)
        self.assertIn("no adjacent leg", reason)

    def test_known_flight_never_enters_the_pairing_rule(self):
        heavy, reason = classify_cabin_augmented_heavy(
            _flight(is_unknown=False), _cabin(2)
        )
        self.assertFalse(heavy)
        self.assertNotIn("UNKNOWN", reason)


def _entry(pos_type="COCKPIT", position="FO", training_type=None):
    return CrewContextEntry(
        pos_type=pos_type, position=position, training_type=training_type
    )


class TestCockpitFrozen(unittest.TestCase):
    def test_threshold_boundary_matches_the_frozen_rule(self):
        standard = [_entry()] * HEAVY_COCKPIT_THRESHOLD
        self.assertEqual(classify_cockpit_heavy(_flight(), standard)[0], False)
        self.assertEqual(classify_cockpit_heavy(_flight(), [*standard, _entry()])[0], True)

    def test_no_svx_or_evn_override_is_applied_to_cockpit(self):
        standard = [_entry()] * HEAVY_COCKPIT_THRESHOLD
        # Airports must make no difference to the cockpit verdict at all.
        for adep, ades in (("SVX", "VKO"), ("EVN", "VKO"), ("SSH", "VKO")):
            self.assertEqual(
                classify_cockpit_heavy(_flight(adep=adep, ades=ades), standard)[0],
                False,
            )
            self.assertEqual(
                classify_cockpit_heavy(_flight(adep=adep, ades=ades), [*standard, _entry()])[0],
                True,
            )

    def test_regression_identical_to_the_previous_cockpit_path(self):
        """The split must not move a single cockpit verdict."""

        cases = [
            [],
            [_entry()],
            [_entry()] * 2,
            [_entry()] * 3,
            [_entry()] * 5,
            [_entry(), _entry(), _entry(position="OBS")],
            [_entry(), _entry(), _entry(training_type="LINE_TRAINING")],
            [_entry(), _entry(), _entry(position="OPS")],
            [_entry(pos_type="CABIN", position="FA1")] * 6,
        ]
        for entries in cases:
            with self.subTest(entries=len(entries)):
                # Previous behaviour, with tags absent exactly as in production.
                previous, _ = derive_heavy_detail(entries, "B738 - 737-800", None)
                cockpit_only = previous is True and _cockpit_was_the_cause(entries)
                new, _ = classify_cockpit_heavy(_flight(), entries)
                self.assertEqual(new, cockpit_only)


def _cockpit_was_the_cause(entries):
    from backend.statistics.crew_hours.heavy import operating_cockpit_count

    return operating_cockpit_count(entries) > HEAVY_COCKPIT_THRESHOLD


if __name__ == "__main__":
    unittest.main()

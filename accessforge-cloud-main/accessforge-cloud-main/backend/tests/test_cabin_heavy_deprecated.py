"""The deprecated cabin_heavy wrappers: warn loudly, delegate to the engine.

The old rule assertions migrated to test_crew_hours_heavy.py (airport rules,
thresholds, Q1/Q3 pins) and test_crew_hours_unknown_resolver.py (pairing);
the Copilot citation formats live in test_copilot_local_answers.py. This file
only guards the one-release compatibility shim.
"""

import unittest
import warnings

from backend.statistics.crew_hours.cabin_heavy import (
    CabinCrewMember,
    CabinFlight,
    classify_cabin_augmented_heavy,
    classify_cockpit_heavy,
)
from backend.statistics.crew_hours.crew_context import CrewContextEntry


def _cockpit(position="FO"):
    return CrewContextEntry(
        pos_type="COCKPIT", position=position, training_type=None, crew_code="C1"
    )


class TestDeprecatedWrappers(unittest.TestCase):
    def test_both_wrappers_emit_a_deprecation_warning(self):
        flight = CabinFlight(adep="SSH", ades="HRG")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            classify_cockpit_heavy(flight, [_cockpit()])
            classify_cabin_augmented_heavy(flight, [CabinCrewMember("A1", "FA1")])
        self.assertEqual(
            [w.category for w in caught], [DeprecationWarning, DeprecationWarning]
        )

    def test_wrappers_now_apply_the_flight_level_evn_veto(self):
        # Ruling Q2 propagates through the shim: EVN vetoes a count Yes.
        flight = CabinFlight(adep="SSH", ades="EVN")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            heavy, reason = classify_cockpit_heavy(
                flight, [_cockpit("CPT"), _cockpit("FO"), _cockpit("FO2")]
            )
        self.assertFalse(heavy)
        self.assertEqual(reason, "EVN_AIRPORT")

    def test_cabin_wrapper_uses_the_function_sfa_trainee_rule(self):
        # Ruling Q1: Function=='SFA' excludes; position alone never does.
        flight = CabinFlight(adep="SSH", ades="HRG")
        crew = [CabinCrewMember(f"A{i}", f"FA{i}") for i in range(1, 5)]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            heavy, _ = classify_cabin_augmented_heavy(
                flight, crew + [CabinCrewMember("A5", "SFA", function="SFA")]
            )
            still_heavy, _ = classify_cabin_augmented_heavy(
                flight, crew + [CabinCrewMember("A5", "SFA", function=None)]
            )
        self.assertFalse(heavy)        # function SFA → trainee excluded → 4 operating
        self.assertTrue(still_heavy)   # no function data → counts → 5 operating


if __name__ == "__main__":
    unittest.main()

"""STEP 4 UNKNOWN-resolver contract: the approved rotation rules.

Characterization tests for the 2026-08 rule set:

- ``PSN`` on the current leg is an immediate NO (never a rotation search).
- Rotation continuity: a neighbour must chain airports with the current leg.
- Break gate: ``0 <= break < 4h`` strictly — 3:59 connects, 4:00 does not.
- Midnight-safe duty window: the pair belongs to one duty anchored on the
  first sector's UTC start date; a short break across midnight is the SAME
  duty. ``DIFFERENT_DAY`` is reserved for genuinely disjoint days.
- Crew comparison uses operating members only (PSN excluded on both legs).

Fixtures are sanitized: crew codes and airports are synthetic, no LEON
envelopes, tokens, or raw payloads.
"""

import unittest

from backend.statistics.crew_hours.crew_context import (
    CrewContextEntry,
    CrewContextIndex,
    FlightContext,
    build_crew_context_index,
)
from backend.statistics.crew_hours.unknown_resolver import (
    build_rotation_index,
    resolve_unknown_heavy,
)


def _entry(
    crew_code: str,
    *,
    position: str | None = "CPT",
    function: str | None = None,
) -> CrewContextEntry:
    return CrewContextEntry(
        pos_type="COCKPIT",
        position=position,
        training_type=None,
        crew_code=crew_code,
        function=function,
    )


def _context(
    flight_nid: int,
    start: str,
    end: str,
    entries: tuple[CrewContextEntry, ...],
    *,
    adep: str | None = "HRG",
    ades: str | None = "XYZ",
) -> FlightContext:
    return FlightContext(
        flight_nid=flight_nid,
        start_time_utc=start,
        end_time_utc=end,
        flight_tags=(),
        entries=entries,
        departure_airport=adep,
        arrival_airport=ades,
    )


def _index(*contexts: FlightContext) -> CrewContextIndex:
    return CrewContextIndex(
        available=True,
        by_flight={context.flight_nid: context.entries for context in contexts},
        contexts={context.flight_nid: context for context in contexts},
    )


def _resolve(index: CrewContextIndex, flight_nid: int, crew_code: str):
    return resolve_unknown_heavy(
        index,
        build_rotation_index(index),
        flight_nid,
        crew_code,
    )


def _out_and_back(
    *,
    return_start: str = "2026-06-02T00:30:00Z",
    return_end: str = "2026-06-02T04:00:00Z",
    return_entries: tuple[CrewContextEntry, ...] | None = None,
    return_adep: str | None = "XYZ",
    return_ades: str | None = "HRG",
) -> CrewContextIndex:
    """Matrix scenario 7: HRG→XYZ late evening, XYZ→HRG after midnight."""

    crew = (_entry("C1"), _entry("C2", position="FO"))
    return _index(
        _context(
            301,
            "2026-06-01T20:00:00Z",
            "2026-06-01T23:30:00Z",
            crew,
            adep="HRG",
            ades="XYZ",
        ),
        _context(
            302,
            return_start,
            return_end,
            return_entries if return_entries is not None else crew,
            adep=return_adep,
            ades=return_ades,
        ),
    )


class TestPsnShortCircuit(unittest.TestCase):
    def test_psn_member_is_no_immediately_even_with_a_qualifying_neighbour(self):
        # The neighbour would qualify on every gate; PSN must never reach it.
        crew = (_entry("C1", position="PSN"), _entry("C2"))
        index = _index(
            _context(301, "2026-06-01T20:00:00Z", "2026-06-01T23:30:00Z", crew, adep="HRG", ades="XYZ"),
            _context(302, "2026-06-02T00:30:00Z", "2026-06-02T04:00:00Z", crew, adep="XYZ", ades="HRG"),
        )

        resolution = _resolve(index, 301, "C1")

        self.assertFalse(resolution.effective_heavy)
        self.assertTrue(resolution.resolved)
        self.assertEqual(resolution.reason, "PSN_POSITIONING")

    def test_psn_match_is_case_insensitive(self):
        crew = (_entry("C1", position=" psn "),)
        index = _index(_context(301, "2026-06-01T06:00:00Z", "2026-06-01T09:00:00Z", crew))

        resolution = _resolve(index, 301, "C1")

        self.assertEqual(resolution.reason, "PSN_POSITIONING")

    def test_member_with_no_position_or_function_stays_unknown_position(self):
        crew = (_entry("C1", position=None, function=None),)
        index = _index(_context(301, "2026-06-01T06:00:00Z", "2026-06-01T09:00:00Z", crew))

        resolution = _resolve(index, 301, "C1")

        self.assertFalse(resolution.effective_heavy)
        self.assertTrue(resolution.resolved)
        self.assertEqual(resolution.reason, "UNKNOWN_POSITION")


class TestMidnightSafeDutyWindow(unittest.TestCase):
    def test_out_and_back_across_midnight_with_short_break_is_yes(self):
        # Matrix 7: 20:00–23:30Z out, 00:30–04:00Z back next UTC date, break 1:00.
        resolution = _resolve(_out_and_back(), 301, "C1")

        self.assertTrue(resolution.effective_heavy)
        self.assertTrue(resolution.resolved)
        self.assertEqual(resolution.reason, "SAME_DAY_SHORT_BREAK_SAME_CREW")

    def test_break_of_exactly_four_hours_is_no(self):
        # Matrix 8: 4:00 must NOT connect — strictly below four hours.
        index = _out_and_back(
            return_start="2026-06-02T03:30:00Z",
            return_end="2026-06-02T07:00:00Z",
        )

        resolution = _resolve(index, 301, "C1")

        self.assertFalse(resolution.effective_heavy)
        self.assertEqual(resolution.reason, "BREAK_EXCEEDS_LIMIT")

    def test_break_of_three_fifty_nine_still_connects(self):
        index = _out_and_back(
            return_start="2026-06-02T03:29:00Z",
            return_end="2026-06-02T07:00:00Z",
        )

        resolution = _resolve(index, 301, "C1")

        self.assertTrue(resolution.effective_heavy)
        self.assertEqual(resolution.reason, "SAME_DAY_SHORT_BREAK_SAME_CREW")

    def test_genuinely_disjoint_days_report_different_day(self):
        # Two days later: no duty window can span this, whatever the airports.
        index = _out_and_back(
            return_start="2026-06-03T20:00:00Z",
            return_end="2026-06-03T23:00:00Z",
        )

        resolution = _resolve(index, 301, "C1")

        self.assertFalse(resolution.effective_heavy)
        self.assertEqual(resolution.reason, "DIFFERENT_DAY")


class TestOperatingCrewComparison(unittest.TestCase):
    def test_extra_psn_passenger_on_the_return_leg_does_not_break_the_match(self):
        # Matrix 9: the operating sets match; the PSN rider must be invisible.
        crew = (_entry("C1"), _entry("C2", position="FO"))
        index = _out_and_back(
            return_entries=(*crew, _entry("C9", position="PSN")),
        )

        resolution = _resolve(index, 301, "C1")

        self.assertTrue(resolution.effective_heavy)
        self.assertEqual(resolution.reason, "SAME_DAY_SHORT_BREAK_SAME_CREW")

    def test_changed_operating_crew_is_no(self):
        index = _out_and_back(
            return_entries=(_entry("C1"), _entry("C3", position="FO")),
        )

        resolution = _resolve(index, 301, "C1")

        self.assertFalse(resolution.effective_heavy)
        self.assertEqual(resolution.reason, "CREW_SET_CHANGED")

    def test_pad_member_does_not_break_the_operating_crew_comparison(self):
        # Live case RSX6081/RSX6082 (2026-06-22): the outbound leg carried a
        # cockpit "PAD — Positioning · Not Active" member; the return did not.
        crew = (_entry("C1"), _entry("C2", position="FO"))
        index = _index(
            _context(
                301, "2026-06-01T20:00:00Z", "2026-06-01T23:30:00Z",
                (*crew, _entry("P1", position="PAD")),
                adep="HRG", ades="XYZ",
            ),
            _context(
                302, "2026-06-02T00:30:00Z", "2026-06-02T04:00:00Z", crew,
                adep="XYZ", ades="HRG",
            ),
        )

        for flight_nid in (301, 302):
            with self.subTest(flight_nid=flight_nid):
                resolution = _resolve(index, flight_nid, "C1")
                self.assertTrue(resolution.effective_heavy)
                self.assertEqual(resolution.reason, "SAME_DAY_SHORT_BREAK_SAME_CREW")

    def test_non_operating_cockpit_slots_are_excluded_from_comparison(self):
        # OBS/OBS2/STB are non-operating; an observer on one leg must not
        # break the operating-crew match.
        crew = (_entry("C1"), _entry("C2", position="FO"))
        index = _out_and_back(
            return_entries=(*crew, _entry("C9", position="OBS")),
        )

        resolution = _resolve(index, 301, "C1")

        self.assertTrue(resolution.effective_heavy)
        self.assertEqual(resolution.reason, "SAME_DAY_SHORT_BREAK_SAME_CREW")

    def test_rotation_resolves_yes_symmetrically_on_both_legs(self):
        index = _out_and_back()

        for flight_nid in (301, 302):
            for code in ("C1", "C2"):
                with self.subTest(flight_nid=flight_nid, code=code):
                    resolution = _resolve(index, flight_nid, code)
                    self.assertTrue(resolution.effective_heavy)
                    self.assertTrue(resolution.resolved)

    def test_pad_member_is_not_short_circuited_like_psn(self):
        # PSN forces an immediate No; PAD does not — a PAD member with their
        # own qualifying rotation resolves through the normal neighbour rule.
        crew = (_entry("C1", position="PAD"), _entry("C2"))
        index = _index(
            _context(301, "2026-06-01T20:00:00Z", "2026-06-01T23:30:00Z", crew, adep="HRG", ades="XYZ"),
            _context(302, "2026-06-02T00:30:00Z", "2026-06-02T04:00:00Z", crew, adep="XYZ", ades="HRG"),
        )

        resolution = _resolve(index, 301, "C1")

        self.assertTrue(resolution.effective_heavy)
        self.assertEqual(resolution.reason, "SAME_DAY_SHORT_BREAK_SAME_CREW")


class TestRotationContinuity(unittest.TestCase):
    def test_unchained_airports_are_a_rotation_mismatch(self):
        # Matrix 10: same crew, short break, but the airports do not chain.
        index = _out_and_back(return_adep="AAA", return_ades="BBB")

        resolution = _resolve(index, 301, "C1")

        self.assertFalse(resolution.effective_heavy)
        self.assertEqual(resolution.reason, "ROTATION_MISMATCH")

    def test_missing_airports_fail_closed_as_rotation_mismatch(self):
        # No airport data means continuity cannot be established: NO, never YES.
        index = _out_and_back(return_adep=None, return_ades=None)

        resolution = _resolve(index, 301, "C1")

        self.assertFalse(resolution.effective_heavy)
        self.assertEqual(resolution.reason, "ROTATION_MISMATCH")

    def test_chain_via_previous_sector_arrival_also_counts(self):
        # neighbour.arrival == current.departure (the other chain direction).
        crew = (_entry("C1"), _entry("C2", position="FO"))
        index = _index(
            _context(300, "2026-06-01T16:00:00Z", "2026-06-01T18:30:00Z", crew, adep="XYZ", ades="HRG"),
            _context(301, "2026-06-01T20:00:00Z", "2026-06-01T23:30:00Z", crew, adep="HRG", ades="XYZ"),
        )

        resolution = _resolve(index, 301, "C1")

        self.assertTrue(resolution.effective_heavy)
        self.assertEqual(resolution.reason, "SAME_DAY_SHORT_BREAK_SAME_CREW")


class TestReasonRanking(unittest.TestCase):
    def test_the_closest_near_miss_wins_across_neighbours(self):
        # Previous neighbour fails rotation; next neighbour fails only on crew.
        # The previous sector ends 13h before this leg starts, so this leg IS
        # first in its own duty and both directions are searched -- which is the
        # only state in which two reasons compete (pairing-direction ruling,
        # 2026-08-19). A connected predecessor would confine the search to
        # backward and the answer would simply be ROTATION_MISMATCH.
        crew = (_entry("C1"), _entry("C2", position="FO"))
        index = _index(
            _context(300, "2026-06-01T05:00:00Z", "2026-06-01T07:00:00Z", crew, adep="AAA", ades="BBB"),
            _context(301, "2026-06-01T20:00:00Z", "2026-06-01T23:30:00Z", crew, adep="HRG", ades="XYZ"),
            _context(
                302,
                "2026-06-02T00:30:00Z",
                "2026-06-02T04:00:00Z",
                (_entry("C1"), _entry("C3", position="FO")),
                adep="XYZ",
                ades="HRG",
            ),
        )

        resolution = _resolve(index, 301, "C1")

        self.assertFalse(resolution.effective_heavy)
        self.assertEqual(resolution.reason, "CREW_SET_CHANGED")


class TestCrewContextCarriesAirports(unittest.TestCase):
    def test_build_index_extracts_airport_codes_from_flight_mappings(self):
        index = build_crew_context_index(
            [
                {
                    "flightNid": 301,
                    "crewList": [
                        {
                            "contact": {"name": "A", "surname": "B", "personCode": "c1"},
                            "position": {"name": "CPT", "posType": "COCKPIT"},
                            "flightTrainingType": None,
                        }
                    ],
                    "startTimeUTC": "2026-06-01T20:00:00Z",
                    "endTimeUTC": "2026-06-01T23:30:00Z",
                    "flightTags": [],
                    "startAirport": {"code": {"icao": "HEGN", "iata": "HRG"}},
                    "endAirport": {"code": {"icao": None, "iata": "XYZ"}},
                }
            ]
        )

        context = index.contexts[301]
        self.assertEqual(context.departure_airport, "HEGN")
        # ICAO is preferred; IATA is the fallback when ICAO is absent.
        self.assertEqual(context.arrival_airport, "XYZ")

    def test_missing_airport_objects_stay_none(self):
        index = build_crew_context_index(
            [
                {
                    "flightNid": 302,
                    "crewList": [],
                    "startTimeUTC": "2026-06-01T20:00:00Z",
                    "endTimeUTC": "2026-06-01T23:30:00Z",
                    "flightTags": [],
                }
            ]
        )

        context = index.contexts[302]
        self.assertIsNone(context.departure_airport)
        self.assertIsNone(context.arrival_airport)


class TestIdProbeFormatting(unittest.TestCase):
    def test_probe_lines_show_the_candidate_ids_side_by_side(self):
        from backend.statistics.crew_hours.tools.id_probe import format_report_row

        line = format_report_row(
            {
                "scope_row_unique_id": "row-1",
                "unique_id": 101,
                "unique_leg_number": 555,
                "trip_nid": 777,
                "flightNo": "RSX331",
                "JL_STD_UTC": "20:00",
            }
        )

        for token in ("row-1", "101", "555", "777", "RSX331"):
            self.assertIn(token, line)

    def test_probe_lines_mark_absent_ids_explicitly(self):
        from backend.statistics.crew_hours.tools.id_probe import format_report_row

        line = format_report_row({"scope_row_unique_id": "row-2"})

        self.assertIn("row-2", line)
        self.assertIn("—", line)


if __name__ == "__main__":
    unittest.main()

"""The five approved Heavy corrections (owner rulings, 2026-08-19).

D-1  IATA/ICAO aliases, and the facade receiving both airport sources.
D-2  a member's own PAD slot must not delete them from their own rotation.
2.3  rotation continuity is a true out-and-back, not a chain-onward.
2.4  the badge means the resolver established Heavy = True, nothing else.
2.5  a leg whose duty started on an earlier day pairs backward, not forward.
2.6  heavy_trace explains every leg's verdict without a screenshot.

Cases A-D are sanitized replicas of the live June 2026 rotations; no real crew
names or person codes appear here.
"""

import unittest

from backend.statistics.crew_hours.augmented import AugmentedIndex
from backend.statistics.crew_hours.crew_context import (
    CrewContextEntry,
    CrewContextIndex,
    FlightContext,
)
from backend.statistics.crew_hours.heavy import (
    classify_flight_heavy,
    derive_heavy_detail,
)
from backend.statistics.crew_hours.mcp_report import OfficialMcpReport
from backend.statistics.crew_hours.service import _build_mcp_report_response
from backend.statistics.crew_hours.unknown_resolver import (
    build_rotation_index,
    resolve_unknown_heavy,
)


_CABIN_PREFIXES = ("FA", "SFA", "EFA", "IFA")


def _pos_type_for(position: str) -> str:
    """Cabin ranks must not be counted as cockpit crew by the fixtures."""

    upper = position.strip().upper()
    return "CABIN" if upper.startswith(_CABIN_PREFIXES) else "COCKPIT"


def _entry(code: str, position: str, *, pos_type: str | None = None) -> CrewContextEntry:
    return CrewContextEntry(
        pos_type=pos_type or _pos_type_for(position),
        position=position,
        training_type=None,
        crew_code=code,
        function=None,
    )


def _row(
    unique_id: int,
    flight_number: str,
    adep: str | None,
    ades: str | None,
    codes_positions,
) -> dict:
    codes = [code for code, _ in codes_positions]
    return {
        "scope_row_unique_id": f"row-{unique_id}",
        "unique_id": unique_id,
        "flightNo": flight_number,
        "crew_codes": codes,
        "crew_names": [f"Crew {code}" for code in codes],
        "crew_position_names": [position for _, position in codes_positions],
        "acftType": "B738 - 737-800",
        "blockTimeJourneyLog": "01:30",
        "jl_adep_preferred_code": adep,
        "jl_ades_preferred_code": ades,
    }


def _context(unique_id, start, end, codes_positions, adep, ades) -> FlightContext:
    return FlightContext(
        flight_nid=unique_id,
        start_time_utc=start,
        end_time_utc=end,
        flight_tags=(),
        entries=tuple(_entry(code, position) for code, position in codes_positions),
        departure_airport=adep,
        arrival_airport=ades,
    )


def _index(*contexts: FlightContext) -> CrewContextIndex:
    return CrewContextIndex(
        available=True,
        by_flight={context.flight_nid: context.entries for context in contexts},
        contexts={context.flight_nid: context for context in contexts},
    )


def _response(rows, contexts):
    totals = {code: "10:00" for row in rows for code in row["crew_codes"]}
    return _build_mcp_report_response(
        OfficialMcpReport(totals, rows),
        from_date="2026-06-01",
        to_date="2026-06-30",
        position="All",
        crew_member=None,
        # LEON is silent for every case: the FTL index exists but holds no value.
        augmented_index=AugmentedIndex(True, {}, 0, 0, {}),
        crew_context_index=_index(*contexts),
    )


def _legs(response, crew_code):
    member = next(item for item in response.crew_members if item.person_code == crew_code)
    return {flight.flight_number: flight for flight in member.flights}


def _trace_steps(flight) -> list[str]:
    return [step.step for step in flight.heavy_trace]


def _trace_step(flight, name):
    return next(step for step in flight.heavy_trace if step.step == name)


# --------------------------------------------------------------------------
# 2.1 — D-1: IATA/ICAO aliases
# --------------------------------------------------------------------------


class TestAirportCodeAliases(unittest.TestCase):
    """SVX ↔ USSS and EVN ↔ UDYZ are the same airport, in either form."""

    def test_icao_form_fires_the_svx_rule(self):
        for route in (("HESH", "USSS"), ("USSS", "HESH"), (" usss ", None)):
            with self.subTest(route=route):
                self.assertEqual(
                    derive_heavy_detail([_entry("C1", "CPT")] * 2, "B738", None, route_airports=route),
                    (True, "SVX_AIRPORT"),
                )

    def test_icao_form_fires_the_evn_rule_and_still_wins_over_svx(self):
        self.assertEqual(
            derive_heavy_detail([], "B738", None, route_airports=("HESH", "UDYZ")),
            (False, "EVN_AIRPORT"),
        )
        # Either form on either side: EVN still beats SVX.
        self.assertEqual(
            derive_heavy_detail([], "B738", None, route_airports=("UDYZ", "SVX")),
            (False, "EVN_AIRPORT"),
        )
        self.assertEqual(
            derive_heavy_detail([], "B738", None, route_airports=("EVN", "USSS")),
            (False, "EVN_AIRPORT"),
        )

    def test_mixed_forms_across_the_two_sources_still_match(self):
        # The report row may carry IATA while the flight-list context carries
        # ICAO; both are passed together and either one counts.
        self.assertEqual(
            derive_heavy_detail(
                [_entry("C1", "CPT")] * 2,
                "B738",
                None,
                route_airports=("SSH", "SVX", "HESH", "USSS"),
            ),
            (True, "SVX_AIRPORT"),
        )

    def test_alias_matching_is_exact_never_substring(self):
        standard = [_entry("C1", "CPT")] * 2
        for route in (("USSSX", "UDYZA"), ("XUSSS", "AUDYZ"), ("USS", "UDY")):
            with self.subTest(route=route):
                self.assertEqual(
                    derive_heavy_detail(standard, "B738", None, route_airports=route),
                    (False, "NONE"),
                )


class TestFacadeReceivesBothAirportSources(unittest.TestCase):
    """classify_flight_heavy must see the report row's codes, not only the context."""

    def test_report_row_codes_reach_the_airport_rule(self):
        # The context knows nothing about the route; the caller supplies the
        # report row's preferred codes. The airport rule must still fire.
        context = _context(
            701, "2026-06-16T17:15:00Z", "2026-06-16T22:35:00Z",
            [("C1", "CPT"), ("C2", "FO")], None, None,
        )
        index = _index(context)

        verdict, reason = classify_flight_heavy(
            index,
            build_rotation_index(index),
            701,
            aircraft_type="B738 - 737-800",
            route_airports=("SSH", "SVX"),
        )

        self.assertIs(verdict, True)
        self.assertEqual(reason, "SVX_AIRPORT")

    def test_context_codes_still_count_when_the_caller_supplies_none(self):
        context = _context(
            702, "2026-06-16T17:15:00Z", "2026-06-16T22:35:00Z",
            [("C1", "CPT"), ("C2", "FO")], "HESH", "USSS",
        )
        index = _index(context)

        verdict, reason = classify_flight_heavy(
            index, build_rotation_index(index), 702, aircraft_type="B738 - 737-800"
        )

        self.assertIs(verdict, True)
        self.assertEqual(reason, "SVX_AIRPORT")

    def test_an_icao_only_leg_agrees_with_the_report(self):
        # The same leg through both engines must not disagree.
        rows = [_row(703, "RSX331", "HESH", "USSS", [("C1", "CPT"), ("C2", "FO")])]
        contexts = [
            _context(
                703, "2026-06-16T17:15:00Z", "2026-06-16T22:35:00Z",
                [("C1", "CPT"), ("C2", "FO")], "HESH", "USSS",
            )
        ]
        report_flight = _legs(_response(rows, contexts), "C1")["RSX331"]

        index = _index(*contexts)
        facade_verdict, facade_reason = classify_flight_heavy(
            index,
            build_rotation_index(index),
            703,
            aircraft_type="B738 - 737-800",
            route_airports=("HESH", "USSS"),
        )

        self.assertIs(report_flight.augmented_heavy, True)
        self.assertEqual(report_flight.heavy_reason, "SVX_AIRPORT")
        self.assertIs(facade_verdict, report_flight.augmented_heavy)
        self.assertEqual(facade_reason, report_flight.heavy_reason)


class TestCaseA(unittest.TestCase):
    """Case A — the SVX rotation, in IATA and again in ICAO-only form."""

    IATA = ("SSH", "SVX")
    ICAO = ("HESH", "USSS")

    def _rotation(self, outbound, inbound):
        rows = [
            _row(801, "RSX331", outbound[0], outbound[1], [("C1", "CPT"), ("C2", "FO")]),
            _row(802, "RSX332", inbound[0], inbound[1], [("C1", "CPT"), ("C2", "FO")]),
        ]
        contexts = [
            _context(
                801, "2026-06-16T17:15:00Z", "2026-06-16T22:35:00Z",
                [("C1", "CPT"), ("C2", "FO")], outbound[0], outbound[1],
            ),
            _context(
                802, "2026-06-16T23:50:00Z", "2026-06-17T06:00:00Z",
                [("C1", "CPT"), ("C2", "FO")], inbound[0], inbound[1],
            ),
        ]
        return _response(rows, contexts)

    def _assert_svx_on_both_legs(self, response):
        for code in ("C1", "C2"):
            for leg, flight in _legs(response, code).items():
                self.assertIs(flight.augmented_heavy, True, f"{code} {leg}")
                self.assertEqual(flight.heavy_reason, "SVX_AIRPORT", f"{code} {leg}")
                # Deterministic airport rule: never the resolver, never a badge.
                self.assertFalse(flight.unknown_resolved, f"{code} {leg}")
                self.assertIsNone(flight.unknown_resolution_reason, f"{code} {leg}")

    def test_case_a_with_iata_codes(self):
        self._assert_svx_on_both_legs(
            self._rotation(self.IATA, (self.IATA[1], self.IATA[0]))
        )

    def test_case_a_with_icao_only_codes(self):
        self._assert_svx_on_both_legs(
            self._rotation(self.ICAO, (self.ICAO[1], self.ICAO[0]))
        )


# --------------------------------------------------------------------------
# 2.2 — D-2: a member's own PAD slot must not break their rotation
# --------------------------------------------------------------------------


class TestCaseB(unittest.TestCase):
    """Case B — RSX6077 HRG→LIS / RSX6078 LIS→HRG, one member F0 then PAD.

    The subject rides PAD on the return leg. Because the crew-set identity
    drops positioning members and the comparison was a symmetric set equality,
    that dropped the subject from one side only and broke the rotation for
    EVERY member of it, not just the PAD rider.
    """

    OUTBOUND = ("2026-06-14T14:25:00Z", "2026-06-14T20:40:00Z")
    INBOUND = ("2026-06-14T21:50:00Z", "2026-06-15T03:35:00Z")

    def _rotation(self, inbound_positions):
        outbound_positions = [("C1", "CPT"), ("C2", "FO"), ("C3", "FA1")]
        rows = [
            _row(901, "RSX6077", "HRG", "LIS", outbound_positions),
            _row(902, "RSX6078", "LIS", "HRG", inbound_positions),
        ]
        contexts = [
            _context(901, *self.OUTBOUND, outbound_positions, "HRG", "LIS"),
            _context(902, *self.INBOUND, inbound_positions, "LIS", "HRG"),
        ]
        return _response(rows, contexts)

    def test_the_pad_rider_and_every_colleague_stay_yes_on_both_legs(self):
        # C2 flew out as FO and rode home as PAD.
        response = self._rotation([("C1", "CPT"), ("C2", "PAD"), ("C3", "FA1")])

        for code in ("C1", "C2", "C3"):
            flights = _legs(response, code)
            for leg in ("RSX6077", "RSX6078"):
                flight = flights[leg]
                self.assertIs(flight.augmented_heavy, True, f"{code} {leg}")
                self.assertEqual(
                    flight.unknown_resolution_reason,
                    "SAME_DAY_SHORT_BREAK_SAME_CREW",
                    f"{code} {leg}",
                )
                # Resolver-established Heavy: the badge belongs on both legs.
                self.assertTrue(flight.unknown_resolved, f"{code} {leg}")

    def test_a_different_person_riding_pad_on_the_return_only(self):
        # C4 joins the return leg as PAD and was not on the outbound at all.
        response = self._rotation(
            [("C1", "CPT"), ("C2", "FO"), ("C3", "FA1"), ("C4", "PAD")]
        )

        for code in ("C1", "C2", "C3"):
            flights = _legs(response, code)
            for leg in ("RSX6077", "RSX6078"):
                self.assertIs(flights[leg].augmented_heavy, True, f"{code} {leg}")

    def test_a_genuine_roster_change_still_breaks_the_rotation(self):
        # The correction must not swallow a real crew change: C3 is replaced.
        response = self._rotation([("C1", "CPT"), ("C2", "FO"), ("C9", "FA1")])

        flight = _legs(response, "C1")["RSX6077"]
        self.assertIs(flight.augmented_heavy, False)
        self.assertEqual(flight.unknown_resolution_reason, "CREW_SET_CHANGED")

    def test_psn_keeps_its_immediate_no(self):
        # Unchanged rule: a PSN slot on the leg being judged is No at once.
        response = self._rotation([("C1", "CPT"), ("C2", "PSN"), ("C3", "FA1")])

        psn_leg = _legs(response, "C2")["RSX6078"]
        self.assertIs(psn_leg.augmented_heavy, False)
        self.assertEqual(psn_leg.unknown_resolution_reason, "PSN_POSITIONING")
        # ...and it does not damage anyone else's rotation.
        self.assertIs(_legs(response, "C1")["RSX6078"].augmented_heavy, True)


# --------------------------------------------------------------------------
# 2.3 — rotation continuity is a true out-and-back
# --------------------------------------------------------------------------


class TestCaseC(unittest.TestCase):
    """Case C — RSX8891 HRG→SSH then RSX6083 SSH→OPO: chain onward, not a return.

    Break 0:50 and an identical roster, so every other gate passes. Only the
    out-and-back requirement can produce the correct No here, and the reason
    must name the rotation, not the crew or the break.
    """

    def _response(self):
        crew = [("C1", "CPT"), ("C2", "FO")]
        rows = [
            _row(1001, "RSX8891", "HRG", "SSH", crew),
            _row(1002, "RSX6083", "SSH", "OPO", crew),
        ]
        contexts = [
            _context(1001, "2026-06-18T06:00:00Z", "2026-06-18T07:10:00Z", crew, "HRG", "SSH"),
            _context(1002, "2026-06-18T08:00:00Z", "2026-06-18T13:30:00Z", crew, "SSH", "OPO"),
        ]
        return _response(rows, contexts)

    def test_chain_onward_is_no_on_both_legs_for_rotation_reasons(self):
        response = self._response()

        for code in ("C1", "C2"):
            flights = _legs(response, code)
            for leg in ("RSX8891", "RSX6083"):
                flight = flights[leg]
                self.assertIs(flight.augmented_heavy, False, f"{code} {leg}")
                self.assertEqual(
                    flight.unknown_resolution_reason, "ROTATION_MISMATCH", f"{code} {leg}"
                )
                # 2.4: a resolver No is not a resolver-established Heavy.
                self.assertFalse(flight.unknown_resolved, f"{code} {leg}")

    def test_the_same_pair_flown_as_an_out_and_back_is_yes(self):
        # Change only the second leg's destination back to the origin.
        crew = [("C1", "CPT"), ("C2", "FO")]
        rows = [
            _row(1011, "RSX8891", "HRG", "SSH", crew),
            _row(1012, "RSX8892", "SSH", "HRG", crew),
        ]
        contexts = [
            _context(1011, "2026-06-18T06:00:00Z", "2026-06-18T07:10:00Z", crew, "HRG", "SSH"),
            _context(1012, "2026-06-18T08:00:00Z", "2026-06-18T09:20:00Z", crew, "SSH", "HRG"),
        ]

        for leg, flight in _legs(_response(rows, contexts), "C1").items():
            self.assertIs(flight.augmented_heavy, True, leg)
            self.assertEqual(flight.unknown_resolution_reason, "SAME_DAY_SHORT_BREAK_SAME_CREW")

    def test_a_missing_airport_still_fails_closed(self):
        crew = [("C1", "CPT"), ("C2", "FO")]
        rows = [
            _row(1021, "RSX8891", "HRG", None, crew),
            _row(1022, "RSX8892", None, "HRG", crew),
        ]
        contexts = [
            _context(1021, "2026-06-18T06:00:00Z", "2026-06-18T07:10:00Z", crew, "HRG", None),
            _context(1022, "2026-06-18T08:00:00Z", "2026-06-18T09:20:00Z", crew, None, "HRG"),
        ]

        flight = _legs(_response(rows, contexts), "C1")["RSX8891"]
        self.assertIs(flight.augmented_heavy, False)
        self.assertEqual(flight.unknown_resolution_reason, "ROTATION_MISMATCH")


# --------------------------------------------------------------------------
# 2.4 — badge ⟺ the resolver established Heavy = True
# --------------------------------------------------------------------------


class TestBadgeMeansResolverEstablishedHeavy(unittest.TestCase):
    def test_a_resolver_no_carries_no_badge(self):
        # Case D: 22-06 HRG→OPO then 23-06 OPO→SSH. STEP 4 ran and found no
        # qualifying rotation. "Not found" is not "locally resolved".
        crew = [("C1", "CPT"), ("C2", "FO")]
        rows = [
            _row(1101, "RSX6081", "HRG", "OPO", crew),
            _row(1102, "RSX6084", "OPO", "SSH", crew),
        ]
        contexts = [
            _context(1101, "2026-06-22T15:00:00Z", "2026-06-22T21:00:00Z", crew, "HRG", "OPO"),
            _context(1102, "2026-06-23T08:00:00Z", "2026-06-23T12:00:00Z", crew, "OPO", "SSH"),
        ]

        response = _response(rows, contexts)
        for code in ("C1", "C2"):
            for leg, flight in _legs(response, code).items():
                self.assertIs(flight.augmented_heavy, False, f"{code} {leg}")
                self.assertFalse(flight.unknown_resolved, f"{code} {leg}")

    def test_a_leg_with_no_context_at_all_carries_no_badge(self):
        rows = [_row(1111, "RSX700", "HRG", "SSH", [("C1", "CPT")])]

        flight = _legs(_response(rows, []), "C1")["RSX700"]
        self.assertIs(flight.augmented_heavy, False)
        self.assertFalse(flight.unknown_resolved)
        self.assertEqual(flight.unknown_resolution_reason, "NO_FLIGHT_CONTEXT")

    def test_a_count_rule_verdict_carries_no_badge(self):
        crew = [("C1", "CPT"), ("C2", "FO"), ("C3", "FO2")]
        rows = [_row(1121, "RSX500", "HRG", "SSH", crew)]
        contexts = [
            _context(1121, "2026-06-18T06:00:00Z", "2026-06-18T07:10:00Z", crew, "HRG", "SSH")
        ]

        flight = _legs(_response(rows, contexts), "C1")["RSX500"]
        self.assertIs(flight.augmented_heavy, True)
        self.assertEqual(flight.heavy_reason, "EXTRA_COCKPIT_CREW")
        self.assertFalse(flight.unknown_resolved)


# --------------------------------------------------------------------------
# 2.5 — pairing direction
# --------------------------------------------------------------------------


class TestPairingDirection(unittest.TestCase):
    """A leg that is not first in its duty pairs backward only."""

    def _index(self):
        # 14-06 HRG→LIS 14:25-20:40, then LIS→HRG 21:50-03:35(+1) — one duty,
        # break 1:10. The next day's HRG→LIS is a different duty entirely.
        return _index(
            _context(
                1201, "2026-06-14T14:25:00Z", "2026-06-14T20:40:00Z",
                [("C1", "CPT"), ("C9", "FO")], "HRG", "LIS",
            ),
            _context(
                1202, "2026-06-14T21:50:00Z", "2026-06-15T03:35:00Z",
                [("C1", "CPT"), ("C2", "FO")], "LIS", "HRG",
            ),
            _context(
                1203, "2026-06-15T06:00:00Z", "2026-06-15T12:15:00Z",
                [("C1", "CPT"), ("C2", "FO")], "HRG", "LIS",
            ),
        )

    def test_the_late_leg_pairs_backward_and_not_forward(self):
        index = self._index()

        resolution = resolve_unknown_heavy(
            index, build_rotation_index(index), 1202, "C1"
        )

        # Backward is the only direction considered: the roster changed on the
        # outbound leg, so the answer is CREW_SET_CHANGED. Pairing forward with
        # the next day's leg would have produced a spurious Yes -- that leg is a
        # perfect out-and-back partner by airports, break arithmetic aside.
        self.assertIs(resolution.effective_heavy, False)
        self.assertEqual(resolution.reason, "CREW_SET_CHANGED")

    def test_a_leg_first_in_its_duty_still_pairs_forward(self):
        index = self._index()

        resolution = resolve_unknown_heavy(
            index, build_rotation_index(index), 1201, "C1"
        )

        # 1201 has no predecessor at all, so the forward search runs and finds
        # the genuine out-and-back partner.
        self.assertIs(resolution.effective_heavy, False)
        self.assertEqual(resolution.reason, "CREW_SET_CHANGED")

    def test_forward_pairing_survives_when_the_predecessor_is_a_separate_duty(self):
        # A 10h gap before the leg means the leg IS first in its own duty, so
        # the forward partner must still be reachable.
        index = _index(
            _context(
                1301, "2026-06-14T02:00:00Z", "2026-06-14T04:00:00Z",
                [("C1", "CPT"), ("C2", "FO")], "HRG", "SSH",
            ),
            _context(
                1302, "2026-06-14T18:00:00Z", "2026-06-14T20:00:00Z",
                [("C1", "CPT"), ("C2", "FO")], "HRG", "SSH",
            ),
            _context(
                1303, "2026-06-14T21:00:00Z", "2026-06-14T23:00:00Z",
                [("C1", "CPT"), ("C2", "FO")], "SSH", "HRG",
            ),
        )

        resolution = resolve_unknown_heavy(
            index, build_rotation_index(index), 1302, "C1"
        )

        self.assertIs(resolution.effective_heavy, True)
        self.assertEqual(resolution.reason, "SAME_DAY_SHORT_BREAK_SAME_CREW")


if __name__ == "__main__":
    unittest.main()

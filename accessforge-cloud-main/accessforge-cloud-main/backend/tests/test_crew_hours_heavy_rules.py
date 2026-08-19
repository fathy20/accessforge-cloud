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


if __name__ == "__main__":
    unittest.main()

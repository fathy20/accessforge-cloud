"""Cross-consistency gate: the report and the Copilot agree on every flight.

One flight, one verdict (owner ruling 2026-08-17). Both surfaces run the same
engine (heavy.classify_flight_heavy); this test feeds identical MCP report
rows to the REAL service pipeline and the REAL Copilot answer path and asserts
the verdicts match on the five screenshot cases plus the EVN-veto and cabin-
positioning variants that exposed the old divergence.
"""

import unittest
from datetime import date

from backend.copilot.local_answers import _context_index_from_report, answer_locally
from backend.statistics.crew_hours.augmented import AugmentedIndex
from backend.statistics.crew_hours.domain import select_rows_for_period
from backend.statistics.crew_hours.mcp_report import OfficialMcpReport
from backend.statistics.crew_hours.positions import POSITIONING_POSITIONS
from backend.statistics.crew_hours.service import _build_mcp_report_response


def _row(
    unique_id: int,
    flight_number: str,
    day: str,          # dd-mm-YYYY, the report's date format
    off: str,
    on: str,
    adep: str,
    ades: str,
    crew: list[tuple[str, str]],   # (code, position)
) -> dict:
    return {
        "scope_row_unique_id": str(unique_id),
        "unique_id": unique_id,
        "flightNo": flight_number,
        "date_STD_log_UTC": day,
        "JL_STD_UTC": off,
        "JL_STA_UTC": on,
        "jl_adep_preferred_code": adep,
        "jl_ades_preferred_code": ades,
        "crew_codes": [code for code, _ in crew],
        "crew_names": [f"Crew {code}" for code, _ in crew],
        "crew_position_names": [position for _, position in crew],
        "acftType": "B738 - 737-800",
        "blockTimeJourneyLog": "01:30",
    }


def _report(rows: list[dict]) -> OfficialMcpReport:
    totals = {code: "10:00" for row in rows for code in row["crew_codes"]}
    return OfficialMcpReport(totals, rows)


def report_path_verdict(report: OfficialMcpReport, unique_id: int, crew_code: str):
    """The REAL Crew Hours service pipeline, LEON silent, same row-built index."""

    response = _build_mcp_report_response(
        report,
        from_date="2026-06-01",
        to_date="2026-06-30",
        position="All",
        crew_member=None,
        augmented_index=AugmentedIndex(True, {}, 0, 0, {}),
        crew_context_index=_context_index_from_report(report),
    )
    member = next(m for m in response.crew_members if m.person_code == crew_code)
    flight = next(f for f in member.flights if f.flight_nid == str(unique_id))
    return flight.augmented_heavy


def copilot_path_verdict(report: OfficialMcpReport, flight_number: str, day_iso: str):
    """The REAL Copilot local answer; verdict parsed from its fixed phrasing."""

    def fetch(from_date: str, to_date: str) -> OfficialMcpReport:
        # Emulate the REAL fetcher's trimming (fetch_official_report):
        # duty-attributed period selection, not a pass-through of all rows.
        return OfficialMcpReport(
            dict(report),
            select_rows_for_period(report.rows, from_date, to_date),
        )

    answer = answer_locally(
        f"Is {flight_number} on {day_iso} Augmented (Heavy)?",
        today=date(2026, 6, 30),
        fetch_report=fetch,
    )
    assert answer is not None
    if "cannot be determined" in answer.text:
        return None
    if "Not Heavy" in answer.text:
        return False
    assert "Heavy" in answer.text
    return True


class TestHeavyCrossConsistency(unittest.TestCase):
    def assert_flight_agrees(self, report, unique_id, flight_number, day_iso):
        copilot = copilot_path_verdict(report, flight_number, day_iso)
        for row in report.rows:
            if row["unique_id"] != unique_id:
                continue
            for code, position in zip(row["crew_codes"], row["crew_position_names"]):
                if position.upper() in POSITIONING_POSITIONS:
                    continue  # member-level semantics differ for riders by design
                service = report_path_verdict(report, unique_id, code)
                self.assertEqual(
                    service,
                    copilot,
                    f"{flight_number}/{code}: report={service} copilot={copilot}",
                )

    def test_case_1_svx_rotation_both_yes(self):
        report = _report([
            _row(501, "RSX331", "16-06-2026", "17:15", "22:35", "SSH", "SVX",
                 [("C1", "CPT"), ("C2", "FO")]),
            _row(502, "RSX332", "16-06-2026", "23:50", "06:00", "SVX", "SSH",
                 [("C1", "CPT"), ("C2", "FO")]),
        ])
        self.assert_flight_agrees(report, 501, "RSX331", "2026-06-16")
        self.assert_flight_agrees(report, 502, "RSX332", "2026-06-16")

    def test_case_2_evn_rotation_both_no(self):
        report = _report([
            _row(511, "RSX121", "20-06-2026", "22:05", "01:00", "SSH", "EVN",
                 [("C1", "CPT"), ("C2", "FO")]),
        ])
        self.assert_flight_agrees(report, 511, "RSX121", "2026-06-20")

    def test_case_2b_evn_vetoes_a_cockpit_count_yes_on_both_surfaces(self):
        # The case that exposed the old divergence: report said No (EVN
        # absolute), the Copilot's cockpit rule said Yes. Owner ruling Q2.
        report = _report([
            _row(513, "RSX121", "20-06-2026", "22:05", "01:00", "SSH", "EVN",
                 [("C1", "CPT"), ("C2", "FO"), ("C3", "FO2")]),
        ])
        self.assert_flight_agrees(report, 513, "RSX121", "2026-06-20")
        self.assertFalse(copilot_path_verdict(report, "RSX121", "2026-06-20"))

    def test_case_3_resolver_rotation_yes_on_both_surfaces(self):
        # RSX6081/RSX6082 with the PAD rider: STEP 4 now runs on the Copilot
        # path too (the is_unknown=False dead end is gone).
        report = _report([
            _row(601, "RSX6081", "22-06-2026", "15:00", "21:00", "HRG", "OPO",
                 [("C1", "CPT"), ("C2", "FO"), ("P1", "PAD")]),
            _row(602, "RSX6082", "22-06-2026", "22:00", "03:50", "OPO", "HRG",
                 [("C1", "CPT"), ("C2", "FO")]),
        ])
        self.assert_flight_agrees(report, 601, "RSX6081", "2026-06-22")
        self.assert_flight_agrees(report, 602, "RSX6082", "2026-06-22")
        self.assertTrue(copilot_path_verdict(report, "RSX6081", "2026-06-22"))

    def test_case_4_unresolvable_chain_no_on_both_surfaces(self):
        report = _report([
            _row(611, "RSX6081", "22-06-2026", "15:00", "21:00", "HRG", "OPO",
                 [("C1", "CPT"), ("C2", "FO")]),
            _row(612, "RSX6084", "23-06-2026", "08:00", "12:00", "OPO", "SSH",
                 [("C1", "CPT"), ("C2", "FO")]),
        ])
        self.assert_flight_agrees(report, 611, "RSX6081", "2026-06-22")
        self.assert_flight_agrees(report, 612, "RSX6084", "2026-06-23")

    def test_case_6_cross_midnight_return_with_rider_difference(self):
        # M-1 (bug report 2026-08-17): the return leg STARTS on the next UTC
        # day, and the legs differ by a PAD rider — so duty grouping (PSN-only
        # identity, the 2026-08-09 parity ruling) does NOT connect them, and a
        # single-day fetch trims the return leg out. The Copilot's STEP 4 then
        # never saw the neighbour and answered No while the month-window
        # report answered Yes. The widened Copilot fetch window closes this.
        report = _report([
            _row(701, "RSX6081", "22-06-2026", "20:00", "23:30", "HRG", "OPO",
                 [("C1", "CPT"), ("C2", "FO"), ("P1", "PAD")]),
            _row(702, "RSX6082", "23-06-2026", "00:30", "04:00", "OPO", "HRG",
                 [("C1", "CPT"), ("C2", "FO")]),
        ])
        self.assert_flight_agrees(report, 701, "RSX6081", "2026-06-22")
        self.assert_flight_agrees(report, 702, "RSX6082", "2026-06-23")
        self.assertTrue(copilot_path_verdict(report, "RSX6081", "2026-06-22"))

    def test_case_5_cabin_positioning_rider_no_on_both_surfaces(self):
        # Four operating cabin plus a PAD rider: the rider never tips the
        # count on either surface (the old cabin engine counted it).
        report = _report([
            _row(621, "RSX700", "25-06-2026", "08:00", "11:00", "HRG", "SSH",
                 [("C1", "CPT"), ("C2", "FO"),
                  ("A1", "FA1"), ("A2", "FA2"), ("A3", "FA3"), ("A4", "FA4"),
                  ("A9", "PAD")]),
        ])
        self.assert_flight_agrees(report, 621, "RSX700", "2026-06-25")
        self.assertFalse(copilot_path_verdict(report, "RSX700", "2026-06-25"))


if __name__ == "__main__":
    unittest.main()

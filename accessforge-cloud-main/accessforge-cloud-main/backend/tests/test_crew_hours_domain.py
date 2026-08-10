import unittest

from backend.statistics.crew_hours.mcp_report import (
    OfficialMcpReport,
    _aggregate_report_rows,
    _format_minutes,
    _parse_block_time,
)
from backend.statistics.crew_hours.service import LiveCrewHoursService
from backend.tests.crew_hours_parity_fixtures import (
    ACCUMULATED_DURATION_ROWS,
    EXPLICIT_TRN_SECTOR,
    JUNE_COCKPIT_REFERENCE_NUMERIC_GRAND_TOTAL,
    JUNE_COCKPIT_REFERENCE_VALUES,
    LIVE_BOUNDARY_A,
    LIVE_BOUNDARY_B,
    MIXED_OPERATING_PSN_SECTOR,
    NORMAL_OPERATING_SECTOR,
    PSN_ONLY_SECTOR,
    connected_boundary_pair,
    report_leg,
)


class TestOperatingPositionAggregation(unittest.TestCase):
    def test_normal_operating_sector_counts_for_its_member(self):
        totals, minutes = _aggregate_report_rows([NORMAL_OPERATING_SECTOR])

        self.assertEqual(totals, {"OPERATING": "1:30"})
        self.assertEqual(minutes, {"OPERATING": 90})

    def test_psn_only_sector_is_traceable_but_has_no_operating_total(self):
        totals, minutes = _aggregate_report_rows([PSN_ONLY_SECTOR])

        self.assertEqual(totals, {})
        self.assertEqual(minutes, {})

    def test_mixed_sector_excludes_only_the_psn_member(self):
        totals, minutes = _aggregate_report_rows([MIXED_OPERATING_PSN_SECTOR])

        self.assertEqual(totals, {"OPERATING": "2:15"})
        self.assertEqual(minutes, {"OPERATING": 135})

    def test_aligned_positions_still_exclude_psn_when_names_are_misaligned(self):
        row = {
            **MIXED_OPERATING_PSN_SECTOR,
            "crew_names": ["Only one name"],
        }

        totals, minutes = _aggregate_report_rows([row])

        self.assertEqual(totals, {"OPERATING": "2:15"})
        self.assertEqual(minutes, {"OPERATING": 135})

    def test_accumulated_durations_do_not_wrap_at_24_hours(self):
        totals, minutes = _aggregate_report_rows(list(ACCUMULATED_DURATION_ROWS))

        self.assertEqual(totals, {"LONG-HOURS": "240:45"})
        self.assertEqual(minutes, {"LONG-HOURS": 14_445})

    def test_explicit_trn_is_exact_and_never_enters_numeric_position_totals(self):
        class FakeCrewClient:
            def fetch_official_totals(self, from_date, to_date):
                return OfficialMcpReport(
                    {"TRAINING": "TRN"},
                    [EXPLICIT_TRN_SECTOR],
                    total_minutes={},
                )

        report = LiveCrewHoursService(FakeCrewClient()).get_crew_hours_report(
            "2026-06-01", "2026-06-30"
        )
        member = report.crew_members[0]

        self.assertEqual(member.official_total, "TRN")
        self.assertEqual(member.raw_official_total, "TRN")
        self.assertEqual(member.status, "TRN")
        self.assertTrue(member.flights[0].is_trn)
        self.assertEqual(member.flights[0].flight_training_type, "TRN")
        self.assertEqual(report.official_totals_by_position, {})

    def test_june_reference_numeric_grand_total_excludes_text_trn(self):
        numeric_values = [
            _parse_block_time(value)
            for value in JUNE_COCKPIT_REFERENCE_VALUES
            if value != "TRN"
        ]

        self.assertEqual(
            _format_minutes(sum(numeric_values)),
            JUNE_COCKPIT_REFERENCE_NUMERIC_GRAND_TOTAL,
        )

    def test_mixed_psn_member_and_source_position_remain_traceable(self):
        totals, minutes = _aggregate_report_rows([MIXED_OPERATING_PSN_SECTOR])

        class FakeCrewClient:
            def fetch_official_totals(self, from_date, to_date):
                return OfficialMcpReport(
                    totals,
                    [MIXED_OPERATING_PSN_SECTOR],
                    total_minutes=minutes,
                )

        report = LiveCrewHoursService(FakeCrewClient()).get_crew_hours_report(
            "2026-06-01", "2026-06-30"
        )
        by_code = {member.person_code: member for member in report.crew_members}

        self.assertEqual(by_code["OPERATING"].official_total, "2:15")
        self.assertEqual(by_code["OPERATING"].flights[0].position, "FO")
        self.assertIsNone(by_code["PASSENGER"].official_total)
        self.assertEqual(by_code["PASSENGER"].flights[0].position, "PSN")
        self.assertEqual(report.official_totals_by_position, {"Cockpit": "2:15"})

    def test_supplied_ground_only_trn_survives_without_flight_scope_rows(self):
        class FakeCrewClient:
            def fetch_official_totals(self, from_date, to_date):
                return OfficialMcpReport(
                    {"GROUND-TRAINING": "TRN"},
                    [],
                    total_minutes={},
                )

        report = LiveCrewHoursService(FakeCrewClient()).get_crew_hours_report(
            "2026-06-01", "2026-06-30"
        )
        member = report.crew_members[0]

        self.assertEqual(member.person_code, "GROUND-TRAINING")
        self.assertEqual(member.official_total, "TRN")
        self.assertEqual(member.status, "TRN")
        self.assertEqual(member.flight_count, 0)
        self.assertEqual(report.official_totals_by_position, {})


class TestConnectedDutyAttribution(unittest.TestCase):
    @staticmethod
    def _select(rows, from_date, to_date):
        from backend.statistics.crew_hours.domain import select_rows_for_period

        return select_rows_for_period(rows, from_date, to_date)

    def test_three_hours_fifty_nine_connects_across_month_boundary(self):
        rows = connected_boundary_pair(239)

        self.assertEqual(len(self._select(rows, "2026-06-01", "2026-06-30")), 2)
        self.assertEqual(self._select(rows, "2026-07-01", "2026-07-31"), [])

    def test_four_hours_does_not_connect(self):
        rows = connected_boundary_pair(240)

        self.assertEqual(len(self._select(rows, "2026-06-01", "2026-06-30")), 1)
        self.assertEqual(len(self._select(rows, "2026-07-01", "2026-07-31")), 1)

    def test_four_hours_one_minute_does_not_connect(self):
        rows = connected_boundary_pair(241)

        self.assertEqual(len(self._select(rows, "2026-06-01", "2026-06-30")), 1)
        self.assertEqual(len(self._select(rows, "2026-07-01", "2026-07-31")), 1)

    def test_crew_change_starts_a_new_duty(self):
        rows = connected_boundary_pair(180, second_codes=("A", "C"))

        self.assertEqual(len(self._select(rows, "2026-06-01", "2026-06-30")), 1)
        self.assertEqual(len(self._select(rows, "2026-07-01", "2026-07-31")), 1)

    def test_crew_order_does_not_change_deterministic_set_comparison(self):
        rows = connected_boundary_pair(180, reverse_second_order=True)

        self.assertEqual(len(self._select(rows, "2026-06-01", "2026-06-30")), 2)
        self.assertEqual(self._select(rows, "2026-07-01", "2026-07-31"), [])

    def test_verified_live_boundary_a_is_june_only(self):
        june = self._select(LIVE_BOUNDARY_A, "2026-06-01", "2026-06-30")
        july = self._select(LIVE_BOUNDARY_A, "2026-07-01", "2026-07-31")

        self.assertEqual([row["flightNo"] for row in june], ["RSX331", "RSX332"])
        self.assertEqual(july, [])

    def test_verified_live_boundary_b_rolls_on_to_next_utc_day_and_is_june_only(self):
        june = self._select(LIVE_BOUNDARY_B, "2026-06-01", "2026-06-30")
        july = self._select(LIVE_BOUNDARY_B, "2026-07-01", "2026-07-31")

        self.assertEqual([row["flightNo"] for row in june], ["RSX123", "RSX124"])
        self.assertEqual(july, [])

    def test_psn_members_are_excluded_from_operating_crew_set_comparison(self):
        rows = (
            report_leg(
                "RSX-PSN-OUT",
                flight_date="30-06-2026",
                off="20:00",
                on="23:00",
                crew_codes=("OPERATING", "PSN-ONE"),
                positions=("CPT", "PSN"),
                block_time="03:00",
            ),
            report_leg(
                "RSX-PSN-BACK",
                flight_date="01-07-2026",
                off="00:00",
                on="02:00",
                crew_codes=("PSN-TWO", "OPERATING"),
                positions=("PSN", "CPT"),
                block_time="02:00",
            ),
        )

        self.assertEqual(len(self._select(rows, "2026-06-01", "2026-06-30")), 2)
        self.assertEqual(self._select(rows, "2026-07-01", "2026-07-31"), [])

    def test_negative_break_does_not_connect_overlapping_legs(self):
        rows = (
            report_leg(
                "RSX-OVERLAP-ONE",
                flight_date="30-06-2026",
                off="23:00",
                on="02:00",
                crew_codes=("A", "B"),
                positions=("CPT", "FO"),
                block_time="03:00",
            ),
            report_leg(
                "RSX-OVERLAP-TWO",
                flight_date="01-07-2026",
                off="01:00",
                on="03:00",
                crew_codes=("A", "B"),
                positions=("CPT", "FO"),
                block_time="02:00",
            ),
        )

        self.assertEqual(len(self._select(rows, "2026-06-01", "2026-06-30")), 1)
        self.assertEqual(len(self._select(rows, "2026-07-01", "2026-07-31")), 1)

    def test_normalized_live_window_is_timezone_aware_utc(self):
        from datetime import timezone
        from backend.statistics.crew_hours.domain import normalize_report_row

        normalized = normalize_report_row(LIVE_BOUNDARY_B[0])

        self.assertIs(normalized.off_utc.tzinfo, timezone.utc)
        self.assertIs(normalized.on_utc.tzinfo, timezone.utc)
        self.assertEqual(normalized.off_utc.isoformat(), "2026-06-30T23:50:00+00:00")
        self.assertEqual(normalized.on_utc.isoformat(), "2026-07-01T02:25:00+00:00")


if __name__ == "__main__":
    unittest.main()

"""The member-duty Heavy allowance model, pinned to the July 2026 evidence.

Every case here replicates a real member shape from the manual reference
workbook that validated the model 54/55 (names replaced by codes).
"""

import unittest

from backend.statistics.crew_hours.allowance import (
    CREDIT_LEON,
    CREDIT_SWAP,
    AllowanceLeg,
    compute_member_credits,
)


def leg(key, date, start, end, position, *, leon=None, adep="HRG", ades="SSH"):
    return AllowanceLeg(
        key=key,
        flight_date=date,
        start_time=start,
        end_time=end,
        position=position,
        leon_heavy=leon,
        departure_airport=adep,
        arrival_airport=ades,
    )


class TestSwapCredit(unittest.TestCase):
    def test_operate_out_ride_pad_back_is_one_credit_painted_on_both_legs(self):
        # Donia's shape: FO out, PAD home, one duty -> exactly 1, both legs lit.
        result = compute_member_credits([
            leg("a", "10-06-2026", "14:25", "20:40", "FO", adep="HRG", ades="LIS"),
            leg("b", "10-06-2026", "21:50", "03:35", "PAD", adep="LIS", ades="HRG"),
        ])
        self.assertEqual(result.credits, 1)
        self.assertEqual(result.duties[0].source, CREDIT_SWAP)
        self.assertEqual(result.by_leg["a"], (True, CREDIT_SWAP))
        self.assertEqual(result.by_leg["b"], (True, CREDIT_SWAP))

    def test_ride_first_then_operate_is_the_same_credit(self):
        # Ziad Mohab's shape: PAD out, CPT home (direction is irrelevant).
        result = compute_member_credits([
            leg("a", "02-07-2026", "14:25", "19:50", "PAD", adep="HRG", ades="VKO"),
            leg("b", "02-07-2026", "21:20", "03:20", "CPT", adep="VKO", ades="HRG"),
        ])
        self.assertEqual(result.credits, 1)

    def test_two_swap_duties_are_two_credits(self):
        # John Ashraf's July: exactly 2 in the sheet, from 2 swap duties.
        result = compute_member_credits([
            leg("a1", "15-07-2026", "12:10", "12:55", "FO"),
            leg("a2", "15-07-2026", "14:10", "20:35", "FO", adep="HRG", ades="LIS"),
            leg("a3", "15-07-2026", "22:30", "04:10", "PAD", adep="LIS", ades="HRG"),
            leg("b1", "28-07-2026", "19:05", "00:55", "FO", adep="SSH", ades="ALA"),
            leg("b2", "29-07-2026", "02:10", "08:45", "PAD", adep="ALA", ades="SSH"),
        ])
        self.assertEqual(result.credits, 2)

    def test_operate_both_legs_without_riding_is_no_credit(self):
        # The 23-06 pair the owner asked about (RSX8891+RSX6083): the sheet
        # gave the all-operating member nothing for the identical July shape.
        result = compute_member_credits([
            leg("a", "23-06-2026", "05:30", "06:10", "FO", adep="HRG", ades="SSH"),
            leg("b", "23-06-2026", "07:00", "13:00", "FO", adep="SSH", ades="OPO"),
        ])
        self.assertEqual(result.credits, 0)
        self.assertIn("no PAD leg", result.duties[0].reason)

    def test_pad_only_duty_is_no_credit(self):
        result = compute_member_credits([
            leg("a", "01-07-2026", "00:00", "05:40", "PAD", adep="SVX", ades="SSH"),
        ])
        self.assertEqual(result.credits, 0)
        self.assertIn("rode PAD only", result.duties[0].reason)


class TestLeonCredit(unittest.TestCase):
    def test_leon_augmented_pair_is_one_credit_per_duty_not_per_leg(self):
        # The CGN 3-pilot rotations: LEON marks both legs; the sheet pays 1.
        result = compute_member_credits([
            leg("a", "10-07-2026", "17:05", "22:15", "CPT2", leon=True, adep="HRG", ades="CGN"),
            leg("b", "10-07-2026", "23:40", "04:40", "CPT2", leon=True, adep="CGN", ades="HRG"),
        ])
        self.assertEqual(result.credits, 1)
        self.assertEqual(result.duties[0].source, CREDIT_LEON)

    def test_leon_false_never_credits_by_itself(self):
        result = compute_member_credits([
            leg("a", "13-07-2026", "14:30", "20:50", "FO", leon=False, adep="HRG", ades="OPO"),
        ])
        self.assertEqual(result.credits, 0)


class TestNeutralSlots(unittest.TestCase):
    def test_a_short_psn_shuttle_neither_operates_nor_rides(self):
        # Karim Fekry's 11-07: a 0:40 PSN base shuttle + operated KRR pair ->
        # NOT credited (the July sheet paid him nothing for this duty).
        result = compute_member_credits([
            leg("a", "11-07-2026", "06:35", "07:15", "PSN"),
            leg("b", "11-07-2026", "09:40", "12:50", "FO", adep="SSH", ades="KRR"),
            leg("c", "11-07-2026", "15:00", "18:20", "FO", adep="KRR", ades="SSH"),
        ])
        self.assertEqual(result.credits, 0)

    def test_psn_on_a_rotation_scale_sector_rides(self):
        # Owner case 29-06 (Ahmed Kamel): PSN HRG->OPO 5:45 out, FO back ->
        # the swap credit, painted on both legs.
        result = compute_member_credits([
            leg("a", "29-06-2026", "14:35", "20:20", "PSN", adep="HRG", ades="OPO"),
            leg("b", "29-06-2026", "21:25", "03:10", "FO", adep="OPO", ades="HRG"),
        ])
        self.assertEqual(result.credits, 1)
        self.assertEqual(result.duties[0].source, CREDIT_SWAP)
        self.assertEqual(result.by_leg["a"], (True, CREDIT_SWAP))
        self.assertEqual(result.by_leg["b"], (True, CREDIT_SWAP))

    def test_operate_then_long_psn_back_rides_too(self):
        # Owner case 09-06 (Ahmed Tahoon): CPT out HRG->OPO, PSN 5:20 back.
        result = compute_member_credits([
            leg("a", "09-06-2026", "07:15", "13:20", "CPT", adep="HRG", ades="OPO"),
            leg("b", "09-06-2026", "14:45", "20:05", "PSN", adep="OPO", ades="SSH"),
        ])
        self.assertEqual(result.credits, 1)

    def test_obs_pair_is_no_credit_even_when_a_rotation_exists(self):
        # Amro Nasef's OGZ pair: sheet blank; observers never earn.
        result = compute_member_credits([
            leg("a", "13-07-2026", "09:25", "12:35", "OBS", adep="SSH", ades="OGZ"),
            leg("b", "13-07-2026", "14:50", "18:20", "OBS", adep="OGZ", ades="SSH"),
        ])
        self.assertEqual(result.credits, 0)

    def test_trainee_slots_earn_nothing_without_any_rank_rule(self):
        result = compute_member_credits([
            leg("a", "05-07-2026", "10:00", "12:00", "SP"),
            leg("b", "05-07-2026", "13:00", "15:00", "OPS"),
        ])
        self.assertEqual(result.credits, 0)


class TestEvnVeto(unittest.TestCase):
    def test_evn_legs_contribute_nothing_in_either_role(self):
        # Operated + PAD across EVN sectors: still nothing (owner absolute).
        result = compute_member_credits([
            leg("a", "01-07-2026", "23:05", "02:00", "FO", adep="SSH", ades="EVN"),
            leg("b", "02-07-2026", "03:10", "06:30", "PAD", adep="EVN", ades="SSH"),
        ])
        self.assertEqual(result.credits, 0)

    def test_evn_in_icao_form_is_the_same_airport(self):
        result = compute_member_credits([
            leg("a", "01-07-2026", "23:05", "02:00", "FO", adep="HESH", ades="UDYZ"),
            leg("b", "02-07-2026", "03:10", "06:30", "PAD", adep="UDYZ", ades="HESH"),
        ])
        self.assertEqual(result.credits, 0)


class TestDutyBoundaries(unittest.TestCase):
    def test_a_four_hour_break_splits_the_duty_strictly(self):
        # 4:00 exactly rejects -> two duties, each missing the other role.
        result = compute_member_credits([
            leg("a", "10-07-2026", "08:00", "10:00", "FO"),
            leg("b", "10-07-2026", "14:00", "16:00", "PAD"),
        ])
        self.assertEqual(result.credits, 0)
        self.assertEqual(len(result.duties), 2)

    def test_a_359_break_keeps_one_duty(self):
        result = compute_member_credits([
            leg("a", "10-07-2026", "08:00", "10:00", "FO"),
            leg("b", "10-07-2026", "13:59", "16:00", "PAD"),
        ])
        self.assertEqual(result.credits, 1)

    def test_crossing_midnight_is_one_duty_not_two_days(self):
        result = compute_member_credits([
            leg("a", "16-06-2026", "17:15", "22:35", "FO", adep="SSH", ades="SVX"),
            leg("b", "16-06-2026", "23:50", "06:00", "PAD", adep="SVX", ades="SSH"),
        ])
        self.assertEqual(result.credits, 1)
        self.assertEqual(result.duties[0].anchor_utc_date, "2026-06-16")

    def test_duty_is_attributed_to_its_anchor_month(self):
        # Salah Hesham's 30-06 -> 01-07 SVX duty: July's sheet did not pay it.
        result = compute_member_credits(
            [
                leg("a", "30-06-2026", "17:15", "23:00", "FO", adep="SSH", ades="SVX"),
                leg("b", "01-07-2026", "00:00", "05:40", "PAD", adep="SVX", ades="SSH"),
            ],
            window_start="2026-07-01",
            window_end="2026-07-31",
        )
        self.assertEqual(result.credits, 0)
        self.assertIn("outside the requested window", result.duties[0].reason)

    def test_a_duty_anchored_on_the_last_day_of_the_window_counts(self):
        result = compute_member_credits(
            [
                leg("a", "31-07-2026", "17:20", "22:45", "FO", adep="HRG", ades="LED"),
                leg("b", "31-07-2026", "23:50", "05:20", "PAD", adep="LED", ades="HRG"),
            ],
            window_start="2026-07-01",
            window_end="2026-07-31",
        )
        self.assertEqual(result.credits, 1)

    def test_iso_timestamps_are_accepted_too(self):
        result = compute_member_credits([
            leg("a", None, "2026-06-10T14:25:00Z", "2026-06-10T20:40:00Z", "FO"),
            leg("b", None, "2026-06-10T21:50:00Z", "2026-06-11T03:35:00Z", "PAD"),
        ])
        self.assertEqual(result.credits, 1)

    def test_unusable_times_exclude_the_leg_without_crashing(self):
        result = compute_member_credits([
            leg("a", None, None, None, "FO"),
            leg("b", "10-07-2026", "08:00", "10:00", "PAD"),
        ])
        self.assertEqual(result.credits, 0)
        self.assertNotIn("a", result.by_leg)


class TestServiceWiring(unittest.TestCase):
    """The report response carries H.C and paints both legs of a credited duty."""

    def _response(self, rows):
        from backend.statistics.crew_hours.augmented import AugmentedIndex
        from backend.statistics.crew_hours.crew_context import CrewContextIndex
        from backend.statistics.crew_hours.mcp_report import OfficialMcpReport
        from backend.statistics.crew_hours.service import _build_mcp_report_response

        totals = {code: "10:00" for row in rows for code in row["crew_codes"]}
        return _build_mcp_report_response(
            OfficialMcpReport(totals, rows),
            from_date="2026-06-01",
            to_date="2026-06-30",
            position="All",
            crew_member=None,
            augmented_index=AugmentedIndex(True, {}, 0, 0, {}),
            crew_context_index=CrewContextIndex(False, {}),
        )

    @staticmethod
    def _row(uid, number, adep, ades, date, start, end, codes, positions):
        return {
            "scope_row_unique_id": f"row-{uid}",
            "unique_id": uid,
            "flightNo": number,
            "crew_codes": codes,
            "crew_names": [f"Crew {c}" for c in codes],
            "crew_position_names": positions,
            "acftType": "B738 - 737-800",
            "blockTimeJourneyLog": "01:30",
            "jl_adep_preferred_code": adep,
            "jl_ades_preferred_code": ades,
            "date_STD_log_UTC": date,
            "JL_STD_UTC": start,
            "JL_STA_UTC": end,
        }

    def test_the_owner_complaint_donia_both_legs_credited_and_hc_is_one(self):
        # 10-06: FO out HRG->LIS, PAD home LIS->HRG. The old per-leg verdict
        # split them (No / Yes+badge); the allowance paints BOTH and H.C = 1.
        rows = [
            self._row(901, "RSX6077", "HRG", "LIS", "10-06-2026", "14:25", "20:40",
                      ["DON"], ["FO"]),
            self._row(902, "RSX6078", "LIS", "HRG", "10-06-2026", "21:50", "03:35",
                      ["DON"], ["PAD"]),
        ]
        member = self._response(rows).crew_members[0]

        self.assertEqual(member.heavy_credits, 1)
        by_number = {f.flight_number: f for f in member.flights}
        for number in ("RSX6077", "RSX6078"):
            self.assertIs(by_number[number].duty_credit, True, number)
            self.assertEqual(by_number[number].credit_source, "OPERATE_PLUS_RIDE")

    def test_the_owner_complaint_all_operating_pair_is_uncredited_for_both(self):
        # 23-06 RSX8891 + RSX6083: operated both, no PAD, LEON silent ->
        # symmetric No-credit (the July sheet paid nothing for this shape).
        rows = [
            self._row(911, "RSX8891", "HRG", "SSH", "23-06-2026", "05:30", "06:10",
                      ["C1"], ["FO"]),
            self._row(912, "RSX6083", "SSH", "OPO", "23-06-2026", "07:00", "13:00",
                      ["C1"], ["FO"]),
        ]
        member = self._response(rows).crew_members[0]

        self.assertEqual(member.heavy_credits, 0)
        for flight in member.flights:
            self.assertIs(flight.duty_credit, False, flight.flight_number)
            self.assertIsNone(flight.credit_source)


if __name__ == "__main__":
    unittest.main()

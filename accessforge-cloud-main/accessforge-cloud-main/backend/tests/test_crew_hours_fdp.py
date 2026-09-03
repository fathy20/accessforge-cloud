"""The regulatory FDP model (fdp.py), pinned to the owner's document and the
ten owner cases with real times.

Every golden case below is a duty the owner has already ruled on (June/July
2026 evidence, see test_crew_hours_allowance.py and
test_crew_hours_heavy_rules.py). The FDP inequality must reproduce the ruling
with no airport special case, no sector minimum, and no link constant.
"""

import unittest
from datetime import datetime, timedelta, timezone

from backend.statistics.crew_hours.allowance import AllowanceLeg
from backend.statistics.crew_hours.fdp import (
    BAND_06_08,
    BAND_08_15,
    BAND_15_22,
    BAND_22_06,
    TABLES_ECAR_2016,
    TABLES_OM_2009,
    assess,
    assess_member,
    assess_rotation,
    egypt_utc_offset,
    member_window,
    relief_cap,
    relief_extension,
    rotation_window,
    split_duty_extension,
    start_band,
    tables_for,
)


def leg(key, date, start, end, position="FO", *, adep="HRG", ades="SSH", leon=None):
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


def hm(text: str) -> timedelta:
    hours, minutes = text.split(":")
    return timedelta(hours=int(hours), minutes=int(minutes))


class TestOwnerCasesReproduce(unittest.TestCase):
    """Rotation view: every leg a sector, 1:30 before / 0:30 after."""

    def _check(self, legs, *, planned, band, sectors, limit, heavy):
        result = assess_rotation(legs)
        self.assertIsNotNone(result)
        self.assertEqual(result.window.planned, hm(planned), "planned FDP")
        self.assertEqual(result.band, band)
        self.assertEqual(result.window.sectors, sectors)
        self.assertEqual(result.limit, hm(limit), "table limit")
        self.assertIs(result.needs_augmentation, heavy)
        return result

    def test_svx_16_06_is_over_the_limit(self):
        result = self._check(
            [
                leg("a", "16-06-2026", "17:15", "22:35", adep="SSH", ades="SVX"),
                leg("b", "16-06-2026", "23:50", "06:00", "PAD", adep="SVX", ades="SSH"),
            ],
            planned="14:45", band=BAND_15_22, sectors=2, limit="12:15", heavy=True,
        )
        self.assertEqual(result.margin, hm("2:30"))

    def test_cgn_10_07_three_pilot_sector_is_over_the_limit(self):
        self._check(
            [
                leg("a", "10-07-2026", "17:05", "22:15", "CPT2", adep="HRG", ades="CGN", leon=True),
                leg("b", "10-07-2026", "23:40", "04:40", "CPT2", adep="CGN", ades="HRG", leon=True),
            ],
            planned="13:35", band=BAND_15_22, sectors=2, limit="12:15", heavy=True,
        )

    def test_lis_10_06_swap_rotation_is_over_the_limit(self):
        self._check(
            [
                leg("a", "10-06-2026", "14:25", "20:40", adep="HRG", ades="LIS"),
                leg("b", "10-06-2026", "21:50", "03:35", "PAD", adep="LIS", ades="HRG"),
            ],
            planned="15:10", band=BAND_15_22, sectors=2, limit="12:15", heavy=True,
        )

    def test_vko_02_07_ride_out_operate_back_is_over_the_limit(self):
        self._check(
            [
                leg("a", "02-07-2026", "14:25", "19:50", "PAD", adep="HRG", ades="VKO"),
                leg("b", "02-07-2026", "21:20", "03:20", "CPT", adep="VKO", ades="HRG"),
            ],
            planned="14:55", band=BAND_15_22, sectors=2, limit="12:15", heavy=True,
        )

    def test_ala_and_led_are_over_the_limit(self):
        self._check(
            [
                leg("b1", "28-07-2026", "19:05", "00:55", adep="SSH", ades="ALA"),
                leg("b2", "29-07-2026", "02:10", "08:45", "PAD", adep="ALA", ades="SSH"),
            ],
            planned="15:40", band=BAND_15_22, sectors=2, limit="12:15", heavy=True,
        )
        self._check(
            [
                leg("a", "31-07-2026", "17:20", "22:45", adep="HRG", ades="LED"),
                leg("b", "31-07-2026", "23:50", "05:20", "PAD", adep="LED", ades="HRG"),
            ],
            planned="14:00", band=BAND_15_22, sectors=2, limit="12:15", heavy=True,
        )

    def test_evn_01_07_is_within_the_night_limit(self):
        result = self._check(
            [
                leg("a", "01-07-2026", "23:05", "02:00", adep="SSH", ades="EVN"),
                leg("b", "02-07-2026", "03:10", "06:30", "PAD", adep="EVN", ades="SSH"),
            ],
            planned="9:25", band=BAND_22_06, sectors=2, limit="10:15", heavy=False,
        )
        self.assertEqual(result.margin, -hm("0:50"))

    def test_krr_11_07_is_within_the_daytime_limit(self):
        self._check(
            [
                leg("b", "11-07-2026", "09:40", "12:50", adep="SSH", ades="KRR"),
                leg("c", "11-07-2026", "15:00", "18:20", adep="KRR", ades="SSH"),
            ],
            planned="10:40", band=BAND_08_15, sectors=2, limit="13:15", heavy=False,
        )

    def test_opo_23_06_without_the_return_is_within_the_limit(self):
        self._check(
            [
                leg("shuttle", "23-06-2026", "05:30", "06:10", adep="HRG", ades="SSH"),
                leg("out", "23-06-2026", "07:00", "13:00", adep="SSH", ades="OPO"),
            ],
            planned="9:30", band=BAND_06_08, sectors=2, limit="12:15", heavy=False,
        )

    def test_opo_23_06_with_the_return_is_over_the_three_sector_limit(self):
        self._check(
            [
                leg("shuttle", "23-06-2026", "05:30", "06:10", adep="HRG", ades="SSH"),
                leg("out", "23-06-2026", "07:00", "13:00", adep="SSH", ades="OPO"),
                leg("back", "23-06-2026", "14:15", "20:00", adep="OPO", ades="SSH"),
            ],
            planned="16:30", band=BAND_06_08, sectors=3, limit="11:30", heavy=True,
        )


class TestMemberWindow(unittest.TestCase):
    """A member's own FDP: rides before count inside it (not as sectors),
    rides after are duty, not FDP."""

    def test_ride_before_operating_extends_the_member_fdp_but_is_not_a_sector(self):
        window = member_window([
            leg("a", "02-07-2026", "14:25", "19:50", "PAD", adep="HRG", ades="VKO"),
            leg("b", "02-07-2026", "21:20", "03:20", "CPT", adep="VKO", ades="HRG"),
        ])
        self.assertEqual(window.planned, hm("14:55"))
        self.assertEqual(window.sectors, 1)
        self.assertEqual(window.leg_keys, ("a", "b"))

    def test_ride_after_operating_is_outside_the_member_fdp(self):
        window = member_window([
            leg("a", "10-06-2026", "14:25", "20:40", "FO", adep="HRG", ades="LIS"),
            leg("b", "10-06-2026", "21:50", "03:35", "PAD", adep="LIS", ades="HRG"),
        ])
        # Operated one sector: 12:55 -> 21:10. Legal for a two-pilot crew —
        # which is exactly why the operator swaps crews instead of augmenting.
        self.assertEqual(window.planned, hm("8:15"))
        self.assertEqual(window.sectors, 1)
        self.assertIs(assess(window).needs_augmentation, False)
        # While the rotation itself is not:
        self.assertIs(assess(rotation_window([
            leg("a", "10-06-2026", "14:25", "20:40", "FO", adep="HRG", ades="LIS"),
            leg("b", "10-06-2026", "21:50", "03:35", "PAD", adep="LIS", ades="HRG"),
        ])).needs_augmentation, True)

    def test_neutral_positions_and_pure_riders_have_no_member_window(self):
        self.assertIsNone(member_window([leg("a", "13-07-2026", "09:25", "12:35", "OBS")]))
        self.assertIsNone(member_window([leg("a", "13-07-2026", "09:25", "12:35", "PAD")]))
        self.assertIsNone(assess_member([leg("a", "13-07-2026", "09:25", "12:35", "PSN")]))

    def test_unparseable_times_are_skipped_and_empty_duty_has_no_window(self):
        self.assertIsNone(rotation_window([leg("a", "13-07-2026", "", "12:35")]))
        self.assertIsNone(assess_rotation([]))


class TestBandsAndLocalTime(unittest.TestCase):
    def test_egypt_offset_follows_the_2023_dst_rule(self):
        self.assertEqual(egypt_utc_offset(datetime(2026, 7, 1, tzinfo=timezone.utc)), timedelta(hours=3))
        self.assertEqual(egypt_utc_offset(datetime(2026, 1, 15, tzinfo=timezone.utc)), timedelta(hours=2))
        # 2026: last Friday of April is the 24th; last Thursday of October the 29th.
        self.assertEqual(egypt_utc_offset(datetime(2026, 4, 23, 21, 59, tzinfo=timezone.utc)), timedelta(hours=2))
        self.assertEqual(egypt_utc_offset(datetime(2026, 4, 23, 22, 0, tzinfo=timezone.utc)), timedelta(hours=3))
        self.assertEqual(egypt_utc_offset(datetime(2026, 10, 29, 20, 59, tzinfo=timezone.utc)), timedelta(hours=3))
        self.assertEqual(egypt_utc_offset(datetime(2026, 10, 29, 21, 0, tzinfo=timezone.utc)), timedelta(hours=2))
        self.assertEqual(egypt_utc_offset(datetime(2020, 7, 1, tzinfo=timezone.utc)), timedelta(hours=2))

    def test_band_edges(self):
        def band(hh, mm):
            return start_band(datetime(2026, 7, 1, hh, mm))

        self.assertEqual(band(5, 59), BAND_22_06)
        self.assertEqual(band(6, 0), BAND_06_08)
        self.assertEqual(band(7, 59), BAND_06_08)
        self.assertEqual(band(8, 0), BAND_08_15)
        self.assertEqual(band(14, 59), BAND_08_15)
        self.assertEqual(band(15, 0), BAND_15_22)
        self.assertEqual(band(21, 59), BAND_15_22)
        self.assertEqual(band(22, 0), BAND_22_06)

    def test_summer_and_winter_move_the_same_utc_start_across_a_band_edge(self):
        # 05:00Z is 08:00 local in summer (band 08:00-14:59) and 07:00 local
        # in winter (band 06:00-07:59): one hour of allowed FDP hinges on it.
        summer = assess_rotation([leg("a", "01-07-2026", "06:30", "10:00"), leg("b", "01-07-2026", "11:00", "14:30")])
        winter = assess_rotation([leg("a", "15-01-2026", "06:30", "10:00"), leg("b", "15-01-2026", "11:00", "14:30")])
        self.assertEqual(summer.band, BAND_08_15)
        self.assertEqual(summer.limit, hm("13:15"))
        self.assertEqual(winter.band, BAND_06_08)
        self.assertEqual(winter.limit, hm("12:15"))

    def test_explicit_local_offset_overrides_egypt(self):
        window = rotation_window([leg("a", "01-07-2026", "06:30", "10:00")])
        self.assertEqual(assess(window, local_offset=timedelta(hours=5)).band, BAND_08_15)   # 10:00 local
        self.assertEqual(assess(window, local_offset=timedelta(hours=0)).band, BAND_22_06)   # 05:00 local


class TestTables(unittest.TestCase):
    def test_the_two_published_versions_differ_exactly_where_the_documents_do(self):
        for band in (BAND_06_08, BAND_15_22, BAND_22_06):
            self.assertEqual(TABLES_OM_2009.table_a[band], TABLES_ECAR_2016.table_a[band], band)
        om, ecar = TABLES_OM_2009.table_a[BAND_08_15], TABLES_ECAR_2016.table_a[BAND_08_15]
        self.assertEqual(om[:2], ecar[:2])                         # 14:00, 13:15 agree
        self.assertEqual(om[2], hm("12:30"))                       # 3 sectors: OM 12½
        self.assertEqual(ecar[2], hm("11:45"))                     #            ECAR 11:45
        self.assertEqual(TABLES_OM_2009.table_b, TABLES_ECAR_2016.table_b)

    def test_sector_count_clamps_to_the_last_column(self):
        self.assertEqual(TABLES_OM_2009.table_a_limit(BAND_08_15, 8), hm("9:00"))
        self.assertEqual(TABLES_OM_2009.table_a_limit(BAND_08_15, 12), hm("9:00"))
        self.assertEqual(TABLES_OM_2009.table_a_limit(BAND_08_15, 0), hm("14:00"))
        self.assertEqual(TABLES_OM_2009.table_b_limit("over_30", 9), hm("9:00"))

    def test_tables_for_selects_by_version_and_rejects_unknown(self):
        self.assertIs(tables_for(None), TABLES_OM_2009)
        self.assertIs(tables_for("ECAR-2016"), TABLES_ECAR_2016)
        with self.assertRaises(ValueError):
            tables_for("cap-371")

    def test_table_b_by_preceding_rest_and_the_under_18_difference(self):
        window = rotation_window([leg("a", "01-07-2026", "06:30", "10:00"), leg("b", "01-07-2026", "11:00", "14:30")])
        over_30 = assess(window, acclimatised=False, preceding_rest=timedelta(hours=35))
        between = assess(window, acclimatised=False, preceding_rest=timedelta(hours=20))
        self.assertEqual((over_30.table, over_30.limit), ("B", hm("12:15")))
        self.assertEqual((between.table, between.limit), ("B", hm("11:15")))
        # Rest under 18 h: the 2009 OM has no row (not rosterable); ECAR 2016
        # labels its first row "up to 18 or over 30".
        om = assess(window, acclimatised=False, preceding_rest=timedelta(hours=10))
        ecar = assess(window, acclimatised=False, preceding_rest=timedelta(hours=10), tables=TABLES_ECAR_2016)
        self.assertIsNone(om.limit)
        self.assertIsNone(om.needs_augmentation)
        self.assertEqual(ecar.limit, hm("12:15"))

    def test_not_acclimatised_without_rest_data_falls_back_to_table_a_and_says_so(self):
        window = rotation_window([leg("a", "01-07-2026", "06:30", "10:00")])
        result = assess(window, acclimatised=False)
        self.assertEqual(result.table, "A")
        self.assertIn("Table A assumed", result.limit_reason)

    def test_cabin_crew_gets_one_more_hour(self):
        window = rotation_window([
            leg("a", "16-06-2026", "17:15", "22:35", adep="SSH", ades="SVX"),
            leg("b", "16-06-2026", "23:50", "06:00", adep="SVX", ades="SSH"),
        ])
        self.assertEqual(assess(window, crew_type="cabin").limit, hm("13:15"))
        self.assertIs(assess(window, crew_type="cabin").needs_augmentation, True)


class TestExtensions(unittest.TestCase):
    def test_in_flight_relief_extension_and_caps(self):
        self.assertEqual(relief_extension(hm("2:59"), in_bunk=True), timedelta(0))
        self.assertEqual(relief_extension(hm("5:00"), in_bunk=True), hm("2:30"))
        self.assertEqual(relief_extension(hm("6:00"), in_bunk=False), hm("2:00"))
        self.assertEqual(relief_cap(in_bunk=True), hm("18:00"))
        self.assertEqual(relief_cap(in_bunk=False), hm("15:00"))
        self.assertEqual(relief_cap(in_bunk=True, crew_type="cabin"), hm("19:00"))
        self.assertEqual(relief_cap(in_bunk=False, crew_type="cabin"), hm("16:00"))

    def test_split_duty_extension_window(self):
        self.assertEqual(split_duty_extension(hm("2:59")), timedelta(0))
        self.assertEqual(split_duty_extension(hm("3:00")), hm("1:30"))
        self.assertEqual(split_duty_extension(hm("4:00")), hm("2:00"))
        self.assertEqual(split_duty_extension(hm("10:00")), hm("5:00"))
        self.assertEqual(split_duty_extension(hm("10:01")), timedelta(0))


class TestTrace(unittest.TestCase):
    def test_trace_names_the_rule_the_limit_and_says_it_is_shadow_only(self):
        result = assess_rotation([
            leg("a", "16-06-2026", "17:15", "22:35", adep="SSH", ades="SVX"),
            leg("b", "16-06-2026", "23:50", "06:00", "PAD", adep="SVX", ades="SSH"),
        ])
        names = [item.step for item in result.trace]
        self.assertEqual(names, ["FDP_SHADOW_WINDOW", "FDP_SHADOW_LIMIT", "FDP_SHADOW_VERDICT"])
        window, limit, verdict = result.trace
        self.assertEqual(window.inputs["report_utc"], "2026-06-16T15:45Z")
        self.assertEqual(window.inputs["off_duty_utc"], "2026-06-17T06:30Z")
        self.assertEqual(window.inputs["local_start"], "18:45 (UTC+3)")
        self.assertEqual(limit.inputs["tables_version"], "om-2009")
        self.assertEqual(verdict.inputs["margin"], "2:30")
        self.assertIn("needs augmentation", verdict.outcome)
        self.assertIn("shadow only", verdict.inputs["note"])


if __name__ == "__main__":
    unittest.main()


class TestServiceShadow(unittest.TestCase):
    """The report paints the assessment beside the verdict and never through it."""

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

    @staticmethod
    def _response(rows):
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

    def test_both_legs_of_a_duty_carry_the_same_shadow_and_the_trace_steps(self):
        member = self._response([
            self._row(901, "RSX6077", "HRG", "LIS", "10-06-2026", "14:25", "20:40", ["DON"], ["FO"]),
            self._row(902, "RSX6078", "LIS", "HRG", "10-06-2026", "21:50", "03:35", ["DON"], ["PAD"]),
        ]).crew_members[0]
        by_number = {f.flight_number: f for f in member.flights}

        for number in ("RSX6077", "RSX6078"):
            shadow = by_number[number].fdp_shadow
            self.assertIsNotNone(shadow, number)
            self.assertEqual(shadow.planned, "15:10")
            self.assertEqual(shadow.limit, "12:15")
            self.assertEqual(shadow.margin, "2:55")
            self.assertEqual(shadow.sectors, 2)
            self.assertEqual(shadow.band, "15:00-21:59")
            self.assertEqual(shadow.tables_version, "om-2009")
            self.assertIs(shadow.needs_augmentation, True)
            self.assertEqual(sorted(shadow.duty_leg_keys), ["row-901", "row-902"])
            names = [item.step for item in by_number[number].heavy_trace]
            self.assertEqual(names[-3:], ["FDP_SHADOW_WINDOW", "FDP_SHADOW_LIMIT", "FDP_SHADOW_VERDICT"])
            self.assertIn("VERDICT", names[:-3], "the existing verdict step still precedes the shadow")

        # The shadow reports agreement but never sets the verdict or the credit.
        for flight in member.flights:
            if flight.effective_heavy is None:
                self.assertIsNone(flight.fdp_shadow.agrees_with_verdict)
            else:
                self.assertEqual(flight.fdp_shadow.agrees_with_verdict, flight.effective_heavy is True)
        self.assertEqual(member.heavy_credits, 1)
        self.assertIs(by_number["RSX6077"].duty_credit, True)

    def test_legs_without_times_get_no_shadow_and_keep_their_verdict_fields(self):
        row = self._row(903, "RSX121", "SSH", "EVN", "20-06-2026", "", "", ["DON"], ["FO"])
        flight = self._response([row]).crew_members[0].flights[0]
        self.assertIsNone(flight.fdp_shadow)
        self.assertEqual(flight.heavy_reason, "EVN_AIRPORT")
        self.assertIs(flight.effective_heavy, False)
        self.assertNotIn("FDP_SHADOW_VERDICT", [item.step for item in flight.heavy_trace])

    def test_table_version_is_selectable_by_environment(self):
        import os
        from unittest import mock

        rows = [
            self._row(904, "RSX1", "HRG", "KRR", "11-07-2026", "09:40", "12:50", ["DON"], ["FO"]),
            self._row(905, "RSX2", "KRR", "HRG", "11-07-2026", "15:00", "18:20", ["DON"], ["FO"]),
            self._row(906, "RSX3", "HRG", "SSH", "11-07-2026", "19:00", "20:00", ["DON"], ["FO"]),
        ]
        # Three sectors from 08:00-14:59: the one row where the documents differ.
        with mock.patch.dict(os.environ, {"CREW_HOURS_FDP_TABLES": "ecar-2016"}):
            ecar = self._response(rows).crew_members[0].flights[0].fdp_shadow
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CREW_HOURS_FDP_TABLES", None)
            om = self._response(rows).crew_members[0].flights[0].fdp_shadow
        self.assertEqual((om.tables_version, om.limit), ("om-2009", "12:30"))
        self.assertEqual((ecar.tables_version, ecar.limit), ("ecar-2016", "11:45"))

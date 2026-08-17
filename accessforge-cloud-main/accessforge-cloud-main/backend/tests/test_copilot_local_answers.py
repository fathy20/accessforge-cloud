import unittest
from datetime import date

from backend.copilot.local_answers import (
    INTENT_HEAVY,
    INTENT_HOURS,
    INTENT_ROSTER,
    answer_locally,
    detect_intent,
    resolve_period,
)
from backend.statistics.crew_hours.mcp_report import OfficialMcpReport

TODAY = date(2026, 6, 15)


def _report() -> OfficialMcpReport:
    return OfficialMcpReport(
        # "HAS" is a real-shaped LEON crew code that collides with an English word.
        {"HAS": "74:10", "KHD": "12:30"},
        [
            {
                "scope_row_unique_id": "row-1",
                "unique_id": 1,
                "crew_codes": ["HAS", "KHD"],
                "crew_names": ["Hesham Abd ElSamad", "Khaled Darwish"],
                "crew_position_names": ["CPT", "FO"],
                "flightNo": "RSX431",
                "blockTimeJourneyLog": "01:30",
            }
        ],
        {"HAS": 4450, "KHD": 750},
    )


def _fetch(_from_date, _to_date):
    return _report()


class TestIntentAndPeriod(unittest.TestCase):
    def test_intents(self):
        self.assertEqual(detect_intent("Who is on the roster tomorrow?"), INTENT_ROSTER)
        self.assertEqual(
            detect_intent("How many hours has the crew logged this month?"), INTENT_HOURS
        )
        self.assertEqual(detect_intent("Is this flight Augmented (Heavy)?"), INTENT_HEAVY)
        self.assertIsNone(detect_intent("what is the weather"))

    def test_periods(self):
        self.assertEqual(resolve_period("roster tomorrow", TODAY).start, date(2026, 6, 16))
        self.assertEqual(resolve_period("roster today", TODAY).start, TODAY)
        self.assertEqual(resolve_period("hours this month", TODAY).start, date(2026, 6, 1))
        self.assertEqual(resolve_period("roster on 2026-07-04", TODAY).start, date(2026, 7, 4))
        self.assertIsNone(resolve_period("roster sometime", TODAY))


class TestLocalAnswers(unittest.TestCase):
    def test_roster_lists_real_crew_and_cites_the_report(self):
        answer = answer_locally(
            "Who is on the roster tomorrow?", today=TODAY, fetch_report=_fetch
        )

        self.assertIn("Khaled Darwish", answer.text)
        self.assertIn("2 crew", answer.text)
        self.assertEqual(
            answer.citation.source,
            "LEON MCP · get-report-wizard-flight-scope-report · 2026-06-16..2026-06-16",
        )

    def test_unnamed_hours_question_reports_the_fleet_total(self):
        answer = answer_locally(
            "How many hours has the crew logged this month?", today=TODAY, fetch_report=_fetch
        )

        # Regression: crew code "HAS" must not match the word "has".
        self.assertNotIn("Hesham", answer.text)
        self.assertIn("2 crew", answer.text)
        self.assertIn("86:40", answer.text)

    def test_named_crew_gets_their_own_total(self):
        answer = answer_locally(
            "how many hours did khaled log this month?", today=TODAY, fetch_report=_fetch
        )

        self.assertIn("Khaled Darwish", answer.text)
        self.assertIn("12:30", answer.text)

    def test_explicit_crew_code_is_matched_case_sensitively(self):
        answer = answer_locally(
            "hours for HAS this month", today=TODAY, fetch_report=_fetch
        )

        self.assertIn("Hesham Abd ElSamad", answer.text)
        self.assertIn("74:10", answer.text)

    def test_heavy_without_a_flight_asks_which_one(self):
        answer = answer_locally(
            "Is this flight Augmented (Heavy)?", today=TODAY, fetch_report=_fetch
        )

        self.assertIn("Which flight?", answer.text)
        self.assertIsNone(answer.citation)


def _heavy_report(positions, adep="SSH", ades="VKO"):
    codes = [f"C{index}" for index in range(len(positions))]
    return OfficialMcpReport(
        {code: "01:00" for code in codes},
        [
            {
                "scope_row_unique_id": "row-9",
                "unique_id": 660214,
                "crew_codes": codes,
                "crew_names": [f"Crew {index}" for index in range(len(positions))],
                "crew_position_names": list(positions),
                "flightNo": "RSX431",
                "acftType": "B738 - 737-800",
                "blockTimeJourneyLog": "01:00",
                # SVX/EVN are matched on the route, not on flight tags.
                "jl_adep_preferred_code": adep,
                "jl_ades_preferred_code": ades,
            }
        ],
    )


class TestHeavyFromMcp(unittest.TestCase):
    def _ask(self, report):
        return answer_locally(
            "Is RSX431 on 2026-06-02 Augmented (Heavy)?",
            today=TODAY,
            fetch_report=lambda _f, _t: report,
        )

    def test_five_operating_cockpit_is_heavy(self):
        answer = self._ask(_heavy_report(["CPT", "FO", "FO2", "FO3", "CPT2"]))

        self.assertIn("Heavy", answer.text)
        self.assertNotIn("Not Heavy", answer.text)
        self.assertEqual(answer.citation.tone, "heavy")
        self.assertIn("effective cockpit count = 5 > 2", answer.citation.source)
        self.assertIn("unique_id 660214", answer.citation.source)

    def test_standard_crew_is_not_heavy(self):
        answer = self._ask(_heavy_report(["CPT", "FO", "FA1", "FA2"]))

        self.assertIn("Not Heavy", answer.text)
        self.assertEqual(answer.citation.tone, "resolved")

    def test_evn_route_overrides_an_oversized_cabin(self):
        # Six cabin would be Heavy on count; an EVN leg must override to No.
        answer = self._ask(
            _heavy_report(["CPT", "FO"] + [f"FA{i}" for i in range(1, 7)], ades="EVN")
        )

        self.assertIn("Not Heavy", answer.text)
        self.assertIn("EVN override", answer.citation.source)

    def test_evn_vetoes_even_a_cockpit_count_yes(self):
        # Owner ruling 2026-08-17 (Q2): EVN/SVX are FLIGHT-LEVEL absolutes.
        # Five operating cockpit would be Heavy on count; EVN must veto it.
        # (This inverts the retired "overrides are cabin-only" behavior.)
        answer = self._ask(
            _heavy_report(["CPT", "FO", "FO2", "FO3", "CPT2"], ades="EVN")
        )

        self.assertIn("Not Heavy", answer.text)
        self.assertIn("EVN override", answer.citation.source)

    def test_svx_route_forces_heavy_on_a_standard_crew(self):
        answer = self._ask(_heavy_report(["CPT", "FO", "FA1", "FA2"], ades="SVX"))

        self.assertIn("Heavy", answer.text)
        self.assertIn("SVX override", answer.citation.source)

    def test_ops_and_sp_trainees_do_not_push_a_flight_over_the_line(self):
        # Standard 2 cockpit + 4 cabin, plus two cockpit trainees.
        answer = self._ask(
            _heavy_report(["CPT", "FO", "OPS", "SP", "FA1", "FA2", "FA3", "FA4"])
        )

        self.assertIn("Not Heavy", answer.text)
        self.assertIn("2 cockpit / 4 cabin", answer.text)

    def test_bare_flight_and_date_routes_to_heavy(self):
        # The answer to "Which flight?" carries no keyword at all.
        for text in ("RSX431 on 2026-06-02", "RSX431 2026-06-02", "rsx431 on 2026-06-02"):
            with self.subTest(text=text):
                self.assertEqual(detect_intent(text), INTENT_HEAVY)

    def test_bare_pattern_never_overrides_an_explicit_keyword(self):
        self.assertEqual(
            detect_intent("how many hours for RSX431 on 2026-06-02"), INTENT_HOURS
        )
        self.assertEqual(
            detect_intent("who is on the roster on 2026-06-02"), INTENT_ROSTER
        )

    def test_bare_pattern_does_not_swallow_unrelated_messages(self):
        for text in ("what is the weather in cairo", "hello", "2026-06-02", "RSX431"):
            with self.subTest(text=text):
                self.assertIsNone(detect_intent(text))

    def test_two_turn_flow_resolves_the_follow_up(self):
        report = _heavy_report(["CPT", "FO", "FA1", "FA2"], ades="SVX")
        fetch = lambda _f, _t: report

        first = answer_locally(
            "Is this flight Augmented (Heavy)?", today=TODAY, fetch_report=fetch
        )
        self.assertIn("Which flight?", first.text)

        # The follow-up must be answered locally, not fall through to Wingman.
        second = answer_locally("RSX431 on 2026-06-02", today=TODAY, fetch_report=fetch)
        self.assertIsNotNone(second)
        self.assertIn("Heavy", second.text)
        self.assertIn("SVX override", second.citation.source)

    def test_unknown_flight_number_says_so(self):
        answer = answer_locally(
            "Is RSX999 on 2026-06-02 Heavy?",
            today=TODAY,
            fetch_report=lambda _f, _t: _heavy_report(["CPT", "FO"]),
        )

        self.assertIn("No flight RSX999", answer.text)
        self.assertEqual(answer.citation.tone, "unresolved")

    def test_unknown_question_falls_through(self):
        self.assertIsNone(
            answer_locally("what is the weather in cairo", today=TODAY, fetch_report=_fetch)
        )

    def test_missing_period_falls_through(self):
        self.assertIsNone(
            answer_locally("who is on the roster", today=TODAY, fetch_report=_fetch)
        )


if __name__ == "__main__":
    unittest.main()

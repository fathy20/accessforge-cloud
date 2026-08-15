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

    def test_heavy_falls_through_rather_than_guessing(self):
        self.assertIsNone(
            answer_locally("Is this flight Augmented (Heavy)?", today=TODAY, fetch_report=_fetch)
        )

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

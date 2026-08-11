import json
import re
import unittest
from datetime import date, datetime, timedelta
import httpx

from backend.statistics.crew_hours.augmented import (
    AugmentedIndex,
    MAX_DUTY_LIST_INTERVAL_DAYS,
    build_augmented_index,
    build_duty_list_query,
    fetch_augmented_index,
)
from backend.statistics.crew_hours.config import LeonConfiguration
from backend.statistics.crew_hours.errors import (
    LeonContractError,
    LeonResponseError,
    LeonTimeoutError,
    LeonTransportError,
)
from backend.statistics.crew_hours.mcp_report import OfficialMcpReport, _aggregate_report_rows
from backend.statistics.crew_hours.service import LiveCrewHoursService
from backend.statistics.crew_hours.token_provider import LeonAccessTokenProvider
from backend.statistics.crew_hours.transport import FakeLeonTransport, LeonRawResponse


def _duty(code, augmentation, *tr_nids):
    return {
        "crewMember": {"code": code, "loginNid": 9001},
        "crewAugmentation": augmentation,
        "sectorList": [{"trNid": tr_nid} for tr_nid in tr_nids],
    }


_INTERVAL_PATTERN = re.compile(
    r'start: "(\d{4}-\d{2}-\d{2})T00:00:00Z", '
    r'end: "(\d{4}-\d{2}-\d{2})T23:59:59Z"'
)


def _graphql_calls(transport):
    return [
        call
        for call in transport.calls
        if call.json_body is not None and "query" in call.json_body
    ]


def _query_intervals(transport):
    intervals = []
    for call in _graphql_calls(transport):
        match = _INTERVAL_PATTERN.search(call.json_body["query"])
        if match is None:
            raise AssertionError("GraphQL call did not contain a duty-list interval.")
        intervals.append(tuple(date.fromisoformat(value) for value in match.groups()))
    return intervals


class TestAugmentedIndex(unittest.TestCase):
    def test_exact_stable_id_match_maps_to_yes(self):
        index = build_augmented_index([_duty(" c1 ", "AUGMENTED", 101)])

        self.assertTrue(index.available)
        self.assertTrue(index.lookup("C1", "101"))
        self.assertEqual(index.resolved_count, 1)
        self.assertEqual(index.ambiguous_count, 0)

    def test_integer_and_numeric_string_ids_resolve_identically(self):
        index = build_augmented_index([_duty("C1", "AUGMENTED", 101)])

        integer_value = index.lookup("C1", 101)
        string_value = index.lookup("C1", "101")

        self.assertIsNotNone(integer_value)
        self.assertIs(integer_value, True)
        self.assertEqual(integer_value, string_value)

    def test_normal_maps_to_no(self):
        index = build_augmented_index([_duty("C1", "normal", 101)])

        self.assertIs(index.lookup("c1", "101"), False)

    def test_unrecognised_enum_is_unknown_and_safe_warning(self):
        with self.assertLogs(
            "backend.statistics.crew_hours.augmented", level="WARNING"
        ) as logs:
            index = build_augmented_index([_duty("SECRET-CREW", "future_value", 101)])

        self.assertIsNone(index.lookup("SECRET-CREW", "101"))
        self.assertEqual(index.resolved_count, 0)
        self.assertEqual(index.ambiguous_count, 0)
        message = "\n".join(logs.output)
        self.assertIn("unrecognised", message)
        self.assertNotIn("SECRET-CREW", message)
        self.assertNotIn("future_value", message)

    def test_missing_augmentation_is_unknown(self):
        row = _duty("C1", None, 101)
        row.pop("crewAugmentation")

        index = build_augmented_index([row])

        self.assertIsNone(index.lookup("C1", "101"))

    def test_no_matching_duty_is_unknown(self):
        index = build_augmented_index([_duty("C1", "NORMAL", 101)])

        self.assertIsNone(index.lookup("C2", "101"))
        self.assertIsNone(index.lookup("C1", "999"))
        self.assertIsNone(index.lookup(None, "101"))

    def test_conflicting_values_are_ambiguous(self):
        index = build_augmented_index([
            _duty("C1", "NORMAL", 101),
            _duty("C1", "DOUBLED", 101),
        ])

        self.assertIsNone(index.lookup("C1", "101"))
        self.assertEqual(index.ambiguous_count, 1)
        self.assertEqual(index.resolved_count, 0)

    def test_duplicate_identical_values_are_not_ambiguous(self):
        index = build_augmented_index([
            _duty("C1", "NORMAL", 101),
            _duty(" c1 ", "normal", "101"),
        ])

        self.assertIs(index.lookup("C1", "101"), False)
        self.assertEqual(index.resolved_count, 1)
        self.assertEqual(index.ambiguous_count, 0)

    def test_same_flight_number_on_different_dates_uses_distinct_stable_ids(self):
        index = build_augmented_index([
            _duty("C1", "NORMAL", 101),
            _duty("C1", "DOUBLED", 202),
        ])

        self.assertIs(index.lookup("C1", "101"), False)
        self.assertIs(index.lookup("C1", "202"), True)

    def test_same_crew_multiple_flights_and_multiple_crew_one_flight(self):
        index = build_augmented_index([
            _duty("C1", "AUGMENTED", 101, 102),
            _duty("C2", "NORMAL", 101),
        ])

        self.assertIs(index.lookup("C1", "101"), True)
        self.assertIs(index.lookup("C1", "102"), True)
        self.assertIs(index.lookup("C2", "101"), False)

    def test_multi_sector_duty_applies_to_every_sector(self):
        index = build_augmented_index([_duty("C1", "TRIPLED", 101, 102, 103)])

        self.assertEqual(
            [index.lookup("C1", str(tr_nid)) for tr_nid in (101, 102, 103)],
            [True, True, True],
        )

    def test_matching_is_order_independent(self):
        duties = [
            _duty("C1", "NORMAL", 101),
            _duty("C1", "DOUBLED", 102),
            _duty("C2", "AUGMENTED", 101),
            _duty("C3", "NORMAL", 103),
            _duty("C3", "NORMAL", 103),
        ]
        first = build_augmented_index(duties)
        second = build_augmented_index(list(reversed(duties)))

        self.assertEqual(dict(first.by_crew_sector), dict(second.by_crew_sector))
        self.assertEqual(first.resolved_count, second.resolved_count)
        self.assertEqual(first.ambiguous_count, second.ambiguous_count)


class TestAugmentedFetch(unittest.TestCase):
    def setUp(self):
        self.configuration = LeonConfiguration(
            "https://leon.invalid",
            "refresh-token",
        )

    def test_month_buffer_uses_two_safe_graphql_calls(self):
        transport = FakeLeonTransport([
            LeonRawResponse(200, '{"access_token":"access","expires_in":1800}'),
            LeonRawResponse(200, json.dumps({
                "data": {"ftl": {"dutyList": [_duty("C1", "NORMAL", 101)]}},
            })),
            LeonRawResponse(200, json.dumps({
                "data": {"ftl": {"dutyList": []}},
            })),
        ])

        index = fetch_augmented_index(
            self.configuration,
            transport,
            LeonAccessTokenProvider(self.configuration, transport),
            "2026-06-01",
            "2026-06-30",
        )

        self.assertIs(index.lookup("C1", "101"), False)
        graphql_calls = _graphql_calls(transport)
        self.assertEqual(len(graphql_calls), 2)
        intervals = _query_intervals(transport)
        self.assertEqual(
            intervals,
            [
                (date(2026, 5, 30), date(2026, 6, 29)),
                (date(2026, 6, 30), date(2026, 7, 2)),
            ],
        )
        for call in graphql_calls:
            query = call.json_body["query"]
            self.assertIn("crewMember { code loginNid }", query)
            self.assertIn("crewAugmentation", query)
            self.assertIn("sectorList { trNid }", query)
            start, end = next(
                interval for interval in intervals if interval[0].isoformat() in query
            )
            self.assertLessEqual(
                (end - start).days + 1,
                MAX_DUTY_LIST_INTERVAL_DAYS,
            )

    def test_thirteen_day_buffer_uses_exactly_one_graphql_call(self):
        transport = FakeLeonTransport([
            LeonRawResponse(200, '{"access_token":"access","expires_in":1800}'),
            LeonRawResponse(200, json.dumps({
                "data": {"ftl": {"dutyList": [_duty("C1", "AUGMENTED", 101)]}},
            })),
        ])

        index = fetch_augmented_index(
            self.configuration,
            transport,
            LeonAccessTokenProvider(self.configuration, transport),
            "2026-07-01",
            "2026-07-09",
        )

        self.assertIs(index.lookup("C1", 101), True)
        intervals = _query_intervals(transport)
        self.assertEqual(len(intervals), 1)
        self.assertEqual(intervals, [(date(2026, 6, 29), date(2026, 7, 11))])
        self.assertEqual((intervals[0][1] - intervals[0][0]).days + 1, 13)

    def test_chunks_are_contiguous_and_cover_the_buffered_window(self):
        transport = FakeLeonTransport([
            LeonRawResponse(200, '{"access_token":"access","expires_in":1800}'),
            LeonRawResponse(200, '{"data":{"ftl":{"dutyList":[]}}}'),
            LeonRawResponse(200, '{"data":{"ftl":{"dutyList":[]}}}'),
        ])

        fetch_augmented_index(
            self.configuration,
            transport,
            LeonAccessTokenProvider(self.configuration, transport),
            "2026-06-01",
            "2026-06-30",
        )

        intervals = _query_intervals(transport)
        self.assertEqual(intervals[0][0], date(2026, 5, 30))
        self.assertEqual(intervals[-1][1], date(2026, 7, 2))
        for previous, current in zip(intervals, intervals[1:]):
            self.assertEqual(current[0], previous[1] + timedelta(days=1))

    def test_rows_from_chunks_merge_and_identical_boundary_values_resolve(self):
        transport = FakeLeonTransport([
            LeonRawResponse(200, '{"access_token":"access","expires_in":1800}'),
            LeonRawResponse(200, json.dumps({
                "data": {"ftl": {"dutyList": [_duty("C1", "NORMAL", 101)]}},
            })),
            LeonRawResponse(200, json.dumps({
                "data": {"ftl": {"dutyList": [
                    _duty("C1", "NORMAL", 101),
                    _duty("C2", "AUGMENTED", 202),
                ]}},
            })),
        ])

        index = fetch_augmented_index(
            self.configuration,
            transport,
            LeonAccessTokenProvider(self.configuration, transport),
            "2026-06-01",
            "2026-06-30",
        )

        self.assertIs(index.lookup("C1", 101), False)
        self.assertIs(index.lookup("C2", 202), True)
        self.assertEqual(index.resolved_count, 2)
        self.assertEqual(index.ambiguous_count, 0)

    def test_conflicting_boundary_values_are_ambiguous(self):
        transport = FakeLeonTransport([
            LeonRawResponse(200, '{"access_token":"access","expires_in":1800}'),
            LeonRawResponse(200, json.dumps({
                "data": {"ftl": {"dutyList": [_duty("C1", "NORMAL", 101)]}},
            })),
            LeonRawResponse(200, json.dumps({
                "data": {"ftl": {"dutyList": [_duty("C1", "DOUBLED", 101)]}},
            })),
        ])

        index = fetch_augmented_index(
            self.configuration,
            transport,
            LeonAccessTokenProvider(self.configuration, transport),
            "2026-06-01",
            "2026-06-30",
        )

        self.assertIsNone(index.lookup("C1", 101))
        self.assertEqual(index.ambiguous_count, 1)
        self.assertEqual(index.resolved_count, 0)

    def test_duty_list_interval_boundary_is_31_days(self):
        self.assertEqual(MAX_DUTY_LIST_INTERVAL_DAYS, 31)

    def test_chunk_failure_propagates(self):
        transport = FakeLeonTransport([
            LeonRawResponse(200, '{"access_token":"access","expires_in":1800}'),
            LeonRawResponse(200, '{"data":{"ftl":{"dutyList":[]}}}'),
            LeonRawResponse(400, '{"errors":[{"message":"interval failure"}]}'),
        ])

        with self.assertRaises(LeonResponseError):
            fetch_augmented_index(
                self.configuration,
                transport,
                LeonAccessTokenProvider(self.configuration, transport),
                "2026-06-01",
                "2026-06-30",
            )

    def test_query_date_validation_rejects_injection_and_datetime_values(self):
        for start, end in (
            ('2026-06-01" } mutation { x', "2026-06-02"),
            ("2026-02-30", "2026-03-01"),
            (date(2026, 6, 1), datetime(2026, 6, 2, 12)),
        ):
            with self.subTest(start=start, end=end):
                with self.assertRaises(LeonContractError):
                    build_duty_list_query(start, end)

    def test_build_accepts_the_graphql_payload_shape(self):
        index = build_augmented_index({"ftl": {"dutyList": [_duty("C1", "DOUBLED", 101)]}})

        self.assertIs(index.lookup("C1", "101"), True)


class TestAugmentedServiceIntegration(unittest.TestCase):
    @staticmethod
    def _report():
        rows = [
            {
                "scope_row_unique_id": "scope-1",
                "unique_id": 101,
                "crew_codes": [" C1 "],
                "crew_names": ["Fixture One"],
                "crew_position_names": ["CPT"],
                "blockTimeJourneyLog": "01:00",
            },
            {
                "scope_row_unique_id": "scope-2",
                "unique_id": 102,
                "crew_codes": ["C1", "C2"],
                "crew_names": ["Fixture One", "Fixture Two"],
                "crew_position_names": ["CPT", "FO"],
                "blockTimeJourneyLog": "02:00",
            },
        ]
        return OfficialMcpReport(
            {"C1": "03:00", "C2": "02:00"},
            rows,
            total_minutes={"C1": 180, "C2": 120},
        )

    def test_exactly_one_augmented_fetch_and_no_fetch_inside_row_loop(self):
        class FakeClient:
            def __init__(self):
                self.calls = 0

            def fetch_official_totals(self, from_date, to_date):
                return TestAugmentedServiceIntegration._report()

            def fetch_augmented_index(self, from_date, to_date):
                self.calls += 1
                return build_augmented_index([
                    _duty("C1", "AUGMENTED", 101, 102),
                    _duty("C2", "NORMAL", 102),
                ])

        client = FakeClient()
        report = LiveCrewHoursService(client).get_crew_hours_report(
            "2026-06-01", "2026-06-30"
        )

        self.assertEqual(client.calls, 1)
        by_code = {member.person_code: member for member in report.crew_members}
        self.assertIs(by_code["C1"].flights[0].augmented_heavy, True)
        self.assertIs(by_code["C1"].flights[1].augmented_heavy, True)
        self.assertIs(by_code["C2"].flights[0].augmented_heavy, False)

    def test_enrichment_failure_returns_report_with_all_unknown_values(self):
        class FailingClient:
            def fetch_official_totals(self, from_date, to_date):
                return TestAugmentedServiceIntegration._report()

            def fetch_augmented_index(self, from_date, to_date):
                raise LeonTransportError("transport sentinel with secret-like data")

        report = LiveCrewHoursService(FailingClient()).get_crew_hours_report(
            "2026-06-01", "2026-06-30"
        )

        self.assertEqual(report.official_totals_by_position, {"Cockpit": "5:00"})
        self.assertTrue(
            all(
                flight.augmented_heavy is None
                for member in report.crew_members
                for flight in member.flights
            )
        )

    def test_chunk_failure_returns_report_with_all_unknown_values(self):
        configuration = LeonConfiguration("https://leon.invalid", "refresh-token")
        transport = FakeLeonTransport([
            LeonRawResponse(200, '{"access_token":"access","expires_in":1800}'),
            LeonRawResponse(200, json.dumps({
                "data": {"ftl": {"dutyList": [_duty("C1", "NORMAL", 101)]}},
            })),
            LeonRawResponse(400, '{"errors":[{"message":"interval failure"}]}'),
        ])
        token_provider = LeonAccessTokenProvider(configuration, transport)

        class ChunkFailingClient:
            def fetch_official_totals(self, from_date, to_date):
                return TestAugmentedServiceIntegration._report()

            def fetch_augmented_index(self, from_date, to_date):
                return fetch_augmented_index(
                    configuration,
                    transport,
                    token_provider,
                    from_date,
                    to_date,
                )

        report = LiveCrewHoursService(ChunkFailingClient()).get_crew_hours_report(
            "2026-06-01", "2026-06-30"
        )

        self.assertTrue(
            all(
                flight.augmented_heavy is None
                for member in report.crew_members
                for flight in member.flights
            )
        )

    def test_official_totals_are_unchanged_when_enrichment_is_enabled(self):
        class Client:
            def __init__(self, index):
                self.index = index

            def fetch_official_totals(self, from_date, to_date):
                return TestAugmentedServiceIntegration._report()

            def fetch_augmented_index(self, from_date, to_date):
                return self.index

        enabled = LiveCrewHoursService(
            Client(build_augmented_index([_duty("C1", "DOUBLED", 101, 102)]))
        ).get_crew_hours_report("2026-06-01", "2026-06-30")
        disabled = LiveCrewHoursService(
            Client(AugmentedIndex(False, {}, 0, 0))
        ).get_crew_hours_report("2026-06-01", "2026-06-30")

        self.assertEqual(
            enabled.official_totals_by_position,
            disabled.official_totals_by_position,
        )
        self.assertEqual(
            [member.official_total for member in enabled.crew_members],
            [member.official_total for member in disabled.crew_members],
        )
        self.assertNotEqual(
            enabled.crew_members[0].flights[0].augmented_heavy,
            disabled.crew_members[0].flights[0].augmented_heavy,
        )

    def test_unique_id_is_additive_and_does_not_change_totals(self):
        base = {
            "scope_row_unique_id": "scope-1",
            "crew_codes": ["C1"],
            "blockTimeJourneyLog": "01:30",
        }
        with_unique_id = {**base, "unique_id": "101"}

        self.assertEqual(_aggregate_report_rows([base]), _aggregate_report_rows([with_unique_id]))


class TestAugmentedTransportFailures(unittest.TestCase):
    def test_graphql_timeout_is_typed(self):
        configuration = LeonConfiguration("https://leon.invalid", "refresh-token")
        transport = FakeLeonTransport(error=httpx.TimeoutException("timeout"))

        with self.assertRaises(LeonTimeoutError):
            fetch_augmented_index(
                configuration,
                transport,
                LeonAccessTokenProvider(configuration, transport),
                "2026-06-01",
                "2026-06-30",
            )


if __name__ == "__main__":
    unittest.main()

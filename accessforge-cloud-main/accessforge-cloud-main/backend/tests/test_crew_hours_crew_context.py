import json
import re
import unittest
from datetime import date, timedelta

from backend.statistics.crew_hours.config import LeonConfiguration
from backend.statistics.crew_hours.crew_context import (
    CREW_CONTEXT_CHUNK_DAYS,
    CrewContextEntry,
    build_crew_context_index,
    fetch_crew_context_index,
)
from backend.statistics.crew_hours.errors import LeonContractError, LeonTransportError
from backend.statistics.crew_hours.response_models import LeonFlight
from backend.statistics.crew_hours.token_provider import LeonAccessTokenProvider
from backend.statistics.crew_hours.transport import FakeLeonTransport, LeonRawResponse


_INTERVAL_PATTERN = re.compile(
    r'timeInterval: \{ start: "(\d{4}-\d{2}-\d{2})", end: "(\d{4}-\d{2}-\d{2})" \}'
)


def _flight(flight_nid: str, crew_list=None) -> LeonFlight:
    return LeonFlight(
        flight_nid=flight_nid,
        start_time_utc="2026-06-01T00:00:00Z",
        end_time_utc="2026-06-01T01:00:00Z",
        flight_tags=None,
        start_airport=None,
        end_airport=None,
        aircraft=None,
        crew_list=crew_list,
        journey_log=None,
    )


def _flight_payload(flights) -> LeonRawResponse:
    return LeonRawResponse(
        200,
        json.dumps(
            {
                "data": {
                    "flightList": [
                        {
                            "flightNid": int(flight.flight_nid),
                            "startTimeUTC": flight.start_time_utc,
                            "endTimeUTC": flight.end_time_utc,
                            "crewList": flight.crew_list,
                        }
                        for flight in flights
                    ]
                }
            }
        ),
    )


def _transport_for_chunks(flights_by_chunk) -> FakeLeonTransport:
    responses = [LeonRawResponse(200, '{"access_token":"access","expires_in":1800}')]
    responses.extend(_flight_payload(flights) for flights in flights_by_chunk)
    return FakeLeonTransport(responses)


def _query_intervals(transport: FakeLeonTransport) -> list[tuple[date, date]]:
    intervals = []
    for call in transport.calls:
        if call.json_body is None or "query" not in call.json_body:
            continue
        match = _INTERVAL_PATTERN.search(call.json_body["query"])
        if match is None:
            raise AssertionError("GraphQL call did not contain a flight-list interval.")
        intervals.append(tuple(date.fromisoformat(value) for value in match.groups()))
    return intervals


class TestCrewContextIndex(unittest.TestCase):
    def test_builds_entries_keyed_by_integer_flight_nid(self):
        flights = [
            _flight(
                "101",
                [
                    {
                        "position": {"name": " FO ", "posType": " COCKPIT "},
                        "flightTrainingType": " LINE_CHECK ",
                    }
                ],
            )
        ]

        index = build_crew_context_index(flights)

        self.assertTrue(index.available)
        self.assertEqual(
            index.by_flight,
            {
                101: (
                    CrewContextEntry(
                        pos_type="COCKPIT",
                        position="FO",
                        training_type="LINE_CHECK",
                    ),
                )
            },
        )

    def test_integer_and_numeric_string_nids_use_the_same_integer_key(self):
        crew_list = [
            {
                "position": {"name": "FO", "posType": "COCKPIT"},
                "flightTrainingType": None,
            }
        ]

        integer_index = build_crew_context_index(
            [{"flightNid": 101, "crewList": crew_list}]
        )
        string_index = build_crew_context_index(
            [{"flightNid": " 101 ", "crewList": crew_list}]
        )

        self.assertEqual(set(integer_index.by_flight), {101})
        self.assertEqual(set(string_index.by_flight), {101})
        self.assertEqual(integer_index.by_flight, string_index.by_flight)

    def test_malformed_context_rows_raise_contract_errors(self):
        malformed_flights = [
            {"flightNid": 101, "crewList": ["not a mapping"]},
            {"flightNid": 101, "crewList": [{"position": []}]},
            {"flightNid": "not-a-number", "crewList": []},
        ]

        for flight in malformed_flights:
            with self.subTest(flight=flight):
                with self.assertRaises(LeonContractError):
                    build_crew_context_index([flight])

    def test_fetch_indexes_integer_flight_nid_from_raw_graphql_payload(self):
        transport = _transport_for_chunks(
            [
                [
                    _flight(
                        "101",
                        [
                            {
                                "position": {"name": "FO", "posType": "COCKPIT"},
                                "flightTrainingType": None,
                            }
                        ],
                    )
                ],
                [],
                [],
                [],
                [],
            ]
        )
        configuration = LeonConfiguration("https://leon.invalid", "refresh-token")

        index = fetch_crew_context_index(
            configuration,
            transport,
            LeonAccessTokenProvider(configuration, transport),
            "2026-06-01",
            "2026-06-30",
        )

        self.assertIn(101, index.by_flight)
        self.assertEqual(index.by_flight[101][0].pos_type, "COCKPIT")

    def test_weekly_chunking_is_buffered_contiguous_and_row_independent(self):
        empty_chunks = [[] for _ in range(5)]
        transport = _transport_for_chunks(empty_chunks)
        configuration = LeonConfiguration("https://leon.invalid", "refresh-token")
        token_provider = LeonAccessTokenProvider(configuration, transport)

        index = fetch_crew_context_index(
            configuration,
            transport,
            token_provider,
            "2026-06-01",
            "2026-06-30",
        )

        intervals = _query_intervals(transport)
        self.assertEqual(len(intervals), 5)
        self.assertEqual(len(intervals), (34 + CREW_CONTEXT_CHUNK_DAYS - 1) // CREW_CONTEXT_CHUNK_DAYS)
        for start, end in intervals:
            self.assertLessEqual((end - start).days + 1, CREW_CONTEXT_CHUNK_DAYS)
        for previous, current in zip(intervals, intervals[1:]):
            self.assertEqual(current[0], previous[1] + timedelta(days=1))
        self.assertEqual(intervals[0][0], date(2026, 5, 30))
        self.assertEqual(intervals[-1][1], date(2026, 7, 2))
        self.assertEqual(index.by_flight, {})

        many_rows_transport = _transport_for_chunks(
            [[_flight(str(number)) for number in range(chunk * 10, chunk * 10 + 10)] for chunk in range(5)]
        )
        many_rows_provider = LeonAccessTokenProvider(configuration, many_rows_transport)
        many_rows_index = fetch_crew_context_index(
            configuration,
            many_rows_transport,
            many_rows_provider,
            "2026-06-01",
            "2026-06-30",
        )
        self.assertEqual(len(_query_intervals(many_rows_transport)), len(intervals))
        self.assertEqual(len(many_rows_index.by_flight), 50)

    def test_chunk_failure_propagates_without_returning_partial_index(self):
        class FailingTransport(FakeLeonTransport):
            def __init__(self):
                super().__init__([
                    LeonRawResponse(200, '{"access_token":"access","expires_in":1800}'),
                    _flight_payload([]),
                ])
                self.query_count = 0

            def send(self, request, timeout_seconds):
                if request.json_body is not None and "query" in request.json_body:
                    self.query_count += 1
                    if self.query_count == 2:
                        raise LeonTransportError("second chunk failed")
                return super().send(request, timeout_seconds)

        transport = FailingTransport()
        configuration = LeonConfiguration("https://leon.invalid", "refresh-token")
        with self.assertRaises(LeonTransportError):
            fetch_crew_context_index(
                configuration,
                transport,
                LeonAccessTokenProvider(configuration, transport),
                "2026-06-01",
                "2026-06-30",
            )


if __name__ == "__main__":
    unittest.main()

import json
import unittest

from backend.statistics.crew_hours.augmented import fetch_augmented_index
from backend.statistics.crew_hours.config import LeonConfiguration
from backend.statistics.crew_hours.crew_context import fetch_crew_context_index
from backend.statistics.crew_hours.token_provider import LeonAccessTokenProvider
from backend.statistics.crew_hours.transport import FakeLeonTransport, LeonRawResponse


def _flight_record(flight_nid: int, crew_count: int) -> dict:
    return {
        "flightNid": flight_nid,
        "startTimeUTC": "2026-06-01T00:00:00Z",
        "endTimeUTC": "2026-06-01T01:00:00Z",
        "crewList": [
            {
                "contact": {"personCode": f"C{flight_nid}-{index}"},
                "position": {"name": "FO", "posType": "COCKPIT"},
                "flightTrainingType": None,
            }
            for index in range(crew_count)
        ],
    }


def _transport(scale: int) -> FakeLeonTransport:
    responses = [LeonRawResponse(200, '{"access_token":"access","expires_in":1800}')]
    for _ in range(2):
        responses.append(
            LeonRawResponse(
                200,
                json.dumps(
                    {
                        "data": {
                            "ftl": {
                                "dutyList": [
                                    {
                                        "crewMember": {"code": f"C{index}"},
                                        "crewAugmentation": "NORMAL",
                                        "sectorList": [{"trNid": index}],
                                    }
                                    for index in range(10 * scale)
                                ]
                            }
                        }
                    }
                ),
            )
        )
    for chunk in range(5):
        responses.append(
            LeonRawResponse(
                200,
                json.dumps(
                    {
                        "data": {
                            "flightList": [
                                _flight_record(chunk * 100 + index, scale)
                                for index in range(10 * scale)
                            ]
                        }
                    }
                ),
            )
        )
    return FakeLeonTransport(responses)


def _fetch_both(scale: int):
    configuration = LeonConfiguration("https://leon.invalid", "refresh-token")
    transport = _transport(scale)
    token_provider = LeonAccessTokenProvider(configuration, transport)
    augmented = fetch_augmented_index(
        configuration,
        transport,
        token_provider,
        "2026-06-01",
        "2026-06-30",
    )
    context = fetch_crew_context_index(
        configuration,
        transport,
        token_provider,
        "2026-06-01",
        "2026-06-30",
    )
    graphql_calls = [
        call
        for call in transport.calls
        if call.json_body is not None and "query" in call.json_body
    ]
    return transport, augmented, context, graphql_calls


class TestCrewHoursEnrichmentPerformance(unittest.TestCase):
    def test_graphql_call_count_is_augmented_plus_context_chunks_only(self):
        transport, _, _, graphql_calls = _fetch_both(scale=1)

        self.assertEqual(len(graphql_calls), 2 + 5)
        self.assertEqual(len(transport.calls), 1 + 2 + 5)

    def test_call_count_does_not_scale_with_rows_or_crew_members(self):
        _, _, _, small_calls = _fetch_both(scale=1)
        _, _, _, large_calls = _fetch_both(scale=10)

        self.assertEqual(len(small_calls), len(large_calls))
        self.assertEqual(len(small_calls), 7)

    def test_row_loop_index_lookups_do_not_touch_transport(self):
        transport, augmented, context, _ = _fetch_both(scale=1)
        calls_after_index_build = len(transport.calls)

        for flight_nid in context.by_flight:
            entries = context.by_flight.get(flight_nid, ())
            self.assertIsNotNone(entries)
            augmented.lookup("C0", flight_nid)
            augmented.lookup_raw("C0", flight_nid)

        self.assertEqual(len(transport.calls), calls_after_index_build)


if __name__ == "__main__":
    unittest.main()

import os
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from unittest.mock import patch

import httpx


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class Clock:
    def __init__(self, value=0.0):
        self.value = value

    def __call__(self):
        return self.value


class TestS4Configuration(unittest.TestCase):
    base_url = "https://operator.sandbox.leon.aero"
    refresh_token = "unit-test-refresh-token"

    def _load(self, values):
        from backend.statistics.crew_hours.config import load_leon_configuration
        with patch.dict(os.environ, values, clear=True):
            return load_leon_configuration()

    def test_refresh_token_configuration_is_required_and_safe(self):
        from backend.statistics.crew_hours.errors import LeonConfigurationError

        for values in (
            {"LEON_BASE_URL": self.base_url},
            {"LEON_BASE_URL": self.base_url, "LEON_REFRESH_TOKEN": "   "},
            {"LEON_BASE_URL": "http://operator.sandbox.leon.aero", "LEON_REFRESH_TOKEN": self.refresh_token},
            {"LEON_BASE_URL": self.base_url, "LEON_REFRESH_TOKEN": self.refresh_token, "LEON_TIMEOUT_SECONDS": "0"},
            {"LEON_BASE_URL": self.base_url, "LEON_REFRESH_TOKEN": self.refresh_token, "LEON_TIMEOUT_SECONDS": "NaN"},
        ):
            with self.assertRaises(LeonConfigurationError) as captured:
                self._load(values)
            self.assertNotIn(self.refresh_token, str(captured.exception))

        with self.assertRaises(LeonConfigurationError):
            self._load({"LEON_BASE_URL": self.base_url, "LEON_API_KEY": "obsolete-only"})
        configuration = self._load({
            "LEON_BASE_URL": f" {self.base_url}/ ",
            "LEON_REFRESH_TOKEN": f" {self.refresh_token} ",
        })
        self.assertEqual(configuration.refresh_token, self.refresh_token)
        self.assertEqual(configuration.timeout_seconds, 30.0)
        self.assertNotIn(self.refresh_token, repr(configuration))


class TestS4TokenProvider(unittest.TestCase):
    refresh_token = "unit-test-refresh-token"

    def _provider(self, transport, clock=None):
        from backend.statistics.crew_hours.config import LeonConfiguration
        from backend.statistics.crew_hours.token_provider import LeonAccessTokenProvider
        return LeonAccessTokenProvider(
            LeonConfiguration("https://operator.sandbox.leon.aero", self.refresh_token, 10),
            transport,
            clock=clock or Clock(),
        )

    def test_refresh_request_cache_expiry_and_safety_margin(self):
        from backend.statistics.crew_hours.transport import FakeLeonTransport, LeonRawResponse

        clock = Clock()
        transport = FakeLeonTransport([
            LeonRawResponse(200, '{"access_token": "access-one", "expires_in": 120}'),
            LeonRawResponse(200, '{"access_token": "access-two", "expires_in": 120}'),
        ])
        provider = self._provider(transport, clock)
        self.assertEqual(provider.get_access_token(), "access-one")
        self.assertEqual(provider.get_access_token(), "access-one")
        self.assertEqual(len(transport.calls), 1)
        first_call = transport.calls[0]
        self.assertEqual(first_call.method, "POST")
        self.assertEqual(first_call.url, "https://operator.sandbox.leon.aero/access_token/refresh/")
        self.assertEqual(first_call.form_field_names, ("refresh_token",))
        self.assertEqual(first_call.header_names, ("Content-Type",))
        clock.value = 61
        self.assertEqual(provider.get_access_token(), "access-two")
        self.assertEqual(len(transport.calls), 2)

    def test_token_provider_errors_are_typed_and_secret_safe(self):
        from backend.statistics.crew_hours.errors import (
            LeonAuthenticationError,
            LeonContractError,
            LeonRateLimitError,
            LeonResponseError,
            LeonTimeoutError,
            LeonTransportError,
        )
        from backend.statistics.crew_hours.transport import FakeLeonTransport, LeonRawResponse

        cases = [
            (FakeLeonTransport(error=httpx.TimeoutException("timeout")), LeonTimeoutError),
            (FakeLeonTransport(error=httpx.ConnectError("network")), LeonTransportError),
            (FakeLeonTransport([LeonRawResponse(401, "{}")] ), LeonAuthenticationError),
            (FakeLeonTransport([LeonRawResponse(403, "{}")] ), LeonAuthenticationError),
            (FakeLeonTransport([LeonRawResponse(400, "{}")] ), LeonAuthenticationError),
            (FakeLeonTransport([LeonRawResponse(500, "{}")] ), LeonResponseError),
            (FakeLeonTransport([LeonRawResponse(200, "not-json")] ), LeonResponseError),
            (FakeLeonTransport([LeonRawResponse(200, "{}")]), LeonContractError),
            (FakeLeonTransport([LeonRawResponse(200, '{"access_token": ""}')]), LeonContractError),
            (FakeLeonTransport([LeonRawResponse(200, '{"access_token": "access", "expires_in": 0}')]), LeonContractError),
        ]
        for transport, error_type in cases:
            with self.assertRaises(error_type) as captured:
                self._provider(transport).get_access_token()
            self.assertNotIn(self.refresh_token, str(captured.exception))

        rate_limited = self._provider(FakeLeonTransport([LeonRawResponse(429, "{}", {"Retry-After": "7"})]))
        with self.assertRaises(LeonRateLimitError) as captured:
            rate_limited.get_access_token()
        self.assertEqual(captured.exception.retry_after_seconds, 7)
        self.assertNotIn(self.refresh_token, str(captured.exception))

    def test_concurrent_callers_share_one_refresh(self):
        from backend.statistics.crew_hours.transport import FakeLeonTransport, LeonRawResponse

        transport = FakeLeonTransport([LeonRawResponse(200, '{"access_token": "access", "expires_in": 1800}')])
        provider = self._provider(transport)
        with ThreadPoolExecutor(max_workers=8) as executor:
            tokens = list(executor.map(lambda _unused: provider.get_access_token(), range(8)))
        self.assertEqual(tokens, ["access"] * 8)
        self.assertEqual(len(transport.calls), 1)


class StaticTokenProvider:
    def __init__(self, tokens):
        self._tokens = list(tokens)
        self.invalidations = 0

    def get_access_token(self):
        if not self._tokens:
            raise AssertionError("No test access token available.")
        return self._tokens.pop(0)

    def invalidate(self):
        self.invalidations += 1


class TestS4GraphQLExecutor(unittest.TestCase):
    def _executor(self, transport, token_provider=None):
        from backend.statistics.crew_hours.config import LeonConfiguration
        from backend.statistics.crew_hours.graphql import LeonGraphQLExecutor
        from backend.statistics.crew_hours.leon_client import BearerAccessTokenHeaderBuilder

        return LeonGraphQLExecutor(
            LeonConfiguration("https://operator.sandbox.leon.aero", "unit-test-refresh-token", 10),
            transport,
            token_provider or StaticTokenProvider(["access"]),
            BearerAccessTokenHeaderBuilder(),
        )

    def test_graphql_request_data_and_auth_retry(self):
        from backend.statistics.crew_hours.transport import FakeLeonTransport, LeonRawResponse

        provider = StaticTokenProvider(["old-access", "new-access"])
        transport = FakeLeonTransport([
            LeonRawResponse(401, "{}"),
            LeonRawResponse(200, '{"data": {"flightList": []}}'),
        ])
        data = self._executor(transport, provider).execute_query("query { flightList { flightNid } }", {"unused": "value"})
        self.assertEqual(data, {"flightList": []})
        self.assertEqual(provider.invalidations, 1)
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(transport.calls[0].url, "https://operator.sandbox.leon.aero/api/graphql/")
        self.assertIn("Authorization", transport.calls[0].header_names)
        self.assertIn("Content-Type", transport.calls[0].header_names)
        self.assertEqual(transport.calls[0].json_body["variables"], {"unused": "value"})

    def test_graphql_error_timeout_and_second_401_stop(self):
        from backend.statistics.crew_hours.errors import LeonAuthenticationError, LeonResponseError, LeonTimeoutError
        from backend.statistics.crew_hours.transport import FakeLeonTransport, LeonRawResponse

        with self.assertRaises(LeonResponseError):
            self._executor(FakeLeonTransport([LeonRawResponse(200, '{"errors": [{"message": "bad"}]}')])).execute_query("query { x }")
        with self.assertRaises(LeonResponseError):
            self._executor(FakeLeonTransport([LeonRawResponse(200, "not-json")])).execute_query("query { x }")
        with self.assertRaises(LeonTimeoutError):
            self._executor(FakeLeonTransport(error=httpx.TimeoutException("timeout"))).execute_query("query { x }")
        provider = StaticTokenProvider(["one", "two"])
        with self.assertRaises(LeonAuthenticationError):
            self._executor(FakeLeonTransport([LeonRawResponse(401, "{}"), LeonRawResponse(401, "{}")]), provider).execute_query("query { x }")
        self.assertEqual(provider.invalidations, 2)


class TestS4FlightQuery(unittest.TestCase):
    def test_validated_query_and_nullable_response(self):
        from backend.statistics.crew_hours.flight_query import build_flight_list_query, parse_flight_list

        query = build_flight_list_query(date(2024, 12, 1), "2024-12-31")
        self.assertIn('start: "2024-12-01"', query)
        self.assertIn('end: "2024-12-31"', query)
        self.assertIn("flightStatus: CONFIRMED", query)
        self.assertIn("isCnl: false", query)
        self.assertIn("journeyLog", query)
        flights = parse_flight_list({"flightList": [{
            "flightNid": "flight-1",
            "startTimeUTC": "2024-12-01T00:00:00Z",
            "endTimeUTC": "2024-12-01T01:00:00Z",
            "flightTags": None,
            "startAirport": None,
            "endAirport": None,
            "acft": None,
            "crewList": None,
            "journeyLog": None,
        }]})
        self.assertEqual(flights[0].flight_nid, "flight-1")
        self.assertIsNone(flights[0].journey_log)

    def test_invalid_dates_injection_and_malformed_flights_are_rejected(self):
        from backend.statistics.crew_hours.errors import LeonContractError, LeonResponseError
        from backend.statistics.crew_hours.flight_query import build_flight_list_query, parse_flight_list

        for start, end in (("2024-02-30", "2024-03-01"), ("2024-12-31", "2024-12-01"), ('2024-12-01" } mutation { x', "2024-12-02")):
            with self.assertRaises(LeonContractError):
                build_flight_list_query(start, end)
        with self.assertRaises(LeonResponseError):
            parse_flight_list({"flightList": {}})
        with self.assertRaises(LeonResponseError):
            parse_flight_list({"flightList": [{"flightNid": 1, "startTimeUTC": "x", "endTimeUTC": "y"}]})


if __name__ == "__main__":
    unittest.main()

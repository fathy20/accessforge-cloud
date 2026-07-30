import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class TestLeonConfiguration(unittest.TestCase):
    api_key = "unit-test-key"
    base_url = "https://leon.invalid/api"

    def _load(self, values):
        from backend.statistics.crew_hours.config import load_leon_configuration
        with patch.dict(os.environ, values, clear=True):
            return load_leon_configuration()

    def test_required_values_and_timeout_validation(self):
        from backend.statistics.crew_hours.errors import LeonConfigurationError

        with self.assertRaises(LeonConfigurationError):
            self._load({"LEON_API_KEY": self.api_key})
        with self.assertRaises(LeonConfigurationError):
            self._load({"LEON_BASE_URL": self.base_url})
        with self.assertRaises(LeonConfigurationError):
            self._load({"LEON_BASE_URL": self.base_url, "LEON_API_KEY": self.api_key, "LEON_TIMEOUT_SECONDS": "0"})
        with self.assertRaises(LeonConfigurationError):
            self._load({"LEON_BASE_URL": self.base_url, "LEON_API_KEY": self.api_key, "LEON_TIMEOUT_SECONDS": "-1"})
        with self.assertRaises(LeonConfigurationError):
            self._load({"LEON_BASE_URL": self.base_url, "LEON_API_KEY": self.api_key, "LEON_TIMEOUT_SECONDS": "not-a-number"})

    def test_valid_values_are_trimmed_and_repr_is_redacted(self):
        configuration = self._load({
            "LEON_BASE_URL": f"  {self.base_url}/  ",
            "LEON_API_KEY": f"  {self.api_key}  ",
            "LEON_TIMEOUT_SECONDS": " 12.5 ",
        })

        self.assertEqual(configuration.base_url, self.base_url)
        self.assertEqual(configuration.api_key, self.api_key)
        self.assertEqual(configuration.timeout_seconds, 12.5)
        self.assertNotIn(self.api_key, repr(configuration))

    def test_timeout_defaults_when_omitted(self):
        configuration = self._load({"LEON_BASE_URL": self.base_url, "LEON_API_KEY": self.api_key})
        self.assertEqual(configuration.timeout_seconds, 30.0)


class TestConfiguredLeonClient(unittest.TestCase):
    api_key = "unit-test-key"

    def _client(self, transport):
        from backend.statistics.crew_hours.config import LeonConfiguration
        from backend.statistics.crew_hours.leon_client import ConfiguredCrewHoursLeonClient

        class HeaderBuilder:
            def __init__(self):
                self.received_key = None

            def build(self, api_key):
                self.received_key = api_key
                return {"X-Test-LEON-Auth": api_key}

        header_builder = HeaderBuilder()
        client = ConfiguredCrewHoursLeonClient(
            LeonConfiguration(base_url="https://leon.invalid/api", api_key=self.api_key, timeout_seconds=5),
            transport,
            header_builder,
        )
        return client, header_builder

    def test_injected_fake_transport_and_authentication_builder(self):
        from backend.statistics.crew_hours.transport import FakeLeonTransport, LeonRawResponse, LeonRequest

        transport = FakeLeonTransport(LeonRawResponse(status_code=200, body="{}"))
        client, header_builder = self._client(transport)
        result = client.send(LeonRequest(method="GET", url="future-resource"))

        self.assertEqual(result.payload, {})
        self.assertEqual(header_builder.received_key, self.api_key)
        self.assertEqual(len(transport.calls), 1)
        outbound_request, timeout_seconds = transport.calls[0]
        self.assertEqual(outbound_request.url, "https://leon.invalid/api/future-resource")
        self.assertEqual(outbound_request.headers["X-Test-LEON-Auth"], self.api_key)
        self.assertEqual(timeout_seconds, 5)

    def test_error_mapping_and_secret_redaction(self):
        from backend.statistics.crew_hours.errors import (
            LeonAuthenticationError,
            LeonResponseError,
            LeonTimeoutError,
            LeonTransportError,
        )
        from backend.statistics.crew_hours.transport import FakeLeonTransport, LeonRawResponse, LeonRequest

        request = LeonRequest(method="GET", url="future-resource")
        cases = [
            (FakeLeonTransport(error=httpx.TimeoutException("timeout")), LeonTimeoutError),
            (FakeLeonTransport(error=httpx.ConnectError("connection failed")), LeonTransportError),
            (FakeLeonTransport(LeonRawResponse(status_code=401, body="{}")), LeonAuthenticationError),
            (FakeLeonTransport(LeonRawResponse(status_code=403, body="{}")), LeonAuthenticationError),
            (FakeLeonTransport(LeonRawResponse(status_code=200, body="not-json")), LeonResponseError),
        ]
        for transport, exception_type in cases:
            client, _ = self._client(transport)
            with self.assertRaises(exception_type) as captured:
                client.send(request)
            self.assertNotIn(self.api_key, str(captured.exception))


class TestCrewHoursEndpointCompatibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="crew_hours_leon_"))
        cls.original_db_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"sqlite:///{cls.tmpdir / 'skeleton.db'}"
        for name in list(sys.modules):
            if name == "backend" or name.startswith("backend."):
                sys.modules.pop(name, None)
        import backend.main as main
        cls.main = main
        cls.client = TestClient(main.app)

    @classmethod
    def tearDownClass(cls):
        cls.main.app.dependency_overrides.clear()
        cls.client.close()
        import backend.database as database
        database.engine.dispose()
        for name in list(sys.modules):
            if name == "backend" or name.startswith("backend."):
                sys.modules.pop(name, None)
        if cls.original_db_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = cls.original_db_url
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_s2_endpoint_remains_exact_501(self):
        response = self.client.post("/api/statistics/crew-hours", json={})

        self.assertEqual(response.status_code, 501)
        self.assertEqual(response.json(), {
            "message": "Crew Hours backend skeleton only. Not implemented yet.",
        })


if __name__ == "__main__":
    unittest.main()

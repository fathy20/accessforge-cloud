import json
from typing import Annotated, Mapping, Protocol
from urllib.parse import urljoin, urlsplit

import httpx
from fastapi import Depends

from .config import LeonConfiguration, get_leon_configuration
from .errors import (
    LeonAuthenticationError,
    LeonContractError,
    LeonResponseError,
    LeonTimeoutError,
    LeonTransportError,
)
from .schemas import CrewHoursRequest
from .transport import LeonHttpTransport, LeonRawResponse, LeonRequest, LeonResponse, get_leon_transport


class LeonAuthenticationHeaderBuilder(Protocol):
    def build(self, api_key: str) -> Mapping[str, str]:
        ...


class MissingLeonAuthenticationHeaderBuilder:
    """Safe default until project documentation defines LEON authentication."""

    def build(self, api_key: str) -> Mapping[str, str]:
        raise LeonContractError("LEON authentication header format is not documented.")


def get_leon_authentication_header_builder() -> LeonAuthenticationHeaderBuilder:
    return MissingLeonAuthenticationHeaderBuilder()


class CrewHoursLeonClient(Protocol):
    def send(self, request: LeonRequest) -> LeonResponse:
        ...

    def fetch_crew_hours(self, request: CrewHoursRequest) -> None:
        ...


class ConfiguredCrewHoursLeonClient:
    def __init__(
        self,
        configuration: LeonConfiguration,
        transport: LeonHttpTransport,
        authentication_header_builder: LeonAuthenticationHeaderBuilder,
    ):
        self._configuration = configuration
        self._transport = transport
        self._authentication_header_builder = authentication_header_builder

    def send(self, request: LeonRequest) -> LeonResponse:
        parsed_url = urlsplit(request.url)
        if parsed_url.scheme or parsed_url.netloc:
            raise LeonContractError("LEON requests must use a relative path.")

        headers = dict(request.headers)
        headers.update(self._authentication_header_builder.build(self._configuration.api_key))
        outbound_request = LeonRequest(
            method=request.method,
            url=urljoin(f"{self._configuration.base_url}/", request.url.lstrip("/")),
            headers=headers,
            params=request.params,
            json_body=request.json_body,
        )
        response = self._send(outbound_request)
        if response.status_code in {401, 403}:
            raise LeonAuthenticationError("LEON authentication failed.")
        if response.status_code >= 400:
            raise LeonResponseError(f"LEON returned HTTP {response.status_code}.")
        try:
            payload = json.loads(response.body)
        except (TypeError, ValueError) as exc:
            raise LeonResponseError("LEON returned a malformed JSON response.") from exc
        if not isinstance(payload, dict):
            raise LeonResponseError("LEON returned a malformed JSON response.")
        return LeonResponse(status_code=response.status_code, payload=payload)

    def fetch_crew_hours(self, request: CrewHoursRequest) -> None:
        raise LeonContractError("Crew Hours LEON endpoint contract is not documented.")

    def _send(self, request: LeonRequest) -> LeonRawResponse:
        try:
            return self._transport.send(request, self._configuration.timeout_seconds)
        except httpx.TimeoutException as exc:
            raise LeonTimeoutError("LEON request timed out.") from exc
        except httpx.HTTPError as exc:
            raise LeonTransportError("LEON transport request failed.") from exc


class PlaceholderCrewHoursLeonClient:
    def send(self, request: LeonRequest) -> LeonResponse:
        raise LeonContractError("LEON client is not configured for the Crew Hours skeleton.")

    def fetch_crew_hours(self, request: CrewHoursRequest) -> None:
        raise LeonContractError("Crew Hours LEON endpoint contract is not documented.")


def get_crew_hours_leon_client() -> CrewHoursLeonClient:
    """Keep the S2 placeholder endpoint independent of LEON configuration."""
    return PlaceholderCrewHoursLeonClient()


def get_configured_crew_hours_leon_client(
    configuration: Annotated[LeonConfiguration, Depends(get_leon_configuration)],
    transport: Annotated[LeonHttpTransport, Depends(get_leon_transport)],
    authentication_header_builder: Annotated[
        LeonAuthenticationHeaderBuilder,
        Depends(get_leon_authentication_header_builder),
    ],
) -> CrewHoursLeonClient:
    return ConfiguredCrewHoursLeonClient(configuration, transport, authentication_header_builder)

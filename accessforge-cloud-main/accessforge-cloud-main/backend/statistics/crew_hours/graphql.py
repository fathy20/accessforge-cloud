import json
from typing import Any, Mapping

import httpx

from .config import LeonConfiguration
from .errors import LeonAuthenticationError, LeonResponseError, LeonTimeoutError, LeonTransportError
from .leon_client import LeonAuthenticationHeaderBuilder
from .token_provider import LeonAccessTokenProvider
from .transport import LeonHttpTransport, LeonRawResponse, LeonRequest


class LeonGraphQLExecutor:
    def __init__(
        self,
        configuration: LeonConfiguration,
        transport: LeonHttpTransport,
        token_provider: LeonAccessTokenProvider,
        authentication_header_builder: LeonAuthenticationHeaderBuilder,
    ):
        self._configuration = configuration
        self._transport = transport
        self._token_provider = token_provider
        self._authentication_header_builder = authentication_header_builder

    def execute_query(self, query: str, variables: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        for attempt in range(2):
            token = self._token_provider.get_access_token()
            response = self._send_query(query, variables, token)
            if response.status_code in {401, 403}:
                self._token_provider.invalidate()
                if attempt == 0:
                    continue
                raise LeonAuthenticationError("LEON GraphQL authentication failed.")
            return self._parse_response(response)
        raise AssertionError("GraphQL retry loop exhausted unexpectedly.")

    def _send_query(
        self,
        query: str,
        variables: Mapping[str, Any] | None,
        access_token: str,
    ) -> LeonRawResponse:
        request = LeonRequest(
            method="POST",
            url=f"{self._configuration.base_url}/api/graphql/",
            headers={
                "Content-Type": "application/json",
                **self._authentication_header_builder.build(access_token),
            },
            json_body={"query": query, "variables": dict(variables or {})},
        )
        try:
            return self._transport.send(request, self._configuration.timeout_seconds)
        except httpx.TimeoutException as exc:
            raise LeonTimeoutError("LEON GraphQL request timed out.") from exc
        except httpx.HTTPError as exc:
            raise LeonTransportError("LEON GraphQL transport failed.") from exc

    @staticmethod
    def _parse_response(response: LeonRawResponse) -> Mapping[str, Any]:
        if response.status_code < 200 or response.status_code >= 300:
            raise LeonResponseError(f"LEON GraphQL returned HTTP {response.status_code}.")
        try:
            payload = json.loads(response.body)
        except (TypeError, ValueError) as exc:
            raise LeonResponseError("LEON GraphQL response was not valid JSON.") from exc
        if not isinstance(payload, dict):
            raise LeonResponseError("LEON GraphQL response had an invalid shape.")
        if payload.get("errors"):
            raise LeonResponseError("LEON GraphQL returned errors.")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise LeonResponseError("LEON GraphQL response did not contain a data object.")
        return data

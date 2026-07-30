import json
import math
import threading
import time
from typing import Callable

import httpx

from .config import LeonConfiguration
from .errors import (
    LeonAuthenticationError,
    LeonContractError,
    LeonRateLimitError,
    LeonResponseError,
    LeonTimeoutError,
    LeonTransportError,
)
from .transport import LeonHttpTransport, LeonRawResponse, LeonRequest


DEFAULT_ACCESS_TOKEN_LIFETIME_SECONDS = 30 * 60
TOKEN_REFRESH_SAFETY_MARGIN_SECONDS = 60


class LeonAccessTokenProvider:
    def __init__(
        self,
        configuration: LeonConfiguration,
        transport: LeonHttpTransport,
        *,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._configuration = configuration
        self._transport = transport
        self._clock = clock
        self._lock = threading.Lock()
        self._access_token: str | None = None
        self._expires_at: float = 0.0

    def get_access_token(self) -> str:
        with self._lock:
            now = self._clock()
            if self._access_token is not None and now < self._expires_at - TOKEN_REFRESH_SAFETY_MARGIN_SECONDS:
                return self._access_token
            return self._refresh_locked(now)

    def invalidate(self) -> None:
        with self._lock:
            self._access_token = None
            self._expires_at = 0.0

    def _refresh_locked(self, now: float) -> str:
        response = self._send_refresh_request()
        payload = self._parse_refresh_response(response)
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token.strip():
            raise LeonContractError("LEON refresh response did not contain a usable access_token.")
        lifetime = self._access_token_lifetime(payload)
        self._access_token = access_token.strip()
        self._expires_at = now + lifetime
        return self._access_token

    def _send_refresh_request(self) -> LeonRawResponse:
        request = LeonRequest(
            method="POST",
            url=f"{self._configuration.base_url}/access_token/refresh/",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            form_data={"refresh_token": self._configuration.refresh_token},
        )
        try:
            response = self._transport.send(request, self._configuration.timeout_seconds)
        except httpx.TimeoutException as exc:
            raise LeonTimeoutError("LEON access-token refresh timed out.") from exc
        except httpx.HTTPError as exc:
            raise LeonTransportError("LEON access-token refresh transport failed.") from exc

        if response.status_code in {401, 403}:
            raise LeonAuthenticationError("LEON refresh authentication failed.")
        if response.status_code == 400:
            raise LeonAuthenticationError("LEON refresh request was rejected.")
        if response.status_code == 429:
            raise LeonRateLimitError(_parse_retry_after(response.headers.get("Retry-After")))
        if response.status_code < 200 or response.status_code >= 300:
            raise LeonResponseError(f"LEON refresh returned HTTP {response.status_code}.")
        return response

    @staticmethod
    def _parse_refresh_response(response: LeonRawResponse) -> dict:
        try:
            payload = json.loads(response.body)
        except (TypeError, ValueError) as exc:
            raise LeonResponseError("LEON refresh response was not valid JSON.") from exc
        if not isinstance(payload, dict):
            raise LeonResponseError("LEON refresh response had an invalid shape.")
        return payload

    @staticmethod
    def _access_token_lifetime(payload: dict) -> float:
        if "expires_in" not in payload:
            return float(DEFAULT_ACCESS_TOKEN_LIFETIME_SECONDS)
        expires_in = payload["expires_in"]
        if expires_in is None or isinstance(expires_in, bool):
            raise LeonContractError("LEON refresh response had an invalid expires_in value.")
        try:
            lifetime = float(expires_in)
        except (TypeError, ValueError) as exc:
            raise LeonContractError("LEON refresh response had an invalid expires_in value.") from exc
        if not math.isfinite(lifetime) or lifetime <= 0:
            raise LeonContractError("LEON refresh response had an invalid expires_in value.")
        return lifetime


def _parse_retry_after(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    if not math.isfinite(parsed) or parsed < 0:
        return None
    return int(parsed)

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

import httpx


SENSITIVE_HEADER_NAMES = {"authorization", "x-api-key"}
SENSITIVE_FORM_FIELD_NAMES = {"refresh_token", "access_token"}


@dataclass(frozen=True)
class LeonRequest:
    method: str
    url: str
    headers: Mapping[str, str] = field(default_factory=dict)
    params: Mapping[str, str] | None = None
    json_body: Mapping[str, Any] | None = None
    form_data: Mapping[str, str] | None = None


@dataclass(frozen=True)
class LeonRawResponse:
    status_code: int
    body: str
    headers: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class LeonResponse:
    status_code: int
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class LeonErrorResponse:
    status_code: int
    message: str


@dataclass(frozen=True)
class LeonRequestRecord:
    method: str
    url: str
    header_names: tuple[str, ...]
    form_field_names: tuple[str, ...]
    json_body: Mapping[str, Any] | None


class LeonHttpTransport(Protocol):
    def send(self, request: LeonRequest, timeout_seconds: float) -> LeonRawResponse:
        ...


class HttpxLeonTransport:
    """One-shot HTTP transport that closes its owned httpx client per request."""

    def send(self, request: LeonRequest, timeout_seconds: float) -> LeonRawResponse:
        with httpx.Client(timeout=httpx.Timeout(timeout_seconds)) as client:
            response = client.request(
                method=request.method,
                url=request.url,
                headers=dict(request.headers),
                params=request.params,
                json=request.json_body,
                data=request.form_data,
            )
        return LeonRawResponse(
            status_code=response.status_code,
            body=response.text,
            headers=dict(response.headers),
        )


class FakeLeonTransport:
    """Deterministic test transport; it records metadata only and never opens a network connection."""

    def __init__(self, responses: list[LeonRawResponse] | None = None, error: Exception | None = None):
        self._responses = list(responses or [])
        self.error = error
        self.calls: list[LeonRequestRecord] = []

    def send(self, request: LeonRequest, timeout_seconds: float) -> LeonRawResponse:
        self.calls.append(LeonRequestRecord(
            method=request.method,
            url=request.url,
            header_names=tuple(sorted(request.headers)),
            form_field_names=tuple(sorted((request.form_data or {}).keys())),
            json_body=request.json_body,
        ))
        if self.error is not None:
            raise self.error
        if not self._responses:
            raise AssertionError("FakeLeonTransport requires a queued response or error.")
        return self._responses.pop(0)


class LeonAuthenticationHeaderBuilder(Protocol):
    def build(self, access_token: str) -> Mapping[str, str]:
        ...


class BearerAccessTokenHeaderBuilder:
    def build(self, access_token: str) -> Mapping[str, str]:
        return {"Authorization": f"Bearer {access_token}"}


def get_leon_authentication_header_builder() -> LeonAuthenticationHeaderBuilder:
    return BearerAccessTokenHeaderBuilder()


def get_leon_transport() -> LeonHttpTransport:
    return HttpxLeonTransport()

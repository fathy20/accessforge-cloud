from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

import httpx


@dataclass(frozen=True)
class LeonRequest:
    method: str
    url: str
    headers: Mapping[str, str] = field(default_factory=dict)
    params: Mapping[str, str] | None = None
    json_body: Mapping[str, Any] | None = None


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
            )
        return LeonRawResponse(
            status_code=response.status_code,
            body=response.text,
            headers=dict(response.headers),
        )


class FakeLeonTransport:
    """Deterministic test transport; it never opens a network connection."""

    def __init__(self, response: LeonRawResponse | None = None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.calls: list[tuple[LeonRequest, float]] = []

    def send(self, request: LeonRequest, timeout_seconds: float) -> LeonRawResponse:
        self.calls.append((request, timeout_seconds))
        if self.error is not None:
            raise self.error
        if self.response is None:
            raise AssertionError("FakeLeonTransport requires a response or error.")
        return self.response


def get_leon_transport() -> LeonHttpTransport:
    return HttpxLeonTransport()

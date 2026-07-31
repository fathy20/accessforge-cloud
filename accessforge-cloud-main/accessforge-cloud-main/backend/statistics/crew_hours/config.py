import math
import os
from dataclasses import dataclass, field
from typing import Mapping
from urllib.parse import urlsplit

from .errors import LeonConfigurationError


DEFAULT_LEON_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class LeonConfiguration:
    base_url: str
    refresh_token: str = field(repr=False)
    timeout_seconds: float = DEFAULT_LEON_TIMEOUT_SECONDS


def load_leon_configuration(
    environment: Mapping[str, str] | None = None,
    *,
    allow_insecure_base_url: bool = False,
) -> LeonConfiguration:
    values = os.environ if environment is None else environment
    base_url = (values.get("LEON_BASE_URL") or "").strip()
    refresh_token = (values.get("LEON_REFRESH_TOKEN") or "").strip()
    timeout_text = (values.get("LEON_TIMEOUT_SECONDS") or str(DEFAULT_LEON_TIMEOUT_SECONDS)).strip()

    if not base_url:
        raise LeonConfigurationError("LEON_BASE_URL is required.")
    if not refresh_token:
        raise LeonConfigurationError("LEON_REFRESH_TOKEN is required.")

    parsed_base_url = urlsplit(base_url)
    allowed_schemes = {"https"}
    if allow_insecure_base_url:
        allowed_schemes.add("http")
    if parsed_base_url.scheme not in allowed_schemes or not parsed_base_url.netloc:
        raise LeonConfigurationError("LEON_BASE_URL must be an HTTPS URL.")
    if parsed_base_url.query or parsed_base_url.fragment:
        raise LeonConfigurationError("LEON_BASE_URL must not contain a query or fragment.")

    try:
        timeout_seconds = float(timeout_text)
    except ValueError as exc:
        raise LeonConfigurationError("LEON_TIMEOUT_SECONDS must be a positive finite number.") from exc
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise LeonConfigurationError("LEON_TIMEOUT_SECONDS must be a positive finite number.")

    return LeonConfiguration(
        base_url=base_url.rstrip("/"),
        refresh_token=refresh_token,
        timeout_seconds=timeout_seconds,
    )


def get_leon_configuration() -> LeonConfiguration:
    return load_leon_configuration()

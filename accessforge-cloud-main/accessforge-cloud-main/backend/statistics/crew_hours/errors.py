class LeonConfigurationError(Exception):
    """Raised when LEON runtime configuration is absent or invalid."""


class LeonTransportError(Exception):
    """Raised when LEON transport fails without an HTTP response."""


class LeonAuthenticationError(Exception):
    """Raised when LEON rejects authentication."""


class LeonTimeoutError(LeonTransportError):
    """Raised when a LEON transport operation times out."""


class LeonResponseError(Exception):
    """Raised when a LEON response is unsuccessful or malformed."""


class LeonContractError(Exception):
    """Raised when a LEON contract cannot be satisfied safely."""


class LeonRateLimitError(LeonResponseError):
    """Raised when LEON rate-limits a request."""

    def __init__(self, retry_after_seconds: int | None):
        self.retry_after_seconds = retry_after_seconds
        super().__init__("LEON rate limit exceeded.")

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
    """Raised when an undocumented LEON contract would be required."""

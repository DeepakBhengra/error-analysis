class DatadogError(Exception):
    """Base error for Datadog API interactions."""


class DatadogAuthError(DatadogError):
    """Authentication or authorization failed."""


class DatadogRateLimitError(DatadogError):
    """Rate limit exceeded."""


class DatadogSearchError(DatadogError):
    """Log search request failed."""

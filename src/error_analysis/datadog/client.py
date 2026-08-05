from __future__ import annotations

import time
from typing import Any

import httpx

from error_analysis.config import Settings
from error_analysis.datadog.errors import (
    DatadogAuthError,
    DatadogError,
    DatadogRateLimitError,
    DatadogSearchError,
)
from error_analysis.logging_config import get_logger

logger = get_logger("datadog.client")


def _auth_headers(settings: Settings) -> dict[str, str]:
    """Build Datadog auth headers for API/App keys or an access token."""
    token = settings.dd_access_token.strip()
    if token:
        # Personal Access Token / Service Access Token (Bearer).
        # See: https://docs.datadoghq.com/account_management/personal-access-tokens/
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
    return {
        "DD-API-KEY": settings.dd_api_key,
        "DD-APPLICATION-KEY": settings.dd_app_key,
        "Content-Type": "application/json",
    }


class DatadogClient:
    RETRYABLE_STATUS = {429, 500, 502, 503, 504}
    MAX_RETRIES = 3

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self._client = client or httpx.Client(
            base_url=settings.api_base_url,
            headers=_auth_headers(settings),
            timeout=60.0,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> DatadogClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def validate_credentials(self) -> dict[str, Any]:
        """Validate Datadog credentials.

        Classic API/App keys use ``/api/v1/validate``. Access tokens use a
        minimal Logs search so we confirm the token can read logs.
        """
        if self.settings.uses_access_token:
            self.search_logs(
                {
                    "filter": {
                        "from": "now-1m",
                        "to": "now",
                        "query": "*",
                    },
                    "page": {"limit": 1},
                }
            )
            return {"valid": True, "auth": "access_token"}
        return self._request("GET", "api/v1/validate")

    def search_logs(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "api/v2/logs/events/search", json=body)

    def _auth_hint(self) -> str:
        if self.settings.uses_access_token:
            return (
                " Check DD_ACCESS_TOKEN in .env (Personal or Service Access Token) "
                "and that it includes logs read scope. DD_SITE must match your org."
            )
        return (
            " Check DD_API_KEY and DD_APP_KEY in .env, or set DD_ACCESS_TOKEN. "
            "Application keys are 40 hex characters (Datadog > Organization "
            "Settings > Application Keys) and need Logs read access."
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        last_error: Exception | None = None

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                response = self._client.request(method, path, json=json)
            except httpx.RequestError as exc:
                last_error = exc
                if attempt < self.MAX_RETRIES:
                    logger.warning(
                        "Datadog %s %s network error (attempt %s/%s): %s",
                        method,
                        path,
                        attempt + 1,
                        self.MAX_RETRIES + 1,
                        exc,
                    )
                    time.sleep(2**attempt)
                    continue
                host = str(self.settings.api_base_url).rstrip("/")
                hint = ""
                err = str(exc)
                if "getaddrinfo" in err or "Name or service not known" in err:
                    hint = (
                        " DNS lookup failed — check network/VPN and that "
                        f"DD_SITE resolves (current API base: {host})."
                    )
                message = f"Request failed: {exc}.{hint}"
                logger.error("Datadog %s %s failed after retries: %s", method, path, message)
                raise DatadogError(message) from exc

            if response.status_code == 401 or response.status_code == 403:
                message = (
                    f"Authentication failed ({response.status_code}): "
                    f"{response.text}.{self._auth_hint()}"
                )
                logger.error("Datadog %s %s auth failed: %s", method, path, message)
                raise DatadogAuthError(message)

            if response.status_code == 429:
                if attempt < self.MAX_RETRIES:
                    retry_after = int(response.headers.get("Retry-After", 2**attempt))
                    logger.warning(
                        "Datadog %s %s rate limited; retrying in %ss (attempt %s/%s)",
                        method,
                        path,
                        retry_after,
                        attempt + 1,
                        self.MAX_RETRIES + 1,
                    )
                    time.sleep(retry_after)
                    continue
                logger.error("Datadog %s %s rate limit exceeded", method, path)
                raise DatadogRateLimitError("Rate limit exceeded")

            if response.status_code in self.RETRYABLE_STATUS:
                if attempt < self.MAX_RETRIES:
                    logger.warning(
                        "Datadog %s %s returned %s; retrying (attempt %s/%s)",
                        method,
                        path,
                        response.status_code,
                        attempt + 1,
                        self.MAX_RETRIES + 1,
                    )
                    time.sleep(2**attempt)
                    continue
                message = f"Request failed ({response.status_code}): {response.text}"
                logger.error("Datadog %s %s failed: %s", method, path, message)
                raise DatadogSearchError(message)

            if response.status_code >= 400:
                message = f"Request failed ({response.status_code}): {response.text}"
                logger.error("Datadog %s %s failed: %s", method, path, message)
                raise DatadogSearchError(message)

            return response.json()

        message = f"Request failed after retries: {last_error}"
        logger.error("Datadog %s %s failed: %s", method, path, message)
        raise DatadogError(message)

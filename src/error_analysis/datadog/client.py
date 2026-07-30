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


class DatadogClient:
    RETRYABLE_STATUS = {429, 500, 502, 503, 504}
    MAX_RETRIES = 3

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self._client = client or httpx.Client(
            base_url=settings.api_base_url,
            headers={
                "DD-API-KEY": settings.dd_api_key,
                "DD-APPLICATION-KEY": settings.dd_app_key,
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> DatadogClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def validate_credentials(self) -> dict[str, Any]:
        return self._request("GET", "api/v1/validate")

    def search_logs(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "api/v2/logs/events/search", json=body)

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
                raise DatadogError(f"Request failed: {exc}.{hint}") from exc

            if response.status_code == 401 or response.status_code == 403:
                hint = (
                    " Check DD_API_KEY and DD_APP_KEY in .env. Application keys "
                    "are 40 hex characters (Datadog > Organization Settings > "
                    "Application Keys) and need Logs read access."
                )
                raise DatadogAuthError(
                    f"Authentication failed ({response.status_code}): "
                    f"{response.text}.{hint}"
                )

            if response.status_code == 429:
                if attempt < self.MAX_RETRIES:
                    retry_after = int(response.headers.get("Retry-After", 2**attempt))
                    time.sleep(retry_after)
                    continue
                raise DatadogRateLimitError("Rate limit exceeded")

            if response.status_code in self.RETRYABLE_STATUS:
                if attempt < self.MAX_RETRIES:
                    time.sleep(2**attempt)
                    continue
                raise DatadogSearchError(
                    f"Request failed ({response.status_code}): {response.text}"
                )

            if response.status_code >= 400:
                raise DatadogSearchError(
                    f"Request failed ({response.status_code}): {response.text}"
                )

            return response.json()

        raise DatadogError(f"Request failed after retries: {last_error}")

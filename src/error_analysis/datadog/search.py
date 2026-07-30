from __future__ import annotations

from typing import Any, Iterator

from error_analysis.datadog.client import DatadogClient
from error_analysis.datadog.models import LogSearchFilter, LogSearchParams


def search_logs(
    client: DatadogClient,
    params: LogSearchParams,
) -> Iterator[dict[str, Any]]:
    cursor: str | None = None

    while True:
        body = params.to_api_body(cursor=cursor)
        response = client.search_logs(body)

        data = response.get("data") or []
        for event in data:
            yield event

        meta = response.get("meta") or {}
        page = meta.get("page") or {}
        cursor = page.get("after")

        if not cursor or not data:
            break

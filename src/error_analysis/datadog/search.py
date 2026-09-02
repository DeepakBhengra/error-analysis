from __future__ import annotations

from collections.abc import Callable
from typing import Any, Iterator

from error_analysis.datadog.client import DatadogClient
from error_analysis.datadog.models import LogSearchFilter, LogSearchParams


def search_logs(
    client: DatadogClient,
    params: LogSearchParams,
    *,
    should_stop: Callable[[bool], bool] | None = None,
) -> Iterator[dict[str, Any]]:
    """Iterate log events, optionally stopping before the next page.

    ``should_stop`` receives ``last_page`` (True when the current response has
    no further pages) and returns True to end pagination early.
    """
    cursor: str | None = None

    while True:
        body = params.to_api_body(cursor=cursor)
        response = client.search_logs(body)

        data = response.get("data") or []
        meta = response.get("meta") or {}
        page = meta.get("page") or {}
        next_cursor = page.get("after")
        is_last_page = not next_cursor or not data

        for event in data:
            yield event
            if should_stop is not None and should_stop(is_last_page):
                return

        if not next_cursor or not data:
            break
        cursor = next_cursor
